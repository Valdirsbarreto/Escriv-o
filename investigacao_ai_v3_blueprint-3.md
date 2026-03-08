# Investigação AI v3.0 — Blueprint Técnico e Funcional

## 1. Visão geral

Este documento especifica um aplicativo de apoio à análise de inquéritos policiais, com foco em:

- ingestão e análise de autos em PDF, inclusive inquéritos com média de 3.000 páginas;
- operação por estados do inquérito, sem execução automática indiscriminada;
- agentes especializados para investigação, diligências, oitivas, OSINT, peças e cautelares;
- um agente **Copiloto Investigativo** conversacional, sempre disponível para interação humana;
- uso combinado de LLMs gratuitas/de baixo custo para tarefas repetitivas e modelos mais potentes para raciocínio investigativo e redação complexa;
- auditoria factual rigorosa para evitar nomes, dados ou conclusões alucinativas.

O sistema deve funcionar como **plataforma de apoio à atividade investigativa humana**, e não como substituto da decisão da autoridade policial ou do servidor responsável.

---

## 2. Objetivos do produto

1. Permitir ingestão segura de autos volumosos em PDF.
2. Organizar o conteúdo por páginas, documentos lógicos, pessoas, empresas, datas e eventos.
3. Oferecer um menu inicial após a carga do inquérito, perguntando ao usuário como deseja prosseguir.
4. Disponibilizar agentes especializados sob demanda.
5. Disponibilizar um copiloto conversacional permanente.
6. Suportar investigação em fontes abertas na internet.
7. Redigir produtos úteis ao fluxo do inquérito.
8. Garantir rastreabilidade documental de toda afirmação relevante.
9. Controlar custo computacional com roteamento de modelos por complexidade.
10. Escalar bem para inquéritos com média de 3.000 páginas e possibilidade de crescimento.

---

## 3. Princípios obrigatórios

### 3.1. Controle humano
Nenhuma tarefa crítica deve ser executada automaticamente sem comando do usuário.

### 3.2. Operação por estados
Cada inquérito deve possuir um estado operacional, e apenas certas ações ficam disponíveis em cada fase.

### 3.3. Auditoria factual
Nenhum relatório, ofício, pergunta, sugestão investigativa ou representação cautelar deve ser entregue sem validação factual.

### 3.4. Separação entre fato e inferência
O sistema deve distinguir claramente:
- dados localizados nos autos;
- dados localizados em fontes abertas;
- inferências analíticas;
- hipóteses investigativas.

### 3.5. Escalabilidade documental
O sistema jamais deve tentar enviar um inquérito inteiro ao LLM.

### 3.6. Economia computacional
Modelos baratos devem absorver a maior parte do trabalho mecânico.

---

## 4. Perfis de uso

### 4.1. Triagem rápida
Uso em inquéritos com baixa prioridade ou mera necessidade de organização inicial.

### 4.2. Investigação ativa
Uso quando há linha plausível de apuração e necessidade de aprofundamento.

### 4.3. Encerramento
Uso para relatórios finais, verificação de prescrição e consolidação do apurado.

### 4.4. OSINT dirigido
Uso para pesquisa pública sobre partes, empresas, endereços, imagens, usernames, e-mails e vínculos digitais.

---

## 5. Arquitetura macro

### 5.1. Frontend
Sugestão:
- React (web)
- React Native ou Flutter (mobile)

### 5.2. Backend
Sugestão:
- FastAPI

### 5.3. Banco relacional
Sugestão:
- PostgreSQL

### 5.4. Banco vetorial
Obrigatório:
- Qdrant

### 5.5. Fila assíncrona
Sugestão:
- Redis + Celery / RQ / Dramatiq

### 5.6. Armazenamento de arquivos
Sugestão:
- S3 compatível (MinIO no ambiente local, S3 em produção)

### 5.7. Grafo investigativo
Sugestão:
- Neo4j (preferencial) ou tabelas relacionais com visualização de grafo

