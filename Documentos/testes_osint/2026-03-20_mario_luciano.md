# Teste OSINT — Mario Luciano Pereira da Silva

**Data:** 20/03/2026 19:23
**Inquérito:** TEMP-5D39B8/2026
**CPF consultado:** 933.059.827-72
**Fonte:** direct.data API v3

---

## Qualificação

| Campo | Dado |
|---|---|
| Nome completo | Mario Luciano Pereira da Silva |
| CPF | 933.059.827-72 |
| Sexo | Masculino |
| Data de nascimento | 22/10/1967 (58 anos) |
| Nome da mãe | Celina Pereira da Silva |
| Situação cadastral | **Regular** (atualizada em 15/08/2025) |
| Classe social | B2 |
| Ocupação (CBO) | Negociante — comércio varejista (empregador) |
| Renda estimada | R$ 6.344,27 (~4 salários mínimos) |
| Óbito | Não consta |

---

## Endereços Conhecidos

1. **R. Pierre Curie, SN — Q 38 LT 18 — Bangu, Rio de Janeiro/RJ — CEP 21825-460**
2. R. Pierre Curie, 179 — Bangu, Rio de Janeiro/RJ — CEP 21825-460
3. R. Alcides Bezerra, 473 — Realengo, Rio de Janeiro/RJ — CEP 21765-250

---

## Contatos

### Telefones

| Número | Tipo | Operadora | WhatsApp |
|---|---|---|---|
| (21) 99363-2023 | Celular | OI | Sim |
| (21) 97392-7942 | Celular | CLARO | Sim |
| (21) 97393-2296 | Celular | CLARO | Sim |
| (21) 97393-0700 | Celular | CLARO | Sim |
| (21) 3647-6916 | Residencial | CLARO | Não |
| (21) 2403-9952 | Comercial | OI | Não |
| (21) 2530-3550 | Household | OI | Não |

### E-mails

- mario.luciano.mls@gmail.com
- mario.vodtech@hotmail.com
- mario.vodtech@vodtech.eng.br

---

## Vínculos Empresariais (AML)

### VODTECH INSTALACOES E PROJETOS LTDA

| Campo | Dado |
|---|---|
| CNPJ | 10.822.913/0001-47 |
| Nome fantasia | VODTECH INSTALACOES E PROJETOS |
| Data de abertura | 05/05/2009 |
| Situação | **Ativa** (não baixada) |
| Qualificação de Mario | **Sócio Administrador** |

**Demais sócios:**

| Nome | CPF | Qualificação |
|---|---|---|
| Carlos Alberto de Franca | 511.911.567-53 | Sócio |

> **⚠ Ponto de atenção:** O e-mail `mario.vodtech@vodtech.eng.br` confirma vínculo operacional ativo com a VODTECH. A empresa usa domínio próprio (vodtech.eng.br), sugerindo porte relevante.

---

## Restrições e Sanções

| Verificação | Resultado |
|---|---|
| Mandado de Prisão (CNJ) | ✅ Nenhum ativo |
| PEP — Pessoa Exposta Politicamente | ✅ Não é PEP |
| Parentesco com PEP | ✅ Não identificado |
| CEIS (Empresas Inidôneas) | ✅ Não consta |
| CNEP (Empresas Punidas) | ✅ Não consta |

---

## Patrimônio Veicular

Nenhum veículo registrado em nome do CPF consultado.

---

## Histórico de APIs — Status das Consultas

| API | Endpoint | Status | Observação |
|---|---|---|---|
| Cadastro PF Plus | `/api/CadastroPessoaFisicaPlus` | ✅ OK | |
| Mandados de Prisão | `/api/CNJMandadosPrisao` | ✅ OK | |
| Óbito | `/api/Obito` | ✅ OK | |
| PEP | `/api/PessoaExpostaPoliticamente` | ✅ OK | |
| AML (Vínculos) | `/api/AML` | ✅ OK | |
| CEIS | `/api/CadastroEmpresasInidoneasSuspensas` | ✅ OK | Resultado null = não consta |
| CNEP | `/api/CadastroNacionalEmpresasPunidas` | ✅ OK | Resultado null = não consta |
| Histórico Veículos | `/api/HistoricoVeiculos` | ✅ OK | Sem veículos |
| Antecedentes Criminais | `/api/PoliciaCivilAntecedentesCriminais` | ❌ 400 | API instável — exige parâmetros adicionais |
| Vínculos Societários | `/api/VinculosSocietarios` | ❌ 403 | Fora do plano contratado — substituído pelo AML |

---

## Conclusão do Teste

**7 de 8 APIs relevantes funcionando.** O enriquecimento OSINT está operacional para o fluxo principal.

**Próximo passo:** remover `antecedentes_criminais` e `vinculos_societarios` do fluxo padrão do `OsintService` (AML já cobre vínculos). Antecedentes pode ser tentado como chamada opcional com tratamento de erro silencioso.
