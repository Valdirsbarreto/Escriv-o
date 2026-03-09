"""
Escrivão AI — API: Agentes Especializados
Endpoints para os 3 agentes: Fichas OSINT, Produção Cautelar e Análise de Extratos.
Conforme blueprint §9 (Agentes Especializados).
"""

import uuid
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.agente_ficha import AgenteFicha
from app.services.agente_cautelar import AgenteCautelar
from app.services.agente_extrato import AgenteExtrato

router = APIRouter(prefix="/api/v1/agentes", tags=["Agentes Especializados"])


# ── Fichas OSINT ──────────────────────────────────────────────────────────────

@router.post(
    "/ficha/pessoa/{pessoa_id}",
    summary="Gera ficha investigativa de uma Pessoa",
)
async def gerar_ficha_pessoa(
    pessoa_id: uuid.UUID,
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Consolida todos os dados internos de uma Pessoa (contatos, endereços,
    cronologia) e gera uma ficha investigativa completa via LLM Premium.
    """
    agente = AgenteFicha()
    try:
        ficha = await agente.gerar_ficha_pessoa(db, inquerito_id, pessoa_id)
        return {"status": "concluido", "ficha": ficha}
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
    db: AsyncSession = Depends(get_db),
):
    """
    Consolida dados internos de uma Empresa e gera ficha investigativa.
    """
    agente = AgenteFicha()
    try:
        ficha = await agente.gerar_ficha_empresa(db, inquerito_id, empresa_id)
        return {"status": "concluido", "ficha": ficha}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar ficha: {str(e)[:200]}")


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
    autoridade: str = "Delegado de Polícia"
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
