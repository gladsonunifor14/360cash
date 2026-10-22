<div align="center">

# 360cash

**BPO Financeiro para escritórios de contabilidade**

Consultoria contábil e tributária baseada em dados: notas fiscais, extratos, contas a pagar e receber e
conciliação bancária em um só lugar, com DRE, Fluxo de Caixa e painéis de BI assinados pelo seu escritório.

![status](https://img.shields.io/badge/status-MVP%20em%20valida%C3%A7%C3%A3o-orange)
![licença](https://img.shields.io/badge/licen%C3%A7a-Apache%202.0-blue)
![python](https://img.shields.io/badge/Python-3.12%2B-3776AB)
![react](https://img.shields.io/badge/React-19-61DAFB)
![api](https://img.shields.io/badge/API-OpenAPI%20%2F%20Swagger-85EA2D)

[Apresentação](#apresentação) · [Funcionalidades](#funcionalidades) · [Onboarding](#onboarding-primeiros-passos) ·
[Instalação](#instalação) · [API](#api) · [Segurança](#segurança) · [LGPD](#lgpd) · [Auditoria](#auditoria) ·
[Contribuir](#como-contribuir) · [Status](#status-do-projeto) · [Licença](#licença)

</div>

---

## Sumário

1. [Apresentação](#apresentação)
2. [Funcionalidades](#funcionalidades)
3. [Onboarding: primeiros passos](#onboarding-primeiros-passos)
   - [Perfis de acesso](#perfis-de-acesso)
   - [Trilha 1 — Administrador do escritório](#trilha-1--administrador-do-escritório-implantação)
   - [Trilha 2 — Contador/operador (rotina diária)](#trilha-2--contadoroperador-rotina-diária)
   - [Trilha 3 — Cliente do escritório](#trilha-3--cliente-do-escritório)
   - [Atalhos de teclado](#atalhos-de-teclado)
   - [Como ler os status](#como-ler-os-status)
   - [Perguntas frequentes](#perguntas-frequentes)
4. [Tecnologias utilizadas](#tecnologias-utilizadas)
5. [Instalação](#instalação)
6. [Uso](#uso)
7. [API](#api)
8. [Segurança](#segurança)
9. [LGPD](#lgpd)
10. [Auditoria](#auditoria)
11. [Como contribuir](#como-contribuir)
12. [Status do projeto](#status-do-projeto)
13. [Licença](#licença)

---

## Apresentação

Escritórios de contabilidade que oferecem **BPO Financeiro** passam boa parte do dia em tarefas repetitivas:
baixar XML de notas, digitar contas, conferir boletos, classificar extratos e conciliar pagamentos, para só no
fim do mês conseguir montar um relatório para o cliente. O **360cash** automatiza esse fluxo e transforma o
resultado em consultoria:

1. **Cadastro em segundos**: escritório e clientes são importados pelo CNPJ a partir da base da Receita Federal.
2. **Formalização digital**: contrato de prestação de serviços por adesão, termos de LGPD e confidencialidade e
   procurações, todos com aceite eletrônico rastreável.
3. **Entrada de dados automatizada**:
   - XML de NF-e viram receitas, custos e contas a pagar/receber, classificados pelo CFOP.
   - Extratos OFX/CSV (ou Open Finance) são classificados pelo histórico do próprio cliente, e a IA replica.
4. **Operação guiada**: uma torre de controle mostra o que está atrasado, o que vence hoje e o que já foi
   concluído, em todas as empresas da carteira.
5. **Entrega de valor**: DRE, Fluxo de Caixa e indicadores gerenciais com o nome, CNPJ, CRC e responsável técnico
   do escritório elaborador.

```
┌────────────────────┐   HTTPS/JSON    ┌──────────────────────────────┐     ┌──────────────┐
│ frontend (React)   │ ──────────────▶ │ API FastAPI (/v1, Swagger)   │ ──▶ │ PostgreSQL   │
│ só apresentação    │  Bearer JWT     │ regras, cálculos, auditoria  │     │ + audit_log  │
└────────────────────┘                 └──────────────┬───────────────┘     └──────────────┘
        ▲  Cloudflare (DNS, WAF, TLS)                 │
        │                                             ├─▶ Resend (e-mails OTP / senha)
  sistemas dos clientes ── X-API-Key ──▶ API          ├─▶ BrasilAPI / ReceitaWS (CNPJ)
                                                      ├─▶ Agregador Open Finance (Pluggy)
                                                      └─▶ Claude API (classificação, opcional)
```

**Princípio de arquitetura:** toda regra de negócio, validação e cálculo fica no backend. O frontend é
deliberadamente "burro": só exibe o que a API devolve. Isso reduz a superfície de ataque e permite que qualquer
sistema do cliente use a mesma API documentada.

---

## Funcionalidades

### Acesso e cadastro
| Funcionalidade | Detalhes |
|---|---|
| Login em dois fatores | Senha + código de 6 dígitos enviado por e-mail (contato@360cash.tech via Resend) |
| Senha | Alteração autenticada, recuperação por link de uso único e bloqueio temporário após tentativas inválidas |
| Cadastro do escritório | Importado pelo CNPJ (razão social, endereço, CNAE, situação) e complementado com CRC e responsável técnico |
| Cadastro de clientes | Importado pelo CNPJ, com regime tributário (MEI, Simples, Presumido, Real) |
| Usuários e convites | Perfis administrador, contador e cliente; o convite chega por e-mail com link para definir a senha |
| Chaves de API | Integração de sistemas externos pelo header `X-API-Key` |

### Formalização e documentos
| Funcionalidade | Detalhes |
|---|---|
| Contrato de adesão | Modelo versionado com variáveis (cliente, escritório, honorários, início); aceite registra usuário, data/hora, IP e SHA-256 do texto |
| Termos LGPD | Política de privacidade, termo de confidencialidade e termos de uso, versionados; nova versão exige novo aceite |
| Procurações | Outorgante, outorgado, finalidade, órgão (e-CAC, bancos, SEFAZ), validade e revogação |
| Repositório de documentos | Upload com hash SHA-256, categorias, download auditado e exclusão lógica |

### Fiscal e financeiro
| Funcionalidade | Detalhes |
|---|---|
| NF-e emitidas e recebidas | Importação de XML ou ZIP, detecção automática da direção pelo CNPJ e eventos de cancelamento |
| Classificação por CFOP | O CFOP é convertido para a visão do cliente (5102 do fornecedor → 1102 de compra) e mapeado para a conta gerencial |
| Contas a pagar e receber | Geradas das duplicatas da NF-e ou lançadas manualmente; tela dividida com o documento ao lado dos campos; histórico de alterações |
| Ações em lote | Aprovar, agendar, liquidar ou cancelar vários títulos com a soma exibida antes de confirmar |
| Extratos bancários | OFX (SGML/XML) e CSV; o cliente classifica os primeiros lançamentos e a IA replica (histórico idêntico, similaridade e, opcionalmente, Claude) |
| Conciliação bancária | Extrato e título sugerido lado a lado; atalhos para juros/multa, desconto e pagamento parcial; desfazer |
| Open Finance | Sincronização via agregador autorizado (interface pronta para Pluggy), com status da conexão |
| Aplicações financeiras | Rendimento bruto e líquido, taxa do mês, taxa de administração, IRRF, % do CDI e simulador de IR/IOF regressivo |

### Relatórios e gestão
| Funcionalidade | Detalhes |
|---|---|
| Torre de controle | Pendências de todas as empresas por criticidade, fila de trabalho e status das integrações bancárias |
| Busca global | Uma única barra para CNPJ, nome, valor ou número de nota, em todas as empresas |
| DRE gerencial | Mensal, regime de competência (NF-e + extratos) ou de caixa, com margens |
| Fluxo de Caixa | Mensal por atividade (operacional, investimento, financiamento) e geração acumulada |
| Indicadores (BI) | Faturamento, lucro, margens, ticket médio, maiores clientes, fornecedores e despesas |
| Assinatura do escritório | Todo relatório traz razão social, CNPJ, CRC e responsável técnico do escritório |

---

## Onboarding: primeiros passos

> Este guia leva cada perfil do primeiro acesso até a rotina diária. Se for o primeiro contato, siga a sua trilha
> na ordem; cada passo termina com um ✅ que indica como confirmar que deu certo.

### Perfis de acesso

| Perfil | Quem é | O que pode fazer |
|---|---|---|
| **Administrador** | Sócio ou gestor do escritório | Tudo, inclusive usuários, chaves de API, modelos de contrato, termos e auditoria |
| **Contador** | Equipe do escritório | Operar todas as empresas: cadastros, notas, extratos, títulos, conciliação e relatórios |
| **Cliente** | Usuário da empresa atendida | Ver apenas a própria empresa, aceitar contrato e termos, enviar documentos, classificar extratos e consultar relatórios |

### Como é o login

1. Informe **e-mail e senha** e clique em **Continuar**.
2. Você recebe um **código de 6 dígitos** no e-mail (remetente `contato@360cash.tech`). O código vale **10
   minutos** e só pode ser usado uma vez.
3. Digite o código e clique em **Entrar**. Não chegou? Use **Reenviar código** e confira o spam.

> 🔒 Ninguém do escritório ou do suporte vai pedir o seu código. Após 5 senhas erradas a conta fica bloqueada por
> 15 minutos. Esqueceu a senha? Use **Esqueci minha senha** na tela de login.

---

### Trilha 1 — Administrador do escritório (implantação)

**Tempo estimado: 30 minutos.**

**Passo 1 · Cadastre o escritório**
Em **Cadastrar escritório**, informe o CNPJ, o CRC, seu nome (responsável técnico), e-mail e senha forte (10+
caracteres com maiúscula, minúscula, número e símbolo) e aceite os termos. Os dados cadastrais vêm da Receita
Federal.
✅ A mensagem "Cadastro realizado" aparece e você consegue entrar com o código recebido por e-mail.

**Passo 2 · Revise os textos jurídicos**
Em **Termos e LGPD**, leia (**Ler texto**) a *Política de Privacidade*, o *Termo de Confidencialidade* e os *Termos
de Uso*. Eles são pontos de partida: ajuste com o seu jurídico e use **Publicar nova versão**. O texto atual vem
preenchido; edite, clique em **Revisar e publicar** e confirme. Versões publicadas não mudam mais, e todos os
usuários passam a ter o aceite pendente (aparece um aviso no topo da tela até aceitarem). O modelo do *Contrato de
BPO Financeiro* é publicado pela API (`POST /v1/contract-templates`).
✅ Cada termo mostra a versão vigente, o hash do texto e quantos usuários já aceitaram.

**Passo 3 · Cadastre o primeiro cliente**
Em **Clientes**, digite o CNPJ e clique em **Buscar e cadastrar**. Escolha o regime tributário ou deixe o sistema
detectar.
✅ A empresa aparece na lista e no seletor **Empresa em atendimento** no topo da tela.

**Passo 4 · Convide sua equipe e o cliente**
Em **Usuários → Convidar usuário**, informe nome, e-mail e perfil: **Contador** para a equipe, ou **Cliente** (com
a empresa) para quem vai operar do lado do cliente. Cada convidado recebe um e-mail para definir a própria senha.
Na lista você acompanha a situação (*Ativo*, *Convite pendente*, *Inativo*), os termos pendentes e o último acesso.
Use **Editar** para mudar o perfil ou a empresa, **Reenviar convite** se o link expirou e **Desativar** para
bloquear o acesso: as sessões abertas são encerradas na hora e o histórico é preservado.
✅ O convidado aparece como *Ativo* depois do primeiro login.

**Passo 5 · Formalize o contrato**
Em **Contratos e procurações**, informe os honorários mensais e a data de início e clique em **Gerar contrato**. O cliente
aceita pelo próprio acesso.
✅ O status muda de *pendente* para *aceito*, com data, hora e IP.

**Passo 6 · Registre procurações e documentos**
Envie a procuração (e-CAC, bancos, SEFAZ) em **Documentos** e registre validade e finalidade em **Contratos e
procurações → Procurações**. A torre de controle avisa quando uma procuração estiver para vencer.
✅ A procuração aparece com o período de validade.

**Passo 7 · Carregue os dados iniciais**
1. **Notas fiscais** → importe os XML (ou um ZIP) de emitidas e recebidas. As contas a pagar e receber são
   criadas automaticamente a partir das duplicatas.
2. **Extratos e classificação** → cadastre a conta corrente e importe o OFX/CSV.
3. **Aplicações** → cadastre a aplicação e informe o extrato mensal.

✅ A **Torre de controle** mostra os títulos e os lançamentos a classificar dessa empresa.

**Passo 8 · Ative as integrações (opcional)**
- **Chave de API** para o ERP do cliente: **Minha conta → Integrações via API**. A chave aparece uma única vez.
- **Open Finance**: veja [docs/open-finance.md](docs/open-finance.md).
- **IA de classificação** com Claude: configure `CASH360_ANTHROPIC_API_KEY`.

✅ Uma chamada `GET /v1/clients` com o header `X-API-Key` responde 200.

**Passo 9 · Acompanhe a auditoria**
Em **Auditoria** você vê quem fez o quê, quando, de qual IP e quais campos mudaram.

---

### Trilha 2 — Contador/operador (rotina diária)

**1. Comece pela Torre de controle (tela inicial)**
- Os indicadores no topo resumem a carteira inteira: **Títulos atrasados**, **Vencem hoje**, **Liquidados
  hoje**, **Conciliações sugeridas**, **Lançamentos sem classificação** e **Bancos com falha**.
- Clique em qualquer indicador para abrir a tela já filtrada.
- A **Fila de trabalho** está ordenada por criticidade. Cada item tem **Resolver →**, que já troca para a
  empresa certa.
- Em **Integrações bancárias**, um banco em *Reautenticar* significa que o cliente precisa renovar o
  consentimento no app do banco.

**2. Troque de empresa sem perder o contexto**
- Use o seletor **Empresa em atendimento** no topo ou os botões das empresas recentes (**Alt+1…5**).
- A tela e os filtros atuais são mantidos.

**3. Encontre qualquer coisa com a busca global**
Pressione **/** (ou **Ctrl+K**) e digite um CNPJ (com ou sem máscara), o nome do fornecedor, um valor como
`1.234,56` ou o número da nota. Navegue com ↑/↓ e abra com **Enter**.

**4. Contas a pagar e receber**
1. Filtre por **A pagar / A receber** e pela criticidade (**Atrasados, Para hoje, No prazo, Concluídos**).
2. **Enter** abre o título em **tela dividida**: documento à esquerda, campos à direita. Confira valor,
   vencimento e favorecido sem trocar de aba. Anexe o boleto em PDF, se faltar.
3. Selecione vários títulos (**Espaço**) e escolha **Aprovar, Agendar, Liquidar ou Cancelar**. A confirmação
   mostra quantos títulos, o total a pagar, o total a receber e o total do lote, além dos títulos que ficarão de
   fora e por quê.
4. O **Histórico** do título mostra quem criou, quem alterou o valor e quem aprovou.

**5. Conciliação bancária**
1. Cada cartão mostra o **lançamento do extrato** ao lado do **título sugerido**, com o percentual de confiança.
2. Valores iguais: **Confirmar** (Enter).
3. Valores diferentes: escolha **Criar juros/multa** (J), **Desconto** (D) ou **Lançamento parcial** (P). A
   diferença é lançada na conta correta e reflete no DRE.
4. Errou? Clique em **Desfazer** na mensagem de confirmação.
5. Sem sugestão? Use a **Conciliação manual** no fim da página.

**6. Classificação de extratos**
- Em **Extratos e classificação**, filtre **A classificar** ou **Com sugestão da IA**.
- Selecione e classifique, ou **Aceitar sugestões**. Cada classificação ensina a IA para os próximos extratos.

**7. Notas fiscais**
Abra os **Itens** de uma nota para conferir o CFOP do XML, o CFOP na visão do cliente e a conta gerencial.
Reclassifique quando necessário: a escolha manual prevalece sobre a regra.

**8. Relatórios para o cliente**
- **DRE e Fluxo de caixa**: escolha o período e o regime (competência ou caixa).
- **Indicadores (BI)**: faturamento, margens, maiores clientes, fornecedores e despesas.
- **Imprimir / PDF** gera o relatório com o cabeçalho do escritório.

> 💡 **Fechamento do mês em 5 passos:**
> 1. Importe todos os XML.
> 2. Importe os extratos.
> 3. Zere "Lançamentos sem classificação".
> 4. Confirme as conciliações sugeridas.
> 5. Gere o DRE e o Fluxo de Caixa.

---

### Trilha 3 — Cliente do escritório

1. **Primeiro acesso:** abra o e-mail de convite, defina a senha e faça login com o código enviado por e-mail.
2. **Termos:** clique no aviso "Termos pendentes" (ou abra **Contratos e procurações**), leia e aceite os termos (privacidade, confidencialidade e uso).
3. **Contrato:** clique em **Ver** para ler o contrato de BPO Financeiro e em **Aceitar**. O aceite tem validade
   jurídica e fica registrado com data, hora e IP.
4. **Envie documentos:** em **Documentos** (contratos, comprovantes, procurações) e em **Notas fiscais** (XML).
5. **Classifique os primeiros lançamentos** em **Extratos e classificação**: selecione e escolha a conta (ex.:
   aluguel → *Ocupação*). Depois disso o sistema aprende e classifica sozinho os próximos.
6. **Acompanhe** a situação da empresa na **Torre de controle**, em **Indicadores (BI)** e em **DRE e Fluxo de
   caixa**.

> Você vê apenas os dados da sua empresa. Dúvidas sobre os seus dados pessoais: contato@360cash.tech.

---

### Atalhos de teclado

| Onde | Tecla | Ação |
|---|---|---|
| Qualquer tela | `/` ou `Ctrl+K` | Abrir a busca global |
| Qualquer tela | `Alt+1` … `Alt+5` | Trocar para uma empresa recente |
| Listas | `↑` `↓` `Home` `End` | Navegar entre linhas |
| Contas a pagar/receber | `Espaço` | Selecionar/desmarcar título |
| Contas a pagar/receber | `Enter` | Abrir título (tela dividida) |
| Formulários | `Tab` / `Enter` | Próximo campo / salvar |
| Telas de detalhe e diálogos | `Esc` | Voltar/fechar |
| Conciliação | `Enter` | Confirmar sugestão |
| Conciliação | `J` / `D` / `P` | Juros-multa / desconto / pagamento parcial |

### Como ler os status

Os status sempre combinam **cor, ícone e texto**, então são legíveis também para pessoas com daltonismo.

| Status | Ícone | Significado |
|---|---|---|
| Atrasado | ⚠ triângulo, vermelho | Vencido e não liquidado, ou integração com falha |
| Para hoje | 🕒 relógio, âmbar com borda tracejada | Vence hoje ou aguarda confirmação |
| Atenção | ⓘ círculo, âmbar | Precisa de revisão (classificação, contrato, procuração vencendo) |
| Concluído / Conectado | ✔ check, verde | Liquidado, conferido ou conexão ativa |
| No prazo | → seta, cinza | Ainda dentro do prazo |
| Reautenticar | ⟳ seta circular, âmbar | O cliente precisa renovar o consentimento no banco |

Situações de um título: **Em aberto → Aprovado → Agendado → Liquidado**, ou **Pago parcialmente** ou
**Cancelado**.

### Perguntas frequentes

**Importei a mesma nota ou o mesmo extrato duas vezes. Duplicou?**
Não. Notas são identificadas pela chave de acesso e lançamentos pelo identificador do banco (FITID). O resultado
da importação informa os duplicados.

**A IA classificou errado. E agora?**
Reclassifique o lançamento. A sua escolha vira histórico e a IA passa a seguir esse padrão. A IA só aplica
sozinha acima de 80% de confiança; abaixo disso, deixa como sugestão para você aceitar.

**O DRE ficou diferente do extrato. Por quê?**
No regime de **competência**, receitas e compras vêm das notas fiscais (pela data de emissão), e os pagamentos
dessas notas no extrato são tratados como liquidação, para não contar duas vezes. Use o regime de **caixa** para
ver só o que passou pelo banco.

**Por que a confirmação em lote foi recusada com "o total do lote mudou"?**
Alguém alterou um dos títulos depois que você abriu a confirmação. Revise e confirme de novo. Essa trava evita
aprovar um valor diferente do que você conferiu.

**Como sei se o banco do cliente está desconectado?**
Pela **Torre de controle → Integrações bancárias** e pela faixa no topo da **Conciliação**. Contas marcadas como
*Reautenticar* precisam que o cliente autorize de novo no app do banco.

---

## Tecnologias utilizadas

| Camada | Tecnologia |
|---|---|
| API | Python 3.12+, **FastAPI**, Pydantic v2, Uvicorn |
| Banco de dados | **PostgreSQL 16**, SQLAlchemy 2, Alembic (migrações) |
| Segurança | Argon2id (`argon2-cffi`), JWT (`PyJWT`), `defusedxml` (XML seguro), HMAC-SHA256 para OTP e tokens |
| E-mail | **Resend** (domínio `360cash.tech` verificado) |
| Dados externos | BrasilAPI e ReceitaWS (CNPJ), agregador Open Finance (Pluggy), **Claude API** (opcional, classificação) |
| Frontend | **React 19**, React Router 7, TypeScript 5.9, Vite 8 (sem bibliotecas de UI; CSS próprio com tema claro/escuro) |
| Infra | Docker / Docker Compose, Nginx, Cloudflare (DNS, WAF, TLS) |
| Qualidade | pytest (SQLite e PostgreSQL), Ruff, `pip-audit`, `npm audit`, GitHub Actions, Playwright (E2E manual) |

Estrutura do repositório:

```
backend/
  app/
    core/        config, banco, segurança, auditoria, validação, rate limit, dependências (RBAC/tenant)
    models/      entidades SQLAlchemy
    schemas/     contratos da API (Pydantic)
    routers/     auth, cadastros, compliance, fiscal, banking, payables, workspace, reporting
    services/    CNPJ, NF-e, CFOP, extratos, classificador, títulos, conciliação, investimentos, relatórios
    scripts/     seed_demo (dados de demonstração)
  alembic/       migrações
  tests/
frontend/
  src/pages/     telas
  src/components/
docs/            segurança, UX, DNS/e-mail, Open Finance, roadmap
```

---

## Instalação

### Requisitos
- **Docker** (opção mais simples), ou
- Python 3.12+, Node 22+ e PostgreSQL 16.

### Opção 1 — Docker Compose

```bash
git clone https://github.com/gladsonunifor14/360cash.git
cd 360cash
cp backend/.env.example backend/.env
# edite backend/.env e defina CASH360_JWT_SECRET:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up --build
```

Acesse **http://localhost:8080** (aplicação) e **http://localhost:8080/docs** (Swagger).

Para carregar dados de demonstração:

```bash
docker compose exec api python -m app.scripts.seed_demo
```

### Opção 2 — Ambiente de desenvolvimento

```bash
# Banco
createuser -P cash360            # senha: cash360
createdb -O cash360 cash360

# API
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env             # ajuste CASH360_JWT_SECRET
alembic upgrade head
python -m app.scripts.seed_demo  # opcional
uvicorn app.main:app --reload    # http://localhost:8000/docs

# Frontend (outro terminal)
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

### Variáveis de ambiente (backend)

| Variável | Obrigatória | Descrição |
|---|---|---|
| `CASH360_ENVIRONMENT` | sim | `development`, `test` ou `production` |
| `CASH360_DATABASE_URL` | sim | Ex.: `postgresql+psycopg://user:senha@host:5432/cash360` |
| `CASH360_JWT_SECRET` | sim | Segredo aleatório com 32+ caracteres |
| `CASH360_RESEND_API_KEY` | em produção | Chave do Resend; sem ela, em desenvolvimento, o código OTP aparece no log da API |
| `CASH360_EMAIL_FROM` | não | Padrão `360cash <contato@360cash.tech>` |
| `CASH360_FRONTEND_URL` | sim | Usada nos links de e-mail (ex.: `https://app.360cash.tech`) |
| `CASH360_CORS_ORIGINS` | sim | Lista JSON de origens do frontend |
| `CASH360_STORAGE_DIR` | não | Diretório dos documentos (padrão `./storage`) |
| `CASH360_ANTHROPIC_API_KEY` | não | Ativa a classificação de extratos com Claude |
| `CASH360_PLUGGY_CLIENT_ID` / `_SECRET` | não | Ativa a sincronização Open Finance |

Frontend: `VITE_API_URL` (ex.: `https://api.360cash.tech`) no build de produção.

### Produção
Siga o checklist de [docs/seguranca.md](docs/seguranca.md) (Cloudflare, segredos, backups) e a configuração de
domínio e e-mail em [docs/dns-email.md](docs/dns-email.md).

---

## Uso

### Acesso de demonstração
Depois do `seed_demo`:

| Campo | Valor |
|---|---|
| E-mail | `admin@demo.360cash.tech` |
| Senha | `Demo@360cash` |
| Código OTP | No log da API (`CASH360_ENVIRONMENT=development` sem chave do Resend) |

A demonstração cria duas empresas com notas, extratos, aplicações, títulos atrasados/para hoje/no prazo,
sugestões de conciliação e uma conexão bancária que precisa de reautenticação.

### Fluxo típico

```
Cadastrar cliente (CNPJ) → contrato e termos aceitos → importar XML de NF-e
   → títulos a pagar/receber criados → importar extrato → classificar / IA replica
   → conciliar extrato × títulos → DRE, Fluxo de Caixa e BI para o cliente
```

Formatos aceitos:
- **NF-e/NFC-e:** XML (`nfeProc` ou `NFe`), ZIP com vários XML, evento de cancelamento (110111).
- **Extratos:** OFX 1.x (SGML) e 2.x (XML); CSV com colunas `data`, `descricao`/`historico` e `valor` (ou
  `debito`/`credito`), separados por `;` ou `,`.
- **Documentos:** PDF, PNG/JPG, XML, CSV, OFX, XLSX, DOCX e ZIP, até 15 MB.

---

## API

A API é **REST/JSON**, versionada em `/v1` e documentada desde o início em **OpenAPI**:

| Recurso | URL |
|---|---|
| Swagger UI (interativo) | `/docs` |
| ReDoc | `/redoc` |
| Especificação OpenAPI | `/openapi.json` |
| Healthcheck | `/health` |

### Autenticação

- **Usuários:** `POST /v1/auth/login` → código por e-mail → `POST /v1/auth/otp/verify` → `access_token` (15 min)
  e `refresh_token` (7 dias, rotacionado a cada uso). Envie `Authorization: Bearer <access_token>`.
- **Integrações:** crie uma chave em **Minha conta → Integrações via API** (ou `POST /v1/api-keys`) e envie
  `X-API-Key: c360_...`. A chave age com as permissões do administrador que a criou e pode ser revogada.

```bash
# listar empresas
curl -H "X-API-Key: $CASH360_KEY" https://api.360cash.tech/v1/clients

# importar XML de NF-e
curl -H "X-API-Key: $CASH360_KEY" -F "files=@nota.xml" \
     https://api.360cash.tech/v1/clients/$CLIENT_ID/invoices/import

# DRE por competência
curl -H "X-API-Key: $CASH360_KEY" \
     "https://api.360cash.tech/v1/clients/$CLIENT_ID/reports/dre?start=2026-01-01&end=2026-06-30&regime=competencia"
```

### Grupos de endpoints

| Grupo | Principais rotas |
|---|---|
| Autenticação | `POST /auth/register`, `/auth/login`, `/auth/otp/verify`, `/auth/otp/resend`, `/auth/refresh`, `/auth/logout`, `/auth/password/{forgot,reset,change}`, `GET /auth/me` |
| Torre de controle | `GET /control-tower`, `GET /search?q=` |
| Cadastros | `GET /cnpj/{cnpj}`, `GET/PATCH /office`, `GET/POST /clients`, `POST /clients/{id}/sync-receita`, `GET/POST /users`, `GET/POST/DELETE /api-keys` |
| Contratos e LGPD | `GET/POST /contract-templates`, `GET/POST /contracts`, `POST /contracts/{id}/accept`, `GET/POST /terms`, `GET /terms/pending`, `POST /terms/accept`, `GET /terms/acceptances` |
| Procurações e documentos | `GET/POST /powers-of-attorney`, `POST /powers-of-attorney/{id}/revoke`, `GET/POST /documents`, `GET /documents/{id}/download` |
| Notas fiscais | `POST /clients/{id}/invoices/import`, `GET /clients/{id}/invoices`, `GET /invoices/{id}`, `PATCH /invoice-items/{id}/classification`, `GET /cfop-rules`, `GET/POST /chart-accounts` |
| Contas a pagar e receber | `GET /clients/{id}/titles`, `POST /titles`, `GET/PATCH /titles/{id}`, `POST /titles/{id}/attachment`, `POST /titles/batch/preview`, `POST /titles/batch` |
| Conciliação | `GET /clients/{id}/reconciliation/suggestions`, `GET /clients/{id}/reconciliation/pending`, `POST /reconciliations`, `DELETE /reconciliations/{transaction_id}` |
| Extratos e Open Finance | `POST /bank-accounts`, `POST /bank-accounts/{id}/statements`, `GET /clients/{id}/transactions`, `POST /transactions/classify`, `POST /transactions/accept-suggestions`, `POST /clients/{id}/transactions/auto-classify`, `POST /bank-accounts/{id}/open-finance/sync` |
| Aplicações | `POST /investments`, `GET /clients/{id}/investments`, `POST /investments/simulate-ir` |
| Relatórios | `GET /clients/{id}/reports/{dre,cash-flow,management}` |
| Auditoria | `GET /audit` |

### Erros

Os erros seguem um formato único, em português, citando o campo pelo nome exibido na tela:

```json
{
  "detail": "O campo 'Data de vencimento' não pode ser anterior à 'Data de emissão'",
  "erros": [{ "campo": "Data de vencimento", "loc": ["body", "due_date"], "mensagem": "..." }]
}
```

| Código | Quando |
|---|---|
| `401` | Sem autenticação ou token expirado |
| `403` | Perfil sem permissão |
| `404` | Recurso inexistente ou de outro escritório (o isolamento não revela existência) |
| `409` | Conflito (duplicado, status incompatível, total do lote alterado) |
| `422` | Validação; veja `erros[]` |
| `423` | Conta temporariamente bloqueada |
| `429` | Limite de requisições |

---

## Segurança

Resumo dos controles (detalhes e checklist de produção em [docs/seguranca.md](docs/seguranca.md)):

- **Autenticação forte**:
  - Senha com Argon2id mais OTP por e-mail (10 min, uso único, 5 tentativas).
  - Bloqueio após 5 senhas erradas.
  - Mensagens que não revelam se o e-mail existe.
- **Sessões**:
  - Access token JWT de 15 minutos e refresh token opaco rotacionado.
  - Reuso de refresh token revogado encerra todas as sessões.
  - Troca de senha invalida os tokens anteriores.
- **Isolamento multi-tenant**: toda consulta é filtrada pelo escritório; usuários cliente só acessam a própria
  empresa.
- **RBAC**: perfis administrador, contador e cliente checados no backend.
- **Entrada segura**:
  - Validação Pydantic em toda requisição.
  - XML lido com `defusedxml`, sem DTD (bloqueia XXE e *billion laughs*).
  - Uploads com limite de tamanho, tipos permitidos, proteção contra *zip bomb* e *path traversal*.
- **Cabeçalhos**: HSTS, CSP restritiva, `X-Frame-Options: DENY`, `nosniff`, `no-referrer` e `no-store`.
- **Borda**: Cloudflare (WAF, DDoS, TLS) mais rate limit na API em `/auth/*`.
- **Frontend sem regras**: nenhum cálculo ou segredo no navegador; o access token fica só em memória.
- **Supply chain**: dependências fixadas e verificadas no CI com `pip-audit` e `npm audit`.

Encontrou uma vulnerabilidade? **Não abra issue pública.** Escreva para **contato@360cash.tech** com os
detalhes e os passos para reproduzir.

---

## LGPD

O 360cash foi desenhado para a Lei nº 13.709/2018:

| Tema | Como é atendido |
|---|---|
| Papéis | O escritório é **operador** dos dados pessoais dos documentos dos clientes e **controlador** dos dados dos usuários da plataforma |
| Transparência | Política de privacidade com finalidades, bases legais (art. 7º), compartilhamentos e retenção |
| Consentimento e aceite | Termos versionados; cada aceite guarda usuário, data/hora, IP, navegador e o hash SHA-256 do texto aceito; nova versão gera novo aceite pendente; evidências consultáveis e exportáveis em CSV em **Termos e LGPD → Evidências de aceite** |
| Confidencialidade | Termo de confidencialidade e sigilo profissional (NBC PG 01, LC 105/2001) |
| Minimização | A IA externa recebe apenas o histórico normalizado do lançamento, o sinal e o plano de contas; nunca nome, CNPJ, valores ou conta |
| Segurança (art. 46) | Controles descritos em [Segurança](#segurança) e trilha de auditoria imutável |
| Retenção | Documentos fiscais por no mínimo 5 anos (CTN art. 173); exclusão lógica de documentos |
| Direitos do titular (art. 18) | Solicitações pelo e-mail do encarregado: **contato@360cash.tech** |
| Incidentes (art. 48) | Comunicação à ANPD e aos titulares, prevista na política |

> ⚖️ Os textos de termos e contrato incluídos são **modelos iniciais**. Revise-os com o jurídico do escritório
> antes de usá-los com clientes reais.

---

## Auditoria

Todas as alterações relevantes ficam registradas na tabela **`audit_log`**:

- **Quem:** usuário, escritório, IP real (via `CF-Connecting-IP`) e `request_id`.
- **Quando:** data/hora UTC.
- **O quê:**
  - Criação, alteração (valor **de** e **para** de cada campo) e exclusão de entidades.
  - Eventos de segurança: login, falha de login/OTP, pedido e redefinição de senha, reuso de refresh token,
    download de documentos.
- **Como:**
  - Automático, via listener do SQLAlchemy em toda entidade marcada como auditada. O desenvolvedor não precisa
    lembrar de registrar.
  - Hashes de senha e tokens são mascarados.
- **Imutável:** no PostgreSQL, um *trigger* impede `UPDATE` e `DELETE` em `audit_log`.
- **Consulta:**
  - Tela **Auditoria** (administrador) ou `GET /v1/audit?entity=&entity_id=&user_id=&since=`.
  - Cada título também mostra o seu histórico legível ("Fulano alterou Valor de R$ 100,00 para R$ 120,00").

---

## Como contribuir

1. **Abra uma issue** descrevendo o problema ou a proposta antes de começar algo grande.
2. **Crie uma branch** a partir da `main`: `feat/descricao`, `fix/descricao` ou `docs/descricao`.
3. **Siga os padrões do projeto**:
   - Regras de negócio sempre no backend (`app/services`); o frontend só apresenta.
   - Toda entidade nova com dados de negócio carrega `office_id` e `__audited__ = True`.
   - Mudanças de banco via migração Alembic: `alembic revision --autogenerate -m "descrição"`. Revise o arquivo
     gerado (valores padrão para colunas `NOT NULL` em tabelas existentes).
   - Mensagens de erro em português, citando o campo como aparece na tela.
   - Status sempre com cor + ícone + texto; telas operáveis por teclado.
4. **Teste antes de abrir o PR**:
   ```bash
   cd backend && ruff check . && pytest -q
   TEST_DATABASE_URL=postgresql+psycopg://cash360:cash360@localhost:5432/cash360_test pytest -q
   cd ../frontend && npm run build
   ```
5. **Commits** no imperativo e descritivos (ex.: `feat: conciliação com desconto obtido`).
6. **Pull request** com o que mudou, por que mudou e como testar. O CI precisa estar verde: lint, testes em
   SQLite e PostgreSQL, migrações do zero, `pip-audit` e `npm audit`.
7. **Segurança e dados**: nunca versione `.env`, chaves ou dados reais de clientes. Use o `seed_demo` para testes.

---

## Status do projeto

🟠 **MVP em validação.** As funcionalidades principais estão implementadas e cobertas por testes automatizados;
o sistema ainda não foi homologado em produção com clientes reais.

| Área | Situação |
|---|---|
| Login com OTP, cadastros via CNPJ, contrato e termos | ✅ Implementado |
| NF-e, extratos com IA, aplicações financeiras | ✅ Implementado |
| Contas a pagar/receber, lote, conciliação | ✅ Implementado |
| Torre de controle, busca global, DRE, Fluxo de Caixa, BI | ✅ Implementado |
| Swagger, auditoria imutável, CI | ✅ Implementado |
| Open Finance | 🟡 Interface pronta; depende de contrato com o agregador |
| Telas de usuários (convite, perfis, desativação) e de termos (versões, publicação, evidências) | ✅ Implementado |
| Tela de edição do modelo de contrato | 🟡 Disponível via API/Swagger |
| Exportação PDF/XLSX nativa, CNAB, SEFAZ automática | ⏳ Roadmap |

Próximas entregas: [docs/roadmap.md](docs/roadmap.md). Decisões de UX: [docs/ux.md](docs/ux.md).

---

## Licença

Distribuído sob a **Apache License 2.0**; veja [LICENSE](LICENSE).

Os textos jurídicos-modelo (termos e contrato) são fornecidos "como estão", sem garantia de adequação a casos
concretos, e devem ser revisados por profissional habilitado.

<div align="center">

**360cash** · contato@360cash.tech · [360cash.tech](https://360cash.tech)

</div>
