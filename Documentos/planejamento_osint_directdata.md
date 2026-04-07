# Planejamento: Integração direct.data no Agente OSINT do Escrivão AI

**Data:** 20/03/2026
**Versão:** 1.0
**Contexto:** O agente `AgenteFicha` atual usa apenas dados internos do banco (Pessoa, Empresa, Contato, Endereço, EventoCronológico). Este plano detalha como enriquecê-lo com APIs externas do direct.data para consultas cadastrais, de restrições, veiculares e processuais em tempo real.

---

## 1. Estado Atual do Agente OSINT

O `AgenteFicha` em `backend/app/services/agente_ficha.py` opera da seguinte forma:

1. Busca no banco: Pessoa/Empresa → Contatos → Endereços → Eventos
2. Monta texto consolidado com os dados internos
3. Envia ao LLM Premium (tier premium) via `PROMPT_FICHA_PESSOA` / `PROMPT_FICHA_EMPRESA`
4. Persiste resultado em `ResultadoAgente`

**Limitação crítica:** A ficha é gerada apenas com o que já foi extraído dos documentos do inquérito. Se o suspeito não foi mencionado em nenhum documento, a ficha fica vazia. Sem CPF validado, sem antecedentes, sem vínculos empresariais reais.

---

## 2. APIs direct.data Prioritárias para Investigação Policial

### Prioridade 1 — Essenciais (implementar primeiro)

| API | Categoria | Uso investigativo | Preço est. |
|-----|-----------|-------------------|------------|
| `ConsultaCPF` | Cadastral | Validar CPF, nome completo, data nasc., situação | ~R$0,64 |
| `ConsultaCPF_Completo` | Cadastral | Nome, parentes, histórico de endereços, renda estimada | ~R$2,50 |
| `ConsultaCNPJ` | Cadastral | Quadro societário, atividade, situação na Receita | ~R$0,64 |
| `VinculosEmpresariais` | Cadastral | Empresas onde o CPF é sócio/administrador | ~R$1,20 |
| `CEIS` | Sanções | Cadastro de Empresas Inidôneas e Suspensas (CGU) | ~R$0,36 |
| `CNEP` | Sanções | Cadastro Nacional de Empresas Punidas (CGU) | ~R$0,36 |
| `CEPIM` | Sanções | Entidades impedidas de receber recursos federais | ~R$0,36 |

### Prioridade 2 — Alto valor investigativo

| API | Categoria | Uso investigativo | Preço est. |
|-----|-----------|-------------------|------------|
| `ConsultaPlaca` | Veicular | Dados do veículo a partir da placa | ~R$0,72 |
| `ConsultaProprietarioVeiculo` | Veicular | CPF/CNPJ do proprietário atual do veículo | ~R$0,90 |
| `ProcessosTribunais` | Processos | Ações cíveis/criminais nos TJs estaduais | ~R$2,00 |
| `ProcessosTRF` | Processos | Ações na Justiça Federal (TRFs) | ~R$2,00 |
| `OfacSDN` | Sanções Internacionais | Lista de sancionados do Tesouro dos EUA | ~R$0,36 |
| `ListaONU` | Sanções Internacionais | Sanções do Conselho de Segurança da ONU | ~R$0,36 |

### Prioridade 3 — Complementares (Sprint futura)

| API | Categoria | Uso investigativo |
|-----|-----------|-------------------|
| `ConsultaScore` | Crédito | Perfil financeiro do investigado |
| `DividasAtivas` | Fiscal | Dívidas com a União |
| `SituacaoCadastral` | Fiscal | Situação na Receita Federal |
| `PatrimonioImoveis` | Cadastral | Imóveis registrados em nome da pessoa |
| `BensDeclTransparencia` | Fiscal | Declarações de bens de servidores públicos |

---

## 3. Arquitetura Proposta

### 3.1 Novo serviço: `DirectDataService`

Criar `backend/app/services/directdata_service.py`:

