# Escrivão AI — Contexto do Projeto para Claude / Antigravity

## O que é este projeto
Sistema de apoio à análise de inquéritos policiais com RAG + agentes LLM.
Backend FastAPI + Celery + Redis + Qdrant + PostgreSQL. Frontend Next.js no Vercel. Deploy na Railway.

---

## Ao iniciar uma sessão — leia primeiro
- `backend/app/core/prompts.py` — todos os system prompts (editá-los aqui, não inline)
- `backend/app/services/llm_service.py` — roteamento de tiers LLM
- Memória `project_sessao_18_04_2026_v2.md` — **estado ao encerrar sessão de 18/04 v2, pendências e próximas ações**

---

## Stack atual (atualizado 2026-04-14)
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

## Pipeline Completo: Ingestão → Relatório Inicial → Complementar

### Etapa 1 — Upload e ingestão (`ingest_document`)
1. Download do PDF do storage (Supabase)
2. Extração de texto nativo (pypdf) + OCR seletivo nas páginas sem texto
3. Chunking (600 words, overlap 100)
4. **Embeddings:** `text-embedding-004` → PostgreSQL + Qdrant
5. **Agente Classificador** (`tier=triagem` → `gemini-2.5-flash-lite`): classifica tipo de peça
6. **Agente NER** (`tier=extracao` → `gemini-2.5-flash-lite`): extrai pessoas, empresas, cronologia
7. Dispara `generate_summaries_task` e `extrair_pecas_task`

### Etapa 2 — Resumos Hierárquicos (`generate_summaries_task`)
- Página → Documento → Volume (`tier=resumo` → `gemini-2.5-flash-lite`)

### Etapa 3 — Relatório Inicial (`gerar_relatorio_inicial_task`)
Disparado quando **todos** os documentos do inquérito estão com `status=concluido`.

- **Agente RelatorioInicial** (`tier=premium` → `gemini-2.5-flash`):
  - Contexto: até **2.800.000 chars** (~700k tokens) de `texto_extraido` direto, ordenados por prioridade pericial
  - max_tokens: 65.536 | temperature: 0.1
  - PASSO 0: identifica fase processual (Instauração / Instrução / Indiciamento / Relatamento)
  - Gera **9 seções** com metodologia 5W criminal (v3)
  - **Seção 1 preenche `Inquerito.descricao`** — único lugar onde o campo "Fato" é preenchido
- **Agente AuditorRelatorio** (`tier=standard` → `gemini-2.5-flash`):
  - Verifica alucinações; substitui rascunho só se output contém `## 1.`, `## 4.`, `## 7.`

### Etapa 4 — Síntese Investigativa (`generate_analise_task`)
Disparada automaticamente após Relatório Inicial salvo.
- **Agente Síntese** (`tier=premium` → `gemini-2.5-flash`): 10 seções com Chain-of-Thought
- **ATENÇÃO:** se o Relatório Inicial for regenerado com `forcar=true`, a Síntese também deve ser regenerada via `POST /inqueritos/{id}/gerar-sintese` — ela não é atualizada automaticamente neste caso

### Etapa 5 — Relatório Complementar (`gerar_relatorio_complementar_task`) [NOVO]
Disparado manualmente quando o MP devolveu o inquérito para diligências complementares.

- **Contexto processual:** Fase 4 (Relatório Final) → Fase 5 (MP devolveu com Cota Ministerial) → Fase 2 (nova instrução) → agora: Relatório Complementar
- **Agente RelatorioComplementar** (`tier=premium` → `gemini-2.5-flash`):
  - Carrega `relatorio_inicial` DocumentoGerado como base (até 60.000 chars)
  - Carrega todos os docs indexados — prioriza `oficio_recebido` (Cota Ministerial do MP)
  - Gera **5 seções:** Referência e Objeto | Diligências Realizadas | Resultado | Individualização de Conduta | Conclusão
  - max_tokens: 65.536 | temperature: 0.1
