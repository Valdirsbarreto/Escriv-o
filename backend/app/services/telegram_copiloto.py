"""
Escrivão AI — Copiloto Telegram
Orquestra mensagens recebidas via Telegram: detecta intenção via LLM e
despacha para os serviços apropriados (busca RAG, agenda, índices, etc.).
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.inquerito import Inquerito
from app.models.intimacao import Intimacao
from app.models.pessoa import Pessoa
from app.services.llm_service import LLMService
from app.services.copiloto_service import CopilotoService

logger = logging.getLogger(__name__)

# ── Mapa de estados legíveis ──────────────────────────────────────────────────

ESTADO_LABEL = {
    "recebido": "Recebido",
    "indexando": "Indexando documentos",
    "triagem": "Em triagem",
    "investigacao": "Em investigação",
    "diligencias": "Diligências em andamento",
    "analise": "Em análise",
    "relatorio": "Elaborando relatório",
    "encerramento": "Em encerramento",
    "arquivamento": "Arquivado",
}

# ── System prompt do dispatcher ───────────────────────────────────────────────

DISPATCHER_PROMPT = """Você é o despachante do Escrivão AI via Telegram.
Analise a mensagem do usuário e retorne um JSON com a ação a executar.

Contexto atual:
- Inquérito em foco: {inquerito_atual}
- Histórico recente: {historico_resumido}

Ações disponíveis:
- listar_inqueritos: Lista inquéritos cadastrados. Parâmetros: {{}}
- status_inquerito: Detalhes de um inquérito específico. Parâmetros: {{"numero_ip": "ex: 915-001234/2024"}}
- busca_autos: Busca semântica nos documentos de um inquérito. Parâmetros: {{"numero_ip": "número (use inquerito_atual se já mencionado)", "query": "o que pesquisar"}}
- agenda: Próximas oitivas, audiências e intimações. Parâmetros: {{}}
- ficha_pessoa: Consulta pessoa nos índices do inquérito. Parâmetros: {{"nome": "nome da pessoa", "numero_ip": "inquérito (use inquerito_atual se já mencionado)", "cpf": "CPF se informado (opcional)"}}
- ajuda: Lista de comandos disponíveis. Parâmetros: {{}}
- conversa: Saudações, agradecimentos ou perguntas gerais sem ação específica. Parâmetros: {{"resposta": "sua resposta amigável e concisa (máximo 3 linhas)"}}

