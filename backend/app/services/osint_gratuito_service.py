"""
Escrivão AI — OSINT Gratuito
Consultas a fontes abertas brasileiras sem custo por requisição.

Fontes:
  BrasilAPI  — CNPJ completo (Receita Federal espelhado), sem chave
  ViaCEP     — Endereço por CEP, sem chave
  CGU/CEIS   — Empresas sancionadas (portal transparência), sem chave
"""

import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

BRASIL_API_CNPJ  = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
VIACEP_URL       = "https://viacep.com.br/ws/{cep}/json/"
CGU_CEIS_URL     = "https://api.portaldatransparencia.gov.br/api-de-dados/ceis"


def _limpar_cnpj(cnpj: str) -> str:
    return "".join(c for c in (cnpj or "") if c.isdigit())


def _limpar_cep(cep: str) -> str:
    return "".join(c for c in (cep or "") if c.isdigit())


# ── CNPJ via BrasilAPI ────────────────────────────────────────────────────────

async def consultar_cnpj(cnpj_raw: str) -> Optional[Dict[str, Any]]:
    """
    Consulta dados completos de CNPJ via BrasilAPI (espelho Receita Federal).
    Retorna dict estruturado ou None em caso de erro.
    Sem chave de API, sem custo.
    """
    cnpj = _limpar_cnpj(cnpj_raw)
    if len(cnpj) != 14:
        logger.info(f"[OSINT-GRATUITO] CNPJ inválido: {cnpj_raw!r}")
        return None

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(BRASIL_API_CNPJ.format(cnpj=cnpj))

        if resp.status_code == 404:
            logger.info(f"[OSINT-GRATUITO] CNPJ {cnpj} não encontrado na Receita Federal")
            return None
        if resp.status_code == 429:
            logger.warning(f"[OSINT-GRATUITO] BrasilAPI rate-limit (429) para CNPJ {cnpj}")
            return None
        if resp.status_code >= 400:
            logger.warning(f"[OSINT-GRATUITO] BrasilAPI HTTP {resp.status_code} para CNPJ {cnpj}")
            return None

        data = resp.json()

        # Normalizar QSA (quadro societário)
        socios = []
        for s in data.get("qsa") or []:
            socios.append({
                "nome": s.get("nome_socio", ""),
                "qualificacao": s.get("qualificacao_socio", ""),
                "cpf_cnpj": s.get("cnpj_cpf_do_socio", ""),
                "entrada": s.get("data_entrada_sociedade", ""),
            })

        # Normalizar atividades
        atividade_principal = (data.get("cnae_fiscal_descricao") or "").strip()
        atividades_secundarias = [
            a.get("descricao", "") for a in (data.get("cnaes_secundarios") or [])
        ]

        return {
            "cnpj": cnpj,
            "razao_social": data.get("razao_social", ""),
            "nome_fantasia": data.get("nome_fantasia", ""),
            "situacao_cadastral": data.get("descricao_situacao_cadastral", ""),
            "data_abertura": data.get("data_inicio_atividade", ""),
            "natureza_juridica": data.get("natureza_juridica", ""),
            "porte": data.get("porte", ""),
            "capital_social": data.get("capital_social", 0),
            "endereco": {
                "logradouro": data.get("logradouro", ""),
                "numero": data.get("numero", ""),
                "complemento": data.get("complemento", ""),
                "bairro": data.get("bairro", ""),
                "municipio": data.get("municipio", ""),
                "uf": data.get("uf", ""),
                "cep": data.get("cep", ""),
            },
            "atividade_principal": atividade_principal,
            "atividades_secundarias": atividades_secundarias[:5],
            "socios": socios,
            "email": data.get("email", ""),
            "telefone": data.get("ddd_telefone_1", ""),
            "opcao_simples": data.get("opcao_pelo_simples", False),
            "opcao_mei": data.get("opcao_pelo_mei", False),
            "fonte": "BrasilAPI / Receita Federal",
        }

    except Exception as e:
        logger.warning(f"[OSINT-GRATUITO] Erro ao consultar CNPJ {cnpj}: {e}", exc_info=True)
        return None


# ── CEP via ViaCEP ────────────────────────────────────────────────────────────

