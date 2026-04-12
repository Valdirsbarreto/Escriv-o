# Plano de Execução — Migração Integral para Google Gemini
## Diretriz de Reestruturação e Automação — Projeto Escrivão AI (Antigravity)

> Data: 04 de Abril de 2026
> Baseado na Diretriz assinada por Valdir — Coordenador do Projeto
> Arquiteto: Claude Sonnet 4.6

---

## Resumo Executivo

A migração é predominantemente cirúrgica. O codebase já está bem posicionado:
- `llm_service.py` já possui um caminho `_gemini_completion` funcional para Gemini
- `google-genai` **já é o único SDK de LLM em `requirements.txt`** (o pacote `openai` nunca foi instalado)
- O tier econômico usava `httpx` bruto para chamar `api.openai.com` — esse caminho será deletado
- **Blast radius mínimo:** apenas `config.py` e `llm_service.py` precisam de mudança bloqueante

**Resultado esperado:** eliminação de 100% da dependência OpenAI, redução de custo em ~2.5× no processamento em massa, e ganho de janela de contexto de 40k → 2M tokens no tier Premium.

---

## Nova Tabela de Tiers (Target State)

| Tier | Modelo | Janela | Custo (USD/1M tokens) | Uso |
|------|--------|--------|----------------------|-----|
| **Econômico** | `gemini-1.5-flash-8b` | 1M tokens | In $0.038 / Out $0.15 | NER, classificação, resumos (4 níveis), auditoria |
| **Standard / Vision** | `gemini-1.5-flash` | 1M tokens | In $0.075 / Out $0.30 | Extrato bancário, OCR intimações, orquestração |
| **Premium** | `gemini-1.5-pro` | **2M tokens** | In $1.25 / Out $5.00 | Copiloto RAG, ficha investigativa, cautelares, síntese |
| **Embedding** | `text-embedding-004` | — | Baixo | Vetores Qdrant (sem mudança) |

> **Econômico anterior:** `gpt-4.1-nano` (OpenAI) a $0.10/$0.40 → substituído por `gemini-1.5-flash-8b` a $0.038/$0.15 = **economia de ~2.5×**

---

## Checklist de Execução Ordenada

```
[x] Passo 1 — Verificações pré-trabalho (sem código)
[x] Passo 2 — Editar config.py
[x] Passo 3 — Refatorar llm_service.py
[x] Passo 4 — (Opcional) Ampliar limites de contexto
[x] Passo 5 — Push e deploy Railway
[x] Passo 6 — Limpar variáveis de ambiente obsoletas
[ ] Passo 7 — Validação funcional
```

---

## Passo 1 — Verificações Pré-Trabalho (sem mudança de código)

Confirmar as três premissas do plano antes de qualquer edição:

```bash
# 1. Confirmar que openai nunca aparece no código Python
grep -r "import openai\|from openai" backend/
# Resultado esperado: zero linhas

# 2. Confirmar que openai está ausente dos requirements
grep "openai" backend/requirements.txt
# Resultado esperado: zero linhas

# 3. Confirmar que google-genai está nos requirements
grep "google-genai" backend/requirements.txt
# Resultado esperado: google-genai>=1.0.0
```

---

## Passo 2 — Editar `backend/app/core/config.py`

### Campos a alterar (valores default, os nomes das env vars permanecem iguais):

| Campo | Valor Atual | Novo Valor |
|-------|-------------|-----------|
| `LLM_ECONOMICO_PROVIDER` | `"openai"` | `"google"` |
| `LLM_ECONOMICO_MODEL` | `"gpt-4.1-nano"` | `"gemini-1.5-flash-8b"` |
| `LLM_ECONOMICO_BASE_URL` | `"https://api.openai.com/v1"` | `"https://generativelanguage.googleapis.com"` |
| `LLM_STANDARD_MODEL` | `"gemini-2.0-flash"` | `"gemini-1.5-flash"` |
| `LLM_PREMIUM_MODEL` | `"gemini-2.0-flash"` | `"gemini-1.5-pro"` |

### Campo a adicionar:

```python
LLM_ECONOMICO_TEMPERATURE: float = 0.1  # Conforme diretriz: consistência no econômico
```

### Campo deprecado (manter por 1 sprint para evitar crash no Railway se ainda estiver setado):

```python
OPENAI_API_KEY: Optional[str] = None  # Deprecated — migrado para Gemini
```

---

## Passo 3 — Refatorar `backend/app/services/llm_service.py`

### 3a — Remover o caminho httpx/OpenAI

Deletar inteiramente o bloco de código que constrói a chamada HTTP para `api.openai.com` (linhas ~95–155). Este é o trecho acionado quando `provider != "google"`.

Remover também o `import httpx` (não é usado em mais nenhum lugar do arquivo).

### 3b — Simplificar `__init__`

Após a mudança, o construtor precisa apenas de:

