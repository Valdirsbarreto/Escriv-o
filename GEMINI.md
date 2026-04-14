# Contexto do Projeto — Escrivão AI

Leia o arquivo `CLAUDE.md` na raiz do projeto — ele contém todo o contexto necessário para esta sessão, incluindo:

- Stack completa e tecnologias utilizadas
- Pipeline de ingestão → relatório (quais agentes e LLMs participam de cada etapa)
- Mapa de tiers LLM
- Fases processuais do IP (Instauração → Instrução → Indiciamento → Relatamento → Fase Externa)
- Bugs corrigidos em 2026-04-12 e 2026-04-13 e suas causas raiz
- Diretrizes do prompt mestre para o Relatório Inicial (v3 — Analista de Inteligência Criminal Multidomínio)
- Prompt do Relatório Complementar (novo — quando MP devolve IP para diligências)
- Arquitetura de contexto do Copiloto (o que é injetado e em que ordem)
- Restrições críticas de arquitetura (Railway, Celery, Gemini SDK, etc.)
- Pendências abertas
- Mapa de arquivos-chave do projeto

## Estado atual do sistema (2026-04-13 — continuação)

O sistema está **100% migrado para Google Gemini**. Groq foi removido de todos os tiers.

### Commits recentes (branch main)
- `1cc8fc9` — Refactor: SYSTEM_PROMPT_COPILOTO — 6 diretrizes formais de comportamento
- `e7ff0e6` — Fix: escape `{{}}` em SYSTEM_PROMPT — crash "Replacement index 0 out of range"
- `85fdc49` — Fix: Copiloto não executa ações sem pedido explícito
- `5ad5bde` — Fix: Copiloto max_tokens 4k→8k + ferramenta <RELATORIO_COMPLEMENTAR_CALL>
- `487a479` — Feat: fases processuais do IP nos prompts + botão Rel. Complementar na UI
- `1b81d5c` — Feat: Relatório Complementar — task Celery, prompt e endpoint

### Próximos passos pendentes
1. **Validar Relatório Complementar** no IP 911-00209/2019 — PRÓXIMA AÇÃO:
   - Botão "Gerar Rel. Complementar" na aba Workspace (caminho direto)
   - Via Copiloto: pedir "faz o relatório complementar" (valida a ferramenta)
   - Se falhar: checar `tipo_peca` da Cota Ministerial nos docs do IP
2. **Regenerar Síntese do IP 911-00209/2019**:
   `POST /inqueritos/c38991d7-e669-435e-b54e-64df6ed6c429/gerar-sintese`
3. **Lote de relatórios iniciais** nos demais inquéritos:
   `POST /ingestao/admin/gerar-relatorio-inicial-lote?forcar=false`
4. **Alembic migration `j0k1l2m3n4o5`** — remap tipos de peças no Railway
5. **OSINT Web (Serper.dev)** — plano em `reflective-meandering-sky.md`, ainda não implementado
