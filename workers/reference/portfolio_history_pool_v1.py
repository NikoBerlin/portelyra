"""Netto je Topf im Jahr (#501): Verlustverrechnung, Freistellung, Freigrenzen und Vortraege in der Netto-Sicht.

Festlegungen (22.10.2026):

- **Vorgabe** ist die Rechnung je Topf im Jahr - wie die Jahresrechnung des Abschlusses. Die bisherige Sicht je Asset ohne
  Verrechnung bleibt waehlbar (vorsichtige Obergrenze).
- **Realisiert:** Die Steuer eines Jahres je Topf (Kapitalertraege je Institut, private Veraeusserungsgeschaefte, sonstige
  Einkuenfte) wird auf die Ereignisse verteilt: Jedes traegt Betrag mal Satz, ein Verlust also eine Ersparnis; Freistellung,
  Freigrenze und Vortraege gehen anteilig ein (`tax_pool_v1.allocate_v1`). Die Summe ist die Steuer des Topfs.
- **Unrealisiert:** je Tag die zusaetzliche Steuer, wenn an dem Tag alles verkauft wuerde - nach dem, was im Jahr bis dahin
  realisiert ist, mit verbleibender Freistellung, Freigrenze und Vortraegen. Verteilt auf die Positionen nach derselben Regel.

Die Jahre laufen ab 2020 nacheinander wie in der Jahresrechnung: Vortraege zum 1.1. eingetragen oder aus dem Vorjahr. Jedes
Jahr rechnet zusaetzlich das Regelmodul im Jahresmodus; weicht die Nachbildung ab, gibt es die Sicht je Topf nicht.

Liest nur. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write. Projektion, keine Steuerberechnung.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Hashable, Mapping, Sequence

from workers.reference.tax_pool_v1 import (
    BUCKETS, CAPITAL_BUCKETS, add_to_sums_v1, allocate_v1, bucket_rate_v1, pots_v1, population_of_v1, resolve_parameters_v1,
)

# Teil des Zwischenspeichers: Aendert sich die Rechnung, gilt eine fruehere Topf-Rechnung nicht weiter.
POOL_VERSION = "portfolio_history_pool_v1/2"
FIRST_YEAR = 2020
TOLERANCE = Fraction(1, 10 ** 6)
ZERO = Fraction(0)


def _text(value: Fraction | None) -> str | None:
    if value is None:
        return None
    from migrations.reference.exact_amount_v1 import amount_text_v1
    return amount_text_v1(value)


def _number(value: Any) -> Fraction:
    if value is None or value == "":
        return ZERO
    return value if isinstance(value, Fraction) else Fraction(Decimal(str(value)))


def _module_check(setup: Mapping[str, Any], rows: list[dict[str, Any]], parameters: list[dict[str, Any]], year: int,
                  runner: Callable[..., Any] | None) -> dict[str, Any] | None:
    """Das Regelmodul rechnet das Jahr selbst (Jahresmodus); zurueck kommt sein Pruefteil oder None."""
    from workers.reference.tax_annual_statement_v1 import _run_annual
    configuration = {"portfolio_ref": setup["portfolio_ref"], "context": setup["context"]}
    try:
        _, reconciliation = (runner or _run_annual)(configuration, rows, parameters, year)
    except Exception:
        return None
    detail = reconciliation.get("annual_detail") if isinstance(reconciliation, Mapping) else None
    return detail if isinstance(detail, Mapping) else None


def _matches(detail: Mapping[str, Any], pots: Mapping[str, Any]) -> bool:
    """Stimmen Steuer und Vortraege der Nachbildung mit dem Pruefteil des Moduls?"""
    for entry in detail.get("institutions") or []:
        key = entry.get("institution_key") or ""
        theirs = sum((_number(entry[bucket]["projected_annual_tax_decimal"]) for bucket in CAPITAL_BUCKETS), ZERO)
        if abs(pots["tax"].get(("capital", key), ZERO) - theirs) > TOLERANCE:
            return False
        for bucket in CAPITAL_BUCKETS:
            if detail.get("institution_grouping") and pots["closing"]["institutions"].get(key, {}).get(bucket, ZERO) != _number(
                    entry[bucket]["closing_loss_carryforward_decimal"]):
                return False
    for bucket in ("private_disposal", "other_income"):
        if abs(pots["tax"].get(("personal", bucket), ZERO) - _number(detail[bucket]["projected_annual_tax_decimal"])) > TOLERANCE:
            return False
        if pots["closing"]["personal"][bucket] != _number(detail[bucket]["closing_loss_carryforward_decimal"]):
            return False
    return True


def pool_years_v1(data_space: Path, context: Any, models: Mapping[int, Mapping[str, Any]], setup: Mapping[str, Any], last_year: int,
                  key_of: Callable[[Mapping[str, Any]], tuple[str, str | None, str]], runner: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Je Jahr ab 2020: Parameter samt Vortraegen, die Posten aus den Rechenblaettern und ihre Steuer je Topf.

    'models' sind die Rechenblaetter je Jahr (mit Modulzeilen und Bestandsschluesseln); 'key_of' bildet ein Blatt auf
    (verschleierte Kennung, verschleiertes Asset oder None, Art) ab - dieselben Kennungen wie die Steuer je Ereignis."""
    from migrations.reference.institution_tax_settings_v1 import (
        InstitutionTaxSettingsV1Error, institution_key_v1, read_institution_tax_settings_v1,
    )
    from workers.reference.tax_annual_chain_v1 import annual_parameters_v1, empty_chain_v1, entered_by_year_v1
    if setup.get("status") != "ready":
        return {"version": POOL_VERSION, "status": setup.get("status") or "unavailable", "years": {}}
    try:
        entered_all = entered_by_year_v1(read_institution_tax_settings_v1(Path(data_space), context))
    except InstitutionTaxSettingsV1Error:
        return {"version": POOL_VERSION, "status": "tax_settings_unreadable", "years": {}}
    chain = empty_chain_v1()
    years: dict[str, Any] = {}
    status = "ready"
    for year in range(FIRST_YEAR, last_year + 1):
        if year in setup.get("not_assessed", ()):
            # Zaehlt nicht zur Veranlagung (#501): keine Steuer, die Toepfe laufen unveraendert weiter.
            years[str(year)] = {"status": "not_assessed"}
            continue
        if year not in setup["covered"]:
            years[str(year)] = {"status": "tax_year_rules_missing"}
            status = "tax_year_rules_missing"
            break
        model = models.get(year)
        if model is None or model.get("status") != "ready":
            years[str(year)] = {"status": (model or {}).get("status") or "absent"}
            status = "tax_events_unavailable"
            break
        included = [sheet for sheet in model["sheets"] if sheet["calculation"]["status"] == "calculated" and isinstance(sheet.get("module_row"), dict)
                    and sheet["module_row"]["projection_status"] == "completed"]
        open_count = sum(1 for sheet in model["sheets"] if sheet["calculation"]["status"] == "not_calculated")
        parameters, _ = annual_parameters_v1(setup["parameters"], year, entered_all.get(year, {}), chain)
        rows, items = [], []
        for sheet in included:
            institution = institution_key_v1(sheet["event"].get("institution_label") or "")
            rows.append({**sheet["module_row"], "institution_key": institution})
            # Ein Vorgang ohne Steuerbezug (Topf "not_applicable", Betrag 0) geht ans Modul wie in der Jahresrechnung, wirkt aber
            # auf keinen Topf - er braucht keinen Posten.
            if sheet["module_row"]["tax_bucket"] not in BUCKETS:
                continue
            ref, asset, kind = key_of(sheet)
            items.append({"ref": ref, "asset": asset, "kind": kind, "day": sheet["event"]["local_date"], "bucket": sheet["module_row"]["tax_bucket"],
                          "institution": institution, "taxable": sheet["module_row"]["taxable_contribution_decimal"],
                          "account": sheet["event"].get("account_label") if kind == "interest" else None})
        sums: dict[tuple[str, str], list[Fraction]] = {}
        for item in items:
            add_to_sums_v1(sums, item["institution"], item["bucket"], _number(item["taxable"]))
        resolved = resolve_parameters_v1(parameters, year, setup["legal"], setup["covered"], [item["institution"] for item in items])
        pots = pots_v1(sums, resolved)
        detail = _module_check(setup, rows, parameters, year, runner)
        entry: dict[str, Any] = {"status": "ready", "parameters": parameters, "items": items, "open_count": open_count,
                                 "tax": None if pots["total"] is None else _text(pots["total"])}
        if pots["blocked"] is not None:
            entry["status"] = pots["blocked"]
        elif detail is None:
            entry["status"] = "tax_module_unavailable"
        elif not _matches(detail, pots):
            entry["status"] = "tax_module_mismatch"
        if entry["status"] == "ready":
            shares = _allocate_year(items, pots, resolved)
            for item in items:
                item["tax"] = _text(shares[item["ref"]])
        years[str(year)] = entry
        if entry["status"] != "ready":
            status = entry["status"]
            break
        chain = {"institutions": {key: dict(value) for key, value in pots["closing"]["institutions"].items()},
                 "personal": dict(pots["closing"]["personal"])}
    return {"version": POOL_VERSION, "status": status, "years": years}


