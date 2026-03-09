# Escrivão AI — Identificação de Delegacia de Origem e Redistribuição de Inquérito

## 1. Contexto Institucional

No Estado do Rio de Janeiro, o número do **Inquérito Policial (IP)** possui um formato padronizado:

DDD-NNNNNN/AAAA

Onde:

| Parte | Significado |
|-----|-------------|
| DDD | Código da delegacia que instaurou o inquérito |
| NNNNNN | Número sequencial do procedimento |
| AAAA | Ano de instauração |

### Exemplo

921-00198/2016

| Campo | Valor |
|-----|------|
| Delegacia de origem | 921 |
| Sequencial | 00198 |
| Ano | 2016 |

## Regra institucional importante

Uma vez instaurado, **o número do inquérito nunca é alterado**, mesmo que o procedimento seja redistribuído para outra delegacia.

Portanto:

- delegacia de origem é **imutável**
- delegacia atual pode mudar.

### Exemplo real

| Campo | Valor |
|------|------|
| IP | 921-00198/2016 |
| Delegacia de origem | Delegacia Fazendária |
| Delegacia atual | 10ª DEAC |

---

# 2. Modelagem de Dados

O sistema deve registrar duas informações distintas:

| Campo | Tipo | Descrição |
|------|------|-----------|
| delegacia_origem_codigo | string | Código da delegacia que instaurou o IP |
| delegacia_origem_nome | string | Nome da delegacia de origem |
| delegacia_atual_codigo | string | Código da delegacia que atualmente conduz o IP |
| delegacia_atual_nome | string | Nome da delegacia atual |
| redistribuido | boolean | Indica se houve redistribuição |

---

# 3. Alterações no Modelo de Inquérito

Exemplo em SQLAlchemy:

```python
class Inquerito(Base):
    __tablename__ = "inqueritos"

    id = Column(UUID, primary_key=True)

    numero = Column(String, unique=True)

    delegacia_origem_codigo = Column(String)
    delegacia_origem_nome = Column(String)

    delegacia_atual_codigo = Column(String)
    delegacia_atual_nome = Column(String)

    redistribuido = Column(Boolean, default=False)
 4. Função de Parsing do Número do IP

Implementar função:

def parse_inquerito(numero_ip: str):
Exemplo de entrada
921-00198/2016
Saída esperada
{
 "delegacia_codigo": "921",
 "sequencial": "00198",
 "ano": "2016"
}
5. Tabela de Delegacias

Criar tabela de referência.

SQL
CREATE TABLE delegacias (

    codigo VARCHAR(3) PRIMARY KEY,
    nome TEXT NOT NULL,
    tipo TEXT,
    municipio TEXT,
    departamento TEXT

);
6. Exemplos de Delegacias
Código	Delegacia	Tipo
911	Delegacia de Defraudações	especializada
912	Delegacia de Roubos e Furtos	especializada
913	Delegacia de Roubos e Furtos de Automóveis	especializada
914	Delegacia de Repressão a Entorpecentes	especializada
915	Delegacia de Homicídios da Capital	especializada
918	Delegacia de Crimes contra o Consumidor	especializada
919	Delegacia de Roubos e Furtos de Carga	especializada
920	Delegacia de Crimes contra o Meio Ambiente	especializada
921	Delegacia Fazendária	especializada
059	59ª DP Duque de Caxias	territorial
064	64ª DP São João de Meriti	territorial
072	72ª DP São Gonçalo	territorial
077	77ª DP Icaraí	territorial
105	105ª DP Petrópolis	territorial
7. Fluxo de Cadastro do Inquérito

Quando um usuário cadastrar um IP:

Usuário informa número do inquérito

Sistema executa parse_inquerito

Sistema identifica automaticamente a delegacia de origem

Delegacia atual recebe o mesmo valor inicialmente

Exemplo:

IP: 921-00198/2016

Resultado:

Campo	Valor
delegacia_origem_codigo	921
delegacia_origem_nome	Delegacia Fazendária
delegacia_atual_codigo	921
delegacia_atual_nome	Delegacia Fazendária
8. Suporte à Redistribuição

Na interface deve existir uma opção:

[ ] Inquérito redistribuído

Se marcada:

abrir campo adicional:

Delegacia atual

Esse campo deve ser um dropdown populado pela tabela delegacias.

9. Exemplo de Inquérito Redistribuído

IP:

921-00198/2016
Campo	Valor
delegacia_origem_codigo	921
delegacia_origem_nome	Delegacia Fazendária
redistribuido	true
delegacia_atual_codigo	910
delegacia_atual_nome	10ª DEAC
10. Regras de Integridade

delegacia_origem nunca pode ser alterada após criação do IP

delegacia_atual pode ser alterada apenas se redistribuido = true

11. Ajustes na API

Endpoints afetados:

POST /inqueritos
PATCH /inqueritos/{id}

Validações obrigatórias:

delegacia_origem deve ser calculada pelo sistema

não pode ser enviada pelo frontend

delegacia_atual pode ser alterada pelo usuário

12. Ajustes na Interface

Tela de cadastro do inquérito:

Campo	Tipo
Número do IP	input
Delegacia de origem	automático
Redistribuído	checkbox
Delegacia atual	dropdown
13. Benefícios para o Sistema

Essa implementação permitirá ao Escrivão AI:

interpretar automaticamente o número do inquérito

identificar delegacia de origem

registrar redistribuições

gerar estatísticas por delegacia

manter consistência institucional do procedimento

14. Exemplo de Uso

Entrada:

parse_inquerito("921-00198/2016")

Resultado:

Delegacia de origem: Delegacia Fazendária
Sequencial: 198
Ano: 2016
15. Resultado Esperado

O sistema passa a representar corretamente a tramitação real dos inquéritos policiais no Estado do Rio de Janeiro, preservando a delegacia de origem e registrando redistribuições entre unidades policiais.


---

Valdir, se quiser, posso também gerar **um segundo `.md` muito importante para o seu sistema**:

**`delegacias_pc_rj_completa.md`**

com **todas as delegacias da Polícia Civil do RJ (mais de 150)** já organizadas em:

- SQL
- JSON
- tabela de referência

Isso permitiria ao Escrivão AI **reconhecer automaticamente qualquer inquérito do estado**.   