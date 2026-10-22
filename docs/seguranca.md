# Segurança, SRE e LGPD

## Princípios

- **Backend com as regras, frontend só apresenta.** Validação, autorização, cálculos e classificação acontecem
  na API. O frontend não tem lógica de negócio nem segredos, só exibe o que a API devolve.
- **Defesa em profundidade.** Cloudflare na borda (WAF, DDoS, TLS), rate limit na API, autenticação em dois
  fatores, isolamento por escritório e cliente em toda consulta, e trilha de auditoria imutável.
- **Menor privilégio.** Perfis `admin` (sócio do escritório), `contador` e `cliente` (vê só a própria empresa).

## Autenticação

| Controle | Implementação |
|---|---|
| Senhas | Argon2id (`argon2-cffi`); política: 10+ caracteres com maiúscula, minúscula, número e símbolo |
| 2º fator | OTP de 6 dígitos por e-mail (Resend), válido por 10 min, uso único, até 5 tentativas; guardado como HMAC-SHA256 |
| Bloqueio | 5 senhas erradas ⇒ conta bloqueada por 15 min; mesma mensagem para e-mail inexistente (sem enumeração) |
| Tokens | Access JWT de 15 min; refresh opaco de 7 dias, guardado como hash, com rotação a cada uso |
| Roubo de sessão | Reuso de refresh token revogado derruba todas as sessões do usuário |
| Troca/reset de senha | Invalida access tokens antigos (claim `pwd`) e revoga todos os refresh tokens; e-mail de aviso |
| Recuperação | Link de uso único válido por 30 min; resposta idêntica exista ou não o e-mail |
| Integrações | Chaves `X-API-Key` (prefixo `c360_`), guardadas como hash, revogáveis, com `last_used_at` |
| Rate limit | 10 req/min por IP em `/auth/*` (use também regra WAF no Cloudflare) |

## API

- Cabeçalhos: HSTS, CSP `default-src 'none'`, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`,
  `Cache-Control: no-store`.
- CORS restrito às origens configuradas; sem cookies (token no header `Authorization`, o que elimina CSRF).
- `TrustedHostMiddleware` em produção.
- IP real lido de `CF-Connecting-IP`.
- Uploads: limite de 15 MB, lista de tipos permitidos, ZIP com limite de entradas e tamanho (anti zip bomb),
  armazenamento por hash (sem path traversal), download com `Content-Disposition: attachment`.
- XML: `defusedxml` com DTD proibido (bloqueia XXE e billion laughs). Há teste automatizado para isso.
- Erros 500 devolvem só um `request_id`, nunca stack trace.
- Pydantic valida toda entrada; SQLAlchemy usa parâmetros (sem SQL concatenado).

## Auditoria

`app/core/audit.py` registra automaticamente, para toda entidade marcada `__audited__`, a criação, alteração
(valores *de* e *para* por campo) e exclusão, com usuário, escritório, IP, `request_id` e data/hora. Hashes de
senha e tokens são mascarados. Também ficam registrados login, falha de login/OTP, pedido e reset de senha,
reuso de refresh token e download de documentos. No PostgreSQL, um trigger impede `UPDATE` e `DELETE` em
`audit_log`.

## Produção (checklist SRE)

1. **Cloudflare**: proxy laranja em `app.` e `api.360cash.tech`; SSL *Full (strict)*; *Always Use HTTPS*;
   HSTS; WAF Managed Rules; regra de rate limit em `api.360cash.tech/v1/auth/*` (ex.: 20 req/min por IP);
   *Bot Fight Mode*; bloquear países sem clientes se fizer sentido.
2. **Origem fechada**: aceitar tráfego só dos IPs do Cloudflare (ou Cloudflare Tunnel, que dispensa porta
   aberta).
3. **Segredos** (`CASH360_JWT_SECRET`, `CASH360_RESEND_API_KEY`, banco) em cofre do provedor, nunca no
   repositório. Rotacione o JWT secret em incidente (derruba todas as sessões).
4. **Banco**: PostgreSQL gerenciado com criptografia em repouso, backups diários com PITR, réplica de leitura
   para BI se crescer; usuário da aplicação sem permissão de DDL após a migração.
5. **Storage**: volume cifrado ou Cloudflare R2 (bucket privado). Ver `app/services/storage.py`.
6. **Observabilidade**: logs estruturados com `request_id`; alertas para picos de `login_failed`, `otp_failed`
   e `refresh_reuse` na `audit_log`; uptime em `/health`.
7. **Atualizações**: CI com `pip-audit` e `npm audit`; ative Dependabot.
8. **Múltiplas réplicas**: troque o rate limit em memória (`app/core/ratelimit.py`) por Redis ou pelas regras
   do Cloudflare.

## LGPD

- Papéis: o escritório é **operador** dos dados pessoais contidos nos documentos dos clientes e **controlador**
  dos dados dos usuários da plataforma.
- Termos versionados por escritório (`privacidade`, `confidencialidade`, `uso`); cada aceite guarda usuário,
  data/hora, IP, user agent e o hash do texto aceito. Nova versão ⇒ novo aceite pendente.
- Minimização: a IA externa recebe só o histórico normalizado do lançamento, o sinal e o plano de contas, sem
  nome, CNPJ, valores ou conta.
- Retenção: documentos fiscais por no mínimo 5 anos (CTN art. 173). A exclusão de documentos é lógica, para
  preservar a trilha.
- Direitos do titular (art. 18): pelo e-mail do encarregado, contato@360cash.tech. Endpoint de exportação e
  anonimização está no roadmap.
- **Os textos padrão de termos e contrato são modelos iniciais. Revise com o jurídico do escritório antes de
  usar com clientes reais.**
