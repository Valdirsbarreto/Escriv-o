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
PROMPT_EXTRAIR_PECAS = """Você é um assistente jurídico especializado em inquéritos policiais brasileiros da Polícia Civil do Rio de Janeiro.

Analise o texto extraído de um PDF de autos de inquérito policial e identifique CADA peça individual.

Para cada peça, forneça:
- "titulo": nome descritivo e específico com nomes de pessoas quando relevante
  (ex: "Termo de Declaração de João da Silva", "Ofício nº 123/2024 ao ICCE", "Laudo Pericial Contábil")
- "tipo": OBRIGATORIAMENTE um dos valores abaixo — sem variações, sem tradução:
  termo_declaracao | termo_depoimento | termo_interrogatorio | auto_apreensao | auto_qualificacao |
  oficio_expedido | oficio_recebido | bo | registro_aditamento | portaria | despacho |
  requisicao | mandado | informacao_investigacao | relatorio_policial | laudo_pericial |
  quebra_sigilo | extrato_financeiro | representacao | certidao | notificacao |
  procuracao | peca_processual | outro
- "trecho_inicio": primeiros 120 caracteres ipsis litteris (âncora para localização)
- "pagina_inicial": número de página onde começa, ou null
- "pagina_final": número de página onde termina, ou null
- "resumo": 1 frase curta (máx 100 caracteres)

REGRAS DE DESAMBIGUAÇÃO (críticas):
1. bo vs registro_aditamento vs informacao_investigacao:
   - "bo": Boletim de Ocorrência com número de registro, data/hora do fato, vítima e autor declarados
   - "registro_aditamento": documento que complementa ou corrige um BO existente; título contém "aditamento"
   - "informacao_investigacao": relatório interno de inteligência policial SEM número de crime; tipicamente intitulado "Informação nº..." ou "Info. Invest..."
2. relatorio_policial vs informacao_investigacao:
   - "relatorio_policial": documento conclusivo (relatório final, relatório de diligência, relatório circunstanciado)
   - "informacao_investigacao": parecer analítico intermediário, não conclusivo
3. termo_declaracao vs termo_depoimento vs termo_interrogatorio:
   - "termo_declaracao": vítima ou testemunha voluntária (não intimada)
   - "termo_depoimento": testemunha formalmente intimada
   - "termo_interrogatorio": investigado, indiciado ou autuado
4. oficio_expedido vs oficio_recebido:
   - "oficio_expedido": enviado pela delegacia para outro órgão
   - "oficio_recebido": recebido de outro órgão pela delegacia
   - Se ambíguo, use "oficio_expedido"
5. quebra_sigilo vs extrato_financeiro:
   - "quebra_sigilo": decisão judicial ou representação que autoriza a quebra; também inclui dados telefônicos recebidos por ordem judicial
   - "extrato_financeiro": extrato bancário ou financeiro recebido via requisição comum

REGRAS GERAIS:
- NÃO reproduza o texto completo — apenas o trecho_inicio de 120 chars
- Use nomes completos nos títulos sempre que possível
- Se o texto for homogêneo (uma só peça), retorne um único item
- Não invente conteúdo; baseie-se exclusivamente no texto fornecido
- Retorne APENAS o JSON, sem explicações
- Máximo 25 peças por documento

Formato:
{
  "pecas": [
    {"titulo": "...", "tipo": "...", "trecho_inicio": "...", "pagina_inicial": null, "pagina_final": null, "resumo": "..."}
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
    return create_engine(
        _encode_password_in_url(sync_url),
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
        pool_recycle=300,
    )


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

            # Limitar input a 10k chars — reduz pressão sobre maxOutputTokens e evita truncamento JSON
            texto_limite = doc.texto_extraido[:10000]
            prompt = PROMPT_EXTRAIR_PECAS.replace("{texto}", texto_limite)

            api_key = settings.GEMINI_API_KEY
            if not api_key:
                logger.warning("[PEÇAS] GEMINI_API_KEY não configurada — extração cancelada")
                return

            model_name = settings.LLM_STANDARD_MODEL
            response = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent",
                params={"key": api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 8192,
                        "response_mime_type": "application/json",
                    },
                },
                timeout=60.0,
            )
            response.raise_for_status()

            raw = response.json()
            candidate = raw.get("candidates", [{}])[0]
            finish_reason = candidate.get("finishReason", "UNKNOWN")
            if finish_reason not in ("STOP", "MAX_TOKENS"):
                logger.warning(f"[PEÇAS] finishReason inesperado: {finish_reason} doc={documento_id}")
            elif finish_reason == "MAX_TOKENS":
                logger.warning(f"[PEÇAS] Resposta truncada por MAX_TOKENS doc={documento_id}")
            text_content = (
                candidate.get("content", {})
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
            raise self.retry(exc=RuntimeError(f"JSON inválido da IA: {e}"))
        except Exception as e:
            logger.error(f"[PEÇAS] Erro na extração de peças: {e}", exc_info=True)
            raise self.retry(exc=e)
