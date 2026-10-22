"""Leitura de extratos bancários: OFX (1.x SGML e 2.x XML) e CSV.

Bancos brasileiros exportam OFX majoritariamente em SGML (sem tags de fechamento),
por isso o parser é tolerante e baseado em blocos <STMTTRN>.
"""

import csv
import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


class StatementParseError(Exception):
    pass


@dataclass
class ParsedTransaction:
    fitid: str
    date: date
    description: str
    amount: Decimal


@dataclass
class ParsedStatement:
    bank_code: str | None
    agencia: str | None
    conta: str | None
    transactions: list[ParsedTransaction]
    balance: Decimal | None = None


_NOISE = re.compile(r"\b\d{2}/\d{2}(/\d{2,4})?\b|\b\d{2}:\d{2}\b|\b\d{4,}\b|[^\w\s]")
_MONTHS = re.compile(
    r"\b(JAN(EIRO)?|FEV(EREIRO)?|MAR(CO)?|ABR(IL)?|MAI(O)?|JUN(HO)?|JUL(HO)?|AGO(STO)?|SET(EMBRO)?|"
    r"OUT(UBRO)?|NOV(EMBRO)?|DEZ(EMBRO)?)\b"
)


def normalize_description(text: str) -> str:
    """Remove acentos, datas, horas, números longos (documentos/autenticações) e pontuação."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().upper()
    text = _MONTHS.sub(" ", _NOISE.sub(" ", text))
    return re.sub(r"\s+", " ", text).strip()[:300]


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise StatementParseError("Codificação do arquivo não suportada")


def _tag(block: str, name: str) -> str | None:
    m = re.search(rf"<{name}>\s*([^<\r\n]*)", block, re.IGNORECASE)
    return m.group(1).strip() if m and m.group(1).strip() else None


def _amount(value: str) -> Decimal:
    v = value.strip().replace(" ", "")
    if "," in v and "." in v:  # 1.234,56
        v = v.replace(".", "").replace(",", ".")
    elif "," in v:
        v = v.replace(",", ".")
    try:
        return Decimal(v)
    except InvalidOperation as exc:
        raise StatementParseError(f"Valor inválido: {value}") from exc


def parse_ofx(raw: bytes) -> ParsedStatement:
    text = _decode(raw)
    if "<OFX>" not in text.upper():
        raise StatementParseError("Arquivo não é OFX")
    txs = []
    for block in re.findall(r"<STMTTRN>(.*?)(?=</STMTTRN>|<STMTTRN>|</BANKTRANLIST>)", text, re.S | re.I):
        dt, amt = _tag(block, "DTPOSTED"), _tag(block, "TRNAMT")
        if not dt or not amt:
            continue
        description = " ".join(x for x in [_tag(block, "NAME"), _tag(block, "MEMO")] if x) or "SEM HISTORICO"
        posted = datetime.strptime(dt[:8], "%Y%m%d").date()
        value = _amount(amt)
        fitid = _tag(block, "FITID") or hashlib.sha256(f"{posted}{value}{description}".encode()).hexdigest()[:32]
        txs.append(ParsedTransaction(fitid=fitid[:100], date=posted, description=description[:300], amount=value))
    if not txs:
        raise StatementParseError("Nenhuma transação encontrada no OFX")
    bal = _tag(text, "BALAMT")
    return ParsedStatement(
        bank_code=_tag(text, "BANKID"),
        agencia=_tag(text, "BRANCHID"),
        conta=_tag(text, "ACCTID"),
        transactions=txs,
        balance=_amount(bal) if bal else None,
    )


def parse_csv(raw: bytes) -> ParsedStatement:
    """CSV com cabeçalho contendo data, descrição/histórico e valor (ou débito/crédito)."""
    text = _decode(raw)
    dialect = csv.Sniffer().sniff(text[:2048], delimiters=";,\t")
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    cols = {normalize_description(c).lower(): c for c in reader.fieldnames or []}

    def col(*names):
        return next((cols[n] for n in names if n in cols), None)

    c_date = col("data", "date", "data lancamento", "data movimento")
    c_desc = col("descricao", "historico", "description", "lancamento")
    c_val = col("valor", "amount", "valor r")
    c_deb, c_cred = col("debito", "saida"), col("credito", "entrada")
    if not c_date or not c_desc or not (c_val or c_deb or c_cred):
        raise StatementParseError("CSV deve ter colunas data, descricao/historico e valor (ou debito/credito)")
    txs = []
    for i, row in enumerate(reader):
        raw_date = (row.get(c_date) or "").strip()
        if not raw_date:
            continue
        posted = None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
            try:
                posted = datetime.strptime(raw_date, fmt).date()
                break
            except ValueError:
                continue
        if posted is None:
            raise StatementParseError(f"Data inválida na linha {i + 2}: {raw_date}")
        if c_val:
            value = _amount(row[c_val])
        else:
            deb = _amount(row.get(c_deb) or "0") if c_deb else Decimal(0)
            cred = _amount(row.get(c_cred) or "0") if c_cred else Decimal(0)
            value = cred - abs(deb)
        desc = (row.get(c_desc) or "SEM HISTORICO").strip()[:300]
        fitid = hashlib.sha256(f"{i}|{posted}|{value}|{desc}".encode()).hexdigest()[:32]
        txs.append(ParsedTransaction(fitid=fitid, date=posted, description=desc, amount=value))
    if not txs:
        raise StatementParseError("Nenhuma transação encontrada no CSV")
    return ParsedStatement(bank_code=None, agencia=None, conta=None, transactions=txs)


def parse_statement(filename: str, raw: bytes) -> ParsedStatement:
    name = filename.lower()
    if name.endswith(".ofx") or b"<OFX>" in raw[:4096].upper():
        return parse_ofx(raw)
    if name.endswith((".csv", ".txt")):
        return parse_csv(raw)
    raise StatementParseError("Formato não suportado. Envie OFX ou CSV.")
