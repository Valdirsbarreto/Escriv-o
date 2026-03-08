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
    yield
    # Shutdown
    print("🛑 Escrivão AI — Encerrando...")


app = FastAPI(
    title="Escrivão AI",
    description=(
        "Sistema de apoio à análise de inquéritos policiais. "
        "Ingestão assíncrona, RAG vetorial, copiloto investigativo, "
        "agentes especializados e auditoria factual obrigatória."
    ),
    version="0.1.0 — Sprint 1",
    lifespan=lifespan,
)

# CORS
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(inqueritos_router, prefix="/api/v1")


@app.get("/health", tags=["Sistema"])
async def health_check():
    """Health check da aplicação."""
    return {
        "status": "ok",
        "service": "escrivao-ai",
        "version": "0.1.0",
        "sprint": 1,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/", tags=["Sistema"])
async def root():
    """Página raiz com informações do sistema."""
    return {
        "nome": "Escrivão AI",
        "descricao": "Sistema de Apoio à Análise de Inquéritos Policiais",
        "versao": "0.1.0 — Sprint 1",
        "documentacao": "/docs",
        "health": "/health",
        "endpoints": {
            "inqueritos": "/api/v1/inqueritos",
        },
    }
