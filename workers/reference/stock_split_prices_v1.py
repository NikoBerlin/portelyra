"""Kurse vor einem Aktiensplit in den Stuecken ihres Tages (#451, rc.370). Nur Rechnung beim Lesen; schreibt nichts.

Bestaende stehen bis zum Stichtag eines Splits in alten Stuecken (wie im Beleg), danach in neuen. Ein Kurs der Anbieter ist nach
dem Split rueckwirkend bereinigt - aber nur, wenn er nach dem Stichtag abgerufen wurde. Was vorher taeglich abgerufen wurde,
bleibt der Kurs seines Tages. Beispiel: ein Split 3:1, ganz nach dem Split abgerufen - die Kurse vor dem
Stichtag stehen mit rund einem Drittel des damaligen Kurses. Die Markierung "split_adjusted_close" taugt nicht als Urteil: Sie traegt
auch Tage nach dem Split, und fortgeschriebene Wochenendtage tragen sie nicht.

Regel: Der Kurs eines Tages vor dem Stichtag gilt als bereinigt, wenn die Beobachtung, auf der er beruht (bei fortgeschriebenen
Tagen der Quelltag), am oder nach dem Stichtag abgerufen wurde. Dann wird er mit dem Verhaeltnis neu : alt multipliziert und steht
wieder je altem Stueck - Wert = Menge im Beleg x Kurs je Stueck dieses Tages. Mehrere Splits wirken je fuer sich.

Nur Splits fuer alle Konten: Ein Split nur auf einem Konto hiesse zwei Stueckelungen eines Assets zugleich; dafuer gibt es keinen
gemeinsamen Kurs. Ohne Split oder ohne Speicher aendert sich nichts.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from migrations.reference.daily_market_history_v1 import MarketHistoryContext, read_daily_market_history_v1
from migrations.reference.stock_split_v1 import splits_for_fifo_v1

MARKET_STORE = ("daily-market-history-v1", "daily-market-history.sqlite")
VALUATION_STORE = ("market-valuation-state-v1", "valuation-state.sqlite")


def _decimal_text(value: Fraction) -> str:
    """Exakt, wo endlich; sonst auf 18 Nachkommastellen gerundet (Kurse, nicht Betraege)."""
    with localcontext() as context:
        context.prec = 80
        quotient = Decimal(value.numerator) / Decimal(value.denominator)
        if quotient * value.denominator != value.numerator:
            quotient = quotient.quantize(Decimal(1).scaleb(-18), rounding=ROUND_HALF_EVEN)
        text = format(quotient.normalize(), "f")
    return text


class SplitPriceAdjusterV1:
    """Rechnet bewertete Tage vor einem Split auf die Stuecke ihres Tages um. Leer, wenn es keinen Split fuer alle Konten gibt."""

    def __init__(self, data_space: str | Path, context: Any) -> None:
        self.space = Path(data_space)
        self.context = context
        try:
            splits = splits_for_fifo_v1(self.space, context)
        except Exception:  # noqa: BLE001 - ohne lesbaren Speicher wie ohne Split; der FIFO-Stand meldet den Fehler
            splits = []
        self.splits: dict[str, list[tuple[str, Fraction]]] = {}
        for row in splits:
            if row["account_ref"] is None:
                self.splits.setdefault(row["asset_ref"], []).append(
                    (row["effective_local_date"], Fraction(int(row["ratio_numerator"]), int(row["ratio_denominator"]))))
        self._retrieved: dict[str, dict[str, str]] = {}
        self._listing: dict[str, str] | None = None

    def __bool__(self) -> bool:
        return bool(self.splits)

    def _listings(self) -> dict[str, str]:
        if self._listing is None:
            path = self.space / VALUATION_STORE[0] / VALUATION_STORE[1]
            self._listing = {}
            if path.is_file():
                connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                try:
                    self._listing = {row[0]: row[1] for row in connection.execute("SELECT scope_ref, listing_ref FROM valuation_scope")}
                finally:
                    connection.close()
        return self._listing

    def _retrieved_at(self, listing_ref: str, last_split: str) -> dict[str, str]:
        """Je Handelstag der Notierung, wann seine Beobachtung abgerufen wurde - bis zum letzten Split."""
        if listing_ref not in self._retrieved:
            store = self.space / MARKET_STORE[0] / MARKET_STORE[1]
            reader = MarketHistoryContext(self.context.tenant_id, self.context.user_id, self.context.data_space_id, "portfolio_reader",
                                          "portfolio_worker")
            try:
                days = read_daily_market_history_v1(store, reader, listing_ref, "1990-01-01", last_split)["days"]
            except Exception:  # noqa: BLE001 - ohne Kursreihe kein Urteil: dann gilt der Kurs als roh
                days = []
            self._retrieved[listing_ref] = {row["trading_date"]: row["retrieved_at_utc"] for row in days if row.get("retrieved_at_utc")}
        return self._retrieved[listing_ref]

    def factor(self, asset_id: str, scope_ref: str | None, trading_date: str, source_date: str | None) -> Fraction:
        """Das Produkt der Verhaeltnisse aller spaeteren Splits, fuer die der Kurs dieses Tages schon bereinigt ist."""
        splits = self.splits.get(asset_id)
        if not splits or scope_ref is None:
            return Fraction(1)
        later = [(day, ratio) for day, ratio in splits if day > trading_date]
        if not later:
            return Fraction(1)
        listing = self._listings().get(scope_ref)
        if listing is None:
            return Fraction(1)
        retrieved = self._retrieved_at(listing, max(day for day, _ in splits)).get(source_date or trading_date)
        if retrieved is None:
            return Fraction(1)
        result = Fraction(1)
        for day, ratio in later:
            if retrieved[:10] >= day:
                result *= ratio
        return result

    def adjust(self, row: dict[str, Any], scope_ref: str | None, trading_date: str) -> dict[str, Any]:
        """Ein bewerteter Tag (Spalten wie VALUED_COLUMNS) mit Kurs je Stueck dieses Tages. Unveraendert ohne Split davor."""
        factor = self.factor(row.get("asset_id"), scope_ref, trading_date, row.get("price_source_date"))
        if factor == 1:
            return row
        adjusted = dict(row)
        if row.get("target_numerator") is not None and row.get("target_denominator") is not None:
            exact = Fraction(int(row["target_numerator"]), int(row["target_denominator"])) * factor
            adjusted["target_numerator"], adjusted["target_denominator"] = str(exact.numerator), str(exact.denominator)
            adjusted["target_decimal"] = _decimal_text(exact)
        elif row.get("target_decimal") is not None:
            adjusted["target_decimal"] = _decimal_text(Fraction(Decimal(row["target_decimal"])) * factor)
        if row.get("effective_price") is not None:
            adjusted["effective_price"] = _decimal_text(Fraction(Decimal(row["effective_price"])) * factor)
        return adjusted


def split_price_adjuster_v1(data_space: str | Path, context: Any) -> SplitPriceAdjusterV1:
    return SplitPriceAdjusterV1(data_space, context)


__all__ = ["SplitPriceAdjusterV1", "split_price_adjuster_v1"]
