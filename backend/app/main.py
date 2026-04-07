"""
Escrivão AI — FastAPI Application
Entrypoint principal da aplicação.
"""

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.inqueritos import router as inqueritos_router
from app.api.busca import router as busca_router
from app.api.copiloto import router as copiloto_router
from app.api.indices import router as indices_router
from app.api.agentes import router as agentes_router
from app.api.ingestao import router as ingestao_router
from app.api.intimacoes import router as intimacoes_router
from app.api.telegram import router as telegram_router
from app.api.consumo import router as consumo_router
from app.api.documentos_gerados import router as docs_gerados_router
from app.api.pecas_extraidas import router as pecas_router
from app.api.agente_chat import router as agente_chat_router


async def _diagnostico_embeddings():
    """Verifica quais modelos de embedding estão disponíveis com a API key configurada."""
    if not settings.GEMINI_API_KEY:
        print("   [EMBEDDINGS] GEMINI_API_KEY não configurada — embeddings desativados")
        return
    try:
        from google import genai
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        modelos = client.models.list()
        embedding_models = [
            m.name for m in modelos
            if "embed" in (m.name or "").lower() or "embed" in str(getattr(m, "supported_actions", "")).lower()
        ]
        if embedding_models:
            print(f"   [EMBEDDINGS] Modelos disponíveis: {embedding_models[:5]}")
        else:
            print("   [EMBEDDINGS] Nenhum modelo de embedding encontrado com esta API key")
    except Exception as e:
        print(f"   [EMBEDDINGS] Erro ao listar modelos: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events."""
    # Startup
    print("🔍 Escrivão AI — Sistema de Apoio à Análise de Inquéritos")
    print(f"   Ambiente: {settings.APP_ENV}")
    print(f"   Database: {settings.DATABASE_URL[:50]}...")
    print(f"   Qdrant:   {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
    print(f"   Redis:    {settings.REDIS_URL}")
    print(f"   Storage:  {settings.S3_ENDPOINT_URL}")
    print("   ──────────────────────────────────────────────")
    await _diagnostico_embeddings()
    yield
    # Shutdown
    print("🛑 Escrivão AI — Encerrando...")


app = FastAPI(
    title="Escrivão AI API",
    description="API do backend do sistema Escrivão AI. Sprint 4: Classificação e Índices.",
    version="0.4.0",
    lifespan=lifespan,
)

# CORS — suporta múltiplos domínios separados por vírgula (incluindo Vercel)
_cors_origins_raw = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
_allow_all = settings.APP_ENV != "production"  # em dev, libera tudo

# Filtra origens com wildcard da lista literal (não suportado pelo navegador em Access-Control-Allow-Origin)
# FastAPI usa allow_origin_regex para tratar esses casos.
_literal_origins = [o for o in _cors_origins_raw if "*" not in o]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allow_all else _literal_origins,
    allow_origin_regex=r"https://.*\.vercel\.app" if not _allow_all else None,
    allow_credentials=True,  # Necessário para cookies/sessões se houver
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(inqueritos_router, prefix="/api/v1")
app.include_router(busca_router, prefix="/api/v1")
app.include_router(copiloto_router, prefix="/api/v1")
app.include_router(indices_router, prefix="/api/v1")
app.include_router(agentes_router)
app.include_router(ingestao_router, prefix="/api/v1")
app.include_router(intimacoes_router, prefix="/api/v1")
app.include_router(telegram_router, prefix="/api/v1")
app.include_router(consumo_router, prefix="/api/v1")
app.include_router(docs_gerados_router, prefix="/api/v1")
app.include_router(pecas_router, prefix="/api/v1")
app.include_router(agente_chat_router, prefix="/api/v1")


@app.get("/health", tags=["Sistema"])
async def health_check():
    """Health check da aplicação."""
    return {
        "status": "ok",
        "service": "escrivao-ai",
        "version": "0.2.0",
        "sprint": 2,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/", tags=["Sistema"])
async def root():
    """Página raiz com informações do sistema."""
    return {
        "nome": "Escrivão AI",
        "descricao": "Sistema de Apoio à Análise de Inquéritos Policiais",
        "versao": "0.2.0 — Sprint 2",
        "documentacao": "/docs",
        "health": "/health",
        "endpoints": {
            "inqueritos": "/api/v1/inqueritos",
            "busca": "/api/v1/busca",
        },
    }
