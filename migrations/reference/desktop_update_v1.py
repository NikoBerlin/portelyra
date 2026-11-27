"""Update-Suche (#562, ab 0.3.3; Festlegungen vom 25.11.2026).

Quelle ist die Release-Liste bei GitHub, fest eingebaut: SOURCE (nur HTTPS, Zeitlimit, Antwort hoechstens 2 MB). Gefragt wird ohne
Anmeldung und ohne Kennung des Nutzers: User-Agent "Portelyra", keine Cookies, nichts aus dem Bestand. GitHub sieht dabei die IP-Adresse.

Massgeblich ist die Versionsnummer im Tag (`v0.3.4` oder `0.3.4`), nicht das Haekchen "Pre-release" und nicht "Latest". Tags mit
`-rc.N` gelten nur fuer eine laufende Vorabversion. Gewaehlt wird die hoechste Version ueber der laufenden, die das Archiv
`portelyra-<version>.tar.gz` als Anhang hat; ein Release ohne Archiv wird mit Grund uebersprungen. Die Versionshinweise aller
uebersprungenen Versionen kommen mit, als reiner Text. Ein Release zurueckziehen heisst: loeschen oder zum Entwurf machen.

Das Ergebnis steht in <home>/update-status.json (0600); alle vier Apps lesen nur diese Datei und gehen nie ins Netz. Abgefragt wird nur
hier: auf Klick ("click", genau eine Abfrage) oder taeglich ("daily", nur mit Zustimmung in installation-settings.json und hoechstens
einmal am Tag). Die Sicherheit haengt nicht an der Quelle: Ein Archiv wird vor dem Einspielen gegen die installierte Vertrauensliste
geprueft (desktop_release_v1).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import ssl
import time
from typing import Any, Callable, Mapping
import urllib.error
import urllib.parse
import urllib.request

CONTRACT = "desktop_update_v1"
STATUS_CONTRACT = "desktop_update_status_v1"
STATUS_FILE = "update-status.json"
SETTINGS_FILE = "installation-settings.json"
REPOSITORY = "NikoBerlin/portelyra"
SOURCE = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=30"
ARCHIVE_PREFIX = f"https://github.com/{REPOSITORY}/releases/download/"
# Nur fuer Tests: eine lokale Quelle (http://127.0.0.1:<port>/...). Ein anderes Benutzerkonto kann die Umgebung dieses Prozesses nicht setzen.
SOURCE_ENV = "PORTELYRA_UPDATE_SOURCE_INTERNAL"
USER_AGENT = "Portelyra"
TIMEOUT_SECONDS = 15
LIST_LIMIT_BYTES = 2_000_000
NOTES_LIMIT_CHARS = 20_000
ARCHIVE_LIMIT_BYTES = 512 * 1024 * 1024
DAILY_SECONDS = 24 * 60 * 60
TRIGGERS = ("click", "daily")
FAILURE_CODES = (
    "desktop_update_input_invalid", "desktop_update_state_invalid", "update_version_unknown", "update_source_unreachable",
    "update_source_timeout", "update_source_not_found", "update_source_rate_limited", "update_source_failed", "update_source_too_large",
    "update_source_invalid", "update_consent_missing", "update_not_due",
    "update_download_not_offered", "update_download_not_found", "update_download_failed", "update_download_timeout",
    "update_download_unreachable", "update_download_size_mismatch", "update_download_digest_mismatch",
)
VERSION = re.compile(r"^v?(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})(?:-rc\.(0|[1-9][0-9]{0,4}))?$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class DesktopUpdateV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if code in FAILURE_CODES else "desktop_update_state_invalid"


def _abort(code: str) -> None:
    raise DesktopUpdateV1Error(code)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_stamp(text: Any) -> datetime | None:
    if not isinstance(text, str):
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _home(home: Any) -> Path:
    if not isinstance(home, str):
        _abort("desktop_update_input_invalid")
    path = Path(home).expanduser()
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        _abort("desktop_update_input_invalid")
    return path.resolve()


def version_key(text: Any) -> tuple[int, int, int, int, int] | None:
    """Sortierschluessel; die fertige Version liegt hinter allen Vorabversionen derselben Nummer."""
    match = VERSION.fullmatch(text) if isinstance(text, str) else None
    if match is None:
        return None
    major, minor, patch, rc = match.groups()
    return (int(major), int(minor), int(patch), 0 if rc is not None else 1, int(rc) if rc is not None else 0)


def canonical_version(text: str) -> str:
    return text[1:] if text.startswith("v") else text


def _plain(text: Any) -> str:
    """Versionshinweise aus dem Netz nur als reiner Text: Steuerzeichen (ausser Zeilenumbruch und Tab) entfallen, hoechstens 20 000 Zeichen."""
    if not isinstance(text, str):
        return ""
    cleaned = "".join(char for char in text.replace("\r\n", "\n").replace("\r", "\n") if char in "\n\t" or ord(char) >= 32)
    cleaned = cleaned.strip()
    return cleaned if len(cleaned) <= NOTES_LIMIT_CHARS else cleaned[:NOTES_LIMIT_CHARS].rstrip() + " …"


def archive_prefix_v1() -> str:
    """Woher ein Archiv kommen darf: die Release-Seite des Repos bei GitHub; mit der lokalen Testquelle deren Ursprung."""
    override = os.environ.get(SOURCE_ENV, "")
    if not override:
        return ARCHIVE_PREFIX
    parts = urllib.parse.urlsplit(override)
    return f"{parts.scheme}://{parts.netloc}/{REPOSITORY}/releases/download/"


def select_v1(releases: Any, running: Any) -> dict[str, Any]:
    """Aus der Liste die Version, die angeboten wird. Rein, ohne Netz."""
    prefix = archive_prefix_v1()
    current = version_key(running)
    if current is None:
        _abort("update_version_unknown")
    if not isinstance(releases, list):
        _abort("update_source_invalid")
    prerelease_running = current[3] == 0
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for release in releases:
        if not isinstance(release, Mapping) or release.get("draft") is True:
            continue
        tag = release.get("tag_name")
        key = version_key(tag)
        if key is None:
            skipped.append({"tag": str(tag)[:40], "reason": "tag_invalid"})
            continue
        if key <= current or (key[3] == 0 and not prerelease_running):
            continue
        version = canonical_version(tag)
        wanted = f"portelyra-{version}.tar.gz"
        archive = None
        for asset in release.get("assets") or []:
            if not isinstance(asset, Mapping) or asset.get("name") != wanted:
                continue
            url = asset.get("browser_download_url")
            size = asset.get("size")
            if (asset.get("state", "uploaded") == "uploaded" and isinstance(url, str) and url == f"{prefix}{urllib.parse.quote(tag)}/{wanted}"
                    and isinstance(size, int) and not isinstance(size, bool) and 0 < size <= ARCHIVE_LIMIT_BYTES):
                digest = asset.get("digest")
                archive = {"name": wanted, "size": size, "url": url, "digest": digest if isinstance(digest, str) and DIGEST.fullmatch(digest) else None}
            break
        if archive is None:
            skipped.append({"version": version, "reason": "archive_missing"})
            continue
        candidates.append({"key": key, "version": version, "tag": tag, "archive": archive,
                           "published_at": release.get("published_at") if isinstance(release.get("published_at"), str) else None,
                           "notes": _plain(release.get("body")), "page": release.get("html_url") if isinstance(release.get("html_url"), str) else None})
    if not candidates:
        return {"result": "current", "skipped": skipped}
    candidates.sort(key=lambda item: item["key"])
    chosen = candidates[-1]
    page = chosen["page"] if isinstance(chosen["page"], str) and chosen["page"].startswith(f"https://github.com/{REPOSITORY}/releases/") else None
    return {"result": "available", "version": chosen["version"], "tag": chosen["tag"], "archive": chosen["archive"],
            "published_at": chosen["published_at"], "page": page,
            "notes": [{"version": item["version"], "published_at": item["published_at"], "text": item["notes"]} for item in candidates],
            "skipped": skipped}


def consent_v1(home: Any) -> bool | None:
    """Zustimmung zur taeglichen Suche aus den Einstellungen der Installation: True, False oder None (noch nicht gefragt)."""
    path = _home(home) / SETTINGS_FILE
    if path.is_symlink() or not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    check = value.get("update_check") if isinstance(value, dict) else None
    consent = check.get("consent") if isinstance(check, dict) else None
    return consent if isinstance(consent, bool) else None


def status_read_v1(home: Any) -> dict[str, Any] | None:
    path = _home(home) / STATUS_FILE
    if path.is_symlink() or not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) and value.get("contract_version") == STATUS_CONTRACT else None


def _status_write(home: Path, value: Mapping[str, Any]) -> None:
    path = home / STATUS_FILE
    if path.is_symlink():
        _abort("desktop_update_state_invalid")
    temporary = path.with_name(path.name + f".partial-{os.getpid()}")
    old = os.umask(0o077)
    try:
        temporary.write_text(json.dumps(value, sort_keys=True, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        os.umask(old)
        temporary.unlink(missing_ok=True)


def due_v1(home: Any, now: datetime | None = None) -> dict[str, Any]:
    """Ob die taegliche Suche faellig ist: nur mit Zustimmung, und wenn die letzte Abfrage (gleich welche) mehr als einen Tag her ist."""
    resolved = _home(home)
    if consent_v1(str(resolved)) is not True:
        return {"due": False, "reason": "consent_missing"}
    previous = status_read_v1(str(resolved))
    last = _parse_stamp(previous.get("checked_at_utc")) if previous else None
    moment = now or _now()
    if last is not None and moment - last < timedelta(seconds=DAILY_SECONDS) and last <= moment:
        return {"due": False, "reason": "not_due", "next_at_utc": _stamp(last + timedelta(seconds=DAILY_SECONDS))}
    return {"due": True, "reason": "due"}


class _OnlySource(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen nur innerhalb der Quelle (etwa ein umbenanntes Repo, 301); nie auf einen anderen Host oder ohne HTTPS."""

    def __init__(self, origin: str) -> None:
        super().__init__()
        self.origin = origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        target = urllib.parse.urlsplit(newurl)
        if f"{target.scheme}://{target.netloc}" != self.origin:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _source() -> str:
    override = os.environ.get(SOURCE_ENV, "")
    if override:
        parts = urllib.parse.urlsplit(override)
        if parts.scheme != "http" or parts.hostname != "127.0.0.1":
            _abort("desktop_update_input_invalid")
        return override
    return SOURCE


