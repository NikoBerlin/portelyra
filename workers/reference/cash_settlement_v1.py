"""Abrechnungen und Auszugszeilen (#539): welche Kauf-, Verkaufs- und Dividendenbuchung auf welchem Cash-Konto angekommen ist.

Zwei Leser teilen dieselbe Zuordnung:
- die Tageshistorie (#480, #481) erklaert damit die Kontoaenderung je Tag - was bleibt, ist ein externer Fluss;
- der vorlaeufige Cash-Stand (#539) zaehlt damit die Abrechnungen, die noch keine Auszugszeile haben.

Der vorlaeufige Stand ist eine Anzeige, keine Buchung. Cash kommt mit dem Monatsauszug, Wertpapiere kommen mit den
Abrechnungen; dazwischen zeigt das Bild nach einem Kauf zu viel und nach einem Verkauf zu wenig (Festlegung 04.11.2026).
Der vorlaeufige Saldo eines Kontos ist sein amtlicher (letzter Auszug bzw. Abgleich) plus die danach gebuchten Bewegungen
plus die Abrechnungen seiner Depots, die noch keiner Auszugszeile zugeordnet sind. Kommt der Auszug, ordnet die Zuordnung
die Abrechnung ihrer Zeile zu, und die Schaetzung faellt von selbst weg. Gebucht wird nichts - deshalb kann nichts doppelt
gebucht werden.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from fractions import Fraction
import sqlite3
from pathlib import Path
from typing import Any

from migrations.reference.exact_amount_v1 import amount_text_v1, exact_amount_v1

TARGET_CURRENCY = "EUR"
# Bucht das Geld eines Kaufs oder Verkaufs spaeter (Valuta), sucht der Abgleich je Konto so viele Tage weiter.
VALUTA_DAYS = 5
# Konten, deren Saldo im Cash zaehlt (#481).
CASH_ACCOUNT_TYPES = ("cash", "bank")
# Eine Gutschrift, die einem Verkauf oder einer Dividende im Valuta-Fenster vor dem letzten Auszug folgt, aber nicht auf den
# Cent passt (einbehaltene Steuer, Entgelt), gilt als dessen Abrechnung, wenn sie zwischen diesen Anteilen des Betrags liegt.
LOOSE_SHARE = (Fraction(6, 10), Fraction(105, 100))
# Geschaetzt wird nur die Luecke eines laufenden Auszugszyklus: Ist der letzte Auszug eines Kontos aelter, wird nichts
# geschaetzt, sondern das Konto mit seinen offenen Abrechnungen genannt (ein Konto mit Auszug vom
# Vorjahr haette sonst Monate voller Kaeufe als Cash-Abfluss gezaehlt).
MAX_GAP_DAYS = 62
# Ein Depot rechnet nachweislich auf ein Konto ab, wenn mindestens so viele seiner Abrechnungen dort eine Auszugszeile haben.
MIN_LEARNED = 3
# Auf einem geschlossenen oder ruhenden Konto kommt keine Abrechnung mehr an.
QUIET_STATES = ("closed", "resting")


def match_settlements_v1(cash_view: dict[str, Any], ledger: list[dict[str, Any]], accounts: dict[str, dict[str, Any]],
                         scope: dict[str, Any]) -> dict[str, Any]:
    """Die Zuordnung Abrechnung -> Auszugszeile, wie die Tageshistorie sie seit rc.288 rechnet (aus `_account_flows`
    herausgeloest, unveraendert).

    - Kauf und Verkauf: das Konto, auf dem genau der Betrag gebucht ist - beim selben Institut, am Handelstag oder bis zu
      VALUTA_DAYS Tage spaeter (Valuta); bei einem Institut ohne gefuehrtes Konto auf irgendeinem eigenen Konto.
      Danach die Summe der Kaeufe bzw. Verkaeufe eines Depots am Tag (Teilausfuehrungen in einer Zeile).
    - Dividenden wie Kaeufe, mit einer Gutschrift zwischen 60 % und 100 % des gebuchten Betrags (einbehaltene Steuer).
    - Zinsen (Bewegungen mit `income_receipt`) gelten als erklaert.

    `scope`: je Cash-Konto (Bezeichnung) mindestens `institution`. Rueckgabe: `events` (Bewegungen mit `used`), `explained`
    und `valuta` je (Konto, Tag bzw. Monat), `settles` (je Depot, wie oft es auf welches Konto abrechnete) und `unmatched`:
    je nicht zugeordneter Abrechnung `row`, `meta`, `amount`, `target` (wie die Historie es waehlt) und `learned` (nur das
    Konto, auf dem das Depot nachweislich abrechnet, sonst None)."""
    zero = exact_amount_v1("0")
    tolerance = exact_amount_v1("0.01")
    labels = set(scope)
    institution_of = {label: meta["institution"] for label, meta in scope.items()}
    events: list[dict[str, Any]] = []
    for event in cash_view.get("cash_history") or []:
        if event.get("event_type") in ("deposit", "withdrawal") and event.get("currency") == TARGET_CURRENCY and event.get("account_label") in labels:
            amount = exact_amount_v1(event["amount_decimal"]) * (1 if event["event_type"] == "deposit" else -1)
            events.append({"label": event["account_label"], "day": event["local_date"], "amount": amount, "used": False,
                           "income": event.get("flow_classification") == "income_receipt"})
    at_institution: dict[tuple[str, str], list[int]] = defaultdict(list)
    on_day: dict[str, list[int]] = defaultdict(list)
    for index, event in enumerate(events):
        at_institution[(institution_of[event["label"]], event["day"])].append(index)
        on_day[event["day"]].append(index)
    explained: dict[tuple[str, str], Any] = defaultdict(lambda: zero)
    valuta: dict[tuple[str, str], int] = defaultdict(int)
    for event in events:
        if event["income"]:
            event["used"] = True
            explained[(event["label"], event["day"])] += event["amount"]

    def find(institution: str | None, day: str, fits) -> int | None:
        start = date.fromisoformat(day)
        for lag in range(0, VALUTA_DAYS + 1):
            later = (start + timedelta(days=lag)).isoformat()
            pool = at_institution.get((institution, later), []) if institution is not None else on_day.get(later, [])
            for index in pool:
                if not events[index]["used"] and fits(events[index]["amount"]):
                    return index
        return None

    cash_institutions = set(institution_of.values())
    settles: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    waiting = []
    for row in sorted(ledger, key=lambda item: (item["local_date"] or "", item["event_ref"])):
        kind, day, meta = row["event_type"], row["local_date"], accounts.get(row["account_id"])
        if meta is None or not day or row["basis_currency"] != TARGET_CURRENCY or kind not in ("buy", "sell", "dividend"):
            continue
        if kind == "buy" and row["gross_economic_amount_decimal"] is not None:
            amount = -(exact_amount_v1(row["gross_economic_amount_decimal"]) + exact_amount_v1(row["monetary_fee_decimal"] or "0"))
            fits = lambda value, amount=amount: abs(value - amount) <= tolerance
        elif kind == "sell" and row["net_trade_proceeds_decimal"] is not None:
            amount = exact_amount_v1(row["net_trade_proceeds_decimal"])
            fits = lambda value, amount=amount: abs(value - amount) <= tolerance
        elif kind == "dividend":
            value = row.get("gross_income_decimal") if row.get("gross_income_decimal") is not None else row["gross_amount_decimal"]
            if value is None:
                continue
            amount = exact_amount_v1(value)
            fits = lambda received, amount=amount: amount * 6 / 10 <= received <= amount + tolerance
        else:
            continue
        institution = meta["institution"]
        hit = find(institution if institution in cash_institutions else None, day, fits)
        if hit is None:
            waiting.append((row, meta, amount))
            continue
        event = events[hit]; event["used"] = True
        # Gebucht wird, was auf dem Konto ankam; bei einer Dividende mit einbehaltener Steuer ist das der kleinere Betrag.
        explained[(event["label"], event["day"])] += event["amount"] if kind == "dividend" else amount
        settles[row["account_id"]][event["label"]] += 1
        if event["day"] != day:
            valuta[(event["label"], event["day"][:7])] += 1
    # Teilausfuehrungen und mehrere Orders eines Tages bucht das Konto oft als eine Zeile: die Summe je Depot, Tag und Art.
    grouped: dict[tuple[str, str, str], list[tuple[dict[str, Any], dict[str, Any], Any]]] = defaultdict(list)
    for item in waiting:
        grouped[(item[0]["account_id"], item[0]["local_date"], item[0]["event_type"])].append(item)
    waiting = []
    for (account, day, kind), items in sorted(grouped.items()):
        if len(items) < 2 or kind == "dividend":
            waiting.extend(items); continue
        total = sum((amount for _, _, amount in items), start=zero)
        institution = items[0][1]["institution"]
        hit = find(institution if institution in cash_institutions else None, day, lambda value, total=total: abs(value - total) <= tolerance)
        if hit is None:
            waiting.extend(items); continue
        event = events[hit]; event["used"] = True
        explained[(event["label"], event["day"])] += total
        settles[account][event["label"]] += 1
        if event["day"] != day:
            valuta[(event["label"], event["day"][:7])] += 1
    unmatched = []
    for row, meta, amount in waiting:
        usual = settles.get(row["account_id"])
        learned = max(usual, key=lambda label: (usual[label], label)) if usual else None
        target = learned
        if target is None:
            here = sorted(label for label, institution in institution_of.items() if institution == meta["institution"])
            target = here[0] if len(here) == 1 else None
        unmatched.append({"row": row, "meta": meta, "amount": amount, "target": target, "learned": learned})
    return {"events": events, "explained": explained, "valuta": valuta, "settles": settles, "unmatched": unmatched}


def cash_scope_v1(accounts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Je Cash-Konto (Bezeichnung) sein Institut - was die Zuordnung braucht; die Zugehoerigkeit zur Anlage spielt hier keine
    Rolle."""
    return {meta["label"]: {"institution": meta["institution"]} for _, meta in sorted(accounts.items(), key=lambda item: item[1]["label"])
            if meta["account_type"] in CASH_ACCOUNT_TYPES}


