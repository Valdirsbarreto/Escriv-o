# Escrivão AI — Arquitetura de Agentes, Tarefas e LLMs

> Atualizado em: 2026-04-08

---

## 1. Tiers LLM

| Tier | Provedor | Modelo | Custo | Uso |
|------|----------|--------|-------|-----|
| **Resumo / Auditoria** | Groq | `llama-3.3-70b-versatile` | **Gratuito** | Análise preliminar automática OSINT, auditoria factual |
| **Econômico** | OpenAI | `gpt-4.1-nano` | Mínimo | Classificação de peças, resumos hierárquicos |
| **Standard** | Google | `gemini-1.5-flash` | Médio | NER, extrato bancário, copiloto RAG, análise OSINT aprimorada |
| **Premium** | Google | `gemini-1.5-pro` | Alto | Fichas completas com dados externos, cautelares, síntese investigativa |
| **Vision** | Google | `gemini-flash-latest` | Variável | OCR de intimações, processamento de imagens |
| **Embedding** | Google | `text-embedding-004` | Baixo | Vetores 768-dim para RAG |

---

## 2. Fluxo Principal — Upload de Documento até Investigação

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  AGENTE POLICIAL FAZ UPLOAD                                                        │
│  POST /ingestao/iniciar  (PDF, PNG, JPG, TIFF)                              │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  StorageService          │
                    │  Upload para S3/MinIO    │
                    └────────────┬────────────┘
                                 │ dispara
         ┌───────────────────────▼──────────────────────────┐
         │  [CELERY] orchestrate_new_inquerito               │
         │  LLM: PREMIUM (gemini-2.0-flash)                 │
         │  Prompt: SYSTEM_PROMPT_ORQUESTRADOR              │
         │                                                   │
         │  • Extrai número IP, ano, delegacia              │
         │  • Cria ou vincula registro Inquerito no banco    │
         │  • Extrai personagens iniciais                   │
         └────────────────────┬─────────────────────────────┘
                              │ dispara
         ┌────────────────────▼─────────────────────────────┐
         │  [CELERY] ingestion.*  (pipeline de ingestão)    │
         │                                                   │
         │  ① PDFExtractorService — extrai texto do PDF     │
         │     fallback: pytesseract OCR                    │
         │                                                   │
         │  ② ExtractorService.classificar_documento()      │
         │     LLM: ECONÔMICO (gpt-4.1-nano)               │
         │     → tipo_peca: boletim_ocorrencia, portaria,  │
         │       relatorio, extrato_bancario, etc.          │
         │                                                   │
         │  ③ ExtractorService.extrair_entidades()          │
         │     LLM: STANDARD (gemini-2.0-flash, json_mode) │
         │     → pessoas[], empresas[], enderecos[]         │
         │     → upsert no banco (deduplicação por CPF)    │
         │                                                   │
         │  ④ EmbeddingService.generate_batch()            │
         │     Modelo: text-embedding-004 (768-dim)         │
         │     → chunks vetorizados enviados ao Qdrant      │
         └────────────────────┬─────────────────────────────┘
                              │ ao concluir
         ┌────────────────────▼─────────────────────────────┐
         │  [CELERY] generate_summaries_task                │
         │  LLM: ECONÔMICO em todos os níveis              │
         │                                                   │
         │  Nível 1 — PROMPT_RESUMO_PAGINA   (por página)  │
         │  Nível 2 — PROMPT_RESUMO_DOCUMENTO (por doc)    │
         │  Nível 3 — PROMPT_RESUMO_VOLUME   (por volume)  │
         │  Nível 4 — PROMPT_RESUMO_CASO     (caso total)  │
         │                                                   │
         │  → Resultados cacheados em ResumoCache           │
         └──────────────────────────────────────────────────┘
                              │
                   Status: triagem → investigação
```

---

## 3. Agentes Especializados (chamados via HTTP)

### 3.1 Copiloto Investigativo (RAG)

```
POST /copiloto/mensagens
        │
        ▼
