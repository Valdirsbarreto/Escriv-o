# Escrivão AI — Contexto do Projeto para Claude Code

## O que é este projeto
Sistema de apoio à análise de inquéritos policiais com RAG + agentes LLM.
Backend FastAPI + Celery + Redis + Qdrant + Supabase. Frontend Next.js 16 no Vercel. Deploy na Railway.

## Ao iniciar uma sessão — leia primeiro
O sistema de memória automática já carrega `MEMORY.md`. Verifique os arquivos referenciados lá antes de fazer sugestões, especialmente:
- `memory/project_status.md` — o que está pronto e o que está pendente
- `memory/project_llm_tiers.md` — qual LLM usar em cada agente
- `memory/feedback_*.md` — erros já cometidos antes (não repetir)

## Restrições críticas
- **UI:** usa `@base-ui/react`, NÃO `@radix-ui`. Nunca importar ShadCN sem verificar existência.
- **Railway:** imports pesados (gRPC, Qdrant, torch) devem ser lazy dentro dos routers FastAPI — health check tem 100s de timeout.
- **Celery workers:** engines async precisam de `postgresql+asyncpg://` (não `postgresql://`).
- **Gemini SDK:** não usar `aio.models.embed_content` — tem bug 404. Usar `asyncio.to_thread` para embeddings.
- **Next.js 16:** pdfjs-dist só via `dynamic` import em `useEffect`. Sem webpack config (Turbopack).
- **Git:** sempre `git push` após `git commit`. Nunca deixar commits locais.

## Stack resumida
| Camada | Tecnologia |
|--------|-----------|
| Frontend | Next.js 16, Tailwind, @base-ui/react |
| Backend | FastAPI + SQLAlchemy async (PostgreSQL) |
| Workers | Celery + Redis |
| Vetores | Qdrant |
| Auth | Supabase (Google OAuth) |
| LLM | Groq (gratuito), Gemini Flash (standard), Gemini Pro (premium) |
| OSINT | direct.data (BigDataCorp) — APIs pagas, requer permissão |
| Deploy | Vercel (frontend) + Railway (backend + worker) |

## Arquivos de arquitetura
- `Documentos/arquitetura_agentes_llm.md` — fluxo completo de todos os agentes e tiers LLM
- `backend/app/core/prompts.py` — todos os system prompts
- `backend/app/api/agentes.py` — endpoints dos agentes especializados
- `src/components/osint/PainelInvestigacao.tsx` — painel OSINT por personagem