```python
def __init__(self):
    if not settings.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY é obrigatório — todos os tiers LLM agora usam Google Gemini"
        )
    self._genai_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    self.eco_model     = settings.LLM_ECONOMICO_MODEL    # gemini-1.5-flash-8b
    self.std_model     = settings.LLM_STANDARD_MODEL     # gemini-1.5-flash
    self.premium_model = settings.LLM_PREMIUM_MODEL      # gemini-1.5-pro
```

Remover campos `base_url`, `api_key` por tier — não mais necessários.

### 3c — Simplificar o dispatch em `chat_completion`

```python
async def chat_completion(self, messages, tier="premium",
                          temperature=0.3, max_tokens=2000, json_mode=False):
    if tier == "economico":
        model = self.eco_model
        temperature = settings.LLM_ECONOMICO_TEMPERATURE  # 0.1
    elif tier == "standard":
        model = self.std_model
    else:  # "premium"
        model = self.premium_model

    return await self._gemini_completion(messages, model, temperature, max_tokens, json_mode)
```

Sem branching de provider. Sem httpx. Todos os tiers → `_gemini_completion`.

### 3d — Atualizar tabela de custos `_estimar_custo`

```python
precos = {
    "gemini-1.5-flash-8b": {"in": 0.0375, "out": 0.15},   # econômico
    "gemini-1.5-flash":    {"in": 0.075,  "out": 0.30},   # standard/vision
    "gemini-1.5-pro":      {"in": 1.25,   "out": 5.00},   # premium
    "gemini-2.0-flash":    {"in": 0.10,   "out": 0.40},   # manter por período de transição
    "text-embedding-004":  {"in": 0.00,   "out": 0.00},   # embedding gratuito no tier atual
}
# Remover: gpt-4o-mini, gpt-4o, deepseek-chat, claude-3-5-sonnet (código morto)
```

---

## Passo 4 — Aproveitamento da Janela Longa (Opcional, mesma sprint)

### 4a — `orchestrator_service.py` — Ampliar truncamento

```python
# Antes: texto_curto = texto_extraido[:40000]
# Depois:
MAX_CHARS_ORQUESTRACAO = 500_000  # ~125k tokens — dentro da janela 1M do standard/pro
texto_analisado = texto_extraido[:MAX_CHARS_ORQUESTRACAO]
```

### 4b — `summary_service.py` — Ampliar limites de resumo

Os limites atuais foram definidos com as restrições do GPT. Com flash-8b (1M tokens):

```python
MAX_CHARS_DOCUMENTO = 50_000   # era 25_000
MAX_CHARS_VOLUME    = 40_000   # era 20_000
MAX_CHARS_CASO      = 30_000   # era 15_000
```

### 4c — `copiloto_service.py` — Aumentar chunks RAG

Com Gemini 1.5 Pro no premium, o limite de contexto deixa de ser um obstáculo:

```python
max_chunks = 12  # era 8 — mais contexto para respostas mais completas
```

---

## Passo 5 — Deploy Railway

```bash
git add backend/app/core/config.py backend/app/services/llm_service.py
git commit -m "feat(llm): migra tier econômico para gemini-1.5-flash-8b, remove dependência OpenAI/httpx"
git push
```

O Railway fará o redeploy automaticamente.

> **Nota crítica de rollback:** Este commit é o ponto de rollback. Se necessário reverter:
> ```bash
> git revert <hash>
> git push
> ```
> OU (rollback instantâneo via env vars, sem redeploy de código):
> ```
> LLM_ECONOMICO_PROVIDER=openai
> LLM_ECONOMICO_MODEL=gpt-4.1-nano
> LLM_ECONOMICO_BASE_URL=https://api.openai.com/v1
> LLM_ECONOMICO_API_KEY=<chave-openai>
> ```
> *Disponível apenas se o caminho httpx NÃO for removido no Passo 3a — recomenda-se remover httpx apenas após validação bem-sucedida.*

---

## Passo 6 — Variáveis de Ambiente no Railway

### Verificar se já existem / confirmar valores:

```
GEMINI_API_KEY=<chave-google-ai-studio>   ← OBRIGATÓRIO (provavelmente já existe)
```

### Variáveis opcionais (só necessárias se quiser sobrescrever os defaults do config.py):

```
LLM_ECONOMICO_PROVIDER=google
LLM_ECONOMICO_MODEL=gemini-1.5-flash-8b
LLM_STANDARD_MODEL=gemini-1.5-flash
LLM_PREMIUM_MODEL=gemini-1.5-pro
```

### Variáveis a remover (após deploy bem-sucedido):

```
LLM_ECONOMICO_API_KEY   ← era a chave OpenAI para o tier econômico
OPENAI_API_KEY          ← se existir apenas no serviço backend
```

### Variáveis a MANTER (segurança):

```
DEEPSEEK_API_KEY        ← manter para eventual fallback futuro
GEMINI_API_KEY          ← continuidade (sem mudança)
```

