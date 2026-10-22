# Roadmap

## Entregue nesta versão (MVP)

- Login com senha + OTP por e-mail (Resend), troca e recuperação de senha, convites, chaves de API.
- Cadastro do escritório e de clientes a partir do CNPJ (BrasilAPI, com ReceitaWS de reserva).
- Contrato de adesão versionado com aceite eletrônico; termos LGPD, confidencialidade e uso com aceite.
- Procurações e repositório de documentos.
- Importação de NF-e/NFC-e (XML/ZIP, cancelamento) com classificação por CFOP na visão do cliente.
- Extratos OFX/CSV com classificação humana e replicação automática (histórico + TF-IDF + Claude opcional).
- Aplicações financeiras: rendimento, taxas, taxa de administração, IRRF, % do CDI e simulador regressivo.
- Fluxo de Caixa, DRE (competência e caixa) e relatório gerencial com KPIs e rankings.
- Swagger, auditoria automática e imutável, CI, Docker e dados de demonstração.

## Próximas entregas sugeridas

**Produto (contábil/financeiro)**
- Contas a pagar/receber e conciliação de títulos com extrato (PMR, PMP, ciclo de caixa).
- Orçado × realizado e projeção de fluxo de caixa (13 semanas).
- NFS-e (padrão nacional) e CT-e; importação automática da SEFAZ por certificado digital (Distribuição DF-e).
- Apuração estimada de tributos (Simples, Presumido) e alertas de enquadramento.
- Exportação de lançamentos para os sistemas contábeis (Domínio, Alterdata, Questor) e de relatórios em PDF/XLSX.

**Robotização (RPA)**
- Job agendado de sincronização Open Finance e importação de XML da SEFAZ.
- Captura de e-mails com XML/OFX enviados pelos clientes (inbound do Resend) direto para o repositório.
- Lembretes automáticos de documentos pendentes e de procurações a vencer.

**Segurança e plataforma**
- Endpoints LGPD de exportação/anonimização do titular.
- Storage em Cloudflare R2 com URLs assinadas; antivírus nos uploads.
- Rate limit distribuído (Redis) e fila de jobs (RQ/Celery) para importações grandes.
- Testes E2E com Playwright no CI e testes de carga.
- Opção de TOTP (app autenticador) e WebAuthn além do OTP por e-mail.
