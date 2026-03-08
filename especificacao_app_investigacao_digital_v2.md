# Especificação Técnica e Funcional
## Plataforma de Assistência Investigativa com Módulo OSINT Avançado

**Versão:** 2.0  
**Objetivo:** orientar um modelo construtor de código na implementação de um aplicativo de apoio à análise de inquéritos policiais, com fluxo por estados, agentes especializados, auditoria factual e módulo de investigação digital em fontes abertas.  
**Perfil do usuário principal:** servidor/analista/autoridade que atua com grande volume de inquéritos policiais e precisa escolher, para cada procedimento, quais tarefas deseja executar.

---

# 1. Visão Geral do Produto

O produto deverá ser um **aplicativo web responsivo, com futura expansão para mobile**, destinado a auxiliar a análise investigativa de inquéritos policiais, sem substituir a decisão humana.

O sistema deve operar por **máquina de estados do inquérito**, com **agentes especializados sob demanda**, evitando execução automática indiscriminada para todos os procedimentos.

O aplicativo deverá:

- receber autos em PDF e outros documentos;
- indexar, classificar e organizar peças processuais;
- permitir escolha do caminho investigativo logo após a carga do inquérito;
- oferecer agentes especializados para tarefas específicas;
- possuir auditoria rígida contra fatos, nomes, datas e dados alucinativos;
- utilizar modelos econômicos para tarefas repetitivas;
- reservar modelos mais potentes para tarefas analíticas e redacionais complexas;
- incluir módulo avançado de investigação digital em fontes abertas (OSINT), inspirado em técnicas de correlação, pivoting e rastreamento de identidade digital.

---

# 2. Princípios Obrigatórios do Sistema

## 2.1. Controle humano
Nenhum agente deve concluir automaticamente pela autoria ou encerrar o raciocínio jurídico sem revisão humana.

## 2.2. Execução sob demanda
Ao carregar um inquérito, o sistema deve perguntar ao usuário como deseja prosseguir, exibindo lista de possibilidades.

## 2.3. Auditoria factual obrigatória
Nenhum texto final poderá ser exibido sem validação contra as fontes dos autos e, quando houver, contra as fontes públicas coletadas.

## 2.4. Separação entre fato e inferência
Toda saída deve distinguir:
- fato documental;
- fato localizado em fonte aberta;
- inferência analítica;
- hipótese investigativa.

## 2.5. Rastreabilidade
Toda afirmação relevante deve conter origem:
- documento;
- página;
- trecho;
- ou URL/fonte aberta e data da coleta.

## 2.6. Modularidade
Cada agente deve ser isolado, acionável via API e controlado pelo orquestrador.

---

# 3. Fluxo Principal do Aplicativo

## 3.1. Importação do inquérito
Ao receber documentos do procedimento, o sistema deve:

1. armazenar os arquivos;
2. extrair texto dos PDFs nativamente;
3. aplicar OCR apenas quando necessário;
4. classificar as peças;
5. extrair entidades iniciais (nomes, empresas, datas, órgãos, números de documentos);
6. apresentar resumo mínimo do material carregado.

## 3.2. Pergunta obrigatória ao usuário
Após a carga do procedimento, o aplicativo deve exibir algo como:

```text
Inquérito importado com sucesso.
Como deseja prosseguir?

[1] Apenas indexar e organizar os autos
[2] Fazer triagem rápida
[3] Identificar linhas de investigação
[4] Preparar perguntas para oitivas
[5] Sugerir diligências pendentes
[6] Fazer pesquisa OSINT das partes
[7] Redigir ofício
[8] Verificar prescrição
[9] Preparar representação cautelar
[10] Produzir relatório parcial
[11] Produzir relatório final
```

## 3.3. Classificação estratégica opcional
O sistema também deve permitir marcar o procedimento como:

- alta probabilidade de elucidação;
- probabilidade moderada;
- baixa probabilidade;
- foco em triagem;
- foco em prescrição;
- foco em encerramento;
- foco em organização documental.