def read_accounts_v1(canonical: Path) -> dict[str, dict[str, Any]]:
    """Je Konto Bezeichnung, Kontoart und Institut - gelesen, nicht veraendert (wie die Tageshistorie)."""
    connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
    try:
        rows = connection.execute("SELECT account_id, display_name, account_type, institution_label FROM account").fetchall()
    finally:
        connection.close()
    return {account: {"label": label, "account_type": kind, "institution": (institution or "").strip() or label}
            for account, label, kind, institution in rows}


def read_ledger_v1(ledger_path: str | Path) -> list[dict[str, Any]]:
    """Die aktuellen Buchungen, soweit die Zuordnung sie braucht - nur lesend."""
    connection = sqlite3.connect("file:" + str(ledger_path) + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(
            "SELECT event_ref, event_type, account_id, local_date, gross_economic_amount_decimal, gross_amount_decimal,"
            " gross_income_decimal, monetary_fee_decimal, net_trade_proceeds_decimal, basis_currency"
            " FROM current_asset_activity_event")]
    finally:
        connection.close()


def provisional_cash_v1(cash_accounts: list[dict[str, Any]], matched: dict[str, Any], as_of_date: str) -> dict[str, Any]:
    """Der vorlaeufige Saldo je Euro-Konto in der Summe - nur, wo er vom amtlichen abweicht.

    Je aktivem Konto mit amtlichem Saldo vom Tag D (`balance_date`) bis zum Stichtag S:
    - die Bewegungen auf dem Konto nach D bis S (etwa eine Handbuchung nach dem letzten Auszug);
    - die Abrechnungen, die keiner Auszugszeile zugeordnet sind und deren Depot nachweislich auf dieses Konto abrechnet
      (`learned` mit mindestens MIN_LEARNED Treffern; ein Depot, das nie auf einem gefuehrten Konto abrechnete, bezahlt von
      ausserhalb - das aendert die Summe nicht), vom Tag nach D - VALUTA_DAYS bis S. Liegt eine Abrechnung im
      Valuta-Fenster vor D und steht auf dem Konto zwischen ihrem Tag und D eine noch freie Bewegung derselben Richtung mit
      60-105 % ihres Betrags, gilt sie als abgerechnet (einbehaltene Steuer, Entgelt).
    Liegt D mehr als MAX_GAP_DAYS vor S, werden die Abrechnungen nicht geschaetzt, sondern gezaehlt (`unestimated`); die
    gebuchten Bewegungen zaehlen trotzdem - sie sind Tatsachen, keine Schaetzung (ein Tagesgeld ohne Importer wird oft nur
    selten abgeglichen, eine Handbuchung soll dort im vorlaeufigen Stand stehen).
    Ein Kauf zaehlt mit Kurswert plus Gebuehr, ein Verkauf mit dem Erloes nach Gebuehr und vor Steuer, eine Dividende mit dem
    gebuchten Betrag. Rueckgabe: je Konto (`account_label`) `provisional_balance_decimal` (None, wenn nicht geschaetzt),
    `settlement_count`, `movement_count`, `unestimated_count`, dazu die Summe der Abweichungen."""
    by_label = {row["account_label"]: row for row in cash_accounts
                if row.get("currency") == TARGET_CURRENCY and row.get("in_total") and isinstance(row.get("balance_date"), str)
                and row.get("balance_decimal") is not None and row.get("account_state") not in QUIET_STATES}
    limit = (date.fromisoformat(as_of_date) - timedelta(days=MAX_GAP_DAYS)).isoformat()
    events = matched["events"]
    found: dict[str, dict[str, Any]] = {}

    def entry(label: str) -> dict[str, Any]:
        return found.setdefault(label, {"moved": Fraction(0), "settled": Fraction(0), "settlement_count": 0, "movement_count": 0})

    for event in events:
        row = by_label.get(event["label"])
        if row is not None and row["balance_date"] < event["day"] <= as_of_date:
            item = entry(event["label"]); item["moved"] += event["amount"]; item["movement_count"] += 1
    settles = matched["settles"]
    for pending in sorted(matched["unmatched"], key=lambda item: (item["row"]["local_date"], item["row"]["event_ref"])):
        label, day = pending["learned"], pending["row"]["local_date"]
        if label is not None and settles.get(pending["row"]["account_id"], {}).get(label, 0) < MIN_LEARNED:
            label = None
        row = by_label.get(label) if label is not None else None
        if row is None or day > as_of_date:
            continue
        since = (date.fromisoformat(row["balance_date"]) - timedelta(days=VALUTA_DAYS)).isoformat()
        if day <= since:
            continue
        amount = pending["amount"]
        if day <= row["balance_date"]:
            low, high = sorted((amount * LOOSE_SHARE[0], amount * LOOSE_SHARE[1]))
            near = next((event for event in events if not event["used"] and event["label"] == label
                         and day <= event["day"] <= row["balance_date"] and low <= event["amount"] <= high), None)
            if near is not None:
                near["used"] = True
                continue
        item = entry(label); item["settled"] += amount; item["settlement_count"] += 1
    accounts = {}
    total = Fraction(0)
    for label, item in sorted(found.items()):
        stale = by_label[label]["balance_date"] < limit
        settled, settlements = (Fraction(0), 0) if stale else (item["settled"], item["settlement_count"])
        unestimated = item["settlement_count"] if stale else 0
        delta = item["moved"] + settled
        if delta == 0 and not settlements and not unestimated:
            continue
        estimated = bool(settlements or item["movement_count"])
        accounts[label] = {"provisional_balance_decimal": amount_text_v1(exact_amount_v1(by_label[label]["balance_decimal"]) + delta) if estimated else None,
                           "settlement_count": settlements, "movement_count": item["movement_count"] if estimated else 0,
                           "unestimated_count": unestimated}
        if estimated:
            total += delta
    return {"accounts": accounts, "delta": total}


__all__ = ["CASH_ACCOUNT_TYPES", "MAX_GAP_DAYS", "MIN_LEARNED", "VALUTA_DAYS", "cash_scope_v1", "match_settlements_v1", "provisional_cash_v1", "read_accounts_v1", "read_ledger_v1"]
