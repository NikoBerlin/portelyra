"""Nennt den Grund, aus dem ein Entwurf blockiert ist (#420).

Die Pruefung eines Entwurfs haelt nur fest, dass der Kern ablehnte
(`activity_draft_domain_invalid`). Der Kern selbst weiss es genau: Auf dem Weg
zur Oberflaeche wurde aus `semantic_realized_fifo_v2_custody_inventory_insufficient`
erst `asset_activity_correction_fifo_invalid`, dann `activity_draft_domain_invalid`,
dann `data_asset_activity_correction_adapter_failed` - und die Oberflaeche zeigte nur
"Aktion blockiert". Etwa laesst sich ein Kauf nicht auf ein anderes Konto umstellen,
wenn ein spaeterer Verkauf auf dem alten Konto dann zu wenig Stueck vorfaende, und
Rewards bleiben liegen, wenn die Quelle feiner rechnet als die Mengenskala des Assets.

Dieses Modul schreibt nichts und aendert keine Regel. Es ruft dieselbe fachliche
Vorschau noch einmal auf, die die Pruefung aufgerufen hat, und liest den Fehler:

- die Kette der Fehlercodes vom aeusseren bis zum innersten,
- bei fehlendem Verwahrbestand die Buchung, an der es scheitert. Sie wird nicht
  nachgerechnet: Die FIFO-Rechnung selbst bekommt die Buchungen bis zu einem
  Zeitpunkt vorgelegt und sagt, ab wann es nicht mehr aufgeht; der vorhandene
  Bestand stammt aus ihrem letzten gueltigen Ergebnis,
- bei Eingaben, die der Kern fuer diese Buchung nicht annimmt, welche es ist.

Das Ergebnis traegt interne Kennungen von Konto und Asset. Es bleibt im
Serverprozess; die Oberflaeche bildet daraus einen Satz mit Bezeichnungen.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from migrations.reference.desktop_activity_draft_v1 import (
    _domain_preview,
    read_desktop_activity_draft_v1,
)
from migrations.reference.desktop_asset_activity_correction_v1 import (
    DesktopAssetActivityCorrectionV1Error,
)
from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1,
    DesktopProductAssetActivityV1Error,
    read_desktop_product_per_asset_catalog_v1,
)
from workers.reference.semantic_realized_fifo_v2 import (
    SemanticRealizedFifoV2Error,
    project_semantic_realized_fifo_v2,
)

CUSTODY_CODE = "semantic_realized_fifo_v2_custody_inventory_insufficient"
# Derselbe Mangel ohne Kontobezug: Der Bestand des Assets reicht ueber alle Konten nicht.
INVENTORY_CODE = "semantic_realized_fifo_v2_inventory_insufficient"
# Mehrere Buchungen desselben Assets tragen denselben Zeitpunkt; die Reihenfolge fehlt.
ORDER_CODE = "semantic_realized_fifo_v2_order_evidence_required"
DUPLICATE_CODE = "asset_activity_event_duplicate"
AMOUNT_CODE = "asset_activity_amount_invalid"
INPUT_CODE = "asset_activity_input_invalid"
OUTFLOW_TYPES = frozenset({"sell", "withdrawal", "transfer"})
# Was der Kern je Buchungsart annimmt (asset_activity_v1); dieselbe Tabelle, nach
# der sich das Formular richtet (tests/contracts/test_asset_activity_v1.py).
MONETARY_FEE_TYPES = frozenset({"buy", "sell", "transfer"})
ELIGIBLE_QUANTITY_TYPES = frozenset({"dividend"})
REASONS = (
    "custody_inventory_insufficient", "inventory_insufficient", "order_evidence_required",
    "event_duplicate", "quantity_scale_exceeded", "amount_fields_conflict",
    "field_not_accepted", "domain_rejected",
)


def _codes(error: BaseException) -> list[str]:
    """Die Fehlercodes vom aeusseren zum innersten Fehler."""
    codes: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        code = getattr(current, "code", None)
        if isinstance(code, str):
            codes.append(code)
        current = current.__cause__ or current.__context__
    return codes


def _fifo_world(error: BaseException) -> tuple[Mapping[str, Any] | None, str | None]:
    """Die Welt, an der die FIFO-Probe scheiterte, und - bei einer Neuanlage - die
    Kennung, unter der die neue Buchung darin steht."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        world = getattr(current, "fifo_world", None)
        if isinstance(world, Mapping):
            probe_ref = getattr(current, "fifo_probe_event_ref", None)
            return world, probe_ref if isinstance(probe_ref, str) else None
        current = current.__cause__ or current.__context__
    return None, None


