# Domínio 360cash.tech (Cloudflare) e e-mail (Resend)

## Hosts sugeridos

| Host | Aponta para | Proxy Cloudflare |
|---|---|---|
| `app.360cash.tech` | frontend (container `web`, Pages ou outro estático) | Sim |
| `api.360cash.tech` | API (container `api`) ou Cloudflare Tunnel | Sim |
| `360cash.tech` | site institucional / redirect para `app.` | Sim |

Variáveis de produção da API:

```
CASH360_ENVIRONMENT=production
CASH360_FRONTEND_URL=https://app.360cash.tech
CASH360_CORS_ORIGINS=["https://app.360cash.tech"]
CASH360_EMAIL_FROM=360cash <contato@360cash.tech>
CASH360_RESEND_API_KEY=re_...
```

Frontend: `VITE_API_URL=https://api.360cash.tech` no build.

## Resend com remetente contato@360cash.tech

1. No Resend, em **Domains**, confirme que `360cash.tech` está **Verified**. Se não estiver, copie os registros
   que o Resend mostra para o domínio (DKIM `resend._domainkey`, MX e TXT/SPF do subdomínio `send`) e crie-os
   no DNS do Cloudflare com **proxy desligado** (nuvem cinza).
2. Adicione um DMARC, começando por monitoramento:
   `TXT _dmarc.360cash.tech  "v=DMARC1; p=none; rua=mailto:contato@360cash.tech"`.
   Depois de alguns dias sem falhas, passe para `p=quarantine`.
3. Crie uma API key com permissão **Sending access**, restrita ao domínio `360cash.tech`, e coloque-a em
   `CASH360_RESEND_API_KEY` (no cofre de segredos, nunca no repositório).
4. Teste: cadastre um usuário e faça login; o OTP deve chegar com remetente `contato@360cash.tech`.

Os e-mails enviados são: código OTP de login, link de redefinição de senha, convite de novo usuário (que é um
link de definição de senha) e aviso de senha alterada. Os modelos estão em `backend/app/services/email.py`.
