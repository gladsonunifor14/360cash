"""Cálculos de aplicações financeiras (extrato mensal).

Rendimento bruto do mês = saldo final − saldo inicial − aplicações + resgates + IRRF + IOF
                          + taxa de administração (quando debitados do saldo).
Rendimento líquido     = rendimento bruto − IRRF − IOF − taxa de administração.
Taxa do mês (Dietz simplificado) = rendimento / (saldo inicial + (aplicações − resgates) / 2).
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

Q2 = Decimal("0.01")
Q6 = Decimal("0.000001")

# Tabela regressiva de IR para renda fixa / fundos de longo prazo (Lei 11.033/2004)
IR_TABLE = [(180, Decimal("22.5")), (360, Decimal("20.0")), (720, Decimal("17.5"))]
IR_MIN = Decimal("15.0")


def aliquota_ir_regressiva(dias: int) -> Decimal:
    for limite, aliquota in IR_TABLE:
        if dias <= limite:
            return aliquota
    return IR_MIN


def iof_regressivo_pct(dias: int) -> Decimal:
    """IOF sobre rendimento para resgates em menos de 30 dias (Decreto 6.306/2007, anexo)."""
    if dias >= 30:
        return Decimal(0)
    # 96% no dia 1 decrescendo ~3,33 p.p./dia até 0% no dia 30
    tabela = [96, 93, 90, 86, 83, 80, 76, 73, 70, 66, 63, 60, 56, 53, 50, 46, 43, 40, 36, 33, 30, 26, 23, 20, 16,
              13, 10, 6, 3, 0]
    return Decimal(tabela[max(dias, 1) - 1])


def calcular_ir_resgate(valor_aplicado: Decimal, valor_resgate_bruto: Decimal, data_aplicacao: date,
                        data_resgate: date) -> dict:
    dias = (data_resgate - data_aplicacao).days
    rendimento = max(valor_resgate_bruto - valor_aplicado, Decimal(0))
    iof = (rendimento * iof_regressivo_pct(dias) / 100).quantize(Q2, ROUND_HALF_UP)
    aliquota = aliquota_ir_regressiva(dias)
    ir = ((rendimento - iof) * aliquota / 100).quantize(Q2, ROUND_HALF_UP)
    return {
        "dias": dias,
        "rendimento_bruto": rendimento,
        "iof": iof,
        "aliquota_ir_pct": aliquota,
        "irrf": ir,
        "valor_liquido": valor_resgate_bruto - iof - ir,
    }


def calcular_mes(
    saldo_inicial: Decimal,
    aplicacoes: Decimal,
    resgates: Decimal,
    saldo_final: Decimal,
    irrf: Decimal = Decimal(0),
    iof: Decimal = Decimal(0),
    taxa_administracao: Decimal = Decimal(0),
    benchmark_mes_pct: Decimal | None = None,
) -> dict:
    """Indicadores do mês. `resgates` é o valor líquido creditado; tributos e taxa são
    considerados como retirados do saldo da aplicação."""
    bruto = saldo_final - saldo_inicial - aplicacoes + resgates + irrf + iof + taxa_administracao
    liquido = bruto - irrf - iof - taxa_administracao
    base = saldo_inicial + (aplicacoes - resgates) / 2
    pct = (lambda v: (v / base * 100).quantize(Q6, ROUND_HALF_UP)) if base > 0 else (lambda v: Decimal(0))
    taxa_bruta = pct(bruto)
    taxa_liquida = pct(liquido)
    out = {
        "rendimento_bruto": bruto.quantize(Q2, ROUND_HALF_UP),
        "rendimento_liquido": liquido.quantize(Q2, ROUND_HALF_UP),
        "taxa_bruta_pct": taxa_bruta,
        "taxa_liquida_pct": taxa_liquida,
        "taxa_adm_pct": pct(taxa_administracao),
        "aliquota_ir_efetiva_pct": (irrf / bruto * 100).quantize(Q6, ROUND_HALF_UP) if bruto > 0 else Decimal(0),
        "pct_benchmark": None,
    }
    if benchmark_mes_pct:
        out["pct_benchmark"] = (taxa_bruta / benchmark_mes_pct * 100).quantize(Decimal("0.0001"), ROUND_HALF_UP)
    return out
