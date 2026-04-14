# Escrivão AI — Contexto do Projeto para Claude / Antigravity

## O que é este projeto
Sistema de apoio à análise de inquéritos policiais com RAG + agentes LLM.
Backend FastAPI + Celery + Redis + Qdrant + PostgreSQL. Frontend Next.js no Vercel. Deploy na Railway.

---

## Ao iniciar uma sessão — leia primeiro
- `backend/app/core/prompts.py` — todos os system prompts (editá-los aqui, não inline)
- `backend/app/services/llm_service.py` — roteamento de tiers LLM
- Memória `project_sessao_13_04_2026.md` — **estado ao encerrar 13/04, pendências e próximas ações**

---

## Stack atual (atualizado 2026-04-13)
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
5. **Agente Classificador** (`tier=triagem` → `gemini-1.5-flash-8b`): classifica tipo de peça
6. **Agente NER** (`tier=extracao` → `gemini-1.5-flash-8b`): extrai pessoas, empresas, cronologia
7. Dispara `generate_summaries_task` e `extrair_pecas_task`

### Etapa 2 — Resumos Hierárquicos (`generate_summaries_task`)
- Página → Documento → Volume (`tier=resumo` → `gemini-1.5-flash-8b`)

### Etapa 3 — Relatório Inicial (`gerar_relatorio_inicial_task`)
Disparado quando **todos** os documentos do inquérito estão com `status=concluido`.

- **Agente RelatorioInicial** (`tier=premium` → `gemini-1.5-pro`):
  - Contexto: até **2.800.000 chars** (~700k tokens) de `texto_extraido` direto, ordenados por prioridade pericial
  - max_tokens: 8.000 | temperature: 0.1
  - Gera **9 seções** com metodologia 5W criminal (v3)
  - **Seção 1 preenche `Inquerito.descricao`** — único lugar onde o campo "Fato" é preenchido
- **Agente AuditorRelatorio** (`tier=standard` → `gemini-1.5-flash`):
  - Verifica alucinações; substitui rascunho só se output contém `## 1.`, `## 4.`, `## 7.`

### Etapa 4 — Síntese Investigativa (`generate_analise_task`)
Disparada automaticamente após Relatório Inicial salvo.
- **Agente Síntese** (`tier=premium` → `gemini-1.5-pro`): 10 seções com Chain-of-Thought
- **ATENÇÃO:** se o Relatório Inicial for regenerado com `forcar=true`, a Síntese também deve ser regenerada via `POST /inqueritos/{id}/gerar-sintese` — ela não é atualizada automaticamente neste caso

---

## Mapa de Tiers LLM
| Tier | Modelo | Usado em |
|------|--------|----------|
| `triagem` | `gemini-1.5-flash-8b` | Classificação de tipo de peça |
| `extracao` | `gemini-1.5-flash-8b` | NER — pessoas/empresas/endereços |
| `resumo` | `gemini-1.5-flash-8b` | Resumos hierárquicos |
| `economico` | `gemini-1.5-flash-8b` | Genérico barato |
| `auditoria` | `gemini-1.5-flash-8b` | Auditoria factual do Copiloto |
| `standard` | `gemini-1.5-flash` | Orquestrador, auditoria de relatório |
| `premium` | `gemini-1.5-pro` | Copiloto RAG, fichas, cautelares, relatório inicial, síntese |

---

## Prompt do Relatório Inicial — v3 (atual)
**Localização:** `backend/app/core/prompts.py` → `PROMPT_RELATORIO_INICIAL` (linha ~844)

Role: **Analista de Inteligência Criminal Multidomínio**.

### Metodologia 5W
| W | Pergunta | Função |
|---|---------|--------|
| O QUÊ | Qual o crime? | Tipificação jurídica + concurso + qualificadoras |
| QUANDO | Marco Zero ★ | Nexo temporal, álibi, prescrição |
| ONDE | Local do crime | Competência territorial + contexto pericial |
| QUEM | Autores / vítimas / testemunhas | Derivado das PROVAS, não da lista de envolvidos |
| POR QUÊ | Motivação / dolo | Agrava pena, orienta tipificação |

**Ordem analítica:** Materialidade → Autoria → Cronologia → Conclusão.

### 9 Seções
| Seção | Título | Auto-parse |
|-------|--------|-----------|
| ## 1. | OBJETO E TIPIFICAÇÃO | preenche `Inquerito.descricao` |
| ## 2. | SUSPEITOS PRINCIPAIS | `mapa_papel[2] = suspeito_principal` |
| ## 3. | COAUTORES / PARTÍCIPES | `mapa_papel[3] = coautor` |
| ## 4. | VÍTIMAS | `mapa_papel[4] = vitima` |
| ## 5. | TESTEMUNHAS RELEVANTES | `mapa_papel[5] = testemunha` |
| ## 6. | ANÁLISE DE MATERIALIDADE | — |
| ## 7. | ANÁLISE DE AUTORIA E VÍNCULOS | — |
| ## 8. | CRONOLOGIA DOS FATOS | — |
| ## 9. | CONCLUSÃO TÉCNICA E LACUNAS | — |

**Seção Servidores: REMOVIDA** — inquérito é impessoal, servidores não são objeto de análise.

### Arquitetura de contexto
- Fonte: `texto_extraido` direto. Fallback ao resumo só se `len < 200 chars`
- Limite: `LIMITE_CHARS = 2_800_000`
- Prioridade: `quebra_sigilo/extrato(0)` → `laudo/interrogatorio(1)` → `depoimento/declaracao(2)` → `relatorio/informacao/aditamento(3)` → `bo/auto(4)` → `oficio(5)`

---

## Copiloto — Arquitetura de contexto (atualizado 2026-04-13)

