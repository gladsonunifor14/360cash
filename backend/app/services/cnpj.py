"""Validação e consulta de CNPJ.

A Receita Federal não oferece API pública gratuita de consulta online; os dados abertos
do CNPJ são distribuídos pela RFB e servidos por provedores como BrasilAPI (primário) e
ReceitaWS (fallback). O resultado é normalizado para o formato interno do 360cash.
"""

import re
from datetime import date, datetime

import httpx

from app.core.config import get_settings


class CnpjError(Exception):
    pass


def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def is_valid_cnpj(value: str) -> bool:
    cnpj = only_digits(value)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    def digit(base: str, weights: list[int]) -> str:
        total = sum(int(d) * w for d, w in zip(base, weights, strict=True))
        r = total % 11
        return "0" if r < 2 else str(11 - r)

    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = digit(cnpj[:12], w1)
    d2 = digit(cnpj[:12] + d1, [6] + w1)
    return cnpj[12:] == d1 + d2


def format_cnpj(cnpj: str) -> str:
    c = only_digits(cnpj)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else cnpj


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def normalize(data: dict) -> dict:
    """Converte respostas de BrasilAPI ou ReceitaWS para um dicionário comum."""
    if "razao_social" in data:  # BrasilAPI
        cnae = data.get("cnae_fiscal")
        return {
            "cnpj": only_digits(data.get("cnpj", "")),
            "razao_social": data.get("razao_social"),
            "nome_fantasia": data.get("nome_fantasia") or None,
            "email": (data.get("email") or None),
            "telefone": data.get("ddd_telefone_1") or None,
            "situacao_cadastral": data.get("descricao_situacao_cadastral"),
            "natureza_juridica": data.get("natureza_juridica"),
            "cnae_principal": f"{cnae} - {data.get('cnae_fiscal_descricao')}" if cnae else None,
            "data_abertura": _parse_date(data.get("data_inicio_atividade")),
            "regime_tributario": "simples"
            if data.get("opcao_pelo_simples")
            else ("mei" if data.get("opcao_pelo_mei") else None),
            "endereco": {
                "logradouro": " ".join(
                    x for x in [data.get("descricao_tipo_de_logradouro"), data.get("logradouro")] if x
                ),
                "numero": data.get("numero"),
                "complemento": data.get("complemento"),
                "bairro": data.get("bairro"),
                "municipio": data.get("municipio"),
                "uf": data.get("uf"),
                "cep": data.get("cep"),
            },
        }
    if "nome" in data:  # ReceitaWS
        atv = (data.get("atividade_principal") or [{}])[0]
        simples = (data.get("simples") or {}).get("optante")
        return {
            "cnpj": only_digits(data.get("cnpj", "")),
            "razao_social": data.get("nome"),
            "nome_fantasia": data.get("fantasia") or None,
            "email": data.get("email") or None,
            "telefone": data.get("telefone") or None,
            "situacao_cadastral": data.get("situacao"),
            "natureza_juridica": data.get("natureza_juridica"),
            "cnae_principal": f"{atv.get('code')} - {atv.get('text')}" if atv else None,
            "data_abertura": _parse_date(data.get("abertura")),
            "regime_tributario": "simples" if simples else None,
            "endereco": {
                "logradouro": data.get("logradouro"),
                "numero": data.get("numero"),
                "complemento": data.get("complemento"),
                "bairro": data.get("bairro"),
                "municipio": data.get("municipio"),
                "uf": data.get("uf"),
                "cep": only_digits(data.get("cep", "")),
            },
        }
    raise CnpjError("Formato de resposta desconhecido")


def lookup(cnpj: str) -> tuple[dict, dict]:
    """Retorna (dados normalizados, resposta bruta). Tenta cada provedor em ordem."""
    cnpj = only_digits(cnpj)
    if not is_valid_cnpj(cnpj):
        raise CnpjError("CNPJ inválido")
    errors = []
    for url in get_settings().cnpj_providers:
        try:
            resp = httpx.get(url.format(cnpj=cnpj), timeout=10, headers={"Accept": "application/json"})
            if resp.status_code == 404:
                raise CnpjError("CNPJ não encontrado na base da Receita Federal")
            resp.raise_for_status()
            raw = resp.json()
            if raw.get("status") == "ERROR":
                raise CnpjError(raw.get("message", "CNPJ não encontrado"))
            return normalize(raw), raw
        except CnpjError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            errors.append(f"{url.split('/')[2]}: {exc.__class__.__name__}")
    raise CnpjError("Serviço de consulta de CNPJ indisponível (" + "; ".join(errors) + ")")
