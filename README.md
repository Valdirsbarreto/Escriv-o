# Escrivão AI — Sistema de Apoio à Análise de Inquéritos Policiais

Sistema inteligente para ingestão, indexação e análise de inquéritos policiais volumosos (até 3.000+ páginas), com copiloto investigativo conversacional, agentes especializados sob demanda e auditoria factual obrigatória.

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (React)                      │
├─────────────────────────────────────────────────────────┤
│                  FastAPI Backend (API)                    │
├──────────┬──────────┬──────────┬────────────────────────┤
│ PostgreSQL│  Qdrant  │  Redis   │  MinIO (S3)            │
│ (relac.) │ (vetorial)│ (fila)  │ (arquivos)             │
└──────────┴──────────┴──────────┴────────────────────────┘
```

**Stack:** FastAPI · PostgreSQL 16 · Qdrant · Redis 7 · MinIO · Celery · SQLAlchemy 2 · Pydantic 2

## 📋 Sprint 1 — Fundação (Atual)

- ✅ Monorepo com Docker Compose (PostgreSQL, Qdrant, Redis, MinIO)
- ✅ Backend FastAPI com health check e documentação Swagger
- ✅ 7 modelos SQLAlchemy (inquéritos, documentos, chunks, pessoas, transições, tarefas, auditorias)
- ✅ Máquina de estados do inquérito (11 estados, transições validadas, ações por estado)
- ✅ CRUD de inquéritos + menu de ações pós-carga
- ✅ Upload de PDFs com armazenamento no MinIO
- ✅ Pipeline assíncrono de ingestão (Celery): extração → chunking → indexação
- ✅ Serviço de busca vetorial Qdrant (preparado para RAG)
- ✅ Extração de texto de PDF com chunking (500-800 palavras com overlap)
- ✅ Alembic para migrations
- ✅ Testes automatizados

## 🚀 Instalação e Execução

### Pré-requisitos

- Docker e Docker Compose
- Python 3.11+
- Git

### 1. Clonar o repositório

```bash
git clone https://github.com/Valdirsbarreto/Escriv-o.git
cd Escriv-o
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite .env se necessário (os padrões funcionam para dev local)
```

### 3. Subir os serviços de infraestrutura

```bash
docker-compose up -d
```

Aguarde até que todos os serviços estejam healthy:

```bash
docker-compose ps
```

### 4. Instalar dependências do backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 5. Rodar migrations

```bash
cd backend
alembic revision --autogenerate -m "Sprint 1 - tabelas iniciais"
alembic upgrade head
```

### 6. Iniciar o backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Acesse a documentação Swagger: **http://localhost:8000/docs**

### 7. Iniciar o worker Celery (em outro terminal)

```bash
cd backend
celery -A app.workers.celery_app worker --loglevel=info
```

## 🧪 Testes

```bash
cd backend
python -m pytest tests/ -v
```

## 📡 Endpoints principais (Sprint 1)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/health` | Health check |
| POST | `/api/v1/inqueritos/` | Criar inquérito |
| GET | `/api/v1/inqueritos/` | Listar inquéritos |
| GET | `/api/v1/inqueritos/{id}` | Detalhe do inquérito |
| GET | `/api/v1/inqueritos/{id}/status` | Status + ações disponíveis |
| PATCH | `/api/v1/inqueritos/{id}/estado` | Transição de estado (FSM) |
| GET | `/api/v1/inqueritos/{id}/menu` | Menu de opções pós-carga |
| POST | `/api/v1/inqueritos/{id}/upload` | Upload de PDF |
| GET | `/api/v1/inqueritos/{id}/documentos` | Listar documentos |

## 🔄 Máquina de Estados

```
recebido → indexando → triagem → investigação_preliminar → investigação_ativa
                                                          ↕
                                         diligências_externas ← → aguardando_resposta
                                                          ↓
                                                    análise_final → relatório → encerramento → arquivamento
```

## 📂 Estrutura do Projeto

```
backend/
├── app/
│   ├── api/              # Endpoints REST
│   │   └── inqueritos.py
│   ├── core/             # Configuração e fundamentos
│   │   ├── config.py
│   │   ├── database.py
│   │   └── state_machine.py
│   ├── models/           # Modelos SQLAlchemy
│   │   ├── inquerito.py
│   │   ├── documento.py
│   │   ├── chunk.py
│   │   ├── pessoa.py
│   │   ├── estado_inquerito.py
│   │   ├── tarefa_agente.py
│   │   └── auditoria.py
│   ├── schemas/          # Schemas Pydantic
│   │   ├── inquerito.py
│   │   └── documento.py
│   ├── services/         # Serviços de infraestrutura
│   │   ├── storage.py
│   │   ├── qdrant_service.py
│   │   └── pdf_extractor.py
│   ├── workers/          # Tasks assíncronas Celery
│   │   ├── celery_app.py
│   │   └── ingestion.py
│   └── main.py           # Entrypoint FastAPI
├── alembic/              # Migrations
├── tests/                # Testes automatizados
├── requirements.txt
└── pytest.ini
```

## 🗺️ Roadmap (Próximos Sprints)

- **Sprint 2:** Ingestão documental completa (OCR seletivo, logs detalhados)
- **Sprint 3:** Chunking avançado + embeddings + indexação Qdrant + RAG
- **Sprint 4:** Classificação de peças + extração de entidades + índices
- **Sprint 5:** Resumos hierárquicos (página, documento, volume, caso)
- **Sprint 6:** Copiloto Investigativo conversacional
- **Sprint 7:** Agentes investigativos (linhas, oitivas, diligências)
- **Sprint 8:** Produção documental (ofícios, relatórios)
- **Sprint 9:** Auditoria factual forte
- **Sprint 10-14:** OSINT, cautelares, frontend avançado, deploy