### 5.8. OCR e parsing
Sugestão:
- parser nativo de PDF como primeira escolha
- OCR apenas quando necessário

---

## 6. Large Case Processing Architecture

Esta seção é obrigatória para suportar inquéritos médios e grandes, inclusive com cerca de 3.000 páginas.

### 6.1. Document Ingestion Pipeline
Todo inquérito deve passar por pipeline de ingestão antes de ser analisado pelos agentes.

Etapas obrigatórias:
1. Upload do PDF
2. Extração de texto nativo
3. OCR apenas nas páginas sem texto confiável
4. Divisão em páginas
5. Detecção de blocos semânticos
6. Classificação do tipo de peça
7. Extração de entidades
8. Criação de embeddings
9. Indexação vetorial
10. Geração de resumos hierárquicos
11. Atualização de índices investigativos
12. Persistência em cache

### 6.2. Chunking obrigatório
Todos os documentos devem ser divididos em blocos de aproximadamente 500 a 800 palavras antes da indexação vetorial.

Cada chunk deve conter metadados:
- inquerito_id
- volume
- página inicial
- página final
- tipo_documento
- pessoa_principal (se houver)
- nome_arquivo
- hash_documento
- texto_extraido
- resumo_curto

### 6.3. Classificação de peças
O sistema deve classificar automaticamente, ao menos, os seguintes tipos:
- registro de ocorrência
- termo de declaração
- despacho
- ofício
- laudo
- relatório
- documento societário
- documento bancário
- manifestação ministerial
- decisão judicial
- anexo diverso

### 6.4. Resumos hierárquicos
O sistema deve gerar, armazenar e atualizar:
- page summary
- document summary
- volume summary
- case summary

### 6.5. Índices investigativos automáticos
O sistema deve criar:
- índice de pessoas
- índice de empresas
- índice de endereços
- índice de telefones
- índice de e-mails
- índice de datas
- índice de depoimentos
- índice cronológico
- índice de documentos

### 6.6. RAG obrigatório
Toda resposta do copiloto ou dos agentes deve usar recuperação contextual.

Fluxo:
1. consulta do usuário;
2. busca híbrida (vetorial + filtros por metadados);
3. seleção dos chunks mais relevantes;
4. envio apenas desse contexto ao LLM;
5. resposta com referência a documento e página.

### 6.7. Modo “Inquérito Grande”
Se o sistema detectar mais de 1.500 páginas, deve ativar automaticamente o modo de processamento grande, com:
- análise por partes;
- cache ampliado;
- resumos por volume;
- uso preferencial de modelos baratos na triagem;
- limitação de chamadas premium a tarefas de síntese e redação final.

### 6.8. Cache investigativo
Resultados de análise, resumos e extrações devem ser armazenados em cache para evitar reprocessamento de milhares de páginas.

### 6.9. Desempenho esperado
Meta operacional:
- ingestão inicial de 3.000 páginas em lote assíncrono;
- consultas usuais retornando em poucos segundos após indexação concluída.

---

## 7. Máquina de estados do inquérito

Cada procedimento deve ter um estado operacional.

Estados sugeridos:
1. recebido
2. indexando
3. triagem
4. investigação preliminar
5. investigação ativa
6. diligências externas
7. análise final
8. relatório
9. encerramento
10. arquivamento sugerido
11. aguardando resposta externa

### 7.1. Regras
- o sistema não deve acionar todos os agentes em todos os estados;
- cada estado libera apenas certas ações;
- o histórico de transições deve ser persistido.

### 7.2. Pergunta inicial obrigatória após carga
Após o inquérito ser indexado, o sistema deve perguntar ao usuário:

> O que deseja fazer com este inquérito?

Opções sugeridas:
1. Conversar com o Copiloto
2. Fazer triagem rápida
3. Identificar linhas de investigação
4. Preparar perguntas para oitivas
5. Levantar dados OSINT
6. Sugerir diligências
7. Verificar prescrição
8. Preparar ofício ou despacho
9. Preparar representação cautelar
10. Produzir relatório parcial ou final
11. Apenas consultar documentos e índices

