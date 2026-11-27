"""Query-only Bundle-A dependency, freshness and completeness matrix."""
from __future__ import annotations
import hashlib,json,sqlite3
from pathlib import Path
from typing import Any
from migrations.reference.desktop_product_asset_activity_v1 import DesktopProductAssetActivityContextV1,DesktopProductAssetActivityV1Error,_context,_owner_directory,_owner_file,read_desktop_product_asset_activity_binding_v1
from migrations.reference.desktop_cash_coverage_v1 import DesktopCashCoverageV1Error,read_desktop_cash_coverage_view_v1
from workers.reference.asset_activity_realized_state_v2 import AssetActivityRealizedStateV2Error,read_asset_activity_realized_state_v2

class PortfolioOperationalReadinessV1Error(RuntimeError):
    CODES={"portfolio_readiness_context_invalid","portfolio_readiness_evidence_invalid","portfolio_readiness_boundary_failed"}
    def __init__(self,code):
        if code not in self.CODES:raise ValueError("portfolio_readiness_error_code_unregistered")
        self.code=code;super().__init__(code)
def _abort(code):raise PortfolioOperationalReadinessV1Error(code)
def _canonical(value):return json.dumps(value,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(",",":")).encode()
def _fingerprint(value):return hashlib.sha256(_canonical(value)).hexdigest()
def _runtime(value):
    try:return _context(value)
    except DesktopProductAssetActivityV1Error:_abort("portfolio_readiness_context_invalid")
def _owned_directory(value):
    try:return _owner_directory(value)
    except DesktopProductAssetActivityV1Error:_abort("portfolio_readiness_evidence_invalid")
def _owned_file(value):
    try:return _owner_file(value,"desktop_asset_activity_storage_invalid")
    except DesktopProductAssetActivityV1Error:_abort("portfolio_readiness_evidence_invalid")
def _migration(data_space:Path):
    path=data_space/"noncash-canonical-cutover-v1"/"receipt.json"
    if not path.exists():return None
    path=_owned_file(path)
    try:value=json.loads(path.read_text(encoding="utf-8"))
    except Exception:_abort("portfolio_readiness_evidence_invalid")
    if not isinstance(value,dict) or path.read_bytes()!=_canonical(value)+b"\n" or value.get("noncash_partitioned_canonical_cutover_receipt_version")!=1 or value.get("status")!="completed_incomplete_portfolio" or value.get("receipt_fingerprint") is None:_abort("portfolio_readiness_evidence_invalid")
    body=dict(value);fingerprint=body.pop("receipt_fingerprint")
    if (fingerprint!=_fingerprint(body) or value.get("cash_imported") is not False or value.get("complete_portfolio_claim_authorized") is not False
        or value.get("portfolio_completeness")!="incomplete_quarantined_or_derivative_blocked"
        or not isinstance(value.get("quarantined_component_count"),int) or value["quarantined_component_count"]<0
        or not isinstance(value.get("derivative_blocked_component_count"),int) or value["derivative_blocked_component_count"]<0):_abort("portfolio_readiness_evidence_invalid")
    return value


VALUATION_AREA="market-valuation-v1"
def _valuation(data_space:Path):
    """Alle abgeschlossenen Marktbewertungen lesen, je Asset die juengste.

    Bewertet wird assetweise, also traegt jeder Beleg nur sein Asset. Nur den
    neuesten Beleg zu lesen zaehlte deshalb immer genau ein bewertetes Asset
.

    Fail-closed bleibt auf die Dimension beschraenkt: ein unlesbarer Beleg darf
    die Aussage ueber Aktivitaet, FIFO und Cash nicht mitreissen.
    """
    root=data_space/VALUATION_AREA
    if not root.is_dir():return None
    latest:dict[str,dict[str,Any]]={}
    requirements:list[dict[str,Any]]=[]
    newest_completed=None
    for path in sorted(root.glob("completed-*.json")):
        try:value=json.loads(path.read_text(encoding="utf-8"))
        except Exception:return {"unreadable":True}
        if not isinstance(value,dict) or not isinstance(value.get("preview_ref"),str) or not isinstance(value.get("completed_at_utc"),str):return {"unreadable":True}
        preview_path=root/(value["preview_ref"]+".json")
        if not preview_path.is_file():return {"unreadable":True}
        try:preview=json.loads(preview_path.read_text(encoding="utf-8"))
        except Exception:return {"unreadable":True}
        if not isinstance(preview,dict) or not isinstance(preview.get("request"),dict):return {"unreadable":True}
        completed=value["completed_at_utc"];as_of=preview["request"].get("end_date")
        if newest_completed is None or completed>newest_completed:newest_completed=completed
        for row in preview.get("summaries") or []:
            if not isinstance(row,dict) or not isinstance(row.get("asset_name"),str):continue
            known=latest.get(row["asset_name"])
            if known is None or completed>known["completed_at_utc"]:
                latest[row["asset_name"]]={**row,"completed_at_utc":completed,"as_of_date":as_of}
        requirements.extend(row for row in preview.get("requirements") or [] if isinstance(row,dict))
    if not latest and newest_completed is None:return None
    summaries=list(latest.values())
    as_of_dates=[row["as_of_date"] for row in summaries if isinstance(row.get("as_of_date"),str)]
    return {"unreadable":False,"completed_at_utc":newest_completed,
            "as_of_date":min(as_of_dates) if as_of_dates else None,
            "valuation_status":"complete" if all(row.get("valuation_status")=="complete" for row in summaries) else "incomplete",
            "summaries":summaries,"requirements":requirements}

