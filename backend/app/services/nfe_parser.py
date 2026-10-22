"""Leitura de XML de NF-e (modelo 55) e NFC-e (modelo 65), incluindo eventos de cancelamento.

Usa `defusedxml` para bloquear XXE, billion laughs e entidades externas.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from defusedxml import ElementTree as ET

NS = {"n": "http://www.portalfiscal.inf.br/nfe"}


class NfeParseError(Exception):
    pass


@dataclass
class NfeItem:
    n_item: int
    codigo: str | None
    descricao: str
    ncm: str | None
    cfop: str
    quantidade: Decimal
    valor_unitario: Decimal
    valor_total: Decimal


@dataclass
class NfeDuplicata:
    numero: str | None
    vencimento: date
    valor: Decimal


@dataclass
class NfeData:
    chave: str
    modelo: str | None
    numero: str | None
    serie: str | None
    natureza_operacao: str | None
    tipo_nf: str | None  # 0 entrada / 1 saída (visão do emitente)
    data_emissao: date
    emit_cnpj: str | None
    emit_nome: str | None
    dest_documento: str | None
    dest_nome: str | None
    totais: dict[str, Decimal]
    items: list[NfeItem] = field(default_factory=list)
    duplicatas: list[NfeDuplicata] = field(default_factory=list)


@dataclass
class NfeCancelEvent:
    chave: str


def _text(el, path: str) -> str | None:
    found = el.find(path, NS) if el is not None else None
    return found.text.strip() if found is not None and found.text else None


def _dec(value: str | None) -> Decimal:
    try:
        return Decimal(value) if value else Decimal("0")
    except InvalidOperation:
        return Decimal("0")


def _parse_date(value: str | None) -> date:
    if not value:
        raise NfeParseError("Data de emissão ausente")
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()


def parse(xml_bytes: bytes) -> NfeData | NfeCancelEvent:
    try:
        root = ET.fromstring(xml_bytes, forbid_dtd=True)
    except Exception as exc:  # defusedxml lança tipos variados
        raise NfeParseError(f"XML inválido: {exc.__class__.__name__}") from exc

    # Evento de cancelamento (procEventoNFe / evento, tpEvento 110111)
    ev = root.find(".//n:infEvento", NS)
    if ev is not None and root.find(".//n:infNFe", NS) is None:
        if _text(ev, "n:tpEvento") == "110111":
            chave = _text(ev, "n:chNFe")
            if chave:
                return NfeCancelEvent(chave=chave)
        raise NfeParseError("Evento de NF-e não suportado (apenas cancelamento 110111)")

    inf = root.find(".//n:infNFe", NS)
    if inf is None:
        raise NfeParseError("Arquivo não é uma NF-e (infNFe não encontrado)")

    chave = (inf.get("Id") or "").removeprefix("NFe") or _text(root, ".//n:protNFe/n:infProt/n:chNFe")
    if not chave or len(chave) != 44 or not chave.isdigit():
        raise NfeParseError("Chave de acesso inválida")

    ide = inf.find("n:ide", NS)
    emit = inf.find("n:emit", NS)
    dest = inf.find("n:dest", NS)
    tot = inf.find("n:total/n:ICMSTot", NS)

    items = []
    for det in inf.findall("n:det", NS):
        prod = det.find("n:prod", NS)
        cfop = _text(prod, "n:CFOP")
        if not cfop:
            raise NfeParseError(f"Item {det.get('nItem')} sem CFOP")
        items.append(
            NfeItem(
                n_item=int(det.get("nItem") or len(items) + 1),
                codigo=_text(prod, "n:cProd"),
                descricao=(_text(prod, "n:xProd") or "")[:300],
                ncm=_text(prod, "n:NCM"),
                cfop=cfop,
                quantidade=_dec(_text(prod, "n:qCom")),
                valor_unitario=_dec(_text(prod, "n:vUnCom")),
                valor_total=_dec(_text(prod, "n:vProd")),
            )
        )
    if not items:
        raise NfeParseError("NF-e sem itens")

    totais = {
        k: _dec(_text(tot, f"n:{tag}"))
        for k, tag in {
            "valor_produtos": "vProd",
            "valor_desconto": "vDesc",
            "valor_frete": "vFrete",
            "valor_icms": "vICMS",
            "valor_icms_st": "vST",
            "valor_ipi": "vIPI",
            "valor_pis": "vPIS",
            "valor_cofins": "vCOFINS",
            "valor_total": "vNF",
        }.items()
    }

    duplicatas = []
    for dup in inf.findall("n:cobr/n:dup", NS):
        venc = _text(dup, "n:dVenc")
        if venc:
            duplicatas.append(NfeDuplicata(numero=_text(dup, "n:nDup"), vencimento=_parse_date(venc),
                                           valor=_dec(_text(dup, "n:vDup"))))

    return NfeData(
        duplicatas=duplicatas,
        chave=chave,
        modelo=_text(ide, "n:mod"),
        numero=_text(ide, "n:nNF"),
        serie=_text(ide, "n:serie"),
        natureza_operacao=_text(ide, "n:natOp"),
        tipo_nf=_text(ide, "n:tpNF"),
        data_emissao=_parse_date(_text(ide, "n:dhEmi") or _text(ide, "n:dEmi")),
        emit_cnpj=_text(emit, "n:CNPJ") or _text(emit, "n:CPF"),
        emit_nome=_text(emit, "n:xNome"),
        dest_documento=_text(dest, "n:CNPJ") or _text(dest, "n:CPF"),
        dest_nome=_text(dest, "n:xNome"),
        totais=totais,
        items=items,
    )
