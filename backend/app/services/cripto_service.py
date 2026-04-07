"""
Escrivão AI — Agente Cripto (OSINT Blockchain)
Integração com Chainabuse e Blockchain Explorers para rastreio de ativos.
"""

import logging
import httpx
from typing import Any, Dict, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

class CriptoService:
    """
    Serviço especializado em rastreio de criptoativos e análise de risco.
    """

    def __init__(self):
        self.chainabuse_key = settings.CHAINABUSE_API_KEY
        self.etherscan_key = settings.ETHERSCAN_API_KEY
        self.tronscan_key = settings.TRONSCAN_API_KEY

    async def consultar_chainabuse(self, address: str) -> Dict[str, Any]:
        """
        Consulta o banco de dados do Chainabuse para verificar se o endereço foi denunciado.
        """
        if not self.chainabuse_key:
            return {"status": "nao_configurado", "mensagem": "API Key do Chainabuse não configurada."}

        url = f"https://api.chainabuse.com/v1/reports?address={address}"
        headers = {"Authorization": f"Basic {self.chainabuse_key}"}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 404:
                    return {"status": "limpo", "mensagem": "Nenhum reporte encontrado para este endereço."}
                resp.raise_for_status()
                data = resp.json()
                
                # Consolidar reportes
                return {
                    "status": "denunciado" if data else "limpo",
                    "total_reportes": len(data) if isinstance(data, list) else 0,
                    "detalhes": data
                }
        except Exception as e:
            logger.error(f"[CRIPTO-CHAINABUSE] Erro ao consultar {address}: {e}")
            return {"status": "erro", "mensagem": str(e)}

    async def rastrear_fluxo_ether(self, address: str, limit: int = 10) -> Dict[str, Any]:
        """
        Consulta histórico de transações na rede Ethereum via Etherscan.
        """
        if not self.etherscan_key:
            return {"status": "nao_configurado", "mensagem": "API Key do Etherscan não configurada."}

        url = "https://api.etherscan.io/api"
        params = {
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": limit,
            "sort": "desc",
            "apikey": self.etherscan_key
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                
                if data.get("status") != "1":
                    return {"status": "vazio", "mensagem": data.get("message", "Sem transações.")}

                return {
                    "status": "ok",
                    "transacoes": data.get("result", [])
                }
        except Exception as e:
            logger.error(f"[CRIPTO-ETHERSCAN] Erro ao rastrear {address}: {e}")
            return {"status": "erro", "mensagem": str(e)}

    async def analisar_carteira_completa(self, address: str) -> Dict[str, Any]:
        """
        Executa a análise completa (Chainabuse + Fluxo).
        """
        logger.info(f"[CRIPTO-AGENTE] Analisando carteira: {address}")
        
        # TODO: Detectar rede automaticamente (ETH, BTC, TRX)
        # Por enquanto assume-se Ethereum para endereços 0x
        
        chain_res = await self.consultar_chainabuse(address)
        
        if address.startswith("0x"):
            flow_res = await self.rastrear_fluxo_ether(address)
        else:
            flow_res = {"status": "nao_suportado", "mensagem": "Apenas rede Ethereum suportada no momento."}

        return {
            "address": address,
            "chainabuse": chain_res,
            "fluxo": flow_res
        }
