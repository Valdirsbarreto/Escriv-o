"""
Escrivão AI — Task Celery: Relatório Inicial de Investigação
Disparada quando todos os documentos de um inquérito estão indexados.

Fluxo:
1. Coleta resumos de todos os documentos + último aditamento do BO
2. LLM Premium gera Relatório Inicial estruturado (8 seções)
3. Salva como DocumentoGerado(tipo="relatorio_inicial") — 1ª peça na área de IA
4. Extrai e atualiza tipo_pessoa dos personagens (suspeito_principal, coautor, vitima,
   testemunha, policial_investigador, advogado, outro)
5. Atualiza Inquerito.descricao com o fato da Seção 1
6. Dispara generate_analise_task (síntese usa o relatório como contexto)
"""

import asyncio
import json
import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import _encode_password_in_url
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Papéis válidos para tipo_pessoa
PAPEIS_VALIDOS = {
    "suspeito_principal", "coautor", "vitima", "testemunha",
    "policial_investigador", "advogado", "outro",
    # legado (mantidos para compatibilidade)
    "investigado",
}

# Regex para extrair seções do relatório
_RE_SECAO = re.compile(
    r"##\s*(\d+)\.\s*([^\n]+)\n(.*?)(?=##\s*\d+\.|$)",
    re.DOTALL,
)
# Regex para extrair nomes de linha "- **Nome**: ..."
_RE_PESSOA = re.compile(r"-\s*\*\*([^*]+)\*\*")


def _extrair_personagens_da_secao(texto_secao: str) -> list[str]:
    return [m.group(1).strip() for m in _RE_PESSOA.finditer(texto_secao)]


def _normalizar_nome(nome: str) -> str:
    import unicodedata
    nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", nome).strip().lower()


