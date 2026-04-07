# Análise Custo × Benefício — Modelos LLM do Escrivão AI

**Data:** 20/03/2026
**Contexto:** O sistema usa 3 tiers de LLM configuráveis via `.env`. Esta análise mapeia cada agente, avalia a adequação do modelo atual e propõe ajustes.

---

## Tiers configurados hoje

| Tier | Modelo atual | Preço in / out (USD/1M tokens) |
|---|---|---|
| `economico` | `gpt-4.1-nano` | $0,10 / $0,40 |
| `standard` | `gemini-1.5-flash` | $0,075 / $0,30 |
| `premium` | `gemini-pro-latest` | ~$1,25 / $5,00 |

> Flash é **mais barato que nano** por token. O tier econômico e o standard estão trocados em custo — mas cada um tem provider diferente (OpenAI vs Google), o que mantém a separação por resiliência.

---

## Mapa completo de chamadas LLM

| Agente / Tarefa | Arquivo | Tier atual | Input típico | Output | Complexidade real |
|---|---|---|---|---|---|
| Classificar tipo de peça | `extractor_service.py` | **standard** (Flash) | ~15k chars | **1 palavra** | ⬛ Mínima |
| Extrair entidades (NER) | `extractor_service.py` | standard (Flash) | ~30k chars | JSON médio | 🟧 Moderada |
| Resumo de página (3 linhas) | `summary_service.py` | economico (nano) | ~1k chars | 3 linhas | ⬛ Mínima |
| Resumo de documento (10 linhas) | `summary_service.py` | economico (nano) | ~40k chars | 10 linhas | 🟩 Baixa |
| Resumo de volume | `summary_service.py` | economico (nano) | variável | 15 linhas | 🟩 Baixa |
| **Resumo executivo do caso** | `summary_service.py` | economico (nano) | variável | 20 linhas | 🟧 Moderada |
| **Análise extrato bancário** | `agente_extrato.py` | economico (nano) | ~40k chars | JSON longo | 🟥 Alta |
| **Copiloto — chat RAG** | `copiloto_service.py` | economico (nano) | 8 chunks + histórico | texto livre | 🟥 Alta |
| Copiloto — auditoria factual | `copiloto_service.py` | economico (nano) | resposta + chunks | JSON simples | 🟩 Baixa |
| **Orquestrador — análise inicial** | `orchestrator_service.py` | **premium** (Pro) | ~40k chars | JSON médio | 🟧 Moderada |
| **Orquestrador — relatório boas-vindas** | `orchestrator_service.py` | **premium** (Pro) | contexto | texto livre | 🟩 Baixa |
| **Ficha pessoa** | `agente_ficha.py` | **premium** (Pro) | dados + OSINT | JSON longo | 🟥 Alta |
| **Ficha empresa** | `agente_ficha.py` | **premium** (Pro) | dados + OSINT | JSON longo | 🟥 Alta |
| **Minuta cautelar / ofício** | `agente_cautelar.py` | **premium** (Pro) | contexto + instrução | texto formal legal | 🔴 Crítica |

---

## Diagnóstico: o que está errado

### Sobre-dimensionado (premium onde não precisa)

**Orquestrador — análise inicial** usa premium para extrair JSON estruturado (pessoas, empresas, cronologia) dos primeiros documentos. Esta é exatamente a tarefa em que Flash 2.0 performa igual ao Pro — estruturação de JSON a partir de texto extenso. **Custo: ~17× acima do necessário.**

**Orquestrador — relatório de boas-vindas** usa premium para gerar um texto descritivo simples ("Bem-vindo ao inquérito X, foram identificadas Y pessoas..."). Flash faz isso com qualidade idêntica. **Custo: ~17× acima do necessário.**

### Sub-dimensionado (economico onde não serve)

**Copiloto — chat RAG** usa nano para responder perguntas investigativas do delegado. Esta é a principal interface de uso do sistema. Qualidade de resposta, raciocínio jurídico, citação correta de fontes — tudo sofre com o modelo mais fraco. É o lugar **errado** para economizar.

**Análise de extrato bancário** usa nano para detectar padrões suspeitos, calcular médias, identificar contrapartes recorrentes e emitir score de suspeição em JSON. Nano erra padrões numéricos e perde detalhes em textos longos de 40k chars. Resultado: análise rasa.

**Resumo executivo do caso** usa nano para o relatório final do inquérito — o documento que o delegado lê para entender o caso. Nano produz texto genérico. Flash produz síntese investigativa real.

### Corretamente dimensionado

