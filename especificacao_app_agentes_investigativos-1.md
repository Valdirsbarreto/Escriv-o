# Especificação Funcional e Técnica — Aplicativo de Agentes Investigativos para Apoio a Inquéritos Policiais

## 1. Objetivo do produto

Construir um aplicativo de apoio ao trabalho investigativo em inquéritos policiais, com foco em:

- organização e leitura de autos em PDF e imagens;
- identificação de linhas de investigação plausíveis;
- preparação de perguntas para oitivas de testemunhas, vítimas, investigados e representantes de órgãos/empresas;
- redação assistida de ofícios, despachos, relatórios e outras peças;
- geração assistida de representações por medidas cautelares, sempre sob controle humano;
- pesquisa em fontes abertas (OSINT) para subsidiar diligências e peças;
- auditoria rigorosa para impedir nomes, datas, valores, documentos ou fatos alucinativos.

O sistema deve ser **modular, auditável, orientado por estados do inquérito e comandado pelo usuário**, sem executar automaticamente todas as tarefas para todos os procedimentos.

---

## 2. Premissas centrais do produto

1. **O usuário controla o fluxo.** O sistema deve perguntar como o usuário deseja prosseguir após a carga do inquérito.
2. **Não inventar fatos.** Toda afirmação relevante deve estar vinculada a documento, página, fonte pública ou instrução expressa do usuário.
3. **Arquitetura por agentes especializados.** Cada agente tem missão, entrada, processamento, saída e regras de bloqueio.
4. **Fluxo por estados.** Cada inquérito evolui por etapas e só libera certos agentes conforme o estado atual.
5. **Modelo híbrido de LLMs.** Utilizar modelos gratuitos ou de baixo custo nas tarefas repetitivas e modelos mais potentes nas tarefas analíticas, sensíveis ou redacionais complexas.
6. **Auditoria obrigatória.** Nenhuma saída final deve ser entregue sem validação factual e jurídica mínima.
7. **Rastreabilidade total.** Sempre exibir ou armazenar a origem de cada dado usado nas peças produzidas.

---

## 3. Público-alvo inicial

- Delegados de Polícia
- Oficiais / agentes / analistas que trabalham com inquéritos
- Setores de inteligência policial
- Cartórios policiais / delegacias de acervo

---

## 4. Escopo funcional do MVP

### 4.1 O que o MVP deve fazer

- permitir upload de PDFs e imagens dos autos;
- extrair texto dos documentos;
- identificar peças e páginas;
- indexar conteúdo em banco vetorial para consulta semântica;
- apresentar menu inicial de possibilidades ao usuário;
- sugerir linhas de investigação plausíveis;
- gerar perguntas para oitivas por perfil da pessoa a ser intimada;
- redigir minutas de ofícios;
- redigir despachos simples;
- executar pesquisa OSINT básica em fontes abertas públicas;
- gerar relatórios parciais estruturados;
- validar se a saída contém dados sustentados nos autos.

### 4.2 O que pode ficar para fase posterior

- representações cautelares complexas;
- mapas relacionais com visualização gráfica avançada;
- integração com agenda, WhatsApp, Telegram ou e-mail;
- gerenciamento multiusuário avançado;
- dashboard de produtividade e priorização por prescrição;
- exportação para DOCX/PDF com modelos oficiais sofisticados.

---

## 5. Fluxo de uso desejado

### 5.1 Carga inicial do inquérito

Quando um novo inquérito for importado, o sistema **não deve disparar todas as análises automaticamente**.

Deve executar apenas:

- ingestão do arquivo;
- OCR se necessário;
- separação e indexação dos documentos;
- identificação preliminar de pessoas, datas, peças e eventos.

Em seguida, deve exibir algo como:

```text
Inquérito carregado com sucesso.
Selecione como deseja prosseguir:

1. Fazer triagem rápida do procedimento
2. Identificar linhas de investigação
3. Preparar perguntas para oitivas
4. Levantar dados em fontes abertas (OSINT)
5. Redigir ofício para órgão público
6. Redigir despacho simples
7. Verificar prescrição em tese
8. Produzir relatório parcial
9. Preparar minuta de representação cautelar
10. Apenas organizar e indexar os autos por ora
```

### 5.2 Perguntas orientadoras iniciais

Após a carga do inquérito, o sistema pode solicitar respostas rápidas do usuário para calibrar os agentes:

