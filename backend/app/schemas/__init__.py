"""Contratos de entrada/saída da API (validados pelo Pydantic e publicados no Swagger)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.services.cnpj import is_valid_cnpj, only_digits


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str


# --------------------------------------------------------------------------- auth


class RegisterIn(BaseModel):
    """Cadastro inicial: escritório (via CNPJ na Receita) + usuário administrador."""

    office_cnpj: str = Field(examples=["12.345.678/0001-95"])
    name: str = Field(min_length=3, max_length=200)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    crc: str | None = Field(default=None, max_length=40, examples=["CE-012345/O-1"])
    accept_terms: bool = Field(description="Aceite dos Termos de Uso e da Política de Privacidade (LGPD)")

    @field_validator("office_cnpj")
    @classmethod
    def _cnpj(cls, v: str) -> str:
        if not is_valid_cnpj(v):
            raise ValueError("CNPJ inválido")
        return only_digits(v)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class LoginStep1Out(BaseModel):
    otp_required: bool = True
    otp_token: str = Field(description="Token temporário para enviar junto com o código OTP")
    message: str


class OtpVerifyIn(BaseModel):
    otp_token: str
    code: str = Field(pattern=r"^\d{6}$")


class OtpResendIn(BaseModel):
    otp_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshIn(BaseModel):
    refresh_token: str


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    new_password: str = Field(min_length=10, max_length=128)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class UserOut(ORM):
    id: str
    name: str
    email: str
    role: str
    office_id: str
    client_id: str | None
    last_login_at: datetime | None


class UserCreate(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    email: EmailStr
    role: Literal["admin", "contador", "cliente"]
    client_id: str | None = None


class ApiKeyIn(BaseModel):
    name: str = Field(min_length=3, max_length=100)


class ApiKeyOut(ORM):
    id: str
    name: str
    prefix: str
    created_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    key: str = Field(description="Exibida apenas uma vez. Envie no header X-API-Key.")


# --------------------------------------------------------------------------- cadastro


class CnpjLookupOut(BaseModel):
    cnpj: str
    razao_social: str | None
    nome_fantasia: str | None
    email: str | None
    telefone: str | None
    situacao_cadastral: str | None
    natureza_juridica: str | None
    cnae_principal: str | None
    data_abertura: date | None
    regime_tributario: str | None
    endereco: dict | None


class OfficeOut(ORM):
    id: str
    cnpj: str
    razao_social: str
    nome_fantasia: str | None
    email: str | None
    telefone: str | None
    endereco: dict | None
    cnae_principal: str | None
    situacao_cadastral: str | None
    crc: str | None
    responsavel_tecnico: str | None


class OfficeUpdate(BaseModel):
    nome_fantasia: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    telefone: str | None = Field(default=None, max_length=40)
    crc: str | None = Field(default=None, max_length=40)
    responsavel_tecnico: str | None = Field(default=None, max_length=200)


Regime = Literal["simples", "presumido", "real", "mei"]


class ClientCreate(BaseModel):
    cnpj: str
    regime_tributario: Regime | None = None
    email: EmailStr | None = None
    telefone: str | None = Field(default=None, max_length=40)

    @field_validator("cnpj")
    @classmethod
    def _cnpj(cls, v: str) -> str:
        if not is_valid_cnpj(v):
            raise ValueError("CNPJ inválido")
        return only_digits(v)


class ClientUpdate(BaseModel):
    nome_fantasia: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    telefone: str | None = Field(default=None, max_length=40)
    regime_tributario: Regime | None = None
    is_active: bool | None = None


class ClientOut(ORM):
    id: str
    cnpj: str
    razao_social: str
    nome_fantasia: str | None
    email: str | None
    telefone: str | None
    endereco: dict | None
    natureza_juridica: str | None
    cnae_principal: str | None
    situacao_cadastral: str | None
    data_abertura: date | None
    regime_tributario: str | None
    is_active: bool


# --------------------------------------------------------------------------- contratos / termos


class ContractTemplateIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=50, description="Markdown. Placeholders: {{cliente_razao_social}}, "
                      "{{cliente_cnpj}}, {{escritorio_razao_social}}, {{escritorio_cnpj}}, {{mensalidade}}, "
                      "{{data_inicio}}")


class ContractTemplateOut(ORM):
    id: str
    version: int
    title: str
    body: str
    is_active: bool
    created_at: datetime


class ContractIn(BaseModel):
    client_id: str
    template_id: str | None = Field(default=None, description="Padrão: modelo ativo mais recente")
    monthly_fee: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    start_date: date


class ContractOut(ORM):
    id: str
    client_id: str
    template_id: str
    content: str
    content_sha256: str
    monthly_fee: Decimal
    start_date: date
    status: str
    accepted_at: datetime | None
    accepted_ip: str | None


class TermIn(BaseModel):
    kind: Literal["privacidade", "confidencialidade", "uso"]
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=50)


class TermOut(ORM):
    id: str
    kind: str
    version: int
    title: str
    body: str
    content_sha256: str
    created_at: datetime


class TermAcceptanceOut(ORM):
    id: str
    term_id: str
    user_id: str
    content_sha256: str
    accepted_at: datetime
    ip: str | None


class PoaIn(BaseModel):
    client_id: str
    outorgante: str = Field(max_length=200)
    outorgado: str = Field(max_length=200)
    finalidade: str = Field(max_length=300)
    orgao: str | None = Field(default=None, max_length=100)
    valid_from: date
    valid_until: date | None = None
    document_id: str | None = None


class PoaOut(ORM):
    id: str
    client_id: str
    outorgante: str
    outorgado: str
    finalidade: str
    orgao: str | None
    valid_from: date
    valid_until: date | None
    document_id: str | None
    revoked_at: datetime | None


DocCategory = Literal["contrato", "procuracao", "nfe_xml", "extrato", "societario", "fiscal", "trabalhista", "outros"]


class DocumentOut(ORM):
    id: str
    client_id: str | None
    category: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


# --------------------------------------------------------------------------- fiscal / bancário


class InvoiceItemOut(ORM):
    id: str
    n_item: int
    codigo: str | None
    descricao: str
    ncm: str | None
    cfop: str
    cfop_cliente: str
    quantidade: Decimal
    valor_unitario: Decimal
    valor_total: Decimal
    operation: str | None
    account_id: str | None
    classification_source: str | None


class InvoiceOut(ORM):
    id: str
    client_id: str
    direction: str
    chave: str
    modelo: str | None
    numero: str | None
    serie: str | None
    natureza_operacao: str | None
    data_emissao: date
    emit_cnpj: str | None
    emit_nome: str | None
    dest_documento: str | None
    dest_nome: str | None
    valor_produtos: Decimal
    valor_icms: Decimal
    valor_ipi: Decimal
    valor_pis: Decimal
    valor_cofins: Decimal
    valor_total: Decimal
    cancelled: bool


class InvoiceDetailOut(InvoiceOut):
    items: list[InvoiceItemOut]


class ImportResult(BaseModel):
    arquivo: str
    status: Literal["importado", "duplicado", "cancelamento", "erro"]
    detalhe: str | None = None
    id: str | None = None


class ItemClassifyIn(BaseModel):
    account_id: str


class ChartAccountOut(ORM):
    id: str
    code: str
    name: str
    nature: str
    dre_group: str | None
    cash_flow_group: str


class ChartAccountIn(BaseModel):
    code: str = Field(pattern=r"^\d+(\.\d+)*$", max_length=20)
    name: str = Field(max_length=200)
    nature: Literal["receita", "despesa", "neutro"]
    dre_group: Literal["receita_bruta", "deducoes", "custos", "despesas_pessoal", "despesas_administrativas",
                       "despesas_comerciais", "receitas_financeiras", "despesas_financeiras",
                       "outras_receitas", "impostos_lucro"] | None = None
    cash_flow_group: Literal["operacional", "investimento", "financiamento", "transferencia"] = "operacional"


class CfopRuleOut(ORM):
    cfop: str
    description: str
    operation: str
    account_code: str | None


class BankAccountIn(BaseModel):
    client_id: str
    kind: Literal["corrente", "aplicacao"] = "corrente"
    bank_code: str | None = Field(default=None, max_length=5)
    bank_name: str = Field(max_length=100)
    agencia: str | None = Field(default=None, max_length=10)
    conta: str | None = Field(default=None, max_length=20)
    product_name: str | None = Field(default=None, max_length=150)


class BankAccountOut(ORM):
    id: str
    client_id: str
    kind: str
    bank_code: str | None
    bank_name: str
    agencia: str | None
    conta: str | None
    product_name: str | None
    source: str


class TransactionOut(ORM):
    id: str
    bank_account_id: str
    date: date
    description: str
    amount: Decimal
    account_id: str | None
    classified_by: str | None
    confidence: float | None
    suggested_account_id: str | None


class StatementImportOut(BaseModel):
    importados: int
    duplicados: int
    classificacao: dict[str, int]


class TransactionClassifyIn(BaseModel):
    transaction_ids: list[str] = Field(min_length=1, max_length=500)
    account_id: str


class AcceptSuggestionsIn(BaseModel):
    transaction_ids: list[str] = Field(min_length=1, max_length=500)


class InvestmentIn(BaseModel):
    bank_account_id: str
    competencia: date = Field(description="Qualquer dia do mês de referência")
    saldo_inicial: Decimal = Field(ge=0)
    aplicacoes: Decimal = Field(default=Decimal(0), ge=0)
    resgates: Decimal = Field(default=Decimal(0), ge=0, description="Valor líquido creditado na conta")
    saldo_final: Decimal = Field(ge=0)
    irrf: Decimal = Field(default=Decimal(0), ge=0)
    iof: Decimal = Field(default=Decimal(0), ge=0)
    taxa_administracao: Decimal = Field(default=Decimal(0), ge=0)
    benchmark_mes_pct: Decimal | None = Field(default=None, gt=0, description="Ex.: CDI do mês em %")


class InvestmentOut(ORM):
    id: str
    bank_account_id: str
    competencia: date
    saldo_inicial: Decimal
    aplicacoes: Decimal
    resgates: Decimal
    saldo_final: Decimal
    irrf: Decimal
    iof: Decimal
    taxa_administracao: Decimal
    benchmark_mes_pct: Decimal | None
    rendimento_bruto: Decimal
    rendimento_liquido: Decimal
    taxa_bruta_pct: Decimal
    taxa_liquida_pct: Decimal
    taxa_adm_pct: Decimal
    aliquota_ir_efetiva_pct: Decimal
    pct_benchmark: Decimal | None


class IrSimulationIn(BaseModel):
    valor_aplicado: Decimal = Field(gt=0)
    valor_resgate_bruto: Decimal = Field(gt=0)
    data_aplicacao: date
    data_resgate: date


class AuditOut(ORM):
    id: int
    at: datetime
    user_id: str | None
    ip: str | None
    action: str
    entity: str
    entity_id: str | None
    changes: dict | None
