# Escrivão AI — Contexto do Projeto para Claude / Antigravity

## O que é este projeto
Sistema de apoio à análise de inquéritos policiais com RAG + agentes LLM.
Backend FastAPI + Celery + Redis + Qdrant + PostgreSQL. Frontend Next.js no Vercel. Deploy na Railway.

---

## Ao iniciar uma sessão — leia primeiro
Verifique os arquivos abaixo antes de fazer qualquer sugestão:
- `Documentos/plano_migracao_gemini_full.md` — status das tarefas concluídas e pendentes
- `backend/app/core/prompts.py` — todos os system prompts (editá-los aqui, não inline)
- `backend/app/services/llm_service.py` — roteamento de tiers LLM

---

## Stack atual (atualizado 2026-04-12)
| Camada | Tecnologia |
|--------|-----------|
| Frontend | Next.js, Tailwind, @base-ui/react |
| Backend | FastAPI + SQLAlchemy async (PostgreSQL) |
| Workers | Celery + Redis |
| Vetores | Qdrant |
| Auth | Supabase (Google OAuth) |
| LLM Provider | **Google Gemini (100% — Groq removido)** |
| Embeddings | `text-embedding-004` (Google) |
| OSINT | direct.data (BigDataCorp) + Serper.dev (Google Search) |
| Deploy | Vercel (frontend) + Railway (backend + worker) |

---

## Pipeline Completo: Ingestão → Relatório Inicial

### Etapa 1 — Upload e ingestão (`ingest_document`)
1. Download do PDF do storage (Supabase)
2. Extração de texto nativo (pypdf) + OCR seletivo nas páginas sem texto
3. Chunking (600 words, overlap 100)
4. **Embeddings:** `text-embedding-004` → PostgreSQL + Qdrant
5. **Agente Classificador** (`tier=triagem` → `gemini-1.5-flash-8b`):
   - Classifica tipo de peça: `boletim_ocorrencia`, `laudo_pericial`, `quebra_sigilo`, etc.
6. **Agente NER** (`tier=extracao` → `gemini-1.5-flash-8b`):
   - Extrai pessoas, empresas, endereços, telefones, emails, cronologia
   - Upsert no banco (deduplicação por CPF > nome normalizado)
7. Dispara `generate_summaries_task` e `extrair_pecas_task`

### Etapa 2 — Resumos Hierárquicos (`generate_summaries_task`)
- **Agente Resumo Página** (`tier=resumo` → `gemini-1.5-flash-8b`): resumo de cada página
- **Agente Resumo Documento** (`tier=resumo`): consolida páginas → resumo por documento
- **Agente Resumo Volume** (`tier=resumo`): consolida documentos → resumo por volume

### Etapa 3 — Relatório Inicial (`gerar_relatorio_inicial_task`)
Disparado quando **todos** os documentos do inquérito estão com `status=concluido`.

- **Agente RelatorioInicial** (`tier=premium` → `gemini-1.5-pro`):
  - Contexto: até **400.000 chars** de resumos de TODOS os documentos do inquérito
  - max_tokens: 6.000 tokens de saída
  - Gera 8 seções estruturadas (fato, suspeitos, coautores, vítimas, testemunhas, servidores, timeline, lacunas)
- **Agente AuditorRelatorio** (`tier=standard` → `gemini-1.5-flash`):
  - Contexto: até 300.000 chars das fontes primárias
  - Verifica alucinações e adiciona marcadores `[⚠ NÃO CONFIRMADO]`
  - O resultado **só substitui** o rascunho se contiver seções `## 1.`, `## 4.`, `## 7.`
  - O bloco `## AUDITORIA FACTUAL` é removido do conteúdo salvo (vai apenas para o log)

### Etapa 4 — Síntese Investigativa (`generate_analise_task`)
Disparada automaticamente após o Relatório Inicial ser salvo.
- **Agente Síntese** (`tier=premium` → `gemini-1.5-pro`): 10 seções com Chain-of-Thought

---

## Mapa de Tiers LLM
| Tier | Modelo | Usado em |
|------|--------|----------|
| `triagem` | `gemini-1.5-flash-8b` | Classificação de tipo de peça |
| `extracao` | `gemini-1.5-flash-8b` | NER — pessoas/empresas/endereços |
| `resumo` | `gemini-1.5-flash-8b` | Resumos hierárquicos (página/doc/volume) |
| `economico` | `gemini-1.5-flash-8b` | Genérico barato |
| `auditoria` | `gemini-1.5-flash-8b` | Auditoria factual do Copiloto |
| `standard` | `gemini-1.5-flash` | Orquestrador, auditoria de relatório, extrato bancário |
| `premium` | `gemini-1.5-pro` | Copiloto RAG, fichas, cautelares, relatório inicial, síntese |

---

## Correções aplicadas em 2026-04-12