```python
"""
Escrivão AI — DirectData Service
Wrapper para as APIs do direct.data (Big Data Corp).
Documentação: https://api.bigdatacorp.com.br
"""
import httpx
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

DIRECTDATA_BASE_URL = "https://bigdatacorp.com.br/api/v1"  # confirmar na doc

class DirectDataService:
    def __init__(self):
        from app.core.config import settings
        self.token = settings.DIRECTDATA_API_TOKEN  # Bearer token
        self.base = settings.DIRECTDATA_BASE_URL
        self.client = httpx.AsyncClient(
            base_url=self.base,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=20.0,
        )

    async def consultar_cpf(self, cpf: str) -> Dict[str, Any]:
        """Retorna dados cadastrais básicos do CPF."""
        cpf_limpo = cpf.replace(".", "").replace("-", "").replace("/", "")
        resp = await self.client.get(f"/pessoas/cpf/{cpf_limpo}")
        resp.raise_for_status()
        return resp.json()

    async def consultar_cpf_completo(self, cpf: str) -> Dict[str, Any]:
        """Retorna dados cadastrais ampliados (parentes, endereços históricos, renda)."""
        cpf_limpo = cpf.replace(".", "").replace("-", "").replace("/", "")
        resp = await self.client.get(f"/pessoas/cpf/{cpf_limpo}/completo")
        resp.raise_for_status()
        return resp.json()

    async def consultar_cnpj(self, cnpj: str) -> Dict[str, Any]:
        """Retorna dados da empresa: QSA, atividade, situação."""
        cnpj_limpo = cnpj.replace(".", "").replace("-", "").replace("/", "")
        resp = await self.client.get(f"/empresas/cnpj/{cnpj_limpo}")
        resp.raise_for_status()
        return resp.json()

    async def consultar_vinculos_empresariais(self, cpf: str) -> Dict[str, Any]:
        """Lista empresas onde o CPF aparece como sócio ou administrador."""
        cpf_limpo = cpf.replace(".", "").replace("-", "").replace("/", "")
        resp = await self.client.get(f"/pessoas/cpf/{cpf_limpo}/vinculos")
        resp.raise_for_status()
        return resp.json()

    async def consultar_sancoes(self, documento: str) -> Dict[str, Any]:
        """
        Consulta simultânea em CEIS, CNEP e CEPIM.
        documento pode ser CPF ou CNPJ.
        """
        doc_limpo = documento.replace(".", "").replace("-", "").replace("/", "")
        resp = await self.client.get(f"/sancoes/{doc_limpo}")
        resp.raise_for_status()
        return resp.json()

    async def consultar_placa(self, placa: str) -> Dict[str, Any]:
        """Retorna dados do veículo pela placa."""
        resp = await self.client.get(f"/veiculos/placa/{placa.upper()}")
        resp.raise_for_status()
        return resp.json()

    async def consultar_processos(self, documento: str) -> Dict[str, Any]:
        """Busca processos judiciais pelo CPF ou CNPJ."""
        doc_limpo = documento.replace(".", "").replace("-", "").replace("/", "")
        resp = await self.client.get(f"/processos/{doc_limpo}")
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self.client.aclose()
```

### 3.2 Modelo de auditoria: `ConsultaExterna`

Criar migration e model para registrar cada consulta paga:

```python
# backend/app/models/consulta_externa.py
class ConsultaExterna(Base):
    __tablename__ = "consultas_externas"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    inquerito_id = Column(UUID, ForeignKey("inqueritos.id", ondelete="CASCADE"))
    tipo_consulta = Column(String)       # "cpf_completo", "sancoes", "placa", etc.
    documento_consultado = Column(String) # CPF/CNPJ mascarado
    custo_estimado = Column(Numeric(10,4))
    resultado_json = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)
```

Isso serve para: rastrear custos por inquérito, evitar consultas duplicadas (cache), e auditoria de uso do sistema.

### 3.3 Extensão do `AgenteFicha`

Adicionar método `enriquecer_pessoa_externa` ao `AgenteFicha`:

```python
async def enriquecer_pessoa_externa(
    self,
    db: AsyncSession,
    inquerito_id: uuid.UUID,
    pessoa_id: uuid.UUID,
) -> Dict[str, Any]:
    """
    Consulta APIs externas do direct.data para enriquecer ficha de pessoa.
    Retorna dict com dados externos consolidados.
    """
    pessoa = await db.get(Pessoa, pessoa_id)
    if not pessoa or not pessoa.cpf:
        return {"erro": "CPF não disponível para consulta externa"}

    directdata = DirectDataService()
    enriquecimento = {}

    try:
        enriquecimento["cadastral"] = await directdata.consultar_cpf_completo(pessoa.cpf)
    except Exception as e:
        logger.warning(f"[OSINT] CPF completo falhou: {e}")
        try:
            enriquecimento["cadastral"] = await directdata.consultar_cpf(pessoa.cpf)
        except Exception:
            pass

    try:
        enriquecimento["vinculos_empresariais"] = await directdata.consultar_vinculos_empresariais(pessoa.cpf)
    except Exception as e:
        logger.warning(f"[OSINT] Vínculos empresariais falhou: {e}")

    try:
        enriquecimento["sancoes"] = await directdata.consultar_sancoes(pessoa.cpf)
    except Exception as e:
        logger.warning(f"[OSINT] Sanções falhou: {e}")

    try:
        enriquecimento["processos"] = await directdata.consultar_processos(pessoa.cpf)
    except Exception as e:
        logger.warning(f"[OSINT] Processos falhou: {e}")

    await directdata.close()

    # Persistir auditoria
    registro_auditoria = ConsultaExterna(
        inquerito_id=inquerito_id,
        tipo_consulta="enriquecimento_completo_pessoa",
        documento_consultado=f"***{pessoa.cpf[-4:]}",
        custo_estimado=Decimal("4.70"),  # estimativa conservadora
        resultado_json=enriquecimento,
    )
    db.add(registro_auditoria)
    await db.commit()

    return enriquecimento
```

