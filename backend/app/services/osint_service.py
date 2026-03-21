"""
Escrivão AI — OSINT Service
Orquestra as consultas às APIs externas (direct.data) com cache e auditoria.

Fluxo por consulta:
  1. Verifica cache em ConsultaExterna (24h por padrão)
  2. Se não há cache: chama DirectDataService
  3. Persiste resultado + auditoria em ConsultaExterna
  4. Retorna dados consolidados ao chamador

Custos estimados (referência cardápio direct.data 2026):
  cadastro_pf_plus          R$ 2,50
  antecedentes_criminais    R$ 1,80
  mandados_prisao           R$ 1,20
  obito                     R$ 0,36
  pep                       R$ 0,72
  vinculos_societarios      R$ 1,84
  ceis / cnep / cepim       R$ 0,36 cada
  consulta_veicular         R$ 0,72
  processos_tj              R$ 2,00
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consulta_externa import ConsultaExterna
from app.models.pessoa import Pessoa
from app.models.empresa import Empresa
from app.services.directdata_service import DirectDataService, _limpar_documento

logger = logging.getLogger(__name__)

# Custo estimado por tipo de consulta (em R$)
CUSTOS: Dict[str, Decimal] = {
    "cadastro_pf":             Decimal("0.64"),
    "cadastro_pf_plus":        Decimal("2.50"),
    "antecedentes_criminais":  Decimal("1.80"),
    "mandados_prisao":         Decimal("1.20"),
    "obito":                   Decimal("0.36"),
    "pep":                     Decimal("0.72"),
    "vinculos_societarios":    Decimal("1.84"),
    "historico_veiculos_pf":   Decimal("0.90"),
    "receita_federal_pj":      Decimal("0.64"),
    "participacao_societaria": Decimal("1.20"),
    "ceis":                    Decimal("0.36"),
    "cnep":                    Decimal("0.36"),
    "cepim":                   Decimal("0.36"),
    "ofac":                    Decimal("0.36"),
    "lista_onu":               Decimal("0.36"),
    "aml":                     Decimal("0.72"),
    "consulta_veicular":       Decimal("0.72"),
    "processos_tj":            Decimal("2.00"),
    "processos_trf":           Decimal("2.00"),
}

CACHE_TTL_HORAS = 24

# Perfis de profundidade OSINT — quais APIs são acionadas por nível
_P1 = ["cadastro_pf_plus", "historico_veiculos_pf"]
_P2 = [*_P1, "mandados_prisao", "pep", "obito"]
_P3 = [*_P2, "aml", "ceis", "cnep"]
_P4 = [*_P3, "processos_tj", "ofac", "lista_onu"]

APIS_POR_PERFIL: Dict[int, List[str]] = {
    1: _P1,
    2: _P2,
    3: _P3,
    4: _P4,
}

# Custo estimado por perfil (soma dos custos das APIs incluídas)
CUSTO_POR_PERFIL: Dict[int, Decimal] = {
    1: Decimal("3.40"),   # cadastro_pf_plus + historico_veiculos
    2: Decimal("5.68"),   # P1 + mandados + pep + obito
    3: Decimal("7.76"),   # P2 + aml + ceis + cnep
    4: Decimal("11.76"),  # P3 + processos_tj + ofac + lista_onu
}


class OsintService:
    """Orquestra consultas externas com cache de 24h e auditoria automática."""

    def __init__(self):
        self.dd = DirectDataService()

    # ── Cache ──────────────────────────────────────────────────────────────────

    async def _buscar_cache(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        tipo_consulta: str,
        documento_limpo: str,
    ) -> Optional[ConsultaExterna]:
        """Retorna consulta cacheada se existir nas últimas CACHE_TTL_HORAS horas."""
        cutoff = datetime.utcnow() - timedelta(hours=CACHE_TTL_HORAS)
        doc_hash = ConsultaExterna.hash_documento(documento_limpo)
        result = await db.execute(
            select(ConsultaExterna)
            .where(ConsultaExterna.inquerito_id == inquerito_id)
            .where(ConsultaExterna.tipo_consulta == tipo_consulta)
            .where(ConsultaExterna.documento_hash == doc_hash)
            .where(ConsultaExterna.status == "ok")
            .where(ConsultaExterna.created_at > cutoff)
            .order_by(ConsultaExterna.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _salvar_auditoria(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        tipo_consulta: str,
        documento_limpo: str,
        resultado: Optional[Dict[str, Any]],
        status: str,
    ) -> ConsultaExterna:
        """Persiste resultado e metadados da consulta."""
        registro = ConsultaExterna(
            inquerito_id=inquerito_id,
            tipo_consulta=tipo_consulta,
            documento_hash=ConsultaExterna.hash_documento(documento_limpo),
            custo_estimado=CUSTOS.get(tipo_consulta),
            status=status,
            resultado_json=resultado,
        )
        db.add(registro)
        await db.commit()
        return registro

    async def _consultar(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        tipo_consulta: str,
        documento_limpo: str,
        fn,  # coroutine: async () -> dict
    ) -> Optional[Dict[str, Any]]:
        """
        Wrapper genérico: verifica cache → chama API → salva auditoria.
        Retorna None em caso de erro sem lançar exceção (não bloqueia a ficha).
        """
        cached = await self._buscar_cache(db, inquerito_id, tipo_consulta, documento_limpo)
        if cached:
            logger.info(f"[OSINT] Cache hit: {tipo_consulta} / {documento_limpo[-4:]}")
            return cached.resultado_json

        try:
            resultado = await fn()
            await self._salvar_auditoria(db, inquerito_id, tipo_consulta, documento_limpo, resultado, "ok")
            logger.info(f"[OSINT] OK: {tipo_consulta} / ***{documento_limpo[-4:]}")
            return resultado

        except Exception as e:
            status = "nao_encontrado" if "404" in str(e) else ("timeout" if "Timeout" in type(e).__name__ else "erro")
            await self._salvar_auditoria(db, inquerito_id, tipo_consulta, documento_limpo, None, status)
            logger.warning(f"[OSINT] {status}: {tipo_consulta} / ***{documento_limpo[-4:]} — {e}")
            return None

    # ── Enriquecimento de Pessoa ───────────────────────────────────────────────

    async def enriquecer_pessoa(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        pessoa_id: uuid.UUID,
        incluir_processos: bool = False,
        incluir_sancoes_internacionais: bool = False,
    ) -> Dict[str, Any]:
        """
        Fluxo principal de enriquecimento OSINT de uma Pessoa:
          - Cadastro Plus, Mandados de Prisão, Óbito, PEP, AML (vínculos + sociedades),
            Histórico de Veículos, CEIS, CNEP
          - Opcionalmente: Processos TJ, OFAC/ONU
        Retorna dict consolidado com todos os resultados (None onde falhou).

        Removidos do fluxo padrão (testado em 20/03/2026):
          - antecedentes_criminais: API Polícia Civil retorna 400 — parâmetros instáveis
          - vinculos_societarios: endpoint retorna 403 — fora do plano; AML substitui
        """
        pessoa = await db.get(Pessoa, pessoa_id)
        if not pessoa or not pessoa.cpf:
            return {"erro": "CPF não disponível para consulta OSINT"}

        cpf = _limpar_documento(pessoa.cpf)

        resultado: Dict[str, Any] = {"cpf": f"***{cpf[-4:]}", "nome_interno": pessoa.nome}

        # ── Bloco 1: Ficha Criminal Básica ────────────────────────────────────
        resultado["obito"] = await self._consultar(
            db, inquerito_id, "obito", cpf, lambda: self.dd.obito(cpf)
        )
        resultado["cadastro"] = await self._consultar(
            db, inquerito_id, "cadastro_pf_plus", cpf, lambda: self.dd.cadastro_pf_plus(cpf)
        )
        resultado["mandados_prisao"] = await self._consultar(
            db, inquerito_id, "mandados_prisao", cpf, lambda: self.dd.mandados_prisao(cpf)
        )
        resultado["pep"] = await self._consultar(
            db, inquerito_id, "pep", cpf, lambda: self.dd.pep(cpf)
        )

        # ── Bloco 2: Patrimônio e Vínculos ────────────────────────────────────
        # AML cobre vínculos societários + PEP + óbito em uma única chamada
        resultado["aml"] = await self._consultar(
            db, inquerito_id, "aml", cpf, lambda: self.dd.aml(cpf)
        )
        resultado["historico_veiculos"] = await self._consultar(
            db, inquerito_id, "historico_veiculos_pf", cpf, lambda: self.dd.historico_veiculos_pf(cpf)
        )

        # ── Bloco 3: Sanções Brasileiras ──────────────────────────────────────
        resultado["ceis"] = await self._consultar(
            db, inquerito_id, "ceis", cpf, lambda: self.dd.ceis(cpf)
        )
        resultado["cnep"] = await self._consultar(
            db, inquerito_id, "cnep", cpf, lambda: self.dd.cnep(cpf)
        )

        # ── Bloco 4: Opcionais ────────────────────────────────────────────────
        if incluir_processos:
            resultado["processos_tj"] = await self._consultar(
                db, inquerito_id, "processos_tj", cpf, lambda: self.dd.processos_tj(cpf)
            )

        if incluir_sancoes_internacionais and pessoa.nome:
            resultado["ofac"] = await self._consultar(
                db, inquerito_id, "ofac", cpf, lambda: self.dd.ofac(pessoa.nome)
            )
            resultado["lista_onu"] = await self._consultar(
                db, inquerito_id, "lista_onu", cpf, lambda: self.dd.lista_onu(pessoa.nome)
            )

        return resultado

    # ── Enriquecimento de Empresa ──────────────────────────────────────────────

    async def enriquecer_empresa(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        empresa_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Consultas para uma Empresa: Receita Federal, Participação Societária, Sanções.
        """
        empresa = await db.get(Empresa, empresa_id)
        if not empresa or not empresa.cnpj:
            return {"erro": "CNPJ não disponível para consulta OSINT"}

        cnpj = _limpar_documento(empresa.cnpj)
        resultado: Dict[str, Any] = {"cnpj": f"**{cnpj[-6:]}", "nome_interno": empresa.nome}

        resultado["receita_federal"] = await self._consultar(
            db, inquerito_id, "receita_federal_pj", cnpj, lambda: self.dd.receita_federal_pj(cnpj)
        )
        resultado["participacao_societaria"] = await self._consultar(
            db, inquerito_id, "participacao_societaria", cnpj, lambda: self.dd.participacao_societaria(cnpj)
        )
        resultado["ceis"] = await self._consultar(
            db, inquerito_id, "ceis", cnpj, lambda: self.dd.ceis(cnpj)
        )
        resultado["cnep"] = await self._consultar(
            db, inquerito_id, "cnep", cnpj, lambda: self.dd.cnep(cnpj)
        )
        resultado["processos_tj"] = await self._consultar(
            db, inquerito_id, "processos_tj", cnpj, lambda: self.dd.processos_tj(cnpj)
        )

        return resultado

    # ── Enriquecimento por Perfil (P1–P4) ─────────────────────────────────────

    async def enriquecer_por_perfil(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        pessoa_id: uuid.UUID,
        perfil: int,
    ) -> Dict[str, Any]:
        """
        Enriquece uma Pessoa com o conjunto de APIs correspondente ao perfil:
          P1 (1) — Localização: cadastro + veículos
          P2 (2) — Triagem Criminal: P1 + mandados + PEP + óbito
          P3 (3) — Investigação: P2 + AML + CEIS + CNEP
          P4 (4) — Profundo: P3 + processos TJ + OFAC + ONU

        Retorna dict com resultados de cada API + metadados do perfil.
        """
        if perfil not in APIS_POR_PERFIL:
            return {"erro": f"Perfil inválido: {perfil}. Use 1, 2, 3 ou 4."}

        pessoa = await db.get(Pessoa, pessoa_id)
        if not pessoa or not pessoa.cpf:
            return {"erro": "CPF não disponível para consulta OSINT"}

        cpf = _limpar_documento(pessoa.cpf)
        apis = APIS_POR_PERFIL[perfil]
        resultado: Dict[str, Any] = {
            "perfil": perfil,
            "custo_estimado": float(CUSTO_POR_PERFIL[perfil]),
            "apis_executadas": apis,
            "cpf": f"***{cpf[-4:]}",
            "nome_interno": pessoa.nome,
        }

        # Mapeamento de chave → coroutine factory
        api_map = {
            "cadastro_pf_plus":     ("cadastro",          lambda: self.dd.cadastro_pf_plus(cpf)),
            "historico_veiculos_pf":("historico_veiculos", lambda: self.dd.historico_veiculos_pf(cpf)),
            "mandados_prisao":      ("mandados_prisao",    lambda: self.dd.mandados_prisao(cpf)),
            "pep":                  ("pep",                lambda: self.dd.pep(cpf)),
            "obito":                ("obito",              lambda: self.dd.obito(cpf)),
            "aml":                  ("aml",                lambda: self.dd.aml(cpf)),
            "ceis":                 ("ceis",               lambda: self.dd.ceis(cpf)),
            "cnep":                 ("cnep",               lambda: self.dd.cnep(cpf)),
            "processos_tj":         ("processos_tj",       lambda: self.dd.processos_tj(cpf)),
            "ofac":                 ("ofac",               lambda: self.dd.ofac(pessoa.nome or "")),
            "lista_onu":            ("lista_onu",          lambda: self.dd.lista_onu(pessoa.nome or "")),
        }

        for api_key in apis:
            if api_key not in api_map:
                continue
            chave_resultado, fn = api_map[api_key]
            resultado[chave_resultado] = await self._consultar(
                db, inquerito_id, api_key, cpf, fn
            )

        return resultado

    async def enriquecer_lote(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        itens: List[Dict[str, Any]],  # [{pessoa_id, perfil}]
    ) -> List[Dict[str, Any]]:
        """
        Executa enriquecimento em lote para múltiplas pessoas em paralelo.
        Itens com perfil=None (Ignorar) são registrados mas não consultados.

        Retorna lista de resultados na mesma ordem dos itens de entrada.
        """
        async def _processar(item: Dict[str, Any]) -> Dict[str, Any]:
            pessoa_id = item["pessoa_id"]
            perfil = item.get("perfil")  # None = Ignorar

            if perfil is None:
                return {
                    "pessoa_id": str(pessoa_id),
                    "perfil": None,
                    "status": "ignorado",
                    "mensagem": "Delegado optou por não investigar este personagem.",
                }

            try:
                dados = await self.enriquecer_por_perfil(db, inquerito_id, pessoa_id, perfil)
                return {"pessoa_id": str(pessoa_id), "perfil": perfil, "status": "concluido", "dados": dados}
            except Exception as e:
                logger.error(f"[OSINT lote] pessoa_id={pessoa_id} perfil={perfil} erro: {e}")
                return {"pessoa_id": str(pessoa_id), "perfil": perfil, "status": "erro", "mensagem": str(e)[:200]}

        return await asyncio.gather(*[_processar(item) for item in itens])

    # ── Consulta Veicular Avulsa ───────────────────────────────────────────────

    async def consultar_placa(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        placa: str,
    ) -> Dict[str, Any]:
        """Consulta dados de um veículo pela placa."""
        placa_limpa = placa.upper().strip()
        resultado = await self._consultar(
            db, inquerito_id, "consulta_veicular", placa_limpa,
            lambda: self.dd.consulta_veicular(placa_limpa)
        )
        return resultado or {"erro": "Consulta veicular não retornou dados"}

    # ── Consulta Avulsa (sem inquérito vinculado) ──────────────────────────────

    async def consulta_avulsa(
        self,
        cpf: str | None = None,
        cnpj: str | None = None,
        placa: str | None = None,
        nome: str | None = None,
        data_nascimento: str | None = None,
        rg: str | None = None,
        uf: str = "RJ",
    ) -> Dict[str, Any]:
        """
        Consulta direta às APIs da direct.data sem vínculo com inquérito.
        Não persiste auditoria. Executa apenas as consultas para as quais
        há dados suficientes (CPF, CNPJ, placa, nome, etc.).

        Retorna dict com resultado de cada API tentada.
        """
        resultado: Dict[str, Any] = {"fontes_consultadas": [], "fontes_sem_dados": []}

        async def _tentar(chave: str, coro):
            try:
                r = await coro
                resultado[chave] = r.get("retorno", r)
                resultado["fontes_consultadas"].append(chave)
            except Exception as e:
                resultado[chave] = None
                resultado["fontes_sem_dados"].append({"fonte": chave, "motivo": str(e)[:120]})

        # ── Por CPF ───────────────────────────────────────────────────────────
        if cpf:
            cpf_limpo = _limpar_documento(cpf)
            await _tentar("cadastro",         self.dd.cadastro_pf_plus(cpf_limpo))
            await _tentar("mandados_prisao",  self.dd.mandados_prisao(cpf_limpo))
            await _tentar("obito",            self.dd.obito(cpf_limpo))
            await _tentar("pep",              self.dd.pep(cpf_limpo))
            await _tentar("aml",              self.dd.aml(cpf_limpo))
            await _tentar("historico_veiculos", self.dd.historico_veiculos_pf(cpf_limpo))
            await _tentar("ceis",             self.dd.ceis(cpf_limpo))
            await _tentar("cnep",             self.dd.cnep(cpf_limpo))

        # ── Por CNPJ ──────────────────────────────────────────────────────────
        if cnpj:
            cnpj_limpo = _limpar_documento(cnpj)
            await _tentar("receita_federal",        self.dd.receita_federal_pj(cnpj_limpo))
            await _tentar("participacao_societaria", self.dd.participacao_societaria(cnpj_limpo))
            await _tentar("ceis_pj",                self.dd.ceis(cnpj_limpo))
            await _tentar("cnep_pj",                self.dd.cnep(cnpj_limpo))

        # ── Por Placa ─────────────────────────────────────────────────────────
        if placa:
            await _tentar("veiculo", self.dd.consulta_veicular(placa))

        # ── Por Nome (sem CPF) ────────────────────────────────────────────────
        if nome and not cpf:
            await _tentar("mandados_por_nome", self.dd.mandados_prisao_por_nome(nome))

        # ── Por Nome + Data Nascimento + UF (RG ou nome) ──────────────────────
        if (nome or rg) and uf:
            await _tentar(
                "antecedentes_por_nome",
                self.dd.antecedentes_por_nome(
                    nome=nome, rg=rg,
                    data_nascimento=data_nascimento,
                    uf=uf,
                )
            )

        return resultado

    # ── Custo Acumulado do Inquérito ───────────────────────────────────────────

    async def custo_total_inquerito(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Retorna resumo de custo OSINT do inquérito."""
        result = await db.execute(
            select(ConsultaExterna)
            .where(ConsultaExterna.inquerito_id == inquerito_id)
            .order_by(ConsultaExterna.created_at.desc())
        )
        consultas = result.scalars().all()

        total = sum(c.custo_estimado or Decimal("0") for c in consultas if c.status == "ok")
        por_tipo = {}
        for c in consultas:
            por_tipo.setdefault(c.tipo_consulta, {"total": 0, "custo": Decimal("0")})
            por_tipo[c.tipo_consulta]["total"] += 1
            if c.status == "ok":
                por_tipo[c.tipo_consulta]["custo"] += c.custo_estimado or Decimal("0")

        return {
            "total_consultas": len(consultas),
            "custo_total_estimado": float(total),
            "por_tipo": {k: {"total": v["total"], "custo": float(v["custo"])} for k, v in por_tipo.items()},
        }
