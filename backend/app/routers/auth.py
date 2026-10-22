"""Autenticação em dois fatores: senha + OTP enviado por e-mail (Resend)."""

from datetime import timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.audit import current_ctx, log_event
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import Principal, get_principal
from app.core.ratelimit import auth_rate_limit, client_ip
from app.core.security import (
    constant_time_equals,
    create_jwt,
    decode_jwt,
    generate_otp,
    hash_password,
    hash_token,
    new_opaque_token,
    utcnow,
    validate_password_strength,
    verify_password,
)
from app.models import Office, OtpCode, PasswordResetToken, RefreshToken, User
from app.schemas import (
    ChangePasswordIn,
    ForgotIn,
    LoginIn,
    LoginStep1Out,
    Message,
    OtpResendIn,
    OtpVerifyIn,
    RefreshIn,
    RegisterIn,
    ResetIn,
    TokenOut,
    UserOut,
)
from app.services import cnpj as cnpj_service
from app.services import email as mailer
from app.services.accounting import seed_chart
from app.services.defaults import accept_current_terms, seed_office_defaults

router = APIRouter(prefix="/auth", tags=["Autenticação"])

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15
INVALID_CREDENTIALS = "E-mail ou senha inválidos"
# hash fixo para equalizar o tempo de resposta quando o e-mail não existe
_DUMMY_HASH = hash_password("dummy-password-for-timing-1A!")


def _check_strength(password: str) -> None:
    problems = validate_password_strength(password)
    if problems:
        raise HTTPException(422, "Senha fraca: " + ", ".join(problems))


def _issue_otp(db: Session, user: User) -> str:
    s = get_settings()
    db.execute(
        update(OtpCode).where(OtpCode.user_id == user.id, OtpCode.used_at.is_(None)).values(used_at=utcnow())
    )
    code = generate_otp()
    db.add(OtpCode(user_id=user.id, code_hash=hash_token(code),
                   expires_at=utcnow() + timedelta(minutes=s.otp_ttl_minutes)))
    db.commit()
    mailer.send_otp(user.email, user.name, code)
    return create_jwt(user.id, "otp", s.otp_token_minutes)


def _issue_tokens(db: Session, user: User, request: Request) -> TokenOut:
    s = get_settings()
    pwd = int(user.password_changed_at.timestamp()) if user.password_changed_at else 0
    access = create_jwt(user.id, "access", s.access_token_minutes,
                        {"office": user.office_id, "role": user.role, "pwd": pwd})
    refresh = new_opaque_token()
    db.add(RefreshToken(user_id=user.id, token_hash=hash_token(refresh),
                        expires_at=utcnow() + timedelta(days=s.refresh_token_days),
                        ip=client_ip(request), user_agent=(request.headers.get("user-agent") or "")[:300]))
    db.commit()
    return TokenOut(access_token=access, refresh_token=refresh, expires_in=s.access_token_minutes * 60)


@router.post("/register", response_model=Message, status_code=201, dependencies=[Depends(auth_rate_limit)],
             summary="Cadastra escritório (dados da Receita Federal) e usuário administrador")
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    if not body.accept_terms:
        raise HTTPException(422, "É necessário aceitar os Termos de Uso e a Política de Privacidade")
    _check_strength(body.password)
    if db.scalar(select(Office.id).where(Office.cnpj == body.office_cnpj)):
        raise HTTPException(409, "Escritório já cadastrado. Solicite acesso ao administrador.")
    if db.scalar(select(User.id).where(User.email == body.email.lower())):
        raise HTTPException(409, "E-mail já cadastrado")
    try:
        data, raw = cnpj_service.lookup(body.office_cnpj)
    except cnpj_service.CnpjError as exc:
        raise HTTPException(422, str(exc)) from exc

    office = Office(
        cnpj=body.office_cnpj, razao_social=data["razao_social"], nome_fantasia=data["nome_fantasia"],
        email=data["email"], telefone=data["telefone"], endereco=data["endereco"],
        cnae_principal=data["cnae_principal"], situacao_cadastral=data["situacao_cadastral"],
        crc=body.crc, responsavel_tecnico=body.name, dados_receita=raw,
    )
    db.add(office)
    db.flush()
    ctx = current_ctx()
    ctx.office_id = office.id
    user = User(office_id=office.id, name=body.name, email=body.email.lower(),
                password_hash=hash_password(body.password), role="admin", password_changed_at=None)
    db.add(user)
    db.flush()
    ctx.user_id = user.id
    seed_chart(db, office.id)
    seed_office_defaults(db, office)
    db.flush()
    accept_current_terms(db, user, client_ip(request), request.headers.get("user-agent"))
    db.commit()
    return Message(detail="Cadastro realizado. Faça login para receber o código de acesso por e-mail.")


@router.post("/login", response_model=LoginStep1Out, dependencies=[Depends(auth_rate_limit)],
             summary="Etapa 1: valida e-mail e senha e envia código OTP por e-mail")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user:
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(401, INVALID_CREDENTIALS)
    now = utcnow()
    if user.locked_until and user.locked_until > now:
        raise HTTPException(423, "Conta temporariamente bloqueada por tentativas inválidas. Tente mais tarde.")
    if not verify_password(body.password, user.password_hash) or not user.is_active:
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            user.failed_logins = 0
        log_event(db, "login_failed", "users", user.id, office_id=user.office_id, user_id=user.id)
        db.commit()
        raise HTTPException(401, INVALID_CREDENTIALS)
    otp_token = _issue_otp(db, user)
    return LoginStep1Out(otp_token=otp_token, message="Enviamos um código de 6 dígitos para seu e-mail.")