```text
Há suspeitos já identificados? [sim/não]
Já houve oitivas? [sim/não]
O caso aparenta ter boa chance de elucidação? [alta/média/baixa]
O objetivo imediato é: [triagem/diligência/oitiva/ofício/relatório/cautelar/OSINT]
Há urgência por prescrição? [sim/não]
```

### 5.3 Estados do inquérito

Cada procedimento deve possuir um estado operacional, por exemplo:

- `recebido`
- `triagem_inicial`
- `investigacao_preliminar`
- `investigacao_ativa`
- `diligencias_externas`
- `analise_final`
- `preparacao_relatorio`
- `encerrado`
- `aguardando_resposta_externa`
- `arquivamento_sugerido`

Cada estado libera ou restringe agentes e ações.

---

## 6. Arquitetura de agentes

### 6.1 Agente Orquestrador Investigativo

**Missão:** controlar o fluxo do procedimento, registrar o estado atual e acionar os agentes corretos conforme a escolha do usuário.

**Entradas:**
- estado do inquérito;
- objetivo do usuário;
- dados já extraídos dos autos.

**Saídas:**
- menu de ações disponíveis;
- tarefa encaminhada ao agente competente;
- trilha de auditoria.

**Bloqueios:**
- não executar ação incompatível com o estado;
- não prosseguir para redação final sem auditoria factual.

---

### 6.2 Agente de Triagem Inicial

**Missão:** oferecer visão panorâmica do procedimento.

**Entradas:** autos importados.

**Processamento:**
- resumir fato investigado;
- identificar datas principais;
- listar peças localizadas;
- apontar lacunas evidentes.

**Saídas:**
- resumo inicial;
- quadro de pessoas citadas;
- cronologia preliminar;
- alertas (ex.: documentos ilegíveis, peças repetidas, ausência de oitiva da vítima).

**Bloqueios:**
- não concluir autoria;
- não tipificar de forma fechada sem base mínima.

---

### 6.3 Agente de Linhas de Investigação

**Missão:** sugerir hipóteses investigativas plausíveis a partir dos autos.

**Entradas:**
- autos indexados;
- triagem;
- OSINT, se houver;
- orientação do usuário.

**Processamento:**
- localizar contradições;
- identificar beneficiários aparentes;
- correlacionar documentos, pessoas e eventos;
- classificar hipóteses por força probatória.

**Saídas:**
- linhas de investigação classificadas em:
  - fortemente apoiadas nos autos;
  - plausíveis, dependentes de diligência;
  - residuais.

**Bloqueios:**
- não afirmar culpa;
- não atribuir participação sem referência documental;
- não criar nomes ou vínculos não localizados.

---

### 6.4 Agente de Perguntas para Oitivas

**Missão:** elaborar perguntas pertinentes para testemunhas, vítimas, investigados, servidores, representantes de empresa etc.

**Entradas:**
- perfil da pessoa a ser ouvida;
- linha investigativa selecionada;
- contradições e lacunas dos autos.

**Processamento:**
- adaptar roteiro ao papel da pessoa;
- separar perguntas prioritárias e subsidiárias;
- relacionar documentos a serem confrontados.

**Saídas:**
- objetivo da oitiva;
- perguntas por tópicos;
- pontos de confronto;
- observações de cautela.

**Bloqueios:**
- não partir de premissa fática inexistente;
- não formular perguntas capciosas baseadas em dado não confirmado.

---

### 6.5 Agente de Diligências Necessárias

**Missão:** sugerir diligências úteis com base no estágio do inquérito.

**Entradas:**
- linhas investigativas;
- lacunas probatórias;
- respostas de órgãos já existentes;
- estado do procedimento.

**Saídas:**
- lista priorizada de diligências;
- objetivo de cada diligência;
- impacto esperado;
- dependências prévias.

**Bloqueios:**
- não sugerir diligência invasiva sem justa causa mínima;
- não repetir diligência já cumprida, salvo se houver motivo explícito.

---

### 6.6 Agente Redator de Ofícios

**Missão:** produzir minutas de ofícios para órgãos públicos e entidades privadas com solicitações objetivas.

**Entradas:**
- órgão destinatário;
- objetivo da requisição;
- dados já conhecidos;
- período de interesse;
- base fática do pedido.

**Saídas:**
- minuta de ofício com:
  - identificação do inquérito;
  - síntese do caso;
  - delimitação precisa do que se requer;
  - prazo ou urgência, se cabível.