# Bewertungsmethoden, die einen abgeschlossenen Bewertungslauf brauchen.
# `unit_value` braucht keinen Kurs, und `transaction_only` wird ausdruecklich nicht
# bewertet. `manual` zaehlte frueher dazu: Assets mit eigener
# Bewertung hielten die Marktdimension dauerhaft auf
# "teilweise", obwohl der Sammellauf sie mit Absicht auslaesst. Eine eigene
# Bewertung entsteht beim Lesen - eigene Kursangabe, sonst letzter bestaetigter
# Trade-Stueckpreis - und braucht keinen Lauf; ob sie einen Wert ergibt, sagt das
# Stichtagsbild an der Position.
VALUED_METHODS=("external_market",)

def _asset_names_to_value(canonical:Path)->set[str]:
    """Alle Assets, die eine Bewertung brauchen - mit ihrem Katalognamen.

    Auch geschlossene Bestaende zaehlen: ein Wiedereinstieg ist denkbar, und die
    Bewertungshistorie soll ueber den ganzen Zeitraum tragen (Festlegung
    20.09.2026). Gezaehlt wird deshalb der aktive Katalog, nicht der Bestand.

    Der Bewertungsbeleg fuehrt browserlokale Referenzen, der Katalog die
    kanonische Asset-Id. Verglichen wird ueber den Anzeigenamen - sonst gilt
    selbst ein bewertetes Asset als unbewertet.
    """
    try:
        connection=sqlite3.connect("file:"+str(canonical)+"?mode=ro",uri=True)
        try:
            rows=connection.execute(
                "SELECT display_name FROM asset WHERE status='active' AND asset_type!='cash' AND valuation_method IN ("
                +",".join("?" for _ in VALUED_METHODS)+")",VALUED_METHODS).fetchall()
        finally:connection.close()
    except sqlite3.Error:_abort("portfolio_readiness_evidence_invalid")
    return {row[0] for row in rows if isinstance(row[0],str)}

def _market_dimensions(valuation,held:set[str]):
    """Markt und FX getrennt bewerten: beide speisen die unrealisierte Bewertung."""
    if not held and valuation is None:
        # Kein Asset verlangt eine Marktbewertung - etwa ein reiner Cash-Datenraum.
        return ("not_applicable","no_asset_requires_valuation"),("not_applicable","no_asset_requires_valuation"),None
    if valuation is None:return ("unavailable","no_completed_valuation"),("unavailable","no_completed_valuation"),None
    if valuation.get("unreadable"):return ("unavailable","valuation_evidence_unreadable"),("unavailable","valuation_evidence_unreadable"),None
    summaries=valuation["summaries"];covered={row.get("asset_name") for row in summaries}
    missing=sorted(held-covered)
    incomplete=[row for row in summaries if row.get("valuation_status")!="complete"]
    if not summaries:market=("unavailable","valuation_without_assets")
    elif missing:market=("partial","assets_without_valuation")
    elif incomplete or valuation.get("valuation_status")!="complete":market=("partial","valuation_days_incomplete")
    else:market=("complete","valuation_complete")
    fx_rows=[row for row in valuation["requirements"] if row.get("kind")=="fx"]
    fx_open=sum(int(row.get("source_gap_review_day_count") or 0)+int(row.get("blocked_day_count") or 0)+int(row.get("unassessed_day_count") or 0) for row in fx_rows)
    fx_substituted=sum(int(row.get("fx_substituted_day_count") or 0) for row in summaries)
    if not fx_rows:fx=("not_applicable","no_foreign_currency_demand")
    elif fx_open:fx=("partial","fx_days_open")
    elif fx_substituted:fx=("partial","fx_days_substituted")
    else:fx=("complete","fx_complete")
    detail={"as_of_date":valuation.get("as_of_date"),"completed_at_utc":valuation.get("completed_at_utc"),
            "valued_asset_count":len(summaries),"asset_without_valuation_count":len(missing),
            "incomplete_asset_count":len(incomplete),"open_fx_day_count":fx_open}
    return market,fx,detail

def _dimension(code,status,reason,detail=None):
    row={"dimension_code":code,"status":status,"reason_code":reason}
    return row if detail is None else {**row,"detail":detail}
