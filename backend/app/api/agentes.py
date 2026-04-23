"""
Escrivão AI — API: Agentes Especializados
Endpoints para os 3 agentes: Fichas OSINT, Produção Cautelar e Análise de Extratos.
Conforme blueprint §9 (Agentes Especializados).
"""

import logging
import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

logger = logging.getLogger(__name__)
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.consulta_externa import ConsultaExterna
from app.models.pessoa import Pessoa
from app.models.contato import Contato
from app.models.endereco import Endereco
from app.services.agente_ficha import AgenteFicha
from app.services.agente_cautelar import AgenteCautelar
from app.services.agente_extrato import AgenteExtrato
from app.services.osint_service import OsintService

router = APIRouter(prefix="/api/v1/agentes", tags=["Agentes Especializados"])


# ── Fichas OSINT ──────────────────────────────────────────────────────────────

@router.post(
    "/ficha/pessoa/{pessoa_id}",
    summary="Gera ficha investigativa de uma Pessoa",
)
async def gerar_ficha_pessoa(
    pessoa_id: uuid.UUID,
    inquerito_id: uuid.UUID,
    usar_dados_externos: bool = False,
    incluir_processos: bool = False,
    incluir_sancoes_internacionais: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Consolida dados internos de uma Pessoa e gera ficha investigativa via LLM Premium.

    - `usar_dados_externos=true` — enriquece com APIs da direct.data (gera custo)
    - `incluir_processos=true` — inclui consulta TJ (adicional)
    - `incluir_sancoes_internacionais=true` — inclui OFAC/ONU (adicional)
    """
    dados_externos = None
    if usar_dados_externos:
        osint = OsintService()
        dados_externos = await osint.enriquecer_pessoa(
            db, inquerito_id, pessoa_id,
            incluir_processos=incluir_processos,
            incluir_sancoes_internacionais=incluir_sancoes_internacionais,
        )

    agente = AgenteFicha()
    try:
        ficha = await agente.gerar_ficha_pessoa(db, inquerito_id, pessoa_id, dados_externos=dados_externos)
        return {"status": "concluido", "ficha": ficha, "osint_usado": usar_dados_externos}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar ficha: {str(e)[:200]}")


@router.post(
    "/ficha/empresa/{empresa_id}",
    summary="Gera ficha investigativa de uma Empresa",
)
async def gerar_ficha_empresa(
    empresa_id: uuid.UUID,
    inquerito_id: uuid.UUID,
    usar_dados_externos: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Consolida dados internos de uma Empresa e gera ficha investigativa via LLM Premium.

    - `usar_dados_externos=true` — enriquece com Receita Federal + sanções via direct.data (gera custo)
    """
    dados_externos = None
    if usar_dados_externos:
        osint = OsintService()
        dados_externos = await osint.enriquecer_empresa(db, inquerito_id, empresa_id)

    agente = AgenteFicha()
    try:
        ficha = await agente.gerar_ficha_empresa(db, inquerito_id, empresa_id, dados_externos=dados_externos)
        return {"status": "concluido", "ficha": ficha, "osint_usado": usar_dados_externos}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar ficha: {str(e)[:200]}")


# ── Análise Preliminar (LLM gratuita, automática) ────────────────────────────

@router.get(
    "/osint/preliminar/{inquerito_id}/{pessoa_id}",
    summary="Análise preliminar OSINT (LLM interna, sem APIs pagas)",
)
async def analise_preliminar_pessoa(
    inquerito_id: uuid.UUID,
    pessoa_id: uuid.UUID,
    aprimorar: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Gera análise investigativa baseada nos dados internos dos autos.
    aprimorar=false → Groq/Llama (gratuito, automático ao expandir card)
    aprimorar=true  → Gemini Flash (por demanda, melhor qualidade)
    """
    agente = AgenteFicha()
    try:
        analise = await agente.gerar_analise_preliminar_pessoa(
            db, inquerito_id, pessoa_id, aprimorar=aprimorar
        )
        return {"status": "concluido", "analise": analise, "aprimorada": aprimorar}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na análise preliminar: {str(e)[:200]}")


# ── OSINT — Fontes Gratuitas (BrasilAPI / ReceitaFederal / CGU) ──────────────

@router.get(
    "/osint/gratuito/{inquerito_id}/{pessoa_id}",
    summary="OSINT gratuito — Receita Federal (CNPJ) + sanções CGU",
)
async def osint_gratuito_pessoa(
    inquerito_id: uuid.UUID,
    pessoa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Consulta fontes abertas brasileiras sem custo:
    - BrasilAPI/Receita Federal (CNPJ: razão social, sócios, situação, endereço)
    - CGU/CEIS (sanções federais, se CGU_API_TOKEN configurado)
    Cache de 12h em ResultadoAgente.
    Custo: $0.
    """
    agente = AgenteFicha()
    try:
        dados = await agente.gerar_osint_gratuito_pessoa(db, inquerito_id, pessoa_id)
        return {"status": "concluido", "dados_gratuitos": dados}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro OSINT gratuito: {str(e)[:200]}")


# ── OSINT — Fontes Abertas (Serper.dev) ──────────────────────────────────────

@router.get(
    "/osint/web/{inquerito_id}/{pessoa_id}",
    summary="OSINT fontes abertas — busca web via Serper.dev",
)
async def osint_web_pessoa(
    inquerito_id: uuid.UUID,
    pessoa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Busca o nome/CPF da pessoa em fontes abertas da internet (Google, JusBrasil,
    Escavador, DOU, notícias policiais) e retorna relatório consolidado pelo LLM.
    Cache de 6h em ResultadoAgente.
    Requer SERPER_API_KEY configurado.
    """
    from app.core.config import settings
    if not settings.SERPER_API_KEY:
        raise HTTPException(status_code=503, detail="SERPER_API_KEY não configurado")

    agente = AgenteFicha()
    try:
        dados = await agente.gerar_osint_web_pessoa(db, inquerito_id, pessoa_id)
        return {"status": "concluido", "dados_web": dados}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro OSINT web: {str(e)[:200]}")


@router.post(
    "/osint/web/{inquerito_id}/{pessoa_id}/relatorio",
    summary="Gera relatório formal OSINT fontes abertas e salva como DocumentoGerado",
)
async def osint_web_relatorio(
    inquerito_id: uuid.UUID,
    pessoa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Usa os dados OSINT web já coletados (cache 6h) e gera um relatório policial
    formal com 7 seções. Salva como DocumentoGerado(tipo='relatorio_osint_web').
    """
    agente = AgenteFicha()
    try:
        resultado = await agente.gerar_relatorio_osint_web(db, inquerito_id, pessoa_id)
        return {"status": "concluido", "resultado": resultado}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar relatório OSINT web: {str(e)[:200]}")


# ── OSINT — Deep Research (Gemini Agent, background 5–15 min) ────────────────

DEEP_RESEARCH_AGENT_MODEL = "deep-research-preview-04-2026"


class OsintDeepExecutarRequest(BaseModel):
    briefing: str = ""


async def _guard_deep_em_andamento(inquerito_id: uuid.UUID, db: AsyncSession):
    """Retorna o doc placeholder se já existe pesquisa em andamento, ou None."""
    from app.models.documento_gerado import DocumentoGerado
    from sqlalchemy import and_
    result = await db.execute(
        select(DocumentoGerado).where(
            and_(
                DocumentoGerado.inquerito_id == inquerito_id,
                DocumentoGerado.tipo == "osint_deep",
                DocumentoGerado.conteudo == "__PROCESSANDO__",
            )
        ).limit(1)
    )
    return result.scalar_one_or_none()


@router.post(
    "/osint/deep/{inquerito_id}/{pessoa_id}/planejar",
    summary="OSINT Deep Research — gera plano investigativo para revisão (~5–10s)",
)
async def osint_deep_planejar(
    inquerito_id: uuid.UUID,
    pessoa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Fase 1 do Deep Research colaborativo.
    Gera um briefing investigativo via gemini-flash com base nos autos e no papel da pessoa.
    O Comissário revisa, edita se necessário, e aprova antes de disparar o Deep Research.
    Custo: praticamente zero (flash-lite, ~2k tokens).
    """
    from app.core.config import settings
    from app.models.contato import Contato
    from app.models.endereco import Endereco
    from app.models.documento_gerado import DocumentoGerado as DocGerado
    from app.services.summary_service import SummaryService
    from app.workers.osint_deep_task import _gerar_briefing

    if not getattr(settings, "GEMINI_API_KEY", None):
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY não configurado.")

    pessoa = await db.get(Pessoa, pessoa_id)
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada.")

    # Contatos e endereços
    contatos_res = await db.execute(
        select(Contato)
        .where(Contato.inquerito_id == inquerito_id, Contato.pessoa_id == pessoa_id)
        .limit(10)
    )
    contatos = contatos_res.scalars().all()

    enderecos_res = await db.execute(
        select(Endereco)
        .where(Endereco.inquerito_id == inquerito_id, Endereco.pessoa_id == pessoa_id)
        .limit(5)
    )
    enderecos = enderecos_res.scalars().all()

    # Contexto do inquérito
    contexto_parts = []
    try:
        rel_res = await db.execute(
            select(DocGerado)
            .where(
                DocGerado.inquerito_id == inquerito_id,
                DocGerado.tipo == "relatorio_inicial",
                DocGerado.conteudo != "__PROCESSANDO__",
            )
            .order_by(DocGerado.created_at.desc())
            .limit(1)
        )
        rel = rel_res.scalar_one_or_none()
        if rel and rel.conteudo:
            contexto_parts.append("=== RELATÓRIO INICIAL ===\n" + rel.conteudo[:8000])

        resumo = await SummaryService(db).obter_resumo_caso(inquerito_id)
        if resumo:
            contexto_parts.append("=== RESUMO EXECUTIVO ===\n" + resumo[:3000])
    except Exception as e:
        logger.warning(f"[OSINT-DEEP-PLAN] Contexto parcial: {e}")

    contexto_inquerito = "\n\n".join(contexto_parts) or "Contexto do inquérito não disponível."

    briefing = await _gerar_briefing(pessoa, contatos, enderecos, contexto_inquerito)
    if not briefing:
        raise HTTPException(status_code=500, detail="Falha ao gerar plano investigativo. Tente novamente.")

    return {
        "briefing": briefing,
        "pessoa_nome": pessoa.nome,
        "papel": getattr(pessoa, "papel", None) or getattr(pessoa, "tipo_pessoa", "não identificado"),
    }


@router.post(
    "/osint/deep/{inquerito_id}/{pessoa_id}/executar",
    summary="OSINT Deep Research — executa com briefing aprovado pelo Comissário",
)
async def osint_deep_executar(
    inquerito_id: uuid.UUID,
    pessoa_id: uuid.UUID,
    body: OsintDeepExecutarRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Fase 2 do Deep Research colaborativo.
    Recebe o briefing (possivelmente editado pelo Comissário) e dispara a pesquisa Deep Research.
    """
    from app.core.config import settings
    from app.models.documento_gerado import DocumentoGerado

    if not getattr(settings, "GEMINI_API_KEY", None):
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY não configurado.")

    pessoa = await db.get(Pessoa, pessoa_id)
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada.")

    em_andamento = await _guard_deep_em_andamento(inquerito_id, db)
    if em_andamento:
        raise HTTPException(status_code=409, detail=f"Pesquisa já em andamento para {pessoa.nome}.")

    doc = DocumentoGerado(
        inquerito_id=inquerito_id,
        titulo=f"OSINT Aprofundado — {pessoa.nome}",
        tipo="osint_deep",
        conteudo="__PROCESSANDO__",
        modelo_llm=DEEP_RESEARCH_AGENT_MODEL,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    from app.workers.osint_deep_task import osint_deep_research_task
    osint_deep_research_task.delay(
        str(inquerito_id), str(pessoa_id), str(doc.id),
        briefing_override=body.briefing.strip() or None,
    )

    logger.info(f"[OSINT-DEEP] Executar com briefing aprovado — doc={doc.id} pessoa={pessoa.nome}")
    return {
        "status": "iniciado",
        "doc_id": str(doc.id),
        "mensagem": f"Pesquisa Deep Research iniciada para {pessoa.nome}. O relatório aparecerá em Documentos IA em 5–15 minutos.",
    }


@router.post(
    "/osint/deep/{inquerito_id}/{pessoa_id}",
    summary="OSINT Aprofundado — disparo direto sem planejamento (legado)",
)
async def osint_deep_research(
    inquerito_id: uuid.UUID,
    pessoa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Disparo direto sem fase de planejamento. Mantido para compatibilidade."""
    from app.core.config import settings
    from app.models.documento_gerado import DocumentoGerado

    if not getattr(settings, "GEMINI_API_KEY", None):
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY não configurado.")

    pessoa = await db.get(Pessoa, pessoa_id)
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada.")

    em_andamento = await _guard_deep_em_andamento(inquerito_id, db)
    if em_andamento:
        raise HTTPException(status_code=409, detail=f"Já existe uma pesquisa Deep Research em andamento para {pessoa.nome}.")

    doc = DocumentoGerado(
        inquerito_id=inquerito_id,
        titulo=f"OSINT Aprofundado — {pessoa.nome}",
        tipo="osint_deep",
        conteudo="__PROCESSANDO__",
        modelo_llm=DEEP_RESEARCH_AGENT_MODEL,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    from app.workers.osint_deep_task import osint_deep_research_task
    osint_deep_research_task.delay(str(inquerito_id), str(pessoa_id), str(doc.id))

    logger.info(f"[OSINT-DEEP] Task disparada — doc={doc.id} pessoa={pessoa.nome}")
    return {
        "status": "iniciado",
        "doc_id": str(doc.id),
        "mensagem": f"Pesquisa Deep Research iniciada para {pessoa.nome}. O relatório aparecerá em Documentos IA em 5–15 minutos.",
    }


@router.get(
    "/osint/deep/{inquerito_id}/{pessoa_id}/status",
    summary="Status do Deep Research para uma pessoa",
)
async def osint_deep_status(
    inquerito_id: uuid.UUID,
    pessoa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna o estado atual do Deep Research para a pessoa no inquérito.
    Usado pelo frontend para restaurar o estado do painel após navegação.
    """
    from app.models.documento_gerado import DocumentoGerado
    from app.models.pessoa import Pessoa

    pessoa = await db.get(Pessoa, pessoa_id)
    nome = pessoa.nome if pessoa else str(pessoa_id)

    # Busca o doc mais recente de tipo osint_deep para este inquérito
    # (título inclui o nome da pessoa — é suficiente para distinguir)
    result = await db.execute(
        select(DocumentoGerado)
        .where(
            DocumentoGerado.inquerito_id == inquerito_id,
            DocumentoGerado.tipo == "osint_deep",
            DocumentoGerado.titulo.ilike(f"%{nome}%"),
        )
        .order_by(DocumentoGerado.created_at.desc())
        .limit(1)
    )
    doc = result.scalar_one_or_none()

    if not doc:
        return {"status": "idle", "doc_id": None}
    if doc.conteudo == "__PROCESSANDO__":
        # Se preso há mais de 25 min (task hard timeout = 22 min), marca como erro
        from datetime import datetime, timezone
        idade = (datetime.now(timezone.utc) - doc.created_at.replace(tzinfo=timezone.utc)).total_seconds()
        if idade > 1500:  # 25 minutos
            doc.conteudo = "# ERRO\n\nA pesquisa excedeu o tempo máximo (22 min) e foi encerrada pelo servidor. Tente novamente."
            await db.commit()
            return {"status": "erro", "doc_id": str(doc.id), "erro": "Timeout — pesquisa excedeu 22 minutos."}
        return {"status": "processando", "doc_id": str(doc.id)}
    if doc.conteudo.startswith("# ERRO"):
        return {"status": "erro", "doc_id": str(doc.id), "erro": doc.conteudo[:300]}
    return {"status": "concluido", "doc_id": str(doc.id)}


# ── OSINT — Consultas brutas (sem LLM) ───────────────────────────────────────

@router.post(
    "/osint/enriquecer/pessoa/{pessoa_id}",
    summary="Consulta APIs externas para uma Pessoa (sem LLM)",
)
async def osint_enriquecer_pessoa(
    pessoa_id: uuid.UUID,
    inquerito_id: uuid.UUID,
    incluir_processos: bool = False,
    incluir_sancoes_internacionais: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Consulta a direct.data e retorna os dados brutos sem processar via LLM.
    Útil para preview antes de gerar a ficha completa.
    """
    osint = OsintService()
    try:
        dados = await osint.enriquecer_pessoa(
            db, inquerito_id, pessoa_id,
            incluir_processos=incluir_processos,
            incluir_sancoes_internacionais=incluir_sancoes_internacionais,
        )
        return {"status": "concluido", "dados_osint": dados}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na consulta OSINT: {str(e)[:200]}")


@router.post(
    "/osint/enriquecer/empresa/{empresa_id}",
    summary="Consulta APIs externas para uma Empresa (sem LLM)",
)
async def osint_enriquecer_empresa(
    empresa_id: uuid.UUID,
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Consulta Receita Federal + sanções via direct.data e retorna dados brutos."""
    osint = OsintService()
    try:
        dados = await osint.enriquecer_empresa(db, inquerito_id, empresa_id)
        return {"status": "concluido", "dados_osint": dados}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na consulta OSINT: {str(e)[:200]}")


@router.post(
    "/osint/veicular",
    summary="Consulta dados de um veículo pela placa",
)
async def osint_consulta_veicular(
    inquerito_id: uuid.UUID,
    placa: str,
    db: AsyncSession = Depends(get_db),
):
    """Retorna dados do veículo (marca, modelo, proprietário, restrições) via direct.data."""
    osint = OsintService()
    try:
        dados = await osint.consultar_placa(db, inquerito_id, placa)
        return {"status": "concluido", "dados_osint": dados}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na consulta veicular: {str(e)[:200]}")


@router.post(
    "/osint/consulta-avulsa",
    summary="Consulta OSINT avulsa por CPF, CNPJ, placa, nome ou RG",
)
async def osint_consulta_avulsa(
    cpf: str | None = None,
    cnpj: str | None = None,
    placa: str | None = None,
    nome: str | None = None,
    data_nascimento: str | None = None,
    rg: str | None = None,
    uf: str = "RJ",
    inquerito_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Consulta avulsa às APIs da direct.data.
    Se `inquerito_id` for informado, os resultados são persistidos em ConsultaExterna
    (com cache de 24h) e vinculados ao inquérito.
    """
    if not any([cpf, cnpj, placa, nome, rg]):
        raise HTTPException(
            status_code=422,
            detail="Informe ao menos um campo: cpf, cnpj, placa, nome ou rg."
        )
    osint = OsintService()
    try:
        if inquerito_id:
            # Consulta com persistência usando o pipeline com cache
            dados = await osint.consulta_avulsa_vinculada(
                db=db,
                inquerito_id=inquerito_id,
                cpf=cpf, cnpj=cnpj, placa=placa,
                nome=nome, data_nascimento=data_nascimento,
                rg=rg, uf=uf,
            )
        else:
            dados = await osint.consulta_avulsa(
                cpf=cpf, cnpj=cnpj, placa=placa,
                nome=nome, data_nascimento=data_nascimento,
                rg=rg, uf=uf,
            )

        # Cruzamento com inquéritos existentes no banco
        from app.services.copiloto_osint_service import buscar_historico_pessoa, buscar_historico_empresa
        historico = []
        if cpf:
            historico = await buscar_historico_pessoa(db, cpf, None)
        elif cnpj:
            historico = await buscar_historico_empresa(db, cnpj, None)
        dados["historico_inqueritos"] = historico

        return {"status": "concluido", "dados": dados}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na consulta avulsa: {str(e)[:200]}")


class OsintLoteItem(BaseModel):
    pessoa_id: uuid.UUID
    modulos: List[str] = []  # Lista de apis a rodar, vazia = ignorar


class OsintLoteRequest(BaseModel):
    inquerito_id: uuid.UUID
    itens: List[OsintLoteItem]


@router.post(
    "/osint/lote",
    summary="Enriquecimento OSINT em lote por módulos customizados",
)
async def osint_lote(
    body: OsintLoteRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Executa enriquecimento OSINT para múltiplas pessoas em paralelo.

    Cada item define `pessoa_id` e `modulos`:
    - `[]` → Ignorar (registra decisão, sem consulta)
    - `["cadastro_pf_plus", "vinculo_empregaticio", ...]` → Executa cirurgicamente os módulos pagos
    """
    if not body.itens:
        raise HTTPException(status_code=422, detail="Lista de itens não pode ser vazia.")

    osint = OsintService()
    try:
        itens = [{"pessoa_id": item.pessoa_id, "modulos": item.modulos} for item in body.itens]
        resultados = await osint.enriquecer_lote(db, body.inquerito_id, itens)

        custo_total = sum(
            r.get("dados", {}).get("custo_estimado", 0.0)
            for r in resultados
            if r.get("status") == "concluido"
        )

        return {
            "status": "concluido",
            "total_processados": len(resultados),
            "custo_estimado_total": round(custo_total, 2),
            "resultados": resultados,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no lote OSINT: {str(e)[:200]}")


@router.get(
    "/osint/historico-pessoa",
    summary="Inquéritos anteriores onde o mesmo CPF aparece",
)
async def osint_historico_pessoa(
    cpf: str,
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Busca em todos os inquéritos registros de Pessoa com o mesmo CPF,
    excluindo o inquérito atual. Retorna lista com número, ano e papel.
    """
    from app.services.copiloto_osint_service import buscar_historico_pessoa
    try:
        historico = await buscar_historico_pessoa(db, cpf, inquerito_id)
        return {"status": "ok", "total": len(historico), "historico": historico}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar histórico: {str(e)[:200]}")


@router.get(
    "/osint/historico-empresa",
    summary="Inquéritos anteriores onde o mesmo CNPJ aparece",
)
async def osint_historico_empresa(
    cnpj: str,
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Busca em todos os inquéritos registros de Empresa com o mesmo CNPJ,
    excluindo o inquérito atual.
    """
    from app.services.copiloto_osint_service import buscar_historico_empresa
    try:
        historico = await buscar_historico_empresa(db, cnpj, inquerito_id)
        return {"status": "ok", "total": len(historico), "historico": historico}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar histórico: {str(e)[:200]}")


@router.get(
    "/osint/sugestao/{inquerito_id}",
    summary="Análise de personagens e sugestão de perfil OSINT (Copiloto)",
)
async def osint_sugestao_personagens(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Para cada personagem do inquérito, analisa os dados já presentes nos autos (RAG)
    e sugere o perfil de enriquecimento OSINT (P1–P4) com justificativa.

    - Sem chamadas LLM nem direct.data — determinístico e gratuito
    - Staleness: ✓ = dado fresco (< 2 anos) | ⚠ = desatualizado | — = não encontrado
    - Custo total estimado calculado automaticamente
    """
    from app.services.copiloto_osint_service import CopilotoOsintService

    svc = CopilotoOsintService()
    try:
        resultado = await svc.analisar_personagens(db, inquerito_id)
        return {"status": "ok", "analise": resultado}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro na análise de personagens: {str(e)[:200]}"
        )


@router.get(
    "/osint/custo/{inquerito_id}",
    summary="Resumo de custo OSINT do inquérito",
)
async def osint_custo_inquerito(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retorna total de consultas pagas e custo estimado acumulado do inquérito."""
    osint = OsintService()
    try:
        resumo = await osint.custo_total_inquerito(db, inquerito_id)
        return {"status": "ok", "resumo": resumo}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao calcular custo: {str(e)[:200]}")


@router.get(
    "/osint/consultas/{inquerito_id}",
    summary="Lista consultas OSINT realizadas para o inquérito, agrupadas por pessoa",
)
async def osint_consultas_inquerito(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna todas as ConsultaExterna do inquérito, cruzando documento_hash
    com Pessoa.cpf para exibir nomes no frontend.
    Agrupa por pessoa (hash), cada grupo lista os módulos consultados.
    """
    # Busca consultas do inquérito
    result = await db.execute(
        select(ConsultaExterna)
        .where(ConsultaExterna.inquerito_id == inquerito_id)
        .order_by(ConsultaExterna.created_at.desc())
    )
    consultas = result.scalars().all()

    if not consultas:
        return {"consultas": []}

    # Monta dicionário hash → nome cruzando com pessoas do inquérito
    pessoas_result = await db.execute(
        select(Pessoa).where(Pessoa.inquerito_id == inquerito_id)
    )
    pessoas = pessoas_result.scalars().all()

    hash_para_nome: Dict[str, str] = {}
    for p in pessoas:
        # Por CPF
        if p.cpf:
            cpf_limpo = p.cpf.replace(".", "").replace("-", "").strip()
            hash_para_nome[ConsultaExterna.hash_documento(cpf_limpo)] = p.nome
        # Por nome (consultas sem CPF usam nome como documento_hash)
        if p.nome:
            hash_para_nome[ConsultaExterna.hash_documento(p.nome.strip())] = p.nome
            # Variações: maiúsculo/minúsculo
            hash_para_nome[ConsultaExterna.hash_documento(p.nome.strip().upper())] = p.nome
            hash_para_nome[ConsultaExterna.hash_documento(p.nome.strip().lower())] = p.nome

    # Agrupa por documento_hash
    grupos: Dict[str, Any] = {}
    for c in consultas:
        h = c.documento_hash
        if h not in grupos:
            # Tenta recuperar nome do resultado JSON quando não há cruzamento com Pessoa
            nome_fallback = None
            if c.resultado_json and isinstance(c.resultado_json, dict):
                nome_fallback = (
                    c.resultado_json.get("Nome")
                    or c.resultado_json.get("nome")
                    or c.resultado_json.get("NomePesquisado")
                )
            grupos[h] = {
                "documento_hash": h,
                "nome": hash_para_nome.get(h) or nome_fallback or "Alvo desconhecido",
                "modulos": [],
                "ultima_consulta": c.created_at.isoformat(),
            }
        grupos[h]["modulos"].append({
            "tipo": c.tipo_consulta,
            "status": c.status,
            "custo": float(c.custo_estimado or 0),
            "resultado": c.resultado_json,
            "data": c.created_at.isoformat(),
        })

    return {"consultas": list(grupos.values())}


# ── Cautelar ──────────────────────────────────────────────────────────────────

class CautelarRequest(BaseModel):
    inquerito_id: uuid.UUID
    tipo_cautelar: Literal[
        "oficio_requisicao",
        "mandado_busca",
        "interceptacao_telefonica",
        "quebra_sigilo_bancario",
        "autorizacao_prisao",
        "oficio_generico",
    ]
    instrucoes: str
    autoridade: str = "Comissário de Polícia Civil"
    model_config = ConfigDict(from_attributes=True)


@router.post(
    "/cautelar",
    summary="Gera minuta de ato cautelar/ofício policial",
)
async def gerar_cautelar(
    body: CautelarRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Gera minuta completa de ato cautelar ou ofício com base nas instruções
    do delegado e contexto do inquérito. Usa LLM Premium com prompt jurídico-policial.
    """
    agente = AgenteCautelar()
    try:
        resultado = await agente.gerar_cautelar(
            db=db,
            inquerito_id=body.inquerito_id,
            tipo_cautelar=body.tipo_cautelar,
            instrucoes=body.instrucoes,
            autoridade=body.autoridade,
        )
        return {"status": "concluido", "resultado": resultado}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar cautelar: {str(e)[:200]}")


# ── Análise de Extratos ──────────────────────────────────────────────────────

@router.post(
    "/extrato/{documento_id}",
    summary="Analisa extrato bancário de um documento",
)
async def analisar_extrato(
    documento_id: uuid.UUID,
    inquerito_id: uuid.UUID,
    forcar: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Analisa o texto extraído do documento como extrato bancário.
    Retorna JSON estruturado com transações, contrapartes e score de suspeição.
    Se `forcar=False`, retorna análise anterior do cache se disponível.
    """
    agente = AgenteExtrato()

    # Verificar cache se não forçar
    if not forcar:
        analise_anterior = await agente.obter_analise_anterior(db, inquerito_id, documento_id)
        if analise_anterior:
            return {"status": "cache", "analise": analise_anterior}

    try:
        analise = await agente.analisar_extrato(db, inquerito_id, documento_id)
        return {"status": "concluido", "analise": analise}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao analisar extrato: {str(e)[:200]}")


# ── Agente Sherlock ────────────────────────────────────────────────────────────

@router.post(
    "/sherlock/{inquerito_id}",
    summary="Agente Sherlock — análise estratégica em 5 camadas de raciocínio",
)
async def sherlock_analise(
    inquerito_id: uuid.UUID,
    forcar: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Gera análise estratégica completa do inquérito com 5 camadas de raciocínio:
    1. Matriz de Contradições (Cross-Check)
    2. Checklist de Tipicidade
    3. Backlog de Diligências (Urgente / Imprescindível / Estratégico)
    4. Tese de Autoria e Materialidade
    5. Advogado do Diabo (vulnerabilidades da tese)

    Cache de 6h em ResultadoAgente. Use `forcar=true` para regenerar.
    Requer RelatorioInicial gerado. Quanto mais dados (OSINT, fichas, síntese), melhor.
    """
    from app.services.sherlock_service import SherlockService

    agente = SherlockService()
    try:
        analise = await agente.gerar_estrategia(db, inquerito_id, forcar=forcar)
        return {"status": "concluido", "analise": analise}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception(f"[SHERLOCK] Erro para inquérito {inquerito_id}")
        raise HTTPException(status_code=500, detail=f"Erro Sherlock: {str(e)[:300]}")


# ── Transcrição de Áudio ──────────────────────────────────────────────────────


async def _transcrever_audio_servico(audio_bytes: bytes, filename: str) -> str:
    """Transcreve áudio usando Gemini (reutilizável por outros endpoints)."""
    from google import genai as _genai
    from google.genai import types as _genai_types
    from app.core.config import settings as _s

    client = _genai.Client(api_key=_s.GEMINI_API_KEY)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "webm"
    mime_map = {
        "ogg": "audio/ogg", "mp3": "audio/mpeg", "m4a": "audio/mp4",
        "wav": "audio/wav", "mp4": "video/mp4", "webm": "audio/webm",
        "mpeg": "audio/mpeg",
    }
    mime = mime_map.get(ext, "audio/webm")
    part = _genai_types.Part.from_bytes(data=audio_bytes, mime_type=mime)
    response = await client.aio.models.generate_content(
        model=_s.LLM_STANDARD_MODEL,
        contents=[
            "Transcreva fielmente o que foi dito neste áudio em português. "
            "Retorne apenas a transcrição, sem comentários adicionais.",
            part,
        ],
    )
    return response.text.strip()


@router.post("/transcrever", summary="Transcreve áudio para texto")
async def transcrever_audio(audio: UploadFile = File(...)):
    """
    Transcreve um arquivo de áudio usando Gemini.
    Aceita WebM, OGG, MP3, WAV, M4A.
    Retorna o texto transcrito.
    """
    audio_bytes = await audio.read()
    filename = audio.filename or "audio.webm"
    try:
        transcricao = await _transcrever_audio_servico(audio_bytes, filename)
        return {"transcricao": transcricao}
    except Exception as e:
        logger.error(f"[TRANSCREVER] Erro: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro na transcrição: {str(e)[:200]}")