**Bloqueios:**
- não pedir informação vaga;
- não incluir fundamento fático sem referência;
- não solicitar dado incompatível com a finalidade informada.

---

### 6.7 Agente de OSINT / Fontes Abertas

**Missão:** pesquisar fontes públicas na internet para subsidiar a investigação.

**Entradas:**
- nome de pessoa;
- empresa;
- CNPJ;
- e-mail;
- telefone;
- endereço;
- placas ou outros identificadores fornecidos pelo usuário ou já constantes dos autos.

**Fontes-alvo:**
- buscadores gerais;
- diários oficiais;
- juntas comerciais e bases empresariais públicas;
- portais governamentais e transparência;
- sites institucionais;
- redes sociais públicas;
- notícias e publicações abertas.

**Saídas:**
- relatório OSINT estruturado;
- fontes encontradas;
- possíveis vínculos públicos;
- dados úteis para diligências ou oitivas.

**Bloqueios:**
- jamais utilizar dados vazados, invasão de conta, quebra de senha ou conteúdo protegido;
- diferenciar fato localizado de inferência;
- armazenar URL e data/hora da coleta.

---

### 6.8 Agente de Cronologia e Mapa Relacional

**Missão:** montar linha do tempo e mapa lógico entre pessoas, empresas, documentos e eventos.

**Saídas:**
- cronologia preliminar ou consolidada;
- eventos sem data clara;
- pessoas ligadas a eventos/documentos;
- conflitos entre versões.

**Bloqueios:**
- não preencher datas ausentes por suposição.

---

### 6.9 Agente de Tipificação Provisória

**Missão:** sugerir enquadramentos penais provisórios em linguagem prudente.

**Saídas:**
- tipos penais em tese aplicáveis;
- elementos típicos ainda dependentes de prova;
- hipóteses alternativas.

**Bloqueios:**
- não fechar imputação sem apoio probatório;
- não confundir indício com prova acabada.

---

### 6.10 Agente de Representações por Medidas Cautelares

**Missão:** quando expressamente solicitado, redigir minuta de representação por medida cautelar.

**Entradas:**
- tipo de medida;
- elementos de necessidade e adequação;
- fundamentos fáticos já constantes dos autos;
- delimitação objetiva do pedido.

**Saídas:**
- minuta estruturada com fatos, indícios, necessidade, adequação e pedido.

**Bloqueios rígidos:**
- só atuar mediante comando explícito do usuário;
- bloquear pedido sem lastro fático mínimo;
- exigir revisão reforçada por auditor jurídico.

---

### 6.11 Agente de Relatórios

**Missão:** produzir relatório parcial, informação policial, despacho saneador ou relatório final, conforme solicitado.

**Entradas:**
- autos;
- resultados dos outros agentes;
- parâmetros definidos pelo usuário.

**Saídas:**
- peça em linguagem jurídico-formal;
- com referência de documentos e páginas;
- sem extrapolar a prova disponível.

**Bloqueios:**
- não inserir nomes, datas ou conclusões sem suporte.

---

## 7. Camada obrigatória de auditoria

### 7.1 Auditor de Conformidade Fática

**Função:** verificar se cada afirmação relevante consta dos autos ou de fonte pública registrada.

**Regra central:**
> nenhuma informação relevante pode integrar a saída final se não houver suporte identificável.

**Deve validar:**
- nomes;
- CPF/CNPJ;
- datas;
- valores;
- endereços;
- placas;
- empresas;
- eventos;
- vínculos mencionados.

**Ação em caso de falha:**
- remover trecho;
- marcar como hipótese não confirmada; ou
- pedir revisão humana.

---

### 7.2 Auditor de Fonte e Página

**Função:** assegurar que cada dado importante aponte documento/página ou fonte pública coletada.

**Exemplo de formato interno:**

```json
{
  "afirmacao": "A testemunha reconheceu João da Silva como intermediador",
  "suporte": {
    "documento": "Termo de declaração de Maria",
    "arquivo": "Volume 2.pdf",
    "pagina": 18,
    "trecho": "... reconhece João da Silva como a pessoa que..."
  }
}
```

---

### 7.3 Auditor de Prudência Investigativa

**Função:** ajustar a linguagem para o nível real da prova.

**Exemplo:**
- trocar “restou comprovado” por “há indícios de” quando a prova ainda é embrionária;
- trocar “o investigado praticou” por “há elementos informativos que sugerem participação”.

---

### 7.4 Auditor Jurídico-Processual

