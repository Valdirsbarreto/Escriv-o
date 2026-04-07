"""
Escrivão AI — Copiloto OSINT: Análise de Personagens
Para cada Pessoa do inquérito:
  1. Varre o Qdrant buscando menções por nome e CPF
  2. Detecta campos-chave nos chunks (CPF, telefone, endereço) via regex
  3. Calcula "staleness" de cada dado (fresco < 2 anos | desatualizado ≥ 2 anos | ausente)
  4. Sugere perfil de enriquecimento P1–P4 baseado em tipo_pessoa × complexidade do crime
  5. Gera justificativa determinística (sem LLM, custo zero)
"""

import logging
import re
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.documento import Documento
from app.models.empresa import Empresa
from app.models.inquerito import Inquerito
from app.models.pessoa import Pessoa
from app.services.embedding_service import EmbeddingService
from app.services.qdrant_service import QdrantService

logger = logging.getLogger(__name__)


# ── Constantes ──────────────────────────────────────────────────────────────

STALENESS_DIAS = 730  # 2 anos

CRIMES_COMPLEXOS_KW = [
    "lavagem", "lavagem de dinheiro", "organização criminosa", "org. criminosa",
    "corrupção", "tráfico", "tráfico de drogas", "máfia", "quadrilha",
    "associação criminosa", "peculato", "concussão", "estelionato qualificado",
]

CUSTO_PERFIL = {1: 3.40, 2: 5.68, 3: 7.76, 4: 11.76}

LABEL_PERFIL = {
    1: "P1 Localização",
    2: "P2 Triagem",
    3: "P3 Investigação",
    4: "P4 Profundo",
}

# Regex para extração de dados e datas
RE_CPF     = re.compile(r'\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[-.\s]?\d{2}\b')
RE_FONE    = re.compile(r'\(?\d{2}\)?\s?\d{4,5}[-\s]?\d{4}')
RE_ENDE    = re.compile(
    r'(?:rua|av\.|avenida|praça|estrada|travessa|alameda|rodovia)\s+[A-Za-zÀ-ú\s,\d\.]{5,60}',
    re.IGNORECASE,
)
RE_DATA    = re.compile(r'\b(\d{2})[/\-](\d{2})[/\-](\d{2,4})\b')


# ── Helpers ─────────────────────────────────────────────────────────────────

def _extrair_data_mais_recente(texto: str) -> Optional[date]:
    """Extrai a data mais recente (dd/mm/aaaa) encontrada no texto."""
    datas: List[date] = []
    for m in RE_DATA.finditer(texto):
        d, mo, a = m.groups()
        ano = int(a)
        if ano < 100:
            ano += 2000 if ano <= 30 else 1900
        try:
            datas.append(date(ano, int(mo), int(d)))
        except ValueError:
            pass
    return max(datas) if datas else None


def _staleness(data_doc: Optional[date]) -> str:
    if data_doc is None:
        return "ausente"
    return "fresco" if (date.today() - data_doc).days < STALENESS_DIAS else "desatualizado"


def _e_crime_complexo(descricao: str) -> bool:
    d = (descricao or "").lower()
    return any(kw in d for kw in CRIMES_COMPLEXOS_KW)


def _sugerir_perfil(tipo_pessoa: Optional[str], crime_complexo: bool) -> int:
    """
    Tabela do plano aprovado:
      investigado  → P3 (simples) / P4 (complexo)
      testemunha   → P2 (ambos)
      vítima       → P1 (simples) / P2 (complexo)
      outro        → P1 (simples) / P2 (complexo)
    """
    t = (tipo_pessoa or "outro").lower().strip()
    if t == "investigado":
        return 4 if crime_complexo else 3
    if t == "testemunha":
        return 2
    if t in ("vitima", "vítima"):
        return 2 if crime_complexo else 1
    return 2 if crime_complexo else 1


