"""Envio de e-mails transacionais via Resend (remetente contato@360cash.tech)."""

import html
import logging

import httpx

from app.core.config import get_settings

log = logging.getLogger("cash360.email")

RESEND_URL = "https://api.resend.com/emails"

# Em testes/desenvolvimento sem chave, os e-mails ficam aqui em vez de serem enviados.
outbox: list[dict] = []


def _layout(title: str, body_html: str) -> str:
    return f"""<!doctype html><html><body style="font-family:Arial,sans-serif;background:#f4f6f8;padding:24px">
<div style="max-width:520px;margin:auto;background:#fff;border-radius:8px;padding:32px">
<h2 style="color:#0b5cad;margin-top:0">360cash</h2><h3>{html.escape(title)}</h3>{body_html}
<p style="color:#888;font-size:12px;margin-top:32px">Se você não solicitou esta ação, ignore este e-mail
e avise seu escritório de contabilidade. Nunca compartilhe códigos de acesso.</p></div></body></html>"""


def send_email(to: str, subject: str, html_body: str, text_body: str) -> None:
    s = get_settings()
    message = {"from": s.email_from, "to": [to], "subject": subject, "html": html_body, "text": text_body}
    if not s.resend_api_key:
        if s.is_production:
            raise RuntimeError("CASH360_RESEND_API_KEY obrigatório em produção")
        outbox.append(message)
        log.warning("RESEND_API_KEY ausente: e-mail para %s não enviado (modo dev)", to)
        if s.environment == "development":
            log.warning("Conteúdo (somente em desenvolvimento): %s", text_body)
        return
    resp = httpx.post(
        RESEND_URL,
        json=message,
        headers={"Authorization": f"Bearer {s.resend_api_key}"},
        timeout=10,
    )
    if resp.status_code >= 400:
        log.error("Falha Resend %s: %s", resp.status_code, resp.text[:300])
        resp.raise_for_status()


def send_otp(to: str, name: str, code: str) -> None:
    minutes = get_settings().otp_ttl_minutes
    body = (
        f"<p>Olá, {html.escape(name)}.</p><p>Seu código de acesso é:</p>"
        f'<p style="font-size:32px;letter-spacing:8px;font-weight:bold">{code}</p>'
        f"<p>Ele expira em {minutes} minutos.</p>"
    )
    send_email(
        to,
        f"Seu código de acesso 360cash: {code}",
        _layout("Código de verificação", body),
        f"Seu código de acesso 360cash é {code}. Expira em {minutes} minutos.",
    )


def send_password_reset(to: str, name: str, token: str) -> None:
    s = get_settings()
    link = f"{s.frontend_url}/redefinir-senha?token={token}"
    body = (
        f"<p>Olá, {html.escape(name)}.</p><p>Recebemos um pedido para redefinir sua senha.</p>"
        f'<p><a href="{html.escape(link)}" style="background:#0b5cad;color:#fff;padding:12px 20px;'
        f'border-radius:6px;text-decoration:none">Redefinir senha</a></p>'
        f"<p>O link expira em {s.password_reset_minutes} minutos.</p>"
    )
    send_email(
        to,
        "Redefinição de senha - 360cash",
        _layout("Redefinir senha", body),
        f"Redefina sua senha em: {link} (expira em {s.password_reset_minutes} minutos)",
    )


def send_password_changed(to: str, name: str) -> None:
    send_email(
        to,
        "Sua senha foi alterada - 360cash",
        _layout("Senha alterada", f"<p>Olá, {html.escape(name)}. Sua senha do 360cash foi alterada.</p>"),
        "Sua senha do 360cash foi alterada.",
    )
