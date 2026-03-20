# Escrivão AI — Memória do Projeto

**Atualizado em:** 20 de março de 2026 — 18h00 (horário de Brasília)

---

## 1. Stack Técnica

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python 3.12 + FastAPI |
| Banco Relacional | PostgreSQL no **Supabase** (pooler AWS us-west-2, SSL ativo) |
| Banco Vetorial | Qdrant (serviço Railway, `qdrant.railway.internal:6333`) |
| Mensageria | Celery + Redis (serviço Railway, `redis.railway.internal:6379`) |
| Object Storage | Supabase Storage (prod) / MinIO (dev local) |
| PDF / OCR | `pypdf` + `pytesseract` + `pdf2image` |
| Embeddings | `sentence-transformers` — `all-MiniLM-L6-v2` (384 dims, local) |
| LLM | **3 Camadas**: Econômico (GPT-4.1-nano/OpenAI), Standard (Gemini Flash), Premium (Gemini Pro) |
| Testes | pytest + pytest-asyncio |
| CI/CD | GitHub Actions (`.github/workflows/ci.yml`) |
| Deploy Frontend | **Vercel** (auto-deploy em push para `main`) |
| Deploy Backend | **Railway** — serviço `Escriv-o` (FastAPI + Celery no mesmo container) |

---

## 2. Sprints Entregues

### ✅ Sprint 1 — Fundação (`a377113`)
- Docker Compose completo (Redis, Qdrant, MinIO)
- 7 modelos SQLAlchemy iniciais + Alembic
- FSM (Máquina de estados com 11 estados do inquérito)
- CRUD de Inquéritos, upload de PDF via Celery

### ✅ Sprint 2 — Ingestão + RAG (`3bf2391`)
- OCR seletivo (páginas sem texto nativo)
- Embeddings locais + indexação batch no Qdrant
- Modelos `Volume` e `LogIngestao` (rastreio granular)
- Endpoint de busca semântica RAG (`POST /api/v1/busca/`)

### ✅ Sprint 3 — Copiloto Investigativo (`95dac25`)
- Modelos `SessaoChat` e `MensagemChat` (histórico por sessão com rastreio de tokens/custo)
- `LLMService` com roteamento econômico/premium
- `CopilotoService` — Pipeline RAG completo com citações obrigatórias e auditoria factual automática
- Prompts especializados (copiloto, triagem, auditoria JSON)
- API completa: criar sessão, chat, histórico, encerrar
- Infraestrutura migrada para Supabase; CORS configurado para Vercel

### ✅ Sprint 4 — Classificação e Índices (`bcaf815`)
- Novos modelos: `Empresa`, `Endereco`, `Contato`, `EventoCronologico`
- Campo `tipo_peca` adicionado a `Documento`
- `ExtractorService` — LLM Econômico em JSON Mode para classificação + NER
- Novos endpoints `/api/v1/inqueritos/{id}/indices/{pessoas|empresas|enderecos|contatos|cronologia}`

### ✅ Sprint 5 — Resumos Hierárquicos
- Geração assíncrona (Celery) de resumos por página → documento → volume → caso completo
- Armazenamento em cache de resumos para evitar reprocessamento

### ✅ Sessão de Deployment — 19/03/2026 (`9908aed`)
- Correção do módulo Celery (`app.workers.celery_app`)
- CORS com `allow_origin_regex` para Vercel
- `DATABASE_URL_SYNC` derivada automaticamente do `DATABASE_URL`
- Commit imediato do inquérito para visibilidade instantânea no Dashboard

### ✅ Sessão de Estabilização em Produção — 20/03/2026
Commits: `cff2c44`, `df09856`, `6995094`, `5b4c67e`, `dd8b7fe`, `dd8e9a9`, `d0430c3`

