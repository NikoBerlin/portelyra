"""Erzeuger erfundener Trade-Republic-Belege fuer den Selbsttest (statement_reader_v1, Stufe 4, rc.379).

Wie die Referenz (c24): Aus einem Startwert entstehen erfundene Vorgaenge; aus ihnen baut der Erzeuger den Beleg im Format von
Trade Republic und - unabhaengig vom Leser - das erwartete Ergebnis. Der Erzeuger ruft den Leser nie auf, sonst bestaetigte der Leser
nur sich selbst. Gleicher Startwert, gleicher Beleg. Alle Werte sind erfunden: Namen, ISIN, Transaktionskennungen, Betraege,
Zeitpunkte (2021-2024, damit "kein Buchungstag nach heute" auch mit dem Datum des Rechners gilt).

Die Kennung trade_republic_v1 gibt es als Cash- und als Wertpapier-Leser; die Erzeuger stehen deshalb je (Bereich, Kennung).

- cash/trade_republic_v1: Kontoauszug ueber die ganze Historie als PDF-Text (.txt). Tag, Monat und Jahr auf eigenen Zeilen in beiden
  Anordnungen (Tag und Monat zusammen, oder der Tag allein ueber dem Verwendungszweck), Vorzeichen nur aus dem laufenden Saldo,
  negativer Saldo, Betrag in der Beschreibung ("ATM fee: 1,00 €"), Zinsen, Seitenwechsel, Tabellen hinter der Umsatzuebersicht
  (nicht gelesen), ein verdruckter Saldo (die Zeile und die naechste werden gemeldet) und eine Zeile, deren Jahr hinter einem
  Seitenwechsel verloren geht (gemeldet).
- cash/trade_republic_transactions_v1: CSV-Export mit amount brutto, fee und tax getrennt: Ein- und Auszahlungen, Kauf und Verkauf
  mit Gebuehr und Steuer, Dividende, Zinsen mit und ohne Steuer, ganz von der Steuer aufgezehrte Zinsen (gemeldet),
  Steueroptimierung, Einbuchung ohne Geldbewegung (uebergangen), Fremdwaehrung, unlesbarer Tag, unlesbarer Betrag, Leerzeile.
- securities/trade_republic_v1: CSV-Export "Transaktionen": Kaeufe und Verkaeufe (Teilausfuehrung aus ganzen Stuecken und Bruchteil
  in derselben Sekunde, Sparplan, Zeiten in UTC ueber Sommer-/Winterzeit und Mitternacht), Dividende (mit Rueckbuchung, auch ohne
  Gegenstueck), Vorabpauschale (EARNINGS), und Zeilen mit Grund (Steueroptimierung, Zeichnung, Zuteilung ohne Betrag, Fremdwaehrung,
  Kontobewegung, Einbuchung, unbekannt, unlesbarer Zeitpunkt, unvollstaendig).
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
import io
import random
from typing import Any
from zoneinfo import ZoneInfo

CENT = Decimal("0.01")
BERLIN = ZoneInfo("Europe/Berlin")


def _plain(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _german(value: Decimal) -> str:
    """1234.5 -> "1.234,50", negativ mit Minus vorn - wie der Kontoauszug."""
    sign = "-" if value < 0 else ""
    whole, _, fraction = f"{abs(value):.2f}".partition(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:]); whole = whole[:-3]
    groups.insert(0, whole)
    return f"{sign}{'.'.join(groups)},{fraction}"


def _money(rng: random.Random, low: int, high: int) -> Decimal:
    """Betrag in Cent zwischen low und high (beide in Cent)."""
    return Decimal(rng.randrange(low, high)) / 100


def _isin(rng: random.Random) -> str:
    return f"{rng.choice(('US', 'DE', 'IE', 'LU', 'FR', 'NL'))}0000{rng.randrange(10**5):05d}{rng.randrange(10)}"


# ---------------------------------------------------------------- cash/trade_republic_v1: Kontoauszug
MONTHS = ("Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sept.", "Okt.", "Nov.", "Dez.")
# (Typ, Beschreibung, Richtung, Spanne in Cent, Gebuehr in der Beschreibung). Weder Typ noch das erste Wort der Beschreibung beginnt
# wie ein Monat, und keine Beschreibung beginnt mit einer Zahl: Beides laese der Auszug als Datum.
STATEMENT_ROWS = (
    ("Überweisung", "Einzahlung akzeptiert", 1, (1_000, 500_000), False),
    ("Überweisung", "Outgoing transfer for Erika Erfunden", -1, (1_000, 200_000), False),
    ("Handel", "Buy trade {isin} ERFUNDENE AG, quantity: {quantity}", -1, (500, 200_000), False),
    ("Handel", "Sell trade {isin} INVENTED CORP, quantity: {quantity}", 1, (500, 200_000), False),
    ("Handel", "Savings plan execution {isin} ERFUNDENER WELT ETF, quantity: {quantity}", -1, (2_500, 50_000), False),
    ("Kartentransaktion", "Erfundener Laden", -1, (100, 20_000), False),
    ("Kartentransaktion", "*Erfundene Bank, ATM fee:", -1, (2_000, 40_000), True),
    ("Erträge", "Cash Dividend for ISIN {isin}", 1, (10, 10_000), False),
    ("Prämie", "Your Saveback payment", 1, (10, 1_500), False),
)
PAGE_BREAK = ["", "TRADE REPUBLIC BANK GMBH", "Seite {page} von {pages}", "", "DATUM TYP BESCHREIBUNG ZAHLUNGSEINGANG ZAHLUNGSAUSGANG SALDO", ""]
TRAILERS = (
    [],
    ["GELDMARKTFONDS ISIN STK. / NOMINALE KURS PRO STÜCK KURSWERT IN EUR", "Erfundener Euro Geldmarkt IE0000000000 12,00 1,00 € 12,00 €",
     "TRANSAKTIONSÜBERSICHT", "07 Aug. 2024 Kauf 132,40 1,00 € 132,40 €"],
    ["TREUHANDKONTEN", "Erfundene Partnerbank 1.234,56 € 1.234,56 €"],
    ["DEPOTÜBERSICHT", "Erfundene AG US0000000001 3,00 120,00 € 360,00 €"],
)


def _statement_rows(rng: random.Random, opening: Decimal) -> list[dict[str, Any]]:
    day = date(2021, 1, 1) + timedelta(days=rng.randrange(0, 365 * 3))
    balance = opening
    rows: list[dict[str, Any]] = []
    for _ in range(rng.randrange(4, 30)):
        previous = day
        day += timedelta(days=rng.randrange(0, 21))
        if day.month != previous.month and rng.random() < 0.7:   # Zinsen am Monatsersten
            interest_day = day.replace(day=1)
            amount = _money(rng, 1, 3_000)
            balance += amount
            rows.append({"day": interest_day, "kind": "Zinsen", "description": "Your interest payment", "sign": 1, "amount": amount,
                         "fee": None, "balance": balance})
        kind, description, sign, (low, high), with_fee = rng.choice(STATEMENT_ROWS)
        amount = _money(rng, low, high)
        if sign < 0 and amount > balance + 50 and rng.random() < 0.8:   # kaum ueberzogen: dann erst eine Einzahlung
            kind, description, sign, with_fee = "Überweisung", "Einzahlung akzeptiert", 1, False
        description = description.replace("{isin}", _isin(rng)).replace("{quantity}", str(rng.choice((rng.randrange(1, 40), Decimal(rng.randrange(1, 9999)) / 1000))))
        balance += amount * sign
        rows.append({"day": day, "kind": kind, "description": description, "sign": sign, "amount": amount,
                     "fee": _money(rng, 100, 500) if with_fee else None, "balance": balance})
    return rows


def _simulate(rows: list[dict[str, Any]], opening: Decimal) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Erwartung aus der Saldokette des Auszugs: Eine Zeile gilt, wenn ihr Saldo um ihren Betrag vom vorigen gedruckten Saldo abweicht;
    auch eine unstimmige Zeile setzt den Saldo neu, eine Zeile ohne Jahr nicht. Liefert zusaetzlich, ob jede geltende Zeile die
    erfundene Richtung traegt (sonst waehlt der Erzeuger keinen Sonderfall)."""
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    running = opening
    faithful = True
    for ordinal, row in enumerate(rows, 1):
        if row.get("year_lost"):
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "row_unreadable"}); continue
        printed = row["printed"]
        matches = abs(printed - running) == row["amount"]
        sign = 1 if printed >= running else -1
        running = printed
        if not matches:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "balance_step_mismatch"}); continue
        faithful &= sign == row["sign"]
        text = row["kind"] if row["wrapped"] else " ".join(part for part in (row["kind"], row["description"]) if part)
        kind = "interest" if row["sign"] > 0 and row["kind"] == "Zinsen" else ("deposit" if row["sign"] > 0 else "withdrawal")
        candidates.append({"source_row_ordinal": ordinal, "local_date": row["day"].isoformat(), "kind": kind, "amount_decimal": _plain(row["amount"]),
                           "balance_after_decimal": _plain(printed), "text": text})
    return candidates, diagnostics, faithful


