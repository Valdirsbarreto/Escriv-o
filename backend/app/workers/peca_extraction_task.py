"""
Escrivão AI — Task Celery: Extração de Peças Individuais
Após ingestão, usa Gemini para identificar peças individuais dentro do PDF
(termos de declaração, ofícios, laudos, BOs, etc.) e salva cada uma como
um registro independente na tabela pecas_extraidas.
"""

import json
import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

from app.core.config import settings
from app.core.database import _encode_password_in_url
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Pedimos apenas METADADOS + uma frase-âncora para localizar o texto no doc original.
# Isso evita o estouro de maxOutputTokens que ocorre quando o Gemini copia o texto completo.
PROMPT_EXTRAIR_PECAS = """Você é um assistente jurídico especializado em inquéritos policiais brasileiros.

Analise o texto a seguir, que foi extraído de um arquivo PDF de autos de inquérito policial.
Um único PDF pode conter muitas peças distintas: termos de declaração, ofícios, laudos, boletins de ocorrência, autos de apreensão, portarias, despachos, etc.

SUA TAREFA:
Identifique CADA peça individual dentro deste texto e retorne um JSON com a lista de peças.

Para cada peça, forneça:
- "titulo": nome descritivo e específico, incluindo nomes de pessoas quando relevante
  (ex: "Termo de Declaração de João da Silva", "Ofício nº 123/2024 ao ICCE", "Laudo de Exame de Local de Crime")
- "tipo": uma das categorias: termo_declaracao | auto_apreensao | oficio | laudo | bo | despacho | portaria | requisicao | mandado | outro
- "trecho_inicio": copie ipsis litteris os primeiros 120 caracteres do texto desta peça (será usado para localizar o texto no documento)
- "pagina_inicial": número de página aproximado onde esta peça começa (se identificável), ou null
- "pagina_final": número de página aproximado onde esta peça termina (se identificável), ou null
- "resumo": resumo de 2-3 linhas descrevendo o conteúdo e relevância desta peça

REGRAS:
- NÃO reproduza o texto completo das peças — apenas o "trecho_inicio" de 120 chars
- Use nomes completos das pessoas nos títulos sempre que possível
- Se o texto for muito curto ou homogêneo (apenas uma peça), retorne um único item
- Não invente conteúdo; baseie-se exclusivamente no texto fornecido
- Retorne APENAS o JSON, sem explicações adicionais

Formato da resposta:
{
  "pecas": [
    {
      "titulo": "...",
      "tipo": "...",
      "trecho_inicio": "...",
      "pagina_inicial": null,
      "pagina_final": null,
      "resumo": "..."
    }
  ]
}

TEXTO DO DOCUMENTO:
{texto}
"""


def _build_sync_engine():
    raw_url = settings.DATABASE_URL
    if raw_url.startswith("postgresql://") or raw_url.startswith("postgres://"):
        sync_url = re.sub(r"^postgres(ql)?://", "postgresql://", raw_url)
    else:
        sync_url = raw_url.replace("postgresql+asyncpg://", "postgresql://")
    return create_engine(_encode_password_in_url(sync_url), pool_pre_ping=True)