Essa classificação servirá para priorizar sugestões do orquestrador.

---

# 4. Máquina de Estados do Inquérito

Implementar uma **Finite State Machine (FSM)** com os seguintes estados iniciais:

- `recebido`
- `indexado`
- `triagem`
- `investigacao_preliminar`
- `investigacao_ativa`
- `diligencias_externas`
- `analise_final`
- `relatorio_parcial`
- `relatorio_final`
- `encerramento`
- `arquivamento_sugerido`
- `aguardando_resposta_externa`

Cada estado deve liberar apenas certas ações.

Exemplo:

- `triagem`: resumo, prescrição, pessoas citadas, linhas preliminares;
- `investigacao_ativa`: perguntas, diligências, OSINT, cronologia, vínculos;
- `analise_final`: relatório, tipificação, indiciamento, cautelares;
- `encerramento`: relatório final e checklist de remessa.

---

# 5. Arquitetura de Alto Nível

## 5.1. Frontend
**Tecnologia sugerida:** React + TypeScript + Tailwind.

Requisitos:
- dashboard de inquéritos;
- página do procedimento;
- visualização de documentos;
- painel de estados;
- chat operacional com agentes;
- formulários guiados;
- visualização de grafo investigativo;
- histórico das ações executadas;
- trilha de auditoria.

## 5.2. Backend
**Tecnologia sugerida:** FastAPI.

Requisitos:
- arquitetura por serviços;
- endpoints REST;
- filas para tarefas pesadas;
- versionamento de prompts/agentes;
- logs estruturados;
- autenticação e perfis.

## 5.3. Banco relacional
**Tecnologia sugerida:** PostgreSQL.

## 5.4. Banco vetorial
**Tecnologia sugerida:** Qdrant.

## 5.5. Grafo investigativo
**Tecnologia sugerida:** Neo4j ou PostgreSQL com extensão de relações, preferindo Neo4j para visualização e consultas complexas.

## 5.6. Armazenamento de arquivos
S3 compatível (MinIO em ambiente local/desenvolvimento).

## 5.7. Fila de tarefas
Celery + Redis, ou alternativa equivalente.

---

# 6. Estratégia de Uso de LLMs

## 6.1. Camada econômica (tarefas repetitivas)
Usar modelos gratuitos ou de baixo custo para:

- classificação de documentos;
- extração de entidades;
- sumarização básica;
- OCR pós-processado;
- deduplicação;
- estruturação JSON;
- tagueamento semântico;
- triagem de OSINT;
- identificação de tipo de fonte;
- criação de resumos curtos.

Modelos possíveis:
- Gemini Flash ou equivalente econômico;
- Llama 3.x Instruct via Groq/infra própria;
- DeepSeek Chat/Reasoner em tarefas controladas;
- Mixtral/Instruct para tarefas simples;
- pipelines não-LLM quando possível.

## 6.2. Camada premium (tarefas complexas)
Usar modelos mais potentes para:

- linhas de investigação plausíveis;
- perguntas de oitivas contextualizadas;
- redação de relatórios formais;
- redação de ofícios sofisticados;
- representações cautelares;
- correlação complexa entre achados dos autos e achados OSINT;
- auditoria argumentativa e prudência jurídica.

Modelos possíveis:
- GPT classe avançada;
- Claude classe avançada;
- Gemini Pro/Ultra classe superior;
- outro modelo premium configurável.

## 6.3. Roteador de modelos
Implementar um **LLM Router** com regras:

- tarefa simples -> modelo econômico;
- tarefa analítica/jurídica -> modelo premium;
- fallback automático entre provedores;
- registro do custo por tarefa;
- limiar máximo de custo por inquérito.

## 6.4. Política de economia
Criar perfis de execução:
- `economico`
- `balanceado`
- `profundo`

---

# 7. Agentes do Sistema

