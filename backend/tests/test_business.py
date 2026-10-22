from decimal import Decimal

from app.services import email as mailer
from app.services.investments import calcular_ir_resgate, calcular_mes

from .conftest import CLIENT_CNPJ, OFFICE_CNPJ, PASSWORD, SUPPLIER_CNPJ, auth, login, nfe_xml

CHAVE_VENDA = "23260311444777000161550010000001231000001230"
CHAVE_COMPRA = "23260319131243000197550010000004561000004560"
CHAVE_DEVOL = "23260311444777000161550010000001241000001240"

OFX = """OFXHEADER:100
DATA:OFXSGML
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>BRL<BANKACCTFROM><BANKID>001<BRANCHID>1234<ACCTID>98765-4</BANKACCTFROM>
<BANKTRANLIST>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260316<TRNAMT>1000.00<FITID>A1<MEMO>PIX RECEBIDO CLIENTE ABC 16/03</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260317<TRNAMT>-350.00<FITID>A2<MEMO>PAGTO ALUGUEL MARCO 123456</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260318<TRNAMT>-12.90<FITID>A3<MEMO>TARIFA PACOTE SERVICOS</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260320<TRNAMT>-2000.00<FITID>A4<MEMO>FOLHA PAGAMENTO SALARIOS</STMTTRN>
</BANKTRANLIST><LEDGERBAL><BALAMT>5000.00</LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""

OFX_ABRIL = """<OFX><BANKTRANLIST>
<STMTTRN><DTPOSTED>20260417<TRNAMT>-350.00<FITID>B1<MEMO>PAGTO ALUGUEL ABRIL 654321</STMTTRN>
<STMTTRN><DTPOSTED>20260418<TRNAMT>-15.50<FITID>B2<MEMO>TARIFA PACOTE SERVICOS</STMTTRN>
<STMTTRN><DTPOSTED>20260419<TRNAMT>-99.00<FITID>B3<MEMO>COMPRA CARTAO PADARIA</STMTTRN>
</BANKTRANLIST></OFX>"""


def _accounts(client, h):
    return {a["code"]: a["id"] for a in client.get("/v1/chart-accounts", headers=h).json()}


def _import(client, h, cid, name, xml):
    r = client.post(f"/v1/clients/{cid}/invoices/import", headers=h, files=[("files", (name, xml, "text/xml"))])
    assert r.status_code == 200, r.text
    return r.json()[0]


def test_client_from_receita_and_tenant_isolation(client, admin, client_company):
    assert client_company["razao_social"] == "COMERCIO DE TESTE LTDA"
    assert client_company["regime_tributario"] == "presumido"
    assert client.post("/v1/clients", json={"cnpj": CLIENT_CNPJ}, headers=admin).status_code == 409
    assert client.post("/v1/clients", json={"cnpj": "11111111111111"}, headers=admin).status_code == 422

    # outro escritório não enxerga o cliente
    r = client.post("/v1/auth/register", json={
        "office_cnpj": SUPPLIER_CNPJ, "name": "Outro Escritório", "email": "outro@x.com.br",
        "password": PASSWORD, "accept_terms": True})
    assert r.status_code == 201
    other = auth(login(client, "outro@x.com.br"))
    assert client.get(f"/v1/clients/{client_company['id']}", headers=other).status_code == 404
    assert client.get("/v1/clients", headers=other).json() == []


def test_contract_adhesion_by_client_user(client, admin, client_company):
    r = client.post("/v1/contracts", headers=admin, json={
        "client_id": client_company["id"], "monthly_fee": "1500.00", "start_date": "2026-04-01"})
    assert r.status_code == 201, r.text
    contract = r.json()
    assert "COMERCIO DE TESTE LTDA" in contract["content"]
    assert "R$ 1.500,00" in contract["content"]
    assert "11.222.333/0001-81" in contract["content"]
    # staff não pode aceitar pelo cliente
    assert client.post(f"/v1/contracts/{contract['id']}/accept", headers=admin).status_code == 403

    r = client.post("/v1/users", headers=admin, json={
        "name": "João Cliente", "email": "joao@loja.com.br", "role": "cliente", "client_id": client_company["id"]})
    assert r.status_code == 201, r.text
    token = mailer.outbox[-1]["text"].split("token=")[1].split()[0]
    client.post("/v1/auth/password/reset", json={"token": token, "new_password": "Cliente#Senha2026"})
    joao = auth(login(client, "joao@loja.com.br", "Cliente#Senha2026"))

    assert len(client.get("/v1/terms/pending", headers=joao).json()) == 3
    assert len(client.post("/v1/terms/accept", headers=joao).json()) == 3

    r = client.post(f"/v1/contracts/{contract['id']}/accept", headers=joao)
    assert r.status_code == 200
    assert r.json()["status"] == "aceito"
    assert r.json()["accepted_ip"]
    # cliente não acessa área do escritório
    assert client.get("/v1/users", headers=joao).status_code == 403
    assert client.post("/v1/clients", json={"cnpj": SUPPLIER_CNPJ}, headers=joao).status_code == 403

    audit = client.get("/v1/audit", headers=admin, params={"entity": "contracts"}).json()
    actions = [a["action"] for a in audit]
    assert "create" in actions and "update" in actions
    upd = next(a for a in audit if a["action"] == "update")
    assert upd["changes"]["status"] == {"de": "pendente", "para": "aceito"}


def test_nfe_import_classification_by_cfop(client, admin, client_company):
    cid = client_company["id"]
    acc = _accounts(client, admin)

    venda = _import(client, admin, cid, "venda.xml", nfe_xml(
        CHAVE_VENDA, CLIENT_CNPJ, SUPPLIER_CNPJ, [("5102", "Produto A", "1000.00"), ("5933", "Instalação", "200.00")],
        icms="180.00", pis="7.80", cofins="36.00"))
    assert venda["status"] == "importado"
    compra = _import(client, admin, cid, "compra.xml", nfe_xml(
        CHAVE_COMPRA, SUPPLIER_CNPJ, CLIENT_CNPJ, [("5102", "Mercadoria revenda", "400.00"),
                                                   ("5556", "Material escritório", "50.00")]))
    assert compra["status"] == "importado"
    assert _import(client, admin, cid, "venda.xml", nfe_xml(
        CHAVE_VENDA, CLIENT_CNPJ, SUPPLIER_CNPJ, [("5102", "Produto A", "1000.00")]))["status"] == "duplicado"

    inv = client.get(f"/v1/invoices/{venda['id']}", headers=admin).json()
    assert inv["direction"] == "emitida"
    assert [i["account_id"] for i in inv["items"]] == [acc["1.01"], acc["1.02"]]

    inv = client.get(f"/v1/invoices/{compra['id']}", headers=admin).json()
    assert inv["direction"] == "recebida"
    # CFOP do fornecedor 5102 vira 1102 na visão do cliente (compra para comercialização)
    assert [i["cfop_cliente"] for i in inv["items"]] == ["1102", "1556"]
    assert [i["account_id"] for i in inv["items"]] == [acc["3.01"], acc["4.04"]]

    # NF de terceiros é rejeitada
    other = _import(client, admin, cid, "x.xml", nfe_xml(
        "23260300000000000191550010000009991000009990", SUPPLIER_CNPJ, OFFICE_CNPJ, [("5102", "X", "1.00")]))
    assert other["status"] == "erro"

    # DRE por competência
    dre = client.get(f"/v1/clients/{cid}/reports/dre", headers=admin,
                     params={"start": "2026-03-01", "end": "2026-03-31"}).json()
    lines = {line["chave"]: Decimal(str(line["total"])) for line in dre["linhas"]}
    assert lines["receita_bruta"] == Decimal("1200.00")
    assert lines["deducoes"] == Decimal("223.80")  # ICMS+PIS+COFINS (lucro presumido)
    assert lines["custos"] == Decimal("400.00")
    assert lines["despesas_administrativas"] == Decimal("50.00")
    assert lines["lucro_bruto"] == Decimal("576.20")
    assert dre["cabecalho"]["elaborado_por"]["cnpj"] == "11.222.333/0001-81"
    assert dre["cabecalho"]["elaborado_por"]["crc"] == "CE-012345/O-1"

    # evento de cancelamento
    cancel = f"""<procEventoNFe xmlns="http://www.portalfiscal.inf.br/nfe"><evento><infEvento>
    <chNFe>{CHAVE_VENDA}</chNFe><tpEvento>110111</tpEvento></infEvento></evento></procEventoNFe>""".encode()
    assert _import(client, admin, cid, "canc.xml", cancel)["status"] == "cancelamento"
    dre = client.get(f"/v1/clients/{cid}/reports/dre", headers=admin,
                     params={"start": "2026-03-01", "end": "2026-03-31"}).json()
    assert Decimal(str(dre["linhas"][0]["total"])) == Decimal("0")


def test_xml_external_entity_is_blocked(client, admin, client_company):
    evil = b"""<?xml version="1.0"?><!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
    <nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe1">&xxe;</infNFe></NFe></nfeProc>"""
    r = _import(client, admin, client_company["id"], "evil.xml", evil)
    assert r["status"] == "erro"