@router.post("/otp/resend", response_model=LoginStep1Out, dependencies=[Depends(auth_rate_limit)],
             summary="Reenvia o código OTP")
def resend_otp(body: OtpResendIn, db: Session = Depends(get_db)):
    try:
        payload = decode_jwt(body.otp_token, "otp")
    except jwt.PyJWTError:
        raise HTTPException(401, "Sessão de login expirada. Faça login novamente.") from None
    user = db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(401, "Sessão de login expirada. Faça login novamente.")
    return LoginStep1Out(otp_token=_issue_otp(db, user), message="Novo código enviado.")


@router.post("/otp/verify", response_model=TokenOut, dependencies=[Depends(auth_rate_limit)],
             summary="Etapa 2: valida o código OTP e emite os tokens de acesso")
def verify_otp(body: OtpVerifyIn, request: Request, db: Session = Depends(get_db)):
    expired = HTTPException(401, "Código inválido ou expirado")
    try:
        payload = decode_jwt(body.otp_token, "otp")
    except jwt.PyJWTError:
        raise expired from None
    user = db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise expired
    otp = db.scalar(
        select(OtpCode)
        .where(OtpCode.user_id == user.id, OtpCode.used_at.is_(None), OtpCode.expires_at > utcnow())
        .order_by(OtpCode.created_at.desc())
    )
    if not otp:
        raise expired
    otp.attempts += 1
    if not constant_time_equals(otp.code_hash, hash_token(body.code)):
        if otp.attempts >= get_settings().otp_max_attempts:
            otp.used_at = utcnow()
        log_event(db, "otp_failed", "users", user.id, office_id=user.office_id, user_id=user.id)
        db.commit()
        raise expired
    otp.used_at = utcnow()
    user.failed_logins = 0
    user.last_login_at = utcnow()
    log_event(db, "login", "users", user.id, office_id=user.office_id, user_id=user.id)
    return _issue_tokens(db, user, request)


@router.post("/refresh", response_model=TokenOut, summary="Renova tokens (rotação do refresh token)")
def refresh(body: RefreshIn, request: Request, db: Session = Depends(get_db)):
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token)))
    if not token:
        raise HTTPException(401, "Sessão inválida")
    if token.revoked_at:
        # reutilização de refresh token revogado ⇒ possível roubo: encerra todas as sessões
        db.execute(update(RefreshToken).where(RefreshToken.user_id == token.user_id,
                                              RefreshToken.revoked_at.is_(None)).values(revoked_at=utcnow()))
        log_event(db, "refresh_reuse", "users", token.user_id, user_id=token.user_id)
        db.commit()
        raise HTTPException(401, "Sessão inválida")
    user = db.get(User, token.user_id)
    if token.expires_at < utcnow() or not user or not user.is_active:
        raise HTTPException(401, "Sessão expirada")
    token.revoked_at = utcnow()
    return _issue_tokens(db, user, request)


@router.post("/logout", response_model=Message, summary="Encerra a sessão (revoga o refresh token)")
def logout(body: RefreshIn, db: Session = Depends(get_db)):
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token)))
    if token and not token.revoked_at:
        token.revoked_at = utcnow()
        db.commit()
    return Message(detail="Sessão encerrada")


@router.post("/password/forgot", response_model=Message, dependencies=[Depends(auth_rate_limit)],
             summary="Envia link de redefinição de senha por e-mail")
def forgot_password(body: ForgotIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user and user.is_active:
        token = new_opaque_token()
        db.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == user.id,
                                                    PasswordResetToken.used_at.is_(None)).values(used_at=utcnow()))
        db.add(PasswordResetToken(
            user_id=user.id, token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(minutes=get_settings().password_reset_minutes)))
        log_event(db, "password_reset_requested", "users", user.id, office_id=user.office_id, user_id=user.id)
        db.commit()
        mailer.send_password_reset(user.email, user.name, token)
    # resposta idêntica exista ou não o e-mail (evita enumeração de usuários)
    return Message(detail="Se o e-mail estiver cadastrado, você receberá as instruções em instantes.")


def _set_password(db: Session, user: User, new_password: str) -> None:
    _check_strength(new_password)
    user.password_hash = hash_password(new_password)
    user.password_changed_at = utcnow()
    user.failed_logins = 0
    user.locked_until = None
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id,
                                          RefreshToken.revoked_at.is_(None)).values(revoked_at=utcnow()))


@router.post("/password/reset", response_model=Message, dependencies=[Depends(auth_rate_limit)],
             summary="Redefine a senha com o token recebido por e-mail")
def reset_password(body: ResetIn, db: Session = Depends(get_db)):
    prt = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(body.token)))
    if not prt or prt.used_at or prt.expires_at < utcnow():
        raise HTTPException(400, "Link inválido ou expirado")
    user = db.get(User, prt.user_id)
    _set_password(db, user, body.new_password)
    prt.used_at = utcnow()
    log_event(db, "password_reset", "users", user.id, office_id=user.office_id, user_id=user.id)
    db.commit()
    mailer.send_password_changed(user.email, user.name)
    return Message(detail="Senha redefinida. Faça login novamente.")


@router.post("/password/change", response_model=Message, summary="Altera a senha do usuário autenticado")
def change_password(body: ChangePasswordIn, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    user = db.get(User, p.user.id)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Senha atual incorreta")
    if body.current_password == body.new_password:
        raise HTTPException(400, "A nova senha deve ser diferente da atual")
    _set_password(db, user, body.new_password)
    db.commit()
    mailer.send_password_changed(user.email, user.name)
    return Message(detail="Senha alterada. Faça login novamente nos demais dispositivos.")


@router.get("/me", response_model=UserOut, summary="Usuário autenticado")
def me(p: Principal = Depends(get_principal)):
    return p.user