| Bug | Causa raiz | Correção |
|-----|-----------|---------|
| `NameError: Optional not defined` | Faltava `from typing import Optional` | Adicionado em `documento_gerado.py` |
| `TypeError: modelo_llm invalid keyword` | Colunas `modelo_llm`, `tokens_*`, `custo_estimado` não existiam na tabela | Adicionadas ao modelo + migração Alembic `e8bab0d91b2a` |
| Worker não subia no Railway | `DocumentoGerado` falhava no import | Resolvido pelo fix acima |
| Migração não rodava no worker | `start.sh` não chamava `alembic upgrade head` no modo `worker` | Corrigido no `start.sh` |
| Relatório corrompido com texto de auditoria | Auditor retornava raciocínio interno; código substituía sem validar | Agora valida se output contém seções antes de substituir |
| Relatório baseado em só 1 PDF | Contexto limitado a 12.000 chars truncava os demais docs | Expandido para 400.000 chars (relatório) e 300.000 chars (auditoria) |
| Endpoint `/documentos-gerados` retornava 404 | Alias não registrado na API | Adicionado alias em `documentos_gerados.py` |

---

## Prompt do Relatório Inicial — Diretriz Mestra (v2)
**Localização:** `backend/app/core/prompts.py` → `PROMPT_RELATORIO_INICIAL`

O prompt deve seguir o modelo de **Analista de Inteligência Criminal Multidomínio**:

**Passo 1:** Identificar tipo penal e Marco Zero (data/hora/local do fato principal).

**Passo 2:** Extrair entidades por categoria de prova:
- Provas testemunhais: oitivas, depoimentos, interrogatórios  `[NOME] | [STATUS] | [PONTO CHAVE]`
- Provas técnicas/periciais: laudos ICCE/IML, autos de apreensão, quebras de sigilo
- Provas digitais/telemáticas: terminais, IMEIs, IPs, contas bancárias

**Passo 3:** Estrutura obrigatória do relatório:
1. **OBJETO E TIPIFICAÇÃO** — Nº inquérito, artigo CP/CPP, resumo do fato
2. **ANÁLISE DE MATERIALIDADE** — O crime existiu? Listar documentos que provam a existência
3. **ANÁLISE DE AUTORIA E VÍNCULOS** — Vínculos diretos e indiretos; contradições entre oitivas
4. **CRONOLOGIA DOS FATOS** — Timeline desde preparação até última diligência
5. **CONCLUSÃO TÉCNICA E LACUNAS** — Força probatória atual + o que ainda falta provar

**Rastreabilidade:** Cada afirmação deve citar a fonte (`conforme fls. 45`, `Termo de Oitiva de [Nome]`).

**Volume de contexto necessário:** Para inquéritos complexos (10+ volumes, interceptações, quebras de sigilo), o Gemini 1.5 Pro precisa de 500k-700k tokens. O limite atual de 400k chars (~100k tokens) pode ser insuficiente para o IP 911-00209/2019. Considerar alimentar o relatório com `texto_extraido` direto dos documentos além dos resumos.

---

## Restrições críticas (não violar)
- **UI:** usa `@base-ui/react`, NÃO `@radix-ui`. Nunca importar ShadCN sem verificar existência.
- **Railway:** imports pesados (gRPC, Qdrant, torch) devem ser lazy dentro dos routers FastAPI.
- **Railway deploy:** NUNCA commitar durante ingestão ativa — rolling deploy mata tasks Celery em andamento.
- **Celery workers:** engines async precisam de `postgresql+asyncpg://` (não `postgresql://`).
- **Gemini SDK:** não usar `aio.models.embed_content` — tem bug 404. Usar `asyncio.to_thread` para embeddings.
- **Next.js:** pdfjs-dist só via `dynamic` import em `useEffect`.
- **Git:** sempre `git push` após `git commit`. Nunca deixar commits locais.
- **SERPER_API_KEY:** Railway não injeta esta variável — está hardcoded como default em `config.py`. Não remover.
- **LLM JSON output:** sempre usar `max_tokens` ≥ 2500 para JSON com múltiplos campos.
- **Alembic:** no Railway, usar `python -m alembic upgrade head` (não `alembic` direto).
- **`max_retries` nas tasks Celery:** `gerar_relatorio_inicial_task` tem `max_retries=2` — se esgotar antes do fix chegar, deve ser disparada novamente via frontend.

---

## Arquivos-chave
| Arquivo | Função |
|---------|--------|
| `backend/app/core/prompts.py` | Todos os prompts do sistema |
| `backend/app/services/llm_service.py` | Roteamento de tiers LLM |
| `backend/app/workers/ingestion.py` | Pipeline de ingestão |
| `backend/app/workers/relatorio_inicial_task.py` | Geração do Relatório Inicial |
| `backend/app/workers/summary_task.py` | Resumos hierárquicos + Síntese |
| `backend/app/models/documento_gerado.py` | Modelo DocumentoGerado (com metadados IA) |
| `backend/alembic/versions/e8bab0d91b2a_*.py` | Migração para colunas de metadados IA |
| `backend/start.sh` | Script de inicialização (roda alembic antes do worker) |
| `backend/app/api/documentos_gerados.py` | Endpoints `/docs-gerados` e `/documentos-gerados` (alias) |
| `backend/app/services/agente_ficha.py` | Fichas investigativas por pessoa/empresa |
| `backend/app/services/copiloto_service.py` | RAG conversacional (Copiloto) |
