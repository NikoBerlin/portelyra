"""Portelyra-Leser bsdex: Krypto-Export (statement_reader_v1, Aufruf read_text/detect/combine_rows).

Erzeugt aus dem bisherigen Kernmodul (rc.375) ohne Aenderung der Leselogik. Liefert die Zeilen einer Datei; Paarung von
Transfers ueber Boersen hinweg und Buchung bleiben im Kern.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import re
from typing import Any, Mapping, Sequence

from reader_cash import (
    BSDEX_WINDOW, bsdex_assign_executions_v1, bsdex_execution_days_v1, bsdex_history_coverage_v1, bsdex_history_executions_v1,
    bsdex_unassigned_reason_v1,
)
from portelyra_reader_sdk_v1 import (
    CryptoSheet,
    BERLIN,
    UTC,
    COIN_NAMES as _NAMES,
    decimal_or_none as _dec,
    crypto_number as _number,
    parse_time as _parse_time,
    plain_or_none as _plain,
    crypto_row_key as _row_key,
    csv_dict_rows as _rows,
    crypto_ticker as _ticker,
)


SOURCES = {"bsdex": {"zone": "Europe/Berlin"}}


def _Sheet(source: str, file_name: str) -> CryptoSheet:
    return CryptoSheet(source, file_name, SOURCES[source]["zone"])


_SIGNATURE = frozenset({"Transaktionstyp", "Kryptowährung", "Betrag", "Erstellt", "Zieladresse", "Sendeadresse"})


def _detect_format(text: str) -> bool:
    """Wie die bisherige Formaterkennung: eine Kopfzeile unter den ersten 30, die alle Spalten des Formats nennt."""
    for line in text.lstrip("\ufeff").splitlines()[:30]:
        delimiter = max(",;\t", key=line.count)
        if _SIGNATURE <= {cell.strip().strip('"') for cell in line.split(delimiter)}:
            return True
    return False


def _four_digit_year(moment: datetime | None) -> datetime | None:
    """Ein Jahr vor 1000 ("02.11.0023" aus gekippten Bytes) schriebe die Zeile ohne vierstelliges Jahr, und der Kern verwuerfe den
    ganzen Export; so eine Zeit gilt als unlesbar (Selbsttest rc.379)."""
    return None if moment is None or moment.year < 1000 else moment


def _bsdex(text: str, file_name: str) -> dict[str, Any]:
    sheet = _Sheet("bsdex", file_name)
    local = lambda value: _four_digit_year(_parse_time(value, "%d.%m.%Y, %H:%M", BERLIN))
    for number, row in sheet.numbered(_rows(text)):
        amount_text = (row.get("Betrag") or "").replace("\xa0", " ")
        unit = re.search(r"([A-Za-z]{2,10})\s*$", amount_text)
        name = (row.get("Kryptowährung") or "").strip().lower()
        ticker = _ticker(unit.group(1)) if unit else _NAMES.get(name, _ticker(name))
        if len(ticker) > 40:   # kein Coin, sondern verrutschte Zellen eines beschaedigten Exports (Selbsttest rc.379): Zeile unvollstaendig
            ticker = ""
        operation, side = row.get("Operation Type", ""), row.get("Seite", "")
        if operation == "Staking Reward":
            sheet.skip("crypto_reward"); continue
        if operation in ("Staking", "Unstaking"):
            # Umbuchung ins Staking zum Zeitpunkt des Auftrags ("Erstellt"; abgeschlossen ist sie Tage spaeter) - so gebucht
            sheet.add(number, "main", local(row.get("Erstellt") or row.get("Completed At", "")), ticker, "internal_staking" if operation == "Staking" else "internal_unstaking",
                      _number(amount_text)); continue
        if operation:
            sheet.skip("crypto_unsupported"); continue
        if side in ("Kaufen", "Verkaufen"):
            # Spaltennamen des Exports: "Ausgeführter Gesamtbetrag" traegt die Menge in Coin, "Gefüllt" den Kurswert in EUR.
            # Es zaehlt nur, was ausgefuehrt ist (Festlegung 26.10.2026, rc.326): ohne ausgefuehrte Menge ist der Auftrag ohne Belang;
            # storniert mit Teilausfuehrung zaehlt dieser Teil; offen mit Teilausfuehrung wartet er auf seinen Abschluss.
            status, quantity = row.get("Bestellstatus"), _number(row.get("Ausgeführter Gesamtbetrag"))
            if status != "Geschlossen" and not quantity:
                sheet.skip("crypto_order_open" if status == "Offen" else "crypto_cancelled"); continue
            if status == "Offen":
                sheet.skip("crypto_order_partly_open"); continue
            signed = None if quantity is None else (abs(quantity) if side == "Kaufen" else -abs(quantity))
            # Ausgefuehrt ist der Auftrag zu "Finalisiert am" (in neueren Exporten bei allen geschlossenen Auftraegen;
            # aeltere Exporte nennen nur "Erstellt" = Anlage, ein Limit-Auftrag kann Monate spaeter ausgefuehrt sein). Ein stornierter
            # endet mit "Storniert"; gebucht wird er zu seiner letzten Ausfuehrung (siehe _bsdex_exact).
            cancelled = status != "Geschlossen"
            executed = row.get("Finalisiert am") or (row.get("Storniert") if cancelled else "")
            eur, eur_fee = _number(row.get("Gefüllt")), _number(row.get("Transaktionsentgelt")) or Decimal(0)
            if (eur is not None and eur < 0) or eur_fee < 0:   # Kurswert und Entgelt sind nie negativ: Zeile verstuemmelt (Selbsttest rc.379)
                sheet.skip("crypto_unreadable_row", number, "eur" if eur is not None and eur < 0 else "eur_fee", "negative"); continue
            sheet.add(number, "main", local(executed or row.get("Erstellt", "")), ticker, "trade" if executed else "order", signed, eur=eur,
                      eur_fee=eur_fee, window_from=local(row.get("Erstellt", "")) if executed else None,
                      at_last_execution=cancelled); continue
        if "€" in (row.get("Betrag") or "") or row.get("IBAN"):
            sheet.skip("crypto_fiat"); continue
        if not (row.get("Sendeadresse") or row.get("Zieladresse")):
            sheet.skip("crypto_unsupported"); continue
        # Ein- oder Auszahlung: der Export nennt keine Richtung; sie folgt aus dem Gegenstueck in einem Wallet-Export.
        at = local(row.get("Finalisiert am") or row.get("Erstellt", ""))
        sheet.add(number, "main", at, ticker, "move_unknown", _number(amount_text), address=row.get("Zieladresse") or "",
                  transaction_id="")
    return sheet.result()

def _bsdex_exact(rows: list[dict[str, Any]], executions: Sequence[Mapping[str, Any]]) -> None:
    """BSDEX je Order auf den Cent (rc.325): Kurswert und Gebuehr sind die Summe ihrer Ausfuehrungen aus der Transaktionshistorie,
    zugeordnet wie im Cash-Import. Eine Order ohne ihre Ausfuehrungen bleibt offen - der gerundete Betrag des Exports wird nie gebucht
    (Festlegung 26.10.2026). Laeuft eine Order ueber mehrere Tage, wird sie je Ausfuehrungstag ein Trade (rc.327), zur Zeit des
    letzten Teils dieses Tages - wie die Euro-Bewegung im Cash-Import."""
    trades = [row for row in rows if row["source"] == "bsdex" and row["kind"] == "trade"]
    if not trades:
        return
    moment = lambda text: datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    orders = [{"side": "buy" if _dec(row["quantity"]) > 0 else "sell", "quantity": abs(_dec(row["quantity"])), "filled": _dec(row["eur"]) or Decimal(0),
               "from": moment(row.get("window_from_utc") or row["at_utc"]) - BSDEX_WINDOW, "to": moment(row["at_utc"]) + BSDEX_WINDOW} for row in trades]
    assigned = bsdex_assign_executions_v1(orders, list(executions))
    used = {fill["id"] for chosen in assigned.values() for fill in chosen}
    coverage = bsdex_history_coverage_v1([fill["at"] for fill in executions])
    split: dict[int, list[dict[str, Any]]] = {}
    for position, row in enumerate(trades):
        chosen = assigned.get(position)
        if chosen is None:
            # Offen mit Grund, so genau wie moeglich (Festlegung 08.11.2026); den Text setzt der Kern.
            why = bsdex_unassigned_reason_v1(orders[position], executions, used, coverage)
            row["kind"], row["unpriced_reason"] = "unpriced_trade", why["reason"]
            if why["reason"] == "amount_differs":
                row["executions_eur"], row["executions_fee"] = _plain(why["eur"]), _plain(why["fee"])
            if why["reason"] == "history_outdated":
                row["history_until"] = why["until"]
            if why["reason"] == "history_missing":
                row["history_year"] = str(why["year"])
            continue
        days = bsdex_execution_days_v1(chosen)
        if len(days) == 1:
            row["eur"] = _plain(sum((fill["eur"] for fill in chosen), Decimal(0)))
            row["eur_fee"] = _plain(sum((fill["fee"] for fill in chosen), Decimal(0)))
            if row.get("at_last_execution"):
                row["at_utc"] = max(fill["at"] for fill in chosen).strftime("%Y-%m-%dT%H:%M:%SZ")
            continue
        sign = Decimal(1) if _dec(row["quantity"]) > 0 else Decimal(-1)
        parts = []
        for _day, group in sorted(days.items()):
            part = {**row, "quantity": _plain(sign * sum((fill["quantity"] for fill in group), Decimal(0))),
                    "eur": _plain(sum((fill["eur"] for fill in group), Decimal(0))), "eur_fee": _plain(sum((fill["fee"] for fill in group), Decimal(0))),
                    "at_utc": max(fill["at"] for fill in group).strftime("%Y-%m-%dT%H:%M:%SZ")}
            part["row_key"] = _row_key(part)
            parts.append(part)
        split[id(row)] = parts
    if split:
        rows[:] = [part for row in rows for part in split.get(id(row), [row])]


def _read_history(text: str, file_name: str) -> dict[str, Any]:
    """BSDEX-Transaktionshistorie je Jahr (rc.325): bucht nichts, belegt aber den genauen Euro-Betrag jeder Order des Exports."""
    executions = bsdex_history_executions_v1(text.encode("utf-8"), file_name)
    if executions is None:
        return {"status": "not_importable", "reason_code": "unknown_document"}
    return {"status": "multi", "candidates": [], "row_reasons": {}, "evidence": {"bsdex_executions": executions}}


def _detect_history(text: str) -> bool:
    return bsdex_history_executions_v1(text.encode("utf-8"), "") is not None


def _combine_rows(batch: dict[str, Any]) -> list[dict[str, Any]]:
    """Export und Jahreshistorie zusammen lesen: Kurswert und Gebuehr je Order aus ihren Ausfuehrungen, je Ausfuehrungstag ein Trade."""
    rows = list(batch["rows"])
    _bsdex_exact(rows, batch.get("executions") or [])
    return rows


READERS = {"bsdex_history_v1": _read_history, "bsdex_crypto_v1": _bsdex}
DETECTORS = {"bsdex_history_v1": _detect_history, "bsdex_crypto_v1": _detect_format}
COMBINERS = {"bsdex_crypto_v1": _combine_rows}