@celery_app.task(bind=True, max_retries=1, default_retry_delay=30, time_limit=1200, soft_time_limit=1140)
def gerar_relatorio_inicial_task(self, inquerito_id: str):
    """Gera o Relatório Inicial de Investigação para o inquérito."""
    logger.info(f"[REL-INICIAL] Iniciando — inquerito={inquerito_id}")

    async def _run():
        from app.models.inquerito import Inquerito
        from app.models.documento import Documento
        from app.models.pessoa import Pessoa
        from app.models.documento_gerado import DocumentoGerado
        from app.services.summary_service import SummaryService
        from app.services.llm_service import LLMService
        from app.core.prompts import PROMPT_RELATORIO_INICIAL, PROMPT_AUDITORIA_RELATORIO

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
                logger.warning(f"[REL-INICIAL] Inquérito não encontrado: {inquerito_id}")
                await engine.dispose()
                return {"status": "inquerito_nao_encontrado"}

            # ── 1. Verificar se já existe relatório inicial ───────────────────
            existing = await db.execute(
                select(DocumentoGerado)
                .where(DocumentoGerado.inquerito_id == inq_uuid)
                .where(DocumentoGerado.tipo == "relatorio_inicial")
                .limit(1)
            )
            if existing.scalar_one_or_none():
                logger.info(f"[REL-INICIAL] Já existe relatório inicial — pulando")
                await engine.dispose()
                return {"status": "ja_existe"}

            # ── 1b. Gravar placeholder imediatamente para evitar execução concorrente ──
            # Se dois workers checarem "já existe?" ao mesmo tempo (race condition pós-deploy),
            # ambos passariam. O placeholder garante que apenas um prossiga: o segundo
            # encontrará o placeholder na próxima checagem.
            placeholder = DocumentoGerado(
                inquerito_id=inq_uuid,
                tipo="relatorio_inicial",
                titulo=f"Relatório Inicial de Investigação — {inq.numero}",
                conteudo="__PROCESSANDO__",
            )
            db.add(placeholder)
            await db.commit()
            await db.refresh(placeholder)
            logger.info(f"[REL-INICIAL] Placeholder criado — iniciando geração LLM")

            # ── 2. Coletar resumos dos documentos ─────────────────────────────
            docs_result = await db.execute(
                select(Documento)
                .where(Documento.inquerito_id == inq_uuid)
                .where(Documento.status_processamento == "concluido")
                .where(Documento.tipo_peca != "sintese_investigativa")
            )
            todos_docs = docs_result.scalars().all()

            if not todos_docs:
                logger.warning(f"[REL-INICIAL] Sem docs indexados ainda: {inquerito_id}")
                raise Exception("sem_documentos_ainda")

            # ── 2b. Montar contexto completo — texto_extraido direto (não resumos)
            # Gemini 1.5 Pro suporta 2M tokens. Para inquéritos complexos (10+ volumes,
            # interceptações, quebras de sigilo), o modelo precisa de 500k-700k tokens
            # para correlacionar provas entre volumes. ~3M chars ≈ 750k tokens (PT-BR).
            # Prioridade: quebras de sigilo e extratos primeiro (dados técnicos densos),
            # depois depoimentos/oitivas, depois relatórios, por último demais peças.

            PRIORIDADE_TIPO = {
                # Prova técnica e financeira — leitura densa
                "quebra_sigilo": 0,
                "extrato_financeiro": 0,
                "laudo_pericial": 1,
                # Oitivas e declarações
                "termo_interrogatorio": 1,
                "termo_depoimento": 2,
                "termo_declaracao": 2,
                "termo_reconhecimento": 2,
                # Relatórios e informações investigativas
                "relatorio_policial": 3,
                "informacao_investigacao": 3,
                "registro_aditamento": 3,
                # Representações cautelares (contexto do pedido)
                "representacao": 3,
                # Peças inaugurais e documentais
                "boletim_ocorrencia": 4,
                "auto_prisao_flagrante": 4,
                "auto_apreensao": 4,
                "resposta_orgao_externo": 4,
                # Ofícios e controle externo
                "oficio_expedido": 5,
                "oficio_recebido": 5,
            }

            docs_ordenados = sorted(
                todos_docs,
                key=lambda d: PRIORIDADE_TIPO.get(d.tipo_peca or "outro", 6)
            )

            partes_contexto = []
            ultimo_aditamento = ""
            total_chars = 0
            LIMITE_CHARS = 2_800_000  # ~700k tokens PT-BR — limite operacional seguro

            service = SummaryService()
            docs_sem_texto = []

            for d in docs_ordenados:
                # Usa texto extraído completo como fonte primária
                texto_completo = d.texto_extraido or ""
                # Fallback: resumo (quando OCR não gerou texto ou doc é muito curto)
                if len(texto_completo) < 200:
                    resumo = await service.obter_resumo_documento(db, inq_uuid, d.id)
                    texto_completo = resumo or texto_completo

                if not texto_completo:
                    docs_sem_texto.append(d.nome_arquivo)
                    continue

                tipo = d.tipo_peca or "outro"
                cabecalho = f"=== {d.nome_arquivo} (tipo: {tipo}) ==="
                bloco = f"{cabecalho}\n{texto_completo}"

                if total_chars + len(bloco) > LIMITE_CHARS:
                    # Inclui o que couber do documento ao invés de descartar
                    espaco = LIMITE_CHARS - total_chars
                    if espaco > 500:
                        partes_contexto.append(f"{cabecalho}\n{texto_completo[:espaco]}[...TRUNCADO]")
                        total_chars = LIMITE_CHARS
                    break

                partes_contexto.append(bloco)
                total_chars += len(bloco)

                # Captura o último aditamento completo
                if tipo == "registro_aditamento" or "aditamento" in (d.nome_arquivo or "").lower():
                    ultimo_aditamento = texto_completo[:5000]

            if not partes_contexto:
                raise Exception("sem_texto_extraido_nos_documentos")

            if docs_sem_texto:
                logger.warning(f"[REL-INICIAL] {len(docs_sem_texto)} doc(s) sem texto: {', '.join(docs_sem_texto)}")

            resumos_str = "\n\n---\n\n".join(partes_contexto)
            logger.info(
                f"[REL-INICIAL] Contexto: {total_chars:,} chars (~{total_chars//4:,} tokens) "
                f"de {len(todos_docs)} docs ({len(partes_contexto)} incluídos)"
            )

            # ── 3. Personagens já no banco ────────────────────────────────────
            pessoas_result = await db.execute(
                select(Pessoa).where(Pessoa.inquerito_id == inq_uuid)
            )
            pessoas = pessoas_result.scalars().all()
            personagens_raw = "\n".join(
                f"- {p.nome} (CPF: {p.cpf or 'não informado'}) — tipo atual: {p.tipo_pessoa or 'não classificado'}"
                for p in pessoas
            ) or "Nenhum personagem identificado ainda."

            # ── 4. Chamar LLM Premium ─────────────────────────────────────────
            prompt = PROMPT_RELATORIO_INICIAL.format(
                resumos_documentos=resumos_str,
                ultimo_aditamento=ultimo_aditamento or "Não disponível.",
                personagens_raw=personagens_raw,
            )

            llm = LLMService()
            result_llm = await asyncio.wait_for(
                llm.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    tier="premium",
                    temperature=0.1,
                    max_tokens=24000,  # 9 seções detalhadas — 16000 truncava na seção 6 em IPs complexos
                    agente="RelatorioInicial",
                ),
                timeout=540,  # 9 min — contexto grande pode levar >5 min no Gemini
            )
            relatorio_rascunho = result_llm["content"].strip()

            # ── 4b. Auditoria Anti-Alucinação (Agente Auditor) ───────────────
            relatorio_texto = relatorio_rascunho
            auditoria_log = ""
            try:
                prompt_auditoria = PROMPT_AUDITORIA_RELATORIO.format(
                    fontes_primarias=resumos_str[:300000],
                    relatorio_gerado=relatorio_rascunho,
                )
                result_auditoria = await asyncio.wait_for(
                    llm.chat_completion(
                        messages=[{"role": "user", "content": prompt_auditoria}],
                        tier="standard",
                        temperature=0.0,
                        max_tokens=24000,  # precisa reproduzir o relatório completo (9 seções)
                        agente="AuditorRelatorio",
                    ),
                    timeout=300,
                )
                relatorio_auditado = result_auditoria["content"].strip()

                # Validação: só usa o resultado da auditoria se parecer um relatório
                # estruturado real (com seções ## esperadas do relatório inicial).
                # Isso previne que o "raciocínio interno" do modelo contamine o doc.
                secoes_esperadas = ["## 1.", "## 4.", "## 7."]
                auditoria_valida = relatorio_auditado and all(
                    s in relatorio_auditado for s in secoes_esperadas
                )

                if auditoria_valida:
                    # Separar o bloco de auditoria do relatório corrigido
                    if "## AUDITORIA FACTUAL" in relatorio_auditado:
                        partes = relatorio_auditado.split("## AUDITORIA FACTUAL")
                        relatorio_texto = partes[0].rstrip("-").strip()
                        auditoria_log = partes[-1].strip()
                        logger.info(f"[REL-INICIAL] Auditoria factual:\n{auditoria_log}")
                    else:
                        relatorio_texto = relatorio_auditado
                        logger.info("[REL-INICIAL] Auditoria concluída — sem marcadores de problema")
                else:
                    # Auditoria retornou conteúdo inesperado — manter rascunho original
                    logger.warning(
                        f"[REL-INICIAL] Auditoria descartada (output inválido, {len(relatorio_auditado)} chars) "
                        f"— usando rascunho original"
                    )
            except Exception as e_audit:
                logger.warning(f"[REL-INICIAL] Auditoria anti-alucinação falhou (usando rascunho): {e_audit}")

            # ── 5. Atualizar placeholder com conteúdo real ───────────────────
            # Usa o placeholder criado em 1b para evitar criar um segundo registro
            placeholder.conteudo = relatorio_texto
            if hasattr(placeholder, "modelo_llm"):
                placeholder.modelo_llm = result_llm.get("model")
            if hasattr(placeholder, "tokens_prompt"):
                placeholder.tokens_prompt = result_llm.get("tokens_prompt")
            if hasattr(placeholder, "tokens_resposta"):
                placeholder.tokens_resposta = result_llm.get("tokens_resposta")
            if hasattr(placeholder, "custo_estimado"):
                placeholder.custo_estimado = result_llm.get("custo_estimado")
            doc_gerado = placeholder
            await db.flush()

            # ── 6. Extrair e atualizar qualificação dos personagens ───────────
            secoes = {int(m.group(1)): m.group(3).strip() for m in _RE_SECAO.finditer(relatorio_texto)}

            mapa_papel = {
                2: "suspeito_principal",
                3: "coautor",
                4: "vitima",
                5: "testemunha",
                # Seção 6 removida — o inquérito é impessoal; servidores não são objeto de análise
            }

            # Constrói dicionário nome_normalizado → novo_papel
            qualificacoes: dict[str, str] = {}
            for secao_num, papel in mapa_papel.items():
                texto_secao = secoes.get(secao_num, "")
                for nome in _extrair_personagens_da_secao(texto_secao):
                    qualificacoes[_normalizar_nome(nome)] = papel

            # Atualiza pessoas no banco
            for p in pessoas:
                nome_norm = _normalizar_nome(p.nome)
                novo_papel = qualificacoes.get(nome_norm)
                if novo_papel and novo_papel != p.tipo_pessoa:
                    p.tipo_pessoa = novo_papel
                    logger.info(f"[REL-INICIAL] {p.nome} → {novo_papel}")

            # ── 7. Atualizar descricao do inquérito com Seção 1 ──────────────
            fato_secao = secoes.get(1, "")
            if fato_secao and len(fato_secao) > 20:
                # Usa as primeiras 3 linhas da seção 1 como descrição
                linhas = [l.strip() for l in fato_secao.split("\n") if l.strip()]
                descricao_nova = " ".join(linhas[:3])[:500]
                if descricao_nova:
                    inq.descricao = descricao_nova

            await db.commit()
            logger.info(f"[REL-INICIAL] Relatório salvo — {len(qualificacoes)} personagens qualificados")

        await engine.dispose()

        # ── 8. Disparar síntese (usa relatório como contexto) ─────────────
        try:
            from app.workers.summary_task import generate_analise_task
            generate_analise_task.delay(inquerito_id)
            logger.info(f"[REL-INICIAL] Síntese agendada — inquerito={inquerito_id}")
        except Exception as e:
            logger.warning(f"[REL-INICIAL] Falha ao agendar síntese: {e}")

        return {"status": "concluido", "inquerito_id": inquerito_id}

    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_run())
        loop.close()
        logger.info(f"[REL-INICIAL] Concluído — {result}")
        return result
    except Exception as e:
        logger.error(f"[REL-INICIAL] Erro: {e}")
        # Remove placeholder "__PROCESSANDO__" para que a próxima tentativa possa rodar
        async def _limpar_placeholder():
            from app.models.documento_gerado import DocumentoGerado
            from sqlalchemy import delete as sa_delete
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
            engine2 = create_async_engine(async_url, connect_args=connect_args, poolclass=NullPool)
            AsyncSession2 = async_sessionmaker(engine2, class_=AsyncSession, expire_on_commit=False)
            async with AsyncSession2() as db2:
                await db2.execute(
                    sa_delete(DocumentoGerado).where(
                        DocumentoGerado.inquerito_id == uuid.UUID(inquerito_id),
                        DocumentoGerado.tipo == "relatorio_inicial",
                        DocumentoGerado.conteudo == "__PROCESSANDO__",
                    )
                )
                await db2.commit()
            await engine2.dispose()
        try:
            loop2 = asyncio.new_event_loop()
            loop2.run_until_complete(_limpar_placeholder())
            loop2.close()
            logger.info(f"[REL-INICIAL] Placeholder removido após erro — retry possível")
        except Exception as e2:
            logger.warning(f"[REL-INICIAL] Falha ao limpar placeholder: {e2}")
        raise self.retry(exc=e)
