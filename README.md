# 360cash

BPO Financeiro para escritórios de contabilidade fazerem consultoria contábil e tributária em painéis de BI.

O escritório cadastra seus clientes pelo CNPJ (dados da Receita Federal), formaliza o contrato de adesão e os
termos de LGPD/confidencialidade e importa notas fiscais (XML) e extratos bancários (OFX/CSV ou Open Finance).
A plataforma classifica tudo no plano de contas gerencial (CFOP para notas; histórico do cliente + IA para extratos)
e gera Fluxo de Caixa, DRE e relatórios gerenciais, sempre com a identificação do escritório elaborador.

```
┌────────────────────┐   HTTPS/JSON    ┌──────────────────────────────┐     ┌──────────────┐
│ frontend (React)   │ ──────────────▶ │ API FastAPI (/v1, Swagger)   │ ──▶ │ PostgreSQL   │
│ só apresentação    │  Bearer JWT     │ regras, cálculos, auditoria  │     │ + audit_log  │
└────────────────────┘                 └──────────────┬───────────────┘     └──────────────┘
        ▲  Cloudflare (DNS, WAF, TLS)                 │
        │                                             ├─▶ Resend (e-mails OTP / senha)
  integrações de clientes ── X-API-Key ──▶ API        ├─▶ BrasilAPI / ReceitaWS (CNPJ)
                                                      ├─▶ Agregador Open Finance (Pluggy)
                                                      └─▶ Claude API (classificação, opcional)
```

## Módulos

| Escopo solicitado | Onde está |
|---|---|
| 1. Login com OTP por e-mail, alterar e recuperar senha | `backend/app/routers/auth.py`, `frontend/src/pages/Auth.tsx` |
| 2. Cadastro do escritório e clientes via CNPJ da Receita | `backend/app/services/cnpj.py`, `routers/registry.py` |
| 2. Contrato de BPO Financeiro por adesão (aceite com IP, data/hora e SHA-256) | `routers/compliance.py`, `services/defaults.py` |
| 3. LGPD, termos de aceite e confidencialidade (versionados) | `routers/compliance.py` (`/terms`) |
| 3. Procurações | `/powers-of-attorney` |
| 3. Repositório de documentos | `/documents` (hash SHA-256, exclusão lógica) |
| 3. NF-e emitidas e recebidas (XML/ZIP, cancelamento, classificação × CFOP) | `services/nfe_parser.py`, `services/accounting.py`, `routers/fiscal.py` |
| 3. Extratos de conta corrente (cliente classifica, IA replica) | `services/bank_parser.py`, `services/classifier.py`, `routers/banking.py` |
| 3. Extratos de aplicações (rendimento, taxas, taxa adm., IRRF) | `services/investments.py`, `/investments` |
| 3. Open Finance | `services/open_finance.py` e [docs/open-finance.md](docs/open-finance.md) |
| 4. Fluxo de Caixa, DRE e Relatórios Gerenciais | `services/reports.py`, `frontend/src/pages/{Dashboard,Reports}.tsx` |
| 5. Backend com regras + frontend "dummy" | todo cálculo na API; o frontend só exibe |
| 5. Swagger desde o início | `/docs`, `/redoc`, `/openapi.json` |
| 5. Auditoria (quem, quando, o que mudou) | `backend/app/core/audit.py`, tabela `audit_log` (append-only no PostgreSQL) |

Detalhes de segurança e operação: [docs/seguranca.md](docs/seguranca.md). Configuração do domínio e e-mail:
[docs/dns-email.md](docs/dns-email.md). Próximos passos: [docs/roadmap.md](docs/roadmap.md).

## Rodando localmente

Requisitos: Python 3.12+, Node 22+, PostgreSQL 16 (ou Docker).

```bash
# opção 1: tudo em Docker → http://localhost:8080 (Swagger em /docs)
cp backend/.env.example backend/.env   # ajuste CASH360_JWT_SECRET
docker compose up --build

# opção 2: manual
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
python -m app.scripts.seed_demo        # dados de demonstração (opcional)
uvicorn app.main:app --reload          # http://localhost:8000/docs

cd ../frontend && npm install && npm run dev   # http://localhost:5173
```

Login de demonstração: `admin@demo.360cash.tech` / `Demo@360cash`. Sem `CASH360_RESEND_API_KEY`, o código OTP é
escrito no log da API (apenas com `CASH360_ENVIRONMENT=development`; em produção a chave é obrigatória).

## Testes

```bash
cd backend
pytest -q                                   # SQLite
TEST_DATABASE_URL=postgresql+psycopg://cash360:cash360@localhost:5432/cash360_test pytest -q
ruff check .
cd ../frontend && npm run build             # typecheck + build
```

O CI (`.github/workflows/ci.yml`) roda lint, testes em SQLite e PostgreSQL, migrações do zero, `pip-audit` e
`npm audit`.

## Como as classificações funcionam

**Notas fiscais.** A direção é definida pelo CNPJ do cliente (emitente ⇒ emitida; destinatário ⇒ recebida). Em
notas recebidas o CFOP do XML é o do fornecedor, então ele é convertido para a visão do cliente (5102 → 1102).
O CFOP do cliente define a operação (venda, compra, devolução, transferência, remessa, uso e consumo, ativo,
serviço) e a conta gerencial. Itens podem ser reclassificados manualmente; eventos de cancelamento (110111)
tiram a nota dos relatórios.

**Extratos.** O cliente (ou o contador) classifica os primeiros lançamentos. A cada importação o motor aprende
com esse histórico: histórico idêntico (datas, números e meses removidos) ou similaridade TF-IDF entre lançamentos
do mesmo sinal. Acima de 80% de confiança aplica a conta; entre 45% e 80% deixa como sugestão para aceitar.
Com `CASH360_ANTHROPIC_API_KEY`, o que sobra recebe sugestão do Claude, que só recebe o histórico do lançamento, o
sinal (crédito/débito) e o plano de contas.

**DRE.** Regime de competência: receitas, devoluções, compras e custos vêm das NF-e; despesas, financeiras e
impostos sobre o lucro vêm dos extratos (lançamentos em contas originadas por nota são tratados como liquidação,
para não contar duas vezes). Regime de caixa: só extratos. Fora do Simples, ICMS/PIS/COFINS destacados nas notas
emitidas entram como deduções.

**Aplicações.** Rendimento bruto = saldo final − saldo inicial − aplicações + resgates + IRRF + IOF + taxa de
administração; taxa do mês pelo método de Dietz simplificado; % do CDI quando informado; simulador de IOF e
IRRF regressivo por prazo.