**Função:** verificar coerência jurídica básica das peças geradas.

**Deve checar:**
- pertinência da diligência;
- adequação do pedido ao objetivo investigativo;
- suficiência mínima para cautelares;
- consistência formal da peça.

---

## 8. Arquitetura técnica sugerida

### 8.1 Frontend

- **Web app:** Next.js ou React
- **Mobile futuro:** React Native ou Flutter

### 8.2 Backend

- **FastAPI** como backend principal
- APIs REST + WebSocket para tarefas assíncronas

### 8.3 Filas e processamento assíncrono

- Celery ou Dramatiq
- Redis para fila e cache

### 8.4 Banco de dados relacional

- PostgreSQL

### 8.5 Banco vetorial

- Qdrant

### 8.6 Extração documental

- PDF text parser nativo quando houver texto incorporado
- OCR apenas quando necessário
- Tesseract ou alternativa mais robusta opcional
- pipeline de separação de páginas e detecção de peças

### 8.7 Armazenamento de arquivos

- S3 compatível (MinIO no ambiente local / cloud storage no deploy)

### 8.8 Autenticação

- login por usuário e senha
- JWT
- controle de papéis (ex.: administrador, analista, leitor)

### 8.9 Observabilidade

- logs estruturados
- trilha de auditoria
- monitoramento de custos por modelo
- monitoramento de latência por agente

---

## 9. Estratégia de modelos (LLMs) por custo e criticidade

### 9.1 Princípio geral

O sistema deve possuir um **roteador de modelos** que selecione o LLM conforme:

- criticidade jurídica da tarefa;
- necessidade de precisão;
- volume da demanda;
- custo alvo por operação;
- urgência/latência.

### 9.2 Classes de tarefas

#### Classe A — tarefas repetitivas, de alto volume e baixo risco
Usar modelos gratuitos, locais ou de baixo custo.

Exemplos:
- classificação de documento;
- extração de metadados simples;
- detecção de entidades;
- deduplicação preliminar;
- resumo mecânico de páginas;
- sugestão inicial de tags;
- roteamento do pedido do usuário.

#### Classe B — tarefas analíticas intermediárias
Usar modelos médios / custo controlado.

Exemplos:
- triagem investigativa;
- formulação de linhas plausíveis;
- perguntas de oitiva;
- OSINT resumido;
- minutas de ofícios e despachos simples.

#### Classe C — tarefas complexas, sensíveis ou juridicamente densas
Usar modelos mais potentes.

Exemplos:
- relatório final;
- representação cautelar;
- confronto complexo entre versões;
- análise de contradições múltiplas;
- revisão final sob prudência jurídica.

---

## 10. Sugestão prática de stack de modelos

### 10.1 Camada econômica / repetitiva

**Preferência 1 — modelos locais (custo marginal próximo de zero)**
- Llama 3.x/4 leves ou equivalentes open-weight via Ollama/vLLM, para:
  - extração simples;
  - classificação;
  - resumo preliminar;
  - tarefas internas não críticas.

**Preferência 2 — APIs muito baratas**
- OpenAI `gpt-4.1-mini` ou `gpt-4.1-nano` para automações repetitivas, quando necessário. A página oficial de preços da OpenAI lista, entre outros, `gpt-4.1-mini` a US$ 0,40 / 1M tokens de entrada e US$ 1,60 / 1M tokens de saída, e `gpt-4.1-nano` em patamar inferior. citeturn0search4turn0search0
- Groq com modelos Llama rápidos e baratos para extração e classificação em alto volume; a página oficial mostra, por exemplo, `Llama 3.1 8B Instant` em US$ 0,05 / 1M tokens de entrada e US$ 0,08 / 1M tokens de saída. citeturn0search3
- Gemini API em Free Tier para prototipação e cargas leves, já que a documentação oficial informa a existência de nível gratuito para certos modelos. citeturn0search9turn0search1

### 10.2 Camada intermediária

- OpenAI `gpt-4.1-mini` para triagem, perguntas e ofícios com boa relação custo/qualidade. citeturn0search4turn0search0
- Claude Haiku 4.5 para redação enxuta e tarefas rápidas; a documentação de preços da Anthropic indica Haiku 4.5 a US$ 1 / MTok de entrada e US$ 5 / MTok de saída. citeturn0search2turn0search14
- Gemini em modelos intermediários quando houver boa janela de custo/desempenho e limites compatíveis com o projeto; a documentação de billing e rate limits deixa claro que há tiers distintos e upgrade por consumo. citeturn0search5turn0search9