Depois, o método `gerar_ficha_pessoa` recebe os dados externos e os inclui no contexto enviado ao LLM:

```python
# Dados internos (já existem)
dados_internos = f"... {contatos} {enderecos} {eventos} ..."

# Dados externos (novo)
dados_externos = json.dumps(enriquecimento, ensure_ascii=False, indent=2)

prompt = PROMPT_FICHA_PESSOA.format(
    nome=pessoa.nome,
    dados_internos=dados_internos,
    dados_externos=dados_externos,   # NOVO
)
```

---

## 4. Mudanças nos Prompts

### `PROMPT_FICHA_PESSOA` (atualizado)

```
Você é um agente de inteligência policial especializado em análise de suspeitos.
Com base nos dados internos extraídos do inquérito E nos dados externos de fontes
oficiais e cadastrais, produza uma ficha investigativa completa de {nome}.

=== DADOS INTERNOS (extraídos do inquérito) ===
{dados_internos}

=== DADOS EXTERNOS (direct.data — consulta em tempo real) ===
{dados_externos}

Produza um JSON com a estrutura:
{{
  "resumo_executivo": "...",
  "qualificacao_completa": {{
    "nome": "...",
    "cpf": "...",
    "data_nascimento": "...",
    "naturalidade": "...",
    "filiacao": ["...", "..."]
  }},
  "enderecos_historicos": [...],
  "vinculos_empresariais": [...],
  "sancoes_restricoes": {{
    "ceis": bool,
    "cnep": bool,
    "cepim": bool,
    "detalhes": "..."
  }},
  "processos_judiciais": [...],
  "nivel_risco": "baixo|medio|alto|critico",
  "justificativa_risco": "...",
  "pontos_de_atencao": [...],
  "sugestoes_diligencias": [...]
}}
```

---

## 5. Novos Endpoints REST

### `POST /agentes/osint/enriquecer/pessoa/{pessoa_id}`
Consulta APIs externas e retorna dados brutos (sem LLM). Útil para preview antes de gerar a ficha.

### `POST /agentes/ficha/pessoa/{pessoa_id}?inquerito_id=...&usar_dados_externos=true`
Extensão do endpoint existente com flag opcional `usar_dados_externos` (default: `false` para não gerar custo automático).

### `GET /inqueritos/{inquerito_id}/consultas-externas`
Lista auditoria de consultas pagas do inquérito com custo acumulado.

---

## 6. Configuração e Variáveis de Ambiente

Adicionar ao `.env` e ao serviço Railway:

```env
# direct.data / BigDataCorp
DIRECTDATA_API_TOKEN=seu_token_aqui
DIRECTDATA_BASE_URL=https://api.bigdatacorp.com.br  # confirmar endpoint correto
DIRECTDATA_AMBIENTE=producao  # ou homologacao para testes
```

Adicionar ao `backend/app/core/config.py`:

```python
DIRECTDATA_API_TOKEN: str = ""
DIRECTDATA_BASE_URL: str = "https://api.bigdatacorp.com.br"
```

---

## 7. Fases de Implementação

### Fase 1 — Fundação (próxima sprint)
1. Criar `DirectDataService` com os 4 endpoints de Prioridade 1 (CPF, CNPJ, Vínculos, Sanções)
2. Criar model `ConsultaExterna` + migration Alembic
3. Criar `enriquecer_pessoa_externa()` no `AgenteFicha`
4. Endpoint `POST /agentes/osint/enriquecer/pessoa/{id}` (sem LLM, dados brutos)
5. Testar em homologação com CPFs/CNPJs de domínio público (políticos, empresas públicas)

