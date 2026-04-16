"""
Escrivão AI — Task Celery: Relatório Complementar ao Relatório Final

Disparada quando o MP devolveu o inquérito relatado solicitando diligências
complementares e a autoridade as cumpriu (novas oitivas, laudos, etc.).

Fluxo:
1. Carrega o Relatório Inicial de IA como base estabelecida
2. Carrega TODOS os documentos indexados (inclui os novos produzidos após devolução do MP)
3. LLM Premium gera Relatório Complementar estruturado (5 seções):
   - Referência e Objeto (solicitação do MP)
   - Diligências Realizadas
   - Resultado das Diligências
   - Individualização de Conduta (se pedida)
   - Conclusão
4. Salva como DocumentoGerado(tipo="relatorio_complementar")
"""

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import _encode_password_in_url
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

PRIORIDADE_TIPO = {
    "oficio_recebido": 0,      # Cota Ministerial — vem primeiro sempre
    # Prova técnica e financeira
    "quebra_sigilo": 1,
    "extrato_financeiro": 1,
    "laudo_pericial": 2,
    # Oitivas e declarações (novas oitivas — foco do complementar)
    "termo_interrogatorio": 2,
    "termo_depoimento": 3,
    "termo_declaracao": 3,
    "termo_reconhecimento": 3,
    # Relatórios e informações
    "relatorio_policial": 4,
    "informacao_investigacao": 4,
    "registro_aditamento": 4,
    "representacao": 4,
    # Documentais
    "boletim_ocorrencia": 5,
    "auto_prisao_flagrante": 5,
    "auto_apreensao": 5,
    "resposta_orgao_externo": 5,
    # Ofícios expedidos
    "oficio_expedido": 6,
}