### 10.3 Camada premium / tarefas críticas

- OpenAI `gpt-5-codex` para geração/refatoração de código e tarefas de engenharia de software complexas; a página oficial de preços mostra `gpt-5-codex` em US$ 1,25 / 1M tokens de entrada e US$ 10 / 1M tokens de saída. citeturn0search4
- OpenAI `gpt-4.1` para revisões jurídicas/redacionais mais exigentes, quando a diferença de custo fizer sentido. A página oficial lista `gpt-4.1` em US$ 2,00 / 1M tokens de entrada e US$ 8,00 / 1M tokens de saída. citeturn0search4
- Claude Sonnet 4.5 para peças difíceis e raciocínio textual mais sofisticado; a Anthropic lista Sonnet 4.5 em US$ 3 / MTok de entrada e US$ 6 / MTok de saída. citeturn0search2

### 10.4 Regra de roteamento sugerida

```text
Se tarefa = classificação / extração / resumo mecânico
    usar modelo local ou API ultrabarata

Se tarefa = triagem / perguntas / ofício / OSINT resumido
    usar modelo intermediário

Se tarefa = cautelar / relatório final / confronto complexo / revisão final
    usar modelo premium + auditoria dupla
```

### 10.5 Recomendação objetiva de combinação inicial

**Combinação MVP econômica:**
- Local/Ollama para classificação e pré-processamento
- OpenAI `gpt-4.1-mini` para triagem, perguntas e ofícios
- OpenAI `gpt-4.1` ou Claude Sonnet 4.5 para relatórios e cautelares

**Combinação MVP com custo mínimo possível:**
- Local/Ollama + Groq para tarefas repetitivas
- Gemini Free Tier para protótipos e testes controlados
- apenas 1 modelo premium reservado ao fechamento de peças complexas

> Importante: implementar configuração por variáveis de ambiente para alternar provedores sem reescrever a aplicação.

---

## 11. Requisitos de engenharia para o código

### 11.1 Requisitos obrigatórios

- backend em FastAPI
- arquitetura modular por domínios
- separação entre camada de agentes, serviços e persistência
- roteador de LLMs desacoplado do restante do sistema
- logs estruturados
- testes automatizados
- suporte a feature flags para ligar/desligar agentes
- auditoria persistida em banco
- exportação em Markdown inicialmente
- pronta evolução para DOCX/PDF

### 11.2 Estrutura sugerida de pastas

```text
app/
  api/
  core/
  agents/
    orchestrator/
    triage/
    investigation_lines/
    interview_questions/
    diligence/
    official_letters/
    osint/
    chronology/
    legal_typing/
    cautions/
    reports/
    auditors/
  services/
    llm_router/
    embeddings/
    ocr/
    pdf/
    storage/
    auth/
    export/
  db/
  models/
  schemas/
  workers/
  tests/
```

---

## 12. Entidades principais do banco de dados

### 12.1 Caso / Inquérito
Campos mínimos:
- id
- número
- delegacia
- ano
- estado_atual
- prioridade
- chance_estimada (manual)
- objetivo_atual
- criado_em
- atualizado_em

### 12.2 Documento
- id
- inquerito_id
- nome_arquivo
- tipo_documento
- hash
- paginas
- texto_extraido
- status_ocr
- duplicado_de

### 12.3 Pessoa
- id
- inquerito_id
- nome
- tipo_pessoa (testemunha, vítima, investigado etc.)
- cpf
- observacoes

### 12.4 Evento cronológico
- id
- inquerito_id
- data_evento
- descricao
- fonte_documental
- pagina
- confiabilidade

### 12.5 Tarefa / Ação do usuário
- id
- inquerito_id
- agente
- comando_usuario
- status
- custo_estimado
- modelo_utilizado
- criado_em

### 12.6 Achado OSINT
- id
- inquerito_id
- entidade_pesquisada
- fonte
- url
- data_coleta
- descricao
- confiabilidade

### 12.7 Registro de auditoria
- id
- tarefa_id
- tipo_auditoria
- status
- inconsistencias
- aprovado_por_usuario

---

## 13. Endpoints sugeridos

### Inquéritos
- `POST /cases/upload`
- `GET /cases/{id}`
- `POST /cases/{id}/set-state`
- `POST /cases/{id}/set-priority`
- `GET /cases/{id}/menu`

