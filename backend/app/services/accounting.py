"""Plano de contas gerencial padrão e classificação contábil por CFOP."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CfopRule, ChartAccount

# (código, nome, natureza, grupo DRE, grupo fluxo de caixa)
DEFAULT_CHART: list[tuple[str, str, str, str | None, str]] = [
    ("1.01", "Receita de venda de mercadorias/produtos", "receita", "receita_bruta", "operacional"),
    ("1.02", "Receita de prestação de serviços", "receita", "receita_bruta", "operacional"),
    ("1.03", "Rendimentos de aplicações financeiras", "receita", "receitas_financeiras", "operacional"),
    ("1.04", "Outras receitas", "receita", "outras_receitas", "operacional"),
    ("2.01", "Devoluções e cancelamentos de vendas", "despesa", "deducoes", "operacional"),
    ("2.02", "Impostos sobre vendas (DAS, ICMS, ISS, PIS, COFINS)", "despesa", "deducoes", "operacional"),
    ("3.01", "Compras de mercadorias para revenda", "despesa", "custos", "operacional"),
    ("3.02", "Matéria-prima e insumos", "despesa", "custos", "operacional"),
    ("3.03", "Devoluções de compras", "receita", "custos", "operacional"),
    ("4.01", "Pessoal (salários, encargos, pró-labore, benefícios)", "despesa", "despesas_pessoal", "operacional"),
    ("4.02", "Ocupação (aluguel, condomínio, energia, água, telecom)", "despesa", "despesas_administrativas",
     "operacional"),
    ("4.03", "Serviços de terceiros (contabilidade, TI, jurídico)", "despesa", "despesas_administrativas",
     "operacional"),
    ("4.04", "Material de uso e consumo", "despesa", "despesas_administrativas", "operacional"),
    ("4.05", "Despesas comerciais (marketing, comissões, fretes)", "despesa", "despesas_comerciais", "operacional"),
    ("4.06", "Tarifas bancárias", "despesa", "despesas_financeiras", "operacional"),
    ("4.07", "Juros, multas e IOF", "despesa", "despesas_financeiras", "operacional"),
    ("4.08", "Impostos e taxas diversos (IPTU, IPVA, alvarás)", "despesa", "despesas_administrativas", "operacional"),
    ("5.01", "IRPJ e CSLL", "despesa", "impostos_lucro", "operacional"),
    ("6.01", "Aquisição de imobilizado", "despesa", None, "investimento"),
    ("6.02", "Venda de imobilizado", "receita", "outras_receitas", "investimento"),
    ("7.01", "Empréstimos e financiamentos captados", "neutro", None, "financiamento"),
    ("7.02", "Amortização de empréstimos", "neutro", None, "financiamento"),
    ("7.03", "Aporte de capital dos sócios", "neutro", None, "financiamento"),
    ("7.04", "Distribuição de lucros", "neutro", None, "financiamento"),
    ("8.01", "Transferência entre contas próprias", "neutro", None, "transferencia"),
    ("8.02", "Aplicações e resgates financeiros", "neutro", None, "transferencia"),
]

# Contas cuja competência vem das NF-e: no regime de competência, lançamentos bancários
# nelas são tratados como liquidação de nota (não entram de novo na DRE).
INVOICE_DRIVEN_CODES = {"1.01", "2.01", "3.01", "3.02", "3.03", "4.04", "6.01", "6.02"}

DRE_ORDER = [
    ("receita_bruta", "Receita bruta"),
    ("deducoes", "(-) Deduções da receita"),
    ("custos", "(-) Custos (CMV/CPV)"),
    ("despesas_pessoal", "(-) Despesas com pessoal"),
    ("despesas_administrativas", "(-) Despesas administrativas"),
    ("despesas_comerciais", "(-) Despesas comerciais"),
    ("receitas_financeiras", "(+) Receitas financeiras"),
    ("despesas_financeiras", "(-) Despesas financeiras"),
    ("outras_receitas", "(+/-) Outras receitas e despesas"),
    ("impostos_lucro", "(-) IRPJ e CSLL"),
]

_SALE = {"101", "102", "103", "104", "105", "106", "109", "110", "111", "112", "113", "114", "115",
         "116", "117", "118", "119", "120", "122", "123", "124", "125", "401", "402", "403", "405"}
_RETURN = {"201", "202", "203", "204", "208", "209", "410", "411", "412", "413", "503", "660", "661", "662"}
_TRANSFER = {"151", "152", "153", "155", "156", "408", "409", "552", "557", "658", "659"}


def classify_cfop(cfop: str) -> tuple[str, str | None, str]:
    """Regra padrão: retorna (operação, código da conta gerencial, descrição).

    Primeiro dígito: 1/2/3 = entrada (estadual/interestadual/exterior), 5/6/7 = saída.
    """
    if len(cfop) != 4 or not cfop.isdigit() or cfop[0] not in "123567":
        return "outros", None, "CFOP inválido ou não mapeado"
    entrada = cfop[0] in "123"
    tail = cfop[1:]
    if tail == "933":
        return ("servico_tomado", "4.03", "Serviço tomado (ISSQN)") if entrada else (
            "servico", "1.02", "Prestação de serviço (ISSQN)")
    if tail in _TRANSFER:
        return "transferencia", None, "Transferência entre estabelecimentos"
    if tail in _RETURN:
        return ("devolucao_venda", "2.01", "Devolução de venda") if entrada else (
            "devolucao_compra", "3.03", "Devolução de compra")
    if entrada:
        if tail in {"101", "111", "116", "401"}:
            return "compra", "3.02", "Compra para industrialização"
        if tail in {"102", "113", "117", "118", "121", "403"}:
            return "compra", "3.01", "Compra para comercialização"
        if tail in {"551", "406"}:
            return "ativo", "6.01", "Compra de ativo imobilizado"
        if tail in {"556", "407"}:
            return "uso_consumo", "4.04", "Compra de material de uso e consumo"
        if tail[:2] == "25":
            return "despesa", "4.02", "Aquisição de energia elétrica"
        if tail[:2] in {"30"}:
            return "despesa", "4.02", "Aquisição de serviço de comunicação"
        if tail[:2] in {"35"}:
            return "despesa", "4.05", "Aquisição de serviço de transporte (frete)"
    else:
        if tail == "556":
            return "devolucao_compra", "4.04", "Devolução de compra de material de uso e consumo"
        if tail in _SALE:
            return "venda", "1.01", "Venda de produção/mercadoria"
        if tail == "551":
            return "ativo", "6.02", "Venda de ativo imobilizado"
        if tail[:2] == "35":
            return "servico", "1.02", "Prestação de serviço de transporte"
    if tail[0] == "9":
        return "remessa", None, "Remessa/retorno (sem efeito no resultado)"
    return "outros", None, "Outras operações"


def seed_chart(db: Session, office_id: str) -> None:
    existing = set(db.scalars(select(ChartAccount.code).where(ChartAccount.office_id == office_id)))
    for code, name, nature, dre, cash in DEFAULT_CHART:
        if code not in existing:
            db.add(ChartAccount(office_id=office_id, code=code, name=name, nature=nature,
                                dre_group=dre, cash_flow_group=cash))


def seed_cfop_rules(db: Session) -> None:
    if db.scalar(select(CfopRule.cfop).limit(1)):
        return
    for first in "123567":
        for tail in sorted(_SALE | _RETURN | _TRANSFER | {"551", "556", "407", "406", "933", "252", "253",
                                                          "302", "303", "352", "353", "901", "902", "910",
                                                          "915", "916", "949"}):
            cfop = first + tail
            operation, account, desc = classify_cfop(cfop)
            db.add(CfopRule(cfop=cfop, description=desc, operation=operation, account_code=account))


def resolve_cfop(db: Session, cfop: str) -> tuple[str, str | None]:
    rule = db.get(CfopRule, cfop)
    if rule:
        return rule.operation, rule.account_code
    operation, account, _ = classify_cfop(cfop)
    return operation, account


def account_by_code(db: Session, office_id: str) -> dict[str, ChartAccount]:
    return {a.code: a for a in db.scalars(select(ChartAccount).where(ChartAccount.office_id == office_id))}