def test_bank_statement_learning_and_cash_flow(client, admin, client_company):
    cid = client_company["id"]
    acc = _accounts(client, admin)
    ba = client.post("/v1/bank-accounts", headers=admin, json={
        "client_id": cid, "bank_code": "001", "bank_name": "Banco do Brasil", "agencia": "1234",
        "conta": "98765-4"}).json()
    r = client.post(f"/v1/bank-accounts/{ba['id']}/statements", headers=admin,
                    files={"file": ("extrato.ofx", OFX.encode(), "application/x-ofx")})
    assert r.status_code == 200, r.text
    assert r.json()["importados"] == 4
    # reimportar não duplica
    r = client.post(f"/v1/bank-accounts/{ba['id']}/statements", headers=admin,
                    files={"file": ("extrato.ofx", OFX.encode(), "application/x-ofx")})
    assert r.json() == {"importados": 0, "duplicados": 4, "classificacao": {"aplicados": 0, "sugeridos": 0,
                                                                            "sem_sugestao": 4}}

    txs = {t["description"]: t for t in client.get(f"/v1/clients/{cid}/transactions", headers=admin).json()}
    plan = {"PIX RECEBIDO CLIENTE ABC 16/03": "1.01", "PAGTO ALUGUEL MARCO 123456": "4.02",
            "TARIFA PACOTE SERVICOS": "4.06", "FOLHA PAGAMENTO SALARIOS": "4.01"}
    for desc, code in plan.items():
        r = client.post("/v1/transactions/classify", headers=admin,
                        json={"transaction_ids": [txs[desc]["id"]], "account_id": acc[code]})
        assert r.status_code == 200

    # abril: IA replica a classificação aprendida
    r = client.post(f"/v1/bank-accounts/{ba['id']}/statements", headers=admin,
                    files={"file": ("abril.ofx", OFX_ABRIL.encode(), "application/x-ofx")})
    assert r.json()["classificacao"]["aplicados"] >= 2
    txs = {t["description"]: t for t in client.get(f"/v1/clients/{cid}/transactions", headers=admin,
                                                   params={"start": "2026-04-01"}).json()}
    assert txs["TARIFA PACOTE SERVICOS"]["account_id"] == acc["4.06"]
    assert txs["TARIFA PACOTE SERVICOS"]["classified_by"] == "ia"
    assert txs["PAGTO ALUGUEL ABRIL 654321"]["account_id"] == acc["4.02"]
    assert txs["COMPRA CARTAO PADARIA"]["account_id"] is None

    fc = client.get(f"/v1/clients/{cid}/reports/cash-flow", headers=admin,
                    params={"start": "2026-03-01", "end": "2026-04-30"}).json()
    assert Decimal(str(fc["entradas"]["2026-03"])) == Decimal("1000.00")
    assert Decimal(str(fc["saidas"]["2026-03"])) == Decimal("-2362.90")
    assert Decimal(str(fc["geracao_acumulada"]["2026-04"])) == Decimal("-1827.40")

    dre = client.get(f"/v1/clients/{cid}/reports/dre", headers=admin,
                     params={"start": "2026-03-01", "end": "2026-03-31", "regime": "caixa"}).json()
    lines = {line["chave"]: Decimal(str(line["total"])) for line in dre["linhas"]}
    assert lines["receita_bruta"] == Decimal("1000.00")
    assert lines["despesas_pessoal"] == Decimal("2000.00")
    assert lines["despesas_financeiras"] == Decimal("12.90")
    assert lines["lucro_liquido"] == Decimal("-1362.90")

    mgmt = client.get(f"/v1/clients/{cid}/reports/management", headers=admin,
                      params={"start": "2026-03-01", "end": "2026-04-30"}).json()
    assert mgmt["indicadores"]["lancamentos_pendentes"] == 1
    assert mgmt["cabecalho"]["elaborado_por"]["razao_social"] == "CONTABIL EXEMPLO LTDA"


