# Contexto do Projeto — Escrivão AI

Leia o arquivo `CLAUDE.md` na raiz do projeto — ele contém todo o contexto necessário para esta sessão, incluindo:

- Stack completa e tecnologias utilizadas
- Pipeline de ingestão → relatório (quais agentes e LLMs participam de cada etapa)
- Mapa de tiers LLM
- Bugs corrigidos em 2026-04-12 e 2026-04-13 e suas causas raiz
- Diretrizes do prompt mestre para o Relatório Inicial (v3 — Analista de Inteligência Criminal Multidomínio)
- Arquitetura de contexto do Copiloto (o que é injetado e em que ordem)
- Restrições críticas de arquitetura (Railway, Celery, Gemini SDK, etc.)
- Pendências abertas
- Mapa de arquivos-chave do projeto

## Estado atual do sistema (2026-04-13)

O sistema está **100% migrado para Google Gemini**. Groq foi removido de todos os tiers.

### Commits recentes (branch main)
- `17840e0` — Fix: campo Fato preenchido só pelo Relatório Inicial + remove auto-save Copiloto
- `33a0ca9` — Fix: remove sintese_investigativa de TIPOS_COMPLETOS no Copiloto
- `b64bc98` — Feat: injeta índice de peças dos autos no contexto do Copiloto
- `ec63cac` — Feat: Copiloto entende referências processuais do usuário ("foi relatado", "MP pediu")
- `33a9142` — Fix: relatorio_inicial injetado sem truncar no Copiloto
- `0a4b4d0` — Feat: PROMPT_RELATORIO_INICIAL v3 + contexto 2.8M chars

### Próximos passos pendentes
1. **Regenerar Síntese do IP 911-00209/2019** — síntese ainda tem conteúdo do contexto antigo:
   `POST /inqueritos/c38991d7-e669-435e-b54e-64df6ed6c429/gerar-sintese`
2. **Lote de relatórios iniciais** nos demais inquéritos:
   `POST /ingestao/admin/gerar-relatorio-inicial-lote?forcar=false`
3. **Testar Copiloto** com contexto limpo (sínteses ruins foram deletadas manualmente)
4. **OSINT Web (Serper.dev)** — plano em `reflective-meandering-sky.md`, ainda não implementado
5. **Alembic migration `j0k1l2m3n4o5`** — remap tipos de peças no Railway
