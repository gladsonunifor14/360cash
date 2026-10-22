"""Relatórios: Fluxo de Caixa, DRE e Relatórios Gerenciais.

Todo relatório carrega o cabeçalho com o escritório elaborador (razão social, CNPJ, CRC
e responsável técnico) e a empresa cliente.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.models import (
    ChartAccount,
    Client,
    InvestmentStatement,
    Invoice,
    InvoiceItem,
    Office,
)
from app.services.accounting import DRE_ORDER, INVOICE_DRIVEN_CODES
from app.services.cnpj import format_cnpj
from app.services.reconciliation import split_rows

REGIME_LABEL = {"competencia": "competência", "caixa": "caixa"}
REVENUE_GROUPS = {"receita_bruta", "receitas_financeiras", "outras_receitas"}
ZERO = Decimal("0.00")


def _month(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _months(start: date, end: date) -> list[str]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def header(db: Session, client: Client, title: str, start: date, end: date) -> dict:
    office = db.get(Office, client.office_id)
    return {
        "titulo": title,
        "periodo": {"inicio": start.isoformat(), "fim": end.isoformat()},
        "empresa": {"razao_social": client.razao_social, "cnpj": format_cnpj(client.cnpj)},
        "elaborado_por": {
            "razao_social": office.razao_social,
            "nome_fantasia": office.nome_fantasia,
            "cnpj": format_cnpj(office.cnpj),
            "crc": office.crc,
            "responsavel_tecnico": office.responsavel_tecnico,
        },
        "gerado_em": utcnow().isoformat(timespec="seconds") + "Z",
    }


def _accounts(db: Session, office_id: str) -> dict[str, ChartAccount]:
    return {a.id: a for a in db.scalars(select(ChartAccount).where(ChartAccount.office_id == office_id))}


def _bank_rows(db: Session, client_id: str, start: date, end: date):
    """(data, valor, conta) do caixa; lançamentos conciliados entram pelo rateio (principal, juros, desconto)."""
    return split_rows(db, client_id, start, end)


# --------------------------------------------------------------------------- fluxo de caixa


def cash_flow(db: Session, client: Client, start: date, end: date) -> dict:
    accounts = _accounts(db, client.office_id)
    months = _months(start, end)
    lines: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    entradas = defaultdict(lambda: ZERO)
    saidas = defaultdict(lambda: ZERO)
    transfer = defaultdict(lambda: ZERO)
    for d, amount, account_id in _bank_rows(db, client.id, start, end):
        m = _month(d)
        acc = accounts.get(account_id)
        group = acc.cash_flow_group if acc else "nao_classificado"
        name = f"{acc.code} {acc.name}" if acc else "Não classificado"
        lines[(group, name)][m] += amount
        if group == "transferencia":
            transfer[m] += amount
            continue
        if amount >= 0:
            entradas[m] += amount
        else:
            saidas[m] += amount

    groups_order = ["operacional", "investimento", "financiamento", "nao_classificado", "transferencia"]
    group_names = {
        "operacional": "Atividades operacionais",
        "investimento": "Atividades de investimento",
        "financiamento": "Atividades de financiamento",
        "nao_classificado": "Não classificado",
        "transferencia": "Transferências entre contas (não afetam o caixa consolidado)",
    }
    grupos = []
    for g in groups_order:
        items = [
            {"conta": name, "valores": {m: vals[m] for m in months}, "total": sum(vals.values(), ZERO)}
            for (grp, name), vals in sorted(lines.items())
            if grp == g
        ]
        if items:
            totals = {m: sum((i["valores"][m] for i in items), ZERO) for m in months}
            grupos.append({"grupo": g, "nome": group_names[g], "contas": items, "valores": totals,
                           "total": sum(totals.values(), ZERO)})

    acumulado, saldo = {}, ZERO
    for m in months:
        saldo += entradas[m] + saidas[m]
        acumulado[m] = saldo
    return {
        "cabecalho": header(db, client, "Demonstrativo de Fluxo de Caixa", start, end),
        "meses": months,
        "grupos": grupos,
        "entradas": {m: entradas[m] for m in months},
        "saidas": {m: saidas[m] for m in months},
        "geracao_caixa": {m: entradas[m] + saidas[m] for m in months},
        "geracao_acumulada": acumulado,
        "total_entradas": sum(entradas.values(), ZERO),
        "total_saidas": sum(saidas.values(), ZERO),
    }


# --------------------------------------------------------------------------- DRE


def dre(db: Session, client: Client, start: date, end: date, regime: str = "competencia") -> dict:
    """DRE gerencial mensal.

    - caixa: somente lançamentos bancários classificados.
    - competencia: receitas, devoluções, compras e custos vêm das NF-e (por CFOP); demais
      grupos vêm dos extratos. Lançamentos bancários em contas originadas por NF-e são
      tratados como liquidação e não entram de novo. Tributos destacados nas notas emitidas
      (ICMS, PIS, COFINS) são deduções para empresas fora do Simples Nacional.
    """
    accounts = _accounts(db, client.office_id)
    months = _months(start, end)
    values: dict[str, dict[str, dict[str, Decimal]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: ZERO)))
    simples = client.regime_tributario in ("simples", "mei")

    def add(group: str, account_name: str, month: str, value: Decimal):
        values[group][account_name][month] += value

    for d, amount, account_id in _bank_rows(db, client.id, start, end):
        acc = accounts.get(account_id)
        if not acc or not acc.dre_group:
            continue
        if regime == "competencia" and (acc.code in INVOICE_DRIVEN_CODES or (acc.code == "2.02" and not simples)):
            continue
        sign = 1 if acc.dre_group in REVENUE_GROUPS else -1
        add(acc.dre_group, f"{acc.code} {acc.name}", _month(d), amount * sign)

    if regime == "competencia":
        rows = db.execute(
            select(Invoice.data_emissao, InvoiceItem.valor_total, InvoiceItem.account_id, InvoiceItem.operation)
            .join(InvoiceItem, InvoiceItem.invoice_id == Invoice.id)
            .where(
                Invoice.client_id == client.id,
                Invoice.cancelled.is_(False),
                Invoice.data_emissao >= start,
                Invoice.data_emissao <= end,
            )
        ).all()
        for d, valor, account_id, operation in rows:
            acc = accounts.get(account_id)
            if not acc or not acc.dre_group:
                continue
            # devolução de compra reduz o custo/despesa; demais seguem a natureza da conta no grupo
            same_direction = (acc.nature == "receita") == (acc.dre_group in REVENUE_GROUPS)
            if operation == "devolucao_compra":
                same_direction = False
            add(acc.dre_group, f"{acc.code} {acc.name}", _month(d), valor if same_direction else -valor)
        if not simples:
            taxes = db.execute(
                select(Invoice.data_emissao, Invoice.valor_icms + Invoice.valor_pis + Invoice.valor_cofins).where(
                    Invoice.client_id == client.id,
                    Invoice.direction == "emitida",
                    Invoice.cancelled.is_(False),
                    Invoice.data_emissao >= start,
                    Invoice.data_emissao <= end,
                )
            ).all()
            for d, t in taxes:
                if t:
                    add("deducoes", "Tributos destacados nas NF-e (ICMS/PIS/COFINS)", _month(d), t)

    def group_total(g: str) -> dict[str, Decimal]:
        return {m: sum((v[m] for v in values[g].values()), ZERO) for m in months}

    totals = {g: group_total(g) for g, _ in DRE_ORDER}

    def combine(*parts: tuple[int, str]) -> dict[str, Decimal]:
        return {m: sum((s * totals[g][m] for s, g in parts), ZERO) for m in months}

    receita_liquida = combine((1, "receita_bruta"), (-1, "deducoes"))
    lucro_bruto = {m: receita_liquida[m] - totals["custos"][m] for m in months}
    resultado_operacional = {
        m: lucro_bruto[m] - totals["despesas_pessoal"][m] - totals["despesas_administrativas"][m]
        - totals["despesas_comerciais"][m]
        for m in months
    }
    antes_ir = {
        m: resultado_operacional[m] + totals["receitas_financeiras"][m] - totals["despesas_financeiras"][m]
        + totals["outras_receitas"][m]
        for m in months
    }
    lucro_liquido = {m: antes_ir[m] - totals["impostos_lucro"][m] for m in months}

    def line(key, label, vals, kind="grupo", contas=None):
        return {"chave": key, "descricao": label, "tipo": kind, "valores": vals,
                "total": sum(vals.values(), ZERO), "contas": contas or []}

    def contas(g):
        return [{"conta": name, "valores": {m: v[m] for m in months}, "total": sum(v.values(), ZERO)}
                for name, v in sorted(values[g].items())]

    labels = dict(DRE_ORDER)
    linhas = [
        line("receita_bruta", labels["receita_bruta"], totals["receita_bruta"], contas=contas("receita_bruta")),
        line("deducoes", labels["deducoes"], totals["deducoes"], contas=contas("deducoes")),
        line("receita_liquida", "= Receita líquida", receita_liquida, "subtotal"),
        line("custos", labels["custos"], totals["custos"], contas=contas("custos")),
        line("lucro_bruto", "= Lucro bruto", lucro_bruto, "subtotal"),
    ]
    for g in ("despesas_pessoal", "despesas_administrativas", "despesas_comerciais"):
        linhas.append(line(g, labels[g], totals[g], contas=contas(g)))
    linhas.append(line("resultado_operacional", "= Resultado operacional", resultado_operacional, "subtotal"))
    for g in ("receitas_financeiras", "despesas_financeiras", "outras_receitas"):
        linhas.append(line(g, labels[g], totals[g], contas=contas(g)))
    linhas.append(line("resultado_antes_ir", "= Resultado antes do IRPJ/CSLL", antes_ir, "subtotal"))
    linhas.append(line("impostos_lucro", labels["impostos_lucro"], totals["impostos_lucro"],
                       contas=contas("impostos_lucro")))
    linhas.append(line("lucro_liquido", "= Lucro líquido", lucro_liquido, "resultado"))

    rb = sum(totals["receita_bruta"].values(), ZERO)

    def margin(vals):
        return (sum(vals.values(), ZERO) / rb * 100).quantize(Decimal("0.01")) if rb else None

    return {
        "cabecalho": header(db, client, f"DRE Gerencial (regime de {REGIME_LABEL[regime]})", start, end),
        "regime": regime,
        "meses": months,
        "linhas": linhas,
        "margens": {"bruta_pct": margin(lucro_bruto), "operacional_pct": margin(resultado_operacional),
                    "liquida_pct": margin(lucro_liquido)},
    }


# --------------------------------------------------------------------------- gerenciais


def management(db: Session, client: Client, start: date, end: date) -> dict:
    accounts = _accounts(db, client.office_id)
    base_inv = (Invoice.client_id == client.id, Invoice.cancelled.is_(False),
                Invoice.data_emissao >= start, Invoice.data_emissao <= end)

    def top_partners(direction: str, doc_col, name_col):
        rows = db.execute(
            select(doc_col, name_col, func.sum(Invoice.valor_total), func.count())
            .where(*base_inv, Invoice.direction == direction)
            .group_by(doc_col, name_col)
            .order_by(func.sum(Invoice.valor_total).desc())
            .limit(10)
        ).all()
        return [{"documento": d, "nome": n, "valor": v, "notas": c} for d, n, v, c in rows]

    faturamento, qtd_notas = db.execute(
        select(func.coalesce(func.sum(Invoice.valor_total), 0), func.count()).where(
            *base_inv, Invoice.direction == "emitida")
    ).one()
    compras = db.scalar(
        select(func.coalesce(func.sum(Invoice.valor_total), 0)).where(*base_inv, Invoice.direction == "recebida"))

    despesas = defaultdict(lambda: ZERO)
    pendentes, valor_pendente = 0, ZERO
    for _, amount, account_id in _bank_rows(db, client.id, start, end):
        acc = accounts.get(account_id)
        if not acc:
            pendentes += 1
            valor_pendente += abs(amount)
        elif amount < 0 and acc.nature == "despesa":
            despesas[f"{acc.code} {acc.name}"] += -amount
    top_despesas = sorted(({"conta": k, "valor": v} for k, v in despesas.items()), key=lambda x: -x["valor"])[:10]

    inv = db.execute(
        select(func.coalesce(func.sum(InvestmentStatement.rendimento_bruto), 0),
               func.coalesce(func.sum(InvestmentStatement.rendimento_liquido), 0),
               func.coalesce(func.sum(InvestmentStatement.irrf), 0),
               func.coalesce(func.sum(InvestmentStatement.taxa_administracao), 0))
        .where(InvestmentStatement.client_id == client.id,
               InvestmentStatement.competencia >= start.replace(day=1),
               InvestmentStatement.competencia <= end)
    ).one()

    d = dre(db, client, start, end, "competencia")
    lucro = next(line_["total"] for line_ in d["linhas"] if line_["chave"] == "lucro_liquido")
    fc = cash_flow(db, client, start, end)
    return {
        "cabecalho": header(db, client, "Relatório Gerencial", start, end),
        "indicadores": {
            "faturamento": Decimal(faturamento),
            "notas_emitidas": qtd_notas,
            "ticket_medio": (Decimal(faturamento) / qtd_notas).quantize(Decimal("0.01")) if qtd_notas else ZERO,
            "compras": Decimal(compras),
            "lucro_liquido": lucro,
            **{f"margem_{k}": v for k, v in d["margens"].items()},
            "geracao_caixa": fc["total_entradas"] + fc["total_saidas"],
            "lancamentos_pendentes": pendentes,
            "valor_pendente_classificacao": valor_pendente,
            "rendimento_aplicacoes_bruto": Decimal(inv[0]),
            "rendimento_aplicacoes_liquido": Decimal(inv[1]),
            "irrf_aplicacoes": Decimal(inv[2]),
            "taxa_adm_aplicacoes": Decimal(inv[3]),
        },
        "top_clientes": top_partners("emitida", Invoice.dest_documento, Invoice.dest_nome),
        "top_fornecedores": top_partners("recebida", Invoice.emit_cnpj, Invoice.emit_nome),
        "top_despesas": top_despesas,
        "receita_mensal": next(line_["valores"] for line_ in d["linhas"] if line_["chave"] == "receita_bruta"),
        "lucro_mensal": next(line_["valores"] for line_ in d["linhas"] if line_["chave"] == "lucro_liquido"),
        "caixa_mensal": fc["geracao_caixa"],
    }