### Documentos
- `POST /documents/ingest`
- `GET /documents/{id}`
- `POST /documents/{id}/reprocess`

### Agentes
- `POST /agents/triage/run`
- `POST /agents/investigation-lines/run`
- `POST /agents/interview-questions/run`
- `POST /agents/diligence/run`
- `POST /agents/official-letter/run`
- `POST /agents/osint/run`
- `POST /agents/cautionary-motion/run`
- `POST /agents/report/run`

### Auditoria
- `POST /audit/factual`
- `POST /audit/legal`
- `GET /audit/task/{id}`

### Exportação
- `POST /export/markdown`
- `POST /export/docx`
- `POST /export/pdf`

---

## 14. Regras de negócio críticas

1. O sistema **não pode executar automaticamente todos os agentes** ao importar um inquérito.
2. O sistema deve sempre **apresentar um menu inicial de possibilidades**.
3. Nenhum nome próprio novo pode surgir na saída final se não estiver nos autos ou nas fontes abertas registradas.
4. Toda peça final deve guardar referência de origem dos fatos centrais.
5. Toda tarefa deve registrar:
   - modelo utilizado;
   - custo estimado;
   - tempo de execução;
   - resultado da auditoria.
6. Medidas cautelares só podem ser geradas por comando explícito do usuário.
7. O agente de perguntas deve considerar o papel processual/fático da pessoa a ser ouvida.
8. O agente OSINT deve respeitar integralmente limites legais e éticos de pesquisa em fontes abertas.

---

## 15. Roadmap sugerido

### Fase 1 — Base documental
- upload
- OCR
- parser PDF
- indexação vetorial
- menu inicial por inquérito
- triagem preliminar

### Fase 2 — Núcleo investigativo
- linhas de investigação
- perguntas para oitivas
- diligências necessárias
- cronologia

### Fase 3 — Peças operacionais
- ofícios
- despachos
- relatórios parciais
- OSINT

### Fase 4 — Alta complexidade
- cautelares
- relatório final
- tipificação provisória
- dashboard gerencial
- controle de prescrição

---

## 16. Prompt mestre para o modelo de geração de código

```text
Você é o arquiteto principal deste aplicativo.
Implemente um sistema web de apoio à análise investigativa de inquéritos policiais, conforme esta especificação.

Requisitos obrigatórios:
1. Backend em FastAPI.
2. Arquitetura modular por agentes.
3. Estado do inquérito controlado por máquina de estados.
4. Upload e ingestão de PDFs/imagens.
5. OCR somente quando necessário.
6. Banco relacional PostgreSQL.
7. Banco vetorial Qdrant.
8. Roteador de LLMs desacoplado, com suporte a múltiplos provedores.
9. Auditoria factual obrigatória antes da saída final.
10. Menu inicial de possibilidades após carga do inquérito.
11. Geração assistida de perguntas para oitivas, ofícios, relatórios e cautelares.
12. Módulo OSINT apenas para fontes abertas públicas.
13. Persistir trilha de auditoria, modelo usado, custo estimado e estado do inquérito.
14. Escrever código limpo, tipado, testável e pronto para expansão.

Entregue em etapas:
- estrutura de pastas
- modelos de dados
- endpoints
- serviços de ingestão
- roteador de LLMs
- agentes principais
- auditores
- testes iniciais
- documentação de instalação

Sempre priorize segurança, rastreabilidade e separação de responsabilidades.
Nunca implemente geração automática irrestrita. O usuário deve escolher o próximo passo do inquérito.
```

---

## 17. Critérios de aceite

O produto será considerado aderente quando:

- importar um inquérito e perguntar ao usuário como deseja prosseguir;
- gerar ao menos 4 tipos de saída úteis (triagem, perguntas, ofício, relatório parcial);
- impedir inclusão de dados não encontrados;
- registrar auditoria de cada tarefa;
- alternar entre pelo menos 2 provedores/modelos via configuração;
- manter custo baixo nas tarefas repetitivas e reservar modelos premium para tarefas críticas.

---

## 18. Observações finais para implementação

- priorizar backend primeiro, frontend simples depois;
- começar com exportação em Markdown e JSON estruturado;
- só depois evoluir para DOCX/PDF sofisticado;
- tratar o aplicativo como **sistema de apoio à decisão investigativa**, não como substituto da autoridade policial;
- preservar linguagem prudente: fatos, indícios, hipóteses e conclusões devem permanecer semanticamente distintos.
