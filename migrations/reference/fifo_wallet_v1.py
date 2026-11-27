"""FIFO-Wallet aus mehreren Konten (#508) - die Zuordnung eines Unterkontos zu einem Hauptkonto, neben den Stammdaten.

Festlegung (23.10.2026): Bucht man innerhalb einer Boerse auf ein Staking-Konto um, ist das Staking-Konto steuerlich eher
ein Unterkonto des Hauptkontos als eine eigene Wallet (BMF 06.03.2025, Rn. 62: walletbezogene Betrachtung). Ein Konto laesst sich
deshalb einem Hauptkonto desselben Instituts zuordnen ("FIFO gemeinsam mit Konto ..."); beide bilden dann eine FIFO-Wallet.

Festlegungen (23.10.2026):
- Nur Kryptowerte. Eine Boerse oder ein Hardware-Wallet ist das "Institut"; seine Unterkonten und Verwahrorte (Staking, Earn,
  weitere Konten auf dem Geraet) lassen sich einem Hauptkonto desselben Instituts zuordnen. Wertpapiere nie: Bei Brokern gilt
  FIFO je Depot (§ 20 Abs. 4 Satz 7 EStG); Wertpapier-, Cash- und Devisenkonten werden nicht angeboten.
- Die Zuordnung gilt fuer die ganze Historie des Kontos; sie beschreibt das Konto.
- Eine Stufe: Ein Hauptkonto ist selbst keinem anderen zugeordnet, ein Unterkonto hat keine eigenen Unterkonten.

Ein Eintrag nennt Konto und Hauptkonto. Der Speicher haengt nur an; je Konto gilt der juengste Eintrag, ein Eintrag ohne
Hauptkonto loest die Zuordnung. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write. Die Zuordnung aendert den
FIFO-Stand; er wird danach fortgeschrieben.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import sqlite3

from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1, DesktopProductAssetActivityV1Error, _context,
)

AREA = "fifo-wallet-v1"
STORE = "fifo-wallet.sqlite"
SCHEMA_VERSION = 1
CONTRACT = "fifo_wallet_v1"
ACCOUNT_ID = re.compile(r"acc_[a-z0-9_]{4,60}")
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
CRYPTO_ACCOUNT_TYPE = "crypto_wallet"
FAILURE_CODES = (
    "fifo_wallet_account_not_crypto",
    "fifo_wallet_account_unknown",
    "fifo_wallet_chain_invalid",
    "fifo_wallet_confirmation_required",
    "fifo_wallet_entry_unknown",
    "fifo_wallet_input_invalid",
    "fifo_wallet_institution_mismatch",
    "fifo_wallet_preview_failed",
    "fifo_wallet_store_invalid",
)
SCHEMA = (
    "CREATE TABLE fifo_wallet_binding("
    "singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE wallet_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, wallet_account_id TEXT,"
    " recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX wallet_entry_key ON wallet_entry(account_id, entry_id)",
    *(f"CREATE TRIGGER wallet_entry_no_{action} BEFORE {action.upper()} ON wallet_entry BEGIN SELECT RAISE(ABORT, 'wallet_entry_immutable'); END"
      for action in ("update", "delete")),
    "CREATE VIEW current_wallet_entry AS SELECT entry.* FROM wallet_entry entry WHERE entry.entry_id = "
    "(SELECT max(later.entry_id) FROM wallet_entry later WHERE later.account_id = entry.account_id)",
)


class FifoWalletV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def fifo_wallet_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise FifoWalletV1Error(code if code in FAILURE_CODES else "fifo_wallet_store_invalid")


def fifo_wallet_context_v1(value):
    """Geprueftes Kontextobjekt; nimmt auch die JSON-Form der CLI-Grenze an."""
    if isinstance(value, dict):
        if set(value) != {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}:
            _abort("fifo_wallet_input_invalid")
        try:
            value = DesktopProductAssetActivityContextV1(**value)
        except TypeError:
            _abort("fifo_wallet_input_invalid")
    try:
        return _context(value)
    except DesktopProductAssetActivityV1Error:
        _abort("fifo_wallet_input_invalid")


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _connect(space, context, create: bool):
    root = Path(space) / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink():
        _abort("fifo_wallet_store_invalid")
    expected = (SCHEMA_VERSION, context.tenant_id, context.user_id, context.data_space_id)
    if not store.exists():
        if not create:
            return None
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        connection = sqlite3.connect(store)
        try:
            with connection:
                for statement in SCHEMA:
                    connection.execute(statement)
                connection.execute("INSERT INTO fifo_wallet_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("fifo_wallet_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id FROM fifo_wallet_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("fifo_wallet_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("fifo_wallet_store_invalid")
    return connection


def _accounts(space, context) -> dict[str, dict]:
    """Die Konten der Stammdaten - gelesen, nicht veraendert."""
    canonical = Path(space) / "canonical.sqlite"
    if not canonical.is_file() or canonical.is_symlink():
        _abort("fifo_wallet_store_invalid")
    try:
        connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
        try:
            binding = connection.execute("SELECT tenant_id,user_id,data_space_id FROM store_binding WHERE singleton_id=1").fetchall()
            if len(binding) != 1 or tuple(binding[0]) != (context.tenant_id, context.user_id, context.data_space_id):
                _abort("fifo_wallet_store_invalid")
            return {row[0]: {"label": row[1], "account_type": row[2], "institution": (row[3] or "").strip(), "portfolio_id": row[4],
                             "status": row[5]}
                    for row in connection.execute(
                        "SELECT account_id, display_name, account_type, institution_label, portfolio_id, status FROM account")}
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("fifo_wallet_store_invalid")
        return {}


def _asset_labels(space, context) -> dict[str, str]:
    """Bezeichnungen der Krypto-Assets fuer den Hinweis auf Verkaeufe - gelesen, nicht veraendert."""
    canonical = Path(space) / "canonical.sqlite"
    try:
        connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
        try:
            return {row[0]: row[1] for row in connection.execute("SELECT asset_id, display_name FROM asset WHERE asset_type = 'crypto'")}
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("fifo_wallet_store_invalid")
        return {}


def _stamp(value) -> str:
    if not isinstance(value, str) or UTC.fullmatch(value) is None:
        _abort("fifo_wallet_input_invalid")
    return value


def _current(connection) -> dict[str, str]:
    rows = connection.execute("SELECT account_id, wallet_account_id FROM current_wallet_entry ORDER BY account_id").fetchall()
    return {row["account_id"]: row["wallet_account_id"] for row in rows if row["wallet_account_id"] is not None}


def _read_current(space, context) -> dict[str, str]:
    connection = _connect(space, context, False)
    if connection is None:
        return {}
    try:
        return _current(connection)
    except sqlite3.Error:
        _abort("fifo_wallet_store_invalid")
        return {}
    finally:
        connection.close()


def _check(accounts: dict[str, dict], current: dict[str, str], account_id, wallet_account_id) -> dict[str, str]:
    """Prueft einen Eintrag gegen Stammdaten und bestehende Zuordnungen; liefert die Zuordnungen danach."""
    if not isinstance(account_id, str) or ACCOUNT_ID.fullmatch(account_id) is None:
        _abort("fifo_wallet_input_invalid")
    if wallet_account_id is not None and (not isinstance(wallet_account_id, str) or ACCOUNT_ID.fullmatch(wallet_account_id) is None):
        _abort("fifo_wallet_input_invalid")
    if account_id not in accounts or (wallet_account_id is not None and wallet_account_id not in accounts):
        _abort("fifo_wallet_account_unknown")
    after = dict(current)
    if wallet_account_id is None:
        after.pop(account_id, None)
        return after
    sub, main = accounts[account_id], accounts[wallet_account_id]
    if sub["account_type"] != CRYPTO_ACCOUNT_TYPE or main["account_type"] != CRYPTO_ACCOUNT_TYPE:
        _abort("fifo_wallet_account_not_crypto")
    if (not sub["institution"] or sub["institution"].casefold() != main["institution"].casefold()
            or sub["portfolio_id"] != main["portfolio_id"]):
        _abort("fifo_wallet_institution_mismatch")
    if account_id == wallet_account_id or wallet_account_id in current or account_id in current.values():
        _abort("fifo_wallet_chain_invalid")
    after[account_id] = wallet_account_id
    return after


def record_fifo_wallet_v1(space, context_value, account_id, wallet_account_id, recorded_at_utc, confirmed) -> dict:
    """Haengt eine Zuordnung an: Konto -> Hauptkonto. wallet_account_id None loest sie. Unveraendert schreibt nichts."""
    if confirmed is not True:
        _abort("fifo_wallet_confirmation_required")
    context = fifo_wallet_context_v1(context_value)
    stamp = _stamp(recorded_at_utc)
    accounts = _accounts(space, context)
    current = _read_current(space, context)
    if wallet_account_id is None and account_id not in current:
        _abort("fifo_wallet_entry_unknown")
    if current.get(account_id) == wallet_account_id:
        return {"contract_version": CONTRACT, "status": "unchanged", "provider_access": False, "network_access": False, "canonical_write": False}
    _check(accounts, current, account_id, wallet_account_id)
    connection = _connect(space, context, True)
    try:
        with connection:
            # Unter der Schreibsperre noch einmal: Eine parallele Zuordnung darf keine Kette entstehen lassen.
            _check(accounts, _current(connection), account_id, wallet_account_id)
            row = {"account_id": account_id, "wallet_account_id": wallet_account_id, "recorded_at_utc": stamp}
            connection.execute("INSERT INTO wallet_entry(account_id,wallet_account_id,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?)",
                               (account_id, wallet_account_id, stamp, _fingerprint(row)))
    except sqlite3.Error:
        _abort("fifo_wallet_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded" if wallet_account_id is not None else "removed", "provider_access": False,
            "network_access": False, "canonical_write": False}


def _for_fifo(mapping: dict[str, str]) -> list[dict]:
    return [{"account_ref": account, "wallet_account_ref": wallet} for account, wallet in sorted(mapping.items())]


def fifo_wallets_for_fifo_v1(space, context_value) -> list[dict]:
    """Die gueltigen Zuordnungen in der Form des FIFO-Kerns (`fifo_wallets`), sortiert. Leer ohne Speicher."""
    return _for_fifo(_read_current(space, fifo_wallet_context_v1(context_value)))


def candidate_fifo_wallets_v1(space, context_value, account_id, wallet_account_id) -> list[dict]:
    """Die Zuordnungen, wie sie nach dem Speichern dieses Eintrags gaelten - fuer die Vorschau; schreibt nichts."""
    context = fifo_wallet_context_v1(context_value)
    current = _read_current(space, context)
    if wallet_account_id is None and account_id not in current:
        _abort("fifo_wallet_entry_unknown")
    return _for_fifo(_check(_accounts(space, context), current, account_id, wallet_account_id))


def read_fifo_wallets_v1(space, context_value) -> dict:
    """Die Zuordnungen mit Bezeichnungen und je Institut die Krypto-Konten zur Auswahl."""
    context = fifo_wallet_context_v1(context_value)
    current = _read_current(space, context)
    accounts = _accounts(space, context)
    label = lambda account: accounts.get(account, {}).get("label")
    entries = [{"account_id": account, "account_label": label(account), "wallet_account_id": wallet, "wallet_account_label": label(wallet),
                "institution": accounts.get(account, {}).get("institution", "")} for account, wallet in current.items()]
    entries.sort(key=lambda row: ((row["institution"] or "").casefold(), (row["account_label"] or "").casefold()))
    crypto = [{"account_id": account, "label": meta["label"], "institution": meta["institution"], "portfolio_id": meta["portfolio_id"]}
              for account, meta in accounts.items() if meta["account_type"] == CRYPTO_ACCOUNT_TYPE and meta["status"] != "archived"]
    crypto.sort(key=lambda row: (row["institution"].casefold(), row["label"].casefold()))
    return {"contract_version": CONTRACT, "status": "ready", "entries": entries, "accounts": crypto,
            "asset_labels": _asset_labels(space, context), "provider_access": False, "network_access": False, "canonical_write": False}


__all__ = [
    "AREA", "FAILURE_CODES", "STORE", "FifoWalletV1Error", "candidate_fifo_wallets_v1", "fifo_wallet_context_v1",
    "fifo_wallet_v1_error_codes", "fifo_wallets_for_fifo_v1", "read_fifo_wallets_v1", "record_fifo_wallet_v1",
]