### Fase 2 — Integração com Ficha LLM
1. Atualizar `PROMPT_FICHA_PESSOA` e `PROMPT_FICHA_EMPRESA` com seção de dados externos
2. Adicionar flag `usar_dados_externos=true` ao endpoint existente de ficha
3. UI: botão "Enriquecer com OSINT externo" na ficha da pessoa (com aviso de custo)
4. Endpoint de auditoria: `GET /inqueritos/{id}/consultas-externas`

### Fase 3 — OSINT Veicular e Processos
1. Adicionar `consultar_placa()` e `consultar_processos()` ao serviço
2. Nova aba "Veículos" na ficha (para placas encontradas nos documentos)
3. Integrar processos judiciais ao `nivel_risco` do prompt

### Fase 4 — Sprint 6 completa (OSINT Dashboard)
1. Painel de custo OSINT por inquérito
2. Cache de consultas (evitar cobrar duas vezes pelo mesmo CPF no mesmo inquérito)
3. Sanções internacionais (OFAC/ONU) automáticas para crimes financeiros
4. Agente autônomo: dado um inquérito, identifica automaticamente quais pessoas têm CPF e dispara enriquecimento em lote (com aprovação do usuário)

---

## 8. Considerações Técnicas

### Cache para evitar custos duplicados
Antes de chamar a API, verificar `ConsultaExterna` no banco:

```python
async def _consulta_ja_existe(self, db, inquerito_id, tipo, documento):
    """Retorna resultado cacheado se consultado nas últimas 24h."""
    cutoff = datetime.utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(ConsultaExterna)
        .where(ConsultaExterna.inquerito_id == inquerito_id)
        .where(ConsultaExterna.tipo_consulta == tipo)
        .where(ConsultaExterna.documento_consultado.contains(documento[-4:]))
        .where(ConsultaExterna.created_at > cutoff)
    )
    return result.scalar_one_or_none()
```

### Tratamento de erros
- **404 Not Found**: CPF/CNPJ não encontrado na base → retornar `{"encontrado": false}`
- **402 / quota excedida**: Logar e retornar erro amigável ao usuário
- **Timeout**: `httpx.TimeoutException` → não bloquear geração da ficha, continuar com dados internos

### Mascaramento de dados sensíveis
Os CPFs consultados devem ser mascarados ao persistir a auditoria:
`***.***.XXX-XX` → `***{cpf[-4:]}`

### LGPD / Sigilo Policial
Os resultados das consultas externas são dados sensíveis. O model `ConsultaExterna` deve ter `ondelete="CASCADE"` para ser removido junto com o inquérito (já tratado no endpoint de exclusão implementado).

---

## 9. Estimativa de Custo por Inquérito

| Operação | APIs chamadas | Custo estimado |
|----------|---------------|----------------|
| Enriquecimento básico de 1 pessoa | CPF + Sanções | ~R$1,00 |
| Enriquecimento completo de 1 pessoa | CPF Completo + Vínculos + Sanções + Processos | ~R$5,00 |
| Inquérito com 5 suspeitos (completo) | × 5 | ~R$25,00 |
| Consulta veicular (1 placa) | Placa + Proprietário | ~R$1,62 |

Para inquéritos complexos (lavagem, organização criminosa) com 10+ suspeitos, o custo OSINT por inquérito ficaria em torno de **R$50–R$100** — marginal para o valor investigativo gerado.

---

## 10. Arquivos a Criar/Modificar

| Arquivo | Ação |
|---------|------|
| `backend/app/services/directdata_service.py` | **Criar** |
| `backend/app/models/consulta_externa.py` | **Criar** |
| `backend/app/services/agente_ficha.py` | **Modificar** — adicionar enriquecimento externo |
| `backend/app/core/prompts.py` | **Modificar** — atualizar PROMPT_FICHA_PESSOA e PROMPT_FICHA_EMPRESA |
| `backend/app/api/agentes.py` | **Modificar** — adicionar endpoint de enriquecimento |
| `backend/app/core/config.py` | **Modificar** — adicionar variáveis DIRECTDATA_* |
| `backend/alembic/versions/xxx_add_consultas_externas.py` | **Criar** — migration |
| `.env.example` | **Modificar** — documentar novas vars |

---

*Próximo passo imediato: confirmar a URL base real da API direct.data e o formato de autenticação (Bearer token ou API Key em header?) antes de escrever o `DirectDataService`.*
