import os
import re
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["CASH360_DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["CASH360_STORAGE_DIR"] = f"{_tmp}/storage"
os.environ["CASH360_ENVIRONMENT"] = "test"
os.environ["CASH360_RATE_LIMIT_AUTH_PER_MINUTE"] = "1000"
os.environ["CASH360_RESEND_API_KEY"] = ""
os.environ["CASH360_ANTHROPIC_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core import ratelimit  # noqa: E402
from app.core.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import cnpj as cnpj_service  # noqa: E402
from app.services import email as mailer  # noqa: E402

OFFICE_CNPJ = "11222333000181"
CLIENT_CNPJ = "11444777000161"
SUPPLIER_CNPJ = "19131243000197"
PASSWORD = "Senha@Forte2026"

FAKE_RECEITA = {
    OFFICE_CNPJ: {"razao_social": "CONTABIL EXEMPLO LTDA", "nome_fantasia": "Contábil Exemplo"},
    CLIENT_CNPJ: {"razao_social": "COMERCIO DE TESTE LTDA", "nome_fantasia": "Loja Teste"},
}


def fake_lookup(cnpj: str):
    cnpj = cnpj_service.only_digits(cnpj)
    if not cnpj_service.is_valid_cnpj(cnpj):
        raise cnpj_service.CnpjError("CNPJ inválido")
    base = FAKE_RECEITA.get(cnpj, {"razao_social": f"EMPRESA {cnpj}", "nome_fantasia": None})
    raw = {
        "cnpj": cnpj, **base, "descricao_situacao_cadastral": "ATIVA", "cnae_fiscal": 4751201,
        "cnae_fiscal_descricao": "Comércio varejista", "natureza_juridica": "206-2 - Sociedade Empresária Limitada",
        "data_inicio_atividade": "2015-03-10", "uf": "CE", "municipio": "FORTALEZA", "opcao_pelo_simples": False,
        "email": "financeiro@exemplo.com.br",
    }
    return cnpj_service.normalize(raw), raw


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    mailer.outbox.clear()
    ratelimit.reset()
    monkeypatch.setattr(cnpj_service, "lookup", fake_lookup)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def last_otp() -> str:
    return re.search(r"\b(\d{6})\b", mailer.outbox[-1]["text"]).group(1)


def login(c: TestClient, email: str, password: str = PASSWORD) -> dict:
    r = c.post("/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    r = c.post("/v1/auth/otp/verify", json={"otp_token": r.json()["otp_token"], "code": last_otp()})
    assert r.status_code == 200, r.text
    return r.json()


def auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def admin(client) -> dict:
    r = client.post("/v1/auth/register", json={
        "office_cnpj": "11.222.333/0001-81", "name": "Maria Contadora", "email": "maria@contabil.com.br",
        "password": PASSWORD, "crc": "CE-012345/O-1", "accept_terms": True,
    })
    assert r.status_code == 201, r.text
    return auth(login(client, "maria@contabil.com.br"))


@pytest.fixture
def client_company(client, admin) -> dict:
    r = client.post("/v1/clients", json={"cnpj": CLIENT_CNPJ, "regime_tributario": "presumido"}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def nfe_xml(chave: str, emit: str, dest: str, items: list[tuple[str, str, str]], dh="2026-03-15T10:00:00-03:00",
            icms="0.00", pis="0.00", cofins="0.00") -> bytes:
    """items: [(cfop, descricao, valor)]"""
    dets = "".join(
        f'<det nItem="{i + 1}"><prod><cProd>P{i}</cProd><xProd>{d}</xProd><NCM>12345678</NCM><CFOP>{c}</CFOP>'
        f"<qCom>1.0000</qCom><vUnCom>{v}</vUnCom><vProd>{v}</vProd></prod></det>"
        for i, (c, d, v) in enumerate(items)
    )
    total = sum(float(v) for _, _, v in items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00"><NFe><infNFe Id="NFe{chave}" versao="4.00">
<ide><natOp>VENDA</natOp><mod>55</mod><serie>1</serie><nNF>123</nNF><dhEmi>{dh}</dhEmi><tpNF>1</tpNF></ide>
<emit><CNPJ>{emit}</CNPJ><xNome>EMITENTE {emit}</xNome></emit>
<dest><CNPJ>{dest}</CNPJ><xNome>DESTINATARIO {dest}</xNome></dest>{dets}
<total><ICMSTot><vProd>{total:.2f}</vProd><vDesc>0.00</vDesc><vFrete>0.00</vFrete><vICMS>{icms}</vICMS>
<vST>0.00</vST><vIPI>0.00</vIPI><vPIS>{pis}</vPIS><vCOFINS>{cofins}</vCOFINS><vNF>{total:.2f}</vNF></ICMSTot></total>
</infNFe></NFe><protNFe><infProt><chNFe>{chave}</chNFe></infProt></protNFe></nfeProc>""".encode()