---

## 8. Agente Copiloto Investigativo

### 8.1. Objetivo
Ser um assistente conversacional permanente, inspirado no comportamento de um analista experiente, sempre disponível para ser chamado a dialogar com o usuário.

### 8.2. Características
- conversa em linguagem técnica, clara e formal;
- compreende o estado do inquérito;
- consulta resumos e chunks relevantes;
- orienta o usuário sobre próximos passos;
- sugere qual agente especializado acionar;
- não executa tudo automaticamente;
- sempre mantém rastreabilidade factual.

### 8.3. Capacidades
O Copiloto deve poder:
- resumir o inquérito;
- explicar o que já foi apurado;
- identificar lacunas investigativas;
- sugerir linhas plausíveis;
- sugerir diligências;
- apontar contradições;
- preparar perguntas;
- iniciar redação assistida;
- interpretar achados OSINT;
- mostrar onde determinada informação está nos autos.

### 8.4. Regras
- não inventar nomes, fatos, documentos ou valores;
- toda afirmação relevante deve apontar documento e página;
- ao sugerir hipótese, marcar como hipótese;
- ao sugerir medida invasiva, exigir comando explícito do usuário e validação jurídica.

---

## 9. Catálogo de agentes especializados

### Núcleo de controle
1. Agente Orquestrador
2. Agente Copiloto Investigativo
3. Auditor de Conformidade Fática
4. Auditor de Adequação Jurídico-Processual
5. Auditor de Fonte e Página
6. Auditor de Prudência Investigativa

### Leitura e organização dos autos
7. Agente de Leitura de Autos
8. Agente de Classificação de Peças
9. Agente de Extração de Entidades
10. Agente de Linha do Tempo
11. Agente de Mapa de Pessoas e Empresas
12. Agente de Contradições

### Inteligência investigativa
13. Agente de Linhas de Investigação
14. Agente de Perguntas para Oitiva
15. Agente de Diligências
16. Agente de Tipificação Provisória
17. Agente de Prescrição

### Produção documental
18. Agente Redator de Ofícios
19. Agente Redator de Despachos
20. Agente Redator de Relatórios
21. Agente de Representações Cautelares
22. Agente de Informações de Inteligência

### OSINT e investigação digital
23. Agente de Identidade Digital
24. Agente Sherlock de Username
25. Agente de Pesquisa por E-mail
26. Agente de Pesquisa por Telefone
27. Agente de Vínculos Empresariais
28. Agente de Redes Sociais
29. Agente de Domínios e Sites
30. Agente de Endereços e Georreferência Aberta
31. Agente de Busca Reversa de Imagem
32. Agente de Comparação Facial Controlada
33. Agente de Notícias e Mídia Pública
34. Agente de Processos e Documentos Públicos Abertos
35. Agente de Pivot Investigativo
36. Agente de Grafo Investigativo
37. Agente de Conversão OSINT em Produto Investigativo

---

## 10. Regras do módulo OSINT

### 10.1. Fontes abertas בלבד
O módulo OSINT deve usar apenas fontes publicamente acessíveis.

### 10.2. Proibição de intrusão
Não deve haver quebra de credencial, invasão, bypass técnico, scraping proibido ou uso de dados clandestinos.

### 10.3. Registro de fonte
Todo achado deve registrar:
- URL ou identificação da fonte
- data da coleta
- tipo de fonte
- trecho ou captura relevante, quando cabível

### 10.4. Separação entre achado e inferência
Saídas devem indicar:
- achado factual em fonte aberta
- correlação analítica
- hipótese investigativa

### 10.5. Comparação facial controlada
Se implementada, a saída deve ser probabilística e exigir validação humana. Nunca afirmar identidade de modo categórico.

---

## 11. Estratégia de modelos (LLM routing)

O sistema deve usar roteamento por complexidade, custo e criticidade.