---

## Passo 7 — Checklist de Validação Funcional

Após o deploy, testar cada tier manualmente:

```
[ ] Tier Econômico — NER
    Upload PDF de teste → verificar nos logs: extração de pessoas/empresas
    Log esperado: [LLM-Gemini] model=gemini-1.5-flash-8b

[ ] Tier Econômico — Resumo
    Verificar que ResumoCache é populado após ingestão
    Log esperado: [LLM-Gemini] model=gemini-1.5-flash-8b

[ ] Tier Standard — Orquestração
    Upload novo inquérito → verificar que número IP é extraído
    Log esperado: [LLM-Gemini] model=gemini-1.5-flash

[ ] Tier Premium — Copiloto
    Abrir inquérito → fazer pergunta ao copiloto → resposta com citações
    Log esperado: [LLM-Gemini] model=gemini-1.5-pro

[ ] Tier Vision — Intimação
    Upload intimação PDF/imagem → verificar extração de nome e data
    (modelo já era Gemini, sem mudança)

[ ] Verificar ausência de erros:
    - Nenhum "httpx.ConnectError" nos logs
    - Nenhum "AttributeError: 'NoneType'" nos logs
    - Nenhum "OPENAI_API_KEY" nos logs
```

---

## Gestão de Orçamento — Projeção R$250/mês

| Workload | Tier | Modelo Antigo | Custo Antigo | Modelo Novo | Custo Novo | Δ |
|----------|------|---------------|--------------|-------------|-----------|---|
| NER + Classificação (em massa) | Econômico | gpt-4.1-nano | $0.10/1M | gemini-1.5-flash-8b | $0.04/1M | **-60%** |
| Resumos 4 níveis | Econômico | gpt-4.1-nano | $0.10/1M | gemini-1.5-flash-8b | $0.04/1M | **-60%** |
| Análise extrato | Standard | gemini-2.0-flash | $0.10/1M | gemini-1.5-flash | $0.08/1M | -20% |
| Copiloto + Fichas | Premium | gemini-2.0-flash | $0.10/1M | gemini-1.5-pro | $1.25/1M | **+1150%** |
| Cautelares + Síntese | Premium | gemini-2.0-flash | $0.10/1M | gemini-1.5-pro | $1.25/1M | **+1150%** |

> **Atenção:** O tier Premium tem aumento significativo de custo. A economia no econômico (bulk) subsidia o uso controlado do Pro. **Monitorar mensalmente o dashboard do Google AI Studio.** O equilíbrio se mantém desde que o volume de chamadas Premium seja proporcional ao investigativo (não mecânico).

---

## Revisão de Compatibilidade de Prompts

Nenhum prompt precisa ser reescrito como pré-requisito. Observações de QA:

| Prompt | Tier | Observação |
|--------|------|------------|
| `SYSTEM_PROMPT_ORQUESTRADOR` | Standard | Flash é mais veloz, Pro seria excessivo aqui |
| `SYSTEM_PROMPT_COPILOTO` | Premium | Pro 1.5 é mais verboso que Flash 2.0 — respostas mais ricas |
| `SYSTEM_PROMPT_AUDITORIA_FACTUAL` | Econômico | Flash-lite pode ser menos estruturado em JSON complexo — monitorar |
| `PROMPT_FICHA_PESSOA` | Premium | Pro 1.5 aproveita melhor os dados longos de OSINT |
| `PROMPT_CAUTELAR` | Premium | Pro 1.5 produz linguagem jurídica mais rigorosa |
| `SYSTEM_PROMPT_EXTRACAO_ENTIDADES` | Econômico | Flash-lite com json_mode=True é confiável — testado |

---

## Arquivos Críticos para Implementação

| Arquivo | Mudança | Prioridade |
|---------|---------|------------|
| [backend/app/core/config.py](../backend/app/core/config.py) | Alterar 5 defaults + adicionar `LLM_ECONOMICO_TEMPERATURE` | **Bloqueante** |
| [backend/app/services/llm_service.py](../backend/app/services/llm_service.py) | Remover httpx path, simplificar dispatch, startup guard, tabela de custos | **Bloqueante** |
| [backend/app/services/summary_service.py](../backend/app/services/summary_service.py) | Ampliar `MAX_CHARS_*` (melhoria de qualidade) | Opcional |
| [backend/app/services/orchestrator_service.py](../backend/app/services/orchestrator_service.py) | Ampliar truncamento de 40k → 500k chars | Opcional |
| [backend/app/services/copiloto_service.py](../backend/app/services/copiloto_service.py) | Aumentar `max_chunks` de 8 → 12 | Opcional |
| Railway Dashboard | Confirmar `GEMINI_API_KEY`, remover `LLM_ECONOMICO_API_KEY` | Pós-deploy |

---

*Plano gerado em 2026-04-04 com base na análise do código-fonte e na Diretriz de Reestruturação assinada por Valdir.*
