# Plano de Otimização de Tiers LLM — Gemma + Gemini
## Projeto Escrivão AI (Antigravity)

> Data: 05 de Abril de 2026
> Objetivo: Introduzir Gemma (open weights) para tarefas de baixo custo,
> reservando Gemini 1.5 Pro exclusivamente para a inteligência de alto valor.

---

## 1. Diagnóstico da Arquitetura Atual

### Estado pós-migração (04/04/2026)

| Tier | Modelo | Usado em | Problema |
|------|--------|----------|---------|
| `economico` | `gemini-1.5-flash-8b` | Classificação, NER, Resumos, Auditoria | Cobrado por token mesmo para tarefas mecânicas |
| `standard` | `gemini-1.5-flash` | Orquestração, Extrato bancário | Caro para NER de volume |
| `premium` | `gemini-1.5-pro` | Copiloto RAG, Fichas, Cautelares | ✅ Correto — alto valor |
| `vision` | `gemini-1.5-flash` | OCR intimações | ✅ Correto — único com visão |

### Problema central
O processamento em massa (NER, Classificação, Resumos) consome a maior parte do orçamento por volume de chamadas, mas não exige capacidade Pro. Gemma via OpenRouter custa 3–8× menos para essas tarefas.

---

## 2. Mapeamento de Tiers Proposto

### Nota sobre "Gemma 4 31B"
Não existe variante 31B do Gemma. O modelo disponível mais próximo é **Gemma 3 27B-IT** (Google, open weights). Para NER de alta precisão, é o modelo correto. O Gemma 4 lançado em 2025 tem variantes até 27B — usar `gemma-4-27b-it` quando disponível via OpenRouter.

### Nova tabela de tiers

| Tier (novo nome) | Modelo | Provider | Custo ~USD/1M | Usado em |
|-----------------|--------|----------|--------------|----------|
| `triagem` | `google/gemma-3-12b-it` | OpenRouter | $0.04 in / $0.10 out | Classificação de peças processuais |
| `extracao` | `google/gemma-3-27b-it` | OpenRouter | $0.10 in / $0.25 out | NER (pessoas, empresas, endereços) |
| `resumo` | `google/gemma-3-27b-it` | OpenRouter | $0.10 in / $0.25 out | Resumos hierárquicos (4 níveis) |
| `auditoria` | `google/gemma-3-27b-it` | OpenRouter | $0.10 in / $0.25 out | Auditoria factual do copiloto |
| `standard` | `gemini-1.5-flash` | Google Gemini | $0.075 in / $0.30 out | Orquestração, extrato bancário |
| `premium` | `gemini-1.5-pro` | Google Gemini | $1.25 in / $5.00 out | Copiloto RAG, Fichas, Cautelares, Síntese |
| `vision` | `gemini-1.5-flash` | Google Gemini | $0.075 in / $0.30 out | OCR intimações (imagem) |

### Por que OpenRouter para Gemma?
- Já existe `OPENROUTER_API_KEY` no `config.py` (não precisa de nova conta)
- API 100% compatível com OpenAI (base_url + Bearer token)
- Sem infraestrutura local (Railway não tem GPU)
- Latência aceitável para tarefas batch (Celery workers)

---

## 3. Mapeamento Função → Tier

```
ExtractorService.classificar_documento()   → tier="triagem"    (era "economico")
ExtractorService.extrair_entidades()       → tier="extracao"   (era "standard")

SummaryService.resumir_documento()         → tier="resumo"     (era "economico")
SummaryService.resumir_volume()            → tier="resumo"     (era "economico")
SummaryService.resumir_caso()             → tier="resumo"     (era "standard")

CopilotoService._auditar_resposta()        → tier="auditoria"  (era "economico")
OrchestratorService.analisar_documentos()  → tier="standard"   (sem mudança)
AgenteExtrato.analisar_extrato()           → tier="standard"   (sem mudança)

CopilotoService.processar_mensagem()       → tier="premium"    (sem mudança ✅)
AgenteFicha.gerar_ficha_*()               → tier="premium"    (sem mudança ✅)
AgenteCautelar.gerar_cautelar()           → tier="premium"    (sem mudança ✅)

IntimacaoExtractor (OCR)                   → vision direto     (sem mudança ✅)
```

---

## 4. Mudanças Técnicas Necessárias

### 4a — `backend/app/core/config.py`

Adicionar:
```python
# ── LLM Camada Triagem (Gemma via OpenRouter) ──────────
LLM_TRIAGEM_MODEL: str = "google/gemma-3-12b-it"
LLM_TRIAGEM_PROVIDER: str = "openrouter"

# ── LLM Camada Extração (Gemma via OpenRouter) ──────────
LLM_EXTRACAO_MODEL: str = "google/gemma-3-27b-it"
LLM_EXTRACAO_PROVIDER: str = "openrouter"

# ── LLM Camada Resumo (Gemma via OpenRouter) ────────────
LLM_RESUMO_MODEL: str = "google/gemma-3-27b-it"
LLM_RESUMO_PROVIDER: str = "openrouter"

# ── LLM Camada Auditoria (Gemma via OpenRouter) ─────────
LLM_AUDITORIA_MODEL: str = "google/gemma-3-27b-it"
LLM_AUDITORIA_PROVIDER: str = "openrouter"

OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
# OPENROUTER_API_KEY já existe no config
```

### 4b — `backend/app/services/llm_service.py`

Reintroduzir `_openrouter_completion` (path OpenAI-compatível) de forma limpa, sem misturar com o path Gemini:

```python
async def chat_completion(self, messages, tier="premium", temperature=0.3,
                          max_tokens=2000, json_mode=False, agente="Desconhecido"):

    # Tiers Gemini
    if tier == "premium":
        return await self._gemini_completion(messages, self.premium_model, ...)
    elif tier == "standard":
        return await self._gemini_completion(messages, self.std_model, ...)
    elif tier == "vision":
        return await self._gemini_completion(messages, self.vision_model, ...)

    # Tiers Gemma (OpenRouter)
    elif tier in ("triagem", "extracao", "resumo", "auditoria"):
        model = {
            "triagem": settings.LLM_TRIAGEM_MODEL,
            "extracao": settings.LLM_EXTRACAO_MODEL,
            "resumo": settings.LLM_RESUMO_MODEL,
            "auditoria": settings.LLM_AUDITORIA_MODEL,
        }[tier]
        return await self._openrouter_completion(messages, model, temperature, max_tokens, json_mode)
```

O `_openrouter_completion` usa `httpx` com header `Authorization: Bearer {OPENROUTER_API_KEY}` e endpoint `/chat/completions` — padrão OpenAI.

### 4c — Serviços: atualizar parâmetro `tier`

Apenas 4 arquivos precisam trocar o `tier`:
- `extractor_service.py`: `"economico"` → `"triagem"`, `"standard"` → `"extracao"`
- `summary_service.py`: `"economico"` → `"resumo"`, `"standard"` → `"resumo"`
- `copiloto_service.py`: auditoria `"economico"` → `"auditoria"`

### 4d — `requirements.txt`

`httpx` já está presente (`httpx==0.28.*`) — sem novo pacote necessário.
Não é preciso adicionar o SDK `openai` — usando httpx diretamente para OpenRouter.

---

## 5. Variáveis de Ambiente no Railway

| Variável | Valor | Ação |
|----------|-------|------|
| `OPENROUTER_API_KEY` | `sk-or-...` | Já existe — confirmar |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Adicionar (ou deixar no default) |
| `LLM_TRIAGEM_MODEL` | `google/gemma-3-12b-it` | Opcional (padrão já no config) |
| `LLM_EXTRACAO_MODEL` | `google/gemma-3-27b-it` | Opcional |
| `LLM_RESUMO_MODEL` | `google/gemma-3-27b-it` | Opcional |

---

## 6. Projeção de Custo Mensal

Assumindo carga moderada (100 documentos/mês, 500 perguntas copiloto):

| Tarefa | Tier | Modelo | Custo estimado/mês |
|--------|------|--------|--------------------|
| Classificação (100 docs) | triagem | Gemma 3 12B | ~$0.05 |
| NER (100 docs, ~10k tokens each) | extracao | Gemma 3 27B | ~$0.30 |
| Resumos 4 níveis (100 docs) | resumo | Gemma 3 27B | ~$0.80 |
| Auditoria (500 chamadas) | auditoria | Gemma 3 27B | ~$0.40 |
| Orquestração | standard | Gemini Flash | ~$0.20 |
| Copiloto (500 msgs, ~3k tokens cada) | premium | Gemini 1.5 Pro | ~$8.00 |
| Fichas OSINT (20/mês) | premium | Gemini 1.5 Pro | ~$1.00 |
| Cautelares (10/mês) | premium | Gemini 1.5 Pro | ~$0.50 |
| **TOTAL USD** | | | **~$11.25** |
| **TOTAL BRL** (×5.80) | | | **~R$65,25** |

Economia vs. configuração atual (estimativa): **R$65 vs ~R$120** — redução de ~45%.
Margem ampla para crescimento dentro do limite de R$250.

---

## 7. Riscos e Mitigações

| Risco | Probabilidade | Mitigação |
|-------|--------------|-----------|
| Gemma 3 27B menos preciso que Flash no NER | Média | Testar com 10 docs reais antes de migrar produção |
| OpenRouter indisponível (fora do ar) | Baixa | Fallback automático: se `_openrouter_completion` falhar → usar gemini-1.5-flash |
| Latência maior no OpenRouter | Média | Aceitável para Celery workers (assíncrono, não é tempo real) |
| `json_mode` inconsistente no Gemma | Média | Adicionar parser de fallback (já existe em extractor_service.py) |
| Gemma 4 27B não disponível no OpenRouter | Baixa | Usar Gemma 3 27B como substituto |

---

## 8. Checklist de Execução

```
[ ] 1. Verificar OPENROUTER_API_KEY no Railway (já deve existir)
[ ] 2. Testar manualmente: POST openrouter.ai/api/v1/chat/completions com gemma-3-12b-it
[ ] 3. Editar config.py — adicionar 4 novos campos LLM_*_MODEL
[ ] 4. Editar llm_service.py — reintroduzir _openrouter_completion + novo dispatch
[ ] 5. Editar extractor_service.py — trocar tiers
[ ] 6. Editar summary_service.py — trocar tiers
[ ] 7. Editar copiloto_service.py auditoria — trocar tier
[ ] 8. Testar localmente com pytest (unit) — verificar mock do OpenRouter
[ ] 9. Push + Railway redeploy
[ ] 10. Monitorar consumo_api por 48h — comparar custos antes/depois
```

---

## 9. O que NÃO muda

- `gemini-1.5-pro` permanece como o único modelo para interação humana (Copiloto)
- `gemini-1.5-flash` (vision) permanece para OCR de intimações (Gemma não tem visão via API)
- `text-embedding-004` permanece para vetores Qdrant (Google, sem alternativa custo-benefício)
- Toda a lógica de `consumo_api`, alertas Telegram e dashboard de orçamento funciona sem alteração (o campo `agente` já rastreia por tier)

---

*Plano elaborado com base na arquitetura atual em `backend/app/` e diretriz do Coordenador Valdir.*