async def consultar_cep(cep_raw: str) -> Optional[Dict[str, Any]]:
    """Consulta endereço por CEP via ViaCEP. Sem chave, sem custo."""
    cep = _limpar_cep(cep_raw)
    if len(cep) != 8:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(VIACEP_URL.format(cep=cep))
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("erro"):
            return None
        return {
            "logradouro": data.get("logradouro", ""),
            "bairro": data.get("bairro", ""),
            "municipio": data.get("localidade", ""),
            "uf": data.get("uf", ""),
            "cep": cep,
        }
    except Exception as e:
        logger.warning(f"[OSINT-GRATUITO] Erro ViaCEP {cep}: {e}")
        return None


# ── Sanções CGU / CEIS ────────────────────────────────────────────────────────

async def consultar_sancoes_cgu(nome: str) -> list:
    """
    Consulta empresas/pessoas sancionadas no CEIS (CGU).
    Requer header com chave gratuita — retorna lista vazia se não configurado.
    """
    from app.core.config import settings
    token = getattr(settings, "CGU_API_TOKEN", None)
    if not token:
        logger.debug("[OSINT-GRATUITO] CGU_API_TOKEN não configurado — CEIS skip")
        return []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                CGU_CEIS_URL,
                headers={"chave-api-dados": token},
                params={"nome": nome, "pagina": 1},
            )
        if resp.status_code >= 400:
            return []
        data = resp.json()
        sancoes = []
        for item in (data if isinstance(data, list) else []):
            sancoes.append({
                "nome": item.get("nomeInfrator", ""),
                "cpf_cnpj": item.get("cpfCnpjInfrator", ""),
                "sancao": item.get("tipoSancao", ""),
                "orgao": item.get("orgaoSancionador", ""),
                "data_inicio": item.get("dataInicioSancao", ""),
                "data_fim": item.get("dataFimSancao", ""),
            })
        return sancoes
    except Exception as e:
        logger.warning(f"[OSINT-GRATUITO] Erro CGU/CEIS: {e}")
        return []


# ── Formatador para LLM ───────────────────────────────────────────────────────

def formatar_dados_cnpj_para_llm(dados: Dict[str, Any]) -> str:
    """Converte resultado do CNPJ em texto estruturado para o prompt LLM."""
    linhas = [
        f"CNPJ: {dados['cnpj']}",
        f"Razão Social: {dados['razao_social']}",
        f"Nome Fantasia: {dados['nome_fantasia'] or '(não consta)'}",
        f"Situação: {dados['situacao_cadastral']}",
        f"Abertura: {dados['data_abertura']}",
        f"Natureza Jurídica: {dados['natureza_juridica']}",
        f"Porte: {dados['porte']}",
        f"Capital Social: R$ {dados['capital_social']:,.2f}",
        f"Simples Nacional: {'Sim' if dados['opcao_simples'] else 'Não'}",
        f"MEI: {'Sim' if dados['opcao_mei'] else 'Não'}",
        f"Atividade Principal: {dados['atividade_principal']}",
    ]
    if dados["atividades_secundarias"]:
        linhas.append("Atividades Secundárias: " + "; ".join(dados["atividades_secundarias"][:3]))

    end = dados["endereco"]
    linhas.append(
        f"Endereço: {end['logradouro']}, {end['numero']} {end['complemento']} — "
        f"{end['bairro']}, {end['municipio']}/{end['uf']} CEP {end['cep']}"
    )

    if dados["telefone"]:
        linhas.append(f"Telefone: {dados['telefone']}")
    if dados["email"]:
        linhas.append(f"E-mail: {dados['email']}")

    if dados["socios"]:
        linhas.append(f"\nQUADRO SOCIETÁRIO ({len(dados['socios'])} sócios):")
        for s in dados["socios"]:
            cpf_info = f" — CPF/CNPJ: {s['cpf_cnpj']}" if s["cpf_cnpj"] else ""
            entrada = f" (entrada: {s['entrada']})" if s["entrada"] else ""
            linhas.append(f"  • {s['nome']} ({s['qualificacao']}){cpf_info}{entrada}")

    return "\n".join(linhas)
