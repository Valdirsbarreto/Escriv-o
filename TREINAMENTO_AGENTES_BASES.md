# Bases de Conhecimento Oficiais para Treinamento RAG (Escrivão AI)

Lista organizada e curada de documentos públicos (.gov.br), manuais e leis para alimentar a base de dados especialista (RAG) da IA Investigativa.

## 1. Leis Fundamentais
- **Código Penal (Dec.-Lei 2.848/1940):** https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm
- **Código de Processo Penal (Dec.-Lei 3.689/1941):** https://www.planalto.gov.br/ccivil_03/decreto-lei/del3689.htm
- **Lei de Lavagem de Dinheiro (9.613/1998):** https://www.planalto.gov.br/ccivil_03/leis/l9613.htm
- **Marco Legal das Criptomoedas (Lei 14.478/2022):** https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/lei/l14478.htm
- **Nova Lei de Licitações e Contratos (14.133/2021):** https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm
- **Lei Anticorrupção (12.846/2013):** https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2013/lei/l12846.htm
- **Pacote Anticrime (Lei 13.964/2019):** https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2019/lei/l13964.htm

## 2. Manuais e POPs (SENASP / PF)
- **Procedimento Operacional Padrão – Perícia Criminal (2013):** https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/seguranca-publica/analise-e-pesquisa/download/pop/procedimento_operacional_padrao-pericia_criminal.pdf
- **Relatório Final Cadeia de Custódia:** https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/seguranca-publica/cadeia-de-custodia-1/relatorio_final_compilado_publicacao.pdf
- **Metodologia Padronizada de Investigação Criminal Nacional:** https://dspace.mj.gov.br/bitstream/1/3838/1/26metodologia-padronizada-de-investigacao-criminal-nacional.pdf
- **Investigação de Homicídios (Mingardi):** https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/seguranca-publica/analise-e-pesquisa/download/estudos/sjcvolume3/investigacao_homicidios_construcao_modelo.pdf
- **IN PF nº 255/2023:** https://www.gov.br/mj/pt-br/acesso-a-informacao/acoes-e-programas/recupera/instrucao_normativa___in_34963175_in_255_2023___regulamenta_as_atividades_de_policia_judiciaria_da_pf.pdf
- **IN DG/PF nº 270/2023 (Competências DICOR, DRLD):** https://www.gov.br/pf/pt-br/acesso-a-informacao/institucional/perfil-profissional/in_270_2023___competencia_das_unidades_e_atribuicoes_dos_dirigentes___atualizada.pdf
- **Técnicas Avançadas de Investigação V2 (ESMPU/MPU):** https://www.mpsp.mp.br/portal/page/portal/documentacao_e_divulgacao/doc_biblioteca/bibli_servicos_produtos/BibliotecaDigital/BibDigitalLivros/TodosOsLivros/Tecnicas-avancadas-de-investigacao-v.2.pdf

## 3. Investigação Econômico-Financeira e Lavagem (COAF/ENCCLA)
- **Cartilha COAF – Lavagem de Dinheiro:** https://www.gov.br/coaf/pt-br/centrais-de-conteudo/publicacoes/publicacoes-do-coaf-1/cartilha-lavagem-de-dinheiro-um-problema-mundial.pdf
- **ENCCLA 2025 – Manual do Participante:** https://www.gov.br/mj/pt-br/assuntos/sua-protecao/lavagem-de-dinheiro/enccla/enccla-2025-manual-do-participante.pdf
- **Casos e Casos – Tipologias LD (COAF 2021):** https://www.gov.br/coaf/pt-br/centrais-de-conteudo/publicacoes/avaliacao-nacional-de-riscos/casos-e-casos-tipologias-edicao-especial-anr-2021.pdf
- **100 Casos de Lavagem de Dinheiro (Egmont/COAF):** https://www.gov.br/fazenda/pt-br/central-de-conteudo/publicacoes/casos-casos/arquivos/100-casos-de-lavagem-de-dinheiro.pdf

## 4. Criptomoedas e Ativos Virtuais
- **Resolução BCB nº 520/2025 (Prestadoras de Serviços):** https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Resolu%C3%A7%C3%A3o%20BCB&numero=520
- **Decreto 11.563/2023:** https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/decreto/d11563.htm

## 5. Corrupção e Licitações
- **Guia de Padronização (Contratação):** https://www.gov.br/compras/pt-br/acesso-a-informacao/manuais/manual-fase-interna/guia-de-padronizacao-dos-procedimentos-de-contratacao.pdf
- **Manual de Integração PNCP:** https://www.gov.br/pncp/pt-br/central-de-conteudo/manuais/versoes-anteriores/ManualdeIntegraoPNCPVerso2.2.1.pdf
- **Manual de Boas Práticas (Governança):** https://www.gov.br/compras/pt-br/acesso-a-informacao/manuais/manual-governanca-nas-contratacoes/manual-de-boas-praticas-em-contratacoes-publicas.pdf

---
**Estratégia de Ingestão Futura:**
Esses manuais não devem ser misturados com os autos do inquérito (tenant). Devem ser ingeridos no **Qdrant** sob uma *collection* apartada chamada `escrivao_conhecimento` para que o Agente Relator possa consultar doutrina e jurisprudência em tempo real e aplicar tipologias criminais validadas nos fatos extraídos dos autos.
