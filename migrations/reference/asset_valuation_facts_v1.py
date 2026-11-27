"""Was ueber ein Asset bekannt ist, wenn kein Marktwert vorliegt.

Stammdaten, Anbieterzuordnung, der Grund fuer eine fehlende Marktbewertung und
der aus eigenen Buchungen hergeleitete Wert je Einheit. Alle vier beantworten
dieselbe Frage aus verschiedenen Richtungen: Warum steht hier keine Zahl vom
Markt, und was laesst sich stattdessen sagen.

Rein lesend. Das Modul ist neutral: Es gehoert weder dem fluechtigen
Intraday-Pfad noch dem systematischen Snapshot-Pfad, sondern beiden. Vorher lagen
diese Helfer im Intraday-Modul, und der systematische Pfad importierte von dort -
funktional harmlos, aber eine Kopplung, ueber die frueher oder spaeter auch ein
Datenzugriff gewandert waere (Festlegung 27.09.2026, #373).
"""
from __future__ import annotations

from fractions import Fraction

import sqlite3
from pathlib import Path
from typing import Any, Mapping

from migrations.reference.exact_amount_v1 import amount_text_v1, exact_amount_v1


def asset_master_v1(data_space_path: str | Path, context: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    """Name, Art und Bewertungsmethode je Asset - aus den Stammdaten.

    Ohne sie steht in der Liste eine Kennung wie `ast_0123456789ab`, und niemand weiss, was gemeint ist.
    """
    try:
        from migrations.reference.desktop_product_asset_activity_v1 import (
            DesktopProductAssetActivityContextV1,
            read_desktop_product_asset_activity_binding_v1,
        )
        binding = read_desktop_product_asset_activity_binding_v1(
            data_space_path,
            DesktopProductAssetActivityContextV1(context["tenant_id"], context["user_id"],
                                                 context["data_space_id"], "desktop_owner", "desktop_owner"))
        if binding.get("status") == "absent" or not binding.get("ledger_path"):
            return {}
        connection = sqlite3.connect("file:" + str(binding["ledger_path"]) + "?mode=ro", uri=True)
    except Exception:
        return {}
    try:
        return {row[0]: {"asset_name": row[1], "asset_type": row[2], "valuation_method": row[3]}
                for row in connection.execute(
                    "SELECT asset_id, display_name, asset_type, valuation_method FROM current_asset_revision")}
    except Exception:
        return {}
    finally:
        connection.close()


def provider_ids_v1(data_space_path: str | Path) -> dict[str, str]:
    """Je Asset die Anbieter-Kennung seiner Tageskurs-Zuordnung - nur fuer die Anzeige (rc.384, #495). Bewusst getrennt von
    provider_mapping_v1: Dessen Ergebnis geht vollstaendig in den Abdruck der Tageshistorie ein, ein neues Feld dort liesse sie
    einmal ganz neu rechnen. Bei mehreren Zuordnungen gilt die aktive mit der hoechsten Revision."""
    path = Path(data_space_path) / "canonical.sqlite"
    if not path.is_file():
        return {}
    try:
        connection = sqlite3.connect("file:" + str(path) + "?mode=ro", uri=True)
    except Exception:
        return {}
    try:
        result: dict[str, str] = {}
        for asset_id, provider_id in connection.execute(
                "SELECT asset_id, provider_id FROM provider_mapping WHERE capability='daily_history' ORDER BY enabled, revision"):
            result[str(asset_id)] = str(provider_id)
        return result
    except Exception:
        return {}
    finally:
        connection.close()


def provider_mapping_v1(data_space_path: str | Path) -> dict[str, dict[str, Any]]:
    """Ob ein Asset ueberhaupt eine Anbieterzuordnung hat - und in welchem Zustand.

    Das unterscheidet "nicht bewertbar" von "noch nicht freigegeben": Ein Papier ohne Kursquelle hat keine Zuordnung, ein Aktienwert mit unverifizierter Zuordnung ist eine offene Aufgabe (#283).
    """
    path = Path(data_space_path) / "canonical.sqlite"
    if not path.is_file():
        return {}
    try:
        connection = sqlite3.connect("file:" + str(path) + "?mode=ro", uri=True)
    except Exception:
        return {}
    try:
        return {row[0]: {"provider_symbol": row[1], "verification_status": row[2],
                         "enabled": bool(row[3])}
                # Feste Reihenfolge (rc.385): Bei mehreren Zuordnungen eines Assets gewinnt die aktive Tageskurs-Zuordnung mit der
                # hoechsten Revision, nicht die zufaellig zuletzt gelesene. Mit einer Zuordnung je Asset ist
                # das Ergebnis gleich - es geht in den Abdruck der Tageshistorie ein.
                for row in connection.execute(
                    "SELECT asset_id, provider_symbol, verification_status, enabled FROM provider_mapping "
                    "ORDER BY capability = 'daily_history', enabled, revision, provider_id")}
    except Exception:
        return {}
    finally:
        connection.close()


def why_no_market_value_v1(master: Mapping[str, Any], mapping: Mapping[str, Any] | None) -> str:
    # Eine bewusst gewaehlte Methode ist kein Mangel: Ein Derivat auf eigene
    # Kursangaben hat zu Recht keine Anbieterzuordnung.
    method = master.get("valuation_method")
    if method and method != "external_market":
        return "nach Eigentümerwahl nicht über den Markt bewertet (" + str(method) + ")"
    if mapping is None:
        return "keine Anbieterzuordnung"
    status = mapping.get("verification_status")
    if status == "disabled":
        return "Anbieterzuordnung deaktiviert (" + str(mapping.get("provider_symbol")) + ")"
    if status != "verified":
        return "Anbieterzuordnung noch nicht geprüft (" + str(mapping.get("provider_symbol")) + ")"
    if not mapping.get("enabled"):
        return "Anbieterzuordnung abgeschaltet (" + str(mapping.get("provider_symbol")) + ")"
    return "geprüfte Zuordnung, aber noch keine Kursreihe abgerufen"


def trade_unit_value_v1(data_space_path: str | Path, context: Mapping[str, str],
                        asset_id: str, holding: Mapping[str, Any], as_of: str) -> tuple[str | None, str]:
    """Ein aus Buchungen hergeleiteter Wert je Einheit - kein Marktkurs.

    Bevorzugt der zuletzt bestaetigte Stueckpreis, sonst der durchschnittliche
    Anschaffungspreis. Beides stammt aus eigenen Buchungen und ist deshalb mit
    Vorsicht zu lesen: Es sagt, was gezahlt wurde, nicht was der Markt heute
    bietet (Festlegung 26.09.2026, #283).
    """
    try:
        from migrations.reference import trade_price_reference_v1 as trades
        source = trades.read_trade_source(Path(data_space_path), dict(context), asset_id,
                                          "1970-01-01", as_of)
    except Exception:
        source = None
    return _trade_unit_value_from(source, holding)


def _trade_unit_value_from(source: Mapping[str, Any] | None, holding: Mapping[str, Any]) -> tuple[str | None, str]:
    if source is not None and source.get("quote_currency") == "EUR":
        priced = [row for row in source.get("rows", ()) if row.get("value") is not None]
        if priced:
            latest = priced[-1]
            # Ein Split danach (#451): Der Preis galt fuer alte Stuecke; je neuem Stueck ist er durch das Verhaeltnis geteilt.
            through = source["rows"][-1]["date"]
            ratio = Fraction(1)
            for day, numerator, denominator in source.get("splits", ()):
                if latest["date"] < day <= through:
                    ratio *= Fraction(int(numerator), int(denominator))
            if ratio != 1:
                value = amount_text_v1(exact_amount_v1(str(latest["value"])) / ratio)
                return value, "zuletzt bestätigter Stückpreis vom " + str(latest["date"]) + ", umgerechnet nach Split"
            return str(latest["value"]), "zuletzt bestätigter Stückpreis vom " + str(latest["date"])
    average = holding.get("cost_average")
    if isinstance(average, str):
        # Auch der Durchschnitt kann ein exakter Bruch sein; angezeigt wird eine Zahl.
        return amount_text_v1(exact_amount_v1(average)), "durchschnittlicher Anschaffungspreis"
    return None, "kein aus Buchungen herleitbarer Wert"


# Bewertungsarten, mit denen der Eigentuemer ein Asset bewusst nicht ueber den
# Markt bewertet. Sie sind keine Luecke: 'manual' traegt einen eigenen Wert,
# 'transaction_only' traegt bewusst keinen (Festlegung 11.10.2026).
OWNER_CHOICE_METHODS = frozenset({"manual", "transaction_only"})

OWNER_VALUATION_BASES = {
    "owner_recorded_manual_price": "eigene Kursangabe",
    "trade_price_reference": "letzter bestätigter Trade-Stückpreis",
}


# Warum eine eigene Bewertung keinen Wert ergibt - in Worten. Der Code steht
# dahinter, damit eine Rueckfrage ihn nennen kann.
OWNER_VALUATION_REASONS = {
    "no_owner_price_and_no_trade_price": "weder eigene Kursangabe noch bestätigter Trade-Stückpreis vorhanden",
    "trade_price_superseded_by_unclear_booking": "nach dem letzten Trade-Stückpreis liegt eine Buchung, die ihn in Frage stellt",
    "trade_price_currency_differs_from_asset_currency": "der Trade-Stückpreis steht in einer anderen Währung als das Asset; eine eigene Kursangabe ist nötig",
    "owner_valuation_currency_without_rate": "für die Währung des Assets führt der Bewertungsstand am Stichtag keinen Wechselkurs",
    "owner_price_currency_conflict": "die eigene Kursangabe steht in einer anderen Währung als das Asset",
    "owner_valuation_not_configured": "für dieses Asset ist keine eigene Bewertung eingerichtet; es wird über Marktdaten bewertet",
}


def owner_valuation_reason_text_v1(code: str) -> str:
    return OWNER_VALUATION_REASONS.get(code, "eigene Bewertung nicht lesbar") + " (" + str(code) + ")"


def owner_valuation_v1(data_space_path: str | Path, context: Mapping[str, str],
                       asset_id: str, as_of: str) -> dict[str, Any]:
    """Der Wert je Einheit eines Assets mit eigener Bewertung ('manual') am Stichtag.

    Die Bewertungsart ist eine Entscheidung, und ihr Ergebnis ist
    deshalb eine Bewertung, kein Ersatz fuer eine fehlende: zuerst die juengste
    eigene Kursangabe bis zum Stichtag, sonst der zuletzt bestaetigte
    Trade-Stueckpreis (Festlegung 11.10.2026). Herkunft und Tag des
    Preises gehen mit, damit niemand ihn fuer eine Stichtagsnotiz haelt.

    Kein Wert entsteht, wenn es weder Angabe noch Trade-Preis gibt, oder wenn nach
    dem letzten Trade-Preis eine Buchung liegt, die ihn in Frage stellt - ein
    spaeterer Kauf oder Verkauf ohne Stueckpreis, widerspruechliche Preise am
    selben Tag, eine Kapitalmassnahme, eine andere Waehrung. Dann sagt
    'reason_code', woran es liegt. Rein lesend.
    """
    from migrations.reference import manual_price_source_v1 as manual
    from migrations.reference import trade_price_reference_v1 as trades
    space, ctx = Path(data_space_path), dict(context)

    def configuration():
        return trades.read_asset_configuration(space, ctx, asset_id, "manual")[0]

    def entries():
        return manual.read_manual_entries_v1(space, ctx, asset_id)["entries"]

    def source():
        return trades.read_trade_source(space, ctx, asset_id, "1970-01-01", as_of)

    return _owner_valuation_from(configuration, entries, source, as_of)


def _owner_valuation_from(configuration: Any, read_entries: Any, read_source: Any, as_of: str) -> dict[str, Any]:
    """Die Regel der eigenen Bewertung ueber austauschbaren Lesern - je Stichtag frisch gelesen (Snapshot) oder einmal
    gelesen und auf den Stichtag zugeschnitten (Tageshistorie, #473). Die Leser duerfen Ausnahmen werfen."""
    unavailable = lambda reason: {"status": "unavailable", "reason_code": reason}
    try:
        asset = configuration()
    except Exception:
        return unavailable("owner_valuation_not_configured")
    currency = asset["price_currency"]
    try:
        entries = [row for row in read_entries() if row["price_date"] <= as_of]
    except Exception:
        return unavailable("owner_price_entries_unreadable")
    if entries:
        latest = entries[-1]
        if latest["currency"] != currency:
            return unavailable("owner_price_currency_conflict")
        return {"status": "valued", "native_decimal": latest["value_decimal"], "native_currency": currency,
                "price_source_date": latest["price_date"], "price_basis": "owner_recorded_manual_price"}
    try:
        source = read_source()
    except Exception:
        return unavailable("trade_price_source_unreadable")
    priced = [row for row in source["rows"] if row.get("value") is not None]
    if not priced:
        return unavailable("no_owner_price_and_no_trade_price")
    latest = priced[-1]
    later = {reason for day, reason in source["barriers"].items() if day >= latest["date"]}
    if "trade_price_currency_conflict" in later:
        return unavailable("trade_price_currency_differs_from_asset_currency")
    if later:
        return unavailable("trade_price_superseded_by_unclear_booking")
    return {"status": "valued", "native_decimal": str(latest["value"]), "native_currency": currency,
            "price_source_date": latest["date"], "price_basis": "trade_price_reference"}


class ValuationFactsCacheV1:
    """Eigene Bewertung und hergeleiteter Handelswert fuer viele Stichtage aus einmal gelesenen Quellen (Tageshistorie, #473).

    Ergebnisgleich mit owner_valuation_v1 und trade_unit_value_v1: Die Handelsquelle wird je Asset einmal bis 'through'
    gelesen und je Stichtag zugeschnitten - Tageszeilen und Hinderungsgruende haengen nur an Buchungen dieses Tages
    (daily_trade_rows fuellt nicht aus spaeteren Trades auf). Wirft das Lesen ueber den ganzen Zeitraum, wird fuer dieses
    Asset je Stichtag frisch gelesen - so bleibt auch ein Fehler im spaeteren Zeitraum ohne Wirkung auf fruehere Tage."""

    def __init__(self, data_space_path: str | Path, context: Mapping[str, str], through: str) -> None:
        from migrations.reference import manual_price_source_v1 as manual
        from migrations.reference import trade_price_reference_v1 as trades
        self._space, self._ctx, self._through = Path(data_space_path), dict(context), through
        self._manual, self._trades = manual, trades
        self._memo: dict[tuple[str, str], Any] = {}

    def _once(self, key: tuple[str, str], read: Any) -> Any:
        if key not in self._memo:
            try:
                self._memo[key] = ("ok", read())
            except Exception as error:   # wie beim frischen Lesen: der Aufrufer entscheidet, was eine Ausnahme bedeutet
                self._memo[key] = ("error", error)
        state, value = self._memo[key]
        if state == "error":
            raise value
        return value

    def _source(self, asset_id: str, as_of: str) -> dict[str, Any]:
        try:
            whole = self._once(("source", asset_id), lambda: self._trades.read_trade_source(self._space, self._ctx, asset_id, "1970-01-01", self._through))
        except Exception:
            return self._trades.read_trade_source(self._space, self._ctx, asset_id, "1970-01-01", as_of)
        return {**whole, "rows": [row for row in whole["rows"] if row["date"] <= as_of],
                "barriers": {day: reason for day, reason in whole["barriers"].items() if day <= as_of},
                "events": [event for event in whole["events"] if event["local_date"] <= as_of]}

    def trade_unit_value(self, asset_id: str, holding: Mapping[str, Any], as_of: str) -> tuple[str | None, str]:
        try:
            source = self._source(asset_id, as_of)
        except Exception:
            source = None
        return _trade_unit_value_from(source, holding)

    def owner_valuation(self, asset_id: str, as_of: str) -> dict[str, Any]:
        return _owner_valuation_from(
            lambda: self._once(("configuration", asset_id), lambda: self._trades.read_asset_configuration(self._space, self._ctx, asset_id, "manual")[0]),
            lambda: self._once(("entries", asset_id), lambda: self._manual.read_manual_entries_v1(self._space, self._ctx, asset_id)["entries"]),
            lambda: self._source(asset_id, as_of), as_of)


__all__ = [
    "OWNER_CHOICE_METHODS",
    "ValuationFactsCacheV1",
    "OWNER_VALUATION_BASES",
    "asset_master_v1",
    "owner_valuation_reason_text_v1",
    "owner_valuation_v1",
    "provider_mapping_v1",
    "trade_unit_value_v1",
    "why_no_market_value_v1",
]