## 7.1. Agente Orquestrador Investigativo
### Função
Controlar fluxo, estado, menu de ações e distribuição de tarefas.

### Entradas
- estado do inquérito;
- classificação estratégica;
- comando do usuário.

### Saídas
- sugestões de ações;
- acionamento de agentes;
- registro em trilha de auditoria.

---

## 7.2. Auditor de Conformidade Fática
### Função
Verificar se toda afirmação produzida encontra amparo em documento ou fonte aberta rastreável.

### Regras
- bloquear nomes não encontrados;
- bloquear datas não sustentadas;
- bloquear números, valores e cargos não confirmados;
- rebaixar afirmações categóricas para linguagem prudencial quando houver apenas indício.

---

## 7.3. Auditor de Fonte e Página
### Função
Associar cada afirmação relevante a:
- nome do documento;
- página;
- trecho;
- ou URL e data de coleta.

---

## 7.4. Auditor de Prudência Investigativa
### Função
Reescrever saídas para evitar conclusões indevidas.

Exemplos de conversão:
- “Fulano praticou” -> “há indícios de participação de Fulano”
- “empresa fraudulenta” -> “empresa apontada nos autos como potencialmente utilizada no contexto investigado”

---

## 7.5. Agente de Linhas de Investigação
### Função
Propor hipóteses investigativas plausíveis a partir dos autos e de achados externos.

### Saída
Classificar cada linha como:
- fortemente apoiada nos autos;
- plausível e dependente de diligência;
- residual.

---

## 7.6. Agente de Perguntas para Oitivas
### Função
Gerar perguntas específicas para:
- testemunhas;
- vítimas;
- possíveis autores;
- representantes de empresa;
- servidores públicos;
- familiares ou terceiros relevantes.

### Estrutura da saída
- objetivo da oitiva;
- perguntas prioritárias;
- perguntas subsidiárias;
- pontos de confronto;
- documento base.

---

## 7.7. Agente de Diligências Necessárias
### Função
Indicar diligências úteis e proporcionais.

### Exemplos
- novas oitivas;
- requisição documental;
- expedição de ofício;
- consulta a bases públicas;
- confronto documental;
- verificação local;
- aprofundamento OSINT.

---

## 7.8. Agente Redator de Ofícios
### Função
Produzir minutas de ofícios a órgãos públicos e entidades privadas.

### Estrutura
- identificação do procedimento;
- objeto;
- síntese objetiva;
- fundamento da solicitação;
- delimitação do que se pretende;
- prazo/urgência.

---

## 7.9. Agente de Representações por Medidas Cautelares
### Função
Minutar representações quando expressamente requisitado.

### Regras críticas
- somente por acionamento do usuário;
- exigir lastro mínimo previamente validado;
- usar checklist de suficiência indiciária;
- manter linguagem prudente e fundamentada.

---

## 7.10. Agente de Tipificação Provisória
### Função
Sugerir enquadramentos penais provisórios com alternativas.

---

## 7.11. Agente de Cronologia e Mapa Relacional
### Função
Reconstruir linha do tempo e relações entre pessoas, empresas, documentos, locais e eventos.

---

## 7.12. Agente de Relatórios
### Função
Produzir:
- relatório parcial;
- informação policial;
- despacho saneador;
- relatório final;
- minuta de remessa.

---

# 8. Módulo OSINT Avançado

## 8.1. Objetivo
Permitir investigação digital em fontes abertas, com foco em correlação de rastros, pivoting e geração de produtos úteis para o inquérito.

## 8.2. Regras do módulo
- operar apenas por comando do usuário;
- executar em níveis de profundidade configuráveis;
- usar somente fontes abertas;
- registrar fonte, data, tipo de coleta e confiabilidade;
- separar achados factuais de inferências.

## 8.3. Níveis do módulo
### Nível 1 — rápido
- busca nominal básica;
- presença digital essencial;
- empresas associadas;
- resumo curto.

