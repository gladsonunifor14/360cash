# Importação de extratos via Open Finance: viabilidade

## Conclusão

**É viável, por meio de um agregador.** Um escritório contábil ou BPO não pode se conectar diretamente às APIs
do Open Finance Brasil: só participantes autorizados pelo Banco Central (instituições financeiras, de pagamento
ou iniciadores de pagamento) recebem dados. O caminho prático é contratar um agregador participante, que cuida
do consentimento e entrega contas e transações por API REST.

| Opção | Prós | Contras |
|---|---|---|
| **Agregador** (ex.: Pluggy, Belvo, Celcoin) | Integração em semanas; consentimento regulado; cobre os principais bancos; contas correntes e investimentos | Custo por conexão/mês; dependência de terceiro (mitigada pela interface `OpenFinanceProvider`) |
| Participação direta no Open Finance | Sem intermediário | Exige autorização do BCB, certificados ICP/Open Finance, diretório, segurança FAPI; inviável para o porte |
| OFX/CSV manual (já implementado) | Sem custo, funciona com qualquer banco | Depende do cliente enviar o arquivo |

## Como ficou no 360cash

- `app/services/open_finance.py` define a interface `OpenFinanceProvider` (`connect_token`, `list_accounts`,
  `list_transactions`) e a implementação `PluggyProvider`.
- A conta bancária recebe `external_id` (id da conta no agregador) e `source=open_finance`.
- `POST /v1/bank-accounts/{id}/open-finance/sync?start=&end=` baixa as transações, deduplica pelo id do
  agregador (`fitid`) e aplica a mesma classificação aprendida dos extratos OFX.

## Fluxo de consentimento

1. O escritório gera um *connect token* para o cliente (`connect_token`).
2. O cliente abre o widget do agregador, escolhe o banco e autoriza o compartilhamento **no app do próprio
   banco** (prazo de até 12 meses, renovável).
3. O agregador devolve o `itemId`; o 360cash lista as contas e grava o `external_id` de cada uma.
4. A sincronização roda sob demanda ou agendada (job diário).

## Pendências para produção

- Contratar o agregador e configurar `CASH360_PLUGGY_CLIENT_ID` / `CASH360_PLUGGY_CLIENT_SECRET`.
- Endpoint para gerar o connect token e tela do widget no frontend.
- Webhook do agregador para sincronizar automaticamente e avisar sobre consentimento expirado.
- Incluir o agregador como suboperador na Política de Privacidade (o texto padrão já menciona).
