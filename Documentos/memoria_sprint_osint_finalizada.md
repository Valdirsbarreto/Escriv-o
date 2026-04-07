# Memória da Sprint OSINT (Concluída)

## 1. Persistência de Docs Gerados na Área de Trabalho (RESOLVIDO)
- **Problema:** Fichas OSINT geradas apenas "em tela" evaporavam, ficando à margem do Inquérito.
- **Solução:** Implementada a injeção do arquivo em `agente_ficha.py`. Fichas OSINT (Pessoa e Empresa) agora são compiladas via markdown (`DocumentoGerado` / Relatório) e caem no ato na "Área de Trabalho > Documentos Gerados pela IA" e atreladas permanentemente no banco ao `inquerito_id`.

## 2. Refatoração UI/UX: Abordagem Modular "A La Carte"
- **Problema:** O método antigo "Perfis P1 a P4" obrigava ao consumo aglomerado de APIs, impedindo o controle fino do custo.
- **Solução:**
  - Substituição do `select` genérico por um grupo de **Checkboxes** granulares em `src/app/agentes/osint/page.tsx` (`OSINT_MODULOS`).
  - Adição de novos endpoints da DirectData (`VinculoEmpregaticio`, `BPC`, `Processos Judiciais`) em `directdata_service.py` visando extrair alvos ocultos nas esferas CLT / Assistencial.
  - Refatoração total do endpoint `/agentes/osint/lote` para aceitar `modulos: List[str]` ao invés do primitivo `perfil: int`.
  - O Custo agora aparece em tempo real no dashboard, totalizando apuramentos precisos de frações de centavos da DirectData.

## 3. Inteligência na Consulta Avulsa
- **Problema:** Usuário pesquisa um CPF/Placa e os resultados são frios.
- **Solução:** O endpoint Avulso agora consulta ativamente `buscar_historico_pessoa` (`copiloto_osint_service.py`).
- **Comportamento:** Ao bater um documento já fichado em outra gaveta, aparece um **[ALERTA DE CRUZAMENTO]** na interface avulsa listando em quais Inquéritos e sob o chapéu de qual perfil (Testemunha, Oculto, Investigado) o alvo já operou no passado.

## 4. Chat Copiloto com Tool Calling (Function Loop)
- **Problema:** Copiloto respondia que não tinha acesso OSINT quando instado em live chat.
- **Solução:** Modificação do `system_prompt_copiloto` instruindo o LLM a cuspir a tag `<OSINT_CALL>{"cpf": "..."}</OSINT_CALL>` caso solicitado.
- Adicionado Loop Agêntico no `copiloto_service.py`: Se LLM cospe a Tag, o pipeline do backend capta na Regex, estanca a comunicação, invoca o micro-serviço da `directdata` e devolve a capivara externa integral na "boca" do LLM. O LLM mastiga isso e joga pro Delegado um texto espetacular com as respostas que ele pediu. Funciona com Gemini e LLaMA.

Tudo implementado, estabilizado e repassado para a interface OSINT do Escrivão. Prontos para rodar bateria de test-drive.

## 5. Nova Feature B�nus: Arquitetura de Jurisprud�ncia e Faro Investigativo
- Criado plano_banco_jurisprudencia_IA.md com arquitetura completa.
- Adicionado suporte nativo no qdrant_service.py para a collection casos_historicos.
- Criado script de minera��o/anonimiza��o PoC ackend/scripts/ingest_casos_historicos.py integrado com Gemini 1.5 Flash para RAG de casos judiciais de sucesso.

