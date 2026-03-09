# Escrivão AI — Memória do Projeto

**Atualizado em:** 08 de março de 2026

## 1. Visão Geral
O Escrivão AI é um sistema de apoio à análise de inquéritos policiais, desenvolvido para processar grandes volumes de documentos (PDFs), realizar OCR, extrair dados, gerar vetores semânticos (embeddings) e permitir consultas via copiloto conversacional RAG (Retrieval-Augmented Generation).

## 2. Arquitetura e Stack
- **Backend:** Python 3.11+ com FastAPI
- **Banco de Dados Relacional:** PostgreSQL 17.6 hospedado no **Supabase** (usando pooler e SSL ativo)
- **Banco Vetorial:** Qdrant (Docker local) para busca semântica RAG
- **Mensageria/Task Queue:** Celery + Redis (Docker local)
- **Object Storage:** MinIO (Docker local) compatível com S3
- **Processamento de PDF:** `pypdf` para texto nativo + `pytesseract` (pdf2image) para OCR seletivo
- **Embeddings:** `sentence-transformers` (modelo local `all-MiniLM-L6-v2`, 384 dimensões)
- **Serviço LLM:** Wrapper customizado (`LLMService`) suportando OpenAI (GPT-4o/mini) com roteamento entre camadas "econômica" e "premium"
- **Testes:** pytest + pytest-asyncio (atualmente **47 testes** passando)

## 3. Estado Atual de Desenvolvimento

O projeto segue um cronograma em Sprints. Os Sprints 1 a 3 estão concluídos e integrados na branch `main`.

### ✅ Sprint 1 — Fundação
- Containerização base (docker-compose)
- Modelos SQLAlchemy (Inquérito, Documento, Chunk, Pessoa, etc) e integrações Alembic
- Máquina de Estados (11 estados de fluxo) e CRUD básico
- Pipeline estrutural Celery para processamento assíncrono

### ✅ Sprint 2 — Ingestão Documental + RAG
- Implementação de OCR seletivo para PDFs scaneados
- Geração local de embeddings e indexação batch no Qdrant
- Modelos `Volume` e rastreio granular com `LogIngestao`
- Endpoint de busca vetorial RAG

### ✅ Sprint 3 — Copiloto Investigativo
- Pipeline RAG completo: Busca contexto $\rightarrow$ Envia ao LLM $\rightarrow$ Resposta com citações estruturadas `[Doc: p. X]`
- Auditoria Factual automatizada via LLM econômico (validação de alucinações via JSON)
- Gestão de sessões conversacionais e histórico (`SessaoChat`, `MensagemChat`) com rastreio de tokens/custo.
- Mudança de infraestrutura: Banco migrado para Supabase (externo) e CORS ajustado para front da Vercel.

## 4. Próximos Passos Faltantes (Roadmap)

Os próximos sprints, focados em abstração avançada e multi-agentes, são:

### ⏳ Sprint 4 — Extração e Classificação Automática
- Classificação de tipo de peça processual via LLM na ingestão.
- Entidades Nomeadas (NER) avançada: Pessoas, empresas, CPFs, datas, locais e veículos.
- Relacionar entidades aos chunks (Graph/Relational sync).

### ⏳ Sprint 5 — Resumos Hierárquicos e Agentes
- Geração de resumos assíncronos (Página $\rightarrow$ Documento $\rightarrow$ Volume $\rightarrow$ Inquérito completo).
- Integração da máquina de estados com ações de Triagem, Relatório Final e Análise de Quebras/Cautelares focados por "Agentes".

## 5. Variáveis de Ambiente Críticas (`.env`)
O projeto requer:
- `DATABASE_URL` do Supabase pooler (senha codificada/URL-encoded).
- `SUPABASE_*` credentials.
- Conexões locais padrão (`REDIS_URL`, `QDRANT_HOST`, `S3_*`).
- Chaves de API de IA: `LLM_ECONOMICO_API_KEY` e `LLM_PREMIUM_API_KEY` (usualmente conectadas via OpenAI).