def _prefix(world: Mapping[str, Any], events: list[Mapping[str, Any]], until: str | None = None) -> dict[str, Any]:
    refs = {row["event_ref"] for row in events}
    candidate = dict(world)
    candidate["asset_activity"] = {**world["asset_activity"], "events": list(events)}
    if "fifo_order_evidence" in world:
        candidate["fifo_order_evidence"] = [
            row for row in world["fifo_order_evidence"] if row["event_ref"] in refs
        ]
    # Splits (#451) nur bis zum geprueften Tag: Ein spaeterer Split wirkte sonst am Ende des Ausschnitts und naennte den Bestand
    # in neuen Stuecken, die es am geprueften Tag noch nicht gab.
    if "splits" in world:
        kept = [row for row in world["splits"] if until is None or row["effective_local_date"] <= until]
        if kept:
            candidate["splits"] = kept
        else:
            candidate.pop("splits")
    return candidate


def _projected(world: Mapping[str, Any], events: list[Mapping[str, Any]], until: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    if not events:
        return {"custody_positions": []}, None
    try:
        return project_semantic_realized_fifo_v2(_prefix(world, events, until)), None
    except SemanticRealizedFifoV2Error as error:
        return None, error.code


def _available(result: Mapping[str, Any], account_ref: str | None, asset_ref: str) -> Decimal:
    """Der Bestand laut FIFO-Rechnung: auf einem Konto, oder ohne Konto ueber alle."""
    if account_ref is None:
        rows = [row for row in result.get("asset_positions", []) if row.get("asset_ref") == asset_ref]
    else:
        rows = [
            row for row in result.get("custody_positions", [])
            if row.get("account_ref") == account_ref and row.get("asset_ref") == asset_ref
        ]
    return Decimal(rows[0]["remaining_quantity_decimal"]) if rows else Decimal(0)


def _plain(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _shortage_detail(
    world: Mapping[str, Any], changed_event_ref: str | None, shortage_code: str,
) -> dict[str, Any] | None:
    """Die Buchung, ab der der Bestand nicht mehr reicht - von der FIFO-Rechnung bestimmt.

    Erst tageweise: der erste Tag, bis zu dem die Rechnung nicht mehr aufgeht.
    Tragen alle Buchungen dieses Tages eine genaue Zeit, dann innerhalb des Tages
    Buchung fuer Buchung. Ohne genaue Zeiten bleibt es beim Tag: Die Reihenfolge
    innerhalb eines Tages bestimmt die Rechnung, nicht dieses Modul.
    """
    try:
        events = list(world["asset_activity"]["events"])
        days = sorted({row["local_date"] for row in events})
    except (KeyError, TypeError):
        return None
    before: list[Mapping[str, Any]] = []
    valid: dict[str, Any] | None = {"custody_positions": []}
    for day in days:
        through = [row for row in events if row["local_date"] <= day]
        result, code = _projected(world, through, day)
        if result is not None:
            before, valid = through, result
            continue
        if code != shortage_code or valid is None:
            return None
        # Der Bestand zu Beginn des Tages - mit einem Split dieses Tages schon in neuen Stuecken (#451).
        if before and "splits" in world:
            rebased, _ = _projected(world, before, day)
            if rebased is not None:
                valid = rebased
        day_events = [row for row in events if row["local_date"] == day]
        detail: dict[str, Any] = {
            "blocking_local_date": day, "blocking_event": None,
            "available_quantity_decimal": None, "missing_quantity_decimal": None,
            "blocking_event_is_changed_event": None,
        }
        if all(isinstance(row.get("effective_at_utc"), str) for row in day_events):
            ordered = sorted(day_events, key=lambda row: (row["effective_at_utc"], row["event_ref"]))
            reached, last_valid = list(before), valid
            for row in ordered:
                step, step_code = _projected(world, reached + [row], day)
                if step is not None:
                    reached, last_valid = reached + [row], step
                    continue
                if step_code != shortage_code or row["event_type"] not in OUTFLOW_TYPES:
                    break
                try:
                    required = Decimal(row["quantity_decimal"])
                    available = _available(
                        last_valid, row["account_ref"] if shortage_code == CUSTODY_CODE else None, row["asset_ref"],
                    )
                except (InvalidOperation, KeyError, TypeError):
                    break
                detail["blocking_event"] = {
                    "event_type": row["event_type"], "local_date": row["local_date"],
                    "quantity_decimal": row["quantity_decimal"],
                    "account_ref": row["account_ref"], "asset_ref": row["asset_ref"],
                }
                detail["blocking_event_is_changed_event"] = row["event_ref"] == changed_event_ref
                detail["available_quantity_decimal"] = _plain(available)
                # Eine Mengengebuehr kaeme hinzu; dann wird kein Fehlbetrag behauptet.
                if row.get("asset_fee_quantity_decimal") is None and required > available:
                    detail["missing_quantity_decimal"] = _plain(required - available)
                break
        return detail
    return None


def _decimal_places(value: Any) -> int:
    return 0 if value is None else len(str(value).partition(".")[2])


def _input_detail(
    event: Mapping[str, Any], inner_code: str, canonical_path: Path,
    context: DesktopProductAssetActivityContextV1,
) -> tuple[str, dict[str, Any] | None]:
    """Welche Eingabe der Kern fuer diese Buchung nicht annimmt - soweit eindeutig."""
    event_type = event.get("event_type")
    if inner_code == AMOUNT_CODE:
        scale = None
        try:
            for asset in read_desktop_product_per_asset_catalog_v1(canonical_path, context)["assets"]:
                if asset["asset_id"] == event.get("asset_ref"):
                    scale = asset["quantity_scale"]
        except DesktopProductAssetActivityV1Error:
            scale = None
        if isinstance(scale, int):
            for field in ("quantity_decimal", "asset_fee_quantity_decimal", "eligible_quantity_decimal"):
                places = _decimal_places(event.get(field))
                if places > scale:
                    return "quantity_scale_exceeded", {
                        "field": field, "decimal_places": places, "quantity_scale": scale,
                        "asset_ref": event.get("asset_ref"),
                    }
        mode = event.get("amount_input_mode")
        unit_price, gross = event.get("unit_price_decimal") is not None, event.get("gross_amount_decimal") is not None
        expected = {"quantity_unit_price": (True, False), "gross_total": (False, True), "not_applicable": (False, False)}.get(mode)
        if expected is not None and (unit_price, gross) != expected:
            return "amount_fields_conflict", {
                "amount_input_mode": mode, "unit_price_present": unit_price, "gross_amount_present": gross,
            }
    if inner_code in {AMOUNT_CODE, INPUT_CODE} and isinstance(event_type, str):
        if event.get("monetary_fee_decimal") is not None and event_type not in MONETARY_FEE_TYPES:
            return "field_not_accepted", {"field": "monetary_fee_decimal", "event_type": event_type}
        if event.get("eligible_quantity_decimal") is not None and event_type not in ELIGIBLE_QUANTITY_TYPES:
            return "field_not_accepted", {"field": "eligible_quantity_decimal", "event_type": event_type}
    return "domain_rejected", None


def explain_desktop_activity_draft_block_v1(
    canonical_path: str | Path,
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
    draft_ref: str,
) -> dict[str, Any]:
    """Der Grund eines blockierten Entwurfs. Liest nur; schreibt weder Entwurf noch Bestand."""
    draft = read_desktop_activity_draft_v1(data_space_path, context_value, draft_ref)["trusted_draft"]
    validation = draft.get("validation")
    base = {
        "activity_block_reason_version": 1,
        "action_type": draft["action_type"],
        "validation_status": draft.get("validation_status"),
        "reason": None, "codes": [], "detail": None,
        "canonical_write": False, "activity_draft_write": False,
        "provider_access": False, "network_access": False,
    }
    if (
        not isinstance(validation, Mapping) or validation.get("status") != "blocked"
        or validation.get("issue_codes") != ["activity_draft_domain_invalid"]
    ):
        return {**base, "status": "not_blocked"}
    event = dict(draft["event"])
    try:
        _domain_preview(
            draft, event, canonical_path, data_space_path, context_value,
            validation["validated_at_utc"],
        )
    except (DesktopProductAssetActivityV1Error, DesktopAssetActivityCorrectionV1Error) as error:
        codes = _codes(error)
        inner = codes[-1] if codes else None
        if inner in {CUSTODY_CODE, INVENTORY_CODE}:
            world, probe_ref = _fifo_world(error)
            changed = None if draft["action_type"] == "void" else (probe_ref or event.get("event_ref"))
            reason = "custody_inventory_insufficient" if inner == CUSTODY_CODE else "inventory_insufficient"
            detail = None if world is None else _shortage_detail(world, changed, inner)
        elif inner == ORDER_CODE:
            reason, detail = "order_evidence_required", None
        elif inner == DUPLICATE_CODE:
            reason, detail = "event_duplicate", None
        else:
            reason, detail = _input_detail(event, inner or "", Path(canonical_path), context_value)
        return {**base, "status": "explained", "reason": reason, "codes": codes, "detail": detail}
    # Seit der Pruefung hat sich der Bestand geaendert: Dieselbe Vorschau gelingt jetzt.
    return {**base, "status": "no_longer_blocked"}


__all__ = ["REASONS", "explain_desktop_activity_draft_block_v1"]
