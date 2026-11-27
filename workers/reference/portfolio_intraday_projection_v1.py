"""Das fluide Portfoliobild: dieselbe Rechnung wie der Stichtags-Snapshot, mit aktuellen Kursen.

Der fluide Snapshot rechnet mit derselben Mechanik wie der Stichtags-Snapshot;
nur die Marktdatenbasis ist eine andere: aktuelle Kurse statt der Tageskurse.

Bis rc.241 rechnete die Momentaufnahme auf eigenem Weg: Eigene Bewertungen
standen neben ihrer Summe, Cash und Gesamtvermoegen fehlten. Zwei Zahlen
aehnlicher Groesse aus zwei Regeln. Dieses Modul rechnet deshalb nichts selbst.
Es reicht der Projektion des Stichtags-Snapshots eine Kursquelle: die zuletzt
abgerufenen Kurse aus `intraday_quote`. Bestand, eigene Bewertung,
Eigentuemerwahl, Cash je Konto, Summen und die Form der Ausgabe sind dieselben.

Was das Bild vom versiegelten Stichtags-Snapshot unterscheidet, steht dabei:
Es ist nicht veroeffentlicht, traegt den Zeitpunkt des Abrufs und zaehlt, wie
viele Kurse die Quelle am Stichtag selbst beobachtet hat und wie viele aelter
sind. Ein Kurs vom letzten Handelstag ist ein Kurs - aber kein aktueller.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

from migrations.reference.asset_valuation_facts_v1 import OWNER_CHOICE_METHODS
from migrations.reference.desktop_product_asset_activity_v1 import DesktopProductAssetActivityContextV1
from workers.reference.portfolio_snapshot_freshness_v1 import (
    STATE_AREA,
    STATE_NAME,
    _market_levels,
    _worst,
)
from workers.reference.portfolio_snapshot_projection_v1 import (
    TARGET_CURRENCY,
    project_portfolio_snapshot_v1,
)

SNAPSHOT_KIND = "intraday"
# Bis zu diesem Alter beim Abruf gilt ein Kurs als aktuell beobachtet.
RECENT_SECONDS = 3600


class _IntradayPrices:
    """Die zuletzt abgerufenen Kurse als Kursquelle der Projektion.

    Gelesen wird einmal je Bild: Frische und Positionen sehen denselben Stand,
    auch wenn waehrenddessen ein neuer Abruf laeuft.
    """

    undated_reason = "kein aktueller Kurs abgerufen"

    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] | None = None

    def _read(self, data_space: Path) -> list[dict[str, Any]]:
        if self._rows is None:
            path = data_space / STATE_AREA / STATE_NAME
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            try:
                rows = [dict(row) for row in connection.execute(
                    "SELECT s.scope_ref,s.asset_id,s.provider_symbol,s.quote_currency,s.pair_ref,"
                    "q.requested_at_utc,q.basis,q.observed_at_utc,q.as_of_date,q.native_decimal,"
                    "q.fx_rate,q.fx_basis,q.target_decimal,q.target_numerator,q.target_denominator "
                    "FROM valuation_scope s LEFT JOIN intraday_quote q USING(scope_ref) ORDER BY s.asset_id")]
                # Je Asset der Bereich, der heute gilt (#474) - ein alter Bereich nach einem Wechsel wird weder abgefragt noch
                # beurteilt (sonst stuende er ohne Kurs als "Bewertung offen" da).
                from workers.reference.portfolio_snapshot_freshness_v1 import current_symbols_v1, preferred_scope_refs_v1, scope_windows_v1
                preferred = set(preferred_scope_refs_v1(scope_windows_v1(connection), current_symbols_v1(data_space)).values())
                self._rows = [{key: value for key, value in row.items() if key != "scope_ref"} for row in rows if row["scope_ref"] in preferred]
            finally:
                connection.close()
        return self._rows

    def market_levels(self, data_space: Path, as_of_date: str, held: set[str],
                      methods: dict[str, str] | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        methods = methods or {}
        if not (data_space / STATE_AREA / STATE_NAME).is_file():
            # Ohne Stand gibt es keine Bereiche und damit nichts abzurufen -
            # dieselbe Aussage wie beim Stichtags-Snapshot.
            return _market_levels(data_space, as_of_date, held, methods)
        scope_rows: list[dict[str, Any]] = []
        needed: set[str] = set()
        proven: set[str] = set()
        unavailable: set[str] = set()
        for row in self._read(data_space):
            if row["requested_at_utc"] is None:
                status, reason = "valuation_pending", "no_intraday_quote"
            elif row["target_decimal"] is None:
                status, reason = "source_gap", "quote_unavailable"
            else:
                status, reason = "complete", "quote_" + row["basis"]
            is_held = row["asset_id"] in held
            scope_rows.append({"asset_id": row["asset_id"], "provider_symbol": row["provider_symbol"],
                               "status": status, "reason_code": reason, "held": is_held})
            if is_held and row["pair_ref"] is not None:
                needed.add(row["pair_ref"])
                if status == "complete":
                    proven.add(row["pair_ref"])
                elif row["fx_basis"] == "unavailable":
                    unavailable.add(row["pair_ref"])
        relevant = [row for row in scope_rows if row["held"]]
        uncovered = sorted(held - {row["asset_id"] for row in relevant})
        by_owner_choice = [asset for asset in uncovered if methods.get(asset) in OWNER_CHOICE_METHODS]
        missing = [asset for asset in uncovered if methods.get(asset) not in OWNER_CHOICE_METHODS]
        pair_rows = []
        for pair_ref in sorted(needed):
            if pair_ref in unavailable:
                status, reason = "source_gap", "rate_unavailable"
            elif pair_ref in proven:
                status, reason = "complete", "rate_effective_in_valuation"
            else:
                status, reason = "valuation_pending", "no_intraday_quote"
            pair_rows.append({"pair_ref": pair_ref, "status": status, "reason_code": reason, "needed": True})
        quoted = any(row["requested_at_utc"] is not None for row in self._read(data_space))
        return (_worst("market_history", relevant, missing), _worst("fx_history", pair_rows, []),
                {"scope_count": len(scope_rows), "held_scope_count": len(relevant),
                 "held_without_scope": missing, "held_by_owner_choice": by_owner_choice,
                 "scopes": scope_rows, "pairs": pair_rows,
                 "latest_valued_date": as_of_date if quoted else None})

    def valued(self, data_space: Path, as_of_date: str) -> tuple[dict[str, dict[str, Any]], set[str]]:
        """Je Asset der abgerufene Kurs in der Gestalt eines Bewertungstags."""
        if not (data_space / STATE_AREA / STATE_NAME).is_file():
            return {}, set()
        rows = self._read(data_space)
        valued: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row["target_decimal"] is None:
                continue
            source_date = row["as_of_date"] or as_of_date
            valued[row["asset_id"]] = {
                "asset_id": row["asset_id"], "provider_symbol": row["provider_symbol"],
                "quote_currency": row["quote_currency"],
                "status": "intraday_quote",
                # Ein Rueckfall auf den letzten Tagesschluss ist ein Ersatzwert
                # und heisst so - wie ein fortgeschriebener Kurs im Tagesbild.
                "valuation_status": "complete" if row["basis"] == "intraday" else "substituted",
                "target_decimal": row["target_decimal"], "target_numerator": row["target_numerator"],
                "target_denominator": row["target_denominator"],
                "effective_price": row["native_decimal"],
                "price_basis": row["basis"], "price_source_date": source_date,
                "price_age_days": max(0, (date.fromisoformat(as_of_date) - date.fromisoformat(source_date)).days),
                "fx_rate": row["fx_rate"], "fx_basis": row["fx_basis"],
                "substitution_used": row["basis"] != "intraday",
                "price_observed_at_utc": row["observed_at_utc"],
            }
        return valued, {row["asset_id"] for row in rows}

    def summary(self, data_space: Path, as_of_date: str, held: set[str]) -> dict[str, Any]:
        """Wie aktuell die Kurse der gehaltenen Positionen sind - gezaehlt, nicht behauptet."""
        if not (data_space / STATE_AREA / STATE_NAME).is_file():
            rows: list[dict[str, Any]] = []
        else:
            rows = [row for row in self._read(data_space) if row["requested_at_utc"] is not None]
        mine = [row for row in rows if row["asset_id"] in held]
        observed = sorted(row["observed_at_utc"] for row in mine if row["observed_at_utc"])

        def recent(row: dict[str, Any]) -> bool:
            # Hoechstens eine Stunde vor dem Abruf beobachtet. Gemessen wird am
            # Zeitpunkt, nicht am Kalendertag: Kurz nach Mitternacht waere ein
            # Kurs von vor zehn Minuten sonst "von gestern".
            if row["basis"] != "intraday" or not row["observed_at_utc"]:
                return False
            asked = datetime.strptime(row["requested_at_utc"], "%Y-%m-%dT%H:%M:%SZ")
            seen = datetime.strptime(row["observed_at_utc"], "%Y-%m-%dT%H:%M:%SZ")
            return (asked - seen).total_seconds() <= RECENT_SECONDS

        return {
            "requested_at_utc": max((row["requested_at_utc"] for row in rows), default=None),
            "quote_count": len(rows),
            "held_quote_count": len(mine),
            "intraday_count": sum(row["basis"] == "intraday" for row in mine),
            "last_close_count": sum(row["basis"] == "last_close" for row in mine),
            "unavailable_count": sum(row["basis"] == "unavailable" for row in mine),
            # Wie aktuell die abgerufenen Kurse wirklich sind: Ein Kurs vom
            # letzten Handelstag ist gueltig, aber kein Bild von jetzt.
            "observed_within_hour_count": sum(recent(row) for row in mine),
            "observed_earlier_count": sum(1 for row in mine if row["basis"] == "intraday" and not recent(row)),
            "oldest_observed_at_utc": observed[0] if observed else None,
            "newest_observed_at_utc": observed[-1] if observed else None,
        }


def _portfolio_facts(data_space: Path, context: DesktopProductAssetActivityContextV1) -> tuple[str | None, str]:
    """Bezeichnung und Basiswaehrung wie im veroeffentlichten Snapshot - soweit eindeutig."""
    try:
        from workers.reference.portfolio_snapshot_publication_v1 import _portfolio
        _, label, currency = _portfolio(data_space, context)
        return label, currency
    except Exception:
        return None, TARGET_CURRENCY


def project_portfolio_intraday_snapshot_v1(
    data_space_path: str | Path,
    context_value: Any,
    as_of_date: str,
    canonical_path: str | Path | None = None,
) -> dict[str, Any]:
    """Das fluide Bild zum heutigen Tag. Kein Abruf, nichts wird geschrieben.

    Die Kurse stammen aus dem letzten Abruf (`snapshot_intraday_v1`); dieser
    Leser ruft selbst nichts ab. Ohne einen Abruf steht jede ueber den Markt
    bewertete Position als offen da - mit dem Grund, nicht mit einer Null.
    """
    source = _IntradayPrices()
    value = project_portfolio_snapshot_v1(data_space_path, context_value, as_of_date, canonical_path,
                                         price_source=source)
    data_space = Path(data_space_path)
    held = {row["asset_id"] for row in value["positions"]} | {row["asset_id"] for row in value["excluded_positions"]}
    quotes = source.summary(data_space, value["as_of_date"], held)
    label, currency = _portfolio_facts(data_space, context_value)
    return {
        **value,
        "portfolio_intraday_projection_version": 1,
        "snapshot_kind": SNAPSHOT_KIND,
        # Dieselben Felder wie die Sicht auf den veroeffentlichten Snapshot, damit
        # Anzeige und spaetere Auswertungen beide Bilder gleich lesen.
        "snapshot_status": "complete" if value["market_value_complete"] else "partial",
        "portfolio_label": label,
        "base_currency": currency,
        "completed_at_utc": quotes["requested_at_utc"],
        "status": "available" if quotes["quote_count"] else "absent",
        "quotes": quotes,
        "published": False,
    }


__all__ = [
    "SNAPSHOT_KIND",
    "project_portfolio_intraday_snapshot_v1",
]