LIMITE_CHARS = 2_800_000


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
def gerar_relatorio_complementar_task(self, inquerito_id: str, forcar: bool = False):
    """Gera o Relatório Complementar ao Relatório Final."""
    logger.info(f"[REL-COMPLEMENTAR] Iniciando — inquerito={inquerito_id} forcar={forcar}")

    async def _run():
        from app.models.inquerito import Inquerito
        from app.models.documento import Documento
        from app.models.pessoa import Pessoa
        from app.models.documento_gerado import DocumentoGerado
        from app.services.summary_service import SummaryService
        from app.services.llm_service import LLMService
        from app.core.prompts import PROMPT_RELATORIO_COMPLEMENTAR, PROMPT_AUDITORIA_RELATORIO

        async_url = _encode_password_in_url(settings.DATABASE_URL)
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        async_url = async_url.replace("postgres://", "postgresql+asyncpg://", 1)

        import ssl
        connect_args = {"statement_cache_size": 0}
        if "supabase" in async_url or "localhost" not in async_url:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            connect_args["ssl"] = ctx

        from sqlalchemy.pool import NullPool
        engine = create_async_engine(async_url, connect_args=connect_args, poolclass=NullPool)
        AsyncSession_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        inq_uuid = uuid.UUID(inquerito_id)

        async with AsyncSession_() as db:
            inq = await db.get(Inquerito, inq_uuid)
            if not inq:
                logger.warning(f"[REL-COMPLEMENTAR] Inquérito não encontrado: {inquerito_id}")
                await engine.dispose()
                return {"status": "inquerito_nao_encontrado"}

            # ── 1. Verificar se já existe (respeitando forcar) ────────────────
            existing_result = await db.execute(
                select(DocumentoGerado)
                .where(DocumentoGerado.inquerito_id == inq_uuid)
                .where(DocumentoGerado.tipo == "relatorio_complementar")
                .order_by(DocumentoGerado.created_at.desc())
                .limit(1)
            )
            existing = existing_result.scalar_one_or_none()
            if existing and not forcar:
                logger.info(f"[REL-COMPLEMENTAR] Já existe — pulando (use forcar=true para regenerar)")
                await engine.dispose()
                return {"status": "ja_existe"}
            if existing and forcar:
                await db.delete(existing)
                logger.info(f"[REL-COMPLEMENTAR] Deletando versão anterior para regenerar")

            # ── 2. Carregar Relatório Inicial de IA como base ─────────────────
            rel_inicial_result = await db.execute(
                select(DocumentoGerado)
                .where(DocumentoGerado.inquerito_id == inq_uuid)
                .where(DocumentoGerado.tipo == "relatorio_inicial")
                .order_by(DocumentoGerado.created_at.desc())
                .limit(1)
            )
            rel_inicial = rel_inicial_result.scalar_one_or_none()
            relatorio_inicial_texto = rel_inicial.conteudo if rel_inicial else (
                "Relatório Inicial não disponível — analise os documentos diretamente."
            )
            if rel_inicial:
                logger.info(f"[REL-COMPLEMENTAR] Relatório Inicial carregado ({len(relatorio_inicial_texto):,} chars)")
            else:
                logger.warning(f"[REL-COMPLEMENTAR] Relatório Inicial não encontrado — prosseguindo sem ele")

            # ── 3. Coletar todos os documentos indexados ──────────────────────
            docs_result = await db.execute(
                select(Documento)
                .where(Documento.inquerito_id == inq_uuid)
                .where(Documento.status_processamento == "concluido")
                .where(Documento.tipo_peca != "sintese_investigativa")
            )
            todos_docs = docs_result.scalars().all()

            if not todos_docs:
                logger.warning(f"[REL-COMPLEMENTAR] Sem documentos indexados: {inquerito_id}")
                raise Exception("sem_documentos_ainda")

            # Ordena por prioridade — ofício do MP primeiro, depois novas oitivas
            docs_ordenados = sorted(
                todos_docs,
                key=lambda d: PRIORIDADE_TIPO.get(d.tipo_peca or "outro", 7)
            )

            partes_contexto = []
            total_chars = 0
            # Reserva espaço para o Relatório Inicial no prompt
            limite_docs = LIMITE_CHARS - min(len(relatorio_inicial_texto), 60_000)

            service = SummaryService()
            for d in docs_ordenados:
                texto = d.texto_extraido or ""
                if len(texto) < 200:
                    resumo = await service.obter_resumo_documento(db, inq_uuid, d.id)
                    texto = resumo or texto
                if not texto:
                    continue

                tipo = d.tipo_peca or "outro"
                cabecalho = f"=== {d.nome_arquivo} (tipo: {tipo}) ==="
                bloco = f"{cabecalho}\n{texto}"

                if total_chars + len(bloco) > limite_docs:
                    espaco = limite_docs - total_chars
                    if espaco > 500:
                        partes_contexto.append(f"{cabecalho}\n{texto[:espaco]}[...TRUNCADO]")
                        total_chars = limite_docs
                    break

                partes_contexto.append(bloco)
                total_chars += len(bloco)

            if not partes_contexto:
                raise Exception("sem_texto_extraido_nos_documentos")

            resumos_str = "\n\n---\n\n".join(partes_contexto)
            logger.info(
                f"[REL-COMPLEMENTAR] Contexto: {total_chars:,} chars de {len(todos_docs)} docs "
                f"({len(partes_contexto)} incluídos)"
            )

            # ── 4a. Isolar Cota Ministerial como campo dedicado ───────────────
            cota_doc = None
            for d in docs_ordenados:
                if d.tipo_peca in ("oficio_recebido",):
                    cota_doc = d
                    break

            if cota_doc:
                cota_texto = cota_doc.texto_extraido or ""
                if len(cota_texto) < 200:
                    cota_resumo = await service.obter_resumo_documento(db, inq_uuid, cota_doc.id)
                    cota_texto = cota_resumo or cota_texto
                cota_ministerial_bloco = (
                    f"Arquivo: {cota_doc.nome_arquivo} | tipo: {cota_doc.tipo_peca}\n"
                    f"--- início do documento ---\n{cota_texto}\n--- fim do documento ---"
                )
                logger.info(f"[REL-COMPLEMENTAR] Cota Ministerial isolada: {cota_doc.nome_arquivo} ({len(cota_texto):,} chars)")
            else:
                cota_ministerial_bloco = (
                    "[COTA MINISTERIAL NÃO LOCALIZADA NOS AUTOS INDEXADOS — "
                    "verificar tipo_peca do documento original: deve ser 'oficio_recebido']"
                )
                logger.warning(f"[REL-COMPLEMENTAR] Cota Ministerial não encontrada nos docs indexados")

            # ── 4b. Personagens ───────────────────────────────────────────────
            pessoas_result = await db.execute(
                select(Pessoa).where(Pessoa.inquerito_id == inq_uuid)
            )
            pessoas = pessoas_result.scalars().all()
            personagens_raw = "\n".join(
                f"- {p.nome} (CPF: {p.cpf or 'não informado'}) — tipo: {p.tipo_pessoa or 'não classificado'}"
                for p in pessoas
            ) or "Nenhum personagem identificado."

            # Lista separada com apenas investigados/indiciados para individualização
            tipos_investigado = {"investigado", "indiciado", "suspeito", "coautor", "suspeito_principal"}
            lista_indiciados = "\n".join(
                f"- {p.nome} (CPF: {p.cpf or 'não informado'})"
                for p in pessoas
                if (p.tipo_pessoa or "").lower() in tipos_investigado
            ) or "Nenhum investigado/indiciado classificado automaticamente — verificar personagens nos autos."
            logger.info(f"[REL-COMPLEMENTAR] Indiciados para individualização: {lista_indiciados.count(chr(10)) + 1} pessoas")

            # ── 5. Chamar LLM Premium ─────────────────────────────────────────
            prompt = PROMPT_RELATORIO_COMPLEMENTAR.format(
                relatorio_inicial=relatorio_inicial_texto[:60_000],
                cota_ministerial_bloco=cota_ministerial_bloco,
                resumos_documentos=resumos_str,
                personagens_raw=personagens_raw,
                lista_indiciados=lista_indiciados,
            )

            llm = LLMService()
            result_llm = await llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                tier="premium",
                temperature=0.1,
                max_tokens=8000,
                agente="RelatorioComplementar",
            )
            relatorio_rascunho = result_llm["content"].strip()

            # ── 5b. Auditoria Anti-Alucinação ─────────────────────────────────
            relatorio_texto = relatorio_rascunho
            try:
                prompt_auditoria = PROMPT_AUDITORIA_RELATORIO.format(
                    fontes_primarias=resumos_str[:300_000],
                    relatorio_gerado=relatorio_rascunho,
                )
                result_auditoria = await llm.chat_completion(
                    messages=[{"role": "user", "content": prompt_auditoria}],
                    tier="standard",
                    temperature=0.0,
                    max_tokens=5000,
                    agente="AuditorComplementar",
                )
                relatorio_auditado = result_auditoria["content"].strip()
                secoes_esperadas = ["## 1.", "## 2.", "## 5."]
                if relatorio_auditado and all(s in relatorio_auditado for s in secoes_esperadas):
                    if "## AUDITORIA FACTUAL" in relatorio_auditado:
                        partes = relatorio_auditado.split("## AUDITORIA FACTUAL")
                        relatorio_texto = partes[0].rstrip("-").strip()
                        logger.info(f"[REL-COMPLEMENTAR] Auditoria concluída")
                    else:
                        relatorio_texto = relatorio_auditado
                else:
                    logger.warning(f"[REL-COMPLEMENTAR] Auditoria descartada — usando rascunho")
            except Exception as e_audit:
                logger.warning(f"[REL-COMPLEMENTAR] Auditoria falhou: {e_audit}")

            # ── 6. Salvar como DocumentoGerado ────────────────────────────────
            doc_gerado = DocumentoGerado(
                inquerito_id=inq_uuid,
                tipo="relatorio_complementar",
                titulo=f"Relatório Complementar ao Relatório Final — {inq.numero}",
                conteudo=relatorio_texto,
                modelo_llm=result_llm.get("model"),
                tokens_prompt=result_llm.get("tokens_prompt"),
                tokens_resposta=result_llm.get("tokens_resposta"),
                custo_estimado=result_llm.get("custo_estimado"),
            )
            db.add(doc_gerado)
            await db.commit()
            logger.info(f"[REL-COMPLEMENTAR] Salvo — {len(relatorio_texto):,} chars")

        await engine.dispose()
        return {"status": "concluido", "inquerito_id": inquerito_id}

    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_run())
        loop.close()
        logger.info(f"[REL-COMPLEMENTAR] Concluído — {result}")
        return result
    except Exception as e:
        logger.error(f"[REL-COMPLEMENTAR] Erro: {e}")
        raise self.retry(exc=e)