IMPORTANTE: Retorne APENAS JSON válido. Exemplo: {{"acao": "listar_inqueritos", "parametros": {{}}}}"""


class TelegramCopilotoService:
    """
    Despachante principal do bot Telegram do Escrivão.

    Fluxo por mensagem:
    1. Carrega contexto (histórico + inquérito atual) do Redis
    2. Chama LLM standard para classificar intenção → JSON de ação
    3. Executa a ação com os serviços existentes
    4. Atualiza contexto no Redis
    5. Retorna texto formatado em HTML para o Telegram
    """

    def __init__(self):
        self.llm = LLMService()
        self._copiloto = None
        self._redis = None

    def _get_copiloto(self):
        if self._copiloto is None:
            self._copiloto = CopilotoService()
        return self._copiloto

    # ── Redis ─────────────────────────────────────────────────────────────────

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    async def _load_ctx(self, chat_id: int) -> dict:
        r = await self._get_redis()
        raw = await r.get(f"telegram:ctx:{chat_id}")
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass
        return {"historico": [], "inquerito_atual": None}

    async def _save_ctx(self, chat_id: int, ctx: dict) -> None:
        r = await self._get_redis()
        await r.setex(
            f"telegram:ctx:{chat_id}",
            86400,  # 24 horas
            json.dumps(ctx, ensure_ascii=False, default=str),
        )

    # ── Entry point ───────────────────────────────────────────────────────────

    async def processar_mensagem(
        self, chat_id: int, mensagem: str, db: AsyncSession
    ) -> str:
        """Processa uma mensagem recebida e retorna a resposta formatada em HTML."""

        # Comandos diretos sem passar pelo LLM
        if mensagem.strip().lower() in ("/start", "/ajuda", "/help", "ajuda", "help"):
            return _mensagem_ajuda()

        ctx = await self._load_ctx(chat_id)

        # Dispatcher via LLM
        acao_json = await self._dispatch(mensagem, ctx)
        acao = acao_json.get("acao", "conversa")
        params = acao_json.get("parametros", {})

        logger.info(f"[TG-COPILOTO] chat={chat_id} acao={acao} params={params}")

        # Execução da ação
        try:
            if acao == "listar_inqueritos":
                resposta = await self._listar_inqueritos(db)

            elif acao == "status_inquerito":
                numero = params.get("numero_ip", "") or ctx.get("inquerito_atual", "")
                if numero:
                    ctx["inquerito_atual"] = numero
                resposta = await self._status_inquerito(numero, db)

            elif acao == "busca_autos":
                numero = params.get("numero_ip") or ctx.get("inquerito_atual", "")
                query = params.get("query", mensagem)
                if numero:
                    ctx["inquerito_atual"] = numero
                resposta = await self._busca_autos(numero, query, ctx, db)

            elif acao == "agenda":
                resposta = await self._agenda(db)

            elif acao == "ficha_pessoa":
                nome = params.get("nome", "")
                cpf = params.get("cpf", "")
                numero = params.get("numero_ip") or ctx.get("inquerito_atual", "")
                if numero:
                    ctx["inquerito_atual"] = numero
                resposta = await self._ficha_pessoa(nome, cpf, numero, db)

            elif acao == "ajuda":
                resposta = _mensagem_ajuda()

            else:  # conversa
                resposta = params.get("resposta", "Como posso ajudar?")

        except Exception as e:
            logger.error(f"[TG-COPILOTO] Erro na ação {acao}: {e}", exc_info=True)
            resposta = f"⚠️ Erro ao executar <b>{acao}</b>: {_esc(str(e)[:200])}"

        # Atualizar contexto
        ctx["historico"].append({"u": mensagem[:150], "b": resposta[:200]})
        if len(ctx["historico"]) > 10:
            ctx["historico"] = ctx["historico"][-10:]
        await self._save_ctx(chat_id, ctx)

        return resposta

    # ── Dispatcher LLM ────────────────────────────────────────────────────────

    async def _dispatch(self, mensagem: str, ctx: dict) -> dict:
        """Chama LLM standard para classificar intenção. Retorna dict com acao+parametros."""
        historico_resumido = "; ".join(
            f"U:{h['u']}" for h in ctx.get("historico", [])[-3:]
        ) or "nenhum"

        system = DISPATCHER_PROMPT.format(
            inquerito_atual=ctx.get("inquerito_atual") or "nenhum",
            historico_resumido=historico_resumido,
        )

        try:
            result = await self.llm.chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": mensagem},
                ],
                tier="standard",
                temperature=0.1,
                max_tokens=300,
                json_mode=True,
            )
            return json.loads(result["content"])
        except Exception as e:
            logger.warning(f"[TG-COPILOTO] Dispatcher falhou: {e}")
            return {"acao": "conversa", "parametros": {"resposta": "Desculpe, não entendi. Digite /ajuda para ver os comandos disponíveis."}}

    # ── Ação: listar inquéritos ───────────────────────────────────────────────

    async def _listar_inqueritos(self, db: AsyncSession) -> str:
        result = await db.execute(
            select(Inquerito).order_by(Inquerito.updated_at.desc()).limit(20)
        )
        inqueritos = result.scalars().all()

        if not inqueritos:
            return "📂 Nenhum inquérito cadastrado."

        linhas = ["📋 <b>Inquéritos</b>\n"]
        for ip in inqueritos:
            estado = ESTADO_LABEL.get(ip.estado_atual, ip.estado_atual)
            docs = ip.total_documentos
            prio = f" 🔴" if ip.prioridade == "alta" else ""
            linhas.append(
                f"• <code>{_esc(ip.numero)}</code> — {_esc(estado)}{prio}\n"
                f"  {docs} doc(s) · {_esc(ip.delegacia_atual_nome or ip.delegacia or '—')}"
            )

        return "\n".join(linhas)

    # ── Ação: status de inquérito ─────────────────────────────────────────────

    async def _status_inquerito(self, numero: str, db: AsyncSession) -> str:
        if not numero:
            return "ℹ️ Informe o número do inquérito. Ex: <i>status do IP 915-001/2024</i>"

        result = await db.execute(
            select(Inquerito).where(Inquerito.numero.ilike(f"%{numero.strip()}%"))
        )
        ip = result.scalars().first()
        if not ip:
            return f"❌ Inquérito <code>{_esc(numero)}</code> não encontrado."

        estado = ESTADO_LABEL.get(ip.estado_atual, ip.estado_atual)
        delegacia = ip.delegacia_atual_nome or ip.delegacia or "—"
        criado = ip.created_at.strftime("%d/%m/%Y") if ip.created_at else "—"
        atualizado = ip.updated_at.strftime("%d/%m/%Y %H:%M") if ip.updated_at else "—"

        partes = [
            f"🔍 <b>IP {_esc(ip.numero)}</b>",
            f"📌 Estado: <b>{_esc(estado)}</b>",
            f"🏛️ Delegacia: {_esc(delegacia)}",
            f"📄 Documentos: {ip.total_documentos} ({ip.total_paginas} pgs)",
            f"📅 Criado: {criado} · Atualizado: {atualizado}",
        ]

        if ip.prioridade and ip.prioridade != "media":
            partes.append(f"⚡ Prioridade: {_esc(ip.prioridade)}")

        if ip.descricao:
            partes.append(f"\n📝 {_esc(ip.descricao[:300])}")

        # Contar pessoas/entidades indexadas (query separada para não sobrecarregar)
        try:
            p_result = await db.execute(
                select(Pessoa).where(Pessoa.inquerito_id == ip.id).limit(5)
            )
            pessoas = p_result.scalars().all()
            if pessoas:
                nomes = ", ".join(_esc(p.nome) for p in pessoas[:3])
                extra = f" (+{len(pessoas)-3})" if len(pessoas) > 3 else ""
                partes.append(f"\n👥 Pessoas: {nomes}{extra}")
        except Exception:
            pass

        return "\n".join(partes)

    # ── Ação: busca semântica nos autos ───────────────────────────────────────

    async def _busca_autos(
        self, numero: str, query: str, ctx: dict, db: AsyncSession
    ) -> str:
        if not numero:
            return (
                "ℹ️ Informe o inquérito para a busca.\n"
                "Ex: <i>no IP 915-001/2024 o que sabemos sobre Fulano?</i>"
            )

        # Localizar o inquérito no banco
        result = await db.execute(
            select(Inquerito).where(Inquerito.numero.ilike(f"%{numero.strip()}%"))
        )
        ip = result.scalars().first()
        if not ip:
            return f"❌ Inquérito <code>{_esc(numero)}</code> não encontrado."

        if ip.total_documentos == 0:
            return (
                f"📂 O IP <code>{_esc(ip.numero)}</code> ainda não tem documentos indexados.\n"
                "Faça o upload dos autos na interface web para habilitar a busca."
            )

        # Chamar CopilotoService (RAG pipeline)
        try:
            resultado = await self._get_copiloto().processar_mensagem(
                query=query,
                inquerito_id=str(ip.id),
                historico=[
                    {"role": "user" if "u" in h else "assistant", "content": h.get("u") or h.get("b", "")}
                    for h in ctx.get("historico", [])[-6:]
                ],
                numero_inquerito=ip.numero,
                estado_atual=ip.estado_atual,
                total_paginas=ip.total_paginas,
                total_documentos=ip.total_documentos,
                auditar=False,  # Desabilitar auditoria para agilidade no Telegram
                db=db,
            )
        except Exception as e:
            logger.error(f"[TG-COPILOTO] Erro CopilotoService: {e}", exc_info=True)
            return f"⚠️ Erro ao consultar os autos: {_esc(str(e)[:200])}"

        resposta_texto = resultado.get("resposta", "Sem resposta.")
        fontes = resultado.get("fontes", [])

        # Truncar resposta longa
        if len(resposta_texto) > 3000:
            resposta_texto = resposta_texto[:2997] + "..."

        partes = [
            f"🔎 <b>Busca no IP {_esc(ip.numero)}</b>",
            f'<i>"{_esc(query[:100])}"</i>\n',
            resposta_texto,
        ]

        if fontes:
            docs_unicos = list({f.get("documento_id", "")[:20] for f in fontes[:3] if f.get("documento_id")})
            partes.append(f"\n📎 Fontes: {', '.join(_esc(d) for d in docs_unicos)}")

        return "\n".join(partes)

    # ── Ação: agenda ─────────────────────────────────────────────────────────

    async def _agenda(self, db: AsyncSession) -> str:
        agora = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC

        result = await db.execute(
            select(Intimacao)
            .where(Intimacao.data_oitiva >= agora)
            .where(Intimacao.status == "agendada")
            .order_by(Intimacao.data_oitiva.asc())
            .limit(10)
        )
        intimacoes = result.scalars().all()

        if not intimacoes:
            # Verificar se há intimações passadas recentes
            result_past = await db.execute(
                select(Intimacao)
                .where(Intimacao.status == "agendada")
                .order_by(Intimacao.data_oitiva.desc())
                .limit(5)
            )
            recentes = result_past.scalars().all()
            if not recentes:
                return "📅 Nenhuma oitiva ou audiência agendada."
            return "📅 Nenhuma oitiva futura. Consulte a interface web para ver o histórico."

        linhas = ["📅 <b>Próximas oitivas / audiências</b>\n"]
        for it in intimacoes:
            data_str = it.data_oitiva.strftime("%d/%m/%Y %H:%M") if it.data_oitiva else "data?"
            nome = _esc(it.intimado_nome or "—")
            qualif = it.intimado_qualificacao or ""
            local = _esc(it.local_oitiva or "local não informado")
            qualif_str = f" ({_esc(qualif)})" if qualif else ""

            linha = f"• <b>{data_str}</b> — {nome}{qualif_str}\n  📍 {local}"
            if it.google_event_url:
                linha += f'\n  <a href="{it.google_event_url}">→ Abrir no Google Agenda</a>'
            linhas.append(linha)

        return "\n".join(linhas)

    # ── Ação: ficha pessoa ────────────────────────────────────────────────────

    async def _ficha_pessoa(
        self, nome: str, cpf: str, numero_ip: str, db: AsyncSession
    ) -> str:
        if not nome and not cpf:
            return "ℹ️ Informe o nome ou CPF da pessoa. Ex: <i>ficha do João Silva no IP 915-001/2024</i>"

        # Montar filtro
        query = select(Pessoa)
        if cpf:
            query = query.where(Pessoa.cpf == cpf.strip())
        elif nome:
            query = query.where(Pessoa.nome.ilike(f"%{nome.strip()}%"))

        # Filtrar por inquérito se disponível
        if numero_ip:
            ip_result = await db.execute(
                select(Inquerito).where(Inquerito.numero.ilike(f"%{numero_ip.strip()}%"))
            )
            ip = ip_result.scalars().first()
            if ip:
                query = query.where(Pessoa.inquerito_id == ip.id)

        query = query.order_by(Pessoa.created_at.desc()).limit(5)
        result = await db.execute(query)
        pessoas = result.scalars().all()

        if not pessoas:
            alvo = cpf or nome
            return f"❌ Nenhuma pessoa encontrada para <i>{_esc(alvo)}</i> nos autos indexados."

        linhas = [f"👤 <b>Ficha(s) encontrada(s)</b>\n"]
        for p in pessoas:
            tipo = _esc(p.tipo_pessoa or "não classificado")
            cpf_str = f" · CPF: <code>{_esc(p.cpf)}</code>" if p.cpf else ""
            linhas.append(f"<b>{_esc(p.nome)}</b> — {tipo}{cpf_str}")
            if p.resumo_contexto:
                linhas.append(f"<i>{_esc(p.resumo_contexto[:400])}</i>")
            if p.observacoes:
                linhas.append(f"📝 {_esc(p.observacoes[:200])}")
            linhas.append("")

        linhas.append("💡 Para enriquecimento OSINT (P1–P4) use a interface web.")
        return "\n".join(linhas)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    """Escapa caracteres especiais HTML."""
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mensagem_ajuda() -> str:
    return (
        "🤖 <b>Escrivão AI — Copiloto Telegram</b>\n\n"
        "<b>Comandos disponíveis:</b>\n"
        "• <i>listar inquéritos</i> — todos os IPs cadastrados\n"
        "• <i>status do IP 915-001/2024</i> — detalhes de um inquérito\n"
        "• <i>no IP 915-001/2024, o que sabemos sobre X?</i> — busca nos autos\n"
        "• <i>agenda</i> ou <i>próximas audiências</i> — oitivas agendadas\n"
        "• <i>ficha do João Silva no IP 915-001/2024</i> — perfil de pessoa\n\n"
        "💡 <b>Dica:</b> Após mencionar um IP, posso manter o contexto "
        "para as próximas perguntas sem precisar repetir o número.\n\n"
        "/ajuda — exibe esta mensagem"
    )
