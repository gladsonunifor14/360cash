"""Importação de extratos via Open Finance Brasil, através de agregador autorizado.

Uma instituição só pode consumir dados do Open Finance diretamente se for participante
regulada pelo Banco Central (instituição financeira/de pagamento autorizada, ou ITP).
Para um BPO/escritório contábil, o caminho viável é usar um agregador participante
(ex.: Pluggy, Belvo, Celcoin), que coleta o consentimento do cliente no app do banco
e expõe contas e transações via API. Ver docs/open-finance.md.

Este módulo define a interface do provedor e uma implementação para a API da Pluggy.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.services.bank_parser import ParsedTransaction


class OpenFinanceError(Exception):
    pass


@dataclass
class RemoteAccount:
    id: str
    name: str
    number: str | None
    kind: str  # corrente | aplicacao
    balance: Decimal | None


class OpenFinanceProvider(Protocol):
    def connect_token(self, client_user_id: str) -> str: ...
    def list_accounts(self, item_id: str) -> list[RemoteAccount]: ...
    def list_transactions(self, account_id: str, start: date, end: date) -> list[ParsedTransaction]: ...


class PluggyProvider:
    BASE = "https://api.pluggy.ai"

    def __init__(self, client_id: str, client_secret: str):
        self._client_id, self._client_secret = client_id, client_secret
        self._api_key: str | None = None

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            r = httpx.post(f"{self.BASE}/auth", json={"clientId": self._client_id,
                                                       "clientSecret": self._client_secret}, timeout=15)
            r.raise_for_status()
            self._api_key = r.json()["apiKey"]
        return {"X-API-KEY": self._api_key}

    def connect_token(self, client_user_id: str) -> str:
        """Token para o widget de conexão (o cliente autoriza o consentimento no próprio banco)."""
        r = httpx.post(f"{self.BASE}/connect_token", json={"clientUserId": client_user_id},
                       headers=self._headers(), timeout=15)
        r.raise_for_status()
        return r.json()["accessToken"]

    def list_accounts(self, item_id: str) -> list[RemoteAccount]:
        r = httpx.get(f"{self.BASE}/accounts", params={"itemId": item_id}, headers=self._headers(), timeout=15)
        r.raise_for_status()
        out = []
        for a in r.json().get("results", []):
            if a.get("type") != "BANK":
                continue
            out.append(RemoteAccount(
                id=a["id"], name=a.get("name") or "", number=a.get("number"),
                kind="corrente" if a.get("subtype") == "CHECKING_ACCOUNT" else "aplicacao",
                balance=Decimal(str(a["balance"])) if a.get("balance") is not None else None,
            ))
        return out

    def list_transactions(self, account_id: str, start: date, end: date) -> list[ParsedTransaction]:
        out, page = [], 1
        while True:
            r = httpx.get(
                f"{self.BASE}/transactions",
                params={"accountId": account_id, "from": start.isoformat(), "to": end.isoformat(),
                        "pageSize": 500, "page": page},
                headers=self._headers(), timeout=30,
            )
            r.raise_for_status()
            body = r.json()
            for t in body.get("results", []):
                value = abs(Decimal(str(t["amount"])))
                out.append(ParsedTransaction(
                    fitid=t["id"][:100],
                    date=date.fromisoformat(t["date"][:10]),
                    description=(t.get("description") or "SEM HISTORICO")[:300],
                    amount=-value if t.get("type") == "DEBIT" else value,
                ))
            if page >= body.get("totalPages", 1):
                return out
            page += 1


def get_provider() -> OpenFinanceProvider:
    s = get_settings()
    if not (s.pluggy_client_id and s.pluggy_client_secret):
        raise OpenFinanceError("Open Finance não configurado (CASH360_PLUGGY_CLIENT_ID/SECRET)")
    return PluggyProvider(s.pluggy_client_id, s.pluggy_client_secret)
