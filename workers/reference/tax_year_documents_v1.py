"""Unterlagen eines Steuerjahres als ein Archiv: Report, Rechenblaetter, hinterlegte Auszuege, Lueckenliste.

Festlegung (13.10.2026): Die Original-Auszuege sollen sich zusammen mit dem
Steuerreport laden lassen. Ins Archiv gehoert alles Relevante - auch die
Lueckenliste und die Rechenblaetter -, aber getrennt in Ordnern: Was weitergegeben
wird, entscheidet der Nutzer je Ordner.

- `1_Steuerreport`: der Report des Jahres, wie die Tax-App ihn erstellt.
- `2_Rechenblaetter_Modellrechnung`: die Rechenblaetter - eigene Modellrechnung.
- `3_Auszuege_und_Belege`: die hinterlegten Dateien, je Institut ein Ordner, und
  ein Inhaltsverzeichnis mit Konten, Zeitraum, Art, Stand und Pruefwert.
- `4_Eigene_Kontrolle`: die Lueckenliste.

Welche Auszuege dazugehoeren, sagt der Report: die Konten seiner Vorgaenge im
Jahr und - ueber das Jahr hinaus - die Monate, in denen die im Jahr verbrauchten
Lots angeschafft und umgeschichtet wurden. Auf Wunsch stattdessen alle Konten.

Report und Rechenblaetter setzt die Oberflaeche (das PDF entsteht dort); sie
kommen als fertige Dateien herein. Geschrieben wird genau eine Datei an dem Ort,
den der Aufrufer nennt - nie in den Datenraum. Jede hinterlegte Datei wird beim
Lesen gegen ihren Pruefwert gerechnet. Kein Providerzugriff, kein Netzzugriff,
kein kanonischer Write.
"""

from __future__ import annotations

import csv
import io
import os
import shutil
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
import zipfile

from migrations.reference.account_reference_v1 import AccountReferenceV1Error, read_account_references_v1
from migrations.reference.statement_archive_v1 import (
    StatementArchiveV1Error, read_statement_file_v1, read_statement_year_evidence_v1, statement_archive_scope_v1,
)
from workers.reference.simple_tax_report_v1 import REPORT_TYPES, SimpleTaxReportV1Error, build_simple_tax_report_with_keys_v1

CONTRACT = "tax_year_documents_v1"
SCOPES = ("report_accounts", "all_accounts")
SECTIONS = ("report", "sheets")
FOLDERS = {"report": "1_Steuerreport", "sheets": "2_Rechenblaetter_Modellrechnung", "statements": "3_Auszuege_und_Belege",
           "control": "4_Eigene_Kontrolle"}
FAILURE_CODES = (
    "tax_year_documents_input_invalid",
    "tax_year_documents_source_invalid",
    "tax_year_documents_target_invalid",
)
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
ATTACHMENT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}")
MAX_ATTACHMENT_BYTES = 64 * 1024 * 1024
MAX_ATTACHMENTS = 12
_KIND_LABELS = {
    "account_statement": "Kontoauszug", "securities_statement": "Depotauszug", "transaction_export": "Transaktionsexport",
    "tax_certificate": "Jahressteuerbescheinigung", "income_statement": "Erträgnisaufstellung", "advance_lump_sum": "Vorabpauschale",
    "confirmation": "Bestätigung / Abrechnung",
    "other": "Sonstiges",
}
_TYPE_LABELS = {"crypto": "Krypto", "equity": "Aktien", "fund": "Fonds", "commodity": "Rohstoffe", "derivative": "Derivate", "fx": "Devisen", "cash": "Cash (Zinsen)"}
_STATUS_LABELS = {
    "confirmed": "bestätigt", "unconfirmed": "hinterlegt, unbestätigt", "not_available": "nicht mehr vorhanden (manuell bestätigt)",
    "open": "offen: Bewegung ohne Beleg",
}
_RELATION_LABELS = {"tax_year": "Steuerjahr", "acquisition": "Anschaffung eines im Jahr verbrauchten Lots"}
_NO_INSTITUTION = "ohne Institutsangabe"


class TaxYearDocumentsV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def tax_year_documents_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise TaxYearDocumentsV1Error(code if code in FAILURE_CODES else "tax_year_documents_source_invalid")


def _member(text: Any, fallback: str) -> str:
    """Ein Namensteil im Archiv: kein Pfadtrenner, kein Steuerzeichen, kein fuehrender Punkt; Leerraum zusammengezogen."""
    value = "".join("_" if char in '/\\:*?"<>|' or ord(char) < 32 or ord(char) == 127 else char for char in str(text or ""))
    value = " ".join(value.split()).lstrip(". ").rstrip(". ")
    return value[:120] if value else fallback


