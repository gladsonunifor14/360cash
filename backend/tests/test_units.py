from decimal import Decimal

from app.services.accounting import classify_cfop
from app.services.bank_parser import normalize_description, parse_csv
from app.services.cnpj import format_cnpj, is_valid_cnpj, normalize
from app.services.investments import aliquota_ir_regressiva


def test_cnpj_validation():
    assert is_valid_cnpj("11.222.333/0001-81")
    assert not is_valid_cnpj("11.222.333/0001-82")
    assert not is_valid_cnpj("00000000000000")
    assert format_cnpj("11222333000181") == "11.222.333/0001-81"


def test_receitaws_normalization():
    data = normalize({"nome": "EMPRESA X", "cnpj": "11.222.333/0001-81", "situacao": "ATIVA",
                      "atividade_principal": [{"code": "69.20-6-01", "text": "Contabilidade"}],
                      "abertura": "10/03/2015", "cep": "60.000-000", "simples": {"optante": True}})
    assert data["razao_social"] == "EMPRESA X"
    assert data["data_abertura"].year == 2015
    assert data["regime_tributario"] == "simples"
    assert data["endereco"]["cep"] == "60000000"


def test_cfop_rules():
    assert classify_cfop("5102")[:2] == ("venda", "1.01")
    assert classify_cfop("6102")[:2] == ("venda", "1.01")
    assert classify_cfop("1102")[:2] == ("compra", "3.01")
    assert classify_cfop("2101")[:2] == ("compra", "3.02")
    assert classify_cfop("1202")[:2] == ("devolucao_venda", "2.01")
    assert classify_cfop("5202")[:2] == ("devolucao_compra", "3.03")
    assert classify_cfop("1556")[:2] == ("uso_consumo", "4.04")
    assert classify_cfop("1551")[:2] == ("ativo", "6.01")
    assert classify_cfop("5933")[:2] == ("servico", "1.02")
    assert classify_cfop("5152")[:2] == ("transferencia", None)
    assert classify_cfop("5949")[:2] == ("remessa", None)
    assert classify_cfop("9999")[0] == "outros"


def test_normalize_description():
    assert normalize_description("Pix Recebido - João 16/03 10:22 Doc 123456") == "PIX RECEBIDO JOAO DOC"
    assert normalize_description("PAGTO ALUGUEL MARÇO") == "PAGTO ALUGUEL"


def test_csv_debit_credit_columns():
    csv = "Data;Histórico;Débito;Crédito\n01/03/2026;Tarifa;12,90;\n02/03/2026;Depósito;;1.500,00\n".encode("cp1252")
    st = parse_csv(csv)
    assert [t.amount for t in st.transactions] == [Decimal("-12.90"), Decimal("1500.00")]


def test_ir_table():
    assert aliquota_ir_regressiva(100) == Decimal("22.5")
    assert aliquota_ir_regressiva(181) == Decimal("20.0")
    assert aliquota_ir_regressiva(500) == Decimal("17.5")
    assert aliquota_ir_regressiva(721) == Decimal("15.0")
