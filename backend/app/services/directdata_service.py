"""
Escrivão AI — DirectData Service
Wrapper assíncrono para as APIs REST da direct.data (BigDataCorp).

Base URL : https://apiv3.directd.com.br
Auth     : TOKEN como query parameter (?TOKEN=xxx)
Swagger  : https://apiv3.directd.com.br/swagger/index.html

Parâmetros verificados via Swagger v3 em 20/03/2026.
"""

import logging
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)

DIRECTDATA_BASE_URL = "https://apiv3.directd.com.br"


def _limpar_documento(doc: str) -> str:
    """Remove pontuação de CPF/CNPJ, retornando apenas dígitos."""
    return doc.replace(".", "").replace("-", "").replace("/", "").strip()


def _tipo_documento(doc_limpo: str) -> str:
    """Retorna 'CPF' ou 'CNPJ' com base no número de dígitos."""
    return "CPF" if len(doc_limpo) <= 11 else "CNPJ"


class DirectDataService:
    """
    Wrapper para as APIs da direct.data.
    Cada chamada abre e fecha seu próprio httpx.AsyncClient para evitar
    vazamento de conexões em ambiente assíncrono.
    """

    def __init__(self):
        from app.core.config import settings
        self.token = settings.DIRECTDATA_API_TOKEN
        self.base = settings.DIRECTDATA_BASE_URL

    def _params(self, extras: Dict[str, str]) -> Dict[str, str]:
        """Monta dict de query params com TOKEN + campos da consulta."""
        return {"TOKEN": self.token, **extras}

    async def _get(self, path: str, campos: Dict[str, str]) -> Dict[str, Any]:
        """Executa GET autenticado e retorna JSON."""
        async with httpx.AsyncClient(base_url=self.base, timeout=60.0) as client:
            resp = await client.get(path, params=self._params(campos))
            if resp.status_code >= 400:
                logger.error(
                    f"[DirectData] HTTP {resp.status_code} em {path} "
                    f"params={list(campos.keys())} body={resp.text[:300]}"
                )
            resp.raise_for_status()
            return resp.json()

    # ── Pessoa Física ──────────────────────────────────────────────────────────

    async def cadastro_pf(self, cpf: str) -> Dict[str, Any]:
        """Cadastro básico — nome, situação na RF, data de nascimento."""
        return await self._get("/api/CadastroPessoaFisica", {"CPF": _limpar_documento(cpf)})

    async def cadastro_pf_plus(self, cpf: str) -> Dict[str, Any]:
        """Cadastro ampliado — histórico de endereços, filiação, renda estimada."""
        return await self._get("/api/CadastroPessoaFisicaPlus", {"CPF": _limpar_documento(cpf)})

    async def antecedentes_criminais(self, cpf: str, uf: str = "RJ") -> Dict[str, Any]:
        """Polícia Civil — Antecedentes Criminais. UF é obrigatório na API."""
        return await self._get("/api/PoliciaCivilAntecedentesCriminais", {
            "CPF": _limpar_documento(cpf),
            "UF": uf.upper(),
        })

    async def mandados_prisao(self, cpf: str) -> Dict[str, Any]:
        """CNJ — Mandados de Prisão ativos em nome do CPF."""
        return await self._get("/api/CNJMandadosPrisao", {"CPF": _limpar_documento(cpf)})

    async def mandados_prisao_por_nome(self, nome: str) -> Dict[str, Any]:
        """CNJ — Mandados de Prisão buscados pelo nome (sem CPF)."""
        return await self._get("/api/CNJMandadosPrisao", {"NOME": nome.strip()})

    async def antecedentes_por_nome(
        self,
        uf: str,
        nome: str | None = None,
        rg: str | None = None,
        data_nascimento: str | None = None,
    ) -> Dict[str, Any]:
        """Polícia Civil — Antecedentes por nome, RG ou data de nascimento (sem CPF). UF obrigatório."""
        campos: Dict[str, str] = {"UF": uf.upper()}
        if nome:
            campos["NOME"] = nome.strip()
        if rg:
            campos["RG"] = rg.strip()
        if data_nascimento:
            campos["DATANASCIMENTO"] = data_nascimento.strip()
        return await self._get("/api/PoliciaCivilAntecedentesCriminais", campos)

    async def obito(self, cpf: str) -> Dict[str, Any]:
        """Verifica se o CPF possui registro de óbito."""
        return await self._get("/api/Obito", {"CPF": _limpar_documento(cpf)})

    async def pep(self, cpf: str) -> Dict[str, Any]:
        """PEP — Pessoa Exposta Politicamente."""
        return await self._get("/api/PessoaExpostaPoliticamente", {"CPF": _limpar_documento(cpf)})

    async def vinculos_societarios(self, cpf: str) -> Dict[str, Any]:
        """Empresas onde o CPF figura como sócio ou administrador."""
        return await self._get("/api/VinculosSocietarios", {"CPF": _limpar_documento(cpf)})

    async def historico_veiculos_pf(self, cpf: str) -> Dict[str, Any]:
        """Histórico de veículos vinculados ao CPF."""
        return await self._get("/api/HistoricoVeiculos", {"CPF": _limpar_documento(cpf)})

    async def vinculo_empregaticio(self, cpf: str) -> Dict[str, Any]:
        """Busca o Vínculo Empregatício formal da pessoa."""
        return await self._get("/api/VinculoEmpregaticio", {"CPF": _limpar_documento(cpf)})

    async def bpc(self, cpf: str) -> Dict[str, Any]:
        """Busca Benefício de Prestação Continuada (BPC)."""
        return await self._get("/api/BeneficioDePrestacaoContinuada", {"CPF": _limpar_documento(cpf)})

    # ── Pessoa Jurídica ───────────────────────────────────────────────────────

    async def receita_federal_pj(self, cnpj: str) -> Dict[str, Any]:
        """Receita Federal — dados da empresa, QSA, situação cadastral."""
        return await self._get("/api/ReceitaFederalPessoaJuridica", {"CNPJ": _limpar_documento(cnpj)})

    async def participacao_societaria(self, cnpj: str) -> Dict[str, Any]:
        """Receita Federal — QSA + Participação Societária."""
        return await self._get("/api/ReceitaPJParticipacaoSocietaria", {"CNPJ": _limpar_documento(cnpj)})

    # ── Sanções e Restrições ──────────────────────────────────────────────────

    async def ceis(self, documento: str) -> Dict[str, Any]:
        """CEIS — Cadastro de Empresas Inidôneas e Suspensas (CGU).
        Aceita CPF ou CNPJ — detectado automaticamente pelo número de dígitos."""
        doc = _limpar_documento(documento)
        return await self._get("/api/CadastroEmpresasInidoneasSuspensas", {_tipo_documento(doc): doc})

    async def cnep(self, documento: str) -> Dict[str, Any]:
        """CNEP — Cadastro Nacional de Empresas Punidas (CGU)."""
        doc = _limpar_documento(documento)
        return await self._get("/api/CadastroNacionalEmpresasPunidas", {_tipo_documento(doc): doc})

    async def cepim(self, documento: str) -> Dict[str, Any]:
        """CEPIM — Entidades impedidas de receber recursos federais."""
        doc = _limpar_documento(documento)
        return await self._get("/api/CadastroEntidadesPrivadasImpedidas", {_tipo_documento(doc): doc})

    async def ofac(self, nome: str) -> Dict[str, Any]:
        """OFAC — Sanctions List (SDN and Non-SDN)."""
        return await self._get("/api/OFAC", {"NOME": nome})

    async def lista_onu(self, nome: str) -> Dict[str, Any]:
        """UNSCCL — United Nations Security Council Consolidated List."""
        return await self._get("/api/UnitedNationsSecurityList", {"NOME": nome})

    async def aml(self, cpf: str) -> Dict[str, Any]:
        """AML — Anti Money Laundering (vínculos societários suspeitos)."""
        return await self._get("/api/AML", {"CPF": _limpar_documento(cpf)})

    # ── Veicular ──────────────────────────────────────────────────────────────

    async def consulta_veicular(self, placa: str) -> Dict[str, Any]:
        """Dados do veículo pela placa (marca, modelo, ano, cor, restrições)."""
        return await self._get("/api/ConsultaVeicular", {"PLACA": placa.upper().strip()})

    # ── Processos Judiciais ───────────────────────────────────────────────────

    async def processos_tj(self, cpf_cnpj: str, uf: str = "RJ", grau: str = "1") -> Dict[str, Any]:
        """TJ — Tribunal de Justiça — Processos. UF e GRAU são obrigatórios na API."""
        doc = _limpar_documento(cpf_cnpj)
        return await self._get("/api/TribunalJustica", {
            _tipo_documento(doc): doc,
            "UF": uf.upper(),
            "GRAU": grau,
        })

    async def processos_trf(self, cpf_cnpj: str, regiao: str = "2", tipo: str = "cpf") -> Dict[str, Any]:
        """TRF — Tribunal Regional Federal. REGIAO e TIPO são obrigatórios na API.
        Regiões: 1=DF/Norte/Centro-Oeste, 2=RJ/ES, 3=SP/MS, 4=Sul, 5=Nordeste."""
        doc = _limpar_documento(cpf_cnpj)
        return await self._get("/api/TribunalRegionalFederal", {
            _tipo_documento(doc): doc,
            "REGIAO": regiao,
            "TIPO": tipo,
        })
