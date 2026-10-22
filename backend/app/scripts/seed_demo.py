"""Popula um ambiente de demonstração sem depender da consulta à Receita Federal.

Uso: python -m app.scripts.seed_demo  (cria escritório, admin, cliente, notas, extratos e aplicações)
Login: admin@demo.360cash.tech / Demo@360cash  (o OTP aparece no log da API em desenvolvimento)
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_password, utcnow
from app.models import (
    BankAccount,
    BankTransaction,
    Client,
    InvestmentStatement,
    Invoice,
    InvoiceItem,
    Office,
    Title,
    User,
)
from app.routers.fiscal import _classify_item, cfop_for_client
from app.services import classifier, investments
from app.services.accounting import account_by_code, seed_cfop_rules, seed_chart
from app.services.bank_parser import normalize_description
from app.services.defaults import accept_current_terms, seed_office_defaults

OFFICE_CNPJ, CLIENT_CNPJ = "11222333000181", "11444777000161"
EMAIL, PASSWORD = "admin@demo.360cash.tech", "Demo@360cash"


def main() -> None:
    if get_settings().is_production:
        raise SystemExit("Não execute o seed de demonstração em produção")
    rnd = random.Random(360)  # noqa: S311 (dados fictícios, não criptográfico)
    db = SessionLocal()
    seed_cfop_rules(db)
    if db.scalar(select(Office).where(Office.cnpj == OFFICE_CNPJ)):
        print("Demo já existe.")
        return
    office = Office(cnpj=OFFICE_CNPJ, razao_social="CONTABILIDADE DEMONSTRAÇÃO LTDA", nome_fantasia="Contábil Demo",
                    crc="CE-000000/O-0", responsavel_tecnico="Contador Demo",
                    endereco={"municipio": "FORTALEZA", "uf": "CE"})
    db.add(office)
    db.flush()
    seed_chart(db, office.id)
    seed_office_defaults(db, office)
    admin = User(office_id=office.id, name="Contador Demo", email=EMAIL, password_hash=hash_password(PASSWORD),
                 role="admin")
    client = Client(office_id=office.id, cnpj=CLIENT_CNPJ, razao_social="COMÉRCIO EXEMPLO LTDA",
                    nome_fantasia="Loja Exemplo", regime_tributario="presumido", situacao_cadastral="ATIVA",
                    endereco={"municipio": "FORTALEZA", "uf": "CE"})
    db.add_all([admin, client])
    db.flush()
    accept_current_terms(db, admin, "127.0.0.1", "seed")
    accounts = account_by_code(db, office.id)

    # notas fiscais de jan a jun
    n = 1
    for month in range(1, 7):
        for _ in range(14):
            emitted = rnd.random() < 0.7
            d = date(2026, month, rnd.randint(1, 28))
            items = [("5102", "Mercadoria", Decimal(rnd.randint(2500, 7000)))] if emitted else \
                [(rnd.choice(["5102", "5102", "5556"]), "Insumo/mercadoria", Decimal(rnd.randint(200, 2500)))]
            total = sum(v for *_, v in items)
            buyer = rnd.randint(1, 10)
            inv = Invoice(
                office_id=office.id, client_id=client.id, direction="emitida" if emitted else "recebida",
                chave=f"2326{month:02d}{CLIENT_CNPJ}55001{n:09d}1{n:08d}"[:44].ljust(44, "0"), modelo="55",
                numero=str(n), serie="1", data_emissao=d,
                emit_cnpj=CLIENT_CNPJ if emitted else "19131243000197",
                emit_nome=client.razao_social if emitted else "FORNECEDOR EXEMPLO SA",
                dest_documento=f"{buyer:014d}" if emitted else CLIENT_CNPJ,
                dest_nome=f"CLIENTE EXEMPLO {buyer}" if emitted else client.razao_social,
                valor_produtos=total, valor_total=total,
                valor_icms=(total * Decimal("0.18")).quantize(Decimal("0.01")) if emitted else 0,
                valor_pis=(total * Decimal("0.0065")).quantize(Decimal("0.01")) if emitted else 0,
                valor_cofins=(total * Decimal("0.03")).quantize(Decimal("0.01")) if emitted else 0,
            )
            for i, (cfop, desc, v) in enumerate(items, 1):
                item = InvoiceItem(n_item=i, descricao=desc, cfop=cfop,
                                   cfop_cliente=cfop_for_client(cfop, inv.direction), quantidade=1,
                                   valor_unitario=v, valor_total=v)
                _classify_item(db, item, accounts)
                inv.items.append(item)
            db.add(inv)
            n += 1

    # extrato bancário com classificação humana nos 3 primeiros meses
    ba = BankAccount(office_id=office.id, client_id=client.id, bank_name="Banco do Brasil", bank_code="001",
                     agencia="1234", conta="56789-0", source="ofx")
    db.add(ba)
    db.flush()
    recurring = [("PIX RECEBIDO CLIENTE", (5000, 12000), "1.01"), ("PAGTO ALUGUEL", (-3500, -3500), "4.02"),
                 ("FOLHA PAGAMENTO", (-6000, -5000), "4.01"), ("TARIFA PACOTE SERVICOS", (-60, -45), "4.06"),
                 ("PAGTO FORNECEDOR BOLETO", (-4000, -1000), "3.01"), ("DARF IRPJ CSLL", (-900, -600), "5.01"),
                 ("ENERGIA ELETRICA ENEL", (-700, -400), "4.02"), ("GOOGLE ADS MARKETING", (-800, -300), "4.05")]
    k = 0
    for month in range(1, 7):
        for desc, (lo, hi), code in recurring:
            for _ in range(3 if code == "1.01" else 1):
                k += 1
                d = date(2026, month, 1) + timedelta(days=rnd.randint(0, 26))
                text = f"{desc} {d:%d/%m} {rnd.randint(100000, 999999)}"
                tx = BankTransaction(office_id=office.id, client_id=client.id, bank_account_id=ba.id, fitid=f"D{k}",
                                     date=d, description=text, normalized_description=normalize_description(text),
                                     amount=Decimal(rnd.randint(lo, hi)))
                if month <= 3:
                    tx.account_id, tx.classified_by, tx.confidence = accounts[code].id, "cliente", 1.0
                db.add(tx)
    db.flush()
    classifier.classify_pending(db, client.id, office.id, use_llm=False)

    # aplicação financeira
    cdb = BankAccount(office_id=office.id, client_id=client.id, kind="aplicacao", bank_name="Banco do Brasil",
                      product_name="CDB DI")
    db.add(cdb)
    db.flush()
    saldo = Decimal("50000")
    for month in range(1, 7):
        rend = (saldo * Decimal("0.0095")).quantize(Decimal("0.01"))
        irrf = (rend * Decimal("0.2")).quantize(Decimal("0.01"))
        final = saldo + rend - irrf
        calc = investments.calcular_mes(saldo, Decimal(0), Decimal(0), final, irrf=irrf,
                                        benchmark_mes_pct=Decimal("0.95"))
        db.add(InvestmentStatement(office_id=office.id, client_id=client.id, bank_account_id=cdb.id,
                                   competencia=date(2026, month, 1), saldo_inicial=saldo, saldo_final=final,
                                   irrf=irrf, benchmark_mes_pct=Decimal("0.95"), **calc))
        saldo = final
    _seed_operations(db, office, client, ba, accounts, rnd)
    db.commit()
    print(f"Demo criada. Login: {EMAIL} / {PASSWORD}")



def _seed_operations(db, office, client, ba, accounts, rnd) -> None:
    """Contas a pagar/receber em várias situações, extrato para conciliar e uma segunda empresa."""
    today = date.today()
    specs = [  # (tipo, favorecido, doc, nº, dias p/ vencer, valor, conta)
        ("pagar", "ENEL DISTRIBUICAO CEARA", "07047251000170", "Conta 03/26", -4, "689.40", "4.02"),
        ("pagar", "IMOBILIARIA SOL NASCENTE", None, "ALUG-0326", -1, "3500.00", "4.02"),
        ("pagar", "FORNECEDOR EXEMPLO SA", "19131243000197", "NF 4581-1", 0, "2310.00", "3.01"),
        ("pagar", "GOOGLE BRASIL", None, "ADS-8812", 0, "540.00", "4.05"),
        ("pagar", "CONTABILIDADE DEMONSTRACAO", "11222333000181", "HON-0326", 3, "1500.00", "4.03"),
        ("pagar", "FORNECEDOR EXEMPLO SA", "19131243000197", "NF 4581-2", 15, "2310.00", "3.01"),
        ("receber", "CLIENTE EXEMPLO 2", "00000000000002", "NF 9001", -6, "4200.00", "1.01"),
        ("receber", "CLIENTE EXEMPLO 5", "00000000000005", "NF 9002", 0, "1850.00", "1.01"),
        ("receber", "CLIENTE EXEMPLO 8", "00000000000008", "NF 9003", 7, "6100.00", "1.01"),
    ]
    titles = []
    for kind, name, doc, num, days, value, code in specs:
        t = Title(office_id=office.id, client_id=client.id, kind=kind, counterparty_name=name, counterparty_doc=doc,
                  document_number=num, issue_date=today - timedelta(days=20), due_date=today + timedelta(days=days),
                  amount=Decimal(value), account_id=accounts[code].id)
        db.add(t)
        titles.append(t)
    db.flush()
    # extrato de hoje: casa com alguns títulos (um com juros, outro com desconto)
    for i, (desc, value) in enumerate([("PAGTO ENEL DISTRIBUICAO CEARA", "-702.19"),
                                       ("TED IMOBILIARIA SOL NASCENTE ALUG-0326", "-3500.00"),
                                       ("PIX RECEBIDO CLIENTE EXEMPLO 2", "4116.00")]):
        text = f"{desc} {today:%d/%m}"
        db.add(BankTransaction(office_id=office.id, client_id=client.id, bank_account_id=ba.id, fitid=f"OP{i}",
                               date=today, description=text, normalized_description=normalize_description(text),
                               amount=Decimal(value)))
    ba.connection_status, ba.last_sync_at = "ativo", utcnow()

    other = Client(office_id=office.id, cnpj="19131243000197", razao_social="PADARIA PÃO QUENTE LTDA",
                   nome_fantasia="Pão Quente", regime_tributario="simples", situacao_cadastral="ATIVA",
                   endereco={"municipio": "SOBRAL", "uf": "CE"})
    db.add(other)
    db.flush()
    db.add(BankAccount(office_id=office.id, client_id=other.id, bank_name="Itaú", agencia="0450", conta="12345-6",
                       source="open_finance", external_id="demo", connection_status="reautenticar",
                       last_sync_error="Consentimento expirado: o cliente precisa autorizar novamente no banco"))
    for name, days, value in [("MOINHO DOM BOSCO", -2, "5400.00"), ("FOLHA PAGAMENTO", 0, "8200.00")]:
        db.add(Title(office_id=office.id, client_id=other.id, kind="pagar", counterparty_name=name,
                     issue_date=today - timedelta(days=10), due_date=today + timedelta(days=days),
                     amount=Decimal(value), account_id=accounts["4.01" if "FOLHA" in name else "3.02"].id))


if __name__ == "__main__":
    main()
