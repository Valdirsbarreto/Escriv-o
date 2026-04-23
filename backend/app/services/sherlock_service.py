"""
Escrivão AI — Agente Sherlock
Motor de inteligência investigativa estratégica.

Camadas de raciocínio:
  1. Cross-Check     — confronta contradições entre depoimentos, NER e documentos
  2. Tipicidade      — mapeia elementares do crime, identifica o que está provado/faltando
  3. Backlog         — diligências priorizadas por urgência (prescrição, perecimento)
  4. Tese            — constrói teoria da autoria com base probatória
  5. Advogado Diabo  — tenta derrubar a tese para antecipar a defesa

Usa: RelatorioInicial + SínteseInvestigativa + Fichas + OSINT + peças indexadas
Cache: 6h por inquérito (forçável com ?forcar=true)
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


def _recuperar_json_truncado(raw: str) -> dict:
    """
    Tenta recuperar um JSON truncado pelo limite de tokens do LLM.
    Fecha colchetes/chaves pendentes até obter JSON válido.
    """
    # Remove texto parcial após a última vírgula ou valor completo
    text = raw.rstrip()

    # Remove trailing comma se houver
    if text.endswith(","):
        text = text[:-1]

    # Conta estruturas abertas e fecha na ordem inversa
    stack = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ("{", "["):
            stack.append("}" if ch == "{" else "]")
        elif ch in ("}", "]"):
            if stack and stack[-1] == ch:
                stack.pop()

    # Fecha as estruturas abertas em ordem inversa
    closing = "".join(reversed(stack))
    recovered = text + closing

    try:
        result = json.loads(recovered)
        logger.warning(f"[SHERLOCK] JSON truncado recuperado — fechou {len(stack)} estrutura(s)")
        return result
    except json.JSONDecodeError as e:
        logger.error(f"[SHERLOCK] Falha ao recuperar JSON truncado: {e}")
        # Retorna estrutura mínima com campos corretos para não quebrar o frontend
        return {
            "_erro": "JSON truncado — contexto muito longo. Use 'Regenerar' para tentar novamente.",
            "resumo_executivo": "⚠️ Análise incompleta — o contexto do inquérito excedeu o limite de tokens. Clique em 'Regenerar' para nova tentativa.",
            "recomendacao_final": "Regenerar a análise Sherlock com o botão 'Regenerar' acima.",
            "crimes_identificados": [],
            "contradicoes": [],
            "checklist_tipicidade": [],
            "backlog_diligencias": [],
            "tese_autoria": "",
            "vulnerabilidades_defesa": [],
        }


class SherlockService:
    def __init__(self):
        self.llm = LLMService()

    # ── Montagem de contexto ──────────────────────────────────────────────────

    async def _montar_contexto(self, db: AsyncSession, inquerito_id: uuid.UUID) -> Dict[str, Any]:
        """Agrega todos os dados disponíveis sobre o inquérito."""
        from app.models.inquerito import Inquerito
        from app.models.documento_gerado import DocumentoGerado
        from app.models.resultado_agente import ResultadoAgente
        from app.models.pessoa import Pessoa
        from app.models.empresa import Empresa
        from app.models.documento import Documento

        ctx: Dict[str, Any] = {
            "inquerito": None,
            "relatorio_inicial": None,
            "sintese": None,
            "pessoas": [],
            "empresas": [],
            "pecas": [],
            "fichas": [],
            "osint_web": [],
            "osint_gratuito": [],
            "analises_preliminares": [],
        }

        # Inquérito
        inq = await db.get(Inquerito, inquerito_id)
        if inq:
            ctx["inquerito"] = {
                "numero": inq.numero,
                "descricao": inq.descricao or "",
                "status": inq.estado_atual,
            }

        # Documentos gerados
        res_docs = await db.execute(
            select(DocumentoGerado)
            .where(DocumentoGerado.inquerito_id == inquerito_id)
            .order_by(DocumentoGerado.created_at.desc())
        )
        for doc in res_docs.scalars().all():
            if doc.tipo == "relatorio_inicial" and not ctx["relatorio_inicial"]:
                ctx["relatorio_inicial"] = doc.conteudo[:8000]
            elif doc.tipo == "sintese_investigativa" and not ctx["sintese"]:
                ctx["sintese"] = doc.conteudo[:3000]

        # Pessoas
        res_pessoas = await db.execute(
            select(Pessoa).where(Pessoa.inquerito_id == inquerito_id)
        )
        pessoas = res_pessoas.scalars().all()
        for p in pessoas:
            ctx["pessoas"].append({
                "id": str(p.id),
                "nome": p.nome,
                "tipo_pessoa": p.tipo_pessoa,
                "cpf": p.cpf,
                "observacoes": p.observacoes or "",
                "resumo_contexto": p.resumo_contexto or "",
            })

        # Empresas
        try:
            from app.models.empresa import Empresa
            res_emp = await db.execute(
                select(Empresa).where(Empresa.inquerito_id == inquerito_id)
            )
            for e in res_emp.scalars().all():
                ctx["empresas"].append({
                    "nome": e.nome,
                    "cnpj": getattr(e, "cnpj", None),
                    "tipo_pessoa": getattr(e, "tipo_pessoa", None),
                    "observacoes": getattr(e, "observacoes", "") or "",
                })
        except Exception:
            pass

        # Peças indexadas (máximo 20 — evita contexto gigante em casos com muitas peças)
        res_docs2 = await db.execute(
            select(Documento.nome_arquivo, Documento.tipo_peca, Documento.status_processamento)
            .where(Documento.inquerito_id == inquerito_id)
            .limit(20)
        )
        for row in res_docs2.all():
            ctx["pecas"].append({
                "nome": row.nome_arquivo,
                "tipo": row.tipo_peca,
                "status": row.status_processamento,
            })

        # ResultadoAgente — fichas, OSINT, análises
        res_agentes = await db.execute(
            select(ResultadoAgente)
            .where(ResultadoAgente.inquerito_id == inquerito_id)
            .order_by(ResultadoAgente.created_at.desc())
        )
        vistos = set()
        for ra in res_agentes.scalars().all():
            key = (ra.tipo_agente, str(ra.referencia_id))
            if key in vistos:
                continue
            vistos.add(key)

            if ra.tipo_agente in ("ficha_pessoa", "ficha_empresa"):
                ctx["fichas"].append({
                    "tipo": ra.tipo_agente,
                    "referencia_id": str(ra.referencia_id),
                    "dados": ra.resultado_json,
                })
            elif ra.tipo_agente == "osint_web_pessoa":
                ctx["osint_web"].append({
                    "referencia_id": str(ra.referencia_id),
                    "dados": ra.resultado_json,
                })
            elif ra.tipo_agente == "osint_gratuito":
                ctx["osint_gratuito"].append({
                    "referencia_id": str(ra.referencia_id),
                    "dados": ra.resultado_json,
                })
            elif ra.tipo_agente in ("analise_preliminar_pessoa", "analise_preliminar_empresa"):
                ctx["analises_preliminares"].append({
                    "referencia_id": str(ra.referencia_id),
                    "dados": ra.resultado_json,
                })

        return ctx

    def _formatar_contexto_para_prompt(self, ctx: Dict[str, Any]) -> str:
        """Serializa o contexto em texto estruturado para o prompt."""
        partes = []

        if ctx["inquerito"]:
            inq = ctx["inquerito"]
            partes.append(f"=== INQUÉRITO {inq['numero']} ===\n{inq['descricao']}\nStatus: {inq['status']}")

        if ctx["relatorio_inicial"]:
            partes.append(f"=== RELATÓRIO INICIAL ===\n{ctx['relatorio_inicial']}")

        if ctx["sintese"]:
            partes.append(f"=== SÍNTESE INVESTIGATIVA ===\n{ctx['sintese']}")

        if ctx["pessoas"]:
            linhas = ["=== PESSOAS NOS AUTOS ==="]
            for p in ctx["pessoas"]:
                linha = f"• {p['nome']} | Tipo: {p['tipo_pessoa']} | CPF: {p['cpf'] or 'não consta'}"
                if p["resumo_contexto"]:
                    linha += f"\n  Contexto: {p['resumo_contexto'][:300]}"
                if p["observacoes"]:
                    linha += f"\n  Obs: {p['observacoes'][:200]}"
                linhas.append(linha)
            partes.append("\n".join(linhas))

        if ctx["empresas"]:
            linhas = ["=== EMPRESAS NOS AUTOS ==="]
            for e in ctx["empresas"]:
                linhas.append(f"• {e['nome']} | CNPJ: {e['cnpj'] or 'não consta'} | {e['observacoes'][:200]}")
            partes.append("\n".join(linhas))

        if ctx["pecas"]:
            linhas = ["=== PEÇAS INDEXADAS ==="]
            for p in ctx["pecas"]:
                linhas.append(f"• [{p['tipo'] or 'não classificado'}] {p['nome']} ({p['status']})")
            partes.append("\n".join(linhas))

        # Análises preliminares — resumo das flags
        for ap in ctx["analises_preliminares"][:5]:
            d = ap.get("dados") or {}
            if d.get("nivel_risco") or d.get("alertas"):
                ref = ap["referencia_id"]
                partes.append(
                    f"=== ANÁLISE PRELIMINAR (ref {ref[:8]}) ===\n"
                    f"Risco: {d.get('nivel_risco', '?')} | Alertas: {', '.join((d.get('alertas') or [])[:3])}"
                )

        # OSINT gratuito — sócios e sanções
        for og in ctx["osint_gratuito"][:5]:
            d = og.get("dados") or {}
            if d.get("socios_de_interesse") or d.get("alertas"):
                partes.append(
                    f"=== OSINT RECEITA FEDERAL (ref {og['referencia_id'][:8]}) ===\n"
                    f"Situação: {d.get('situacao_cadastral', '?')}\n"
                    f"Alertas: {json.dumps(d.get('alertas', []), ensure_ascii=False)}\n"
                    f"Sócios: {json.dumps([s.get('nome') for s in d.get('socios_de_interesse', [])], ensure_ascii=False)}"
                )

        # OSINT web — alertas
        for ow in ctx["osint_web"][:3]:
            d = ow.get("dados") or {}
            if d.get("alertas"):
                partes.append(
                    f"=== OSINT WEB (ref {ow['referencia_id'][:8]}) ===\n"
                    f"Alertas: {json.dumps(d.get('alertas', [])[:3], ensure_ascii=False)}"
                )

        return "\n\n".join(partes)

    # ── Geração da análise Sherlock ───────────────────────────────────────────

    async def gerar_estrategia(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        forcar: bool = False,
    ) -> Dict[str, Any]:
        """
        Gera análise estratégica completa (5 camadas) para o inquérito.
        Cache de 6h em ResultadoAgente (tipo_agente='sherlock').
        """
        from app.models.resultado_agente import ResultadoAgente
        from app.core.prompts import PROMPT_SHERLOCK

        # ── Cache ──────────────────────────────────────────────────────────────
        if not forcar:
            cache_stmt = (
                select(ResultadoAgente)
                .where(and_(
                    ResultadoAgente.inquerito_id == inquerito_id,
                    ResultadoAgente.tipo_agente == "sherlock",
                ))
                .order_by(ResultadoAgente.created_at.desc())
                .limit(1)
            )
            cached = (await db.execute(cache_stmt)).scalar_one_or_none()
            if cached:
                age = datetime.utcnow() - cached.created_at.replace(tzinfo=None)
                if age < timedelta(hours=6):
                    logger.info(f"[SHERLOCK] Cache hit para inquérito {inquerito_id}")
                    return cached.resultado_json

        # ── Montar contexto ────────────────────────────────────────────────────
        logger.info(f"[SHERLOCK] Iniciando análise estratégica para {inquerito_id}")
        ctx = await self._montar_contexto(db, inquerito_id)
        contexto_str = self._formatar_contexto_para_prompt(ctx)

        if len(contexto_str) < 200:
            raise ValueError(
                "Dados insuficientes para análise Sherlock. "
                "Execute primeiro o Relatório Inicial e a Síntese."
            )

        # ── LLM ───────────────────────────────────────────────────────────────
        prompt = PROMPT_SHERLOCK.format(contexto=contexto_str)

        result = await self.llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            tier="premium",
            temperature=0.2,
            max_tokens=65536,
            json_mode=True,
            agente="Sherlock",
        )

        raw = result["content"].strip()
        try:
            analise = json.loads(raw)
        except json.JSONDecodeError:
            # Tenta recuperar JSON truncado fechando chaves/colchetes pendentes
            analise = _recuperar_json_truncado(raw)
        analise["_gerado_em"] = datetime.utcnow().isoformat()
        analise["_modelo"] = result.get("model")
        analise["_inquerito"] = ctx["inquerito"]

        # ── Salvar cache ───────────────────────────────────────────────────────
        # Remove cache antigo
        old = (await db.execute(
            select(ResultadoAgente)
            .where(and_(
                ResultadoAgente.inquerito_id == inquerito_id,
                ResultadoAgente.tipo_agente == "sherlock",
            ))
        )).scalars().all()
        for o in old:
            await db.delete(o)

        db.add(ResultadoAgente(
            inquerito_id=inquerito_id,
            tipo_agente="sherlock",
            resultado_json=analise,
            modelo_llm=result.get("model"),
        ))
        await db.commit()

        n_dilig = len(analise.get("backlog_diligencias", []))
        n_contra = len(analise.get("contradicoes", []))
        logger.info(
            f"[SHERLOCK] Análise concluída — {n_contra} contradições, "
            f"{n_dilig} diligências sugeridas"
        )
        return analise