- **Agente AuditorComplementar** (`tier=standard`): auditoria anti-alucinação
- Salva como `DocumentoGerado(tipo="relatorio_complementar")`
- Endpoint: `POST /inqueritos/{id}/gerar-relatorio-complementar?forcar=false`
- Botão na UI: "Gerar Rel. Complementar" (cor sky-400) na aba Workspace

---

## Fases Processuais do IP — referência para os prompts

| Fase | Nome | Documentos típicos | tipo_peca |
|------|---------|--------------------|-----------|
| 1 | Instauração | Portaria, APF, Auto de Apreensão inicial | `bo`, `auto_apreensao` |
| 2 | Instrução | Oitivas, laudos, quebras de sigilo, apreensões | `termo_depoimento`, `laudo_pericial`, `quebra_sigilo` |
| 3 | Indiciamento | Despacho de Indiciamento | `relatorio_policial` (parcial) |
| 4 | Relatamento | Relatório Final (último ato do Delegado antes do MP) | `relatorio_policial` |
| 5 | Fase Externa | Cota MP (denúncia / devolução / arquivamento) | `oficio_recebido` |

**Quando o IP retorna do MP (Fase 5 → 2):** existe uma Cota Ministerial (`oficio_recebido`) com a solicitação. O Relatório Complementar responde a essa cota.

---

## Mapa de Tiers LLM
| Tier | Modelo | Usado em |
|------|--------|----------|
| `triagem` | `gemini-2.5-flash-lite` | Classificação de tipo de peça |
| `extracao` | `gemini-2.5-flash-lite` | NER — pessoas/empresas/endereços |
| `resumo` | `gemini-2.5-flash-lite` | Resumos hierárquicos |
| `economico` | `gemini-2.5-flash-lite` | Genérico barato |
| `auditoria` | `gemini-2.5-flash-lite` | Auditoria factual do Copiloto |
| `standard` | `gemini-2.5-flash` | Orquestrador, auditoria de relatório/complementar |
| `premium` | `gemini-2.5-flash` | Copiloto RAG, fichas, cautelares, relatório inicial, síntese, complementar |

---

## Prompt do Relatório Inicial — v3 (atual)
**Localização:** `backend/app/core/prompts.py` → `PROMPT_RELATORIO_INICIAL` (linha ~870)

Role: **Analista de Inteligência Criminal Multidomínio**.

### Passo 0 — Identificação de fase (NOVO)
Antes de escrever qualquer seção, o agente identifica:
- Como o IP foi instaurado (Portaria / APF / VPI)
- Fase atual (instrução / com indiciados / relatado / retornou do MP)
- Tipo e complexidade do crime
- Provas já existentes (diretas, indiretas, técnicas)

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

## Copiloto — Arquitetura de contexto (atualizado 2026-04-15)

O Copiloto monta seu contexto na seguinte ordem:

1. **DocumentoGerado** (relatorio_inicial completo; outros truncados em 3000 chars)
   - `TIPOS_COMPLETOS = {"relatorio_inicial", "relatorio_complementar"}` — sem truncar
   - `sintese_investigativa` **NÃO está em TIPOS_COMPLETOS** — pode estar obsoleta
2. **Índice de peças dos autos** (`tipo_peca + nome_arquivo` de todos os Documentos indexados)
3. **Resumo executivo do caso** (`SummaryService.obter_resumo_caso`)
4. **Índice de pessoas e empresas** (com `tipo_pessoa`)
5. **Contatos e cronologia**
6. **Chunks RAG** (Qdrant + busca híbrida texto)

**Filosofia (atualizado 15/04 — commit `14cf015`):**
O Copiloto conversa naturalmente, sem diretrizes rígidas numeradas. Raciocina em voz alta, faz perguntas quando necessário, age quando pedido. Fluxo ideal:
`Comissário pergunta → Copiloto analisa e responde → refinam juntos → Copiloto gera documento inline → Comissário clica "Salvar"`

**Capacidade "pauta investigativa":** quando o Comissário pergunta "o que está para fazer?", o Copiloto analisa os autos e retorna: itens da Cota MP não cumpridos, investigados sem oitiva, laudos sem resposta, lacunas de prova.

