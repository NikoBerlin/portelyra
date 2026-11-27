"""Native GTK providers for owner-local Statement structural-profiler UAT v1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from migrations.reference.statement_source_profiler_owner_uat_v1 import StatementSourceProfilerOwnerUATError


def _fail() -> None:
    raise StatementSourceProfilerOwnerUATError("statement_source_profiler_owner_uat_boundary_failed")


def _gtk() -> tuple[Any, Any, Any]:
    try:
        import gi
        gi.require_version("Gdk", "4.0")
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gdk, GLib, Gtk
        Gtk.init()
        if Gdk.Display.get_default() is None:
            _fail()
        return Gdk, GLib, Gtk
    except StatementSourceProfilerOwnerUATError:
        raise
    except Exception:
        _fail()


def gtk_statement_source_profiler_selection_v1() -> Path | None:
    _gdk, GLib, Gtk = _gtk()
    dialog = Gtk.FileChooserNative.new(
        "Portelyra – Statement-CSV strukturell prüfen", None, Gtk.FileChooserAction.OPEN,
        "Auswählen (noch nicht lesen)", "Abbrechen",
    )
    file_filter = Gtk.FileFilter(); file_filter.set_name("CSV-Dateien")
    file_filter.add_pattern("*.csv"); file_filter.add_pattern("*.CSV"); dialog.add_filter(file_filter)
    state: dict[str, Any] = {"path": None}; loop = GLib.MainLoop()
    def response(current: Any, code: int) -> None:
        if code == Gtk.ResponseType.ACCEPT:
            selected = current.get_file(); local = selected.get_path() if selected is not None else None
            if isinstance(local, str) and local:
                state["path"] = Path(local)
        current.destroy(); loop.quit()
    dialog.connect("response", response); dialog.show(); loop.run(); return state["path"]


def gtk_statement_source_profiler_authorization_v1(preview: dict[str, Any]) -> dict[str, Any] | None:
    _gdk, GLib, Gtk = _gtk()
    dialog = Gtk.Dialog(title="Portelyra – genau einen Profiler-Lesezugriff freigeben")
    dialog.set_modal(True); dialog.set_default_size(760, 430)
    dialog.add_button("Abbrechen", Gtk.ResponseType.CANCEL); dialog.add_button("Genau einmal lesen", Gtk.ResponseType.OK)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    for name in ("top", "bottom", "start", "end"): getattr(box, "set_margin_" + name)(16)
    box.append(Gtk.Label(label=("Die ausgewählte CSV wird genau einmal read-only geöffnet. Danach erkennt ADR-164 ausschließlich "
        "registrierte technische Formate und Headerrollen. Rohwerte und Pfad werden nicht persistiert. Kein Adapterprofil, "
        "keine Route und keine Produktdaten werden erzeugt."), wrap=True, xalign=0))
    checks = [
        Gtk.CheckButton(label="Ich autorisiere genau einen lokalen Leseversuch."),
        Gtk.CheckButton(label="Private Header und Kategorien bleiben ausschließlich in diesem lokalen Dialog."),
        Gtk.CheckButton(label="Das Ergebnis bleibt deaktiviert und erzeugt weder r2 noch Routingregeln."),
    ]
    for check in checks: box.append(check)
    error = Gtk.Label(label="", wrap=True, xalign=0); error.add_css_class("error"); box.append(error)
    dialog.get_content_area().append(box); state: dict[str, Any] = {"value": None}; loop = GLib.MainLoop()
    def response(current: Any, code: int) -> None:
        if code != Gtk.ResponseType.OK:
            current.destroy(); loop.quit(); return
        if not all(check.get_active() for check in checks):
            error.set_text("Alle drei Bestätigungen sind erforderlich."); return
        state["value"] = {
            "activation_authorized": False, "authorization_id": preview["authorization_id"],
            "automatic_retry_authorized": False, "canonical_write_authorized": False,
            "context_binding_sha256": preview["context_binding_sha256"],
            "private_values_local_only_acknowledged": True,
            "profiler_binding_sha256": preview["profiler_binding_sha256"],
            "provider_access_authorized": False,
            "selection_binding_sha256": preview["selection_binding_sha256"],
            "source_read_once_authorized": True,
        }
        current.destroy(); loop.quit()
    dialog.connect("response", response); dialog.present(); loop.run(); return state["value"]


def _review_text(review: dict[str, Any]) -> str:
    lines = [
        "OWNER-LOKAL – DIESE WERTE WERDEN NICHT PERSISTIERT", "",
        f"Encoding: {review['encoding']}", f"Delimiter: {review['delimiter']}",
        f"Zeitformat: {review['time_format']} (Zeitzone nicht inferiert)",
        f"Decimal-Formate: {json.dumps(review['decimal_formats'], ensure_ascii=False, sort_keys=True)}", "",
        "Header | explizite Rolle | Entscheidung",
    ]
    for item in review["column_dispositions"]:
        lines.append(f"{item['raw_header']} | {item['role']} | {item['status']}")
    lines.extend(["", "type | subtype | aclass | Zeilen"])
    for item in review["semantic_route_tuples"]:
        lines.append(f"{item['source_type']} | {item['source_subtype']} | {item['asset_class']} | {item['row_count']}")
    lines.extend(["", "Keine der sichtbaren Kategorien wurde einer Geschäftsroute zugeordnet."])
    return "\n".join(lines)


def gtk_statement_source_profiler_review_v1(review: dict[str, Any]) -> dict[str, Any] | None:
    _gdk, GLib, Gtk = _gtk()
    dialog = Gtk.Dialog(title="Portelyra – private Statement-Struktur prüfen")
    dialog.set_modal(True); dialog.set_default_size(1050, 740)
    dialog.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
    dialog.add_button("Verwerfen (deaktiviert)", Gtk.ResponseType.REJECT)
    dialog.add_button("Struktur beobachtet (deaktiviert)", Gtk.ResponseType.OK)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    for name in ("top", "bottom", "start", "end"): getattr(box, "set_margin_" + name)(12)
    scroller = Gtk.ScrolledWindow(); scroller.set_vexpand(True); scroller.set_hexpand(True)
    text = Gtk.TextView(); text.set_editable(False); text.set_cursor_visible(False); text.set_monospace(True)
    text.get_buffer().set_text(_review_text(review)); scroller.set_child(text); box.append(scroller)
    local = Gtk.CheckButton(label="Private Werte bleiben lokal und werden nicht veröffentlicht.")
    disabled = Gtk.CheckButton(label="Die Beobachtung aktiviert nichts und erzeugt weder Profilrevision noch Routingregeln.")
    box.append(local); box.append(disabled)
    error = Gtk.Label(label="", wrap=True, xalign=0); error.add_css_class("error"); box.append(error)
    dialog.get_content_area().append(box); state: dict[str, Any] = {"value": None}; loop = GLib.MainLoop()
    def response(current: Any, code: int) -> None:
        if code == Gtk.ResponseType.CANCEL or code == Gtk.ResponseType.DELETE_EVENT:
            current.destroy(); loop.quit(); return
        if not local.get_active() or not disabled.get_active():
            error.set_text("Beide Bestätigungen sind erforderlich."); return
        decision = "observe_disabled" if code == Gtk.ResponseType.OK else "reject_disabled"
        state["value"] = {"decision": decision, "no_activation_acknowledged": True,
            "private_values_local_only_acknowledged": True,
            "review_binding_sha256": review["review_binding_sha256"]}
        current.destroy(); loop.quit()
    dialog.connect("response", response); dialog.present(); loop.run(); return state["value"]


__all__ = ["gtk_statement_source_profiler_authorization_v1", "gtk_statement_source_profiler_review_v1", "gtk_statement_source_profiler_selection_v1"]
