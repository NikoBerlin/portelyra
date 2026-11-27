"""Netto-Sicht der Tageshistorie (#481, #483, #494): projizierte Verkaufsgebuehr und Steuer.

Festlegungen (21.10.2026):

- Netto unrealisiert je Tag: Regeln und Saetze des Jahresmoduls (`tax_de_personal_income_tax_projection_v2`, Projektionsart
  `unrealized_snapshot`) auf jeden Tag angewandt - hypothetischer Verkauf je Asset, ein Verlust traegt die Steuer null,
  Fonds nach Teilfreistellung, privates Veraeusserungsgut je Kauflot nur in der Jahresfrist. Am letzten Tag rechnet das
  Modul selbst gegen; weicht es ab, wird Netto nicht veroeffentlicht.
- Netto realisiert: Abrechnung samt Gebuehren minus projizierte Steuer je Ereignis - die konservative Sicht der
  Rechenblaetter (keine Freigrenze, kein Freibetrag, keine Verlustverrechnung).
- Verkaufsgebuehr wie im Abschluss ohne eigene Angabe: Satz aus den eigenen Kaeufen und Verkaeufen des Assets, sonst aus
  denen des Portfolios.
- Projektion (#494): die offenen Lots je Asset mit Gebuehrensatz und Steuersaetzen; die Analyse rechnet daraus nur die
  Kurve fuer einen gewaehlten Kurs.

Fehlt eine Angabe (Einordnung, Satz, Regeln des Jahres), steht der Wert als "nicht verfuegbar" (None), nie als Brutto.
Liest nur. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write. Projektion, keine Steuerberechnung.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Sequence

from migrations.reference.exact_amount_v1 import amount_text_v1, exact_amount_v1

PLUGIN_ID = "tax_de_personal_income_tax_projection_v2"
NET_VERSION = "portfolio_history_net_v1"
SCALE = 10 ** 12
CAPITAL_BUCKETS = ("capital_equity", "capital_general")
PRIVATE_CODE = "de_private_disposal_asset"
# Wie die Klassentabelle des Moduls fuer einen Verkauf: Topf, erlaubte Vorgaenge, Teilfreistellung.
CLASS_MODELS = {
    "de_equity_share": ("capital_equity", ("sell", "dividend"), "zero"),
    "de_capital_instrument": ("capital_general", ("sell", "dividend", "interest"), "zero"),
    "de_cash_interest": ("capital_general", ("interest",), "zero"),
    "de_fund": ("capital_general", ("sell", "dividend"), "asset"),
    PRIVATE_CODE: ("private_disposal", ("sell", "reward"), "zero"),
    "de_other_income_asset": ("other_income", ("reward",), "zero"),
}
FEE_RATE_SCALE = Decimal("0.000001")
# Ereignisse, deren Steuer zum realisierten Ergebnis zaehlt, und solche, deren Steuer die Ertraege mindert.
REALIZED_TYPES = ("sell",)
INCOME_TYPES = ("dividend", "reward", "stock_dividend", "advance_lump_sum", "interest")


def _text(value: Fraction | None) -> str | None:
    return None if value is None else amount_text_v1(value)


def _fraction(value: Any) -> Fraction | None:
    if value is None or value == "":
        return None
    if isinstance(value, Fraction):
        return value
    return exact_amount_v1(str(value))


def dec12(value: Fraction) -> str:
    """Dezimaltext auf zwoelf Stellen (kaufmaennisch zur geraden Ziffer) - das Modul nimmt nur Dezimalzahlen."""
    quantized = (Decimal(value.numerator) / Decimal(value.denominator)).quantize(Decimal("1e-12"), rounding=ROUND_HALF_EVEN) \
        if value.denominator != 1 else Decimal(value.numerator)
    text = format(quantized.normalize(), "f")
    return "0" if text in ("-0", "0E-12") else text


# Gegenprobe: Das Modul rechnet mit den auf zwoelf Stellen gerundeten Eingaben, die Reihe exakt. Ein Unterschied bis zu
# einem Millionstel Euro ist Rundung, alles darueber eine Abweichung.
CHECK_TOLERANCE = Fraction(1, 10 ** 6)


def round12(value: Fraction) -> Fraction:
    """Wie das Modul: auf zwoelf Nachkommastellen abgeschnitten, Richtung null."""
    if value == 0:
        return value
    return Fraction(int(value * SCALE), SCALE)


def anniversary(day: str) -> str:
    """Wie das Modul: derselbe Tag ein Jahr spaeter, der 29. Februar wird zum 28."""
    year, month, dom = (int(part) for part in day.split("-"))
    if month == 2 and dom == 29:
        dom = 28
    return f"{year + 1:04d}-{month:02d}-{dom:02d}"


def _plugin_root(root: Path | None = None) -> Path:
    from migrations.reference.tax_model_plugin_v1 import PLUGIN_ROOT
    return Path(PLUGIN_ROOT if root is None else root) / PLUGIN_ID


def _unrealized_module(data_space: Path, context: Any, portfolio_ref: str) -> dict[str, Any]:
    """Die Fassung des Moduls 2 fuer die Netto-Sicht (#486 Schritt 2): die Auswahl fuer "unrealized_snapshot", die heute gilt. Ohne
    Auswahl, bei fehlender Fassung oder einem anderen Modul die mitgelieferte Fassung 2 (so bis rc.420). `root` = Ordner ueber dem
    Modulordner, None = mitgeliefert."""
    from datetime import datetime, timezone
    from migrations.reference.tax_model_plugin_v1 import TaxPluginBlocked
    from migrations.reference.tax_module_catalog_v1 import TaxModuleCatalogBlocked, resolve_tax_module_v1, tax_module_manifest_v1
    try:
        resolved = resolve_tax_module_v1(data_space, context, portfolio_ref, "unrealized_snapshot", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        entry = resolved.get("entry")
        if resolved["status"] == "selected" and entry["plugin_id"] == PLUGIN_ID and entry["origin"] == "data_space":
            return {"manifest": tax_module_manifest_v1(entry), "root": Path(entry["plugin_root"])}
    except (TaxModuleCatalogBlocked, TaxPluginBlocked):
        pass
    return {"manifest": None, "root": None}


def legal_values_v1(root: Path | None = None) -> tuple[dict[tuple[int, str], Fraction], set[int]]:
    """Die Werte des Gesetzes je Jahr aus dem Modul (Abgeltungsteuersatz, Solidaritaetszuschlag ...); `root` wie bei _unrealized_module."""
    with (_plugin_root(root) / "annual-legal-values.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    values = {(int(row["tax_year"]), row["value_code"]): Fraction(Decimal(row["value_decimal"])) for row in rows if row["value_decimal"]}
    # Die Netto-Sicht folgt der Jahreskette ab 2020 (#496): Die Grundzuege 2016-2019 des Moduls zaehlen hier nicht als abgedeckt.
    from workers.reference.tax_annual_chain_v1 import FIRST_YEAR
    return values, {int(row["tax_year"]) for row in rows if int(row["tax_year"]) >= FIRST_YEAR}


def _param(parameters: Sequence[Mapping[str, Any]], year: int, code: str, field: str) -> Any:
    """Wie das Modul: genau ein eingetragener Wert des Jahres ohne Institut, sonst keiner."""
    found = [row for row in parameters if int(row["tax_year"]) == year and row["parameter_code"] == code and row.get("institution_key") is None]
    if len(found) != 1 or found[0].get(field) is None:
        return None
    return found[0][field]


def year_rates_v1(setup: Mapping[str, Any], year: int) -> dict[str, Any]:
    """Die Saetze eines Jahres, wie das Modul sie liest: eingetragener Wert vor dem Wert des Gesetzes."""
    parameters = setup["parameters"]

    def rate(code: str) -> Fraction | None:
        own = _param(parameters, year, code, "rate_decimal")
        return Fraction(Decimal(str(own))) if own is not None else setup["legal"].get((year, code))

    applicable = _param(parameters, year, "church_tax_applicable", "applicability_value")
    church_rate = _param(parameters, year, "church_tax_rate", "rate_decimal")
    if applicable not in ("applicable", "not_applicable"):
        church: tuple[str, Any] = ("blocked", "church_tax_applicability_required")
    elif applicable == "not_applicable":
        church = ("not_applicable", None)
    elif church_rate is None:
        church = ("blocked", "church_tax_rate_required")
    else:
        church = ("applicable", Fraction(Decimal(str(church_rate))))
    return {"year": year, "covered": year in setup["covered"], "capital": rate("capital_income_tax_rate"),
            "personal": rate("personal_income_tax_rate"), "soli": rate("solidarity_surcharge_rate"), "church": church}


def classification_v1(setup: Mapping[str, Any], asset_ref: str, year: int) -> dict[str, Any] | None:
    """Wie das Modul: die letzte Einordnung des Assets, die im Jahr gilt."""
    found = [row for row in setup["classifications"] if row["asset_ref"] == asset_ref and int(row["effective_from_year"]) <= year
             and (row.get("effective_to_year") is None or int(row["effective_to_year"]) >= year)]
    return found[-1] if found else None


def unrealized_tax_v1(value: Fraction, basis: Fraction, fee: Fraction, cls: Mapping[str, Any] | None, rates: Mapping[str, Any],
                      lots: tuple[Fraction, Fraction, Fraction] | None) -> tuple[Fraction | None, str | None]:
    """Die projizierte Steuer einer hypothetischen Liquidation - dieselbe Rechnung wie das Modul (`unrealized_snapshot`).

    'lots' sind Gesamtmenge, Menge und Anschaffungskosten der Lose in der Jahresfrist. Zurueck kommt die Steuer oder der
    Grund, warum es keine gibt (dann None)."""
    gain = value - basis
    private = cls is not None and cls["classification_code"] == PRIVATE_CODE
    if gain <= 0 and not private:
        return Fraction(0), None
    if not rates["covered"]:
        return None, "tax_year_rules_missing"
    if cls is None:
        return None, "tax_classification_required"
    model = CLASS_MODELS.get(cls["classification_code"])
    exemption = cls.get("partial_exemption_rate_decimal") or "0"
    if model is None or model[0] != cls["tax_bucket"] or "sell" not in model[1] or (model[2] == "zero" and exemption != "0"):
        return None, "tax_classification_invalid"
    taxable = gain - fee
    if private:
        if lots is None or lots[0] <= 0:
            return None, "tax_holding_evidence_required"
        total, inside_quantity, inside_cost = lots
        taxable = round12((value - fee) * inside_quantity / total - inside_cost)
    if model[2] == "asset":
        taxable = round12(taxable * (100 - Fraction(Decimal(exemption))) / 100)
    if taxable <= 0:
        return Fraction(0), None
    base_rate = rates["capital"] if cls["tax_bucket"] in CAPITAL_BUCKETS else rates["personal"]
    if base_rate is None or rates["soli"] is None:
        return None, "tax_rate_required"
    if rates["church"][0] == "blocked":
        return None, rates["church"][1]
    base_tax = taxable * base_rate / 100
    church = base_tax * rates["church"][1] / 100 if rates["church"][0] == "applicable" else Fraction(0)
    return round12(base_tax + base_tax * rates["soli"] / 100 + church), None


def liquidation_taxable_v1(value: Fraction, basis: Fraction, fee: Fraction, cls: Mapping[str, Any] | None, rates: Mapping[str, Any],
                           lots: tuple[Fraction, Fraction, Fraction] | None) -> tuple[str | None, Fraction | None, str | None]:
    """Topf und steuerpflichtiger Betrag (mit Vorzeichen) einer hypothetischen Liquidation fuer die Rechnung je Topf (#501):
    dieselben Schritte wie `unrealized_tax_v1`, aber auch fuer Verluste - sie verrechnen sich im Topf. Ein Verlust ohne
    Einordnung zaehlt nicht (Betrag null); ein Gewinn ohne Einordnung hat keinen Betrag (Grund)."""
    gain = value - basis
    private = cls is not None and cls["classification_code"] == PRIVATE_CODE
    if not rates["covered"]:
        return None, None, "tax_year_rules_missing"
    if cls is None:
        return (None, Fraction(0), None) if gain <= 0 else (None, None, "tax_classification_required")
    model = CLASS_MODELS.get(cls["classification_code"])
    exemption = cls.get("partial_exemption_rate_decimal") or "0"
    if model is None or model[0] != cls["tax_bucket"] or "sell" not in model[1] or (model[2] == "zero" and exemption != "0"):
        return (None, Fraction(0), None) if gain <= 0 and not private else (None, None, "tax_classification_invalid")
    taxable = gain - fee
    if private:
        if lots is None or lots[0] <= 0:
            return None, None, "tax_holding_evidence_required"
        total, inside_quantity, inside_cost = lots
        taxable = round12((value - fee) * inside_quantity / total - inside_cost)
    if model[2] == "asset":
        taxable = round12(taxable * (100 - Fraction(Decimal(exemption))) / 100)
    return cls["tax_bucket"], taxable, None


def fee_rates_v1(ledger: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Fraction], Fraction | None]:
    """Der Gebuehrensatz je Asset aus den eigenen Kaeufen und Verkaeufen (Summe Gebuehren / Summe Umsaetze, in Prozent,
    sechs Nachkommastellen) - wie der Abschluss ohne eigene Angabe; dazu der Satz des Portfolios als Rueckfall."""
    per_asset: dict[str, list[Decimal]] = {}
    portfolio = [Decimal(0), Decimal(0)]
    for row in ledger:
        if row["event_type"] not in ("buy", "sell") or row.get("basis_currency") != "EUR":
            continue
        try:
            turnover = Decimal(row["gross_economic_amount_decimal"] or "0")
            fee = Decimal(row["monetary_fee_decimal"] or "0")
        except ArithmeticError:
            continue
        if turnover <= 0 or fee < 0:
            continue
        totals = per_asset.setdefault(row["asset_id"], [Decimal(0), Decimal(0)])
        totals[0] += fee; totals[1] += turnover
        portfolio[0] += fee; portfolio[1] += turnover

    def rate(fee: Decimal, turnover: Decimal) -> Fraction:
        return Fraction((fee / turnover * Decimal(100)).quantize(FEE_RATE_SCALE, rounding=ROUND_HALF_EVEN))

    rates = {asset: rate(*value) for asset, value in per_asset.items() if value[1] > 0}
    return rates, (rate(*portfolio) if portfolio[1] > 0 else None)


def _current_worlds(store: sqlite3.Connection) -> list[str]:
    rows = store.execute("SELECT world_artifacts_json FROM current_realized_global_artifact").fetchall()
    if not rows:
        return []
    return sorted({item["world_artifact_ref"] for item in json.loads(rows[0][0])})


def fifo_lots_v1(data_space: Path) -> dict[str, Any]:
    """Die Lose des aktuellen FIFO-Stands je Asset (FIFO-Kennung): Anschaffung, Anfangsmenge und -kosten, Verbrauch je
    Buchung und der Rest. Ein Los ist eine Anschaffung; liegt es nach Transfers auf mehreren Konten, steht es hier einmal mit
    seiner ganzen Restmenge (der Kern rechnet je Konto, siehe lot_trace_v1)."""
    path = data_space / "realized-state-v2" / "realized-state.sqlite"
    if not path.is_file():
        return {"lots": {}, "fingerprint": None}
    store = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        worlds = _current_worlds(store)
        fingerprint = store.execute("SELECT artifact_fingerprint FROM current_realized_global_artifact").fetchone()
        if not worlds:
            return {"lots": {}, "fingerprint": None}
        marks = ",".join("?" for _ in worlds)
        events = {(row[0], row[1]): (row[2], row[3]) for row in store.execute(
            f"SELECT world_artifact_ref,event_sequence,event_ref,asset_ref FROM realized_event_result WHERE world_artifact_ref IN ({marks})",
            tuple(worlds))}
        remaining = store.execute(
            f"SELECT world_artifact_ref,lot_ref,asset_ref,acquisition_event_ref,acquisition_local_date,acquisition_effective_at_utc,"
            f"remaining_quantity_decimal,remaining_fifo_basis FROM realized_remaining_lot WHERE world_artifact_ref IN ({marks})",
            tuple(worlds)).fetchall()
        movements = store.execute(
            f"SELECT world_artifact_ref,event_sequence,lot_ref,acquisition_event_ref,quantity_decimal,fifo_basis FROM realized_lot_movement "
            f"WHERE world_artifact_ref IN ({marks}) ORDER BY world_artifact_ref,event_sequence,movement_sequence", tuple(worlds)).fetchall()
        # Splits (#451) stehen im Ergebnis der Welt; nur Welten mit Split werden gelesen. Nur Splits fuer alle Konten.
        split_rows = store.execute(
            f"SELECT world_artifact_ref,result_json FROM realized_world_artifact WHERE world_artifact_ref IN ({marks}) "
            f"AND instr(result_json, '\"split_results\"') > 0", tuple(worlds)).fetchall()
    finally:
        store.close()
    world_splits = {row[0]: [(item["effective_local_date"], Fraction(int(item["ratio_numerator"]), int(item["ratio_denominator"])))
                             for item in json.loads(row[1]).get("split_results", []) if item["account_ref"] is None] for row in split_rows}
    from workers.reference.portfolio_history_performance_v1 import _exact
    lots: dict[tuple[str, str], dict[str, Any]] = {}

    def lot(world: str, ref: str, asset: str | None, acquisition: str) -> dict[str, Any]:
        entry = lots.setdefault((world, ref), {"lot_ref": ref, "asset": asset, "acquisition_event_ref": acquisition, "acquired": None, "effective": None,
                                               "remaining_quantity": Fraction(0), "remaining_basis": Fraction(0), "consumed": [],
                                               "splits": world_splits.get(world, [])})
        if entry["asset"] is None:
            entry["asset"] = asset
        return entry

    for row in remaining:
        entry = lot(row[0], row[1], row[2], row[3])
        entry["acquired"], entry["effective"] = row[4], row[5]
        entry["remaining_quantity"] = _fraction(row[6]) or Fraction(0)
        entry["remaining_basis"] = _exact(row[7]) or Fraction(0)
    for row in movements:
        event_ref, asset = events.get((row[0], row[1]), (None, None))
        entry = lot(row[0], row[2], asset, row[3])
        entry["consumed"].append({"event_ref": event_ref, "quantity": _fraction(row[4]) or Fraction(0), "basis": _exact(row[5]) or Fraction(0)})
    by_asset: dict[str, list[dict[str, Any]]] = {}
    for entry in lots.values():
        if entry["asset"] is not None:
            by_asset.setdefault(entry["asset"], []).append(entry)
    return {"lots": by_asset, "fingerprint": None if fingerprint is None else fingerprint[0]}


def lot_trace_v1(data_space: Path, context: Any, canonical: Path) -> dict[str, Any]:
    """Aus der Lot-Spur des FIFO-Kerns (er rechnet nach und liefert nur, was dem gespeicherten Stand gleicht): die offenen Lose
    je Asset und Konto, die Lose, die Transfers zwischen Konten trugen, die Methode je Wallet im laufenden Abschnitt und - bei
    der Durchschnittsmethode (rc.294) - jede Angleichung der Kosten eines Loses. Dazu die Bezeichnungen der Konten. Leer, wenn
    es keinen Stand gibt."""
    from workers.reference.asset_activity_realized_state_v2 import read_asset_activity_realized_lot_trace_v2
    from workers.reference.portfolio_history_performance_v1 import _exact
    connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
    try:
        labels = dict(connection.execute("SELECT account_id, display_name FROM account").fetchall())
    finally:
        connection.close()
    trace = read_asset_activity_realized_lot_trace_v2(data_space, context)
    lots: dict[str, dict[str, list[dict[str, Any]]]] = {}
    moves: list[dict[str, Any]] = []
    methods: dict[tuple[str, str], str] = {}
    adjustments: dict[str, list[tuple[str, Fraction]]] = {}
    wallets: dict[str, str] = {}
    for world in trace.get("worlds", []):
        # FIFO-Wallet aus mehreren Konten (#508): Lose und Spur nennen dann das Hauptkonto.
        for item in world.get("fifo_wallets") or []:
            wallets[item["account_ref"]] = item["wallet_account_ref"]
        for row in world["account_lots"]:
            lots.setdefault(row["asset_ref"], {}).setdefault(row["account_ref"], []).append({
                "acquired": row["acquisition_local_date"], "effective": row["acquisition_effective_at_utc"],
                "acquisition_event_ref": row["acquisition_event_ref"], "remaining_quantity": _fraction(row["remaining_quantity_decimal"]) or Fraction(0),
                "remaining_basis": _exact(row["remaining_fifo_basis"]) or Fraction(0)})
        moves.extend(world["transfer_lot_movements"])
        for segment in world.get("wallet_segments", []):
            methods[(segment["asset_ref"], segment["account_ref"])] = segment["method"]
        for row in world.get("basis_adjustments", []):
            delta = _exact(row["basis_delta"])
            if delta is not None:
                adjustments.setdefault(row["lot_ref"], []).append((row["event_ref"], delta, row["account_ref"]))
    return {"lots": lots, "moves": moves, "labels": labels, "methods": methods, "adjustments": adjustments,
            "freshness": trace.get("freshness"), "wallets": wallets}


def _split_ratio(splits: Sequence[tuple[str, Fraction]], after: str, until: str | None) -> Fraction:
    """Das Produkt der Splits mit Stichtag nach 'after' und bis einschliesslich 'until' (ohne Ende: alle spaeteren)."""
    ratio = Fraction(1)
    for day, factor in splits:
        if day > after and (until is None or day <= until):
            ratio *= factor
    return ratio


def _initial_quantity(entry: Mapping[str, Any], acquired: str, dates: Mapping[str, str]) -> Fraction:
    """Die Anfangsmenge eines Loses in den Stuecken seiner Anschaffung (#451): Rest und Verbrauch stehen in den Stuecken ihres Tages;
    ohne Split ist es ihre Summe."""
    splits = entry.get("splits") or []
    if not splits:
        return entry["remaining_quantity"] + sum((item["quantity"] for item in entry["consumed"]), Fraction(0))
    total = entry["remaining_quantity"] / _split_ratio(splits, acquired, None)
    for item in entry["consumed"]:
        day = dates.get(item["event_ref"]) if item["event_ref"] else None
        total += item["quantity"] / _split_ratio(splits, acquired, day)
    return total


def _split_changes(entry: Mapping[str, Any], acquired: str, slot: int) -> list[tuple[str, float, int, Fraction, Fraction]]:
    """Je Split nach der Anschaffung eine Teilung des Loses zu Beginn des Stichtags - vor dem Verbrauch dieses Tages."""
    return [(day, 0.5, slot, factor, Fraction(0)) for day, factor in entry.get("splits") or [] if day > acquired]


class _Ladder:
    """Menge und Kosten der Lose je Tag - gesamt und in der Jahresfrist; nur an Tagen mit Aenderung neu gerechnet."""

    def __init__(self, lots: list[dict[str, Any]], dates: Mapping[str, str], adjustments: Mapping[str, list[tuple[str, Fraction]]] | None = None):
        self.changes: list[tuple[str, int, int, Fraction, Fraction]] = []   # Tag, Reihenfolge, Los, Menge, Kosten
        self.lots = []
        for index, entry in enumerate(lots):
            acquired = entry["acquired"] or dates.get(entry["acquisition_event_ref"])
            if acquired is None:
                continue
            # Durchschnittsmethode (rc.294): Ein Zugang in die Wallet gleicht die Kosten ihrer Lose an. Die Anfangskosten eines
            # Loses sind dann Rest plus Verbrauch ohne die Angleichungen; jede Angleichung wirkt am Tag ihres Zugangs.
            shifts = [(dates.get(item[0]), item[1]) for item in (adjustments or {}).get(entry.get("lot_ref"), [])]
            quantity = _initial_quantity(entry, acquired, dates)
            basis = (entry["remaining_basis"] + sum((item["basis"] for item in entry["consumed"]), Fraction(0))
                     - sum((delta for _, delta in shifts), Fraction(0)))
            leave = (date.fromisoformat(anniversary(acquired)) + timedelta(days=1)).isoformat()
            slot = len(self.lots)
            self.lots.append({"acquired": acquired, "leave": leave})
            self.changes.append((acquired, 0, slot, quantity, basis))
            self.changes.extend(_split_changes(entry, acquired, slot))
            for item in entry["consumed"]:
                day = dates.get(item["event_ref"]) if item["event_ref"] else None
                if day is not None:
                    self.changes.append((day, 1, slot, -item["quantity"], -item["basis"]))
            for day, delta in shifts:
                self.changes.append((day or acquired, 1, slot, Fraction(0), delta))
            self.changes.append((leave, 2, slot, Fraction(0), Fraction(0)))
        self.changes.sort(key=lambda change: (change[0], change[1], change[2]))
        self.position = 0
        self.quantity = [Fraction(0)] * len(self.lots)
        self.cost = [Fraction(0)] * len(self.lots)
        self.inside = [False] * len(self.lots)
        self.total = Fraction(0)
        self.total_cost = Fraction(0)
        self.inside_quantity = Fraction(0)
        self.inside_cost = Fraction(0)

    def advance(self, day: str) -> tuple[Fraction, Fraction, Fraction, Fraction]:
        """Stand am Ende des Tages: Gesamtmenge, Gesamtkosten, Menge und Kosten in der Frist."""
        while self.position < len(self.changes) and self.changes[self.position][0] <= day:
            when, kind, slot, quantity, cost = self.changes[self.position]
            self.position += 1
            if kind == 0.5:
                # Split (#451): Das Los wird geteilt, die Kosten bleiben.
                delta = self.quantity[slot] * (quantity - 1)
                self.quantity[slot] += delta; self.total += delta
                if self.inside[slot]:
                    self.inside_quantity += delta
            elif kind == 0:
                self.quantity[slot] += quantity; self.cost[slot] += cost
                self.total += quantity; self.total_cost += cost
                self.inside[slot] = True
                self.inside_quantity += quantity; self.inside_cost += cost
            elif kind == 1:
                self.quantity[slot] += quantity; self.cost[slot] += cost
                self.total += quantity; self.total_cost += cost
                if self.inside[slot]:
                    self.inside_quantity += quantity; self.inside_cost += cost
            elif self.inside[slot]:
                self.inside[slot] = False
                self.inside_quantity -= self.quantity[slot]; self.inside_cost -= self.cost[slot]
        return self.total, self.total_cost, self.inside_quantity, self.inside_cost


def tax_setup_v1(data_space: Path, context: Any, canonical: Path, years: Sequence[int]) -> dict[str, Any]:
    """Einordnungen je Asset und Parameter je Jahr aus dem Steuerspeicher - gelesen wie fuer die Rechenblaetter."""
    from migrations.reference.asset_activity_reference_v1 import AssetActivityReferenceV1Error, activity_reference_scope_v1
    from workers.reference import tax_event_sheet_v1 as sheets
    from workers.reference.semantic_realized_fifo_v1 import public_ref
    legal, covered = legal_values_v1()
    store = data_space / "tax-ui" / "tax-policy.sqlite"
    if not store.is_file() or store.is_symlink():
        return {"status": "tax_settings_absent", "legal": legal, "covered": covered}
    connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
    try:
        portfolios = [row[0] for row in connection.execute("SELECT portfolio_id FROM portfolio WHERE status = 'active'")]
    finally:
        connection.close()
    if len(portfolios) != 1:
        return {"status": "portfolio_ambiguous", "legal": legal, "covered": covered}
    try:
        scope = activity_reference_scope_v1(context)
    except AssetActivityReferenceV1Error:
        return {"status": "tax_settings_unreadable", "legal": legal, "covered": covered}
    parameters: list[dict[str, Any]] = []
    configuration = None
    for year in sorted({year for year in years if year in covered}):
        configuration = sheets._configuration(data_space, scope, portfolios[0], year)
        if configuration["status"] != "ready":
            return {"status": configuration["status"], "legal": legal, "covered": covered}
        seen = set()
        for row in configuration["parameters"]:
            key = (int(row["tax_year"]), row["parameter_code"], json.dumps(row, sort_keys=True, default=str))
            if int(row["tax_year"]) == year and key not in seen:
                seen.add(key)
                parameters.append(dict(row))
    if configuration is None:
        return {"status": "tax_year_rules_missing", "legal": legal, "covered": covered}
    fingerprint = configuration["fingerprint"]
    # Die Fassung der Auswahl fuer die Netto-Sicht; eine andere als die mitgelieferte bringt ihre eigenen Jahreswerte mit.
    module = _unrealized_module(data_space, configuration["context"], configuration["portfolio_ref"])
    if module["root"] is not None:
        legal, covered = legal_values_v1(module["root"])
    return {"status": "ready", "legal": legal, "covered": covered, "parameters": parameters, "module": module,
            "classifications": configuration["classifications"], "context": configuration["context"],
            "portfolio_ref": configuration["portfolio_ref"], "portfolio_id": portfolios[0],
            "asset_ref": lambda asset_id: public_ref("asf_", fingerprint, asset_id)}


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
    elif path.is_dir():
        for item in sorted(path.rglob("*")):
            if item.is_file() and not item.is_symlink():
                digest.update(str(item.relative_to(path)).encode("utf-8"))
                digest.update(_file_digest(item).encode("ascii"))
    return digest.hexdigest()


TAXABLE_DOCUMENT_STORE = Path("asset-activity-reference-v1") / "activity-taxable-document.sqlite"


def tax_inputs_fingerprint_v1(data_space: Path, canonical: Path, fifo_fingerprint: str | None) -> str:
    """Woraus die Steuer je Ereignis entsteht: FIFO-Stand, Stammdaten, Steuereinstellungen, Cash (Zinsen),
    Vorabpauschalen, Betraege laut Beleg (#536) und das Modul. Gleich geblieben, gilt die Steuer der letzten Veroeffentlichung
    weiter. Bis rc.358 fehlte der Speicher laut Beleg: Ein uebernommener Bankwert blieb, bis sich etwas anderes aenderte."""
    from migrations.reference.tax_model_plugin_v1 import tax_plugin_manifest_v1
    from workers.reference.tax_event_sheet_v1 import CONTRACT
    manifest = tax_plugin_manifest_v1(PLUGIN_ID)
    parts = {"version": NET_VERSION, "sheet": CONTRACT, "rules": manifest.rules_fingerprint, "manifest": manifest.manifest_fingerprint,
             "fifo": fifo_fingerprint, "canonical": _file_digest(canonical)}
    for name in ("tax-ui", "institution-tax-settings-v1", "advance-lump-sum-v1", "cash-coverage-v1"):
        parts[name] = _file_digest(data_space / name)
    # Nur der Speicher laut Beleg, nicht der ganze Bereich der Belegangaben: Kennungen und Veraeusserungswerte aendern die Steuer
    # nicht oder stehen schon im FIFO-Stand.
    parts["taxable-document"] = _file_digest(data_space / TAXABLE_DOCUMENT_STORE)
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode("utf-8")).hexdigest()


def opaque_ref_v1(fingerprint_seed: str, event_ref: str) -> str:
    """Eine nicht rueckfuehrbare Kennung je Buchung fuer die Wiederverwendung - interne Schluessel gehen nicht in Dateien."""
    return "ntx_" + hashlib.sha256(f"{fingerprint_seed}|{event_ref}".encode("utf-8")).hexdigest()[:32]


def sheet_models_v1(data_space: Path, context: Any, years: Sequence[int], covered: set[int],
                    sheet_builder: Callable[..., dict[str, Any]] | None = None) -> dict[int, dict[str, Any]]:
    """Die Rechenblaetter je Jahr mit Regeln - mit Modulzeilen und Bestandsschluesseln, einmal gebaut fuer die Steuer je
    Ereignis und fuer die Rechnung je Topf (#501)."""
    from workers.reference.tax_event_sheet_v1 import ASSET_TYPES, build_tax_event_sheets_v1
    builder = sheet_builder or build_tax_event_sheets_v1
    return {year: builder(data_space, context, year, list(ASSET_TYPES), keep_source_keys=True, keep_module_rows=True)
            for year in sorted(set(years)) if year in covered}


def realized_taxes_v1(data_space: Path, context: Any, years: Sequence[int], covered: set[int], seed: str,
                      sheet_builder: Callable[..., dict[str, Any]] | None = None, models: Mapping[int, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Die projizierte Steuer je steuerlichem Ereignis (Verkauf, Dividende, Reward, Vorabpauschale, Zins) aus den
    Rechenblaettern - je Ereignis konservativ. Schluessel sind verschleierte Buchungskennungen; Zinsen je Konto und Tag."""
    if models is None:
        models = sheet_models_v1(data_space, context, years, covered, sheet_builder)
    events: dict[str, dict[str, Any]] = {}
    interest: dict[str, dict[str, Any]] = {}
    status: dict[str, str] = {}
    for year in sorted(set(years)):
        if year not in covered:
            status[str(year)] = "tax_year_rules_missing"
            continue
        model = models[year]
        status[str(year)] = model["status"] if model["status"] != "ready" else (model.get("settings_status") or "ready")
        for sheet in model.get("sheets", []):
            calculation = sheet["calculation"]
            if calculation["status"] == "calculated":
                tax = calculation["tax_total"]
            elif calculation["status"] == "not_taxable":
                tax = "0"
            else:
                tax = None
            entry = {"kind": sheet["event_kind"], "type": sheet["event_type"], "day": sheet["event"]["local_date"], "tax": tax,
                     "reason": None if tax is not None else calculation.get("reason_code"),
                     "asset": opaque_ref_v1(seed, "asset|" + str(sheet["source_key"].get("asset_id")))}
            if sheet["event_type"] == "interest":
                key = sheet["event"].get("account_label") or ""
                bucket = interest.setdefault(f"{key}|{entry['day']}", {"account": key, "day": entry["day"], "tax": "0"})
                bucket["tax"] = None if bucket["tax"] is None or tax is None else _text(Fraction(bucket["tax"]) + _fraction(tax))
            else:
                events[opaque_ref_v1(seed, sheet["source_key"]["event_ref"])] = entry
    return {"events": events, "interest": sorted(interest.values(), key=lambda row: (row["day"], row["account"])), "years": status}


def cross_check_v1(setup: Mapping[str, Any], cutoff: str, rows: Sequence[Mapping[str, Any]],
                   runner: Callable[..., Any] | None = None) -> dict[str, tuple[str | None, str | None]]:
    """Das Modul rechnet die hypothetische Liquidation des letzten Tages selbst - je Asset die Steuer oder der Grund."""
    from migrations.reference.tax_model_plugin_v1 import TaxPluginSelection, new_tax_plugin_bound_input_v1, sha
    from migrations.reference.tax_model_plugin_v1 import tax_plugin_manifest_v1
    from migrations.reference.tax_model_plugin_v2 import run_tax_model_plugin_v2
    if not rows:
        return {}
    module = setup.get("module") or {}
    manifest = module.get("manifest") or tax_plugin_manifest_v1(PLUGIN_ID)
    selection_ref = "tsr_" + sha({"history_net": setup["portfolio_ref"], "cutoff": cutoff})[:32]
    selection = TaxPluginSelection(selection_ref, 1, sha({"selection": selection_ref}), setup["portfolio_ref"], "unrealized_snapshot",
                                   manifest.plugin_id, manifest.plugin_version, manifest.rules_fingerprint, manifest.manifest_fingerprint,
                                   manifest.effective_from, "active")
    year = int(cutoff[:4])
    bound = new_tax_plugin_bound_input_v1(
        projection_mode="unrealized_snapshot", portfolio_ref=setup["portfolio_ref"],
        source_artifact_ref="phn_" + sha({"rows": [row["position_ref"] for row in rows], "cutoff": cutoff})[:32], cutoff=cutoff,
        rows=list(rows), classifications=setup["classifications"],
        parameters=[row for row in setup["parameters"] if int(row["tax_year"]) == year])
    result = (runner or run_tax_model_plugin_v2)(bound_input=bound, context=setup["context"], selection=selection, timeout_seconds=240,
                                                 **({"plugin_root": module["root"]} if module.get("root") is not None else {}))
    return {row["position_ref"]: (row.get("projected_unrealized_tax_decimal"), row.get("failure_code")) for row in result.rows}


class _AccountLadder:
    """Menge und Kosten der Lose eines Kontos je Tag - gesamt und in der Jahresfrist (#499).

    Ein Los kommt durch Anschaffung oder Transfer aufs Konto und geht durch Verbrauch oder Transfer; in der Frist ist es bis zum
    Jahrestag seiner Anschaffung, gleich wann es auf dieses Konto kam (der Transfer traegt das Anschaffungsdatum mit)."""

    def __init__(self, leaves: Sequence[str], changes: Sequence[tuple[str, int, int, Fraction, Fraction]]):
        self.leaves = list(leaves)
        self.changes = sorted([*changes, *((leave, 2, slot, Fraction(0), Fraction(0)) for slot, leave in enumerate(self.leaves))],
                              key=lambda change: (change[0], change[1], change[2]))
        self.position = 0
        self.quantity = [Fraction(0)] * len(self.leaves)
        self.cost = [Fraction(0)] * len(self.leaves)
        self.left = [False] * len(self.leaves)
        self.total = self.total_cost = self.inside_quantity = self.inside_cost = Fraction(0)

    def advance(self, day: str) -> tuple[Fraction, Fraction, Fraction, Fraction]:
        while self.position < len(self.changes) and self.changes[self.position][0] <= day:
            when, kind, slot, quantity, cost = self.changes[self.position]
            self.position += 1
            if kind == 0.5:
                # Split (#451): Das Los auf diesem Konto wird geteilt, die Kosten bleiben.
                delta = self.quantity[slot] * (quantity - 1)
                self.quantity[slot] += delta; self.total += delta
                if not self.left[slot] and when < self.leaves[slot]:
                    self.inside_quantity += delta
            elif kind == 1:
                self.quantity[slot] += quantity; self.cost[slot] += cost
                self.total += quantity; self.total_cost += cost
                if not self.left[slot] and when < self.leaves[slot]:
                    self.inside_quantity += quantity; self.inside_cost += cost
            elif not self.left[slot]:
                self.left[slot] = True
                self.inside_quantity -= self.quantity[slot]; self.inside_cost -= self.cost[slot]
        return self.total, self.total_cost, self.inside_quantity, self.inside_cost


def _wallet_ladder_of(ladders: Mapping[tuple[str, str], Any], wallets: Mapping[str, str] | None) -> Callable[[Any], Any]:
    """Die Losleiter zu (Asset, Konto). Ein Konto einer FIFO-Wallet (#508), das das Asset allein hielt, liest die Leiter der Wallet:
    Dann sind ihre Lose seine. (Hielten mehrere Konten der Wallet das Asset, rechnet nur der Eintrag der Wallet Netto.)"""
    from workers.reference.portfolio_history_accounts_v1 import wallet_groups_v1
    groups = wallet_groups_v1(wallets or {})
    return lambda key: ladders.get(key) or (ladders.get((key[0], groups[key[1]])) if key[1] in groups else None)


def account_ladders_v1(lots: Mapping[str, list[dict[str, Any]]], account_of: Mapping[str, str], moves: Sequence[Mapping[str, Any]],
                       adjustments: Mapping[str, list[tuple[str, Fraction, str]]], dates: Mapping[str, str],
                       wallets: Mapping[str, str] | None = None) -> dict[tuple[str, str], _AccountLadder]:
    """Je (Asset, Konto) die Lose je Tag: Anschaffung auf dem Konto der Anschaffung, Verbrauch auf dem Konto der Buchung,
    Transfers vom Quell- aufs Zielkonto (Lot-Spur des Kerns) und Angleichungen der Durchschnittsmethode auf ihrem Konto.

    Mit 'wallets' (#508) stehen die Lose einer FIFO-Wallet aus mehreren Konten unter dem Schluessel der Wallet: Sie gehoeren
    keinem ihrer Konten allein."""
    from workers.reference.portfolio_history_accounts_v1 import wallet_groups_v1
    groups = wallet_groups_v1(wallets or {})
    from workers.reference.portfolio_history_performance_v1 import _exact as exact
    slots: dict[tuple[str, str], dict[str, int]] = {}
    leaves: dict[tuple[str, str], list[str]] = {}
    changes: dict[tuple[str, str], list[tuple[str, int, int, Fraction, Fraction]]] = {}
    lot_info: dict[str, tuple[str, str]] = {}
    split_targets: list[tuple[str, Mapping[str, Any], str]] = []

    def slot(asset: str, account: str, lot_ref: str) -> tuple[tuple[str, str], int] | None:
        info = lot_info.get(lot_ref)
        if info is None or account is None:
            return None
        key = (asset, groups.get(account, account))
        index = slots.setdefault(key, {}).get(lot_ref)
        if index is None:
            index = slots[key][lot_ref] = len(leaves.setdefault(key, []))
            leaves[key].append(info[1])
        return key, index

    def change(asset: str, account: str | None, lot_ref: str, day: str | None, quantity: Fraction, cost: Fraction) -> None:
        hit = slot(asset, account, lot_ref) if day is not None else None
        if hit is not None:
            changes.setdefault(hit[0], []).append((day, 1, hit[1], quantity, cost))

    for asset, entries in lots.items():
        for entry in entries:
            acquired = entry["acquired"] or dates.get(entry["acquisition_event_ref"])
            if acquired is None or entry.get("lot_ref") is None:
                continue
            lot_info[entry["lot_ref"]] = (asset, (date.fromisoformat(anniversary(acquired)) + timedelta(days=1)).isoformat())
            shifts = adjustments.get(entry["lot_ref"], [])
            quantity = _initial_quantity(entry, acquired, dates)
            basis = (entry["remaining_basis"] + sum((item["basis"] for item in entry["consumed"]), Fraction(0))
                     - sum((item[1] for item in shifts), Fraction(0)))
            change(asset, account_of.get(entry["acquisition_event_ref"]), entry["lot_ref"], acquired, quantity, basis)
            split_targets.append((asset, entry, acquired))
            for item in entry["consumed"]:
                change(asset, account_of.get(item["event_ref"]), entry["lot_ref"], dates.get(item["event_ref"]), -item["quantity"], -item["basis"])
            for event_ref, delta, account in shifts:
                change(asset, account, entry["lot_ref"], dates.get(event_ref) or acquired, Fraction(0), delta)
    for move in moves:
        day = dates.get(move["event_ref"])
        for lot in move["moved_lots"]:
            info = lot_info.get(lot["lot_ref"])
            if info is None:
                continue
            quantity = _fraction(lot["quantity_decimal"]) or Fraction(0)
            cost = exact(lot["fifo_basis"]) or Fraction(0)
            change(info[0], move["source_account_ref"], lot["lot_ref"], day, -quantity, -cost)
            change(info[0], move["destination_account_ref"], lot["lot_ref"], day, quantity, cost)
    # Splits (#451): auf jedem Konto, auf dem das Los je lag, zu Beginn des Stichtags geteilt.
    for asset, entry, acquired in split_targets:
        for key, members in slots.items():
            if key[0] == asset and entry["lot_ref"] in members:
                changes.setdefault(key, []).extend(_split_changes(entry, acquired, members[entry["lot_ref"]]))
    return {key: _AccountLadder(leaves[key], changes.get(key, [])) for key in leaves}


def projection_v1(accounts: Sequence[tuple[str, list[dict[str, Any]], str]], price: Fraction | None, quantity: Fraction, fee_rate: Fraction | None,
                  fee_source: str, cls: Mapping[str, Any] | None, rates: Mapping[str, Any], day: str) -> dict[str, Any]:
    """Die offenen Lose eines Assets je Konto in FIFO-Folge mit Gebuehrensatz und Steuersaetzen - fuer die Projektion (#494).

    Der FIFO-Kern rechnet walletbezogen (seit rc.245, Festlegung 12.10.2026): Ein Verkauf verbraucht nur die Lose
    des Kontos, von dem er abgeht, und ein Transfer traegt Lose mit Anschaffungsdatum und -kosten ins Zielkonto. Die
    Projektion zeigt deshalb je Konto dessen eigene Reihe und die Methode der Wallet (rc.294): Bei der Durchschnittsmethode
    tragen alle Lose denselben Stueckpreis, die Haltefrist folgt weiter ihrer Reihenfolge."""
    def ordered(lots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted((entry for entry in lots if entry["remaining_quantity"] > 0),
                      key=lambda entry: (entry["effective"] or entry["acquired"] or "", entry["acquisition_event_ref"]))
    tax: dict[str, Any] = {"status": "ready"}
    if not rates["covered"]:
        tax = {"status": "tax_year_rules_missing"}
    elif cls is None:
        tax = {"status": "tax_classification_required"}
    else:
        model = CLASS_MODELS.get(cls["classification_code"])
        exemption = cls.get("partial_exemption_rate_decimal") or "0"
        if model is None or model[0] != cls["tax_bucket"] or "sell" not in model[1] or (model[2] == "zero" and exemption != "0"):
            tax = {"status": "tax_classification_invalid"}
        else:
            base_rate = rates["capital"] if cls["tax_bucket"] in CAPITAL_BUCKETS else rates["personal"]
            if base_rate is None or rates["soli"] is None:
                tax = {"status": "tax_rate_required"}
            elif rates["church"][0] == "blocked":
                tax = {"status": rates["church"][1]}
            else:
                tax = {"status": "ready", "classification": cls["classification_code"], "bucket": cls["tax_bucket"],
                       "partial_exemption": exemption if model[2] == "asset" else "0", "rate": _text(base_rate), "solidarity": _text(rates["soli"]),
                       "church": _text(rates["church"][1]) if rates["church"][0] == "applicable" else "0",
                       "holding_period": cls["classification_code"] == PRIVATE_CODE, "tax_year": int(day[:4])}
    rows = []
    for label, lots, method in accounts:
        open_lots = ordered(lots)
        if not open_lots:
            continue
        rows.append({"account": label, "method": method, "quantity": _text(sum((entry["remaining_quantity"] for entry in open_lots), Fraction(0))),
                     "lots": [{"acquired": entry["acquired"], "quantity": _text(entry["remaining_quantity"]), "basis": _text(entry["remaining_basis"]),
                               "free_from": (date.fromisoformat(anniversary(entry["acquired"])) + timedelta(days=1)).isoformat() if entry["acquired"] else None}
                              for entry in open_lots]})
    rows.sort(key=lambda row: (-Fraction(row["quantity"]), row["account"]))
    return {"day": day, "price": _text(price), "quantity": _text(quantity), "fee_rate": _text(fee_rate), "fee_source": fee_source, "tax": tax,
            "accounts": rows}


def liquidation_costs_v1(days: Sequence[str], dailies: Mapping[str, Any], setup: Mapping[str, Any], fee_rates: Mapping[str, Fraction],
                         fee_fallback: Fraction | None, ladders: Mapping[str, list[dict[str, Any]]], dates: Mapping[str, str],
                         adjustments: Mapping[str, list[tuple[str, Fraction]]] | None = None, ladder_of: Callable[[Any], Any] | None = None,
                         asset_of: Callable[[Any], str] | None = None, pooled: bool = False) -> dict[Any, dict[str, Any]]:
    """Je Asset und Tag die Liquidationskosten (Gebuehr und projizierte Steuer) eines hypothetischen Verkaufs am Tagesende.
    None, wo das Asset nicht bewertet ist oder die Steuer fehlt; daneben der erste Grund und die Zahl der Tage ohne Steuer.
    Mit 'pooled' (#501) je Tag dazu Topf und steuerpflichtiger Betrag fuer die Rechnung je Topf ('bucket', 'taxable')."""
    rates_of: dict[int, dict[str, Any]] = {}
    result: dict[str, dict[str, Any]] = {}
    for key, daily in dailies.items():
        # Je Asset; je Konto (#499) mit Schluessel (Asset, Konto) und den Losen des Kontos.
        asset = key if asset_of is None else asset_of(key)
        fee_rate = fee_rates.get(asset, fee_fallback)
        source = "asset" if asset in fee_rates else ("portfolio" if fee_fallback is not None else "none")
        ladder = ladder_of(key) if ladder_of is not None else (_Ladder(ladders.get(asset, []), dates, adjustments) if ladders.get(asset) else None)
        asset_ref = setup["asset_ref"](asset)
        cost: list[Fraction | None] = [None] * len(days)
        fee_list: list[Fraction | None] = [None] * len(days)
        tax_list: list[Fraction | None] = [None] * len(days)
        warned = [False] * len(days)
        taxable_list: list[Fraction | None] = [None] * len(days)
        bucket_list: list[str | None] = [None] * len(days)
        reason, blocked = None, 0
        for position, day in enumerate(days):
            lots = ladder.advance(day) if ladder is not None else None
            value = daily.value[position]
            if value is None:
                continue
            basis = daily.basis[position]
            if value == 0 and basis == 0:
                cost[position] = fee_list[position] = tax_list[position] = Fraction(0)
                taxable_list[position] = Fraction(0)
                continue
            year = int(day[:4])
            rates = rates_of.get(year)
            if rates is None:
                rates = rates_of[year] = year_rates_v1(setup, year)
            fee = value * (fee_rate or Fraction(0)) / 100
            cls = classification_v1(setup, asset_ref, year)
            tax, code = unrealized_tax_v1(value, basis, fee, cls, rates, None if lots is None else (lots[0], lots[2], lots[3]))
            if pooled:
                bucket_list[position], taxable_list[position], _ = liquidation_taxable_v1(value, basis, fee, cls, rates,
                                                                                          None if lots is None else (lots[0], lots[2], lots[3]))
            fee_list[position] = fee
            if tax is None and code == "tax_year_rules_missing":
                # Fuer das Jahr hat das Modul noch keine Regeln (#496): netto = brutto, mit Warnhinweis (Festlegung 21.10.2026).
                tax, warned[position] = Fraction(0), True
            if tax is None:
                blocked += 1
                reason = reason or code
                continue
            tax_list[position] = tax
            cost[position] = fee + tax
        result[key] = {"cost": cost, "fee": fee_list, "tax": tax_list, "warned": warned, "fee_rate": fee_rate, "fee_source": source,
                       "reason": reason, "blocked_days": blocked, "taxable": taxable_list, "bucket": bucket_list}
    return result


def cost_parts_v1(values: Sequence[Fraction | None], cost: Sequence[Fraction | None]) -> list[Fraction | None]:
    """Die Aenderung der Liquidationskosten je Tag fuer ein Asset - ueber unbewertete Tage hinweg wie das Unrealisierte."""
    parts: list[Fraction | None] = [Fraction(0)] * len(values)
    previous = Fraction(0)
    for position in range(len(values)):
        if values[position] is None:
            continue
        if cost[position] is None:
            parts[position] = None
            continue
        parts[position] = cost[position] - previous
        previous = cost[position]
    return parts


def group_cost_v1(members: Sequence[tuple[Sequence[Fraction | None], Sequence[Fraction | None]]], size: int
                  ) -> tuple[list[Fraction | None], list[Fraction | None]]:
    """Kosten einer Gruppe je Tag und ihre Aenderung: wie Wert und Bruecke nur ueber Mitglieder, die heute (und fuer die
    Aenderung auch gestern) bewertet sind - der Tag, an dem eine Bewertung beginnt oder endet, ist neutral."""
    total: list[Fraction | None] = [Fraction(0)] * size
    parts: list[Fraction | None] = [Fraction(0)] * size
    for values, cost in members:
        for position in range(size):
            if values[position] is None:
                continue
            if total[position] is not None:
                total[position] = None if cost[position] is None else total[position] + cost[position]
            if position and values[position - 1] is not None and parts[position] is not None:
                if cost[position] is None or cost[position - 1] is None:
                    parts[position] = None
                else:
                    parts[position] += cost[position] - cost[position - 1]
    return total, parts


def with_net_v1(periods: list[dict[str, Any]], days: Sequence[str], tax_realized: Sequence[Fraction | None],
                tax_income: Sequence[Fraction | None], cost_parts: Sequence[Fraction | None], available: bool = True,
                warned: Sequence[bool] | None = None, field: str = "net") -> list[dict[str, Any]]:
    """Haengt an die Bruecke jedes Zeitraums die Netto-Teile: Steuer auf realisierte Gewinne und auf Ertraege, Aenderung der
    projizierten Liquidationskosten und den Anlageerfolg netto. Fehlt ein Teil im Zeitraum, ist Netto nicht verfuegbar.
    'warned' markiert Tage, an denen mangels Regeln des Jahres netto = brutto gerechnet ist (#496) - dann traegt der Zeitraum
    den Hinweis `tax_year_rules_missing`."""
    index_of = {day: position for position, day in enumerate(days)}

    def total(values: Sequence[Fraction | None], begin: int, stop: int) -> Fraction | None:
        result = Fraction(0)
        for position in range(begin + 1, stop + 1):
            if values[position] is None:
                return None
            result += values[position]
        return result

    for row in periods:
        begin, stop = index_of[row["start_day"]], index_of[row["end_day"]]
        realized = total(tax_realized, begin, stop) if available else None
        income = total(tax_income, begin, stop) if available else None
        change = total(cost_parts, begin, stop) if available else None
        gain = _fraction(row.get("gain"))
        net_gain = None if None in (realized, income, change, gain) else gain - realized - income - change
        warning = "tax_year_rules_missing" if available and warned is not None and any(warned[begin:stop + 1]) else None
        row.setdefault("bridge", {})[field] = {"tax_realized": _text(realized), "tax_income": _text(income), "cost_change": _text(change),
                                               "gain": _text(net_gain), "warning": warning}
    return periods


class NetState:
    """Was vor dem Aufbau der Reihen feststeht: Steuereinstellungen, Gebuehrensaetze, Lose und die Steuer je Ereignis."""

    def __init__(self, data_space: Path, context: Any, canonical: Path, ledger: Sequence[Mapping[str, Any]], years: Sequence[int],
                 previous: Mapping[str, Any] | None = None, sheet_builder: Callable[..., dict[str, Any]] | None = None,
                 trace: Mapping[str, Any] | None = None, pool_runner: Callable[..., Any] | None = None):
        self.seed = f"{context.data_space_id}|{NET_VERSION}"
        self.dates = {row["event_ref"]: row["local_date"] for row in ledger if row.get("local_date")}
        self.asset_ids = sorted({row["asset_id"] for row in ledger if row.get("asset_id")})
        self.fee_rates, self.fee_fallback = fee_rates_v1(ledger)
        self.fifo = fifo_lots_v1(data_space)
        self.trace = trace if trace is not None else lot_trace_v1(data_space, context, canonical)
        self.setup = tax_setup_v1(data_space, context, canonical, years)
        self.status = self.setup["status"]
        # Jahre, in denen das Portfolio nicht zur Veranlagung zaehlt (#501): keine Steuer, wie ein Jahr ohne Regeln - mit Hinweis.
        if self.status == "ready":
            from migrations.reference.tax_assessment_v1 import not_assessed_years_v1
            not_assessed = not_assessed_years_v1(Path(data_space) / "tax-ui", context)
            self.setup["not_assessed"] = not_assessed
            self.setup["covered"] = set(self.setup["covered"]) - not_assessed
        self.realized: dict[str, Any] = {"inputs": None, "events": {}, "interest": [], "years": {}}
        self.pool: dict[str, Any] = {"inputs": None, "version": None, "status": self.status, "years": {}}
        if self.status != "ready":
            return
        from workers.reference.portfolio_history_pool_v1 import POOL_VERSION, pool_years_v1
        inputs = tax_inputs_fingerprint_v1(data_space, canonical, self.fifo["fingerprint"])
        cached = (previous or {}).get("realized") if isinstance(previous, Mapping) else None
        cached_pool = (previous or {}).get("pool") if isinstance(previous, Mapping) else None
        # Die Rechnung je Topf (#501) gilt weiter, wenn die Eingaben gleich sind und die Jahre bis zum letzten reichen.
        pool_fresh = isinstance(cached_pool, Mapping) and cached_pool.get("inputs") == inputs and cached_pool.get("version") == POOL_VERSION \
            and cached_pool.get("last_year") == max(years)
        if isinstance(cached, Mapping) and cached.get("inputs") == inputs and pool_fresh:
            self.realized = dict(cached)
            self.pool = dict(cached_pool)
        else:
            models = sheet_models_v1(data_space, context, years, self.setup["covered"], sheet_builder)
            taxes = realized_taxes_v1(data_space, context, years, self.setup["covered"], self.seed, models=models)
            self.realized = {"inputs": inputs, **taxes}
            pool = pool_years_v1(data_space, context, models, self.setup, max(years), self._pool_key, pool_runner)
            self.pool = {"inputs": inputs, "last_year": max(years), **pool}
        self.realized["events"] = dict(self.realized["events"])

    def _pool_key(self, sheet: Mapping[str, Any]) -> tuple[str, str | None, str]:
        """Kennung, Asset und Art eines Blatts - dieselben verschleierten Kennungen wie die Steuer je Ereignis; Zinsen je Buchung."""
        source = sheet["source_key"]
        if sheet["event_type"] == "interest":
            return opaque_ref_v1(self.seed, "interest|" + str(source.get("event_ref"))), None, "interest"
        return opaque_ref_v1(self.seed, source["event_ref"]), opaque_ref_v1(self.seed, "asset|" + str(source.get("asset_id"))), sheet["event_kind"]

    def event_tax(self, event_ref: str) -> tuple[bool, str | None]:
        """(bekannt, Steuer) einer Buchung; nicht bekannt, wenn die Rechenblaetter sie nicht fuehren."""
        entry = self.realized["events"].get(opaque_ref_v1(self.seed, event_ref))
        return (False, None) if entry is None else (True, entry["tax"])

    def pool_taxes(self) -> dict[str, Any]:
        """Die Steuer je Ereignis je Topf (#501) aus den gerechneten Jahren, mit verschleierter Kennung."""
        if getattr(self, "_pool_index", None) is None:
            result: dict[str, Any] = {}
            for entry in (self.pool.get("years") or {}).values():
                if entry.get("status") == "ready":
                    for item in entry["items"]:
                        result[item["ref"]] = item
            self._pool_index = result
        return self._pool_index

    def event_tax_pooled(self, event_ref: str) -> tuple[bool, str | None]:
        """(bekannt, Steuer je Topf) einer Buchung; ausserhalb gerechneter Jahre die Steuer je Ereignis."""
        item = self.pool_taxes().get(opaque_ref_v1(self.seed, event_ref))
        return (True, item.get("tax")) if item is not None else self.event_tax(event_ref)


def _daily_taxes(state: NetState, days: Sequence[str], ledger: Sequence[Mapping[str, Any]], key_of: Callable[[Mapping[str, Any]], Any] | None = None
                 ) -> tuple[dict[Any, list], dict[Any, list], dict[Any, list]]:
    """Je Asset und Tag die Steuer auf Verkaeufe und auf Ertraege (None, wo eine fehlt) und die Tage, an denen sie mangels
    Regeln des Jahres null ist (Warnhinweis)."""
    index_of = {day: position for position, day in enumerate(days)}
    realized: dict[str, list[Fraction | None]] = {}
    income: dict[str, list[Fraction | None]] = {}
    by_ref = {opaque_ref_v1(state.seed, row["event_ref"]): row for row in ledger}
    for ref, entry in state.realized["events"].items():
        row = by_ref.get(ref)
        if key_of is not None:
            # Je Konto (#499): nur Ereignisse mit Buchung - Konto und Asset stehen dort.
            asset = None if row is None else key_of(row)
        else:
            asset = row["asset_id"] if row is not None else entry.get("asset_id")
        if asset is None and key_of is None:
            asset = next((candidate for candidate in state.asset_ids if opaque_ref_v1(state.seed, "asset|" + candidate) == entry.get("asset")), None)
        position = index_of.get(entry["day"])
        if asset is None or position is None:
            continue
        target = realized if entry.get("kind") == "disposal" else income
        values = target.setdefault(asset, [Fraction(0)] * len(days))
        tax = _fraction(entry["tax"])
        values[position] = None if tax is None or values[position] is None else values[position] + tax
    # In Jahren ohne Regeln des Moduls (#496) gilt netto = brutto: Steuer null, der Tag traegt einen Warnhinweis.
    covered = state.setup.get("covered", set())
    warned: dict[str, list[bool]] = {}
    for row in ledger:
        day = row.get("local_date")
        position = index_of.get(day) if day else None
        if position is None or int(day[:4]) in covered or row["event_type"] not in ("sell", "dividend", "reward", "stock_dividend"):
            continue
        warned.setdefault(row["asset_id"] if key_of is None else key_of(row), [False] * len(days))[position] = True
    return realized, income, warned


def _net_steps(days: Sequence[str], realized_parts: Sequence[Fraction], taxes: Sequence[Fraction | None]) -> list[dict[str, Any]]:
    """Realisiert netto, kumuliert, je Tag mit Verkauf: realisierte GuV minus die Steuer der Verkaeufe bis dahin."""
    steps, cumulative, tax_sum, known = [], Fraction(0), Fraction(0), True
    for position in range(len(days)):
        if realized_parts[position]:
            cumulative += realized_parts[position]
            tax = taxes[position]
            known = known and tax is not None
            tax_sum += tax or Fraction(0)
            steps.append({"day": days[position], "tax": _text(tax), "realized_net_cumulative": _text(cumulative - tax_sum) if known else None})
    return steps


def _group_steps(days: Sequence[str], realized_steps: Sequence[Mapping[str, Any]], taxes: Sequence[Fraction | None]) -> list[dict[str, Any]]:
    """Wie `_net_steps` fuer Klassen und Gruppen: an ihren Stufen das kumulierte Realisierte minus die Steuer bis dahin."""
    tax_sum, known, previous, steps = Fraction(0), True, 0, []
    index_of = {day: position for position, day in enumerate(days)}
    for step in realized_steps:
        position = index_of[step["day"]]
        for inner in range(previous, position + 1):
            known = known and taxes[inner] is not None
            tax_sum += taxes[inner] or Fraction(0)
        previous = position + 1
        steps.append({"day": step["day"], "realized_net_cumulative": _text(_fraction(step["realized_cumulative"]) - tax_sum) if known else None})
    return steps


def _add(total: list[Fraction | None], values: Sequence[Fraction | None] | None) -> None:
    if values is None:
        return
    for position, value in enumerate(values):
        if total[position] is not None:
            total[position] = None if value is None else total[position] + value


def pooled_net_v1(state: NetState, days: Sequence[str], dailies: Mapping[str, Any], costs: Mapping[str, Mapping[str, Any]],
                  ledger: Sequence[Mapping[str, Any]], interest_inside: Callable[[str], bool],
                  holdings: Mapping[str, Mapping[int, str | None]] | None = None, institution_of: Mapping[str, str] | None = None,
                  account_dailies: Mapping[tuple[str, str], Any] | None = None, fifo_events: Mapping[str, Mapping[str, Any]] | None = None,
                  runner: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Netto je Topf im Jahr (#501): je Asset und Tag die verteilte Steuer eines gedachten Verkaufs aller Positionen nach dem
    bis dahin Realisierten des Jahres, dazu die Steuer der Verkaeufe und Ertraege je Topf.

    'costs' sind die Liquidationskosten je Asset mit Topf und Betrag ('pooled'). 'holdings' nennt je Asset und Tag das Konto,
    wenn es auf genau einem liegt (None: auf mehreren); 'institution_of' je Konto den Institutsschluessel. Liegt ein Asset an
    einem Tag auf mehreren Konten, rechnen die Posten je Konto ('account_dailies'), weil Kapitalertraege je Institut
    verrechnet werden. Jahre vor 2020 und ohne Regeln: wie je Asset (netto = brutto mit Warnhinweis)."""
    from workers.reference.portfolio_history_pool_v1 import FIRST_YEAR, PoolDays
    size = len(days)
    pool = state.pool
    status = pool.get("status")
    if state.status != "ready" or status not in ("ready", "tax_year_rules_missing"):
        return {"available": False, "status": "unavailable", "reason": status or state.status}
    holdings = holdings or {}
    institution_of = institution_of or {}
    years = {int(year): entry for year, entry in (pool.get("years") or {}).items()}
    covered = state.setup["covered"]

    def ready(year: int) -> bool:
        return (years.get(year) or {}).get("status") == "ready"

    def uncovered(year: int) -> bool:
        return year < FIRST_YEAR or year not in covered

    account_costs: dict[tuple[str, str], dict[str, Any]] = {}
    if account_dailies and fifo_events is not None:
        account_of = {ref: entry.get("account") for ref, entry in fifo_events.items()}
        ladders = account_ladders_v1(state.fifo["lots"], account_of, state.trace["moves"], state.trace["adjustments"], state.dates,
                                     state.trace.get("wallets"))
        account_costs = liquidation_costs_v1(days, account_dailies, state.setup, state.fee_rates, state.fee_fallback, {}, state.dates,
                                             ladder_of=_wallet_ladder_of(ladders, state.trace.get("wallets")), asset_of=lambda key: key[0], pooled=True)
    accounts_of: dict[str, list[tuple[str, str]]] = {}
    for key in account_costs:
        accounts_of.setdefault(key[0], []).append(key)
    calculator = PoolDays(pool, state.setup, sorted(set(institution_of.values()) | {""}))
    tax: dict[str, list[Fraction | None]] = {asset: [None] * size for asset in dailies}
    warned: dict[str, list[bool]] = {asset: [False] * size for asset in dailies}
    blocked_days = approximated_days = 0
    last_items: list[tuple[Any, str, str, Fraction]] = []
    for position, day in enumerate(days):
        year = int(day[:4])
        if not ready(year):
            for asset in dailies:
                if dailies[asset].value[position] is None:
                    continue
                if uncovered(year):
                    tax[asset][position] = costs[asset]["tax"][position]
                    warned[asset][position] = costs[asset]["warned"][position]
            if not uncovered(year):
                blocked_days += 1
            continue
        items: list[tuple[Any, str, str, Fraction]] = []
        owners: dict[Any, str] = {}
        stopped: set[str] = set()
        for asset, daily in dailies.items():
            if daily.value[position] is None:
                continue
            account = holdings.get(asset, {}).get(position, "")
            if account is None and accounts_of.get(asset):
                for key in accounts_of[asset]:
                    if account_dailies[key].value[position] is None:
                        continue
                    taxable, bucket = account_costs[key]["taxable"][position], account_costs[key]["bucket"][position]
                    if taxable is None:
                        stopped.add(asset)
                    elif bucket is not None and taxable != 0:
                        items.append((key, institution_of.get(key[1], ""), bucket, taxable)); owners[key] = asset
                continue
            if account is None:
                approximated_days += 1
            taxable, bucket = costs[asset]["taxable"][position], costs[asset]["bucket"][position]
            if taxable is None:
                stopped.add(asset)
            elif bucket is not None and taxable != 0:
                items.append((asset, institution_of.get(account or "", ""), bucket, taxable)); owners[asset] = asset
        shares = calculator.day(day, items)
        if shares is None:
            blocked_days += 1
            continue
        per_asset: dict[str, Fraction] = {}
        for key, share in shares.items():
            per_asset[owners[key]] = per_asset.get(owners[key], Fraction(0)) + share
        for asset, daily in dailies.items():
            if daily.value[position] is None or asset in stopped:
                continue
            tax[asset][position] = round12(per_asset.get(asset, Fraction(0)))
        if position == size - 1:
            last_items = items
    cost = {asset: [None if tax[asset][position] is None or costs[asset]["fee"][position] is None and dailies[asset].value[position] != 0
                    else (costs[asset]["fee"][position] or Fraction(0)) + tax[asset][position] for position in range(size)] for asset in dailies}
    # Realisiert und Ertraege je Topf; in Jahren ohne Rechnung je Topf die Steuer je Ereignis wie bisher.
    conservative_realized, conservative_income, conservative_warned = _daily_taxes(state, days, ledger)
    zero = [Fraction(0)] * size
    realized: dict[str, list[Fraction | None]] = {}
    income: dict[str, list[Fraction | None]] = {}
    for target, source in ((realized, conservative_realized), (income, conservative_income)):
        for asset, values in source.items():
            target[asset] = [Fraction(0) if ready(int(days[position][:4])) else values[position] for position in range(size)]
    opaque_asset = {opaque_ref_v1(state.seed, "asset|" + asset): asset for asset in set(state.asset_ids) | set(dailies)}
    index_of = {day: position for position, day in enumerate(days)}
    interest = [Fraction(0)] * size
    for row in state.realized["interest"]:
        position = index_of.get(row["day"])
        if position is None or ready(int(row["day"][:4])) or not interest_inside(row["account"]):
            continue
        amount = _fraction(row["tax"])
        interest[position] = None if amount is None or interest[position] is None else interest[position] + amount
    for year, entry in years.items():
        if entry.get("status") != "ready":
            continue
        for item in entry["items"]:
            position = index_of.get(item["day"])
            if position is None:
                continue
            amount = _fraction(item.get("tax"))
            if item["kind"] == "interest":
                if interest_inside(item.get("account") or ""):
                    interest[position] = None if amount is None or interest[position] is None else interest[position] + amount
                continue
            asset = opaque_asset.get(item["asset"])
            if asset is None:
                continue
            target = realized if item["kind"] == "disposal" else income
            values = target.setdefault(asset, list(zero))
            values[position] = None if amount is None or values[position] is None else values[position] + amount
    for asset, values in conservative_warned.items():
        if asset in warned:
            warned[asset] = [left or (right and not ready(int(days[position][:4]))) for position, (left, right) in enumerate(zip(warned[asset], values))]
    # Gegenprobe am letzten Tag: Das Modul rechnet das Jahr samt gedachtem Verkauf selbst.
    check: dict[str, Any] = {"checked_day": None, "mismatch": None}
    last_year = int(days[-1][:4])
    available = True
    if ready(last_year):
        totals = calculator.totals(days[-1], last_items)
        entry = years[last_year]
        rows = [{"event_ref": "evr_" + hashlib.sha256(f"{state.seed}|{item['ref']}".encode("utf-8")).hexdigest()[:32], "tax_bucket": item["bucket"],
                 "taxable_contribution_decimal": item["taxable"], "realized_gross_gain_decimal": item["taxable"], "gross_income_decimal": "0",
                 "currency": "EUR", "institution_key": item["institution"]} for item in entry["items"] if item["day"] <= days[-1]]
        for number, (_, institution, bucket, taxable) in enumerate(last_items):
            text = dec12(taxable)
            rows.append({"event_ref": "evr_" + hashlib.sha256(f"{state.seed}|liquidation|{number}".encode("utf-8")).hexdigest()[:32],
                         "tax_bucket": bucket, "taxable_contribution_decimal": text, "realized_gross_gain_decimal": text, "gross_income_decimal": "0",
                         "currency": "EUR", "institution_key": institution})
        from workers.reference.portfolio_history_pool_v1 import _module_check
        detail = _module_check(state.setup, rows, entry["parameters"], last_year, runner)
        if totals is None or detail is None:
            available, check["mismatch"] = False, "tax_module_unavailable"
        else:
            theirs = sum((_fraction(item[bucket]["projected_annual_tax_decimal"]) or Fraction(0) for item in detail.get("institutions") or []
                          for bucket in CAPITAL_BUCKETS), Fraction(0)) + sum((_fraction(detail[bucket]["projected_annual_tax_decimal"]) or Fraction(0)
                                                                             for bucket in ("private_disposal", "other_income")), Fraction(0))
            check["checked_day"] = days[-1]
            if abs(theirs - totals[1]) > Fraction(1, 10 ** 4):
                available, check["mismatch"] = False, "tax_module_mismatch"
    return {"available": available, "status": "ready" if available else "unavailable", "reason": None if available else check["mismatch"],
            "tax": tax, "cost": cost, "warned": warned, "realized": realized, "income": income, "interest": interest,
            "blocked_days": blocked_days, "approximated_days": approximated_days, **check}


def account_net_v1(state: NetState, days: Sequence[str], account_dailies: Mapping[tuple[str, str], Any], ledger: Sequence[Mapping[str, Any]],
                   fifo_events: Mapping[str, Mapping[str, Any]], available: bool = True) -> dict[tuple[str, str], dict[str, Any]]:
    """Netto je Asset und Konto (#499): Liquidationskosten je Tag aus den Losen des Kontos, Steuer der Verkaeufe und Ertraege auf
    dem Konto. Dieselben Regeln wie je Asset; die Gegenprobe am letzten Tag gilt fuer das Asset und damit auch hier."""
    if not available or state.status != "ready" or not account_dailies:
        return {}
    account_of = {ref: entry.get("account") for ref, entry in fifo_events.items()}
    ladders = account_ladders_v1(state.fifo["lots"], account_of, state.trace["moves"], state.trace["adjustments"], state.dates,
                                 state.trace.get("wallets"))
    costs = liquidation_costs_v1(days, account_dailies, state.setup, state.fee_rates, state.fee_fallback, {}, state.dates,
                                 ladder_of=_wallet_ladder_of(ladders, state.trace.get("wallets")), asset_of=lambda key: key[0])
    realized_tax, income_tax, tax_warned = _daily_taxes(state, days, ledger, key_of=lambda row: (row["asset_id"], row["account_id"]))
    size = len(days)
    zero = [Fraction(0)] * size
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for key, daily in account_dailies.items():
        cost = costs[key]["cost"]
        own = tax_warned.get(key)
        warned = [costs[key]["warned"][position] or bool(own and own[position]) for position in range(size)]
        realized = realized_tax.get(key, zero)
        steps, cumulative, tax_sum, known = [], Fraction(0), Fraction(0), True
        for position in range(size):
            if daily.parts["realized"][position]:
                cumulative += daily.parts["realized"][position]
                tax = realized[position]
                known = known and tax is not None
                tax_sum += tax or Fraction(0)
                steps.append({"day": days[position], "tax": _text(tax), "realized_net_cumulative": _text(cumulative - tax_sum) if known else None})
        result[key] = {"cost_by_day": cost, "parts": cost_parts_v1(daily.value, cost), "realized_tax": realized, "income_tax": income_tax.get(key, zero),
                       "warned": warned, "realized_net_steps": steps, "reason": costs[key]["reason"], "blocked_days": costs[key]["blocked_days"],
                       "warned_days": sum(warned), "fee_rate": _text(costs[key]["fee_rate"]), "fee_source": costs[key]["fee_source"]}
    return result


def net_apply_v1(state: NetState, days: Sequence[str], perf: Mapping[str, Any], ledger: Sequence[Mapping[str, Any]],
                 class_of: Callable[[str], str], investment_periods: Sequence[list[dict[str, Any]]], interest_inside: Callable[[str], bool],
                 runner: Callable[..., Any] | None = None, interest_gross: Sequence[Fraction] | None = None,
                 extra_groups: Mapping[str, tuple[Sequence[str], dict[str, Any]]] | None = None,
                 holdings: Mapping[str, Mapping[int, str | None]] | None = None, institution_of: Mapping[str, str] | None = None,
                 account_dailies: Mapping[tuple[str, str], Any] | None = None, fifo_events: Mapping[str, Mapping[str, Any]] | None = None,
                 pool_runner: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Die Netto-Sicht: Liquidationskosten je Asset und Tag, Netto-Teile der Bruecke je Zeitraum (Asset, Klasse, Anlage),
    Netto-Stufen des Realisierten und die Projektionsdaten. Haengt die Bruecke an die Zeitraumzeilen; gibt den Rest zurueck.

    Zwei Sichten (#501): 'net' je Asset ohne Verrechnung (die vorsichtige Obergrenze) und 'net_pooled' je Topf im Jahr - die
    Vorgabe der Analyse. Faellt die Rechnung je Topf aus, bleibt die Sicht je Asset und 'net_pooled' steht als nicht verfuegbar."""
    dailies = perf["dailies"]
    size = len(days)
    last = days[-1]
    block: dict[str, Any] = {"status": state.status, "reason": None if state.status == "ready" else state.status,
                             "module": {"plugin_id": PLUGIN_ID}, "checked_day": None, "years": [], "fee_rate_portfolio": _text(state.fee_fallback),
                             "realized": state.realized}
    assets: dict[str, dict[str, Any]] = {}
    classes: dict[str, dict[str, Any]] = {}
    extra: dict[str, dict[str, Any]] = {}
    investment: dict[str, Any] = {"cost": None}
    lots_of = state.fifo["lots"]
    year_of_last = int(last[:4])
    setup = state.setup
    rates_last = year_rates_v1(setup, year_of_last) if state.status == "ready" else {"covered": False}
    available = state.status == "ready"
    costs: dict[str, dict[str, Any]] = {}
    if available:
        block["years"] = [{"tax_year": year, "status": state.realized["years"].get(str(year), "absent")} for year in sorted(
            {int(day[:4]) for day in days})]
        costs = liquidation_costs_v1(days, dailies, setup, state.fee_rates, state.fee_fallback, lots_of, state.dates, state.trace["adjustments"],
                                     pooled=True)
        # Gegenprobe: Am letzten Tag rechnet das Modul die hypothetische Liquidation selbst - nicht in einem Jahr, das nicht zur
        # Veranlagung zaehlt (#501): Dort rechnet die Netto-Sicht bewusst ohne Steuer.
        block["not_assessed_years"] = sorted(setup.get("not_assessed", ()))
        rows, mine = [], {}
        for asset, daily in sorted(dailies.items()):
            value = daily.value[-1]
            if value is None or (value == 0 and daily.basis[-1] == 0):
                continue
            fee = costs[asset]["fee"][-1]
            ref = "psr_" + hashlib.sha256(f"{state.seed}|{asset}".encode("utf-8")).hexdigest()[:32]
            remaining = [entry for entry in lots_of.get(asset, []) if entry["remaining_quantity"] > 0]
            market, cost_text = dec12(value), dec12(daily.basis[-1])
            rows.append({"position_ref": ref, "asset_ref": setup["asset_ref"](asset), "account_ref": "acr_" + "0" * 32, "currency": "EUR",
                         "market_value_decimal": market, "fifo_cost_decimal": cost_text,
                         "unrealized_gross_gain_decimal": format((Decimal(market) - Decimal(cost_text)).normalize(), "f"),
                         "liquidation_fee_decimal": dec12(fee or Fraction(0)),
                         "remaining_lots": [{"quantity_decimal": dec12(entry["remaining_quantity"]), "fifo_cost_decimal": dec12(entry["remaining_basis"]),
                                             "acquisition_local_date": entry["acquired"] or state.dates.get(entry["acquisition_event_ref"])}
                                            for entry in remaining]})
            mine[ref] = (costs[asset]["tax"][-1], costs[asset]["reason"] if costs[asset]["tax"][-1] is None else None)
        try:
            module = cross_check_v1(setup, last, rows, runner) if year_of_last not in setup.get("not_assessed", ()) else {}
            if year_of_last in setup.get("not_assessed", ()):
                mine = {}
        except Exception:
            module = None
        if module is None:
            available, block["status"], block["reason"] = False, "unavailable", "tax_module_unavailable"
        else:
            mismatches = 0
            for ref, (tax, code) in mine.items():
                other_tax, other_code = module.get(ref, (None, "missing"))
                if tax is None:
                    mismatches += other_tax is not None
                elif other_tax is None or abs(exact_amount_v1(str(other_tax)) - tax) > CHECK_TOLERANCE:
                    mismatches += 1
            block["checked_day"], block["checked_positions"], block["mismatches"] = last, len(rows), mismatches
            if mismatches:
                available, block["status"], block["reason"] = False, "unavailable", "tax_module_mismatch"
        from migrations.reference.tax_model_plugin_v1 import tax_plugin_manifest_v1
        manifest = tax_plugin_manifest_v1(PLUGIN_ID)
        block["module"] = {"plugin_id": PLUGIN_ID, "plugin_version": manifest.plugin_version, "rules_fingerprint": manifest.rules_fingerprint}
    tax_realized, tax_income, tax_warned = _daily_taxes(state, days, ledger) if available else ({}, {}, {})
    pooled: dict[str, Any] = {"available": False, "status": "unavailable", "reason": "net_unavailable"}
    if available:
        try:
            pooled = pooled_net_v1(state, days, dailies, costs, ledger, interest_inside, holdings, institution_of, account_dailies, fifo_events,
                                   pool_runner)
        except Exception:
            pooled = {"available": False, "status": "unavailable", "reason": "pool_failed"}
    pool_ok = bool(pooled.get("available"))
    block["pool"] = {**{key: value for key, value in state.pool.items() if key != "years"},
                     "years": state.pool.get("years") or {}, "status": pooled.get("status"), "reason": pooled.get("reason"),
                     "checked_day": pooled.get("checked_day"), "blocked_days": pooled.get("blocked_days"),
                     "approximated_days": pooled.get("approximated_days"), "available": pool_ok}

    def warned_of(asset: str) -> list[bool]:
        own = tax_warned.get(asset)
        cost_warned = costs[asset]["warned"]
        return [cost_warned[position] or bool(own and own[position]) for position in range(size)]

    warned_years: set[int] = set()
    groups: dict[str, list[str]] = {}
    for asset in dailies:
        groups.setdefault(class_of(asset), []).append(asset)
    zero = [Fraction(0)] * size
    for asset, daily in dailies.items():
        entry: dict[str, Any] = {}
        remaining = lots_of.get(asset, [])
        total = sum((lot["remaining_quantity"] for lot in remaining), Fraction(0))
        held = daily.value[-1] is not None and total > 0
        if available:
            cost = costs[asset]["cost"]
            parts = cost_parts_v1(daily.value, cost)
            realized_tax = tax_realized.get(asset, zero)
            income_tax = tax_income.get(asset, zero)
            warned = warned_of(asset)
            warned_years.update(int(days[position][:4]) for position in range(size) if warned[position])
            with_net_v1(perf["assets"][asset]["periods"], days, realized_tax, income_tax, parts, warned=warned)
            steps, cumulative, tax_sum, known = [], Fraction(0), Fraction(0), True
            for position in range(size):
                if daily.parts["realized"][position]:
                    cumulative += daily.parts["realized"][position]
                    tax = realized_tax[position]
                    known = known and tax is not None
                    tax_sum += tax or Fraction(0)
                    steps.append({"day": days[position], "tax": _text(tax), "realized_net_cumulative": _text(cumulative - tax_sum) if known else None})
            entry = {"cost_by_day": cost, "realized_net_steps": steps, "reason": costs[asset]["reason"], "blocked_days": costs[asset]["blocked_days"],
                     "warned_days": sum(warned),
                     "fee_rate": _text(costs[asset]["fee_rate"]), "fee_source": costs[asset]["fee_source"]}
            if pool_ok:
                cost_p = pooled["cost"][asset]
                realized_p = pooled["realized"].get(asset, zero)
                with_net_v1(perf["assets"][asset]["periods"], days, realized_p, pooled["income"].get(asset, zero), cost_parts_v1(daily.value, cost_p),
                            warned=pooled["warned"][asset], field="net_pooled")
                entry["cost_by_day_pooled"] = cost_p
                entry["realized_net_steps_pooled"] = _net_steps(days, daily.parts["realized"], realized_p)
            else:
                with_net_v1(perf["assets"][asset]["periods"], days, [], [], [], available=False, field="net_pooled")
        if held:
            # Der Kurs je Einheit am letzten Tag: Wert durch Menge - so wie im Wert gerechnet.
            price = daily.value[-1] / total
            cls = classification_v1(setup, setup["asset_ref"](asset), year_of_last) if state.status == "ready" else None
            fee_rate = state.fee_rates.get(asset, state.fee_fallback)
            source = "asset" if asset in state.fee_rates else ("portfolio" if state.fee_fallback is not None else "none")
            by_account = state.trace["lots"].get(asset, {})
            # Eine FIFO-Wallet aus mehreren Konten (#508) traegt ihre Lose unter dem Hauptkonto und heisst wie im Steuerreport.
            from workers.reference.portfolio_history_accounts_v1 import wallet_label_v1
            wallets = state.trace.get("wallets") or {}
            accounts = [(wallet_label_v1(state.trace["labels"], wallets, account) if account in set(wallets.values())
                         else state.trace["labels"].get(account, account), entries, state.trace["methods"].get((asset, account), "fifo"))
                        for account, entries in by_account.items()]
            projection = projection_v1(accounts, price, total, fee_rate, source, cls, rates_last, last)
            if state.status != "ready":
                projection["tax"] = {"status": state.status}
            entry["projection"] = projection
        assets[asset] = entry
    if available:
        everything_cost = [Fraction(0)] * size
        everything_parts = [Fraction(0)] * size
        all_realized = [Fraction(0)] * size
        all_income = [Fraction(0)] * size
        all_warned = [False] * size
        # Klassen zaehlen in die Anlage; eigene Gruppen (#483 Stufe 2) bekommen dieselbe Rechnung, ohne zu zaehlen.
        jobs = [(group, members, perf["classes"].get(group), True) for group, members in groups.items()]
        jobs += [(key, [asset for asset in members if asset in dailies], row, False) for key, (members, row) in (extra_groups or {}).items()]
        everything_cost_p = [Fraction(0)] * size
        everything_parts_p = [Fraction(0)] * size
        all_realized_p = [Fraction(0)] * size
        all_income_p = [Fraction(0)] * size
        all_warned_p = [False] * size
        for group, members, row, counts in jobs:
            if pool_ok:
                cost_p, parts_p = group_cost_v1([(dailies[asset].value, pooled["cost"][asset]) for asset in members], size)
                realized_p = [Fraction(0)] * size
                income_p = [Fraction(0)] * size
                warned_p = [False] * size
                for asset in members:
                    _add(realized_p, pooled["realized"].get(asset))
                    _add(income_p, pooled["income"].get(asset))
                    warned_p = [left or right for left, right in zip(warned_p, pooled["warned"][asset])]
                if row is not None:
                    with_net_v1(row["periods"], days, realized_p, income_p, parts_p, warned=warned_p, field="net_pooled")
                if counts:
                    _add(everything_cost_p, cost_p)
                    _add(everything_parts_p, parts_p)
                    _add(all_realized_p, realized_p)
                    _add(all_income_p, income_p)
                    all_warned_p = [left or right for left, right in zip(all_warned_p, warned_p)]
            elif row is not None:
                with_net_v1(row["periods"], days, [], [], [], available=False, field="net_pooled")
            cost, parts = group_cost_v1([(dailies[asset].value, costs[asset]["cost"]) for asset in members], size)
            realized = [Fraction(0)] * size
            income = [Fraction(0)] * size
            group_warned = [False] * size
            for asset in members:
                _add(realized, tax_realized.get(asset))
                _add(income, tax_income.get(asset))
                group_warned = [left or right for left, right in zip(group_warned, warned_of(asset))]
            steps = []
            if row is not None:
                with_net_v1(row["periods"], days, realized, income, parts, warned=group_warned)
                # Realisiert netto je Klasse: kumulierte realisierte GuV minus die Steuer der Verkaeufe bis dahin.
                tax_sum, known, index_of_day = Fraction(0), True, {day: position for position, day in enumerate(days)}
                previous = 0
                for step in row["realized_steps"]:
                    position = index_of_day[step["day"]]
                    for inner in range(previous, position + 1):
                        known = known and realized[inner] is not None
                        tax_sum += realized[inner] or Fraction(0)
                    previous = position + 1
                    steps.append({"day": step["day"], "realized_net_cumulative": _text(_fraction(step["realized_cumulative"]) - tax_sum) if known else None})
            pooled_entry = {}
            if pool_ok:
                pooled_entry = {"cost_by_day_pooled": cost_p,
                                "realized_net_steps_pooled": _group_steps(days, row["realized_steps"], realized_p) if row is not None else []}
            if not counts:
                extra[group] = {"cost_by_day": cost, "realized_net_steps": steps, **pooled_entry}
                continue
            classes[group] = {"cost_by_day": cost, "realized_net_steps": steps, **pooled_entry}
            all_warned = [left or right for left, right in zip(all_warned, group_warned)]
            _add(everything_cost, cost)
            _add(everything_parts, parts)
            _add(all_realized, realized)
            _add(all_income, income)
        # Zinsen der Konten in der Anlage: ihre Steuer mindert die Ertraege der Anlage.
        index_of = {day: position for position, day in enumerate(days)}
        for row in state.realized["interest"]:
            position = index_of.get(row["day"])
            if position is None or not interest_inside(row["account"]):
                continue
            tax = _fraction(row["tax"])
            all_income[position] = None if tax is None or all_income[position] is None else all_income[position] + tax
        # Zinsen in Jahren ohne Regeln des Moduls (vor 2020, #496): netto = brutto, mit Warnhinweis.
        for position, amount in enumerate(interest_gross or []):
            if amount and int(days[position][:4]) not in setup["covered"]:
                all_warned[position] = True
                warned_years.add(int(days[position][:4]))
        for periods in investment_periods:
            with_net_v1(periods, days, all_realized, all_income, everything_parts, warned=all_warned)
        investment["cost"] = everything_cost
        if pool_ok:
            _add(all_income_p, pooled["interest"])
            for position, amount in enumerate(interest_gross or []):
                if amount and (int(days[position][:4]) not in setup["covered"]):
                    all_warned_p[position] = True
            for periods in investment_periods:
                with_net_v1(periods, days, all_realized_p, all_income_p, everything_parts_p, warned=all_warned_p, field="net_pooled")
            investment["cost_pooled"] = everything_cost_p
        else:
            for periods in investment_periods:
                with_net_v1(periods, days, [], [], [], available=False, field="net_pooled")
    else:
        for periods in [*(perf["assets"][asset]["periods"] for asset in perf["assets"]),
                        *(row["periods"] for row in perf["classes"].values()), *investment_periods,
                        *(row["periods"] for _, row in (extra_groups or {}).values())]:
            with_net_v1(periods, days, [], [], [], available=False)
            with_net_v1(periods, days, [], [], [], available=False, field="net_pooled")
    block["available"] = available
    block["warning_years"] = sorted(warned_years) if available else []
    return {"block": block, "assets": assets, "classes": classes, "groups": extra, "investment": investment, "available": available}


__all__ = ["NetState", "net_apply_v1", "pooled_net_v1", "liquidation_taxable_v1", "sheet_models_v1", "CLASS_MODELS", "NET_VERSION", "PLUGIN_ID", "anniversary", "classification_v1", "cost_parts_v1", "cross_check_v1",
           "fee_rates_v1", "fifo_lots_v1", "lot_trace_v1", "account_ladders_v1", "account_net_v1", "group_cost_v1", "legal_values_v1", "liquidation_costs_v1", "opaque_ref_v1",
           "projection_v1", "realized_taxes_v1", "round12", "tax_inputs_fingerprint_v1", "tax_setup_v1", "unrealized_tax_v1",
           "with_net_v1", "year_rates_v1"]