┌───────────────────────────────────────────────────────┐
│  CopilotoService.processar_mensagem()                │
│                                                       │
│  ① EmbeddingService — vetoriza a pergunta            │
│     Modelo: text-embedding-004                       │
│                                                       │
│  ② QdrantService — busca os top-8 chunks similares  │
│     Collection: escrivao_chunks                      │
│                                                       │
│  ③ Monta contexto com citações (TEMPLATE_RAG)        │
│                                                       │
│  ④ LLM PREMIUM — gera resposta fundamentada         │
│     Prompt: SYSTEM_PROMPT_COPILOTO                  │
│     → Resposta com [Doc: nome, p. X]                │
│                                                       │
│  ⑤ [Opcional] LLM PREMIUM — auditoria factual       │
│     Prompt: SYSTEM_PROMPT_AUDITORIA_FACTUAL         │
│     → Verifica se resposta tem suporte nos docs     │
└───────────────────────────────────────────────────────┘
```

---

### 3.2 Agente Ficha / OSINT Investigativo

**Fluxo de 3 camadas para personagem:**

```
Ao expandir card na aba "Investigação OSINT"
        │
        ▼ (automático, gratuito)
┌───────────────────────────────────────────────────────┐
│  AgenteFicha.gerar_analise_preliminar_pessoa()       │
│  LLM: RESUMO (Groq llama-3.3-70b — gratuito)        │
│  Prompt: PROMPT_ANALISE_PRELIMINAR                  │
│  Cache: 24h em ResultadoAgente                      │
│                                                       │
│  Apenas dados internos dos autos:                   │
│  → resumo, nivel_risco, fatos_conhecidos,           │
│     pontos_de_atencao, lacunas                      │
│  (lacunas justificam quais APIs pagas usar)         │
└───────────────────────────────────────────────────────┘
        │
        ▼ (por demanda — botão "Aprimorar")
┌───────────────────────────────────────────────────────┐
│  AgenteFicha.gerar_analise_preliminar_pessoa(        │
│      aprimorar=True)                                │
│  LLM: STANDARD (Gemini Flash)                       │
│  Mesmo prompt, melhor raciocínio                    │
└───────────────────────────────────────────────────────┘
        │
        ▼ (por demanda + permissão explícita)
┌───────────────────────────────────────────────────────┐
│  OsintService — módulos direct.data (APIs pagas)    │
│  Perfis de profundidade:                             │
│  P1 → cadastro_pf_plus, historico_veiculos          │
│  P2 → P1 + mandados_prisao, pep, obito              │
│  P3 → P2 + aml, ceis, cnep                         │
│  P4 → P3 + processos_tj, ofac, lista_onu           │
│  Cache: 24h em ConsultaExterna                      │
└──────────────────────────┬────────────────────────────┘
                           │ dados externos
                           ▼
┌───────────────────────────────────────────────────────┐
│  AgenteFicha.gerar_ficha_pessoa()                    │
│  LLM: PREMIUM (Gemini Pro)                          │
│  Prompt: PROMPT_FICHA_PESSOA                        │
│  → Ficha completa salva em DocumentoGerado          │
└───────────────────────────────────────────────────────┘
```

**Endpoints:**
```
GET  /api/v1/agentes/osint/preliminar/{inquerito_id}/{pessoa_id}?aprimorar=false
POST /api/v1/agentes/ficha/pessoa/{pessoa_id}?inquerito_id=...
POST /api/v1/agentes/ficha/empresa/{empresa_id}?inquerito_id=...
```

---

### 3.3 Agente Extrato Bancário

```
POST /api/v1/agentes/extrato/{documento_id}
        │
        ▼
┌───────────────────────────────────────────────────────┐
│  AgenteExtrato.analisar_extrato()                    │
│  LLM: STANDARD (gemini-2.0-flash)                   │
│  Prompt: PROMPT_ANALISE_EXTRATO                     │
│                                                       │
│  → transacoes[], contrapartes[],                    │
│     score_suspeicao (0-10), alertas                 │
└───────────────────────────────────────────────────────┘
```

---

### 3.4 Agente Cautelar (Geração de Documentos Jurídicos)

```
POST /api/v1/agentes/cautelar/
        │
        ▼
