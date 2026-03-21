"""
Escrivão AI — API: Agentes Especializados
Endpoints para os 3 agentes: Fichas OSINT, Produção Cautelar e Análise de Extratos.
Conforme blueprint §9 (Agentes Especializados).
"""

import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
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
    db: AsyncSession = Depends(get_db),
):
    """
    Consulta avulsa às APIs da direct.data, sem vínculo com inquérito.
    Passe qualquer combinação de parâmetros disponíveis:

    - **CPF** → cadastro, mandados, óbito, PEP, AML, veículos, sanções
    - **CNPJ** → Receita Federal, participação societária, sanções PJ
    - **Placa** → dados do veículo
    - **Nome** → mandados de prisão por nome (sem CPF)
    - **Nome / RG + UF** → antecedentes criminais (UF obrigatório, default RJ)
    """
    if not any([cpf, cnpj, placa, nome, rg]):
        raise HTTPException(
            status_code=422,
            detail="Informe ao menos um campo: cpf, cnpj, placa, nome ou rg."
        )
    osint = OsintService()
    try:
        dados = await osint.consulta_avulsa(
            cpf=cpf, cnpj=cnpj, placa=placa,
            nome=nome, data_nascimento=data_nascimento,
            rg=rg, uf=uf,
        )
        return {"status": "concluido", "dados": dados}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na consulta avulsa: {str(e)[:200]}")


class OsintLoteItem(BaseModel):
    pessoa_id: uuid.UUID
    perfil: Optional[int] = None  # None = Ignorar; 1-4 = profundidade


class OsintLoteRequest(BaseModel):
    inquerito_id: uuid.UUID
    itens: List[OsintLoteItem]


@router.post(
    "/osint/lote",
    summary="Enriquecimento OSINT em lote por perfil de profundidade",
)
async def osint_lote(
    body: OsintLoteRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Executa enriquecimento OSINT para múltiplas pessoas em paralelo.

    Cada item define `pessoa_id` e `perfil`:
    - `null` → Ignorar (registra decisão, sem consulta)
    - `1` → P1 Localização (cadastro + veículos) ~R$ 3,40
    - `2` → P2 Triagem Criminal (P1 + mandados + PEP + óbito) ~R$ 5,68
    - `3` → P3 Investigação (P2 + AML + CEIS + CNEP) ~R$ 7,76
    - `4` → P4 Profundo (P3 + processos TJ + OFAC + ONU) ~R$ 11,76
    """
    if not body.itens:
        raise HTTPException(status_code=422, detail="Lista de itens não pode ser vazia.")

    osint = OsintService()
    try:
        itens = [{"pessoa_id": item.pessoa_id, "perfil": item.perfil} for item in body.itens]
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