**Ferramenta `<RELATORIO_COMPLEMENTAR_CALL>`:** SOMENTE quando Comissário diz "salva no sistema" / "usa a ferramenta dedicada". Pedidos conversacionais ("consolide", "redija", "elabore") → gera INLINE na conversa, não dispara a ferramenta. Quando disparada: `copiloto_service.py` chama `gerar_relatorio_complementar_task.delay()`.

**NÃO auto-salva respostas** — o usuário salva explicitamente pelo botão "Salvar" no canvas.

**ATENÇÃO — `{}` no prompt:** qualquer literal `{}` em `SYSTEM_PROMPT_COPILOTO` deve ser `{{}}` — o serviço faz `.format(**kwargs)` e quebra com placeholders posicionais vazios.

- `max_tokens = 65536`

---

## Correções aplicadas em 2026-04-13/14

| Bug | Causa raiz | Correção |
|-----|-----------|---------|
| Copiloto retornava síntese genérica "Não especificados" | `sintese_investigativa` antiga injetada completa; LLM a reproduzia | Removida de TIPOS_COMPLETOS; `relatorio_inicial` injetado completo |
| Copiloto auto-salvava documentos ruins silenciosamente | `CopilotoDrawer.tsx` chamava `createDocGerado` em background | Auto-save removido — só salva via clique explícito |
| Campo "Fato" preenchido com descrição NER precoce | `orchestrator.py` setava `descricao=fato_resumo` na criação | `descricao=""` na criação; preenchido somente pela Seção 1 do Relatório Inicial |
| Copiloto "⚠️ LLM indisponível" — 403/404 Gemini | Chave nova AI Studio → família 2.0 bloqueada; billing atrasado | Pagar fatura + migrar para `gemini-2.5-flash` / `gemini-2.5-flash-lite` (14/04) |
| `Documento.num_paginas` AttributeError no Copiloto | Campo se chama `total_paginas` no modelo | Corrigido em `copiloto_service.py` (commit `87cb2a6`) |
| Copiloto rígido — gerava relatório sem conversar | `SYSTEM_PROMPT` com 6 diretrizes obrigatórias engessava o LLM | Reescrito como conversa natural (15/04, commit `bdb8389`) |
| `<RELATORIO_COMPLEMENTAR_CALL>` disparava cedo demais | Trigger em "consolide" além de pedidos explícitos | Restringido: só "salva no sistema" / "usa a ferramenta" (commit `14cf015`) |
| Rel. Complementar não localizava Cota Ministerial | Cota perdida no blob; sem Passo 0 de parsing | Cota isolada como campo dedicado + Passo 0 obrigatório (commit `bdb8389`) |

---

## Pendências abertas

1. **Síntese do IP 911-00009-2020** — ✅ CONCLUÍDO (19/04)

2. **Síntese do IP 911-00209/2019** — regenerar:
   ```
   POST /inqueritos/c38991d7-e669-435e-b54e-64df6ed6c429/gerar-sintese
   ```

3. **Lote de relatórios iniciais** nos demais inquéritos:
   ```
   POST /ingestao/admin/gerar-relatorio-inicial-lote?forcar=false
   ```

4. **Alembic migration `j0k1l2m3n4o5`** no Railway — remap tipos de peças:
   `laudo → laudo_pericial` | `oficio → oficio_expedido` | `termo_oitiva → termo_depoimento`

5. **CGU_API_TOKEN** — configurar no Railway para OSINT gratuito (sanções CEIS)

6. **`intimacao_extractor.py`** — ✅ já usa `settings.LLM_STANDARD_MODEL` (verificado 19/04)

7. **Testar Telegram investigativo** — ✅ fix total_documentos real aplicado em 19/04 (commit `1e3ae8f`); busca de apelidos/alcunhas em Chunks adicionada (`3775457`)

8. **OSINT Web (Serper.dev)** — ✅ IMPLEMENTADO: `serper_service.py`, `gerar_osint_web_pessoa`, endpoint `/agentes/osint/web/`, `OsintWebPanel` no `PainelInvestigacao.tsx`

