"""360cash API — BPO Financeiro para escritórios de contabilidade.

Toda regra de negócio, validação e cálculo vive aqui; o frontend é apenas apresentação.
Documentação interativa: /docs (Swagger UI), /redoc e /openapi.json.
"""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.core.audit import AuditContext, audit_ctx
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.ratelimit import client_ip
from app.routers import auth, banking, compliance, fiscal, registry, reporting
from app.services.accounting import seed_cfop_rules

log = logging.getLogger("cash360")
settings = get_settings()

TAGS = [
    {"name": "Autenticação", "description": "Login com senha + OTP por e-mail, refresh, troca e recuperação de senha."},
    {"name": "Cadastros", "description": "Escritório e clientes importados da Receita Federal pelo CNPJ; usuários."},
    {"name": "Integrações", "description": "Chaves de API (header `X-API-Key`) para integração com outros sistemas."},
    {"name": "Contratos", "description": "Contrato de prestação de serviços de BPO Financeiro por adesão."},
    {"name": "LGPD e Termos", "description": "Política de privacidade, confidencialidade, termos de uso e aceites."},
    {"name": "Procurações", "description": "Procurações outorgadas pelo cliente ao escritório."},
    {"name": "Documentos", "description": "Repositório de documentos com hash SHA-256."},
    {"name": "Notas fiscais", "description": "Importação de XML de NF-e emitidas/recebidas e classificação por CFOP."},
    {"name": "Plano de contas", "description": "Plano de contas gerencial e tabela CFOP."},
    {"name": "Extratos bancários", "description": "OFX/CSV, classificação pelo cliente e replicação por IA."},
    {"name": "Open Finance", "description": "Importação de extratos via agregador Open Finance Brasil."},
    {"name": "Aplicações financeiras", "description": "Rendimentos mensais, taxas, taxa de administração e IRRF."},
    {"name": "Relatórios", "description": "Fluxo de Caixa, DRE e relatórios gerenciais para os painéis de BI."},
    {"name": "Auditoria", "description": "Trilha de auditoria (quem, quando, o que foi alterado)."},
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        seed_cfop_rules(db)
        db.commit()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=__doc__,
    openapi_tags=TAGS,
    lifespan=lifespan,
    contact={"name": "360cash", "email": "contato@360cash.tech", "url": "https://360cash.tech"},
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,  # tokens trafegam no header Authorization, não em cookies
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
)
if settings.is_production:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["api.360cash.tech", "*.360cash.tech"])


@app.middleware("http")
async def security_and_audit_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    token = audit_ctx.set(AuditContext(ip=client_ip(request), request_id=request_id[:36]))
    try:
        response = await call_next(request)
    except Exception:
        log.exception("Erro não tratado request_id=%s", request_id)
        response = JSONResponse({"detail": "Erro interno", "request_id": request_id}, status_code=500)
    finally:
        audit_ctx.reset(token)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    if not request.url.path.startswith(("/docs", "/redoc")):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health", tags=["Infra"], summary="Healthcheck")
def health():
    return {"status": "ok"}


for r in (auth.router, registry.router, compliance.router, fiscal.router, banking.router, reporting.router):
    app.include_router(r, prefix="/v1")
