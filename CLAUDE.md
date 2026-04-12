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
- **Railway deploy:** NUNCA commitar durante ingestão ativa — rolling deploy mata o container e perde a task Celery.
- **Celery workers:** engines async precisam de `postgresql+asyncpg://` (não `postgresql://`).
- **Gemini SDK:** não usar `aio.models.embed_content` — tem bug 404. Usar `asyncio.to_thread` para embeddings.
- **Next.js 16:** pdfjs-dist só via `dynamic` import em `useEffect`. Sem webpack config (Turbopack).
- **Git:** sempre `git push` após `git commit`. Nunca deixar commits locais.
- **SERPER_API_KEY:** Railway não injeta esta variável — está hardcoded como default em `config.py`. Não remover.
- **GROQ_API_KEY:** tem trailing `\n` no Railway — sempre usar `.strip()` ao usar a chave em headers HTTP.
- **LLM JSON output:** sempre usar `max_tokens` ≥ 2500 para endpoints que geram JSON com múltiplos campos. Prompt deve limitar explicitamente o tamanho das strings (máx 100 chars) para evitar truncamento.

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

## Stack resumida — adições recentes
| Camada | Tecnologia |
|--------|-----------|
| Web Search | Serper.dev (Google Search API) — OSINT fontes abertas |

## Arquivos de arquitetura
- `Documentos/arquitetura_agentes_llm.md` — fluxo completo de todos os agentes e tiers LLM
- `backend/app/core/prompts.py` — todos os system prompts (PROMPT_OSINT_WEB, PROMPT_OSINT_WEB_RELATORIO, etc.)
- `backend/app/api/agentes.py` — endpoints dos agentes especializados
- `backend/app/api/inqueritos.py` — CRUD + `/progresso` com `processos_bg`
- `backend/app/services/agente_ficha.py` — fichas, análise preliminar, OSINT web
- `backend/app/services/serper_service.py` — wrapper Serper.dev
- `src/components/osint/PainelInvestigacao.tsx` — painel OSINT (OsintWebPanel, AnalisePreliminarPanel)
- `src/app/inqueritos/[id]/page.tsx` — página do inquérito com ProcessosBgBadge