9. **Edição de documentos gerados pela IA** — ✅ IMPLEMENTADO (sessão 16/04): botão ✏️ abre modal de edição (título + conteúdo) → `PUT /docs-gerados/{id}`

10. **Exportação PDF de docs gerados** — ✅ IMPLEMENTADO (sessão 16/04): botão 📄 exporta como HTML + `window.print()`

11. **OSINT Gratuito (BrasilAPI + CGU)** — ✅ IMPLEMENTADO (sessão 16/04 v2): `osint_gratuito_service.py`, endpoint `/agentes/osint/gratuito/`, `OsintGratuitoPanel` — roda ANTES do direct.data

12. **Agente Sherlock** — ✅ IMPLEMENTADO + corrigido (`estado_atual`, commit `4f12f74`): `sherlock_service.py`, `PROMPT_SHERLOCK` (5 camadas), endpoint `POST /agentes/sherlock/{inq_id}`, painel no Workspace

13. **OneDrive Picker** — ✅ IMPLEMENTADO (sessão 16/04 v3): `OneDrivePicker.tsx` + `/auth/onedrive`, PKCE flow, botão na ingestão e no workspace. Azure App: client `5434c90f`, tenant `a960e527`, redirect `https://escriv-o.vercel.app/auth/onedrive`

14. **Copiar texto limpo** — ✅ IMPLEMENTADO: botão `Copy` nos docs gerados, strip completo de markdown para colar no sistema da PC

15. **Harness (Celery + LLM)** — ✅ IMPLEMENTADO (sessão 18/04): task_failure Telegram alerts, telemetria `tempo_ms`/`status` em `consumo_api`, migration `o5p6q7r8s9t0`

16. **Indicador visual docs em geração** — ✅ IMPLEMENTADO (sessão 18/04 v2): borda âmbar + spinner quando `em_processamento=true`; borda verde quando pronto; auto-poll 8s

17. **Telegram investigativo** — ✅ IMPLEMENTADO (sessão 18/04): `_resposta_investigativa()` via CopilotoService; fix HTML parse failure; fix gemini-flash-latest

18. **Railway billing GraphQL** — queries atualizadas para Team (`me.teams.edges...`) e Hobby (`me.subscription...`) — aguarda validação em produção

19. **Voz no Copiloto web** — ✅ IMPLEMENTADO (sessão 19/04): mic → MediaRecorder → TTS Gemini voz Charon; `handleSendRef` evita stale closure; `onstop` antes de `stop()`

20. **Vision + intimações** — ✅ IMPLEMENTADO (sessão 19/04): `POST /agent/analisar-documento` (Gemini Vision) detecta mandados → `<CRIAR_INTIMACAO>` → `POST /intimacoes/manual`

21. **BUSCA_GLOBAL_CALL** — ✅ IMPLEMENTADO (sessão 19/04): ferramenta nativa #5 no Copiloto; `_buscar_global()` em `copiloto_service.py`; `processar_mensagem_global()` sem inquerito; Telegram: `buscar_pessoa_sistema` estendida com Chunks

---