O Copiloto monta seu contexto na seguinte ordem:

1. **DocumentoGerado** (relatorio_inicial completo; outros truncados em 3000 chars)
   - `TIPOS_COMPLETOS = {"relatorio_inicial", "relatorio_complementar"}` — sem truncar
   - `sintese_investigativa` **NÃO está em TIPOS_COMPLETOS** — pode estar obsoleta
2. **Índice de peças dos autos** (`tipo_peca + nome_arquivo` de todos os Documentos indexados)
3. **Resumo executivo do caso** (`SummaryService.obter_resumo_caso`)
4. **Índice de pessoas e empresas** (com `tipo_pessoa`)
5. **Contatos e cronologia**
6. **Chunks RAG** (Qdrant + busca híbrida texto)

**Comportamento esperado:**
- Referências processuais do usuário ("foi relatado", "MP pediu X") → trata como verdade e busca corroboração nos autos
- Pedido de documento formal → gera completo com conteúdo real (não síntese de 5 linhas)
- `max_tokens = 4000`

**NÃO auto-salva respostas** — o usuário salva explicitamente pelo botão "Salvar" no canvas.

---

## Correções aplicadas em 2026-04-13

| Bug | Causa raiz | Correção |
|-----|-----------|---------|
| Copiloto retornava síntese genérica "Não especificados" | `sintese_investigativa` antiga (contexto pré-v3) injetada completa; LLM a reproduzia | Removida de TIPOS_COMPLETOS; `relatorio_inicial` injetado completo |
| Copiloto auto-salvava documentos ruins silenciosamente | `CopilotoDrawer.tsx` chamava `createDocGerado` em background quando `pediriaDocumento()` era verdadeiro | Auto-save removido — só salva via clique explícito |
| Campo "Fato" preenchido com descrição NER precoce | `orchestrator.py` setava `descricao=fato_resumo` na criação do inquérito | `descricao=""` na criação; preenchido somente pela Seção 1 do Relatório Inicial |

---

## Pendências abertas

1. **Síntese do IP 911-00209/2019** — regenerar após limpeza das sínteses ruins:
   ```
   POST /inqueritos/c38991d7-e669-435e-b54e-64df6ed6c429/gerar-sintese
   ```

2. **Lote de relatórios iniciais** nos demais inquéritos:
   ```
   POST /ingestao/admin/gerar-relatorio-inicial-lote?forcar=false
   ```

3. **Alembic migration `j0k1l2m3n4o5`** no Railway — remap tipos de peças:
   `laudo → laudo_pericial` | `oficio → oficio_expedido` | `termo_oitiva → termo_depoimento`

4. **OSINT Web (Serper.dev)** — plano completo em `reflective-meandering-sky.md`:
   - `serper_service.py`, endpoint `/agentes/osint/web/`, `OsintWebPanel` — NÃO criados
   - `SERPER_API_KEY` já está no `.env.local` e hardcoded em `config.py`

---

## Restrições críticas (não violar)
- **UI:** usa `@base-ui/react`, NÃO `@radix-ui`. Nunca importar ShadCN sem verificar existência.
- **Railway:** imports pesados (gRPC, Qdrant, torch) devem ser lazy dentro dos routers FastAPI.
- **Railway deploy:** NUNCA commitar durante ingestão ativa — rolling deploy mata tasks Celery.
- **Celery workers:** engines async precisam de `postgresql+asyncpg://` (não `postgresql://`).
- **Gemini SDK:** não usar `aio.models.embed_content` — tem bug 404. Usar `asyncio.to_thread` para embeddings.
- **Next.js:** pdfjs-dist só via `dynamic` import em `useEffect`.
- **Git:** sempre `git push` após `git commit`. Nunca deixar commits locais.
- **SERPER_API_KEY:** hardcoded como default em `config.py` — não remover.
- **LLM JSON output:** sempre `max_tokens` ≥ 2500 para JSON com múltiplos campos.
- **Alembic:** no Railway, usar `python -m alembic upgrade head` (não `alembic` direto).
- **Inquérito é impessoal:** servidores policiais não são objeto de análise — nunca incluir como suspeitos ou alvos OSINT.
- **Campo "Fato":** preenchido SOMENTE pela Seção 1 do Relatório Inicial. Não setar em outros lugares.
- **Síntese Investigativa:** derivada do Relatório Inicial — fica obsoleta se o relatório for regenerado. Sempre regenerar a síntese depois de `forcar=true` no relatório.

---

## Arquivos-chave
| Arquivo | Função |
|---------|--------|
| `backend/app/core/prompts.py` | Todos os prompts do sistema |
| `backend/app/services/llm_service.py` | Roteamento de tiers LLM |
| `backend/app/services/copiloto_service.py` | RAG conversacional — contexto, injeção de docs, tool calling |
| `backend/app/workers/ingestion.py` | Pipeline de ingestão |
| `backend/app/workers/relatorio_inicial_task.py` | Geração do Relatório Inicial (contexto 2.8M chars) |
| `backend/app/workers/summary_task.py` | Resumos hierárquicos + Síntese |
| `backend/app/workers/orchestrator.py` | Criação automática de inquérito na ingestão |
| `backend/app/models/documento_gerado.py` | Modelo DocumentoGerado |
| `backend/app/api/documentos_gerados.py` | Endpoints `/docs-gerados` e `/documentos-gerados` |
| `backend/app/api/inqueritos.py` | Endpoints `gerar-relatorio-inicial`, `gerar-sintese` |
| `backend/app/services/agente_ficha.py` | Fichas investigativas por pessoa/empresa |
| `src/components/CopilotoDrawer.tsx` | Frontend do Copiloto — canvas, save explícito |