def _safe(text: Any) -> str:
    """Kein Zellinhalt, den eine Tabellenkalkulation als Formel liest."""
    value = "" if text is None else str(text).replace("\r", " ").replace("\n", " ")
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


def _table(rows: Sequence[Sequence[Any]]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    for row in rows:
        writer.writerow(row)
    return ("﻿" + out.getvalue()).encode("utf-8")


def _attachments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)) or len(value) > MAX_ATTACHMENTS:
        _abort("tax_year_documents_input_invalid")
    result = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"section", "name", "path"} or item["section"] not in SECTIONS or (
                not isinstance(item["name"], str) or ATTACHMENT_NAME.fullmatch(item["name"]) is None or not isinstance(item["path"], str)):
            _abort("tax_year_documents_input_invalid")
        path = Path(item["path"])
        if not path.is_absolute() or path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ATTACHMENT_BYTES:
            _abort("tax_year_documents_input_invalid")
        result.append({"section": item["section"], "name": item["name"], "path": path})
    if len({(item["section"], item["name"]) for item in result}) != len(result):
        _abort("tax_year_documents_input_invalid")
    return result


def _target(value: Any, space: Path) -> Path:
    """Der Ort des Archivs: eine neue .zip-Datei in einem vorhandenen Verzeichnis ausserhalb des Datenraums."""
    if not isinstance(value, str) or not value.endswith(".zip"):
        _abort("tax_year_documents_target_invalid")
    target = Path(value)
    if not target.is_absolute() or target.exists() or target.is_symlink() or not target.parent.is_dir() or target.parent.is_symlink():
        _abort("tax_year_documents_target_invalid")
    resolved, inside = target.parent.resolve(), space.resolve()
    if resolved == inside or inside in resolved.parents:
        _abort("tax_year_documents_target_invalid")
    return target


def _institution(document: Mapping[str, Any], accounts: Mapping[str, Mapping[str, Any]]) -> str:
    """Der Ordner eines Dokuments: das Institut, an dem es haengt - sonst das seiner Konten, wenn sie sich einig sind."""
    if document["institution_label"]:
        return document["institution_label"]
    labels = {accounts[account]["institution_label"] for account in document["account_ids"] if account in accounts}
    labels.discard(None)
    return next(iter(labels)) if len(labels) == 1 else ("mehrere Institute" if labels else _NO_INSTITUTION)