## Restrições críticas (não violar)
- **Gemini 2.0 bloqueado:** `gemini-2.0-flash*` e `gemini-2.0-flash-lite*` (com ou sem `-001`) retornam 404 para a chave ativa. Usar sempre família **2.5** (`gemini-2.5-flash`, `gemini-2.5-flash-lite`). `gemini-2.5-pro` disponível mas 503 frequente — reservado para uso futuro.
- **UI:** usa `@base-ui/react`, NÃO `@radix-ui`. Nunca importar ShadCN sem verificar existência.
- **Railway:** imports pesados (gRPC, Qdrant, torch) devem ser lazy dentro dos routers FastAPI.
- **Railway deploy:** NUNCA commitar durante ingestão ativa — rolling deploy mata tasks Celery.
- **Celery workers:** engines async precisam de `postgresql+asyncpg://` (não `postgresql://`).
- **Gemini SDK:** não usar `aio.models.embed_content` — tem bug 404. Usar `asyncio.to_thread` para embeddings.
- **Next.js:** pdfjs-dist só via `dynamic` import em `useEffect`.
- **Git:** sempre `git push` após `git commit`. Nunca deixar commits locais.
- **SERPER_API_KEY:** hardcoded como default em `config.py` — não remover.
- **LLM JSON output:** sempre `max_tokens` ≥ 2500 para JSON com múltiplos campos.
- **LLM geradores de documentos:** sempre `max_tokens=65536` (teto do Flash) — sem limite artificial menor. O modelo para sozinho quando termina. Limites baixos apenas para chamadas estruturais curtas (JSON, timestamps, classificações).
- **Alembic:** no Railway, usar `python -m alembic upgrade head` (não `alembic` direto).
- **Inquérito é impessoal:** servidores policiais não são objeto de análise — nunca incluir como suspeitos ou alvos OSINT.
- **Campo "Fato":** preenchido SOMENTE pela Seção 1 do Relatório Inicial. Não setar em outros lugares.
- **Síntese Investigativa:** derivada do Relatório Inicial — fica obsoleta se o relatório for regenerado. Sempre regenerar a síntese depois de `forcar=true` no relatório.
- **Relatório Complementar:** só faz sentido quando o MP devolveu o IP (Cota Ministerial presente nos autos). Não confundir com Relatório Final.
- **DocGeradoListItem:** o endpoint de lista `GET /docs-gerados` NUNCA retorna `conteudo`. Estado de processamento é exposto via `em_processamento: bool` calculado no backend (`conteudo == "__PROCESSANDO__"`). Nunca checar `doc.conteudo` no frontend para detectar estado — usar `doc.em_processamento`.
- **Telegram send_message:** re-envia como texto plano se HTML parse falhar (400 "can't parse entities"). Respostas do LLM podem conter `<>` não escapados que quebram o parse_mode=HTML.
- **gemini-flash-latest bloqueado:** alias para gemini-1.5-flash, bloqueado para a chave atual. `intimacao_extractor.py` ainda usa este alias — pendente de correção.

---

## Arquivos-chave
| Arquivo | Função |
|---------|--------|
| `backend/app/core/prompts.py` | Todos os prompts do sistema |
| `backend/app/services/llm_service.py` | Roteamento de tiers LLM |
| `backend/app/services/copiloto_service.py` | RAG conversacional — contexto, injeção de docs, tool calling |
| `backend/app/workers/ingestion.py` | Pipeline de ingestão |
| `backend/app/workers/relatorio_inicial_task.py` | Geração do Relatório Inicial (contexto 2.8M chars) |
| `backend/app/workers/relatorio_complementar_task.py` | Geração do Relatório Complementar (fase MP→delegacia) |
| `backend/app/workers/summary_task.py` | Resumos hierárquicos + Síntese |
| `backend/app/workers/orchestrator.py` | Criação automática de inquérito na ingestão |
| `backend/app/models/documento_gerado.py` | Modelo DocumentoGerado |
| `backend/app/api/documentos_gerados.py` | Endpoints `/docs-gerados` e `/documentos-gerados` |
| `backend/app/api/inqueritos.py` | Endpoints `gerar-relatorio-inicial`, `gerar-sintese`, `gerar-relatorio-complementar` |
| `backend/app/services/agente_ficha.py` | Fichas investigativas por pessoa/empresa + OSINT web + OSINT gratuito |
| `backend/app/services/sherlock_service.py` | Agente Sherlock — análise estratégica em 5 camadas (cache 6h) |
| `backend/app/services/serper_service.py` | Wrapper Serper.dev — dorks paralelos (OSINT web) |
| `backend/app/services/osint_gratuito_service.py` | BrasilAPI CNPJ + CGU CEIS — OSINT gratuito |
| `src/components/CopilotoDrawer.tsx` | Frontend do Copiloto — canvas, save explícito |
| `src/app/inqueritos/[id]/page.tsx` | Workspace: Sherlock, Rel. Inicial, Rel. Complementar, editor docs, PDF |
