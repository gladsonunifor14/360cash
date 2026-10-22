"""Modelo de dados do 360cash.

Todas as entidades de negócio carregam `office_id` (multi-tenant por escritório).
Entidades com `__audited__ = True` geram registros em `audit_log` automaticamente.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.security import utcnow

Money = Numeric(18, 2)


def _uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


# --------------------------------------------------------------------------- tenancy / identidade


class Office(TimestampMixin, Base):
    """Escritório de contabilidade (tenant). Aparece como elaborador nos relatórios."""

    __tablename__ = "offices"
    __audited__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, nullable=False)
    razao_social: Mapped[str] = mapped_column(String(200), nullable=False)
    nome_fantasia: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))
    telefone: Mapped[str | None] = mapped_column(String(40))
    endereco: Mapped[dict | None] = mapped_column(JSON)
    cnae_principal: Mapped[str | None] = mapped_column(String(200))
    situacao_cadastral: Mapped[str | None] = mapped_column(String(40))
    crc: Mapped[str | None] = mapped_column(String(40))  # registro no Conselho Regional de Contabilidade
    responsavel_tecnico: Mapped[str | None] = mapped_column(String(200))
    dados_receita: Mapped[dict | None] = mapped_column(JSON)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __audited__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    office_id: Mapped[str] = mapped_column(ForeignKey("offices.id"), nullable=False, index=True)
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # admin (sócio do escritório) | contador | cliente
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="contador")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    office: Mapped[Office] = relationship()


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), default="login", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip: Mapped[str | None] = mapped_column(String(64))


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ApiKey(Base):
    """Chave de integração para sistemas do cliente consumirem a API (header X-API-Key)."""

    __tablename__ = "api_keys"
    __audited__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    office_id: Mapped[str] = mapped_column(ForeignKey("offices.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# --------------------------------------------------------------------------- cadastro


class Client(TimestampMixin, Base):
    """Empresa cliente do escritório (tomadora do BPO financeiro)."""

    __tablename__ = "clients"
    __audited__ = True
    __table_args__ = (UniqueConstraint("office_id", "cnpj"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    office_id: Mapped[str] = mapped_column(ForeignKey("offices.id"), nullable=False, index=True)
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False)
    razao_social: Mapped[str] = mapped_column(String(200), nullable=False)
    nome_fantasia: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))
    telefone: Mapped[str | None] = mapped_column(String(40))
    endereco: Mapped[dict | None] = mapped_column(JSON)
    natureza_juridica: Mapped[str | None] = mapped_column(String(200))
    cnae_principal: Mapped[str | None] = mapped_column(String(200))
    situacao_cadastral: Mapped[str | None] = mapped_column(String(40))
    data_abertura: Mapped[date | None] = mapped_column(Date)
    # simples | presumido | real | mei
    regime_tributario: Mapped[str | None] = mapped_column(String(20))
    dados_receita: Mapped[dict | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ContractTemplate(TimestampMixin, Base):
    """Modelo de contrato de adesão de BPO Financeiro (versionado)."""

    __tablename__ = "contract_templates"
    __audited__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    office_id: Mapped[str] = mapped_column(ForeignKey("offices.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Contract(TimestampMixin, Base):
    __tablename__ = "contracts"
    __audited__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    office_id: Mapped[str] = mapped_column(ForeignKey("offices.id"), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(ForeignKey("contract_templates.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    monthly_fee: Mapped[Decimal] = mapped_column(Money, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    # pendente | aceito | cancelado
    status: Mapped[str] = mapped_column(String(20), default="pendente", nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    accepted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    accepted_ip: Mapped[str | None] = mapped_column(String(64))
    accepted_user_agent: Mapped[str | None] = mapped_column(String(300))


# --------------------------------------------------------------------------- LGPD / confidencialidade


class Term(TimestampMixin, Base):
    """Termos (privacidade/LGPD, confidencialidade, uso). Versões imutáveis após publicação."""

    __tablename__ = "terms"
    __audited__ = True
    __table_args__ = (UniqueConstraint("office_id", "kind", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    office_id: Mapped[str] = mapped_column(ForeignKey("offices.id"), nullable=False, index=True)
    # privacidade | confidencialidade | uso
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TermAcceptance(Base):
    __tablename__ = "term_acceptances"
    __audited__ = True
    __table_args__ = (UniqueConstraint("term_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    term_id: Mapped[str] = mapped_column(ForeignKey("terms.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))


class PowerOfAttorney(TimestampMixin, Base):
    """Procuração (ex.: e-CAC, bancos, prefeitura) outorgada pelo cliente ao escritório."""

    __tablename__ = "powers_of_attorney"
    __audited__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    office_id: Mapped[str] = mapped_column(ForeignKey("offices.id"), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    outorgante: Mapped[str] = mapped_column(String(200), nullable=False)
    outorgado: Mapped[str] = mapped_column(String(200), nullable=False)
    finalidade: Mapped[str] = mapped_column(String(300), nullable=False)
    orgao: Mapped[str | None] = mapped_column(String(100))  # RFB/e-CAC, banco, SEFAZ, prefeitura...
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)


class Document(Base):
    """Repositório de documentos. Conteúdo fica no storage (disco/R2); banco guarda metadados e hash."""

    __tablename__ = "documents"
    __audited__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    office_id: Mapped[str] = mapped_column(ForeignKey("offices.id"), nullable=False, index=True)
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"), index=True)
    # contrato | procuracao | nfe_xml | extrato | societario | fiscal | outros
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="outros")
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


# --------------------------------------------------------------------------- contabilidade gerencial


class ChartAccount(Base):
    """Plano de contas gerencial do escritório, mapeado para DRE e Fluxo de Caixa."""

    __tablename__ = "chart_accounts"
    __audited__ = True
    __table_args__ = (UniqueConstraint("office_id", "code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    office_id: Mapped[str] = mapped_column(ForeignKey("offices.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # receita | despesa | neutro (transferências, aportes, empréstimos)
    nature: Mapped[str] = mapped_column(String(20), nullable=False)
    dre_group: Mapped[str | None] = mapped_column(String(40))
    cash_flow_group: Mapped[str] = mapped_column(String(20), nullable=False, default="operacional")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CfopRule(Base):
    """Tabela CFOP → natureza da operação e conta gerencial padrão."""

    __tablename__ = "cfop_rules"

    cfop: Mapped[str] = mapped_column(String(4), primary_key=True)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    # venda | devolucao_venda | compra | devolucao_compra | transferencia | remessa | servico | ativo |
    # uso_consumo | outros
    operation: Mapped[str] = mapped_column(String(30), nullable=False)
    account_code: Mapped[str | None] = mapped_column(String(20))


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"
    __audited__ = True
    __table_args__ = (UniqueConstraint("client_id", "chave"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    office_id: Mapped[str] = mapped_column(ForeignKey("offices.id"), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    # emitida | recebida
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    chave: Mapped[str] = mapped_column(String(44), nullable=False)
    modelo: Mapped[str | None] = mapped_column(String(2))
    numero: Mapped[str | None] = mapped_column(String(20))
    serie: Mapped[str | None] = mapped_column(String(5))
    natureza_operacao: Mapped[str | None] = mapped_column(String(200))
    data_emissao: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    emit_cnpj: Mapped[str | None] = mapped_column(String(14))
    emit_nome: Mapped[str | None] = mapped_column(String(200))
    dest_documento: Mapped[str | None] = mapped_column(String(14))
    dest_nome: Mapped[str | None] = mapped_column(String(200))
    valor_produtos: Mapped[Decimal] = mapped_column(Money, default=0)
    valor_desconto: Mapped[Decimal] = mapped_column(Money, default=0)
    valor_frete: Mapped[Decimal] = mapped_column(Money, default=0)
    valor_icms: Mapped[Decimal] = mapped_column(Money, default=0)
    valor_icms_st: Mapped[Decimal] = mapped_column(Money, default=0)
    valor_ipi: Mapped[Decimal] = mapped_column(Money, default=0)
    valor_pis: Mapped[Decimal] = mapped_column(Money, default=0)
    valor_cofins: Mapped[Decimal] = mapped_column(Money, default=0)
    valor_total: Mapped[Decimal] = mapped_column(Money, default=0)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceItem.n_item"
    )


class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    __audited__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    n_item: Mapped[int] = mapped_column(Integer, nullable=False)
    codigo: Mapped[str | None] = mapped_column(String(60))
    descricao: Mapped[str] = mapped_column(String(300), nullable=False)
    ncm: Mapped[str | None] = mapped_column(String(8))
    cfop: Mapped[str] = mapped_column(String(4), nullable=False, index=True)  # como consta no XML (emitente)
    # CFOP na perspectiva do cliente: em notas recebidas, saída do fornecedor (5/6/7) vira entrada (1/2/3)
    cfop_cliente: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    valor_unitario: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    valor_total: Mapped[Decimal] = mapped_column(Money, default=0)
    operation: Mapped[str | None] = mapped_column(String(30))
    account_id: Mapped[str | None] = mapped_column(ForeignKey("chart_accounts.id"))
    # cfop | manual
    classification_source: Mapped[str | None] = mapped_column(String(10))

    invoice: Mapped[Invoice] = relationship(back_populates="items")


class BankAccount(TimestampMixin, Base):
    __tablename__ = "bank_accounts"
    __audited__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    office_id: Mapped[str] = mapped_column(ForeignKey("offices.id"), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    # corrente | aplicacao
    kind: Mapped[str] = mapped_column(String(15), nullable=False, default="corrente")
    bank_code: Mapped[str | None] = mapped_column(String(5))
    bank_name: Mapped[str] = mapped_column(String(100), nullable=False)
    agencia: Mapped[str | None] = mapped_column(String(10))
    conta: Mapped[str | None] = mapped_column(String(20))
    product_name: Mapped[str | None] = mapped_column(String(150))  # p/ aplicações: CDB, fundo DI...
    # origem dos dados: manual | ofx | open_finance
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(100))  # id no agregador Open Finance
    # status da integração: manual | ativo | reautenticar | erro
    connection_status: Mapped[str] = mapped_column(String(15), default="manual", nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_sync_error: Mapped[str | None] = mapped_column(String(300))


class BankTransaction(TimestampMixin, Base):
    __tablename__ = "bank_transactions"
    __audited__ = True
    __table_args__ = (UniqueConstraint("bank_account_id", "fitid"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    office_id: Mapped[str] = mapped_column(ForeignKey("offices.id"), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    bank_account_id: Mapped[str] = mapped_column(ForeignKey("bank_accounts.id"), nullable=False, index=True)
    fitid: Mapped[str] = mapped_column(String(100), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_description: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)  # + crédito / - débito
    account_id: Mapped[str | None] = mapped_column(ForeignKey("chart_accounts.id"))
    # cliente | contador | ia | None (pendente)
    classified_by: Mapped[str | None] = mapped_column(String(15))
    confidence: Mapped[float | None] = mapped_column()
    suggested_account_id: Mapped[str | None] = mapped_column(ForeignKey("chart_accounts.id"))


class InvestmentStatement(TimestampMixin, Base):
    """Extrato mensal de aplicação financeira e indicadores calculados."""

    __tablename__ = "investment_statements"
    __audited__ = True
    __table_args__ = (UniqueConstraint("bank_account_id", "competencia"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    office_id: Mapped[str] = mapped_column(ForeignKey("offices.id"), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    bank_account_id: Mapped[str] = mapped_column(ForeignKey("bank_accounts.id"), nullable=False, index=True)
    competencia: Mapped[date] = mapped_column(Date, nullable=False)  # 1º dia do mês
    saldo_inicial: Mapped[Decimal] = mapped_column(Money, nullable=False)
    aplicacoes: Mapped[Decimal] = mapped_column(Money, default=0)
    resgates: Mapped[Decimal] = mapped_column(Money, default=0)
    saldo_final: Mapped[Decimal] = mapped_column(Money, nullable=False)
    irrf: Mapped[Decimal] = mapped_column(Money, default=0)
    iof: Mapped[Decimal] = mapped_column(Money, default=0)
    taxa_administracao: Mapped[Decimal] = mapped_column(Money, default=0)
    benchmark_mes_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))  # ex.: CDI do mês (%)
    # calculados
    rendimento_bruto: Mapped[Decimal] = mapped_column(Money, default=0)
    rendimento_liquido: Mapped[Decimal] = mapped_column(Money, default=0)
    taxa_bruta_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    taxa_liquida_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    taxa_adm_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    aliquota_ir_efetiva_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    pct_benchmark: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))


# --------------------------------------------------------------------------- contas a pagar e receber


class Title(TimestampMixin, Base):
    """Título financeiro (conta a pagar ou a receber)."""

    __tablename__ = "titles"
    __audited__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    office_id: Mapped[str] = mapped_column(ForeignKey("offices.id"), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    # pagar | receber
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    counterparty_name: Mapped[str] = mapped_column(String(200), nullable=False)
    counterparty_doc: Mapped[str | None] = mapped_column(String(14), index=True)
    document_number: Mapped[str | None] = mapped_column(String(60), index=True)
    description: Mapped[str | None] = mapped_column(String(300))
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    # aberto | aprovado | agendado | parcial | liquidado | cancelado
    status: Mapped[str] = mapped_column(String(15), default="aberto", nullable=False, index=True)
    scheduled_for: Mapped[date | None] = mapped_column(Date)
    settled_at: Mapped[date | None] = mapped_column(Date)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("chart_accounts.id"))
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoices.id"), index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    @property
    def open_amount(self) -> Decimal:
        return Decimal(self.amount) - Decimal(self.paid_amount or 0)


class Reconciliation(Base):
    """Rateio de um lançamento bancário: principal do título e diferenças (juros, desconto).

    A soma das linhas de um lançamento é igual ao valor do lançamento; os relatórios usam
    estas linhas no lugar da classificação simples quando o lançamento está conciliado.
    """

    __tablename__ = "reconciliations"
    __audited__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    office_id: Mapped[str] = mapped_column(ForeignKey("offices.id"), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("bank_transactions.id"), nullable=False, index=True)
    title_id: Mapped[str | None] = mapped_column(ForeignKey("titles.id"), index=True)
    # principal | juros | desconto
    kind: Mapped[str] = mapped_column(String(15), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)  # com sinal do caixa
    account_id: Mapped[str | None] = mapped_column(ForeignKey("chart_accounts.id"))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# --------------------------------------------------------------------------- auditoria


class AuditLog(Base):
    """Trilha de auditoria imutável: quem, quando e o que foi alterado."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    office_id: Mapped[str | None] = mapped_column(String(36), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    ip: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(36))
    # create | update | delete | login | login_failed | otp_failed | password_reset | ...
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    entity: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    changes: Mapped[dict | None] = mapped_column(JSON)