def build_tax_year_documents_v1(
    data_space_path: str | Path, context_value: Any, tax_year: int, asset_types: Sequence[str], scope: str,
    attachments: Sequence[Mapping[str, Any]], target_path: str, generated_at_utc: str,
) -> dict[str, Any]:
    """Stellt die Unterlagen eines Steuerjahres zu einem Archiv zusammen und schreibt es an den genannten Ort."""
    if isinstance(tax_year, bool) or not isinstance(tax_year, int) or not 2000 <= tax_year <= 2100 or scope not in SCOPES or (
            not isinstance(generated_at_utc, str) or UTC.fullmatch(generated_at_utc) is None):
        _abort("tax_year_documents_input_invalid")
    if isinstance(asset_types, (str, bytes)) or not isinstance(asset_types, Sequence) or not asset_types or any(
            kind not in REPORT_TYPES for kind in asset_types) or len(set(asset_types)) != len(asset_types):
        _abort("tax_year_documents_input_invalid")
    space = Path(data_space_path)
    try:
        context = statement_archive_scope_v1(context_value)
    except StatementArchiveV1Error:
        _abort("tax_year_documents_input_invalid")
    files = _attachments(attachments)
    target = _target(target_path, space)
    base = {"contract_version": CONTRACT, "tax_year": tax_year, "asset_types": sorted(asset_types), "scope": scope,
            "provider_access": False, "network_access": False, "canonical_write": False}
    try:
        report = build_simple_tax_report_with_keys_v1(space, context, tax_year, list(asset_types))
    except SimpleTaxReportV1Error as error:
        _abort("tax_year_documents_input_invalid" if error.code == "simple_tax_report_input_invalid" else "tax_year_documents_source_invalid")
    if report["status"] != "ready":
        # Ohne aktuellen FIFO-Stand nennt der Report keine Vorgaenge - dann laesst sich auch nicht sagen, welche Auszuege dazugehoeren.
        return {**base, "status": report["status"], "archive_written": False}
    year = f"{tax_year:04d}"
    involved = {row["account_ref"] for row in report["evidence_accounts"]}
    outside = sorted({(row["account_ref"], row["month"]) for row in report["evidence_accounts"] if row["month"][:4] != year})
    try:
        archive = read_statement_year_evidence_v1(space, context, tax_year, [{"account_id": account, "month": month} for account, month in outside])
        numbers = read_account_references_v1(space, context)["references"]
    except (StatementArchiveV1Error, AccountReferenceV1Error):
        _abort("tax_year_documents_source_invalid")
    accounts = archive["accounts"]
    if scope == "all_accounts":
        # Jedes Konto, das im Jahr etwas traegt: eine Bewegung, einen Beleg oder eine Erklaerung.
        involved = involved | {account for account, cells in archive["year_months"].items()
                               if any(cell["status"] not in ("no_movement", "not_expected", "closed", "inactive") for cell in cells)}
    involved = {account for account in involved if account in accounts}
    evidence_accounts = {account for account, _ in outside}

    def label(account: str) -> str:
        return accounts[account]["account_label"]

    def wanted(document: Mapping[str, Any]) -> list[str]:
        """Weshalb ein Dokument dazugehoert: es beruehrt das Jahr an einem beteiligten Konto oder belegt eine Anschaffung."""
        ids = set(document["account_ids"])
        return [relation for relation in document["relations"]
                if (relation == "tax_year" and (scope == "all_accounts" or ids & involved)) or (relation == "acquisition" and ids & evidence_accounts)]

    chosen = [(document, wanted(document)) for document in archive["documents"]]
    chosen = [(document, relations) for document, relations in chosen if relations]
    index_rows: list[list[Any]] = [[
        "Institut", "Konten", "Kontonummern", "Art", "Zeitraum von", "Zeitraum bis", "Stand", "Bezug", "Datei im Archiv", "Originalname",
        "Größe [Bytes]", "SHA-256"]]
    members: list[tuple[str, Path | bytes]] = []
    used: set[str] = set()
    stored: dict[str, str] = {}
    file_count = total_bytes = unconfirmed_documents = 0
    for document, relations in chosen:
        if document["file_sha256"] is None:
            continue
        try:
            source = read_statement_file_v1(space, context, document["document_ref"])
        except StatementArchiveV1Error:
            _abort("tax_year_documents_source_invalid")
        institution = _institution(document, accounts)
        # Dieselbe Datei kann an mehreren Dokumenten haengen; im Archiv liegt sie einmal.
        name = stored.get(document["file_sha256"])
        if name is None:
            stem = f"{document['period_from']}_bis_{document['period_to']}_{_member(_KIND_LABELS[document['document_kind']].replace(' / ', '-'), 'Dokument')}"
            candidate = f"{FOLDERS['statements']}/{_member(institution, _NO_INSTITUTION)}/{stem}_{_member(document['original_name'], 'Datei')}"
            name, counter = candidate, 2
            while name.lower() in used:
                head, dot, tail = candidate.rpartition(".")
                name = f"{head}_{counter}.{tail}" if dot and "/" not in tail else f"{candidate}_{counter}"
                counter += 1
            used.add(name.lower())
            stored[document["file_sha256"]] = name
            members.append((name, Path(source["path"])))
            file_count += 1
            total_bytes += int(source["size_bytes"])
        unconfirmed_documents += document["status"] == "unconfirmed"
        known = [account for account in document["account_ids"] if account in accounts]
        index_rows.append([
            _safe(institution), _safe(" | ".join(sorted(label(account) for account in known))),
            _safe(" | ".join(numbers[account]["account_number"] for account in sorted(known, key=label) if account in numbers)),
            _KIND_LABELS[document["document_kind"]], document["period_from"], document["period_to"], _STATUS_LABELS[document["status"]],
            " und ".join(_RELATION_LABELS[relation] for relation in relations), name, _safe(document["original_name"]), source["size_bytes"],
            document["file_sha256"]])

    # Lueckenliste: was im Jahr und an den Anschaffungsmonaten nicht durch eine bestaetigte Datei belegt ist.
    gap_rows: list[list[Any]] = [["Institut", "Konto", "Kontonummer", "Monat", "Stand", "Bezug", "Dokumente zum Monat"]]
    counts = {"open": 0, "unconfirmed": 0, "not_available": 0}
    evidence_counts = {"open": 0, "unconfirmed": 0, "not_available": 0}

    def gap(account: str, cell: Mapping[str, Any], relation: str, counter: dict[str, int]) -> None:
        if cell["status"] not in counter:
            return
        counter[cell["status"]] += 1
        gap_rows.append([_safe(accounts[account]["institution_label"] or _NO_INSTITUTION), _safe(label(account)),
                         _safe((numbers.get(account) or {}).get("account_number")), cell["month"], _STATUS_LABELS[cell["status"]],
                         _RELATION_LABELS[relation], cell["document_count"]])

    order = sorted(involved, key=lambda account: ((accounts[account]["institution_label"] or "￿").lower(), label(account).lower()))
    for account in order:
        for cell in archive["year_months"][account]:
            gap(account, cell, "tax_year", counts)
    for cell in sorted(archive["evidence_months"], key=lambda cell: (label(cell["account_id"]).lower(), cell["month"])):
        gap(cell["account_id"], cell, "acquisition", evidence_counts)
    declarations = [document for document, _ in chosen if document["status"] == "not_available"]
    if declarations:
        gap_rows += [[], ["Erklärungen „nicht mehr vorhanden“"], ["Institut", "Konten", "Zeitraum von", "Zeitraum bis", "Erklärt am (UTC)", "Notiz"]]
        for document in declarations:
            gap_rows.append([_safe(_institution(document, accounts)),
                             _safe(" | ".join(sorted(label(account) for account in document["account_ids"] if account in accounts))),
                             document["period_from"], document["period_to"], document["recorded_at_utc"], _safe(document["note"])])

    sections = {section: [item for item in files if item["section"] == section] for section in SECTIONS}
    kinds = ", ".join(_TYPE_LABELS[kind] for kind in sorted(asset_types, key=REPORT_TYPES.index))
    lines = [
        f"Unterlagen zum Steuerjahr {tax_year}",
        f"Zusammengestellt am {generated_at_utc} (UTC) mit Portelyra.",
        f"Auswahl: {kinds} · Konten: {'alle Konten mit Bewegung oder Beleg im Jahr' if scope == 'all_accounts' else 'die Konten des Steuerreports'}",
        "",
        f"{FOLDERS['report']} – der Steuerreport des Jahres ({len(sections['report'])} Datei(en)).",
        f"{FOLDERS['sheets']} – Rechenblätter je Ereignis, Jahresrechnung und Steuerreport in ausführlicher Fassung: eigene Modellrechnung, "
        f"kein Beleg und keine Steuerfestsetzung ({len(sections['sheets'])} Datei(en)).",
        f"{FOLDERS['statements']} – die hinterlegten Original-Auszüge und Belege, je Institut ein Ordner ({file_count} Datei(en)). "
        "Inhaltsverzeichnis.csv nennt zu jeder Datei Konten, Zeitraum, Art, Stand und Prüfwert (SHA-256).",
        f"{FOLDERS['control']} – Lückenliste zur eigenen Kontrolle: Monate mit Bewegung ohne hinterlegten Auszug, unbestätigte Dateien "
        "und als „nicht mehr vorhanden“ erklärte Zeiträume.",
        "",
    ]
    members = [
        ("LIESMICH.txt", ("\r\n".join(lines)).encode("utf-8")),
        *[(f"{FOLDERS[item['section']]}/{item['name']}", item["path"]) for item in files],
        (f"{FOLDERS['statements']}/Inhaltsverzeichnis.csv", _table(index_rows)),
        *members,
        (f"{FOLDERS['control']}/Lueckenliste.csv", _table(gap_rows)),
    ]
    stamp = (int(generated_at_utc[0:4]), int(generated_at_utc[5:7]), int(generated_at_utc[8:10]),
             int(generated_at_utc[11:13]), int(generated_at_utc[14:16]), int(generated_at_utc[17:19]))
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        temporary.unlink(missing_ok=True)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle, zipfile.ZipFile(handle, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name, content in members:
                info = zipfile.ZipInfo(name, date_time=stamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                if isinstance(content, bytes):
                    bundle.writestr(info, content)
                    continue
                # Hinterlegte Auszuege in Stuecken: Eine Datei der Ablage darf bis 1 GB gross sein (rc.276, #464).
                info.file_size = content.stat().st_size
                with content.open("rb") as source, bundle.open(info, "w") as member:
                    shutil.copyfileobj(source, member, 1024 * 1024)
        os.replace(temporary, target)
    except (OSError, ValueError, zipfile.BadZipFile):
        temporary.unlink(missing_ok=True)
        _abort("tax_year_documents_target_invalid")
    return {
        **base, "status": "ready", "archive_written": True, "archive_bytes": target.stat().st_size, "member_count": len(members),
        "account_count": len(involved), "report_file_count": len(sections["report"]), "sheet_file_count": len(sections["sheets"]),
        "statement_document_count": sum(document["file_sha256"] is not None for document, _ in chosen), "statement_file_count": file_count,
        "statement_bytes": total_bytes, "unconfirmed_document_count": unconfirmed_documents, "declaration_count": len(declarations),
        "open_month_count": counts["open"], "unconfirmed_month_count": counts["unconfirmed"], "not_available_month_count": counts["not_available"],
        "acquisition_month_count": len(archive["evidence_months"]), "acquisition_open_month_count": evidence_counts["open"],
        "acquisition_unconfirmed_month_count": evidence_counts["unconfirmed"],
        "acquisition_not_available_month_count": evidence_counts["not_available"],
    }


__all__ = [
    "FAILURE_CODES", "FOLDERS", "SCOPES", "TaxYearDocumentsV1Error", "build_tax_year_documents_v1", "tax_year_documents_v1_error_codes",
]