def _statement(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    opening = Decimal(0) if rng.random() < 0.4 else _money(rng, 1, 500_000)
    rows = _statement_rows(rng, opening)
    for row in rows:
        row["printed"], row["wrapped"] = row["balance"], rng.random() < 0.4
    misprint = rng.randrange(len(rows)) if len(rows) >= 6 and rng.random() < 0.2 else None
    lost = rng.randrange(len(rows)) if len(rows) >= 6 and rng.random() < 0.1 else None
    for error in (Decimal("9.00"), Decimal("-90.00"), Decimal("0.90"), Decimal("123.45")):
        for row in rows:
            row["printed"], row["year_lost"] = row["balance"], False
        if misprint is not None:          # verdruckter Saldo: die Zeile und die naechste passen nicht in die Kette
            rows[misprint]["printed"] = rows[misprint]["balance"] + error
        if lost is not None and lost != misprint:   # das Jahr steht hinter einem Seitenwechsel, ausser Reichweite
            rows[lost]["year_lost"] = True
        candidates, diagnostics, faithful = _simulate(rows, opening)
        if faithful and candidates:
            break
    else:                                 # kein Sonderfall ohne Zufallstreffer in der Kette: dann ohne
        for row in rows:
            row["printed"], row["year_lost"] = row["balance"], False
        candidates, diagnostics, _faithful = _simulate(rows, opening)
    body: list[str] = []
    breaks = {index for index in range(len(rows) - 1) if rng.random() < 0.06}   # Seitenwechsel zwischen zwei Zeilen
    pages = 1 + len(breaks) + sum(1 for row in rows if row["year_lost"])
    page = 1
    for index, row in enumerate(rows):
        month = MONTHS[row["day"].month - 1]
        money = f"{_german(row['amount'])} €{' ' * rng.randrange(2, 24)}{_german(row['printed'])} €"
        description = row["description"] + (f" {_german(row['fee'])} €" if row["fee"] is not None else "")
        if row["wrapped"]:
            body += [f"{row['day'].day:02d}", description, f"{month} {row['kind']} {money}"]
        else:
            body += [f"{row['day'].day:02d} {month}", f"{row['kind']} {description} {money}"]
        if row["year_lost"]:
            page += 1
            body += [line.format(page=page, pages=pages) for line in PAGE_BREAK]
        body.append(str(row["day"].year))
        if index in breaks:
            page += 1
            body += [line.format(page=page, pages=pages) for line in PAGE_BREAK]
    deposits = sum((row["amount"] for row in rows if row["sign"] > 0), Decimal(0))
    withdrawals = sum((row["amount"] for row in rows if row["sign"] < 0), Decimal(0))
    closing = rows[-1]["balance"]
    owner = rng.choice(("ERIKA ERFUNDEN", "MAX ERFUNDEN", "PAULA INVENTED"))
    lines = ["TRADE REPUBLIC BANK GMBH", owner, "", "KONTOÜBERSICHT", "PRODUKT       ANFANGSSALDO   ZAHLUNGSEINGANG   ZAHLUNGSAUSGANG   ENDSALDO",
             f"Cashkonto     {_german(opening)} €         {_german(deposits)} €        {_german(withdrawals)} €        {_german(closing)} €", "",
             "UMSATZÜBERSICHT", "DATUM   TYP   BESCHREIBUNG   ZAHLUNGSEINGANG ZAHLUNGSAUSGANG   SALDO", ""]
    lines += body + [""] + rng.choice(TRAILERS)
    days = sorted(row["local_date"] for row in candidates)
    expected = {"candidates": candidates, "diagnostics": diagnostics,
                "summary": {"opening_balance_decimal": _plain(opening), "closing_balance_decimal": _plain(closing),
                            "period_from": days[0], "period_to": days[-1]}}
    return {"file_name": f"trade-republic-kontoauszug-erfunden-{seed}.txt", "content": ("\n".join(lines) + "\n").encode("utf-8"), "expected": expected}


# ---------------------------------------------------------------- cash/trade_republic_transactions_v1: CSV-Export
EXPORT_SHORT = ["datetime", "date", "category", "type", "name", "amount", "fee", "tax", "currency", "description", "transaction_id"]
EXPORT_FULL = ["datetime", "date", "account_type", "category", "type", "asset_class", "name", "symbol", "shares", "price", "amount", "fee", "tax",
               "currency", "original_amount", "original_currency", "fx_rate", "description", "transaction_id", "counterparty_name",
               "counterparty_iban", "payment_reference", "mcc_code"]


def _transaction_id(rng: random.Random, long: bool = False) -> str:
    text = "".join(rng.choice("0123456789abcdef") for _ in range(32))
    value = f"{text[:8]}-{text[8:12]}-{text[12:16]}-{text[16:20]}-{text[20:]}"
    return value + ("-" + "".join(rng.choice("0123456789") for _ in range(6)) if long else "")


def _amount_text(value: Decimal, places: int = 2) -> str:
    return f"{value:.{places}f}"


def _export_row(rng: random.Random) -> tuple[dict[str, str], dict[str, Any]]:
    """Eine Zeile des Exports und, unabhaengig vom Leser, was sie bedeutet: Kontofluss amount + fee + tax (Gebuehr und Steuer negativ,
    eine Erstattung positiv), Art, Bruttoertrag, Hinweis oder uebergangen."""
    choice = rng.choices(("inbound", "outbound", "buy", "sell", "dividend", "interest", "interest_taxed", "interest_eaten", "tax_optimization",
                          "card", "free_receipt", "foreign", "bad_date", "bad_amount", "zero_flow"),
                         weights=(12, 6, 14, 8, 8, 10, 6, 3, 3, 8, 3, 2, 2, 2, 2))[0]
    isin = _isin(rng)
    name = rng.choice(("ERFUNDENE AG", "INVENTED CORP", "FANTASIE WELT ETF", "MUSTERBAU HOLDING, INC."))
    row = {"category": "CASH", "type": "", "name": "", "amount": "", "fee": "", "tax": "", "currency": "EUR", "description": "", "date_text": None}
    amount = fee = tax = Decimal(0)
    if choice == "inbound":
        amount = _money(rng, 1_000, 500_000)
        row.update(type="CUSTOMER_INBOUND", description=rng.choice(("Umbuchung", "Incoming transfer from Erika Erfunden")))
    elif choice == "outbound":
        amount = -_money(rng, 1_000, 200_000)
        row.update(type="CUSTOMER_OUTBOUND_REQUEST", description="Outgoing transfer for Erika Erfunden")
    elif choice == "buy":
        amount, fee = -_money(rng, 100, 300_000), rng.choice((Decimal("-1.00"), Decimal(0)))
        row.update(category="TRADING", type="BUY", name=name, description=f"{rng.choice(('Buy trade', 'Savings plan execution'))} {isin} {name}")
    elif choice == "sell":
        amount, fee = _money(rng, 100, 300_000), Decimal("-1.00")
        tax = rng.choice((Decimal(0), -_money(rng, 1, 5_000), _money(rng, 1, 2_000)))   # Steuer, keine oder Erstattung
        row.update(category="TRADING", type="SELL", name=name, description=f"Sell trade {isin} {name}")
    elif choice == "dividend":
        amount = _money(rng, 1, 20_000)
        tax = rng.choice((Decimal(0), -(amount * Decimal("0.26375")).quantize(CENT, ROUND_HALF_UP)))
        row.update(type="DIVIDEND", name=name, description=f"Cash Dividend for ISIN {isin}")
    elif choice in ("interest", "interest_taxed", "interest_eaten"):
        amount = _money(rng, 1, 5_000)
        tax = {"interest": Decimal(0), "interest_taxed": -(amount * Decimal("0.26375")).quantize(CENT, ROUND_HALF_UP), "interest_eaten": -amount}[choice]
        row.update(type="INTEREST_PAYMENT", description="Interest payment Booking")
    elif choice == "tax_optimization":
        tax = _money(rng, 1, 5_000)
        row.update(type="TAX_OPTIMIZATION", description="Tax Optimisation", amount="0.000000")
    elif choice in ("card", "foreign"):
        amount = -_money(rng, 100, 30_000)
        row.update(type="CARD_TRANSACTION", description=rng.choice(("Erfundener Laden", "ERFUNDENES CAFE")), currency="USD" if choice == "foreign" else "EUR")
    elif choice == "free_receipt":   # Einbuchung ohne Geldbewegung
        row.update(category="CASH", type="FREE_RECEIPT", description=f"FREE_RECEIPT {isin}", currency="")
    elif choice == "bad_date":
        amount = _money(rng, 1_000, 50_000)
        row.update(type="CUSTOMER_INBOUND", description="Umbuchung", date_text=rng.choice(("unbekannt", "2023-02-30", "2022-13-01")))
    elif choice == "bad_amount":
        row.update(type="CARD_TRANSACTION", description="Erfundener Laden", amount=rng.choice(("-12.345", "n/a", "-1O.00")))
    elif choice == "zero_flow":   # Betrag und Gebuehr heben sich auf: auf dem Konto bewegt sich nichts
        amount = _money(rng, 100, 1_000)
        fee = -amount
        row.update(type="BONUS", description="Erfundene Prämie")
    if not row["amount"] and choice != "free_receipt":   # die Einbuchung ohne Geldbewegung hat keinen Betrag
        row["amount"] = _amount_text(amount, rng.choice((2, 6)))
    if fee:
        row["fee"] = _amount_text(fee)
    if tax:
        row["tax"] = _amount_text(tax)
    flow = amount + fee + tax
    text = " ".join(part for part in (row["type"], row["description"]) if part)
    if choice == "bad_amount":
        meaning = {"diagnostic": "amount_invalid"}
    elif choice == "free_receipt":
        meaning = {"skip": True}
    elif choice == "foreign":
        meaning = {"diagnostic": "currency_unsupported"}
    elif choice == "bad_date":
        meaning = {"diagnostic": "date_invalid"}
    elif choice == "interest_eaten":
        meaning = {"diagnostic": "interest_fully_taxed", "gross": amount}
    elif choice == "zero_flow":
        meaning = {"diagnostic": "amount_invalid"}
    else:
        interest = choice in ("interest", "interest_taxed")
        meaning = {"kind": "interest" if interest else ("deposit" if flow > 0 else "withdrawal"), "amount": abs(flow), "text": text,
                   "gross": amount if interest and amount != flow else None}
    return row, meaning


def _export(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    columns = EXPORT_FULL if rng.random() < 0.4 else EXPORT_SHORT
    moment = datetime(2021, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=rng.randrange(0, 60 * 24 * 365 * 3))
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL if rng.random() < 0.6 else csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow(columns)
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    ordinal = 0
    for _ in range(rng.randrange(3, 30)):
        moment += timedelta(minutes=rng.randrange(1, 60 * 24 * 12))
        if rng.random() < 0.03:   # Zeile ohne Inhalt: der Export zaehlt sie nicht
            writer.writerow([""] * len(columns))
        row, meaning = _export_row(rng)
        values = {"datetime": moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z", "date": row["date_text"] or moment.date().isoformat(),
                  "account_type": "DEFAULT", "transaction_id": _transaction_id(rng), **{key: row[key] for key in
                  ("category", "type", "name", "amount", "fee", "tax", "currency", "description")}}
        writer.writerow([values.get(column, "") for column in columns])
        ordinal += 1
        if meaning.get("skip"):
            continue
        if "diagnostic" in meaning:
            diagnostic = {"source_row_ordinal": ordinal, "reason_code": meaning["diagnostic"]}
            if meaning.get("gross") is not None:
                diagnostic["gross_income_decimal"] = _plain(meaning["gross"])
            diagnostics.append(diagnostic); continue
        candidate = {"source_row_ordinal": ordinal, "local_date": moment.date().isoformat(), "kind": meaning["kind"],
                     "amount_decimal": _plain(meaning["amount"]), "balance_after_decimal": None, "text": meaning["text"]}
        if meaning["gross"] is not None:
            candidate["gross_income_decimal"] = _plain(meaning["gross"])
        candidates.append(candidate)
    if not candidates:   # mindestens eine Bewegung, sonst ist der Export kein Beleg dieses Formats
        moment += timedelta(days=1)
        values = {"datetime": moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z", "date": moment.date().isoformat(), "account_type": "DEFAULT",
                  "category": "CASH", "type": "CUSTOMER_INBOUND", "amount": "25.00", "currency": "EUR", "description": "Umbuchung",
                  "transaction_id": _transaction_id(rng)}
        writer.writerow([values.get(column, "") for column in columns])
        ordinal += 1
        candidates.append({"source_row_ordinal": ordinal, "local_date": moment.date().isoformat(), "kind": "deposit", "amount_decimal": "25",
                           "balance_after_decimal": None, "text": "CUSTOMER_INBOUND Umbuchung"})
    days = sorted(row["local_date"] for row in candidates)
    expected = {"candidates": candidates, "diagnostics": diagnostics,
                "summary": {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": days[0], "period_to": days[-1]}}
    return {"file_name": f"trade-republic-transaktionen-erfunden-{seed}.csv", "content": output.getvalue().encode("utf-8"), "expected": expected}


# ---------------------------------------------------------------- securities/trade_republic_v1: CSV-Export "Transaktionen"
SECURITY_NAMES = ("Erfundene Software AG", "Invented Corp", "Fantasie Welt ETF Acc", "Musterbau Holding AG", "Erfunden, Inc.", "Invented Dividend ETF Dist")


def _security_candidate(kind: str, **fields: Any) -> dict[str, Any]:
    value = {"status": "candidate", "kind": kind, "profile": "trade_republic", "isin": None, "security_name": None, "local_date": None,
             "local_time": None, "quantity": None, "unit_price": None, "gross_amount": None, "fee_amount": "0", "eligible_quantity": None,
             "order_ref": None, "depot_ref": None, "ex_date": None, "net_amount": None, "taxes_amount": None, "withholding_amount": None,
             "bank_gain": None, "fee_on_cash_statement": False, "currency": None, "valuta": None, "statement_checked": False}
    value.update(fields)
    return value


def _stamp(rng: random.Random, moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S") + (f".{moment.microsecond // 1000:03d}Z" if rng.random() < 0.7 else f".{moment.microsecond:06d}Z")


def _securities(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    start = datetime(2021, 1, 4, tzinfo=timezone.utc) + timedelta(days=rng.randrange(0, 365 * 3))
    end = start + timedelta(days=rng.randrange(20, 360))
    papers = [(_isin(rng), rng.choice(SECURITY_NAMES)) for _ in range(rng.randrange(1, 5))]
    used_isins = {isin for isin, _name in papers}

    def fresh_isin() -> str:
        while True:
            isin = _isin(rng)
            if isin not in used_isins:
                used_isins.add(isin); return isin

    def moment() -> datetime:
        """Zeitpunkt in UTC; selten kurz vor Mitternacht UTC, dann liegt der Tag in Berlin schon einen weiter."""
        day = start + timedelta(days=rng.randrange(0, (end - start).days + 1))
        hour = rng.choice((rng.randrange(6, 21), rng.randrange(6, 21), 22, 23))
        return day.replace(hour=hour, minute=rng.randrange(60), second=rng.randrange(60), microsecond=rng.randrange(1000) * 1000)

    events: list[tuple[datetime, int, dict[str, str], Any]] = []   # (Zeitpunkt, Folge, Zeile, Bedeutung)
    sequence = 0

    def add(at: datetime, values: dict[str, str], meaning: Any) -> None:
        nonlocal sequence
        sequence += 1
        events.append((at.replace(microsecond=0), sequence, {"_at": at, **values}, meaning))

    for _ in range(rng.randrange(2, 16)):
        choice = rng.choices(("buy", "split_buy", "savings", "sell", "dividend", "reversal", "earnings", "reason"), weights=(14, 6, 6, 10, 10, 3, 5, 12))[0]
        isin, name = rng.choice(papers)
        at = moment()
        if choice in ("buy", "sell", "savings"):
            buy = choice != "sell"
            price = Decimal(rng.randrange(100, 900_000)) / Decimal(rng.choice((100, 10_000)))
            quantity = Decimal(rng.randrange(1, 50)) if choice != "savings" else (_money(rng, 2_500, 50_000) / price).quantize(Decimal("0.000001"))
            gross = (quantity * price).quantize(CENT, ROUND_HALF_UP)
            fee = Decimal("-1.00") if choice != "savings" else Decimal(0)
            shares = quantity if buy or rng.random() < 0.5 else -quantity
            add(at, {"category": "TRADING", "type": "BUY" if buy else "SELL", "name": name, "symbol": isin, "shares": f"{shares:.10f}",
                     "price": f"{price:.6f}", "amount": f"{(-gross if buy else gross):.2f}", "fee": f"{fee:.2f}" if fee else "",
                     "tax": "" if buy or rng.random() < 0.5 else f"{-_money(rng, 1, 3_000):.2f}"},
                ("trade", "buy" if buy else "sell", isin, name, quantity, price, gross, abs(fee)))
        elif choice == "split_buy":   # Kauf nach Betrag: ganze Stuecke mit Gebuehr und Bruchteil ohne, in derselben Sekunde
            price = Decimal(rng.randrange(100, 90_000)) / 100
            whole, fraction = Decimal(rng.randrange(1, 20)), Decimal(rng.randrange(1, 9_999)) / 10_000
            parts = [(whole, Decimal("-1.00")), (fraction, Decimal(0))]
            milliseconds = rng.sample(range(1000), 2)
            if rng.random() < 0.5:
                parts.reverse()
            for (quantity, fee), millisecond in zip(parts, milliseconds):
                gross = (quantity * price).quantize(CENT, ROUND_HALF_UP)
                add(at.replace(microsecond=millisecond * 1000), {"category": "TRADING", "type": "BUY", "name": name, "symbol": isin,
                                                                 "shares": f"{quantity:.10f}", "price": f"{price:.6f}", "amount": f"{-gross:.2f}",
                                                                 "fee": f"{fee:.2f}" if fee else ""},
                    ("trade", "buy", isin, name, quantity, price, gross, abs(fee)))
        elif choice == "dividend":
            shares = Decimal(rng.randrange(1, 400)) if rng.random() < 0.8 else Decimal(rng.randrange(1, 99_999)) / 1000
            amount = (shares * Decimal(rng.randrange(1, 200)) / 100).quantize(CENT, ROUND_HALF_UP) or CENT
            tax = rng.choice((Decimal(0), (amount * Decimal("0.26375")).quantize(CENT, ROUND_HALF_UP)))
            add(at, {"category": "CASH", "type": "DIVIDEND", "name": name, "symbol": isin, "shares": f"{shares:.10f}", "amount": f"{amount:.2f}",
                     "tax": f"{-tax:.2f}" if tax else ""}, ("dividend", isin, name, shares, amount, tax))
        elif choice == "reversal":   # Gutschrift und Rueckbuchung am selben Tag heben sich auf; danach mal die richtige Gutschrift
            isin = fresh_isin()
            at = at.replace(hour=rng.randrange(6, 20))   # beide Zeilen am selben Tag in Berlin
            shares = Decimal(rng.randrange(1, 300))
            amount = _money(rng, 10, 20_000)
            orphan = rng.random() < 0.25
            if not orphan:
                add(at, {"category": "CASH", "type": "DIVIDEND", "name": name, "symbol": isin, "shares": f"{shares:.10f}", "amount": f"{amount:.2f}"},
                    ("reversed",))
            add(at + timedelta(minutes=rng.randrange(1, 30)), {"category": "CASH", "type": "DIVIDEND", "name": name, "symbol": isin,
                                                              "shares": f"{shares:.10f}", "amount": f"{-amount:.2f}"}, ("reversed",))
            if rng.random() < 0.5:
                corrected = amount + _money(rng, 1, 500)
                add(at + timedelta(minutes=45), {"category": "CASH", "type": "DIVIDEND", "name": name, "symbol": isin, "shares": f"{shares:.10f}",
                                                 "amount": f"{corrected:.2f}"}, ("dividend", isin, name, shares, corrected, Decimal(0)))
        elif choice == "earnings":   # Vorabpauschale: der Export nennt nur die Steuer, gebucht Anfang Januar
            januaries = [year for year in range(start.year, end.year + 1) if start <= datetime(year, 1, 5, tzinfo=timezone.utc) <= end]
            if not januaries:
                continue
            at = datetime(rng.choice(januaries), 1, rng.randrange(2, 6), rng.randrange(6, 20), rng.randrange(60), rng.randrange(60), tzinfo=timezone.utc)
            tax_text = rng.choice(("", f"{-_money(rng, 1, 2_000):.2f}", "0.00"))
            add(at, {"category": "CASH", "type": "EARNINGS", "name": name, "symbol": isin, "tax": tax_text},
                ("earnings", isin, name, abs(Decimal(tax_text)) if tax_text else None))
        else:
            reason = rng.choice(("tax_optimization", "ipo", "allotment", "foreign", "cash", "custody", "unknown", "bad_time", "sell_without_price",
                                 "dividend_without_shares"))
            values = {"tax_optimization": {"category": "CASH", "type": "TAX_OPTIMIZATION", "tax": f"{_money(rng, 1, 3_000):.2f}"},
                      "ipo": {"category": "TRADING", "type": "IPO_SUBSCRIPTION", "name": name, "symbol": isin},
                      "allotment": {"category": "TRADING", "type": "BUY", "name": name, "symbol": isin, "shares": "5.0000000000"},
                      "foreign": {"category": "TRADING", "type": "BUY", "name": name, "symbol": isin, "shares": "2.0000000000", "price": "10.000000",
                                  "amount": "-20.00", "fee": "-1.00", "currency": "USD"},
                      "cash": {"category": "CASH", "type": rng.choice(("INTEREST_PAYMENT", "CUSTOMER_INBOUND", "CARD_TRANSACTION")), "amount": "12.34"},
                      "custody": {"category": "CORPORATE_ACTION", "type": rng.choice(("FREE_RECEIPT", "DELIVERY", "FREE_DELIVERY", "TRANSFER")),
                                  "name": name, "symbol": isin, "shares": "1.0000000000"},
                      "unknown": {"category": "CORPORATE_ACTION", "type": "STOCK_PERK", "name": name, "symbol": isin},
                      "bad_time": {"category": "TRADING", "type": "BUY", "name": name, "symbol": isin, "shares": "1.0000000000", "price": "5.000000",
                                   "amount": "-5.00", "_stamp": "unbekannt"},
                      "sell_without_price": {"category": "TRADING", "type": "SELL", "name": name, "symbol": isin, "shares": "-1.0000000000",
                                             "amount": "15.00"},
                      "dividend_without_shares": {"category": "CASH", "type": "DIVIDEND", "name": name, "symbol": isin, "amount": "3.21"}}[reason]
            code = {"tax_optimization": "tax_document", "ipo": "ipo", "allotment": "ipo", "foreign": "not_eur", "cash": "cash_movement",
                    "custody": "custody_change", "unknown": "unknown_document", "bad_time": "incomplete", "sell_without_price": "incomplete",
                    "dividend_without_shares": "incomplete"}[reason]
            add(at, values, ("reason", code))
    events.sort(key=lambda item: (item[0], item[1]))

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(EXPORT_FULL)
    trades: list[dict[str, Any]] = []
    dividends: list[dict[str, Any]] = []
    earnings: list[dict[str, Any]] = []
    reasons: dict[str, int] = {}
    for position, (_second, _sequence, values, meaning) in enumerate(events):
        at = values.pop("_at")
        local = at.astimezone(BERLIN)
        reference = _transaction_id(rng, long=rng.random() < 0.1)
        stamp = values.pop("_stamp", None) or _stamp(rng, at)
        row = {"datetime": stamp, "date": local.date().isoformat(), "account_type": "DEFAULT", "asset_class": "STOCK" if values.get("symbol") else "",
               "currency": "EUR", "description": "", "transaction_id": reference, **values}
        writer.writerow([row.get(column, "") for column in EXPORT_FULL])
        kind = meaning[0]
        if kind == "trade":
            _kind, side, isin, name, quantity, price, gross, fee = meaning
            trades.append(_security_candidate(side, isin=isin, security_name=name, local_date=local.date().isoformat(), local_time=local.strftime("%H:%M:%S"),
                                              quantity=_plain(quantity), unit_price=_plain(price), gross_amount=_plain(gross), fee_amount=_plain(fee),
                                              order_ref=reference[:36], executed_at_utc=at.isoformat(timespec="microseconds"), export_position=position))
        elif kind == "dividend":
            _kind, isin, name, shares, amount, tax = meaning
            dividends.append(_security_candidate("dividend", isin=isin, security_name=name, local_date=local.date().isoformat(),
                                                 eligible_quantity=_plain(shares), gross_amount=_plain(amount),
                                                 taxes_amount=_plain(tax) if tax else None, order_ref=reference[:36]))
        elif kind == "earnings":
            _kind, isin, name, tax = meaning
            earnings.append(_security_candidate("advance_lump_sum", isin=isin, security_name=name, local_date=local.date().isoformat(),
                                                taxes_amount=_plain(tax) if tax is not None else None, order_ref=reference[:36],
                                                calculation_year=local.year - 1))
        else:
            code = "dividend_reversed" if kind == "reversed" else meaning[1]
            reasons[code] = reasons.get(code, 0) + 1
    expected = {"status": "multi", "candidates": trades + dividends + earnings, "row_reasons": reasons}
    return {"file_name": f"trade-republic-transaktionen-erfunden-{seed}.csv", "content": output.getvalue(), "expected": expected}


GENERATORS = {
    ("cash", "trade_republic_v1"): _statement,
    ("cash", "trade_republic_transactions_v1"): _export,
    ("securities", "trade_republic_v1"): _securities,
}