def _gerar_justificativa(
    tipo_pessoa: str,
    crime_complexo: bool,
    perfil: int,
    dados: Dict[str, Any],
    historico: Optional[List[Dict[str, Any]]] = None,
) -> str:
    partes: List[str] = []

    tipo_fmt = tipo_pessoa.capitalize() if tipo_pessoa else "Personagem"
    crime_fmt = "complexo (lavagem/tráfico/corrupção)" if crime_complexo else "simples"
    partes.append(f"{tipo_fmt} em caso {crime_fmt}.")

    cpf = dados.get("cpf", {})
    if cpf.get("presente"):
        s = cpf.get("staleness", "ausente")
        partes.append(
            "CPF encontrado e atualizado nos autos." if s == "fresco"
            else "CPF encontrado nos autos, mas pode estar desatualizado."
        )
    else:
        partes.append("CPF não encontrado nos autos.")

    end = dados.get("endereco", {})
    if end.get("presente"):
        s = end.get("staleness", "ausente")
        fmt = end.get("data_doc_fmt", "")
        sufixo = f" ({fmt})" if fmt else ""
        partes.append(
            f"Endereço nos autos{sufixo} — atualizado." if s == "fresco"
            else f"Endereço nos autos{sufixo} — possivelmente desatualizado, recomendo verificar."
        )
    else:
        partes.append("Endereço não encontrado nos autos — enriquecimento necessário.")

    fone = dados.get("telefone", {})
    if fone.get("presente"):
        s = fone.get("staleness", "ausente")
        partes.append(
            "Telefone atualizado nos autos." if s == "fresco"
            else "Telefone nos autos pode estar desatualizado."
        )

    # Histórico cruzado
    if historico:
        n = len(historico)
        papeis = list({h["tipo_pessoa"] for h in historico})
        papeis_str = "/".join(papeis[:2])
        nums = ", ".join(h["numero"] for h in historico[:2])
        sufixo = f" ({nums}{'...' if n > 2 else ''})"
        partes.append(
            f"⚠ Aparece em {n} outro(s) inquérito(s) como {papeis_str}{sufixo} — atenção ao histórico."
        )

    partes.append(f"Recomendo {LABEL_PERFIL[perfil]}.")
    return " ".join(partes)


# ── Lookup cruzado entre inquéritos ─────────────────────────────────────────

async def buscar_historico_pessoa(
    db: AsyncSession,
    cpf: str,
    inquerito_id_atual: Optional[uuid.UUID] = None,
) -> List[Dict[str, Any]]:
    """
    Busca em TODOS os inquéritos registros de Pessoa com o mesmo CPF,
    excluindo o inquérito atual (se fornecido).
    Normaliza CPF via regexp_replace (remove não-dígitos) antes de comparar.
    """
    cpf_digits = re.sub(r'\D', '', cpf)
    if not cpf_digits:
        return []

    stmt = select(Pessoa, Inquerito)\
        .join(Inquerito, Pessoa.inquerito_id == Inquerito.id)\
        .where(Pessoa.cpf.isnot(None))\
        .where(func.regexp_replace(Pessoa.cpf, r'\D', '', 'g') == cpf_digits)
    
    if inquerito_id_atual:
        stmt = stmt.where(Pessoa.inquerito_id != inquerito_id_atual)
        
    stmt = stmt.order_by(Inquerito.created_at.desc())
    
    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "inquerito_id": str(inq.id),
            "numero": inq.numero,
            "ano": inq.ano,
            "descricao": (inq.descricao or "")[:120],
            "tipo_pessoa": p.tipo_pessoa or "outro",
            "created_at": inq.created_at.isoformat(),
        }
        for p, inq in rows
    ]


async def buscar_historico_empresa(
    db: AsyncSession,
    cnpj: str,
    inquerito_id_atual: Optional[uuid.UUID] = None,
) -> List[Dict[str, Any]]:
    """
    Busca em TODOS os inquéritos registros de Empresa com o mesmo CNPJ,
    excluindo o inquérito atual (se fornecido).
    """
    cnpj_digits = re.sub(r'\D', '', cnpj)
    if not cnpj_digits:
        return []

    stmt = select(Empresa, Inquerito)\
        .join(Inquerito, Empresa.inquerito_id == Inquerito.id)\
        .where(Empresa.cnpj.isnot(None))\
        .where(func.regexp_replace(Empresa.cnpj, r'\D', '', 'g') == cnpj_digits)
        
    if inquerito_id_atual:
        stmt = stmt.where(Empresa.inquerito_id != inquerito_id_atual)
        
    stmt = stmt.order_by(Inquerito.created_at.desc())
    
    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "inquerito_id": str(inq.id),
            "numero": inq.numero,
            "ano": inq.ano,
            "descricao": (inq.descricao or "")[:120],
            "tipo_empresa": e.tipo_empresa or "outro",
            "created_at": inq.created_at.isoformat(),
        }
        for e, inq in rows
    ]


# ── Serviço ─────────────────────────────────────────────────────────────────