### 11.1. Camada econômica
Usar modelos gratuitos ou de baixo custo para tarefas repetitivas:
- OCR assistido e pós-correção
- classificação de documentos
- extração de entidades
- sumarização inicial
- deduplicação
- estruturação JSON
- identificação de tipo de fonte
- chunk summaries

Modelos candidatos:
- Gemini Flash ou equivalente econômico
- Llama 3/4 Instruct hospedado localmente ou em provedores baratos
- DeepSeek Chat / Reasoner quando economicamente viável
- Mixtral / modelos similares
- inferência via Groq para tarefas rápidas

### 11.2. Camada premium
Reservar modelos mais fortes para:
- síntese investigativa complexa
- redação de relatórios finais
- elaboração de cautelares
- análise de contradições sofisticadas
- perguntas de oitiva estratégicas
- integração entre autos e OSINT
- copiloto em consultas difíceis

Modelos candidatos:
- GPT classe premium
- Claude classe premium
- Gemini Pro / Ultra classe equivalente

### 11.3. Regras de roteamento
1. Não usar modelo premium em tarefas mecânicas.
2. Tarefas com alta sensibilidade factual devem passar por auditoria, mesmo usando modelo premium.
3. Toda saída crítica deve poder ser reproduzida com base nos mesmos chunks e parâmetros.

---

## 12. Banco de dados — entidades principais

### 12.1. Tabelas sugeridas
- users
- inqueritos
- volumes
- documentos
- paginas
- chunks
- embeddings_refs
- pessoas
- empresas
- enderecos
- telefones
- emails
- eventos_cronologicos
- depoimentos
- citacoes_entidade
- tarefas_agentes
- resultados_agentes
- estados_inquerito
- transicoes_estado
- fontes_osint
- achados_osint
- grafos_nos
- grafos_arestas
- produtos_documentais
- auditorias
- llm_calls
- caches_resumos

### 12.2. Metadados mínimos em chunks
- chunk_id
- inquerito_id
- documento_id
- volume
- pagina_inicial
- pagina_final
- tipo_documento
- titulo_detectado
- pessoa_principal
- texto
- resumo_curto
- embedding_model
- created_at

---

## 13. Endpoints sugeridos da API

### 13.1. Ingestão
- `POST /inqueritos/upload`
- `GET /inqueritos/{id}/status`
- `POST /inqueritos/{id}/reindex`

### 13.2. Consultas estruturadas
- `GET /inqueritos/{id}/resumo`
- `GET /inqueritos/{id}/indices/pessoas`
- `GET /inqueritos/{id}/indices/empresas`
- `GET /inqueritos/{id}/indices/documentos`
- `GET /inqueritos/{id}/cronologia`
- `GET /inqueritos/{id}/contradicoes`

### 13.3. Copiloto
- `POST /copiloto/chat`
- `POST /copiloto/sugerir-acoes`

### 13.4. Agentes
- `POST /agentes/linhas-investigacao`
- `POST /agentes/perguntas-oitiva`
- `POST /agentes/diligencias`
- `POST /agentes/oficios`
- `POST /agentes/despachos`
- `POST /agentes/relatorios`
- `POST /agentes/cautelares`
- `POST /agentes/prescricao`

### 13.5. OSINT
- `POST /osint/pessoa`
- `POST /osint/empresa`
- `POST /osint/username`
- `POST /osint/email`
- `POST /osint/telefone`
- `POST /osint/imagem/reversa`
- `POST /osint/imagem/comparar`
- `POST /osint/grafo`

### 13.6. Auditoria
- `POST /auditoria/factual`
- `GET /auditoria/{resultado_id}`

---

## 14. Fluxos principais

### 14.1. Fluxo de carga de inquérito
1. usuário envia PDFs;
2. sistema inicia pipeline assíncrono;
3. sistema extrai texto e chunks;
4. sistema cria índices e resumos;
5. sistema marca o inquérito como pronto;
6. sistema apresenta o menu inicial de ações.

