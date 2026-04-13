# Contexto do Projeto — Escrivão AI

Leia o arquivo `CLAUDE.md` na raiz do projeto — ele contém todo o contexto necessário para esta sessão, incluindo:

- Stack completa e tecnologias utilizadas
- Pipeline de ingestão → relatório (quais agentes e LLMs participam de cada etapa)
- Mapa de tiers LLM (triagem / extracao / resumo / standard / premium)
- Bugs corrigidos em 2026-04-12 e suas causas raiz
- Diretrizes do prompt mestre para o Relatório Inicial (Analista de Inteligência Criminal Multidomínio)
- Restrições críticas de arquitetura (Railway, Celery, Gemini SDK, etc.)
- Mapa de arquivos-chave do projeto

## Estado atual do sistema (2026-04-12)

O sistema está **100% migrado para Google Gemini**. Groq foi removido de todos os tiers.

### Commits recentes (branch main)
- `eb31a98` — Valida output da auditoria antes de substituir rascunho; remove bloco AUDITORIA FACTUAL do doc salvo
- `6a8ebb1` — Expande contexto de 12k para 400k chars (relatório) e 300k chars (auditoria)
- `b58a932` — Roda alembic upgrade head automaticamente no startup do worker
- `3a79129` — **Hotfix:** adiciona `from typing import Optional` + `Float`, `Integer` em `documento_gerado.py`
- `f2872e9` — Resolve TypeError, adiciona colunas IA no modelo, endpoint alias `/documentos-gerados`

### Próximos passos pendentes
1. **Melhorar prompt `PROMPT_RELATORIO_INICIAL`** para seguir estrutura de Analista de Inteligência Criminal Multidomínio (materialidade, autoria/vínculos, cronologia)
2. **Aumentar contexto** para inquéritos grandes: considerar passar `texto_extraido` direto além dos resumos para atingir 500k-700k tokens no Gemini 1.5 Pro
3. **Validar relatório** gerado após os fixes de hoje com o inquérito 911-00209/2019
4. **Task `gerar_relatorio_inicial_task`** — se o relatório gerado ainda não tiver suspeitos mesmo com quebras de sigilo nos autos, o problema é o prompt, não o pipeline