### Nível 2 — intermediário
- redes sociais;
- vínculos empresariais;
- endereços;
- contatos;
- notícias;
- mapa simples.

### Nível 3 — aprofundado
- busca reversa de imagem;
- comparação facial controlada;
- correlação de múltiplos perfis;
- pivot automático;
- grafo avançado;
- geração de sugestões de diligência.

---

# 9. Subagentes OSINT

## 9.1. Agente de Identificação Civil Digital
Pesquisa presença pública a partir de nome, apelido, e-mail, telefone, username e empresa.

## 9.2. Agente de Vínculos Societários e Empresariais
Pesquisa quadro societário, alterações, empresas relacionadas, coincidências de sócios, endereços e contatos.

## 9.3. Agente de Redes Sociais e Perfis Públicos
Localiza perfis e extrai biografias, links, fotos públicas, menções a atividades e vínculos aparentes.

## 9.4. Agente de Domínios e Infraestrutura Digital
Pesquisa domínios, subdomínios, páginas públicas, e-mails e infraestrutura web aparente.

## 9.5. Agente de Endereços e Georreferência Aberta
Padroniza e correlaciona endereços, uso aparente do local e coincidências relevantes.

## 9.6. Agente de Telefones e E-mails Públicos
Localiza e correlaciona contatos publicamente expostos.

## 9.7. Agente de Busca Reversa de Imagens
Verifica reutilização de imagem em páginas e perfis públicos.

## 9.8. Agente de Comparação Facial Controlada
Compara duas imagens fornecidas e retorna similaridade provável, sem afirmar identidade de forma categórica.

## 9.9. Agente de Notícias e Reputação Pública
Pesquisa menções públicas relevantes em mídia e blogs.

## 9.10. Agente de Processos e Documentos Públicos Abertos
Pesquisa referências processuais públicas quando acessíveis em fontes abertas.

## 9.11. Agente de Mapas de Relacionamento
Transforma achados em grafo investigativo.

## 9.12. Agente de Conversão em Produto Investigativo
Converte achados em:
- informação de inteligência;
- perguntas para oitiva;
- sugestão de diligências;
- minuta de despacho;
- anexo de relatório.

---

# 10. Novos Subagentes Inspirados em Técnicas de Pivot Digital

## 10.1. Agente de Pivot OSINT
### Função
Expandir automaticamente a investigação digital a partir de qualquer entidade inicial.

### Entradas possíveis
- nome;
- username;
- e-mail;
- telefone;
- empresa;
- domínio;
- imagem.

### Lógica
1. extrair entidade inicial;
2. localizar novos rastros;
3. adicionar novos nós ao grafo;
4. repetir em profundidade controlada;
5. parar conforme limite configurado.

### Parâmetros configuráveis
- profundidade máxima;
- número máximo de pivôs;
- tempo máximo por execução;
- escopo (pessoa, empresa, domínio, imagem).

---

## 10.2. Agente Sherlock Digital
### Função
Buscar um mesmo username em múltiplas plataformas públicas.

### Saída
- plataforma;
- URL do perfil;
- confiança na correspondência;
- sinais de coincidência (foto, bio, nome, links).

---

## 10.3. Agente de Graph Intelligence
### Função
Consolidar os achados em um grafo visual e textual.

### Tipos de relação
- pessoa -> perfil;
- pessoa -> empresa;
- empresa -> domínio;
- perfil -> imagem;
- e-mail -> domínio;
- telefone -> anúncio;
- endereço -> empresa;
- empresa -> sócio;
- perfil -> outro perfil.

### Entregas
- grafo navegável;
- clusters;
- nós centrais;
- caminhos de conexão;
- exportação para PNG/JSON.

---

# 11. Menu Específico do Módulo OSINT

Ao acionar o módulo, exibir algo como:

```text
Qual tipo de pesquisa deseja realizar?

[1] Pesquisa básica de presença digital
[2] Pesquisa empresarial e societária
[3] Pesquisa de redes sociais
[4] Pesquisa por username
[5] Pesquisa por telefone ou e-mail
[6] Pesquisa por domínio
[7] Pesquisa por imagem
[8] Pivot OSINT automático
[9] Mapa de vínculos
[10] Converter achados em relatório de inteligência
[11] Gerar perguntas para oitiva com base nos achados
[12] Sugerir diligências com base nos achados
```

---

# 12. Banco de Dados — Entidades Principais

Criar as seguintes tabelas iniciais no PostgreSQL:

- `users`
- `cases`
- `case_documents`
- `document_chunks`
- `entities_people`
- `entities_companies`
- `entities_locations`
- `entities_phones`
- `entities_emails`
- `entities_domains`
- `entities_images`
- `investigation_states`
- `agent_runs`
- `agent_outputs`
- `factual_audits`
- `osint_sources`
- `osint_findings`
- `osint_profiles`
- `osint_relationships`
- `graph_nodes`
- `graph_edges`
- `tasks_queue`
- `prompt_versions`
- `citations`

Campos mínimos a prever em `osint_findings`:
- id
- case_id
- source_type
- source_url
- source_title
- collected_at
- entity_type
- entity_value
- raw_excerpt
- structured_data_json
- confidence_score
- factual_or_inference (`fact`, `inference`, `hypothesis`)
- created_by_agent

---

# 13. Estrutura do Banco Vetorial

No Qdrant, manter coleções separadas para:
- chunks documentais dos autos;
- achados OSINT resumidos;
- perguntas e respostas validadas;
- modelos de peças;
- jurisprudência/modelos internos futuros, se aplicável.

Metadados mínimos por chunk:
- case_id
- document_id
- page
- piece_type
- entities
- date_reference
- source_kind (`auto`, `osint`, `user`)

---

# 14. Endpoints da API (MVP + Expansão)

## Casos
- `POST /cases`
- `GET /cases`
- `GET /cases/{id}`
- `PATCH /cases/{id}/state`
- `POST /cases/{id}/classify`

## Documentos
- `POST /cases/{id}/documents`
- `GET /cases/{id}/documents`
- `POST /cases/{id}/index`
- `GET /cases/{id}/timeline`

## Orquestração
- `GET /cases/{id}/available-actions`
- `POST /cases/{id}/run-action`

## Agentes investigativos
- `POST /agents/investigation-lines`
- `POST /agents/questions`
- `POST /agents/diligences`
- `POST /agents/official-letters`
- `POST /agents/cautionary-representations`
- `POST /agents/reports`
- `POST /agents/typing`

## OSINT
- `POST /osint/basic-search`
- `POST /osint/social-search`
- `POST /osint/company-search`
- `POST /osint/username-search`
- `POST /osint/phone-email-search`
- `POST /osint/domain-search`
- `POST /osint/image-reverse-search`
- `POST /osint/face-compare`
- `POST /osint/pivot`
- `POST /osint/graph`
- `POST /osint/convert-to-intelligence-report`

## Auditoria
- `POST /audit/factual`
- `POST /audit/source-trace`
- `POST /audit/prudence`

## Dashboard
- `GET /dashboard/priorities`
- `GET /dashboard/prescription-risks`
- `GET /dashboard/pending-diligences`
- `GET /dashboard/stagnated-cases`

---

# 15. Painel de Inteligência Investigativa

Criar dashboard com:
- inquéritos mais promissores;
- inquéritos próximos da prescrição;
- inquéritos aguardando resposta externa;
- inquéritos sem movimentação recente;
- diligências pendentes;
- quantidade de pessoas e empresas mapeadas;
- quantidade de achados OSINT por procedimento.

---

# 16. Regras de Segurança, Privacidade e Registro

## 16.1. Autenticação
JWT + refresh token.