### 14.2. Fluxo do copiloto
1. usuário faz pergunta;
2. copiloto recupera estado do inquérito;
3. consulta índices e RAG;
4. responde com referências;
5. oferece próximos caminhos possíveis.

### 14.3. Fluxo de produção documental
1. usuário escolhe o produto;
2. agente reúne contexto factual;
3. modelo redige minuta;
4. auditores validam;
5. sistema devolve versão revisável.

### 14.4. Fluxo OSINT
1. usuário escolhe profundidade;
2. sistema executa coleta em fontes abertas;
3. camada econômica estrutura e classifica;
4. camada premium integra e interpreta;
5. auditor valida linguagem e fontes;
6. sistema entrega relatório ou produto derivado.

---

## 15. Auditoria contra alucinações

### 15.1. Regra central
Nenhuma informação relevante pode aparecer no produto final sem lastro documental ou indicação clara de hipótese.

### 15.2. Validação de entidades sensíveis
Validar sempre:
- nomes
- CPF/CNPJ
- datas
- valores
- endereços
- placas
- telefones
- e-mails

### 15.3. Política de bloqueio
Se o sistema gerar um nome não localizado nos autos ou nas fontes citadas, o auditor deve:
- bloquear o envio;
- registrar o erro;
- sugerir revisão ou remoção.

### 15.4. Exibição de suporte
Toda resposta crítica deve exibir:
- documento de origem
- página(s)
- trecho de suporte ou referência resumida

---

## 16. Requisitos funcionais mínimos (MVP)

### MVP fase 1
- upload de PDFs
- extração de texto
- OCR seletivo
- chunking
- indexação vetorial
- resumos por documento/volume/caso
- índices de pessoas, empresas e documentos

### MVP fase 2
- copiloto investigativo
- linhas de investigação
- perguntas para oitivas
- sugestões de diligências
- relatórios simples

### MVP fase 3
- OSINT básico
- vínculos empresariais
- usernames
- mapa relacional simples
- ofícios e despachos

### MVP fase 4
- OSINT avançado
- imagem reversa
- comparação facial controlada
- grafo investigativo
- representações cautelares
- prescrição automatizada assistida

---

## 17. Backlog por sprints

### Sprint 1 — Fundação do projeto
- criar monorepo
- configurar backend FastAPI
- configurar PostgreSQL
- configurar Qdrant
- configurar armazenamento de arquivos
- configurar fila assíncrona

### Sprint 2 — Ingestão documental
- upload de PDFs
- persistência de volumes e documentos
- extração de texto
- OCR seletivo
- logs de ingestão

### Sprint 3 — Chunking e indexação
- divisão em chunks
- embeddings
- indexação no Qdrant
- busca híbrida

### Sprint 4 — Classificação e índices
- classificador de peças
- extração de entidades
- índices de pessoas, empresas, datas, documentos
- cronologia inicial

### Sprint 5 — Resumos hierárquicos
- resumo por página
- resumo por documento
- resumo por volume
- resumo geral
- cache de resumos

### Sprint 6 — Copiloto Investigativo
- chat do copiloto
- recuperação contextual
- memória de sessão por inquérito
- sugestões de próximos passos

### Sprint 7 — Agentes investigativos básicos
- linhas de investigação
- perguntas de oitiva
- diligências
- tipificação provisória
- contradições

### Sprint 8 — Produção documental
- ofícios
- despachos
- relatórios parciais
- relatórios finais simples
- informações de inteligência

### Sprint 9 — Auditoria forte
- auditor factual
- auditor de fonte e página
- auditor de prudência investigativa
- bloqueios automáticos

### Sprint 10 — OSINT básico
- pesquisa de pessoa
- empresa
- username
- e-mail
- telefone
- notícias públicas

### Sprint 11 — OSINT avançado
- busca reversa de imagem
- comparação facial controlada
- pivot investigativo
- grafo relacional