┌───────────────────────────────────────────────────────┐
│  AgenteCautelar.gerar_cautelar()                     │
│  LLM: PREMIUM (gemini-2.0-flash)                    │
│  Prompt: PROMPT_CAUTELAR                            │
│                                                       │
│  Tipos suportados:                                   │
│  • oficio_requisicao     → Ofício/Requerimento       │
│  • mandado_busca         → Mandado de Busca e Apreensão │
│  • interceptacao_telefonica → Req. Interceptação    │
│  • quebra_sigilo_bancario → Req. Quebra de Sigilo   │
│  • autorizacao_prisao    → Req. Prisão Preventiva   │
│                                                       │
│  → Retorna minuta formatada em linguagem jurídica   │
└───────────────────────────────────────────────────────┘
```

---

## 4. Pipeline de Intimações

```
POST /intimacoes/upload  (PDF, PNG, JPG, TIFF)
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│  [CELERY] processar_intimacao(intimacao_id)              │
│                                                           │
│  ① Download do arquivo do S3                            │
│                                                           │
│  ② IntimacaoExtractor.extrair_tudo()                   │
│     LLM: VISION (gemini-flash-latest)                   │
│     → OCR + extração estruturada em passo único        │
│     fallback: Tesseract OCR se Gemini indisponível      │
│                                                           │
│  Campos extraídos:                                       │
│     intimado_nome, intimado_cpf, numero_inquerito,      │
│     data_oitiva, local_oitiva, qualificacao             │
│                                                           │
│  ③ Vincula ao Inquerito por numero_inquerito            │
│     (normalização do número para matching)              │
│                                                           │
│  ④ GoogleCalendarService.create_event()                 │
│     → Cria evento na agenda se data_oitiva presente     │
└───────────────────────────────────────────────────────────┘
```

---

## 5. Bot Telegram

```
Mensagem no Telegram
        │
POST /telegram/webhook
        │
        ▼
