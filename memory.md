# Escrivão AI — Memória do Projeto

**Atualizado em:** 08 de março de 2026 — 22h55 (horário de Brasília)

---

## 1. Stack Técnica

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python 3.11 + FastAPI |
| Banco Relacional | PostgreSQL 17.6 no **Supabase** (pooler AWS sa-east-1, SSL ativo, URL-encode da senha) |
| Banco Vetorial | Qdrant (Docker local, porta 6333) |
| Mensageria | Celery + Redis (Docker local, porta 6379) |
| Object Storage | MinIO (Docker local, porta 9000) |
| PDF / OCR | `pypdf` (texto nativo) + `pytesseract` + `pdf2image` (OCR seletivo) |
| Embeddings | `sentence-transformers` — modelo `all-MiniLM-L6-v2` (384 dims, local, custo zero) |
| LLM | OpenAI GPT-4 via `LLMService` — roteamento **Econômico** (gpt-4.1-nano) / **Premium** (gpt-4.1) |
| Testes | pytest + pytest-asyncio — **52 testes passando** atualmente |
| Deploy Planejado | Frontend → Vercel, Backend → a definir |

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
- Campo `tipo_peca` adicionado a `Documento` (ex: boletim_ocorrencia, despacho, laudo)
- `ExtractorService` — usa LLM Econômico em **JSON Mode** para:
  - Classificar tipo da peça processual
  - Fazer NER (Reconhecimento de Entidade Nomeada): Pessoas, Empresas, Endereços, Telefones, E-mails, Cronologia
- Integração no pipeline Celery — automático após extração de texto
- Migration Alembic aplicada no Supabase
- Novos endpoints `/api/v1/inqueritos/{id}/indices/{pessoas|empresas|enderecos|contatos|cronologia}`

---

## 3. Próximos Passos

### ⏳ Sprint 5 — Resumos Hierárquicos
- Geração assíncrona (Celery) de resumos por página → documento → volume → caso completo
- Armazenamento em cache de resumos para evitar reprocessamento
- Exibição nos endpoints de consulta do copiloto

### ⏳ Sprint 6 → 12 — Agentes Especializados e OSINT
Ver blueprint `investigacao_ai_v3_blueprint-3.md` (raiz do projeto) para detalhes.

---

## 4. Arquivos-Chave

| Arquivo | Função |
|---------|--------|
| `.env` | Variáveis de ambiente (Supabase, Redis, Qdrant, MinIO, LLM) |
| `backend/app/core/config.py` | Settings Pydantic — lê `.env` ou `../.env` |
| `backend/app/core/database.py` | Engine async + SSL Supabase + URL-encode da senha |
| `backend/app/core/prompts.py` | Todos os SYSTEM PROMPTS (copiloto, classificação, NER) |
| `backend/app/workers/ingestion.py` | Pipeline Celery de ingestão (extração → OCR → chunks → embeddings → NER → Qdrant) |
| `backend/app/services/extractor_service.py` | Classificação de peças + NER via LLM Econômico |
| `backend/app/services/copiloto_service.py` | RAG Copiloto conversacional |
| `backend/alembic/env.py` | Alembic configurado para conectar no Supabase (SSL, URL-encode) |
| `memory.md` | **Este arquivo** |

---

## 5. Comandos Úteis

```powershell
# Rodar testes
cd backend; .\venv\Scripts\python -m pytest tests/ -v

# Gerar migration Alembic
cd backend; $env:PYTHONPATH="."; .\venv\Scripts\alembic revision --autogenerate -m "descricao"

# Aplicar migration no Supabase
cd backend; $env:PYTHONPATH="."; .\venv\Scripts\alembic upgrade head

# Subir serviços Docker (Redis, Qdrant, MinIO)
docker-compose up -d redis qdrant minio
```