### Sprint 12 — Cautelares e prescrição
- representações cautelares assistidas
- cálculo e relatório de prescrição
- validações jurídicas adicionais

### Sprint 13 — Frontend avançado
- dashboard do inquérito
- visualização de índices
- cronologia interativa
- grafo de vínculos
- tela de copiloto

### Sprint 14 — Observabilidade e deploy
- métricas de custo por LLM
- rastreamento de latência
- logs estruturados
- deploy
- documentação operacional

---

## 18. Prompt mestre para modelo construtor de código

```text
Você é o engenheiro principal deste projeto. Construa um aplicativo de apoio à análise de inquéritos policiais conforme este documento, respeitando rigorosamente os princípios abaixo:

1. Não implemente fluxo que envie PDFs inteiros a LLMs.
2. Implemente pipeline assíncrono de ingestão com chunking, embeddings, indexação vetorial e resumos hierárquicos.
3. Adote FastAPI, PostgreSQL, Qdrant e armazenamento de arquivos compatível com S3.
4. Implemente máquina de estados do inquérito.
5. Implemente um Copiloto Investigativo conversacional sempre disponível.
6. Implemente agentes especializados acionáveis sob demanda.
7. Implemente auditoria factual obrigatória, com validação de nomes, datas, valores e páginas.
8. Use modelos econômicos para tarefas repetitivas e modelos premium apenas para raciocínio complexo e redação crítica.
9. Estruture o código de forma modular, com testes, logs, filas assíncronas e observabilidade.
10. Entregue o projeto por sprints, gerando código, migrations, testes, documentação e exemplos de uso.

Comece pelo Sprint 1 e avance em ordem. Ao final de cada sprint, produza:
- resumo do que foi implementado;
- arquivos criados/alterados;
- instruções de execução;
- próximos passos.
```

---

## 19. Prompt mestre do Copiloto Investigativo

```text
Você é o Copiloto Investigativo do sistema. Seu papel é auxiliar o usuário a compreender, organizar e explorar o inquérito, sempre sob controle humano.

Regras obrigatórias:
1. Nunca invente nomes, fatos, valores, datas ou documentos.
2. Toda afirmação relevante deve apontar a origem documental sempre que disponível.
3. Distingua fato, indício, hipótese e inferência.
4. Ao identificar lacunas, sugira caminhos investigativos plausíveis.
5. Ao lidar com OSINT, use apenas informações públicas e identifique a fonte.
6. Ao sugerir medida cautelar ou imputação mais grave, adote linguagem prudente e exija base empírica mínima.
7. Sempre que possível, ofereça opções de continuidade ao usuário, em vez de executar tudo automaticamente.
8. Em inquéritos grandes, use resumos hierárquicos e recuperação contextual, jamais assumindo leitura integral instantânea do acervo.
```

---

## 20. Critérios de aceite do sistema

O sistema será considerado aceitável se:
- indexar e consultar autos volumosos com desempenho adequado;
- responder com base em trechos recuperados e não por invenção;
- permitir conversa contínua com o copiloto;
- oferecer menu de ações após a carga do inquérito;
- produzir minutas úteis e auditáveis;
- suportar OSINT sob comando;
- controlar custos por meio de roteamento de modelos;
- registrar histórico e trilha de auditoria.

---

## 21. Melhorias futuras

- ranking estratégico de inquéritos por probabilidade de sucesso;
- painel de procedimentos próximos da prescrição;
- comparação entre inquéritos para detectar padrões repetidos;
- importação automatizada de lote de procedimentos;
- agentes especializados por tipo penal;
- geração de dashboards gerenciais.

---

## 22. Conclusão

A versão 3.0 consolida a arquitetura necessária para construir uma plataforma de apoio à investigação capaz de lidar com grande volume documental, manter diálogo permanente com o usuário por meio de um copiloto, operar com agentes especializados e preservar rigor factual. O foco não é automatizar cegamente, mas potencializar a capacidade analítica do investigador com controle humano, rastreabilidade e eficiência operacional.
