"""
Escrivão AI — Serper Service
Wrapper para a API Serper.dev (Google Search).
Executa dorks estratégicos em paralelo para OSINT de fontes abertas.

Auth: X-API-KEY header
Docs: https://serper.dev/
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)
SERPER_URL = "https://google.serper.dev/search"


class SerperService:
    def __init__(self):
        from app.core.config import settings
        self.api_key = settings.SERPER_API_KEY

    async def _buscar(self, client: httpx.AsyncClient, query: str, num: int = 10) -> List[Dict]:
        """Executa uma query e retorna lista de resultados orgânicos."""
        try:
            resp = await client.post(
                SERPER_URL,
                headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                json={"q": query, "num": num, "gl": "br", "hl": "pt"},
                timeout=20.0,
            )
            if resp.status_code >= 400:
                logger.warning(f"[Serper] HTTP {resp.status_code} — query: {query[:60]}")
                return []
            data = resp.json()
            return data.get("organic", [])
        except Exception as e:
            logger.warning(f"[Serper] Erro na query '{query[:60]}': {e}")
            return []

    async def buscar_pessoa(
        self,
        nome: str,
        cpf: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executa 5-6 dorks paralelos sobre o nome/CPF da pessoa.
        Retorna resultados agrupados por categoria.
        """
        dorks = [
            (f'"{nome}"', "geral"),
            (f'site:jusbrasil.com.br "{nome}"', "juridica"),
            (f'site:escavador.com "{nome}"', "juridica"),
            (f'"{nome}" site:in.gov.br', "oficial"),
            (f'"{nome}" crime OR investigação OR preso OR fraude OR policial', "alerta"),
        ]
        if cpf:
            cpf_limpo = cpf.replace(".", "").replace("-", "").replace("/", "").strip()
            if len(cpf_limpo) == 11:
                cpf_fmt = f"{cpf_limpo[:3]}.{cpf_limpo[3:6]}.{cpf_limpo[6:9]}-{cpf_limpo[9:]}"
                dorks.append((f'"{cpf_fmt}"', "cpf"))

        async with httpx.AsyncClient() as client:
            tasks = [self._buscar(client, query) for query, _ in dorks]
            resultados_raw = await asyncio.gather(*tasks)

        por_categoria: Dict[str, List] = {}
        termos_buscados = []
        total = 0

        for (query, categoria), resultados in zip(dorks, resultados_raw):
            termos_buscados.append(query)
            total += len(resultados)
            for r in resultados:
                por_categoria.setdefault(categoria, []).append({
                    "titulo": r.get("title", ""),
                    "url": r.get("link", ""),
                    "trecho": r.get("snippet", ""),
                    "posicao": r.get("position", 0),
                    "categoria": categoria,
                })

        return {
            "por_categoria": por_categoria,
            "termos_buscados": termos_buscados,
            "total_resultados": total,
        }