**Classificar tipo de peça** usa Flash para responder UMA palavra ("boletim_ocorrencia", "portaria"...). Flash é caro demais para isso. Nano basta.

**NER (extrair entidades)** usa Flash para extrair CPF, nomes, endereços do texto OCR. Correto — OCR pode ser ruidoso e Flash é mais robusto para parsing desestruturado.

**Resumos de página e documento** usam nano. Correto — são tarefas simples de compactação.

**Auditoria factual** usa nano para comparar resposta com chunks. Correto — é essencialmente uma tarefa de matching.

**Minuta cautelar** usa premium. **Correto e inegociável** — documentos legais com citações de artigos (CPP, CP, Lei X) têm consequência jurídica real. Erros custam mais que o modelo.

---

## Recomendações de mudança

| Agente | Atual | Proposto | Justificativa | Impacto |
|---|---|---|---|---|
| Classificar tipo de peça | standard | **economico** | 1 palavra de lista fixa — nano performa igual | ↓ custo |
| Resumo executivo do caso | economico | **standard** | Síntese de inquérito inteiro — Flash produz análise muito melhor | ↑ qualidade |
| Análise extrato bancário | economico | **standard** | Detecção de padrões financeiros suspeitos requer raciocínio | ↑ qualidade |
| Copiloto — chat RAG | economico | **standard** | Interface principal do sistema. Não economize aqui | ↑ qualidade crítica |
| Orquestrador — análise inicial | premium | **standard** | Extração de JSON estruturado — Flash é equivalente | ↓ custo 90% |
| Orquestrador — relatório | premium | **standard** | Texto descritivo simples | ↓ custo 90% |
| Ficha pessoa / empresa | premium | **standard** | Flash 2025 produz fichas JSON excelentes. Testar antes de confirmar | ↓ custo 90% |
| Minuta cautelar | premium | **premium** | Manter — documento legal com impacto jurídico real | — |

---

## Impacto financeiro estimado

Assumindo um inquérito médio com 50 documentos, 5 fichas, 10 sessões do copiloto:

| Mudança | Saving estimado por inquérito |
|---|---|
| Orquestrador → Flash | ~$0,04 (pequeno, poucas chamadas) |
| Ficha → Flash (×5) | ~$0,25 por inquérito |
| Copiloto → Flash (×10 sessões) | custo levemente maior, mas **qualidade compensa** |
| Classificação → nano (×50 docs) | ~$0,005 (micro) |

> O maior ganho financeiro é mover ficha + orquestrador para Flash.
> O maior ganho de qualidade é mover copiloto para Flash.
> Nenhum deles sacrifica resultado — Flash em 2025 é capaz para todas essas tarefas.

---

## Plano de implementação

Todas as mudanças são em 1 linha de código cada — basta trocar `tier=`:

```python
# extractor_service.py — classificar_documento
tier="economico"   # era "standard"

# summary_service.py — resumir_caso
tier="standard"    # era "economico"

# agente_extrato.py — analisar_extrato
tier="standard"    # era "economico"

# copiloto_service.py — chat RAG
tier="standard"    # era "economico"

# orchestrator_service.py — analisar_documentos_iniciais
tier="standard"    # era "premium"

# orchestrator_service.py — gerar_relatorio_contextualizado
tier="standard"    # era "premium"

# agente_ficha.py — gerar_ficha_pessoa e gerar_ficha_empresa
tier="standard"    # era "premium" — TESTAR antes de confirmar em prod
```

> **Recomendação**: aplicar tudo exceto ficha em prod imediatamente.
> Para ficha: testar 3-5 fichas com Flash, comparar saída com Pro, depois decidir.

---

## Contexto de modelos alternativos a considerar

Se quiser trocar o tier standard para algo ainda melhor custo/benefício:

| Modelo | Preço | Contexto | Para usar em |
|---|---|---|---|
| `gemini-2.0-flash` | $0,10/$0,40 | 1M tokens | Standard geral — melhor que 1.5-flash |
| `gemini-2.5-flash` | $0,15/$0,60 | 1M tokens | Raciocínio embutido — excelente para extrato+ficha |
| `gemini-2.0-flash-lite` | $0,075/$0,30 | 1M tokens | Economico alternativo para classificação |
| `gpt-4.1-mini` | $0,40/$1,60 | 1M tokens | Standard OpenAI se quiser manter provider |

> Sugestão: substituir `gemini-1.5-flash` → `gemini-2.0-flash` no tier standard. Custo similar, capacidade muito superior. Apenas trocar a variável de ambiente `LLM_STANDARD_MODEL`.
