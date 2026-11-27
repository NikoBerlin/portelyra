"""Die Kette der Jahresrechnung: Parameter je Jahr und Institut, Verlusttoepfe vom Vorjahr ins Folgejahr.

Jahresrechnung (Tax-App) und Portfolioabschluss rechnen ein Jahr gleich (Festlegung 14.10.2026: Zinsen und
Aufteilung je Institut gehoeren ebenso in die Rechnung des Abschlusses). Was beide gemeinsam brauchen, steht hier:

- welche Parameter das Regelmodul fuer ein Jahr bekommt - die des Steuerspeichers, dazu je Institut der eingetragene
  Freistellungsauftrag, die Quellensteuer und die Verlusttoepfe zum 1.1., wo nichts eingetragen ist der Stand des
  Vorjahres;
- wie aus dem Pruefteil des Moduls (`annual_detail`) der Stand fuer das Folgejahr wird.

Rechnet selbst keine Steuer. Kein Speicherzugriff.
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Any, Mapping, Sequence

from migrations.reference.tax_model_plugin_v2 import INSTITUTION_PARAMETER_CODES

FIRST_YEAR = 2020
# Jahre vor 2020 fuehrt das Modul v2 nur in Grundzuegen (#496, Festlegung 28.10.2026). Die Kette fuer Abschluss und
# Netto-Sicht beginnt weiter 2020; nur eine Jahresrechnung fuer 2016-2019 rechnet ab 2016, eigens und nicht vollstaendig.
PARTIAL_FIRST_YEAR = 2016
CAPITAL_BUCKETS = ("capital_equity", "capital_general")
PERSONAL_BUCKETS = ("private_disposal", "other_income")
OPENING_CODES = {
    "capital_equity": "opening_equity_loss_carryforward", "capital_general": "opening_general_capital_loss_carryforward",
    "private_disposal": "opening_private_disposal_loss_carryforward", "other_income": "opening_other_income_loss_carryforward",
}


def amount_v1(value: Any) -> Fraction:
    return Fraction(0) if value is None else Fraction(str(value))


def text_v1(value: Fraction) -> str:
    """Exakter Dezimaltext; die Betraege der Kette enden alle als Dezimalzahl."""
    with localcontext() as exact:
        exact.prec = 200
        text = format(Decimal(value.numerator) / Decimal(value.denominator), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def empty_chain_v1() -> dict[str, Any]:
    return {"institutions": {}, "personal": {}}


def entered_by_year_v1(settings_model: Mapping[str, Any]) -> dict[int, dict[tuple[str, str], str]]:
    """Die eingetragenen Werte je Jahr und (Institut, Angabe) - ohne verwaiste Angaben."""
    entered: dict[int, dict[tuple[str, str], str]] = {}
    for row in settings_model.get("settings", ()):
        if not row["orphaned"]:
            entered.setdefault(row["tax_year"], {})[(row["institution_key"], row["field_code"])] = row["amount_decimal"]
    return entered


def annual_parameters_v1(base_parameters: Sequence[Mapping[str, Any]], tax_year: int, entered: Mapping[tuple[str, str], str],
                         chain: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Die Parameter des Jahres fuers Regelmodul - und woher jeder Topf zum Jahresbeginn kommt (eingetragen, Vorjahr, keiner).

    Werte ohne Institut, die das Modul je Institut liest, wirken in der Rechnung je Institut nicht und stehen nicht dabei.
    """
    base = [dict(row) for row in base_parameters if row["tax_year"] == tax_year
            and row["parameter_code"] not in INSTITUTION_PARAMETER_CODES and row["parameter_code"] != "externally_used_capital_income_allowance"]
    codes = {row["parameter_code"] for row in base}
    origin: dict[str, Any] = {"institutions": {}}
    for bucket in PERSONAL_BUCKETS:
        code = OPENING_CODES[bucket]
        if code in codes:
            origin[bucket] = "entered"
            continue
        carried = chain["personal"].get(bucket, Fraction(0))
        origin[bucket] = "carried" if carried > 0 else "none"
        if carried > 0:
            base.append({"tax_year": tax_year, "parameter_code": code, "rate_decimal": None, "amount_decimal": text_v1(carried)})
    for key in sorted({key for key, _ in entered} | set(chain["institutions"])):
        sources = {}
        for code in ("capital_income_allowance", "creditable_foreign_withholding_tax"):
            value = entered.get((key, code))
            if value is not None:
                base.append({"tax_year": tax_year, "parameter_code": code, "rate_decimal": None, "amount_decimal": value, "institution_key": key})
        for bucket in CAPITAL_BUCKETS:
            code = OPENING_CODES[bucket]
            value = entered.get((key, code))
            if value is not None:
                sources[bucket] = "entered"
                base.append({"tax_year": tax_year, "parameter_code": code, "rate_decimal": None, "amount_decimal": value, "institution_key": key})
                continue
            carried = chain["institutions"].get(key, {}).get(bucket, Fraction(0))
            sources[bucket] = "carried" if carried > 0 else "none"
            if carried > 0:
                base.append({"tax_year": tax_year, "parameter_code": code, "rate_decimal": None, "amount_decimal": text_v1(carried), "institution_key": key})
        origin["institutions"][key] = sources
    return base, origin


def keyed_v1(rows: Sequence[Mapping[str, Any]], parameters: Sequence[Mapping[str, Any]]) -> bool:
    """Ob das Modul je Institut rechnet: sobald eine Zeile oder ein Parameter einen Institutsschluessel traegt."""
    return any("institution_key" in row for row in rows) or any("institution_key" in row for row in parameters)


def next_chain_v1(detail: Mapping[str, Any], keyed: bool) -> dict[str, Any]:
    """Der Stand zum 31.12. aus dem Pruefteil des Moduls - der Topf zum 1.1. des Folgejahres."""
    institutions = detail["institutions"] if keyed else []
    return {
        "institutions": {entry["institution_key"]: {bucket: amount_v1(entry[bucket]["closing_loss_carryforward_decimal"]) for bucket in CAPITAL_BUCKETS}
                         for entry in institutions},
        "personal": {bucket: amount_v1(detail[bucket]["closing_loss_carryforward_decimal"]) for bucket in PERSONAL_BUCKETS},
    }


def closing_totals_v1(chain: Mapping[str, Any]) -> dict[str, str]:
    """Die Toepfe zum 31.12. je Art, ueber alle Institute zusammengezaehlt."""
    return {
        **{bucket: text_v1(sum((value[bucket] for value in chain["institutions"].values()), Fraction(0))) for bucket in CAPITAL_BUCKETS},
        **{bucket: text_v1(chain["personal"][bucket]) for bucket in PERSONAL_BUCKETS},
    }


__all__ = [
    "CAPITAL_BUCKETS", "FIRST_YEAR", "OPENING_CODES", "PARTIAL_FIRST_YEAR", "PERSONAL_BUCKETS", "amount_v1", "annual_parameters_v1", "closing_totals_v1",
    "empty_chain_v1", "entered_by_year_v1", "keyed_v1", "next_chain_v1", "text_v1",
]