def _allocate_year(items: Sequence[Mapping[str, Any]], pots: Mapping[str, Any], resolved: Mapping[str, Any]) -> dict[Hashable, Fraction]:
    """Die Steuer jedes Topfs auf seine Ereignisse verteilt."""
    groups: dict[tuple[str, str], list[tuple[Hashable, Fraction]]] = {}
    for item in items:
        rate = bucket_rate_v1(resolved, item["bucket"]) or ZERO
        groups.setdefault(population_of_v1(item["institution"], item["bucket"]), []).append((item["ref"], rate * _number(item["taxable"])))
    shares: dict[Hashable, Fraction] = {}
    for population, members in groups.items():
        shares.update(allocate_v1(members, pots["tax"].get(population, ZERO)))
    return shares


class PoolDays:
    """Je Tag die zusaetzliche Steuer eines gedachten Verkaufs aller Positionen, nach dem bis dahin Realisierten des Jahres.

    Rechnet die Tage der Reihe nach; je Jahr laufen die realisierten Posten bis zum Tag mit. 'liquidation' ist je Tag eine
    Liste (Schluessel, Institut, Topf, steuerpflichtiger Betrag); zurueck kommt je Schluessel die verteilte Steuer."""

    def __init__(self, pool: Mapping[str, Any], setup: Mapping[str, Any], extra_keys: Sequence[str] = ()):
        self.pool = pool
        self.setup = setup
        self.extra_keys = list(extra_keys)
        self.year: int | None = None
        self.resolved: dict[str, Any] | None = None
        self.items: list[Mapping[str, Any]] = []
        self.cursor = 0
        self.sums: dict[tuple[str, str], list[Fraction]] = {}

    def _enter(self, year: int) -> bool:
        entry = (self.pool.get("years") or {}).get(str(year))
        self.year, self.cursor, self.sums = year, 0, {}
        if not entry or entry.get("status") != "ready":
            self.resolved, self.items = None, []
            return False
        self.items = sorted(entry["items"], key=lambda item: item["day"])
        keys = [item["institution"] for item in self.items] + self.extra_keys
        self.resolved = resolve_parameters_v1(entry["parameters"], year, self.setup["legal"], self.setup["covered"], keys)
        return True

    def day(self, day: str, liquidation: Sequence[tuple[Hashable, str, str, Fraction]]) -> dict[Hashable, Fraction] | None:
        year = int(day[:4])
        if year != self.year:
            self._enter(year)
        if self.resolved is None:
            return None
        while self.cursor < len(self.items) and self.items[self.cursor]["day"] <= day:
            item = self.items[self.cursor]
            add_to_sums_v1(self.sums, item["institution"], item["bucket"], _number(item["taxable"]))
            self.cursor += 1
        without = pots_v1(self.sums, self.resolved)
        with_sums = {key: list(value) for key, value in self.sums.items()}
        for _, institution, bucket, taxable in liquidation:
            add_to_sums_v1(with_sums, institution, bucket, taxable)
        with_all = pots_v1(with_sums, self.resolved)
        if without["total"] is None or with_all["total"] is None:
            return None
        groups: dict[tuple[str, str], list[tuple[Hashable, Fraction]]] = {}
        for key, institution, bucket, taxable in liquidation:
            rate = bucket_rate_v1(self.resolved, bucket) or ZERO
            groups.setdefault(population_of_v1(institution, bucket), []).append((key, rate * taxable))
        shares: dict[Hashable, Fraction] = {}
        for population, members in groups.items():
            increment = with_all["tax"].get(population, ZERO) - without["tax"].get(population, ZERO)
            shares.update(allocate_v1(members, increment))
        return shares

    def totals(self, day: str, liquidation: Sequence[tuple[Hashable, str, str, Fraction]]) -> tuple[Fraction, Fraction] | None:
        """(Steuer des Jahres bis zum Tag, mit gedachtem Verkauf) - fuer die Gegenprobe am letzten Tag."""
        if self.day(day, liquidation) is None:
            return None
        with_sums = {key: list(value) for key, value in self.sums.items()}
        for _, institution, bucket, taxable in liquidation:
            add_to_sums_v1(with_sums, institution, bucket, taxable)
        return pots_v1(self.sums, self.resolved)["total"], pots_v1(with_sums, self.resolved)["total"]


__all__ = ["FIRST_YEAR", "POOL_VERSION", "PoolDays", "pool_years_v1"]