def read_portfolio_operational_readiness_v1(canonical_path:str|Path,data_space_path:str|Path,context_value:Any)->dict[str,Any]:
    context=_runtime(context_value);data_space=_owned_directory(data_space_path);canonical=_owned_file(canonical_path)
    try:binding=read_desktop_product_asset_activity_binding_v1(data_space,context)
    except DesktopProductAssetActivityV1Error:_abort("portfolio_readiness_evidence_invalid")
    try:realized=read_asset_activity_realized_state_v2(data_space,context)
    except AssetActivityRealizedStateV2Error:_abort("portfolio_readiness_evidence_invalid")
    try:cash=read_desktop_cash_coverage_view_v1(canonical,data_space,context)
    except DesktopCashCoverageV1Error as error:
        if error.code=="desktop_cash_coverage_catalog_invalid":cash={"status":"absent","periods":[],"period_count":0}
        else:_abort("portfolio_readiness_evidence_invalid")
    migration=_migration(data_space)
    dimensions=[]
    activity_available=binding.get("status")=="available" and binding.get("asset_activity_event_count",0)>0
    dimensions.append(_dimension("canonical_activity","complete" if activity_available else "unavailable","active_schema401_generation" if activity_available else "active_schema401_absent"))
    freshness=realized.get("freshness","unavailable")
    fifo_status="complete" if freshness=="fresh" else "stale" if freshness.startswith("stale") else "unavailable"
    dimensions.append(_dimension("fifo_basis",fifo_status,"fifo_v2_"+freshness));dimensions.append(_dimension("time_ordering",fifo_status,"explicit_order_"+freshness))
    if migration is None:
        dimensions.append(_dimension("migration_quarantine","not_applicable","fresh_product_no_migration_receipt"));dimensions.append(_dimension("derivative_activity","not_applicable","no_migration_derivative_scope"))
        portfolio_completeness="fresh_product_scope"
    else:
        quarantine=migration.get("quarantined_component_count",0);derivative=migration.get("derivative_blocked_component_count",0)
        dimensions.append(_dimension("migration_quarantine","partial" if quarantine else "complete","quarantine_excluded" if quarantine else "no_quarantine"));dimensions.append(_dimension("derivative_activity","blocked" if derivative else "complete","derivative_schema401_blocked" if derivative else "no_derivative_block"));portfolio_completeness=migration["portfolio_completeness"]
    periods=cash.get("periods",[])
    if cash.get("status")!="available" or not periods:cash_status,cash_reason="unavailable","cash_not_declared"
    elif all(row.get("coverage_mode")=="complete_reconciled" for row in periods):cash_status,cash_reason="complete","all_declared_periods_reconciled"
    else:cash_status,cash_reason="partial","cash_coverage_partial_or_income_only"
    dimensions.append(_dimension("cash_coverage",cash_status,cash_reason))
    valuation=_valuation(data_space);held=_asset_names_to_value(canonical)
    (market_status,market_reason),(fx_status,fx_reason),valuation_detail=_market_dimensions(valuation,held)
    dimensions.append(_dimension("market_history",market_status,market_reason,valuation_detail))
    dimensions.append(_dimension("fx_history",fx_status,fx_reason,valuation_detail))
    dimensions.append(_dimension("tax_policy","unavailable","tax_projection_not_requested"))
    realized_status="fresh_partial" if freshness=="fresh" and activity_available else "stale" if freshness.startswith("stale") else "unavailable"
    edges=[
        {"upstream":"schema401_activity","downstream":"fifo_v2_realized","status":"satisfied" if freshness=="fresh" else "unsatisfied"},
        {"upstream":"schema2900_cash","downstream":"cash_history","status":"satisfied" if cash_status=="complete" else "partial_or_unavailable"},
        {"upstream":"fifo_v2_realized","downstream":"tax_projection","status":"blocked"},
        {"upstream":"fifo_v2_positions","downstream":"market_unrealized",
         "status":"satisfied" if market_status=="complete" and fx_status in {"complete","not_applicable"} and freshness=="fresh" else "partial_or_unavailable"},
        {"upstream":"market_current_revision","downstream":"market_unrealized","status":"satisfied" if market_status=="complete" else "partial_or_unavailable"},
        {"upstream":"fx_current_revision","downstream":"market_unrealized","status":"satisfied" if fx_status in {"complete","not_applicable"} else "partial_or_unavailable"},
    ]
    # Die unrealisierte Bewertung ist erst belastbar, wenn Bestand, Marktpreise und
    # FX gemeinsam vollstaendig sind - kein Teilstand zaehlt als Bewertung (#189).
    market_ready=market_status=="complete" and fx_status in {"complete","not_applicable"} and freshness=="fresh" and activity_available
    return {"portfolio_operational_readiness_version":1,"status":"available","portfolio_completeness":portfolio_completeness,"actual_realized_before_tax_status":realized_status,"latest_completed_realized_visible":realized.get("status")=="available","realized_job_status":realized.get("job_status","unavailable"),"dimensions":dimensions,"dependency_edges":edges,"portfolio_total_ready":False,"tax_ready":False,"market_valuation_ready":market_ready,"hypothetical_liquidation_ready":False,"display_started_worker":False,"canonical_write":False,"provider_access":False,"network_access":False,"path_exposed":False,"context_exposed":False,"internal_id_exposed":False}

__all__=["PortfolioOperationalReadinessV1Error","read_portfolio_operational_readiness_v1"]
