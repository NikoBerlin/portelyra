"""Wann ein Handelstag abgeschlossen ist (#475, #516). Nur Rechnung, kein Speicher, kein Abruf.

Der Kursabruf endete bis rc.282 bei "gestern" nach Ortszeit. Kurz nach Mitternacht (MESZ) laeuft der
UTC-Tag von gestern aber noch: Fuer Krypto und Wechselkurse lieferte die Quelle dann einen laufenden Kurs als Tageswert,
und weil der Tag danach als vorhanden galt, holte ihn kein spaeterer Lauf erneut. Ein Tag gilt deshalb erst als
abgeschlossen, wenn er vorbei ist - zuzueglich einer Stunde, in der die Quelle ihren Tageswert noch nachzieht.

Zwei Arten (Einstellung "Tageskurse abrufen ab", Festlegung 05.11.2026, rc.368):

- **session_close** (Vorgabe): Boersennotierungen mit bekannter Schlusszeit gelten eine Stunde nach Handelsschluss als
  abgeschlossen - XETRA ab 18:35, New York ab 23:00 deutscher Zeit. Ein Lauf kurz nach Mitternacht holt so den Vortag; bisher
  galt er erst ab 1 Uhr (New York ab 7 Uhr). Die Kurskette ruft weiter hoechstens bis gestern ab (heute zeigt die
  Momentaufnahme), und ein Asset in Fremdwaehrung endet beim letzten abgeschlossenen Tag seines Waehrungspaares.
- **calendar_day_end**: jede Notierung erst nach dem Ende des Kalendertags in ihrer Zeitzone (das Verhalten bis rc.367).

Krypto, Wechselkurse und Notierungen ohne bekannte Schlusszeit gelten in beiden Arten erst nach dem Tagesende: Dort laeuft
der Handel bis Mitternacht, und genau da hatte bis rc.282 ein laufender Tageskurs als Tageswert gegolten. Die Schlusszeiten
sind bewusst die spaeteste regulaere Schlusszeit je Boerse (Frankfurt und Stuttgart handeln bis 22:00). Zu frueh waere
falsch: Ein danach geholter Wert gaelte als endgueltig und wuerde nie erneut angefordert.

Ein Tageswert, der vor diesem Zeitpunkt abgerufen wurde, ist vorlaeufig: Die Planung fordert ihn erneut an, bis ein Abruf
nach dem Abschluss ihn bestaetigt oder korrigiert.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

COMPLETION_MARGIN = timedelta(hours=1)
MODES = ("session_close", "calendar_day_end")
DEFAULT_MODE = "session_close"

# Handelsschluss je Boerse (Kuerzel der Notierung, wie sie die Einrichtung speichert): Zeitzone der Boerse und spaeteste
# regulaere Schlusszeit samt Schlussauktion. Nicht aufgefuehrte Kuerzel (Krypto CCC, Devisen CCY, Terminboersen wie CMX)
# gelten erst nach dem Tagesende.
SESSION_CLOSES = {
    "GER": ("Europe/Berlin", time(17, 35)),       # XETRA, Schlussauktion bis 17:35
    "FRA": ("Europe/Berlin", time(22, 0)),        # Boerse Frankfurt
    "STU": ("Europe/Berlin", time(22, 0)),        # Boerse Stuttgart
    "NYQ": ("America/New_York", time(16, 0)),     # NYSE
    "NMS": ("America/New_York", time(16, 0)),     # Nasdaq Global Select
    "NGM": ("America/New_York", time(16, 0)),     # Nasdaq Global Market
    "NCM": ("America/New_York", time(16, 0)),     # Nasdaq Capital Market
    "PNK": ("America/New_York", time(16, 0)),     # OTC Markets
    "LSE": ("Europe/London", time(16, 35)),       # London, Schlussauktion bis 16:35
    "PAR": ("Europe/Paris", time(17, 35)),        # Euronext Paris
    "AMS": ("Europe/Amsterdam", time(17, 35)),    # Euronext Amsterdam
    "MIL": ("Europe/Rome", time(17, 35)),         # Borsa Italiana
    "EBS": ("Europe/Zurich", time(17, 30)),       # SIX Swiss Exchange
    "VIE": ("Europe/Vienna", time(17, 35)),       # Wiener Boerse
}


def _moment(now_utc: datetime | None) -> datetime:
    moment = now_utc if now_utc is not None else datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("market_day_completion_naive_time")
    return moment


def _mode(mode: str) -> str:
    if mode not in MODES:
        raise ValueError("market_day_completion_mode_invalid")
    return mode


def session_close_v1(market_code: str | None, mode: str = DEFAULT_MODE):
    """(Zeitzone, Schlusszeit) der Boerse, wenn sie in dieser Art nach Handelsschluss abgeschlossen ist; sonst None."""
    if _mode(mode) != "session_close" or market_code is None:
        return None
    return SESSION_CLOSES.get(market_code)


def completed_through_v1(timezone_name: str, now_utc: datetime | None = None, *, market_code: str | None = None,
                         mode: str = "calendar_day_end") -> str:
    """Der juengste Tag, der samt Sicherheitsspanne abgeschlossen ist (ISO-Datum): nach Handelsschluss der Boerse oder nach
    dem Ende des Kalendertags in 'timezone_name'."""
    moment = _moment(now_utc)
    close = session_close_v1(market_code, mode)
    if close is not None:
        local = (moment - COMPLETION_MARGIN).astimezone(ZoneInfo(close[0]))
        return (local.date() if local.time() >= close[1] else local.date() - timedelta(days=1)).isoformat()
    local = (moment - COMPLETION_MARGIN).astimezone(ZoneInfo(timezone_name))
    return (local.date() - timedelta(days=1)).isoformat()


def completed_at_v1(trading_date: str, timezone_name: str, *, market_code: str | None = None, mode: str = "calendar_day_end") -> str:
    """Ab wann ein Tag als abgeschlossen gilt, als UTC-Zeitpunkt im Format der Abrufzeiten (JJJJ-MM-TTThh:mm:ssZ). Ein Wert,
    der vorher abgerufen wurde, ist vorlaeufig."""
    day = date.fromisoformat(trading_date)
    close = session_close_v1(market_code, mode)
    if close is not None:
        end = datetime.combine(day, close[1], tzinfo=ZoneInfo(close[0]))
    else:
        end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=ZoneInfo(timezone_name))
    return (end + COMPLETION_MARGIN).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def completed_end_v1(end_date: str, timezone_name: str, now_utc: datetime | None = None, *, market_code: str | None = None,
                     mode: str = "calendar_day_end") -> str:
    """Das gewuenschte Ende, hoechstens bis zum juengsten abgeschlossenen Tag der Notierung."""
    date.fromisoformat(end_date)
    return min(end_date, completed_through_v1(timezone_name, now_utc, market_code=market_code, mode=mode))


__all__ = ["COMPLETION_MARGIN", "DEFAULT_MODE", "MODES", "SESSION_CLOSES", "completed_at_v1", "completed_end_v1",
           "completed_through_v1", "session_close_v1"]