def fetch_v1(url: str, headers: Mapping[str, str]) -> tuple[int, dict[str, str], bytes]:
    """Eine Abfrage: (Status, Kopfzeilen in Kleinschreibung, Inhalt). Ohne Proxy-Anmeldung, ohne Cookies; Inhalt hoechstens 2 MB + 1 Byte."""
    parts = urllib.parse.urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    handlers: list[Any] = [_OnlySource(origin)]
    if parts.scheme == "https":
        handlers.append(urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(LIST_LIMIT_BYTES + 1)
            return response.status, {key.lower(): value for key, value in response.headers.items()}, body
    except urllib.error.HTTPError as error:
        return error.code, {key.lower(): value for key, value in (error.headers or {}).items()}, b""


def _failure(code: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, **{key: value for key, value in extra.items() if value is not None}}


def check_v1(home: Any, running: Any, trigger: Any, now: datetime | None = None,
             fetch: Callable[[str, Mapping[str, str]], tuple[int, Mapping[str, str], bytes]] | None = None) -> dict[str, Any]:
    """Eine Abfrage und ihr Ergebnis in update-status.json. "daily" ohne Zustimmung oder vor Ablauf eines Tages fragt nicht."""
    resolved = _home(home)
    if trigger not in TRIGGERS:
        _abort("desktop_update_input_invalid")
    if version_key(running) is None:
        _abort("update_version_unknown")
    moment = now or _now()
    if trigger == "daily":
        due = due_v1(str(resolved), moment)
        if not due["due"]:
            _abort("update_consent_missing" if due["reason"] == "consent_missing" else "update_not_due")
    previous = status_read_v1(str(resolved))
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    # Unveraenderte Liste (304) zaehlt bei GitHub nicht gegen das Abfragelimit; gilt nur fuer dieselbe laufende Version.
    reuse = (previous is not None and previous.get("running_version") == running and previous.get("result") in ("current", "available")
             and isinstance(previous.get("etag"), str) and len(previous["etag"]) < 200)
    if reuse:
        headers["If-None-Match"] = previous["etag"]
    status: dict[str, Any] = {"contract_version": STATUS_CONTRACT, "checked_at_utc": _stamp(moment), "trigger": trigger,
                              "running_version": running, "source": "github"}
    try:
        code, reply, body = (fetch or fetch_v1)(_source(), headers)
    except (socket.timeout, TimeoutError):
        code, reply, body = -1, {}, b""
        status.update(result="failed", failure=_failure("update_source_timeout"))
    except (urllib.error.URLError, OSError, ssl.SSLError, ValueError) as error:
        code, reply, body = -1, {}, b""
        reason = getattr(error, "reason", None)
        timed_out = isinstance(reason, (socket.timeout, TimeoutError))
        status.update(result="failed", failure=_failure("update_source_timeout" if timed_out else "update_source_unreachable"))
    if code == 304 and reuse:
        for key in ("result", "version", "tag", "archive", "published_at", "page", "notes", "skipped", "etag"):
            if key in previous:
                status[key] = previous[key]
        status["unchanged"] = True
    elif code == 200:
        if len(body) > LIST_LIMIT_BYTES:
            status.update(result="failed", failure=_failure("update_source_too_large"))
        else:
            try:
                releases = json.loads(body.decode("utf-8"))
                status.update(select_v1(releases, running))
                etag = reply.get("etag")
                if isinstance(etag, str) and len(etag) < 200:
                    status["etag"] = etag
            except (UnicodeDecodeError, ValueError):
                status.update(result="failed", failure=_failure("update_source_invalid"))
            except DesktopUpdateV1Error as error:
                status.update(result="failed", failure=_failure(error.code))
    elif code == 404:
        status.update(result="failed", failure=_failure("update_source_not_found", http_status=404))
    elif code in (403, 429) and (reply.get("x-ratelimit-remaining") == "0" or code == 429):
        reset = reply.get("x-ratelimit-reset")
        retry = None
        if isinstance(reset, str) and reset.isdigit():
            retry = _stamp(datetime.fromtimestamp(int(reset), tz=timezone.utc))
        status.update(result="failed", failure=_failure("update_source_rate_limited", http_status=code, retry_after_utc=retry))
    elif code > 0:
        status.update(result="failed", failure=_failure("update_source_failed", http_status=code))
    if "result" not in status:
        status.update(result="failed", failure=_failure("update_source_failed"))
    _status_write(resolved, status)
    return status


DOWNLOADS_DIR = "update-downloads"
DOWNLOAD_HOSTS = ("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")
DOWNLOAD_TIMEOUT_SECONDS = 30          # je Lesevorgang
DOWNLOAD_TOTAL_SECONDS = 900           # hoechstens 15 Minuten fuer das ganze Archiv
CHUNK_BYTES = 1024 * 1024


class _OnlyDownloadHosts(urllib.request.HTTPRedirectHandler):
    """Das Archiv leitet GitHub auf einen eigenen Host weiter (Live-Probe 25.11.2026: release-assets.githubusercontent.com). Erlaubt sind
    nur HTTPS-Ziele bei GitHub; mit der lokalen Testquelle nur deren Ursprung."""

    def __init__(self, local_origin: str | None) -> None:
        super().__init__()
        self.local_origin = local_origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        target = urllib.parse.urlsplit(newurl)
        if self.local_origin is not None:
            if f"{target.scheme}://{target.netloc}" != self.local_origin:
                return None
        elif target.scheme != "https" or target.hostname not in DOWNLOAD_HOSTS:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download_dir(home: Path) -> Path:
    path = home / DOWNLOADS_DIR
    if path.is_symlink():
        _abort("desktop_update_state_invalid")
    path.mkdir(mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def download_v1(home: Any, version: Any, running: Any, now: datetime | None = None,
                opener: Callable[[str, Mapping[str, str]], Any] | None = None) -> dict[str, Any]:
    """Laedt das Archiv der zuletzt gefundenen Version herunter: nur die Adresse aus update-status.json (die select_v1 geprueft hat),
    Groesse genau wie angekuendigt, SHA-256 wie der digest des Anhangs (falls GitHub ihn nennt). Ergebnis: Datei unter
    <home>/update-downloads/portelyra-<version>.tar.gz (0600) mit Pruefsumme. Die Signatur prueft danach release-check."""
    resolved = _home(home)
    if version_key(version) is None or version_key(running) is None:
        _abort("update_version_unknown")
    status = status_read_v1(str(resolved))
    archive = status.get("archive") if isinstance(status, dict) else None
    if (not isinstance(status, dict) or status.get("result") != "available" or status.get("version") != version
            or not isinstance(archive, dict) or version_key(version) <= version_key(running)):
        _abort("update_download_not_offered")
    url, size, digest, name, tag = archive.get("url"), archive.get("size"), archive.get("digest"), archive.get("name"), status.get("tag")
    if (not isinstance(tag, str) or canonical_version(tag) != version or name != f"portelyra-{version}.tar.gz"
            or url != f"{archive_prefix_v1()}{urllib.parse.quote(tag)}/{name}"
            or not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= ARCHIVE_LIMIT_BYTES):
        _abort("update_download_not_offered")
    target_dir = _download_dir(resolved)
    target = target_dir / name
    partial = target_dir / f"{name}.partial-{os.getpid()}"
    override = os.environ.get(SOURCE_ENV, "")
    local_origin = None
    if override:
        parts = urllib.parse.urlsplit(override)
        local_origin = f"{parts.scheme}://{parts.netloc}"
    handlers: list[Any] = [_OnlyDownloadHosts(local_origin)]
    if url.startswith("https://"):
        handlers.append(urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"}, method="GET")
    digest_seen = hashlib.sha256()
    received = 0
    started = time.monotonic()
    old = os.umask(0o077)
    try:
        try:
            response = (opener or urllib.request.build_opener(*handlers).open)(request, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        except urllib.error.HTTPError as error:
            _abort("update_download_not_found" if error.code == 404 else "update_download_failed")
        except (socket.timeout, TimeoutError):
            _abort("update_download_timeout")
        except (urllib.error.URLError, OSError, ssl.SSLError):
            _abort("update_download_unreachable")
        with response, open(partial, "wb") as sink:
            while True:
                if time.monotonic() - started > DOWNLOAD_TOTAL_SECONDS:
                    _abort("update_download_timeout")
                try:
                    chunk = response.read(CHUNK_BYTES)
                except (socket.timeout, TimeoutError):
                    _abort("update_download_timeout")
                except OSError:
                    _abort("update_download_unreachable")
                if not chunk:
                    break
                received += len(chunk)
                if received > size:
                    _abort("update_download_size_mismatch")
                digest_seen.update(chunk)
                sink.write(chunk)
        if received != size:
            _abort("update_download_size_mismatch")
        sha256 = digest_seen.hexdigest()
        if isinstance(digest, str) and digest != f"sha256:{sha256}":
            _abort("update_download_digest_mismatch")
        os.chmod(partial, 0o600)
        os.replace(partial, target)
    finally:
        os.umask(old)
        partial.unlink(missing_ok=True)
    # Aeltere Downloads entfallen; nur das eben gepruefte Archiv bleibt.
    for other in target_dir.glob("portelyra-*.tar.gz"):
        if other != target and not other.is_symlink():
            other.unlink(missing_ok=True)
    return {"version": version, "file": str(target), "size": received, "sha256": sha256, "digest_checked": isinstance(digest, str),
            "downloaded_at_utc": _stamp(now or _now())}


__all__ = [
    "ARCHIVE_PREFIX", "CONTRACT", "FAILURE_CODES", "SOURCE", "SOURCE_ENV", "STATUS_CONTRACT", "STATUS_FILE", "DesktopUpdateV1Error",
    "archive_prefix_v1", "canonical_version", "check_v1", "consent_v1", "download_v1", "due_v1", "fetch_v1", "select_v1", "status_read_v1",
    "version_key",
]