def test_investment_calculations(client, admin, client_company):
    calc = calcular_mes(Decimal("100000"), Decimal("10000"), Decimal("5000"), Decimal("105900"),
                        irrf=Decimal("150"), iof=Decimal("0"), taxa_administracao=Decimal("50"),
                        benchmark_mes_pct=Decimal("0.90"))
    # bruto = 105900 - 100000 - 10000 + 5000 + 150 + 50 = 1100
    assert calc["rendimento_bruto"] == Decimal("1100.00")
    assert calc["rendimento_liquido"] == Decimal("900.00")
    # base = 100000 + (10000-5000)/2 = 102500 → 1,073171%
    assert calc["taxa_bruta_pct"] == Decimal("1.073171")
    assert calc["pct_benchmark"] == Decimal("119.2412")

    ir = calcular_ir_resgate(Decimal("10000"), Decimal("11000"), __import__("datetime").date(2025, 1, 1),
                             __import__("datetime").date(2025, 12, 1))
    assert ir["aliquota_ir_pct"] == Decimal("20.0") and ir["irrf"] == Decimal("200.00")

    ba = client.post("/v1/bank-accounts", headers=admin, json={
        "client_id": client_company["id"], "kind": "aplicacao", "bank_name": "Itaú", "product_name": "CDB DI"}).json()
    body = {"bank_account_id": ba["id"], "competencia": "2026-03-31", "saldo_inicial": "100000",
            "aplicacoes": "10000", "resgates": "5000", "saldo_final": "105900", "irrf": "150",
            "taxa_administracao": "50", "benchmark_mes_pct": "0.90"}
    r = client.post("/v1/investments", headers=admin, json=body)
    assert r.status_code == 201, r.text
    assert r.json()["competencia"] == "2026-03-01"
    assert Decimal(r.json()["rendimento_liquido"]) == Decimal("900.00")
    # mesmo mês atualiza (upsert)
    client.post("/v1/investments", headers=admin, json={**body, "saldo_final": "106000"})
    assert len(client.get(f"/v1/clients/{client_company['id']}/investments", headers=admin).json()) == 1