## 16.2. Perfis
- administrador;
- investigador/analista;
- leitura/revisão.

## 16.3. Logs
Registrar:
- agente acionado;
- entradas;
- modelo usado;
- custo estimado;
- tempo de execução;
- resultado;
- bloqueios do auditor.

## 16.4. Política de retenção
Permitir configuração por ambiente.

## 16.5. Regra para comparação facial
A comparação facial deve ser opcional, controlada, registrada e sempre acompanhada de alerta de validação humana.

---

# 17. Sprint Backlog de Desenvolvimento

## Sprint 1 — Estrutura base do projeto
### Objetivos
- criar monorepo ou estrutura organizada;
- configurar FastAPI;
- configurar React + TypeScript;
- configurar PostgreSQL, Redis, MinIO e Qdrant via Docker Compose;
- criar autenticação inicial.

### Entregas
- app sobe localmente com docker;
- login funcional;
- CRUD básico de casos.

---

## Sprint 2 — Upload e indexação documental
### Objetivos
- upload de arquivos;
- extração textual de PDFs;
- OCR opcional;
- classificação de peças;
- criação de chunks e embeddings.

### Entregas
- documentos indexados;
- busca simples por texto;
- visualização das peças.

---

## Sprint 3 — Máquina de estados e orquestrador
### Objetivos
- implementar FSM do inquérito;
- implementar menu de ações por estado;
- registrar histórico de transições;
- criar `available-actions`.

### Entregas
- fluxo controlado por estado;
- interface inicial perguntando como prosseguir.

---

## Sprint 4 — Auditoria factual e de prudência
### Objetivos
- implementar auditor factual;
- implementar auditor de fonte e página;
- implementar auditor de prudência.

### Entregas
- qualquer saída textual passa por auditoria;
- painel de inconsistências.

---

## Sprint 5 — Agentes nucleares do inquérito
### Objetivos
- linhas de investigação;
- perguntas de oitivas;
- diligências;
- cronologia e vínculos.

### Entregas
- saídas em JSON + texto formatado;
- revisão humana antes de salvar.

---

## Sprint 6 — Redação jurídica
### Objetivos
- agente de ofícios;
- agente de relatórios;
- agente de tipificação;
- esqueleto de cautelares.

### Entregas
- geração de minutas com auditoria factual.

---

## Sprint 7 — Módulo OSINT básico
### Objetivos
- busca nominal;
- busca empresarial;
- redes sociais;
- domínios;
- telefones/e-mails;
- armazenamento dos achados.

### Entregas
- relatório OSINT resumido;
- visualização das fontes.

---

## Sprint 8 — OSINT avançado
### Objetivos
- busca por username (Sherlock Digital);
- pivot OSINT automático;
- busca reversa de imagem;
- comparação facial controlada.

### Entregas
- investigações digitais mais profundas;
- controles de profundidade e custo.

---

## Sprint 9 — Grafo investigativo
### Objetivos
- integrar Neo4j;
- criar nós e arestas dos achados;
- visualização no frontend;
- filtros por entidade e confiança.

### Entregas
- mapa de relacionamentos navegável.

---

## Sprint 10 — Dashboard, custo e deploy
### Objetivos
- painel de inteligência investigativa;
- métrica de consumo de LLMs;
- perfis `economico`, `balanceado`, `profundo`;
- deploy em ambiente de homologação.

### Entregas
- sistema utilizável fim a fim.

---

# 18. Regras de Prompting dos Agentes

## 18.1. Regra universal
Todo prompt de agente deve conter:
- escopo da tarefa;
- proibição de inventar fatos;
- exigência de indicar fontes;
- separação entre fato e inferência;
- linguagem prudente.

## 18.2. Exemplo de prompt-base do Auditor Factual

