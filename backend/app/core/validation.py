"""Erros de validação acionáveis, em português e citando o campo pelo nome exibido na tela."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

FIELD_LABELS = {
    "email": "E-mail", "password": "Senha", "new_password": "Nova senha", "current_password": "Senha atual",
    "code": "Código", "cnpj": "CNPJ", "office_cnpj": "CNPJ do escritório", "name": "Nome",
    "client_id": "Empresa", "kind": "Tipo", "counterparty_name": "Favorecido/Pagador", "counterparty_doc": "CPF/CNPJ",
    "document_number": "Nº do documento", "description": "Descrição", "issue_date": "Data de emissão",
    "due_date": "Data de vencimento", "amount": "Valor", "account_id": "Conta gerencial",
    "title_ids": "Títulos selecionados", "transaction_ids": "Lançamentos selecionados", "action": "Ação",
    "expected_total": "Total confirmado", "monthly_fee": "Honorários mensais", "start_date": "Data de início",
    "valid_from": "Validade inicial", "valid_until": "Validade final", "saldo_inicial": "Saldo inicial",
    "saldo_final": "Saldo final", "aplicacoes": "Aplicações", "resgates": "Resgates", "competencia": "Mês",
    "bank_name": "Banco", "start": "Data inicial", "end": "Data final", "q": "Busca",
}


def _label(loc: tuple) -> str:
    field = next((str(p) for p in reversed(loc) if isinstance(p, str) and p not in ("body", "query", "path")), "")
    return FIELD_LABELS.get(field, field.replace("_", " ").capitalize())


def _message(err: dict) -> str:
    label, kind, ctx = _label(tuple(err.get("loc", ()))), err.get("type", ""), err.get("ctx") or {}
    if kind == "value_error":  # mensagens já escritas em português nos validadores
        return str(ctx.get("error", err.get("msg", ""))).removeprefix("Value error, ")
    messages = {
        "missing": f"O campo '{label}' é obrigatório",
        "greater_than": f"O campo '{label}' deve ser maior que {ctx.get('gt')}",
        "greater_than_equal": f"O campo '{label}' deve ser maior ou igual a {ctx.get('ge')}",
        "less_than_equal": f"O campo '{label}' deve ser no máximo {ctx.get('le')}",
        "string_too_short": f"O campo '{label}' deve ter pelo menos {ctx.get('min_length')} caracteres",
        "string_too_long": f"O campo '{label}' deve ter no máximo {ctx.get('max_length')} caracteres",
        "too_short": f"Selecione pelo menos {ctx.get('min_length')} item(ns) em '{label}'",
        "too_long": f"O campo '{label}' aceita no máximo {ctx.get('max_length')} itens",
        "string_pattern_mismatch": f"O campo '{label}' está em formato inválido",
        "date_from_datetime_parsing": f"O campo '{label}' deve ser uma data válida (dd/mm/aaaa)",
        "date_parsing": f"O campo '{label}' deve ser uma data válida (dd/mm/aaaa)",
        "date_type": f"O campo '{label}' deve ser uma data válida (dd/mm/aaaa)",
        "decimal_parsing": f"O campo '{label}' deve ser um valor numérico (ex.: 1234,56)",
        "decimal_max_places": f"O campo '{label}' aceita no máximo {ctx.get('decimal_places')} casas decimais",
        "literal_error": f"O campo '{label}' deve ser um destes valores: {ctx.get('expected')}",
        "value_error.email": f"O campo '{label}' deve ser um e-mail válido",
        "bool_parsing": f"O campo '{label}' deve ser verdadeiro ou falso",
    }
    if kind in messages:
        return messages[kind]
    if "email" in str(err.get("msg", "")).lower():
        return f"O campo '{label}' deve ser um e-mail válido"
    return f"O campo '{label}' é inválido"


async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [{"campo": _label(tuple(e.get("loc", ()))), "loc": list(e.get("loc", ())), "mensagem": _message(e)}
              for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "; ".join(dict.fromkeys(e["mensagem"] for e in errors)),
                                                  "erros": errors})


class FieldError(Exception):
    """Regra de negócio violada em um campo específico (vira 422 com `erros[].loc` para a tela destacar)."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field, self.message = field, message


async def field_error_handler(_: Request, exc: FieldError) -> JSONResponse:
    return JSONResponse(status_code=422, content={
        "detail": exc.message,
        "erros": [{"campo": FIELD_LABELS.get(exc.field, exc.field), "loc": ["body", exc.field],
                   "mensagem": exc.message}],
    })