- **Redis Auth** (`cff2c44`): `config.py` injeta `REDISPASSWORD` na `REDIS_URL` quando a URL não tem `@`. Railway define `REDIS_URL` sem senha — agora funciona automaticamente.
- **Celery Concurrency** (`df09856`): limitado a `--concurrency=2` (era 48 workers = ~14GB RAM). `broker_connection_retry_on_startup=True` adicionado. `nixpacks.toml` sincronizado com `railway.toml`.
- **Tasks não registradas** (`6995094`): `orchestrator` e `summary_task` não estavam no `include` do `celery_app.py`. Adicionados.
- **Event loop fechado** (`5b4c67e`): `orchestrator.py` fechava o loop asyncio antes de usá-lo pela segunda vez. Consolidadas todas as chamadas async em uma única corrotina.
- **Argumento inválido** (`dd8b7fe`): `extract_with_ocr()` não aceita `max_pages`. Removido.
- **Axios timeout** (`dd8e9a9`): Frontend ficava em spinner eterno sem timeout. Adicionado 15s para API e 60s para upload.
- **Número TEMP** (`d0430c3`): Orquestrador criava inquéritos com `TEMP-XXXXXX` por falha na extração via LLM. Adicionada extração por regex do filename antes de chamar o LLM (ex: `033-07699-2016.pdf` → número `033-07699-2016`).

---

## 3. Estado Atual (20/03/2026)

**Sistema em produção funcionando:**
- ✅ Pipeline de ingestão completo (upload → storage → chunks → embeddings → Qdrant → NER)
- ✅ Inquéritos aparecem no Dashboard após ingestão
- ✅ Página de detalhes carregando documentos com status de indexação
- ✅ 4/4 documentos indexados em teste real com IP 033-07699-2026
- ⚠️ Número do IP ainda mostra TEMP nos inquéritos já criados (fix aplicado para novos)
- ⚠️ Copiloto não testado ainda em produção

---

## 4. Próximos Passos

### ⏳ Imediato
- **Testar o Copiloto** em produção com um inquérito indexado
- **Separar Celery em serviço próprio** na Railway (P2 — estabilidade)
- **Substituir sentence-transformers** por API de embeddings (OpenAI/Gemini) para eliminar custo de memória

### Sprint 6
- **Agentes Especializados e OSINT**: Tela de triagem OSINT para enriquecimento de dados de pessoas

### Pendências de Infraestrutura
- Autenticação de usuários (sem auth hoje — qualquer um com a URL acessa)
- Monitoramento de tasks Celery (Flower ou similar)
- Websocket para progresso de ingestão em tempo real

---

## 5. Arquitetura Railway

| Serviço | Função |
|---------|--------|
| `Escriv-o` | FastAPI (porta `$PORT`) + Celery worker (2 workers) — mesmo container |
| `Redis` | Broker Celery + backend de resultados |
| `qdrant` | Banco vetorial para embeddings |

**Variáveis críticas no serviço `Escriv-o`:**
- `REDIS_URL` = `redis://default:SENHA@redis.railway.internal:6379` (com senha!)
- `DATABASE_URL` = connection string async Supabase
- `DATABASE_URL_SYNC` = derivada automaticamente se não definida

---

## 6. Arquivos-Chave

| Arquivo | Função |
|---------|--------|
| `.env` | Variáveis de ambiente locais |
| `backend/app/core/config.py` | Settings Pydantic + injeção automática de Redis auth |
| `backend/app/core/database.py` | Engine async + SSL Supabase |
| `backend/app/core/prompts.py` | Todos os SYSTEM PROMPTS |
| `backend/app/workers/celery_app.py` | Config Celery — include das 3 tasks |
| `backend/app/workers/orchestrator.py` | Task mestre de orquestração — cria inquérito + dispara ingestões |
| `backend/app/workers/ingestion.py` | Pipeline: extração → OCR → chunks → embeddings → NER → Qdrant |
| `backend/app/workers/summary_task.py` | Resumos hierárquicos assíncronos |
| `backend/app/services/orchestrator_service.py` | LLM análise inicial + relatório de boas-vindas |
| `backend/app/services/extractor_service.py` | Classificação de peças + NER |
| `backend/app/services/copiloto_service.py` | RAG Copiloto conversacional |
| `backend/railway.toml` | Comando de start: Celery + Uvicorn |
| `backend/nixpacks.toml` | Build config Railway (tesseract, poppler) |
| `src/lib/api.ts` | Axios com timeout (15s API, 60s upload) |
| `memory.md` | **Este arquivo** |

---

## 7. Comandos Úteis

```powershell
# Rodar testes
cd backend; .\venv\Scripts\python -m pytest tests/ -v

# Gerar migration Alembic
cd backend; $env:PYTHONPATH="."; .\venv\Scripts\alembic revision --autogenerate -m "descricao"

# Aplicar migration no Supabase
cd backend; $env:PYTHONPATH="."; .\venv\Scripts\alembic upgrade head

# Subir serviços Docker locais (Redis, Qdrant, MinIO)
docker-compose up -d redis qdrant minio
```