┌────────────────────────────────────────────────────────┐
│  Telegram Dispatcher (Function Calling)               │
│  LLM: PREMIUM (Gemini — decide qual ferramenta usar)  │
│                                                        │
│  Ferramentas disponíveis (Function Tools):            │
│  • listar_inqueritos()                               │
│  • status_inquerito(numero_ip)                       │
│  • busca_autos(numero_ip, query)   → RAG interno     │
│  • sintese_investigativa(numero_ip)                  │
│  • pesquisar_pessoa(cpf_ou_nome, perfil_osint)       │
│  • [+18 ferramentas adicionais]                      │
│                                                        │
│  LLM escolhe ferramenta → executa → responde        │
└────────────────────────────────────────────────────────┘
```

---

## 6. Scheduler (Celery Beat)

| Tarefa | Frequência | O que faz | LLM |
|--------|------------|-----------|-----|
| `verificar_alertas_intimacoes` | A cada 24h | Busca oitivas nas próximas 48h e envia alerta via Telegram | Nenhum |

---

## 7. Tabela Completa — Todos os Agentes e Tarefas

| Agente / Tarefa | Tipo | LLM | Tier | Prompt | Acionado por |
|----------------|------|-----|------|--------|--------------|
| `orchestrate_new_inquerito` | Celery | gemini-2.0-flash | Premium | `SYSTEM_PROMPT_ORQUESTRADOR` | Upload via `/ingestao/iniciar` |
| `ingestion` — classificação | Celery | gpt-4.1-nano | Econômico | `SYSTEM_PROMPT_CLASSIFICADOR_PECA` | Pipeline de ingestão |
| `ingestion` — NER | Celery | gemini-2.0-flash | Standard | `SYSTEM_PROMPT_EXTRACAO_ENTIDADES` | Pipeline de ingestão |
| `generate_summaries_task` | Celery | gpt-4.1-nano | Econômico | `PROMPT_RESUMO_*` (4 níveis) | Pós-ingestão |
| `processar_intimacao` | Celery | gemini-flash-latest | Vision | `_PROMPT_EXTRACAO_DIRETA` | `/intimacoes/upload` |
| `verificar_alertas_intimacoes` | Celery Beat | — | — | — | Agendador 24h |
| `CopilotoService` | HTTP | gemini-2.0-flash | Premium | `SYSTEM_PROMPT_COPILOTO` | `/copiloto/mensagens` |
| `CopilotoService` — auditoria | HTTP | gemini-2.0-flash | Premium | `SYSTEM_PROMPT_AUDITORIA_FACTUAL` | Opcional no copiloto |
| `AgenteFicha` — análise preliminar (auto) | HTTP | Groq llama-3.3-70b | **Resumo (gratuito)** | `PROMPT_ANALISE_PRELIMINAR` | `/agentes/osint/preliminar/{id}/{pid}` |
| `AgenteFicha` — análise preliminar (aprimorar) | HTTP | gemini-1.5-flash | Standard | `PROMPT_ANALISE_PRELIMINAR` | `/agentes/osint/preliminar/{id}/{pid}?aprimorar=true` |
| `AgenteFicha` (pessoa completa) | HTTP | gemini-1.5-pro | Premium | `PROMPT_FICHA_PESSOA` | `/agentes/ficha/pessoa/{id}` |
| `AgenteFicha` (empresa) | HTTP | gemini-1.5-pro | Premium | `PROMPT_FICHA_EMPRESA` | `/agentes/ficha/empresa/{id}` |
| `AgenteExtrato` | HTTP | gemini-1.5-flash | Standard | `PROMPT_ANALISE_EXTRATO` | `/agentes/extrato/{id}` |
| `AgenteCautelar` | HTTP | gemini-1.5-pro | Premium | `PROMPT_CAUTELAR` | `/agentes/cautelar/` |
| `OsintService` | HTTP | — (REST puro) | — | — | `/agentes/osint/enriquecer/*` |
| `EmbeddingService` | Utilitário | text-embedding-004 | — | — | Ingestão + Copiloto |
| `Telegram Dispatcher` | HTTP | gemini (FC) | Premium | — | `/telegram/webhook` |

---

## 8. Diagrama de Dependências entre Serviços

```
                         ┌──────────────────┐
                         │   Frontend       │
                         │   (Next.js 14)   │
                         └────────┬─────────┘
                                  │ REST
                         ┌────────▼─────────┐
                         │   FastAPI         │
                         │   (Railway)       │
                         └────┬──────┬───────┘
                              │      │
               ┌──────────────▼──┐ ┌─▼──────────────┐
               │  Celery Workers │ │  HTTP Agents    │
               │  (Redis queue)  │ │  (sync/async)   │
               └──┬──┬──┬──┬────┘ └──────────────────┘
                  │  │  │  │
      ┌───────────┘  │  │  └─────────────┐
      │              │  │                │
      ▼              ▼  ▼                ▼
┌─────────┐  ┌────────┐ ┌────────┐  ┌──────────┐
│ Qdrant  │  │Postgres│ │  S3 /  │  │ Google   │
│(vetores)│  │   DB   │ │ MinIO  │  │ Gemini + │
└─────────┘  └────────┘ └────────┘  │ OpenAI   │
                                     └──────────┘
                                          │
                                   ┌──────▼──────┐
                                   │ direct.data │
                                   │ (BigDataCorp│
                                   │  APIs OSINT)│
                                   └─────────────┘
```

---

## 9. Prompts Ativos — Referência Rápida

| Prompt | Tier | Propósito |
|--------|------|-----------|
| `SYSTEM_PROMPT_ORQUESTRADOR` | Premium | Análise inicial do caso + extração de metadados |
| `SYSTEM_PROMPT_COPILOTO` | Premium | Chat RAG com citação de fontes |
| `SYSTEM_PROMPT_AUDITORIA_FACTUAL` | Premium | Verifica factualidade da resposta do copiloto |
| `SYSTEM_PROMPT_CLASSIFICADOR_PECA` | Econômico | Classifica tipo de peça processual |
| `SYSTEM_PROMPT_EXTRACAO_ENTIDADES` | Standard | NER — extrai pessoas, empresas, endereços |
| `PROMPT_RESUMO_PAGINA` | Econômico | Resumo por página (max 3 linhas) |
| `PROMPT_RESUMO_DOCUMENTO` | Econômico | Resumo por documento (max 10 linhas) |
| `PROMPT_RESUMO_VOLUME` | Econômico | Resumo por volume (max 15 linhas) |
| `PROMPT_RESUMO_CASO` | Econômico | Síntese executiva do caso (max 20 linhas) |
| `PROMPT_SINTESE_INVESTIGATIVA` | Premium | Síntese investigativa completa (10 seções) |
| `PROMPT_ANALISE_PRELIMINAR` | Resumo/Groq (gratuito) ou Standard | Análise preliminar de personagem — só dados internos |
| `PROMPT_FICHA_PESSOA` | Premium | Ficha investigativa completa de pessoa (com dados externos) |
| `PROMPT_FICHA_EMPRESA` | Premium | Ficha investigativa de empresa |
| `PROMPT_CAUTELAR` | Premium | Minutas de medidas cautelares |
| `PROMPT_ANALISE_EXTRATO` | Standard | Análise de extrato bancário |
| `_PROMPT_EXTRACAO_DIRETA` (intimação) | Vision | OCR + extração de intimação |

---

*Gerado automaticamente a partir do código-fonte em `backend/app/`*
