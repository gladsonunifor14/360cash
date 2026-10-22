from datetime import date, timedelta
from decimal import Decimal

from .conftest import CLIENT_CNPJ, SUPPLIER_CNPJ, nfe_xml

CHAVE = "23260319131243000197550010000007771000007770"
TODAY = date.today()


def _accounts(client, h):
    return {a["code"]: a["id"] for a in client.get("/v1/chart-accounts", headers=h).json()}


def _title(client, h, cid, **kw):
    body = {"client_id": cid, "kind": "pagar", "counterparty_name": "ENERGIA DO CEARA", "document_number": "BOL 123",
            "issue_date": str(TODAY - timedelta(days=10)), "due_date": str(TODAY), "amount": "1000.00", **kw}
    r = client.post("/v1/titles", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _ofx(rows):
    body = "".join(f"<STMTTRN><DTPOSTED>{d:%Y%m%d}<TRNAMT>{v}<FITID>{f}<MEMO>{m}</STMTTRN>" for f, d, v, m in rows)
    return f"<OFX><BANKTRANLIST>{body}</BANKTRANLIST></OFX>".encode()


def test_actionable_validation_messages(client, admin, client_company):
    r = client.post("/v1/titles", headers=admin, json={
        "client_id": client_company["id"], "kind": "pagar", "counterparty_name": "X Ltda",
        "issue_date": "2026-03-10", "due_date": "2026-03-01", "amount": "10"})
    assert r.status_code == 422
    assert r.json()["detail"] == "O campo 'Data de vencimento' não pode ser anterior à 'Data de emissão'"
    assert r.json()["erros"][0]["loc"][-1] == "due_date"  # a tela destaca e foca o campo
    t = _title(client, admin, client_company["id"])
    r = client.patch(f"/v1/titles/{t['id']}", headers=admin, json={"due_date": "2000-01-01"})
    assert r.status_code == 422 and r.json()["erros"][0]["loc"] == ["body", "due_date"]
    r = client.post("/v1/titles", headers=admin, json={"client_id": client_company["id"], "kind": "pagar",
                                                       "counterparty_name": "X", "amount": "-5"})
    msgs = r.json()["detail"]
    assert "O campo 'Data de emissão' é obrigatório" in msgs
    assert "O campo 'Valor' deve ser maior que 0" in msgs
    assert "O campo 'Favorecido/Pagador' deve ter pelo menos 2 caracteres" in msgs


def test_invoice_generates_titles_from_duplicatas(client, admin, client_company):
    xml = nfe_xml(CHAVE, SUPPLIER_CNPJ, CLIENT_CNPJ, [("5102", "Mercadoria", "900.00")]).replace(
        b"<total>", b"<cobr><dup><nDup>001</nDup><dVenc>2026-04-15</dVenc><vDup>450.00</vDup></dup>"
                    b"<dup><nDup>002</nDup><dVenc>2026-05-15</dVenc><vDup>450.00</vDup></dup></cobr><total>")
    r = client.post(f"/v1/clients/{client_company['id']}/invoices/import", headers=admin,
                    files=[("files", ("c.xml", xml, "text/xml"))]).json()[0]
    assert r["status"] == "importado" and "2 título(s) a pagar" in r["detalhe"]
    titles = client.get(f"/v1/clients/{client_company['id']}/titles", headers=admin).json()
    assert [(t["due_date"], t["amount"], t["kind"]) for t in titles] == [
        ("2026-04-15", "450.00", "pagar"), ("2026-05-15", "450.00", "pagar")]
    assert titles[0]["account_id"] == _accounts(client, admin)["3.01"]
    assert titles[0]["document_id"]  # XML anexado para conferência em tela dividida


def test_batch_requires_confirmed_total_and_history(client, admin, client_company):
    cid = client_company["id"]
    a = _title(client, admin, cid, amount="100.00", due_date=str(TODAY - timedelta(days=1)))
    b = _title(client, admin, cid, amount="250.50")
    c = _title(client, admin, cid, kind="receber", amount="80.00", due_date=str(TODAY + timedelta(days=5)))
    urg = {t["id"]: t["urgency"] for t in client.get(f"/v1/clients/{cid}/titles", headers=admin).json()}
    assert (urg[a["id"]], urg[b["id"]], urg[c["id"]]) == ("atrasado", "hoje", "proximo")

    prev = client.post("/v1/titles/batch/preview", headers=admin,
                       json={"title_ids": [a["id"], b["id"]], "action": "aprovar"}).json()
    assert prev["count"] == 2 and Decimal(prev["total"]) == Decimal("350.50")
    stale = client.post("/v1/titles/batch", headers=admin,
                        json={"title_ids": [a["id"], b["id"]], "action": "aprovar", "expected_total": "100.00"})
    assert stale.status_code == 409 and "O total do lote mudou" in stale.json()["detail"]
    ok = client.post("/v1/titles/batch", headers=admin,
                     json={"title_ids": [a["id"], b["id"]], "action": "aprovar", "expected_total": "350.50"})
    assert ok.status_code == 200

    # alteração de valor e liquidação aparecem no mini-feed
    client.patch(f"/v1/titles/{a['id']}", headers=admin, json={"amount": "120.00"})
    client.post("/v1/titles/batch", headers=admin,
                json={"title_ids": [a["id"]], "action": "liquidar", "expected_total": "120.00"})
    detail = client.get(f"/v1/titles/{a['id']}", headers=admin).json()
    feed = [h["text"] for h in detail["history"]]
    assert feed[0] == "Maria Contadora criou o título"
    assert any("“aberto” para “aprovado”" in f for f in feed)
    assert any("alterou Valor de R$ 100,00 para R$ 120,00" in f for f in feed)
    assert detail["status"] == "liquidado" and detail["urgency"] == "concluido"

    # título liquidado não entra em novo lote
    prev = client.post("/v1/titles/batch/preview", headers=admin,
                       json={"title_ids": [a["id"]], "action": "cancelar"}).json()
    assert prev["count"] == 0 and "liquidado não pode ser cancelado" in prev["ineligible"][0]["motivo"]


def test_reconciliation_match_and_divergences(client, admin, client_company):
    cid = client_company["id"]
    acc = _accounts(client, admin)
    energia = _title(client, admin, cid, account_id=acc["4.02"])  # 1000,00 vence hoje
    aluguel = _title(client, admin, cid, counterparty_name="IMOBILIARIA SOL", document_number="ALUG-03",
                     amount="2000.00", account_id=acc["4.02"])
    venda = _title(client, admin, cid, kind="receber", counterparty_name="CLIENTE ABC", amount="500.00",
                   account_id=acc["1.01"])
    ba = client.post("/v1/bank-accounts", headers=admin, json={"client_id": cid, "bank_name": "Banco X"}).json()
    ofx = _ofx([("T1", TODAY, "-1020.00", "PAGTO ENERGIA DO CEARA"),
                ("T2", TODAY, "-1500.00", "TED IMOBILIARIA SOL ALUG-03"),
                ("T3", TODAY, "480.00", "PIX CLIENTE ABC")])
    client.post(f"/v1/bank-accounts/{ba['id']}/statements", headers=admin,
                files={"file": ("e.ofx", ofx, "application/x-ofx")})

    sug = {s["transaction"]["description"]: s for s in
           client.get(f"/v1/clients/{cid}/reconciliation/suggestions", headers=admin).json()}
    s1 = sug["PAGTO ENERGIA DO CEARA"]
    assert s1["title"]["id"] == energia["id"] and Decimal(s1["difference"]) == 20 and s1["actions"] == ["juros"]
    assert sug["TED IMOBILIARIA SOL ALUG-03"]["title"]["id"] == aluguel["id"]
    assert sug["PIX CLIENTE ABC"]["actions"] == ["desconto", "parcial"]

    # confirmar "exato" com divergência devolve mensagem acionável
    r = client.post("/v1/reconciliations", headers=admin, json={
        "transaction_id": s1["transaction"]["id"], "title_id": energia["id"], "action": "exato"})
    assert r.status_code == 422 and "Use “Juros/multa”" in r.json()["detail"]

    for desc, title, action in [("PAGTO ENERGIA DO CEARA", energia, "juros"),
                                ("TED IMOBILIARIA SOL ALUG-03", aluguel, "parcial"),
                                ("PIX CLIENTE ABC", venda, "desconto")]:
        r = client.post("/v1/reconciliations", headers=admin, json={
            "transaction_id": sug[desc]["transaction"]["id"], "title_id": title["id"], "action": action})
        assert r.status_code == 201, r.text

    t = {x["id"]: x for x in client.get(f"/v1/clients/{cid}/titles", headers=admin).json()}
    assert t[energia["id"]]["status"] == "liquidado"
    assert t[aluguel["id"]]["status"] == "parcial" and Decimal(t[aluguel["id"]]["open_amount"]) == 500
    assert t[venda["id"]]["status"] == "liquidado"

    dre = client.get(f"/v1/clients/{cid}/reports/dre", headers=admin, params={
        "start": str(TODAY.replace(day=1)), "end": str(TODAY), "regime": "caixa"}).json()
    lines = {line["chave"]: Decimal(str(line["total"])) for line in dre["linhas"]}
    assert lines["receita_bruta"] == Decimal("500.00")
    assert lines["despesas_administrativas"] == Decimal("2500.00")  # 1000 energia + 1500 aluguel parcial
    assert lines["despesas_financeiras"] == Decimal("40.00")  # 20 juros + 20 desconto concedido

    # desfazer devolve o título ao estado anterior
    assert client.delete(f"/v1/reconciliations/{sug['PIX CLIENTE ABC']['transaction']['id']}",
                         headers=admin).status_code == 200
    venda_now = client.get(f"/v1/titles/{venda['id']}", headers=admin).json()
    assert venda_now["status"] == "aberto" and Decimal(venda_now["open_amount"]) == 500


def test_control_tower_and_global_search(client, admin, client_company):
    cid = client_company["id"]
    _title(client, admin, cid, amount="300.00", due_date=str(TODAY - timedelta(days=3)), counterparty_name="ATRASADA SA")
    _title(client, admin, cid, amount="1234.56", document_number="NF 9876", counterparty_doc="19.131.243/0001-97")
    tower = client.get("/v1/control-tower", headers=admin).json()
    assert tower["totals"]["atrasado"] == 1 and tower["totals"]["hoje"] == 1
    assert tower["tasks"][0]["severity"] == "atrasado"
    assert tower["tasks"][0]["route"] == "/financeiro?kind=pagar&urgency=atrasado"
    assert tower["clients"][0]["client_name"] == "Loja Teste"

    def types(q):
        return {(h["type"], h["label"]) for h in client.get("/v1/search", headers=admin, params={"q": q}).json()}

    assert ("titulo", "A pagar: ENERGIA DO CEARA") in types("1.234,56")
    assert ("titulo", "A pagar: ENERGIA DO CEARA") in types("19.131.243/0001-97")
    assert ("titulo", "A pagar: ENERGIA DO CEARA") in types("9876")
    assert ("cliente", "COMERCIO DE TESTE LTDA") in types(CLIENT_CNPJ[:8])
    assert ("titulo", "A pagar: ATRASADA SA") in types("atrasada")


def test_reconciliation_ignores_out_of_window_and_far_amounts(client, admin, client_company):
    cid = client_company["id"]
    _title(client, admin, cid, kind="receber", counterparty_name="CLIENTE XYZ", amount="6100.00")
    ba = client.post("/v1/bank-accounts", headers=admin, json={"client_id": cid, "bank_name": "Banco X"}).json()
    ofx = _ofx([("OLD", TODAY - timedelta(days=150), "6100.00", "PIX RECEBIDO CLIENTE XYZ"),  # antes da emissão
                ("FAR", TODAY, "4000.00", "DEPOSITO EM DINHEIRO")])  # 34% de diferença e sem evidência
    client.post(f"/v1/bank-accounts/{ba['id']}/statements", headers=admin,
                files={"file": ("e.ofx", ofx, "application/x-ofx")})
    assert client.get(f"/v1/clients/{cid}/reconciliation/suggestions", headers=admin).json() == []