def _extrair_conteudo_por_ancora(texto_doc: str, pecas_data: list) -> list:
    """
    Localiza cada peça no texto do documento usando 'trecho_inicio' como âncora.
    Extrai o texto entre o início de uma peça e o início da próxima.
    """
    # Encontra a posição de início de cada peça
    posicoes = []
    for p in pecas_data:
        ancora = (p.get("trecho_inicio") or "").strip()
        if not ancora:
            posicoes.append(-1)
            continue
        # Busca pelos primeiros 60 chars para tolerar pequenas variações
        busca = ancora[:60].strip()
        idx = texto_doc.find(busca)
        posicoes.append(idx)

    resultados = []
    for i, (p, pos_ini) in enumerate(zip(pecas_data, posicoes)):
        if pos_ini < 0:
            # Âncora não encontrada — usa o trecho_inicio como fallback
            conteudo = p.get("trecho_inicio") or ""
        else:
            # Fim desta peça = início da próxima (ou fim do doc)
            pos_fim = len(texto_doc)
            for j in range(i + 1, len(posicoes)):
                if posicoes[j] > pos_ini:
                    pos_fim = posicoes[j]
                    break
            conteudo = texto_doc[pos_ini:pos_fim].strip()

        resultados.append({**p, "conteudo_texto": conteudo})

    return resultados


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
def extrair_pecas_task(self, documento_id: str, inquerito_id: str):
    """
    Task Celery que extrai peças individuais de um documento PDF já ingerido.
    Disparada automaticamente após a ingestão ser concluída.
    """
    logger.info(f"[PEÇAS] Iniciando extração de peças para doc={documento_id}")

    engine = _build_sync_engine()
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as db:
        try:
            from app.models.documento import Documento
            from app.models.peca_extraida import PecaExtraida

            # Busca o documento e seu texto extraído
            doc = db.execute(
                select(Documento).where(Documento.id == uuid.UUID(documento_id))
            ).scalar_one_or_none()

            if not doc:
                logger.warning(f"[PEÇAS] Documento {documento_id} não encontrado")
                return

            if not doc.texto_extraido or len(doc.texto_extraido.strip()) < 100:
                logger.warning(f"[PEÇAS] Documento {documento_id} sem texto extraído suficiente")
                return

            # Verifica se já existem peças extraídas para este documento
            existing = db.execute(
                select(PecaExtraida).where(
                    PecaExtraida.documento_id == uuid.UUID(documento_id)
                ).limit(1)
            ).scalar_one_or_none()

            if existing:
                logger.info(f"[PEÇAS] Documento {documento_id} já tem peças extraídas — pulando")
                return

            # Chama Gemini via httpx (padrão do projeto)
            import httpx

            texto_limite = doc.texto_extraido[:80000]  # até 80k chars de entrada
            prompt = PROMPT_EXTRAIR_PECAS.replace("{texto}", texto_limite)

            api_key = settings.GEMINI_API_KEY
            if not api_key:
                logger.warning("[PEÇAS] GEMINI_API_KEY não configurada — extração cancelada")
                return

            model_name = settings.LLM_STANDARD_MODEL or "gemini-1.5-flash"
            response = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent",
                params={"key": api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 4096,  # suficiente para metadados apenas
                    },
                },
                timeout=120.0,
            )
            response.raise_for_status()

            raw = response.json()
            text_content = (
                raw.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )

            # Remove blocos de código markdown se presentes
            text_content = re.sub(r"```(?:json)?\n?", "", text_content).strip()

            parsed = json.loads(text_content)
            pecas_data = parsed.get("pecas", [])

            if not pecas_data:
                logger.warning(f"[PEÇAS] IA não identificou peças no documento {documento_id}")
                return

            # Localiza o texto de cada peça no documento original
            pecas_com_texto = _extrair_conteudo_por_ancora(doc.texto_extraido, pecas_data)

            # Persiste peças no banco
            doc_uuid = uuid.UUID(documento_id)
            inq_uuid = uuid.UUID(inquerito_id)
            criadas = 0

            for p in pecas_com_texto:
                titulo = (p.get("titulo") or "Peça sem título")[:500]
                tipo = (p.get("tipo") or "outro")[:80]
                conteudo = p.get("conteudo_texto") or ""
                if not conteudo.strip():
                    continue

                peca = PecaExtraida(
                    id=uuid.uuid4(),
                    inquerito_id=inq_uuid,
                    documento_id=doc_uuid,
                    titulo=titulo,
                    tipo=tipo,
                    conteudo_texto=conteudo,
                    pagina_inicial=p.get("pagina_inicial"),
                    pagina_final=p.get("pagina_final"),
                    resumo=(p.get("resumo") or "")[:2000] or None,
                )
                db.add(peca)
                criadas += 1

            db.commit()
            logger.info(f"[PEÇAS] {criadas} peças extraídas e salvas para doc={documento_id}")

        except json.JSONDecodeError as e:
            logger.error(f"[PEÇAS] Falha ao parsear JSON da IA: {e}")
        except Exception as e:
            logger.error(f"[PEÇAS] Erro na extração de peças: {e}", exc_info=True)
            raise self.retry(exc=e)