```text
Você é um Auditor de Conformidade Fática.
Sua função é verificar se toda afirmação do texto está suportada por documento ou fonte aberta fornecida.
Não admita dados sem amparo.
Para cada afirmação relevante, associe a fonte.
Se não houver amparo, marque como NÃO CONFIRMADO.
Se houver apenas indício, reescreva com prudência.
Nunca invente nomes, cargos, datas, valores ou vínculos.
```

## 18.3. Exemplo de prompt-base do Agente de Linhas de Investigação

```text
Você é um Analista de Linhas Investigativas.
Examine os autos e proponha hipóteses plausíveis, sem afirmar conclusões definitivas.
Classifique cada hipótese como: fortemente apoiada, plausível dependente de diligência, ou residual.
Indique quais documentos sustentam cada hipótese e quais diligências poderiam confirmá-la ou refutá-la.
Nunca invente fatos.
```

## 18.4. Exemplo de prompt-base do Agente OSINT

```text
Você é um Analista OSINT.
Utilize apenas fontes abertas e publicamente acessíveis.
Organize os achados indicando URL, data de coleta, tipo de fonte e trecho relevante.
Separe fato encontrado de inferência analítica.
Não conclua pela autoria delitiva.
Sugira, quando cabível, perguntas, diligências ou pontos de verificação.
```

---

# 19. Prompt Mestre para Modelo Construtor de Código

```text
Atue como Arquiteto de Software Sênior e Engenheiro Full Stack.
Implemente o sistema descrito neste documento em etapas incrementais, com foco em código limpo, tipado, testável e modular.

Stack principal:
- Frontend: React + TypeScript + Tailwind
- Backend: FastAPI
- Banco relacional: PostgreSQL
- Vetor: Qdrant
- Grafo: Neo4j
- Fila: Redis + Celery
- Storage: MinIO
- Orquestração local: Docker Compose

Regras obrigatórias:
1. Criar projeto pronto para execução local.
2. Implementar primeiro a infraestrutura base.
3. Depois implementar upload, indexação e máquina de estados.
4. Toda saída textual deve passar por auditoria factual.
5. Criar roteador de LLMs com perfis economico, balanceado e profundo.
6. Implementar módulo OSINT por etapas, começando pelo básico.
7. Registrar logs, custos e trilha de auditoria.
8. Escrever testes automatizados para os principais fluxos.
9. Gerar README claro e scripts de inicialização.
10. Entregar cada sprint com checklist do que foi concluído.

Ao codificar:
- prefira contratos de API claros;
- use Pydantic no backend;
- use componentes reutilizáveis no frontend;
- documente variáveis de ambiente;
- crie seeds de desenvolvimento;
- use migrations.

Comece pela Sprint 1.
```

---

# 20. Critérios de Aceite do MVP

O MVP será considerado funcional quando:

1. permitir criar um caso/inquérito;
2. aceitar upload de PDFs;
3. indexar documentos e exibir peças;
4. perguntar ao usuário como deseja prosseguir;
5. executar ao menos 4 agentes centrais;
6. executar ao menos 4 subagentes OSINT básicos;
7. auditar factualidade das saídas;
8. gerar uma minuta de ofício;
9. gerar um relatório parcial;
10. exibir um mapa simples de vínculos.

---

# 21. Próxima Expansão Pós-MVP

Após o MVP, priorizar:
- integração com WhatsApp/Telegram como canal de consulta operacional;
- exportação DOCX/PDF;
- workflow colaborativo;
- biblioteca de modelos por tipo de inquérito;
- prescrição penal automatizada;
- dashboards avançados;
- treinamento por modelos redacionais do usuário.

---

# 22. Observações Finais para o Modelo Codificador

- Não criar um chatbot genérico.
- Criar um sistema de apoio investigativo por estados, com agentes especializados.
- Toda automação deve ser guiada por escolha do usuário.
- O módulo OSINT deve privilegiar correlação de rastros e pivoting.
- O produto deve ser auditável, econômico e escalável.
- O foco é produtividade com prudência factual e utilidade real em análise de inquéritos.

