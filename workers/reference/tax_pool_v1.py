"""Topf-Rechnung der Netto-Sicht (#501): die Jahresrechnung des Regelmoduls (`realized_annual`) in Python nachgebildet.

Die Netto-Sicht braucht die Steuer eines Jahres nicht einmal, sondern fuer jeden Tag: Was kostete es zusaetzlich, wenn an
diesem Tag alles verkauft wuerde - nach dem, was im Jahr schon realisiert ist (Festlegung 22.10.2026)? Das Regelmodul
dafuer tausendfach aufzurufen, waere zu langsam. Deshalb rechnet dieses Modul dieselben Schritte nach:

- **Kapitalertraege je Institut** (§ 43a Abs. 3, § 44a Abs. 2 EStG): Das Jahr gleicht sich in sich aus; Aktienverluste
  mindern nur Aktiengewinne (§ 20 Abs. 6 Satz 4), andere Verluste alle positiven Kapitalertraege. Dann die Vortraege,
  zuletzt der Freistellungsauftrag - erst gegen die allgemeinen Ertraege, dann gegen Aktiengewinne. Anrechenbare
  Quellensteuer mindert die Steuer vor Solidaritaetszuschlag und Kirchensteuer.
- **Private Veraeusserungsgeschaefte und sonstige Einkuenfte** (§ 23 Abs. 3, § 22 Nr. 3 EStG): Saldo des Jahres; unter der
  Freigrenze steuerfrei und der Vortrag bleibt, ab der Freigrenze mindert der Vortrag, Steuer mit dem persoenlichen Satz.

Die Publikation prueft die Nachbildung Jahr fuer Jahr gegen die Jahresrechnung des Moduls; weicht sie ab, gibt es die Sicht
je Topf nicht (nie still falsch).

**Verteilung je Ereignis und Position** (Festlegung 22.10.2026): Jeder Posten traegt seinen Betrag mal Satz - ein Verlust
also eine negative Steuer, die er anderswo spart. Der Unterschied zur Steuer des Topfs (Freistellung, Freigrenze, Vortraege,
nicht nutzbare Verluste) wird anteilig verteilt: Mindert er die Steuer, geht er an die Posten mit Gewinn; erhoeht er sie
gegenueber der Summe, an die Posten mit Verlust (ihr Verlust spart dann weniger). So liegt jeder Gewinn zwischen null und
seiner vollen Steuer, jeder Verlust zwischen seiner vollen Ersparnis und null, und die Summe ist die Steuer des Topfs.

Liest nichts, schreibt nichts. Projektion, keine Steuerberechnung.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import Any, Hashable, Iterable, Mapping, Sequence

CAPITAL_BUCKETS = ("capital_equity", "capital_general")
PERSONAL_BUCKETS = ("private_disposal", "other_income")
BUCKETS = (*CAPITAL_BUCKETS, *PERSONAL_BUCKETS)
OPENING_CODES = {
    "capital_equity": "opening_equity_loss_carryforward", "capital_general": "opening_general_capital_loss_carryforward",
    "private_disposal": "opening_private_disposal_loss_carryforward", "other_income": "opening_other_income_loss_carryforward",
}
ZERO = Fraction(0)


def _number(value: Any) -> Fraction:
    if value is None or value == "":
        return ZERO
    if isinstance(value, Fraction):
        return value
    return Fraction(Decimal(str(value)))


def _param(parameters: Sequence[Mapping[str, Any]], year: int, code: str, field: str, key: str | None = None) -> Any:
    """Wie das Modul: genau ein Eintrag des Jahres - ohne Institut, oder mit genau diesem Institut."""
    found = [row for row in parameters if int(row["tax_year"]) == year and row["parameter_code"] == code
             and (row.get("institution_key") is None if key is None else row.get("institution_key") == key)]
    if len(found) != 1 or found[0].get(field) is None:
        return None
    return found[0][field]


def resolve_parameters_v1(parameters: Sequence[Mapping[str, Any]], year: int, legal: Mapping[tuple[int, str], Fraction],
                          covered: Iterable[int], keys: Iterable[str] = ()) -> dict[str, Any]:
    """Die Werte eines Jahres, wie das Modul sie liest: Saetze (eingetragen vor Gesetz), Freigrenzen, Vortraege, je Institut
    Freistellungsauftrag, Vortraege und Quellensteuer. 'keys' sind die Institute der Posten des Jahres - auch "" (ohne
    Institut): Wie im Modul rechnet das Jahr je Institut, sobald ein Posten einen Institutsschluessel traegt."""
    keys = list(keys)
    def rate(code: str) -> Fraction | None:
        own = _param(parameters, year, code, "rate_decimal")
        return _number(own) if own is not None else legal.get((year, code))

    def amount(code: str) -> Fraction | None:
        own = _param(parameters, year, code, "amount_decimal")
        return _number(own) if own is not None else legal.get((year, code))

    applicable = _param(parameters, year, "church_tax_applicable", "applicability_value")
    church_rate = _param(parameters, year, "church_tax_rate", "rate_decimal")
    if applicable not in ("applicable", "not_applicable"):
        church: Any = ("blocked", "church_tax_applicability_required")
    elif applicable == "not_applicable":
        church = ("not_applicable", ZERO)
    elif church_rate is None:
        church = ("blocked", "church_tax_rate_required")
    else:
        church = ("applicable", _number(church_rate))
    keyed = {row["institution_key"] for row in parameters if int(row["tax_year"]) == year and row.get("institution_key") is not None}
    grouped = bool(keyed) or bool(keys)
    groups: dict[str, dict[str, Fraction]] = {}
    for key in sorted(keyed | {key for key in keys if grouped}):
        groups[key] = {name: _number(_param(parameters, year, code, "amount_decimal", key)) for name, code in (
            ("opening_equity", OPENING_CODES["capital_equity"]), ("opening_general", OPENING_CODES["capital_general"]),
            ("allowance", "capital_income_allowance"), ("withholding", "creditable_foreign_withholding_tax"))}
    if not grouped:
        allowance = _number(_param(parameters, year, "capital_income_allowance", "amount_decimal")) - _number(
            _param(parameters, year, "externally_used_capital_income_allowance", "amount_decimal"))
        groups[""] = {"opening_equity": _number(_param(parameters, year, OPENING_CODES["capital_equity"], "amount_decimal")),
                      "opening_general": _number(_param(parameters, year, OPENING_CODES["capital_general"], "amount_decimal")),
                      "allowance": max(allowance, ZERO),
                      "withholding": _number(_param(parameters, year, "creditable_foreign_withholding_tax", "amount_decimal"))}
    return {
        "year": year, "covered": year in set(covered), "grouped": grouped, "groups": groups,
        "personal": {bucket: _number(_param(parameters, year, OPENING_CODES[bucket], "amount_decimal")) for bucket in PERSONAL_BUCKETS},
        "limits": {"private_disposal": amount("private_disposal_exemption_threshold") or ZERO,
                   "other_income": amount("other_income_exemption_threshold") or ZERO},
        "capital_rate": rate("capital_income_tax_rate"), "personal_rate": rate("personal_income_tax_rate"),
        "soli": rate("solidarity_surcharge_rate"), "church": church,
    }


def surcharge_factor_v1(resolved: Mapping[str, Any]) -> Fraction | None:
    """Zuschlaege auf die Steuer: 1 + Solidaritaetszuschlag + Kirchensteuer (als Anteil); None, wenn ein Satz fehlt."""
    if resolved["soli"] is None or resolved["church"][0] == "blocked":
        return None
    return 1 + resolved["soli"] / 100 + (resolved["church"][1] / 100 if resolved["church"][0] == "applicable" else ZERO)


def bucket_rate_v1(resolved: Mapping[str, Any], bucket: str) -> Fraction | None:
    """Steuer je Euro steuerpflichtigen Betrags in einem Topf, samt Zuschlaegen."""
    factor = surcharge_factor_v1(resolved)
    base = resolved["capital_rate"] if bucket in CAPITAL_BUCKETS else resolved["personal_rate"]
    if factor is None or base is None:
        return None
    return base / 100 * factor


def empty_sums_v1() -> dict[tuple[str, str], list[Fraction]]:
    return {}


def add_to_sums_v1(sums: dict[tuple[str, str], list[Fraction]], key: str, bucket: str, taxable: Fraction) -> None:
    """Ein Posten in die Summen: je (Institut, Topf) positiv und negativ getrennt; persoenliche Toepfe ohne Institut."""
    slot = sums.setdefault(("" if bucket in PERSONAL_BUCKETS else key, bucket), [ZERO, ZERO])
    if taxable < 0:
        slot[1] += taxable
    else:
        slot[0] += taxable


def pots_v1(sums: Mapping[tuple[str, str], Sequence[Fraction]], resolved: Mapping[str, Any]) -> dict[str, Any]:
    """Die Steuer des Jahres je Topf aus den Summen der Posten - Schritt fuer Schritt wie das Modul. 'tax' je Population:
    ('capital', Institut) und ('personal', Topf); 'closing' sind die Vortraege zum 31.12.; 'blocked' der Grund ohne Zahl."""
    def side(key: str, bucket: str) -> tuple[Fraction, Fraction]:
        slot = sums.get((key, bucket))
        return (ZERO, ZERO) if slot is None else (slot[0], slot[1])

    def loss_of(value: Fraction) -> Fraction:
        return -value if value < 0 else ZERO

    grouped = resolved["grouped"]
    keys = sorted(set(resolved["groups"]) | ({key for key, bucket in sums if bucket in CAPITAL_BUCKETS} if grouped else set()))
    if not grouped:
        keys = [""]
    capital: dict[str, dict[str, Any]] = {}
    for key in keys:
        values = resolved["groups"].get(key) or {"opening_equity": ZERO, "opening_general": ZERO, "allowance": ZERO, "withholding": ZERO}
        if grouped:
            equity, general = side(key, "capital_equity"), side(key, "capital_general")
        else:
            equity = tuple(sum((sums[(k, b)][i] for k, b in sums if b == "capital_equity"), ZERO) for i in (0, 1))
            general = tuple(sum((sums[(k, b)][i] for k, b in sums if b == "capital_general"), ZERO) for i in (0, 1))
        opening_equity, opening_general = values["opening_equity"], values["opening_general"]
        share = equity[0] + equity[1]
        share_loss = loss_of(share); share = max(share, ZERO)
        general_net = general[0] + general[1]
        general_loss = loss_of(general_net); general_income = max(general_net, ZERO)
        cross = min(share, general_loss); share -= cross; general_loss -= cross
        share_carry = min(share, opening_equity); share -= share_carry
        general_carry_general = min(general_income, opening_general); general_income -= general_carry_general
        general_carry_share = min(share, opening_general - general_carry_general); share -= general_carry_share
        left = values["allowance"]
        used = min(general_income, left); general_income -= used; left -= used
        used = min(share, left); share -= used
        capital[key] = {"base": {"capital_general": general_income, "capital_equity": share},
                        "closing": {"capital_equity": opening_equity - share_carry + share_loss,
                                    "capital_general": opening_general - general_carry_general - general_carry_share + general_loss},
                        "withholding": values["withholding"]}
    personal: dict[str, dict[str, Fraction]] = {}
    for bucket in PERSONAL_BUCKETS:
        positive, negative = side("", bucket)
        net, opening = positive + negative, resolved["personal"][bucket]
        limit = resolved["limits"][bucket]
        if net <= 0:
            personal[bucket] = {"base": ZERO, "closing": opening + loss_of(net)}
        elif limit > 0 and net < limit:
            personal[bucket] = {"base": ZERO, "closing": opening}
        else:
            carry = min(net, opening)
            personal[bucket] = {"base": net - carry, "closing": opening - carry}
    applicable_capital = any(value["base"][bucket] > 0 for value in capital.values() for bucket in CAPITAL_BUCKETS)
    applicable_personal = any(value["base"] > 0 for value in personal.values())
    factor = surcharge_factor_v1(resolved)
    blocked = None
    if not resolved["covered"]:
        blocked = "tax_year_rules_missing"
    elif (applicable_capital and resolved["capital_rate"] is None) or (applicable_personal and resolved["personal_rate"] is None) \
            or ((applicable_capital or applicable_personal) and resolved["soli"] is None):
        blocked = "tax_rate_required"
    elif (applicable_capital or applicable_personal) and resolved["church"][0] == "blocked":
        blocked = resolved["church"][1]
    tax: dict[tuple[str, str], Fraction] = {}
    if blocked is None:
        for key, value in capital.items():
            credit_left, total = value["withholding"], ZERO
            for bucket in ("capital_general", "capital_equity"):
                base_tax = value["base"][bucket] * resolved["capital_rate"] / 100 if value["base"][bucket] > 0 else ZERO
                credit = min(base_tax, credit_left); credit_left -= credit
                net_tax = base_tax - credit
                total += net_tax * factor if net_tax > 0 else net_tax
            tax[("capital", key)] = total
        for bucket, value in personal.items():
            base_tax = value["base"] * resolved["personal_rate"] / 100 if value["base"] > 0 else ZERO
            tax[("personal", bucket)] = base_tax * factor if base_tax > 0 else ZERO
    return {"tax": tax, "total": None if blocked else sum(tax.values(), ZERO), "blocked": blocked,
            "closing": {"institutions": {key: value["closing"] for key, value in capital.items()} if grouped else {},
                        "personal": {bucket: value["closing"] for bucket, value in personal.items()}},
            "capital": capital, "personal": personal}


def population_of_v1(key: str, bucket: str) -> tuple[str, str]:
    """Wem ein Posten seine Steuer schuldet: Kapitalertraege dem Institut, die uebrigen dem persoenlichen Topf."""
    return ("capital", key) if bucket in CAPITAL_BUCKETS else ("personal", bucket)


def allocate_v1(items: Sequence[tuple[Hashable, Fraction]], total: Fraction) -> dict[Hashable, Fraction]:
    """Verteilt die Steuer einer Population auf ihre Posten. 'items' sind (Schluessel, Betrag mal Satz) - Verluste negativ.

    Mindert die Rechnung des Topfs die Steuer gegenueber der Summe (Freistellung, Freigrenze, Vortrag), geht der Unterschied
    an die Posten mit Gewinn, anteilig an ihrer Steuer; erhoeht sie sie (Verluste, die im Jahr nichts sparen), an die Posten
    mit Verlust, anteilig an ihrer Ersparnis. Gibt es auf der Seite keine Posten, traegt ihn die andere."""
    result = {key: value for key, value in items}
    delta = total - sum(result.values(), ZERO)
    if not result or delta == 0:
        return result
    winners = [(key, value) for key, value in items if value > 0]
    losers = [(key, -value) for key, value in items if value < 0]
    side = winners if delta < 0 else losers
    if not side or sum(weight for _, weight in side) == 0:
        side = losers if delta < 0 else winners
    if not side or sum(weight for _, weight in side) == 0:
        side = [(key, Fraction(1)) for key, _ in items]
    weight_total = sum(weight for _, weight in side)
    for key, weight in side:
        result[key] += delta * weight / weight_total
    return result


__all__ = ["BUCKETS", "CAPITAL_BUCKETS", "OPENING_CODES", "PERSONAL_BUCKETS", "add_to_sums_v1", "allocate_v1", "bucket_rate_v1",
           "empty_sums_v1", "population_of_v1", "pots_v1", "resolve_parameters_v1", "surcharge_factor_v1"]
