#!/usr/bin/env python3
"""
Escrivão AI - Ingestor de Casos Históricos (PoC - Fase 2, 3 e 4)

Este script:
1. Simula acórdãos e peças de Inquérito Policial (IP) do STJ (Casos de Sucesso).
2. Usa o Gemini 1.5 Flash (via LlmService) para extrair o fluxo investigativo anonimizado.
3. Gera embeddings com o EmbeddingService.
4. Salva no Qdrant na coleção `casos_historicos`.
"""

import asyncio
import json
import logging
import os
import sys
import uuid

# Adiciona o dretório pai ao sys.path para importar `app`
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.llm_service import LLMService
from app.services.embedding_service import EmbeddingService
from app.services.qdrant_service import QdrantService
from qdrant_client.models import PointStruct

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Casos brutos simulados (O que viria de um web scraper do Jusbrasil/STJ)
CASOS_BRUTOS = [
    {
        "id_processo": "HC-123456-STJ-RJ",
        "inteiro_teor": '''
            HABEAS CORPUS Nº 123.456 - RJ
            O Ministério Público denunciou João "O Alemão" e a empresa Transporte Lava Jato Ltda 
            por organização criminosa e lavagem de capitais referente ao tráfico de entorpecentes.
            A defesa alega nulidade da prova obtida.
            Consta nos autos que a investigação iniciou-se através do Coaf (Relatório de Inteligência Financeira - RIF), 
            que detectou movimentações atípicas de R$ 5 milhões. A Polícia Civil do RJ, não encontrando drogas inicialmente, 
            executou diligência via ferramentas OSINT cruzando dados do quadro societário da Transporte Lava Jato, 
            identificando parentes (laranjas). Em seguida, representou pela quebra de sigilo telemático e bancário.
            Com os logs telemáticos, interceptaram a localização exata de um galpão.
            Na busca e apreensão, acharam 200 kg de cocaína. 
            O STJ decide: O procedimento policial foi irretocável. A quebra de sigilo baseada em RIF cruzada com OSINT processual é lícita. 
            Ordem denegada. Prisão mantida.
        '''
    },
    {
        "id_processo": "AP-999888-STJ-SP",
        "inteiro_teor": '''
            APELAÇÃO PENAL Nº 999.888 - SP
            A apelante Maria do Carmo "Dona" requer a absolvição do crime de estelionato digital via PIX.
            O Inquérito Policial 55/2024 da Divisão de Cibernética mostrou que, após dezenas de B.Os relatando o "Golpe do Falso Parente", 
            a equipe não tinha suspeitos físicos.
            Estratégia: A equipe usou ferramentas OSINT de Vínculo Empregatício para achar as contas CLT em nome de "laranjas" 
            que recebiam os PIX, constatando que muitos eram falecidos (Óbito) no mesmo hospital. 
            Com isso, cruzaram a folha de pagamento do hospital e identificaram a apelante, que era a administradora dos leitos.
            A quebra de sigilo das contas não deixou dúvidas: ela desviava o dinheiro via contas digitais abertas com dados de pessoas mortas.
            Decisão: Materialidade fartamente comprovada pela inteligência policial ao associar cruzamento de vínculo empregatício e óbitos. 
            Recurso desprovido. Condenação a 8 anos de reclusão mantida.
        '''
    }
]

SYSTEM_PROMPT = """
Você é um professor de inteligência policial e análise forense.
Leia o Acórdão Judicial fornecido (resumo do caso).
Sua missão é extrair ESTRITAMENTE a estratégia policial bem-sucedida que fundamentou o caso.

REGRAS OBRIGATÓRIAS:
1. Anonimize o caso (NÃO cite nomes de acusados, laranjas, cidades ou empresas reais).
2. Retorne um JSON válido com os seguintes campos:
   - "natureza_crime": (str) Ex: "Tráfico e Lavagem"
   - "insight_aprendido": (str) Resumo de 1 a 2 parágrafos de COMO a investigação policial evoluiu do nada até a prova cabal.
   - "ferramentas_sugeridas": (list of str) Ex: ["OSINT", "Quebra Bancária", "RIF"]

NÃO RETORNE NENHUM TEXTO FORA DO JSON. NEM MARKDOWN COM ```json ... ```. APENAS O RAW JSON.
"""

async def rodar_ingestao():
    logger.info("Iniciando Fase 2 e 3: Triagem com Gemini 1.5 Flash...")
    llm = LLMService()
    qdrant = QdrantService()
    qdrant.ensure_collection() # Cria casos_historicos se não existir
    embedding_svc = EmbeddingService()

    pontos = []
    
    for caso in CASOS_BRUTOS:
        logger.info(f"Processando processo: {caso['id_processo']}")
        
        mensagens = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": caso["inteiro_teor"]}
        ]
        
        # Usa o Flash (standard) pq é rápido e ultra barato para ler texto pesado
        resposta = await llm.chat_completion(
            messages=mensagens,
            tier="standard", 
            temperature=0.1,
            max_tokens=1000,
            json_mode=True, 
            agente="IngestorHistorico"
        )
        
        texto_limpo = resposta["content"].strip()
        try:
            dados_estruturados = json.loads(texto_limpo)
        except Exception as e:
            logger.error(f"Erro ao parsear JSON do LLM: {texto_limpo}")
            continue
            
        natureza = dados_estruturados.get("natureza_crime", "")
        insight = dados_estruturados.get("insight_aprendido", "")
        
        # Fase 4: Criar Embedding do Insight (pois é como o Copiloto vai pesquisar)
        texto_busca = f"Crime: {natureza}\nTática Vencedora: {insight}"
        vetor = embedding_svc.generate(texto_busca)
        
        p = PointStruct(
            id=str(uuid.uuid4()),
            vector=vetor,
            payload={
                "id_processo_referencia": caso["id_processo"],
                "natureza_crime": natureza,
                "insight_aprendido": insight,
                "ferramentas_sugeridas": dados_estruturados.get("ferramentas_sugeridas", [])
            }
        )
        pontos.append(p)
        logger.info(f"OK. Aprendizado extraído: {insight[:80]}...")

    if pontos:
        logger.info("Fase 4: Injetando embeddings na collection 'casos_historicos'...")
        qdrant.client.upsert(
            collection_name="casos_historicos",
            points=pontos
        )
        logger.info(f"Sucesso! {len(pontos)} casos históricos indexados e prontos para o Copiloto.")

if __name__ == "__main__":
    # Workaround Windows ProactorEventLoop em asyncio rodando em background
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(rodar_ingestao())