def test_documents_and_power_of_attorney(client, admin, client_company):
    r = client.post("/v1/documents", headers=admin, data={"category": "procuracao", "client_id": client_company["id"]},
                    files={"file": ("procuracao.pdf", b"%PDF-1.4 teste", "application/pdf")})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert len(doc["sha256"]) == 64
    assert client.get(f"/v1/documents/{doc['id']}/download", headers=admin).content == b"%PDF-1.4 teste"
    bad = client.post("/v1/documents", headers=admin, files={"file": ("x.exe", b"MZ", "application/x-msdownload")})
    assert bad.status_code == 415

    r = client.post("/v1/powers-of-attorney", headers=admin, json={
        "client_id": client_company["id"], "outorgante": "COMERCIO DE TESTE LTDA",
        "outorgado": "CONTABIL EXEMPLO LTDA", "finalidade": "Acesso ao e-CAC", "orgao": "RFB",
        "valid_from": "2026-01-01", "valid_until": "2027-01-01", "document_id": doc["id"]})
    assert r.status_code == 201, r.text
    assert client.post(f"/v1/powers-of-attorney/{r.json()['id']}/revoke", headers=admin).json()["revoked_at"]


def test_api_key_integration(client, admin, client_company):
    r = client.post("/v1/api-keys", headers=admin, json={"name": "ERP do cliente"})
    assert r.status_code == 201
    key = r.json()["key"]
    r = client.get("/v1/clients", headers={"X-API-Key": key})
    assert r.status_code == 200 and len(r.json()) == 1
    key_id = client.get("/v1/api-keys", headers=admin).json()[0]["id"]
    assert client.delete(f"/v1/api-keys/{key_id}", headers=admin).status_code == 200
    assert client.get("/v1/clients", headers={"X-API-Key": key}).status_code == 401
