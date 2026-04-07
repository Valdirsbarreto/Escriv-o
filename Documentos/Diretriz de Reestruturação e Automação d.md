Diretriz de Reestruturação e Automação de Agentes — Projeto Escrivão AI (Antigravity)
Data: 04 de Abril de 2026
Responsável: Valdir (Retired Police Commissioner / Lead Developer)
Assunto: Migração Integral para o Ecossistema Google Gemini e Otimização de Tiers


1. Objetivo
Este documento formaliza a decisão estratégica de consolidar toda a inteligência artificial do sistema Antigravity (Escrivão AI) sob a infraestrutura do Google AI Studio (Gemini). O objetivo é eliminar a dependência de LLMs externas (OpenAI), otimizar o consumo e maximizar a capacidade de análise de grandes fluxos de documentos descontinuados.
2. Alterações de Tiers e Modelos
Fica determinado que o sistema deve ser reconfigurado conforme a tabela de distribuição abaixo:
2.1 Tier Econômico (Substituição do GPT-4.1 Nano)
Modelo Destinado: gemini-1.5-flash-lite
Funções:
Classificação de peças processuais (ExtractorService.classificar_documento).
Extração de Entidades (NER).
Geração de resumos de todos os níveis (Página, Documento, Volume e Caso).
Configuração de Parâmetros: temperature: 0.1 (foco em consistência).
2.2 Tier Standard e Vision
Modelo Destinado: gemini-1.5-flash
Funções:
Análise estruturada de extratos bancários.
Processamento de OCR para intimações e documentos manuscritos.
Processamento de imagens (VisionService).
2.3 Tier Premium (O "Cérebro" Investigativo)
Modelo Destinado: gemini-1.5-pro
Funções:
Copiloto RAG: Respostas com citações diretas das páginas do inquérito.
Auditoria Factual: Verificação cruzada para evitar alucinações.
Síntese Investigativa: Elaboração de relatórios complexos de 10 seções (investigação financeira e técnica).


3. Diretrizes Técnicas para Documentos Descontinuados
Para combater a desordem documental e tentativas de ocultação de provas, o sistema deverá:

Explorar o Contexto Longo: Utilizar a janela de até 2 milhões de tokens do Gemini 1.5 Pro para processar volumes inteiros de uma única vez, garantindo a correlação de fatos distantes entre si.
Reforço no RAG: Manter a integração com o banco vetorial Qdrant utilizando o modelo text-embedding-004 (Google), assegurando que o raciocínio seja baseado em busca semântica e não apenas na ordem física das páginas.
Output Estruturado: Priorizar o uso do json_mode para garantir que os dados extraídos possam ser auditados de forma tabular.
4. Gestão Financeira e Limites
As alterações devem respeitar o limite de faturamento atual de R$ 250,00 (Nível 1 de faturamento do Google AI Studio). A migração para o flash-lite no processamento em massa visa reduzir o custo operacional, permitindo maior uso do modelo Pro em análises críticas sem exceder o teto orçamentário.



Assinado,

Valdir Coordenador do Projeto Escrivão AI / Antigravity