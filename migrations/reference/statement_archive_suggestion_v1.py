"""Vorschlag je Datei fuer die Ablage (#434): Art, Zeitraum und Konten aus dem Inhalt, statt sie einzutippen.

Ein Jahr mit monatlichen Auszuegen laesst sich ohne Eintippen der Zeitraeume hinterlegen (#434).
Gelesen wird mit den Lesern der Importe: Cash-Auszuege, Wertpapier-, Krypto- und Devisenbelege. Was kein Leser erkennt,
bekommt einen Zeitraum nur, wenn die Datei ihn ausdruecklich nennt ("Zeitraum 01.02.2025 - 28.02.2025") oder - bei einer
CSV - aus den Daten ihrer Zeilen. Konten schlaegt der Vorschlag nur vor, wenn sie eindeutig sind: ueber die Kontonummer am
Konto (IBAN, Depotnummer), den Kontovorschlag des Wertpapier-Lesers oder genau ein passendes Konto des Instituts.

Schreibt nichts; die Dateien bleiben unveraendert. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from migrations.reference import cash_statement_import_v1 as cash
from migrations.reference import statement_reader_plugins_v1 as reader_plugins
from migrations.reference import securities_statement_import_v1 as securities
from migrations.reference.account_reference_v1 import AccountReferenceV1Error, read_account_references_v1
from migrations.reference.statement_archive_v1 import StatementArchiveV1Error, _catalog_accounts, statement_archive_scope_v1

CONTRACT = "statement_archive_suggestion_v1"
MAX_FILES = 2000
MAX_SUGGEST_BYTES = 20 * 1024 * 1024
# Institut je Cash-Leser (#486): das erste Wort aus dem Rezept seines Plugins ("account_words"), das in der Institutsangabe des Kontos steht.
# Art aus dem Wortlaut, wenn kein Leser sie bestimmt: die erste passende Zeile gilt.
KIND_WORDS = (("tax_certificate", ("jahressteuerbescheinigung", "steuerbescheinigung", "verlustbescheinigung", "steuerbericht", "steuerreport")), ("income_statement", ("erträgnisaufstellung", "ertraegnisaufstellung")),
              ("securities_statement", ("depotauszug", "depotübersicht", "wertpapierdepot")),
              # Die Entgeltaufstellung nennt den Kontoauszug, ist aber keiner (rc.321): Als Auszug abgelegt, nahm sie der Cash-Import
              # des Girokontos aus der Ablage mit.
              ("other", ("entgeltaufstellung",)), ("account_statement", ("kontoauszug", "perioden-kontoauszug")))
# "Zeitraum Von 01.01.2024 bis 31.12.2024" (ING-Entgeltaufstellung) gilt seit rc.320 auch.
EXPLICIT_PERIOD = re.compile(r"(?:Zeitraum|vom|Abrechnungszeitraum)\s*:?\s*(?:von\s+)?(\d{2})\.(\d{2})\.(\d{4})\s*(?:-|–|bis)\s*(\d{2})\.(\d{2})\.(\d{4})", re.I)
# Steuerunterlagen (#513, rc.320): Sie nennen das Steuerjahr im Wortlaut ("fuer das Kalenderjahr 2024", "Erträgnisaufstellung fuer
# das Jahr 2024"), einen Zeitraum mit Schraegstrichen (Bondora) oder den Tag einer Verlustverrechnung. Ein Brief, der nur auf "das
# vergangene Steuerjahr" verweist, bleibt ohne Zeitraum.
TAX_KINDS = ("tax_certificate", "income_statement")
TAX_YEAR = tuple(re.compile(pattern, re.I) for pattern in (
    r"(?:Kalender|Steuer)jahr(?:es)?\s+((?:19|20)\d{2})\b",
    r"für\s+das\s+(?:Jahr|Kalenderjahr|Steuerjahr|Geschäftsjahr)\s+((?:19|20)\d{2})\b",
    r"(?:Jahressteuerbescheinigung|Steuerbescheinigung|Erträgnisaufstellung|Ertraegnisaufstellung|Verlustbescheinigung|Steuerreport|Steuerbericht)"
    r"\s+(?:für\s+)?((?:19|20)\d{2})\b"))
# Schraegstriche: Tag/Monat oder Monat/Tag (Bondora schreibt "01/01/2025 - 12/31/2025", rc.321). Welche Folge gilt, zeigt ein Teil
# ueber 12; zeigt es keiner, bleibt der Zeitraum offen.
SLASH_PERIOD = re.compile(r"\b(\d{2})/(\d{2})/((?:19|20)\d{2})\s*(?:-|–|bis)\s*(\d{2})/(\d{2})/((?:19|20)\d{2})\b")
LOSS_OFFSET = re.compile(r"Verlustverrechnung\s+vom\s*:?\s*(\d{2})\.(\d{2})\.((?:19|20)\d{2})", re.I)
ISO_DATE = re.compile(r"\b((?:19|20)\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")
GERMAN_DATE = re.compile(r"\b(0[1-9]|[12]\d|3[01])\.(0[1-9]|1[0-2])\.((?:19|20)\d{2})\b")


def _month(day: str) -> str:
    return day[:7]


def _normal(text: str) -> str:
    return re.sub(r"[\s.\-/]", "", text).upper()


def _kind_from_text(text: str, file_name: str) -> str:
    lowered = text[:20000].lower()
    for kind, words in KIND_WORDS:
        if any(word in lowered for word in words):
            return kind
    return "transaction_export" if file_name.lower().endswith(".csv") else "other"


def _period_from_text(text: str, file_name: str) -> tuple[str, str] | None:
    explicit = EXPLICIT_PERIOD.search(text)
    if explicit:
        d1, m1, y1, d2, m2, y2 = explicit.groups()
        first, last = f"{y1}-{m1}", f"{y2}-{m2}"
        return (first, last) if first <= last else None
    if not file_name.lower().endswith(".csv"):
        return None
    months = {f"{year}-{month}" for year, month, _day in ISO_DATE.findall(text)}
    months |= {f"{year}-{month}" for _day, month, year in GERMAN_DATE.findall(text)}
    return (min(months), max(months)) if months else None


def _tax_period(text: str) -> tuple[str, str] | None:
    """Der Zeitraum einer Steuerunterlage: das Steuerjahr, ein Zeitraum mit Schraegstrichen oder der Monat der Verlustverrechnung."""
    head = text[:20000]
    for pattern in TAX_YEAR:
        found = pattern.search(head)
        if found:
            return (f"{found.group(1)}-01", f"{found.group(1)}-12")
    slash = SLASH_PERIOD.search(head)
    if slash:
        a1, b1, y1, a2, b2, y2 = slash.groups()
        day_first = any(int(part) > 12 for part in (a1, a2))
        month_first = any(int(part) > 12 for part in (b1, b2))
        if day_first != month_first:
            m1, m2 = (b1, b2) if day_first else (a1, a2)
            first, last = f"{y1}-{m1}", f"{y2}-{m2}"
            if all(1 <= int(month) <= 12 for month in (m1, m2)) and first <= last:
                return (first, last)
    loss = LOSS_OFFSET.search(head)
    return (f"{loss.group(3)}-{loss.group(2)}",) * 2 if loss else None


def _matches(words: Sequence[str], *labels: str | None) -> bool:
    # Ganze Woerter: "ing" trifft "ING", nicht "Investing".
    return any(re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", (label or "").lower()) for word in words for label in labels)


class _Accounts:
    """Konten des Katalogs mit Institutsangabe und Kontonummer - nur gelesen."""

    def __init__(self, space: Path, context: Any) -> None:
        self.catalog = {account_id: row for account_id, row in _catalog_accounts(space, context).items() if row["status"] == "active"}
        try:
            numbers = read_account_references_v1(space, context)["references"]
        except AccountReferenceV1Error:
            numbers = {}
        self.numbers = {account_id: _normal(entry["account_number"]) for account_id, entry in numbers.items()
                        if account_id in self.catalog and len(_normal(entry["account_number"])) >= 8}

    def by_number(self, text: str, word: str | None = None) -> list[str]:
        """Konten, deren Nummer im Text steht. Ein Export nennt oft auch die IBAN anderer eigener Konten (Ueberweisungen): Mit einem
        Institut zaehlen nur dessen Konten; ohne Institut nur ein einziger Treffer."""
        flat = _normal(text)
        found = sorted(account_id for account_id, number in self.numbers.items() if number in flat)
        if word:
            own = [account_id for account_id in found if word in (self.catalog[account_id]["institution_label"] or "").lower()]
            return own if own else (found if len(found) == 1 else [])
        return found if len(found) == 1 else []

    def statement_account(self, found: list[str], name: str, text: str) -> list[str]:
        """Das eine Konto eines Kontoauszugs unter mehreren genannten (rc.321): Ein Giro-Auszug nennt bei einer Umbuchung die Nummer
        des Extra-Kontos. Es gilt die Nummer im Dateinamen, sonst die zuerst im Text stehende - die des Kopfes."""
        if len(found) <= 1:
            return found
        in_name = [account_id for account_id in found if self.numbers.get(account_id) and self.numbers[account_id] in _normal(name)]
        if len(in_name) == 1:
            return in_name
        flat = _normal(text)
        return [min(found, key=lambda account_id: (flat.find(self.numbers[account_id]) if account_id in self.numbers else len(flat), account_id))]

    def of_institution(self, words: Sequence[str]) -> list[str]:
        """Die aktiven Konten eines Instituts nach ihrer Institutsangabe - nicht nach dem Namen: Ein Konto mit "Scalable" im Namen kann zur Baader Bank gehoeren."""
        return sorted(account_id for account_id, row in self.catalog.items() if _matches(words, row["institution_label"]))

    def by_institution(self, word: str, account_types: Sequence[str]) -> list[str]:
        return sorted(account_id for account_id, row in self.catalog.items()
                      if row["account_type"] in account_types and word in (row["institution_label"] or "").lower())


def _cash_suggestion(source: bytes, name: str, accounts: _Accounts) -> dict[str, Any] | None:
    best = None
    readers: list[tuple[str, str, str, str, frozenset[int]]] = []
    for adapter_id, adapter in cash.ADAPTERS.items():
        if not name.lower().endswith(adapter["extensions"]):
            continue
        # Erkennungsregeln des Leser-Plugins vorab (rc.373, #486): spart den abgeschotteten Aufruf fuer fremde Dateien.
        if not cash.cash_reader_may_read_v1(adapter_id, [(source, name)]):
            continue
        try:
            parsed = cash.parse_cash_statement_v1(adapter_id, source, name)
        except cash.CashStatementImportV1Error:
            continue
        except Exception:  # noqa: BLE001 - ein Leser, der an einer fremden Datei scheitert, ist kein Fehler des Vorschlags
            continue
        summary = parsed["summary"]
        days = [row["local_date"] for row in parsed["candidates"]]
        first = summary.get("period_from") or (min(days) if days else None)
        last = summary.get("period_to") or summary.get("closing_as_of_date") or (max(days) if days else None)
        if first is None or last is None:
            continue
        score = (len(days), parsed["balance_consistent"])
        readers.append((adapter_id, adapter["label"], _month(first), _month(last), frozenset(row.get("source_row_ordinal", -1) for row in parsed["candidates"])))
        if best is None or score > best[0]:
            best = (score, adapter_id, adapter["label"], _month(first), _month(last))
    if best is None:
        return None
    _score, adapter_id, label, first, last = best
    # Eine Datei, aus der mehrere Leser desselben Instituts verschiedene Zeilen lesen (Revolut: Giro und Sparkonto in einem Export,
    # #521), gehoert zu allen diesen Konten und reicht ueber alle ihre Zeitraeume. Lesen sie dieselben Zeilen (Scalable: Verrechnung
    # und Tagesgeld nach derselben Vorlage), bleibt es beim besten.
    words = reader_plugins.plugin_account_words_v1(adapter_id, "cash")
    word = words[0] if words else None
    plugin_of = lambda reader_id: getattr(reader_plugins.reader_spec_v1(reader_id, "cash"), "plugin_id", None)  # noqa: E731
    own = next(item for item in readers if item[0] == adapter_id)
    # Nur Leser, die Zeilen lesen: Zwei leere Mengen sind nicht "verschiedene Zeilen" - ein bewegungsloser Scalable-Auszug bekam sonst
    # beide Konten (rc.328, im Test gefunden).
    partners = [item for item in readers if item[0] != adapter_id and own[4] and item[4] and item[4].isdisjoint(own[4]) and word is not None
                and plugin_of(item[0]) == plugin_of(adapter_id)]
    if partners:
        first, last = min([first] + [item[2] for item in partners]), max([last] + [item[3] for item in partners])
        label = " · ".join([label] + [item[1] for item in partners])
        candidates = accounts.by_institution(word, ("cash", "bank"))
        if len(candidates) == 1 + len(partners):
            return {"reader": label, "document_kind": "transaction_export" if name.lower().endswith(".csv") else "account_statement",
                    "period_from": first, "period_to": last, "account_ids": candidates, "account_basis": "institution"}
    text = "\n".join(cash._pdf_text(source, name))
    found, basis = accounts.statement_account(accounts.by_number(text, word), name, text), "account_number"
    if not found:
        candidates = accounts.by_institution(word, ("cash", "bank")) if word else []
        found, basis = (candidates, "institution") if len(candidates) == 1 else ([], None)
    # Lesen zwei Leser dieselben Zeilen gleich gut (Scalable: Verrechnung und Tagesgeld nach derselben Vorlage), gewann bisher der
    # erste - der Eingang zeigte "Tagesgeld" auch beim Verrechnungskonto (#522). Steht das Konto fest, nennt die Zeile den Leser, der
    # zu seinem Namen passt.
    twins = [item for item in readers if item[0] != adapter_id and item[4] == own[4]]
    if twins and len(found) == 1:
        name_of = (accounts.catalog.get(found[0]) or {}).get("display_name") or ""
        savings = bool(re.search(r"tagesgeld|zins|spar|savings", name_of, re.I))
        fits = [item for item in [own] + twins if bool(re.search(r"tagesgeld|savings|zins", item[0])) == savings]
        if len(fits) == 1:
            label = fits[0][1]
    return {"reader": label, "document_kind": "transaction_export" if name.lower().endswith(".csv") else "account_statement",
            "period_from": first, "period_to": last, "account_ids": found, "account_basis": basis if found else None}


def _statement_days(adapter_id: str, source: bytes, name: str) -> list[str]:
    """Die Tage eines Kontoauszugs, den ein Beleg-Leser als Saldo-Anker liest (Fremdwaehrungskonten): Salden und Buchungen. Ein
    Auszug ohne Bewegung nennt nur den Saldo zum Stichtag - sein Monat ist der Zeitraum (#513)."""
    adapter = securities.ADAPTERS[adapter_id]
    text = securities._text(source, name)
    try:
        result = adapter["parse"](text, name) if adapter.get("with_name") else adapter["parse"](text)
    except Exception:  # noqa: BLE001 - ein Leser, der an einer fremden Datei scheitert, ist kein Fehler des Vorschlags
        return []
    if not isinstance(result, dict) or result.get("status") != "statement":
        return []
    days = [balance[0] for balance in (result.get("start"), result.get("end")) if balance and balance[0]]
    days += [day for line in result.get("lines", []) for day in (line.get("booked"), line.get("valuta")) if day]
    return days


def _securities_suggestion(canonical: Path, context: Any, source: bytes, name: str, accounts: _Accounts) -> dict[str, Any] | None:
    try:
        matches = securities.detect_securities_statement_adapters_v1([(source, name)], ("securities", "crypto", "fx"))
    except securities.SecuritiesStatementImportV1Error:
        return None
    # Erkennen mehrere Leser die Datei (ein Devisenbeleg der Smartbroker: Wertpapier- und Devisen-Leser), gilt der erste, der ein
    # Datum liefert. Bis rc.317 galt nur der mit den meisten Treffern; bei Gleichstand der Wertpapier-Leser, der den Devisenbeleg
    # mit Grund zuruecklegt - der Vorschlag fand keinen Zeitraum.
    matches = sorted((item for item in matches if item["matching_documents"] > 0), key=lambda item: -item["matching_documents"])

    def days_of(adapter_id: str) -> tuple[dict[str, Any] | None, list[str]]:
        try:
            parsed = securities.parse_securities_statement_set_v1(adapter_id, [(source, name)])
        except securities.SecuritiesStatementImportV1Error:
            return None, []
        days = [candidate["local_date"] for candidate in parsed.get("candidates", []) if candidate.get("local_date")]
        if not days and parsed.get("statement_count"):
            days = _statement_days(adapter_id, source, name)
        return parsed, days

    for index, match in enumerate(matches):
        adapter_id = match["adapter_id"]
        parsed, days = days_of(adapter_id)
        if not days:
            continue
        # Weitere Leser derselben Datei (#550): Eine Dividende mit Gutschrift in Fremdwaehrung liest der Wertpapier-Leser (Dividende) und
        # der Devisen-Leser (Zufluss). Genannt werden alle, damit im Eingang beide Importe auffallen; Zeitraum, Art und Konten bleiben die
        # des ersten.
        readers = [securities.ADAPTERS[adapter_id]["label"]] + [securities.ADAPTERS[item["adapter_id"]]["label"] for item in matches[index + 1:]
                                                               if days_of(item["adapter_id"])[1]]
        try:
            suggestion = securities.suggest_securities_statement_accounts_v1(canonical, context, parsed)
        except securities.SecuritiesStatementImportV1Error:
            continue
        found = sorted({suggestion["trusted_account_refs"][depot["suggested_account_ref"]] for depot in suggestion["public"]["depots"]
                        if depot.get("suggested_account_ref") in suggestion["trusted_account_refs"]})
        found = [account_id for account_id in found if account_id in accounts.catalog]
        basis = "reader" if found else None
        if not found:
            text = securities._text(source, name)
            found = accounts.by_number(text)
            basis = "account_number" if found else None
        statement = not parsed.get("candidates") and parsed.get("statement_count")
        kind = "account_statement" if statement else ("transaction_export" if name.lower().endswith(".csv") else "confirmation")
        # Ein Beleg, den der Leser als Vorabpauschale liest (ING, Scalable), ist ein Jahresdokument (#536); bis rc.357 "Abrechnung".
        if kind == "confirmation" and parsed.get("candidates") and all(item.get("kind") == "advance_lump_sum" for item in parsed["candidates"]):
            kind = "advance_lump_sum"
        return {"reader": " · ".join(readers), "document_kind": kind, "period_from": _month(min(days)), "period_to": _month(max(days)),
                "account_ids": found, "account_basis": basis}
    return None


def _plain_text(source: bytes, name: str) -> str:
    """Der Text einer Datei, die kein Leser liest - leer, wenn sie keinen hat (ein eingescannter Brief, rc.321). Bis dahin hielt
    ein PDF ohne Textebene den ganzen Vorschlag an."""
    if not name.lower().endswith((".pdf", ".txt", ".csv")):
        return ""
    try:
        return "\n".join(cash._pdf_text(source, name))
    except cash.CashStatementImportV1Error as error:
        if error.code == "cash_statement_pdf_tool_missing":
            raise
        return ""


def _fallback_accounts(text: str, tax: bool, accounts: _Accounts, institution: Mapping[str, Any] | None) -> tuple[list[str], str | None]:
    """Konten einer Datei, die kein Leser liest. Ohne Institut wie bisher: genau eine Kontonummer im Text. Mit dem Institut des
    Eingangs (rc.320) zaehlen nur dessen Konten - eine Steuerunterlage nennt oft auch das Referenzkonto bei einer anderen Bank. Eine
    Steuerunterlage gehoert zu allen genannten Konten des Instituts; nennt sie keines, zu allen Konten des Instituts, wenn das
    Rezept das erlaubt (nicht bei Baader und Smartbroker+, die sich die Bank teilen)."""
    flat = _normal(text)
    hits = sorted(account_id for account_id, number in accounts.numbers.items() if number in flat)
    words = tuple(institution.get("words") or ()) if institution else ()
    # Ein Unterordner ohne Rezept (#486) zaehlt mit seinem Namen nur, wenn der Name genau ein Institut der Konten trifft ("Beispiel Bank"). Trifft er keines ("Steuern") oder mehrere ("Bank": DKB Bank, C24 Bank ...), gilt wie ohne Institut die Kontonummer.
    if words and institution.get("from_folder") and len({accounts.catalog[account_id]["institution_label"] for account_id in accounts.of_institution(words)}) != 1:
        words = ()
    if not words:
        return (hits, "account_number") if len(hits) == 1 else ([], None)
    own = [account_id for account_id in hits if _matches(words, accounts.catalog[account_id].get("display_name"), accounts.catalog[account_id]["institution_label"])]
    if tax and own:
        return own, "account_number"
    if not tax:
        return (own, "account_number") if len(own) == 1 else ([], None)
    if institution.get("tax_fallback"):
        every = accounts.of_institution(words)
        return (every, "institution") if every else ([], None)
    return [], None


def _folder_years(value, count: int) -> None:
    if value is not None and (not isinstance(value, (list, tuple)) or len(value) != count or not all(
            year is None or (isinstance(year, int) and not isinstance(year, bool) and 1900 <= year <= 2099) for year in value)):
        raise StatementArchiveV1Error("statement_archive_input_invalid")


@reader_plugins.within_reader_session
def suggest_statement_placements_v1(space, context_value, sources: Sequence[tuple[str, str]], institution: Mapping[str, Any] | None = None,
                                    other_years: Sequence[int | None] | None = None,
                                    advance_years: Sequence[int | None] | None = None) -> dict[str, Any]:
    """Je Datei (Pfad, Dateiname) ein Vorschlag fuer die Ablage. Vollstaendig ist er mit Zeitraum und mindestens einem Konto.

    'institution' (vom Eingang, rc.320): {"words": Woerter des Instituts, "tax_fallback": bool, optional "from_folder": Woerter aus dem Namen
    eines Unterordners ohne Rezept} - wirkt nur auf Dateien, die kein Leser liest. 'other_years' (vom Eingang, rc.321): je Datei das Jahr ihres Ordners "Sonstiges" oder None. Eine solche Datei ist
    "Sonstiges" dieses Jahres, ohne Leser; ihre Konten wie bei einer Steuerunterlage - der Eigentuemer hat sie so einsortiert.
    'advance_years' (vom Eingang, #536): je Datei das Jahr ihres Ordners "Vorabpauschalen" oder None. Die Leser lesen sie wie jede
    Datei; der Ordner setzt nur die Art. Was kein Leser erkennt, gilt fuer Januar des Ordnerjahres - den Monat des Zuflusses am
    ersten Werktag (§ 18 Abs. 3 InvStG), den auch die Leser aus Ex-Tag bzw. Zahltag setzen - und fuer die Konten wie bei einer
    Steuerunterlage."""
    context = statement_archive_scope_v1(context_value)
    space = Path(space)
    if not isinstance(sources, (list, tuple)) or not 0 < len(sources) <= MAX_FILES:
        raise StatementArchiveV1Error("statement_archive_input_invalid")
    _folder_years(other_years, len(sources))
    _folder_years(advance_years, len(sources))
    if other_years is not None and advance_years is not None and any(
            first is not None and second is not None for first, second in zip(other_years, advance_years)):
        raise StatementArchiveV1Error("statement_archive_input_invalid")
    accounts = _Accounts(space, context)
    canonical = space / "canonical.sqlite"
    rows = []
    # Die Cash-Leser laufen abgeschottet (rc.373); je Leser ein Aufruf fuer alle Dateien statt je Datei und Leser.
    prefetch = []
    for index, item in enumerate(sources, 1):
        if isinstance(item, (list, tuple)) and len(item) == 2 and all(isinstance(value, str) for value in item) \
                and (other_years is None or other_years[index - 1] is None):
            path = Path(item[0])
            if not path.is_symlink() and path.is_file() and path.stat().st_size <= MAX_SUGGEST_BYTES:
                prefetch.append((path.read_bytes(), re.split(r"[\\/]", item[1])[-1]))
    prefetched = cash.cash_prefetch_v1(prefetch) if prefetch else []
    prefetched_securities = securities.securities_prefetch_v1(prefetch, ("securities", "crypto", "fx")) if prefetch else []
    try:
        return _suggest_rows(space, context, sources, institution, other_years, advance_years, accounts, canonical, rows)
    finally:
        cash.cash_prefetch_release_v1(prefetched)
        securities.securities_prefetch_release_v1(prefetched_securities)


def _suggest_rows(space, context, sources, institution, other_years, advance_years, accounts, canonical, rows):
    for index, item in enumerate(sources, 1):
        if not isinstance(item, (list, tuple)) or len(item) != 2 or not all(isinstance(value, str) for value in item):
            raise StatementArchiveV1Error("statement_archive_input_invalid")
        path, name = Path(item[0]), re.split(r"[\\/]", item[1])[-1]
        row: dict[str, Any] = {"index": index, "file_name": name, "reader": None, "document_kind": None, "period_from": None, "period_to": None,
                               "account_ids": [], "account_basis": None, "reason": None}
        if path.is_symlink() or not path.is_file():
            row["reason"] = "unreadable"
        elif path.stat().st_size > MAX_SUGGEST_BYTES:
            row["reason"] = "too_large"
        else:
            source = path.read_bytes()
            year = other_years[index - 1] if other_years is not None else None
            if year is not None:
                text = _plain_text(source, name)
                ids, basis = _fallback_accounts(text, True, accounts, institution)
                found = {"reader": None, "document_kind": "other", "period_from": f"{year}-01", "period_to": f"{year}-12",
                         "account_ids": ids, "account_basis": basis}
            else:
                found = _cash_suggestion(source, name, accounts)
                if found is None:
                    found = _securities_suggestion(canonical, context, source, name, accounts)
                elif name.lower().endswith(".csv"):
                    # Ein Boersenexport nennt Coins, Staking und das Euro-Guthaben in einer Datei (#521): Der Cash-Leser sieht nur die
                    # Euro-Bewegungen. Erkennt auch ein Krypto- oder Wertpapier-Leser die Datei, gelten beide Sichten zusammen.
                    other = _securities_suggestion(canonical, context, source, name, accounts)
                    if other is not None:
                        # Staking-Ertraege liest keiner der beiden als Vorgang; der Zeitraum der Datei reicht ueber alle ihre Zeilen.
                        spans = [(other["period_from"], other["period_to"]), (found["period_from"], found["period_to"])]
                        spans += [span for span in [_period_from_text(_plain_text(source, name), name)] if span]
                        found = {"reader": f"{other['reader']} · {found['reader']}", "document_kind": "transaction_export",
                                 "period_from": min(span[0] for span in spans), "period_to": max(span[1] for span in spans),
                                 "account_ids": sorted(set(other["account_ids"]) | set(found["account_ids"])),
                                 "account_basis": other["account_basis"] or found["account_basis"]}
            advance = advance_years[index - 1] if advance_years is not None else None
            if found is None and advance is not None:
                text = _plain_text(source, name)
                ids, basis = _fallback_accounts(text, True, accounts, institution)
                found = {"reader": None, "document_kind": "advance_lump_sum", "period_from": f"{advance}-01", "period_to": f"{advance}-01",
                         "account_ids": ids, "account_basis": basis}
            elif found is not None and advance is not None:
                found = {**found, "document_kind": "advance_lump_sum"}
                if not found["account_ids"]:
                    ids, basis = _fallback_accounts(_plain_text(source, name), True, accounts, institution)
                    found.update(account_ids=ids, account_basis=basis)
            if found is None:
                text = _plain_text(source, name)
                period = _period_from_text(text, name)
                kind = _kind_from_text(text, name)
                tax_period = _tax_period(text) if text and (kind in TAX_KINDS or LOSS_OFFSET.search(text[:20000])) else None
                tax = tax_period is not None or kind in TAX_KINDS
                period = period or tax_period
                ids, basis = _fallback_accounts(text, tax, accounts, institution) if text else ([], None)
                found = {"reader": None, "document_kind": kind, "period_from": period[0] if period else None,
                         "period_to": period[1] if period else None, "account_ids": ids, "account_basis": basis}
                if period is None:
                    row["reason"] = "no_period"
            row.update(found)
        row["complete"] = bool(row["period_from"] and row["period_to"] and row["account_ids"] and row["document_kind"])
        if not row["complete"] and row["reason"] is None:
            row["reason"] = "no_account"
        rows.append(row)
    return {"contract_version": CONTRACT, "status": "ready", "files": rows, "complete_count": sum(row["complete"] for row in rows),
            "provider_access": False, "network_access": False, "canonical_write": False}


__all__ = ["CONTRACT", "suggest_statement_placements_v1"]