class CopilotoOsintService:
    """
    Analisa personagens do inquérito para alimentar o painel OSINT.
    Determinístico, sem chamadas LLM, sem consumo de direct.data.
    """

    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.qdrant_service = QdrantService()

    # ── Ponto de entrada ────────────────────────────────────────────────────

    async def analisar_personagens(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Retorna análise completa de todos os personagens do inquérito.
        Inclui dados_nos_autos (staleness), perfil_sugerido e justificativa por pessoa.
        """
        inquerito = await db.get(Inquerito, inquerito_id)
        if not inquerito:
            return {"erro": "Inquérito não encontrado"}

        crime_complexo = _e_crime_complexo(inquerito.descricao or "")

        result = await db.execute(
            select(Pessoa).where(Pessoa.inquerito_id == inquerito_id)
        )
        pessoas = result.scalars().all()

        if not pessoas:
            return {
                "inquerito_id": str(inquerito_id),
                "crime_complexo": crime_complexo,
                "personagens": [],
                "total_custo_estimado": 0.0,
            }

        personagens = []
        custo_total = 0.0

        for pessoa in pessoas:
            analise = await self._analisar_pessoa(
                db, pessoa, str(inquerito_id), crime_complexo
            )
            personagens.append(analise)
            custo_total += CUSTO_PERFIL.get(analise["perfil_sugerido"], 0.0)

        return {
            "inquerito_id": str(inquerito_id),
            "crime_complexo": crime_complexo,
            "descricao_inquerito": inquerito.descricao or "",
            "personagens": personagens,
            "total_custo_estimado": round(custo_total, 2),
        }

    # ── Análise por pessoa ───────────────────────────────────────────────────

    async def _analisar_pessoa(
        self,
        db: AsyncSession,
        pessoa: Pessoa,
        inquerito_id: str,
        crime_complexo: bool,
    ) -> Dict[str, Any]:
        """Analisa uma pessoa individualmente, incluindo histórico entre inquéritos."""
        inquerito_uuid = uuid.UUID(inquerito_id)
        chunks = self._buscar_chunks(pessoa, inquerito_id)
        doc_dates = await self._datas_documentos(db, chunks)
        dados = self._detectar_dados(pessoa, chunks, doc_dates)

        # Histórico cruzado — outros inquéritos onde o mesmo CPF aparece
        historico: List[Dict[str, Any]] = []
        if pessoa.cpf:
            try:
                historico = await buscar_historico_pessoa(db, pessoa.cpf, inquerito_uuid)
            except Exception as e:
                logger.warning(f"[COPILOTO_OSINT] Histórico falhou para {pessoa.nome}: {e}")

        perfil = _sugerir_perfil(pessoa.tipo_pessoa, crime_complexo)
        justificativa = _gerar_justificativa(
            pessoa.tipo_pessoa or "outro", crime_complexo, perfil, dados, historico
        )

        return {
            "pessoa_id": str(pessoa.id),
            "nome": pessoa.nome,
            "tipo_pessoa": pessoa.tipo_pessoa or "outro",
            "cpf": pessoa.cpf,
            "dados_nos_autos": dados,
            "historico_inqueritos": historico,
            "perfil_sugerido": perfil,
            "perfil_sugerido_label": LABEL_PERFIL[perfil],
            "custo_estimado": CUSTO_PERFIL[perfil],
            "justificativa": justificativa,
            "chunks_encontrados": len(chunks),
        }

    # ── Busca Qdrant ─────────────────────────────────────────────────────────

    def _buscar_chunks(
        self,
        pessoa: Pessoa,
        inquerito_id: str,
        max_chunks: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Busca semântica no Qdrant pelo nome da pessoa.
        Se CPF disponível, faz segunda busca e filtra por presença numérica do CPF no texto.
        Deduplica por chunk_id.
        """
        chunks: List[Dict[str, Any]] = []

        # Busca por nome
        try:
            vetor = self.embedding_service.generate(pessoa.nome)
            chunks += self.qdrant_service.search(
                query_vector=vetor,
                limit=max_chunks,
                inquerito_id=inquerito_id,
                score_threshold=0.4,
            )
        except Exception as e:
            logger.warning(f"[COPILOTO_OSINT] Busca nome '{pessoa.nome}': {e}")

        # Busca por CPF (filtra chunks que realmente têm o número)
        if pessoa.cpf:
            cpf_digits = re.sub(r'\D', '', pessoa.cpf)
            try:
                vetor_cpf = self.embedding_service.generate(f"CPF {pessoa.cpf}")
                candidatos = self.qdrant_service.search(
                    query_vector=vetor_cpf,
                    limit=5,
                    inquerito_id=inquerito_id,
                    score_threshold=0.3,
                )
                for r in candidatos:
                    texto_digits = re.sub(r'\D', '', r["payload"].get("texto_preview", ""))
                    if cpf_digits[:9] in texto_digits:
                        chunks.append(r)
            except Exception as e:
                logger.warning(f"[COPILOTO_OSINT] Busca CPF '{pessoa.cpf}': {e}")

        # Deduplica
        vistos: set = set()
        uniq: List[Dict[str, Any]] = []
        for c in chunks:
            cid = c.get("id") or c["payload"].get("chunk_id", "")
            if cid not in vistos:
                vistos.add(cid)
                uniq.append(c)

        return uniq

    # ── Datas dos documentos ─────────────────────────────────────────────────

    async def _datas_documentos(
        self,
        db: AsyncSession,
        chunks: List[Dict[str, Any]],
    ) -> Dict[str, date]:
        """
        Para cada chunk, tenta extrair data do texto.
        Fallback: Documento.created_at do banco.
        Retorna {documento_id: date}.
        """
        doc_dates: Dict[str, date] = {}

        for chunk in chunks:
            doc_id = chunk["payload"].get("documento_id")
            if not doc_id or doc_id in doc_dates:
                continue

            # Tentar extrair data do texto do chunk
            texto = chunk["payload"].get("texto_preview", "")
            data = _extrair_data_mais_recente(texto)
            if data:
                doc_dates[doc_id] = data
                continue

            # Fallback: data de upload no banco
            try:
                doc = await db.get(Documento, uuid.UUID(doc_id))
                if doc and doc.created_at:
                    doc_dates[doc_id] = doc.created_at.date()
            except Exception:
                pass

        return doc_dates

    # ── Detecção de dados nos chunks ─────────────────────────────────────────

    def _detectar_dados(
        self,
        pessoa: Pessoa,
        chunks: List[Dict[str, Any]],
        doc_dates: Dict[str, date],
    ) -> Dict[str, Any]:
        """
        Detecta CPF, telefone e endereço nos chunks.
        Se a pessoa já tem CPF no banco, marca como presente.
        Para cada campo retorna: presente, staleness, data_doc, data_doc_fmt, texto.
        """
        # Estado inicial de cada campo
        def _vazio():
            return {"presente": False, "staleness": "ausente", "data_doc": None, "data_doc_fmt": None, "texto": None}

        cpf_info  = _vazio()
        fone_info = _vazio()
        end_info  = _vazio()

        # CPF já cadastrado no banco → sabemos que está nos autos
        if pessoa.cpf:
            cpf_info["presente"] = True
            cpf_info["texto"] = pessoa.cpf

        for chunk in chunks:
            texto  = chunk["payload"].get("texto_preview", "")
            doc_id = chunk["payload"].get("documento_id")
            data   = doc_dates.get(doc_id)

            # — CPF —
            m = RE_CPF.search(texto)
            if m and data:
                cpf_info["presente"] = True
                cpf_info["texto"] = cpf_info["texto"] or m.group(0)
                # Guardar data mais recente
                if cpf_info["data_doc"] is None or data > cpf_info["data_doc"]:
                    cpf_info["data_doc"] = data
                    cpf_info["data_doc_fmt"] = data.strftime("%b/%Y")

            # — Telefone —
            m = RE_FONE.search(texto)
            if m:
                data_fone = data
                if not fone_info["presente"] or (data_fone and fone_info["data_doc"] and data_fone > fone_info["data_doc"]):
                    fone_info["presente"] = True
                    fone_info["texto"] = m.group(0)
                    if data_fone:
                        fone_info["data_doc"] = data_fone
                        fone_info["data_doc_fmt"] = data_fone.strftime("%b/%Y")

            # — Endereço —
            m = RE_ENDE.search(texto)
            if m:
                data_end = data
                if not end_info["presente"] or (data_end and end_info["data_doc"] and data_end > end_info["data_doc"]):
                    end_info["presente"] = True
                    end_info["texto"] = m.group(0)[:80].strip()
                    if data_end:
                        end_info["data_doc"] = data_end
                        end_info["data_doc_fmt"] = data_end.strftime("%b/%Y")

        # Calcular staleness + serializar data para JSON
        for info in [cpf_info, fone_info, end_info]:
            info["staleness"] = _staleness(info["data_doc"])
            if info["data_doc"]:
                info["data_doc"] = info["data_doc"].isoformat()

        return {"cpf": cpf_info, "telefone": fone_info, "endereco": end_info}
