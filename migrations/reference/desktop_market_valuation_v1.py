"""Owner-local published-history valuation drafts and immutable completion receipts.

Only this module writes market-valuation-v1. No canonical/Market/FX/stage writer
is invoked. Each asset gets one private evidence blob; the browser
receives summaries and explicitly selected day tables, not the whole portfolio.
"""
from contextlib import closing
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
import hashlib
import sqlite3
import os
import stat as stat_module
import re
import time
import uuid
from migrations.reference import desktop_market_fx_batch_execution_v1 as files
from migrations.reference.desktop_market_worklist_v1 import locked, binding
from migrations.reference import daily_market_history_v1 as market
from migrations.reference import fx_history_v1 as fx
from migrations.reference import desktop_fx_history_attempt_v2 as fx_attempts
from migrations.reference import desktop_market_history_review_v1 as native
from migrations.reference import trade_price_reference_v1 as trades
from migrations.reference import manual_price_source_v1 as manual_prices
from migrations.reference.market_valuation_calendar_v1 import propose_calendar
from migrations.reference.market_valuation_projection_v1 import effective_series, convert_series, valuation_policy, SUBSTITUTE_BASES
from migrations.reference import market_valuation_state_v1 as valuation_state
from migrations.reference.market_valuation_requirements_v1 import saved_calendar, calendar_requirements
from migrations.reference.market_calendar_v1 import validate_market_calendar_profile_v1
from migrations.reference.market_calendar_registry_v1 import read_market_calendar_catalog_v1, MarketCalendarRegistryV1Error
from workers.reference.semantic_realized_fifo_v1 import context_values, public_ref

AREA='market-valuation-v1'


def invalid(code='input_invalid'):
    raise ValueError('desktop_market_valuation_'+code)


def _root(space, ctx):
    return space/AREA,files._sha({'scope':binding(space,ctx),'domain':AREA})


def _receipts(path):
    """Quittungen eines Kurs- oder Wechselkursspeichers statt seines Inhalts.

    Jede Aenderung dieser Speicher entsteht durch eine Anfrage mit Quittung und
    eine Notierungs- bzw. Paarbindung. Deren Mengen sagen exakt, ob etwas
    hinzugekommen oder korrigiert wurde - und kosten Millisekunden statt des
    Hashens grosser Datenmengen.
    """
    import sqlite3
    if not os.path.lexists(path):return None
    files._check_owner(path,False)
    try:
        connection=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
    except sqlite3.Error:invalid('source_busy')
    try:
        tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        token={}
        for table,columns in (('daily_market_history_request','request_ref,receipt_fingerprint'),
                              ('market_listing_binding','listing_ref,listing_fingerprint'),
                              ('fx_history_request','request_ref,receipt_fingerprint'),
                              ('fx_pair_binding','pair_ref,pair_fingerprint')):
            if table not in tables:continue
            digest=hashlib.sha256()
            for row in connection.execute('SELECT '+columns+' FROM '+table+' ORDER BY 1'):
                digest.update(('\x1f'.join('' if item is None else str(item) for item in row)+'\x1e').encode())
            token[table]=digest.hexdigest()
        return token
    except sqlite3.Error:
        invalid('source_busy')
    finally:
        connection.close()


def _sealed_set(space, name, skip=()):
    """Die Menge der versiegelten Belege eines Beweisbereichs.

    Diese Dateien werden mit O_EXCL genau einmal geschrieben; Name und Groesse
    bestimmen sie damit eindeutig. Ein laufender Schreibvorgang faellt weiterhin
    ueber sein Journal auf.
    """
    root=space/name
    if not os.path.lexists(root):return None
    entries=[]
    prefix=len(str(space))+1
    def check(info,path,directory):
        expected=0o700 if directory else 0o600
        kind=stat_module.S_ISDIR if directory else stat_module.S_ISREG
        if (not kind(info.st_mode) or stat_module.S_IMODE(info.st_mode)!=expected
                or info.st_uid!=os.geteuid() or (not directory and info.st_nlink!=1)):
            invalid('store_invalid')
    def walk(path,info):
        # Ein Aufruf je Eintrag statt vier: is_dir, is_symlink, Rechtepruefung und
        # Groesse kommen aus demselben lstat. Bei vielen Dateien, viermal je Asset,
        # ist das der Unterschied zwischen Sekunden und Millisekunden.
        if stat_module.S_ISLNK(info.st_mode):return
        if stat_module.S_ISDIR(info.st_mode):
            check(info,path,True)
            with os.scandir(path) as handle:
                children=sorted(handle,key=lambda entry:entry.name)
            for child in children:walk(child.path,child.stat(follow_symlinks=False))
            return
        name=os.path.basename(path)
        if name.endswith('-journal'):invalid('source_busy')
        if name.endswith(('-shm','.lock')) or name=='.lock':return
        # Die beiden SQLite-Speicher deckt die Quittungspruefung ab; ihre Datei
        # zu vermessen brauchte es nicht. Alles andere in ihrem Verzeichnis
        # gehoert aber weiterhin dazu - ein Test hat genau das gefangen
        # (26.09.2026, #283).
        if name in skip or name.startswith(tuple(item+'-' for item in skip)):return
        check(info,path,False)
        entries.append(path[prefix:]+'\x1f'+str(info.st_size))
    walk(str(root),os.lstat(root))
    return hashlib.sha256('\x1e'.join(entries).encode()).hexdigest()


# Die Uhr der Dateizeiten laeuft in groben Takten (Millisekunden). Liegt die juengste Aenderung kuerzer zurueck als diese Spanne,
# misst der Rundgang nach einer kurzen Pause neu - sonst bliebe eine zweite Aenderung im selben Takt unbemerkt.
SEALED_DIRS_SETTLE_NS = 50_000_000
# Ein Verzeichnis, das sich in dieser Spanne geaendert hat, liest der Rundgang nach Namen durch: Ein laufender SQLite-Schreibvorgang
# legt dort sein Journal an und meldet den Bestand als beschaeftigt ('source_busy'), wie im Rundgang je Datei.
SEALED_DIRS_BUSY_NS = 300_000_000_000


def _sealed_dirs(space, name):
    """Die Verzeichnisse eines grossen Beweisbereichs, je mit Kennung und Aenderungszeit (#516, rc.368).

    Belege entstehen hier mit O_EXCL genau einmal oder werden per Umbenennen ersetzt; beides aendert die Aenderungszeit ihres
    Verzeichnisses. Ob sich etwas geaendert hat, zeigt deshalb das Verzeichnis, ohne jede Datei zu vermessen:
    wenige Verzeichnisse statt vieler Dateien, Millisekunden je Aufruf, und die Zahl der Verzeichnisse
    waechst kaum mit den Abrufen. Unterverzeichnisse findet der Rundgang ueber die Linkzahl (2 heisst keine) und sonst ueber
    die Eintragsart, ohne Dateien zu oeffnen. Die Sperrdateien unter 'locks' entstehen beim ersten Gebrauch und gehoeren nicht
    dazu, wie schon im Rundgang je Datei. Rechte und Besitzer prueft er je Verzeichnis; ob jede Datei unversehrt ist, bleibt
    Sache des eigenen Pruefkommandos (Entscheidung 26.09.2026, #283).

    Was er nicht sieht: eine Datei, die an Ort und Stelle ueberschrieben wird. Das tut die App in diesen Bereichen nie - sie
    schreibt neu (O_EXCL) oder ersetzt per Umbenennen -, und der Waechter schuetzt gegen die Nebenlaeufigkeit der App. Ein
    Loeschen und Wiederanlegen laesst ihn umschlagen, auch wenn danach dieselben Dateien liegen: lieber einmal zu oft neu
    bewerten als eine Aenderung uebersehen.
    """
    root=space/name
    if not os.path.lexists(root):return None
    prefix=len(str(space))+1
    for _ in range(6):
        entries=[];newest=0;started=time.time_ns()
        def walk(path):
            nonlocal newest
            info=os.lstat(path)
            if stat_module.S_ISLNK(info.st_mode):return
            if (not stat_module.S_ISDIR(info.st_mode) or stat_module.S_IMODE(info.st_mode)!=0o700
                    or info.st_uid!=os.geteuid()):invalid('store_invalid')
            entries.append(path[prefix:]+'\x1f'+str(info.st_ino)+':'+str(info.st_mtime_ns))
            newest=max(newest,info.st_mtime_ns)
            if info.st_nlink==2 and started-info.st_mtime_ns>=SEALED_DIRS_BUSY_NS:return
            children=[]
            with os.scandir(path) as handle:
                for entry in handle:
                    if entry.name.endswith('-journal'):invalid('source_busy')
                    if entry.name!='locks' and entry.is_dir(follow_symlinks=False):children.append(entry.path)
            for child in sorted(children):walk(child)
        walk(str(root))
        if time.time_ns()-newest>=SEALED_DIRS_SETTLE_NS:break
        time.sleep(SEALED_DIRS_SETTLE_NS/1e9)
    return hashlib.sha256('\x1e'.join(sorted(entries)).encode()).hexdigest()


def _content(space, name):
    """Kleine Bereiche behalten die Inhaltspruefung je Datei.

    Nicht nur, weil sie nichts kostet: Der Kalender-Stapellauf bildet seinen
    eigenen Fingerprint ueber die Eintraege `market-calendar-v1/...`, und die
    Stapelsteuerung erkennt einen frisch angelegten Bereich an seinem Eintrag
    `.context`. Diese Schluessel zu verdichten hiesse, beide blind zu machen.
    """
    root=space/name
    if not os.path.lexists(root):return {}
    result={}
    def walk(p):
        if p.is_dir() and not p.is_symlink():
            files._check_owner(p,True)
            for child in sorted(p.iterdir()):walk(child)
        elif p.name.endswith('-journal'):
            invalid('source_busy')
        elif not p.name.endswith(('-shm','.lock')) and p.name != '.lock':
            files._check_owner(p,False)
            digest=hashlib.sha256()
            with p.open('rb') as handle:
                for block in iter(lambda:handle.read(1024*1024),b''):digest.update(block)
            result[str(p.relative_to(space))]=digest.hexdigest()
    walk(root)
    return result


def _sources(space, include_calendar=False, *, calendar_only=False):
    """Hat sich etwas geaendert, waehrend der Entwurf entstand?

    Die Frage beantworten die Quittungen der Speicher selbst: Anfrage- und
    Bindungsmengen der beiden SQLite-Speicher, die Menge der versiegelten Belege
    der Beweisbereiche und die aktive Generation des Aktivitaetsledgers. Das ist
    exakt fuer alles, was durch die App geschieht - und genau das ist die
    Nebenlaeufigkeit, gegen die der Waechter schuetzt.

    Frueher wurde dafuer der ganze Inhalt gehasht, mehrmals je Asset, und das kostete den
    groessten Teil der Laufzeit. Ob der Bestand unversehrt ist, ist eine eigene Frage und
    gehoert in ein eigenes, bewusst aufgerufenes Pruefkommando (#283).
    """
    result={}
    # Ein geaenderter Leser oder Rechenweg macht offene Entwuerfe ebenso ungueltig
    # wie geaenderte Daten.
    code_paths={Path(function.__code__.co_filename) for function in (
        prepare,trades.read_trade_source,trades.activity.read_desktop_product_asset_activity_binding_v1,propose_calendar,effective_series,convert_series,saved_calendar,calendar_requirements,
        read_market_calendar_catalog_v1,validate_market_calendar_profile_v1,files._read,
        market.read_daily_market_history_v1,fx.read_fx_history_v1,native._read_fetch_attempt,
        fx_attempts.catalog,fx_attempts.api().public_desktop_fx_history_review_v1)}
    for path in sorted(code_paths):result['@code/'+path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    if calendar_only:
        result.update(_content(space,'market-calendar-v1'))
        return result
    # Klein genug fuer den Volltext - und ihre Einzelschluessel werden gebraucht.
    for name in ('canonical.sqlite',files.AREA) + (('market-calendar-v1',) if include_calendar else ()):
        result.update(_content(space,name))
    for name in ('daily-market-history-v1/daily-market-history.sqlite','fx-history-v1/fx-history.sqlite'):
        token=_receipts(space/name)
        if token is not None:result['@receipts/'+name]=token
    # Kleine Bereiche je Datei - dort liegen die SQLite-Speicher, deren Journal einen laufenden Schreibvorgang anzeigt.
    for name,skip in (('desktop-fx-history-review-v1',()),
                      ('daily-market-history-v1',('daily-market-history.sqlite',)),
                      ('fx-history-v1',('fx-history.sqlite',))):
        value=_sealed_set(space,name,skip)
        if value is not None:result['@sealed/'+name]=value
    # Die beiden grossen je Verzeichnis: Belege der Kurshistorie und Generationen des Buchungsbestands (#516, rc.368). Bis
    # rc.367 wuchs der Rundgang mit jeder Datei; er lief mehrmals je Asset.
    for name in (native.AREA,trades.activity.PRODUCT_AREA):
        value=_sealed_dirs(space,name)
        if value is not None:result['@dirs/'+name]=value
    return result


def _pending(space, ctx, mctx, fctx, accepted_stages=frozenset(), listings=None):
    """Unpublished attempts cannot be reclassified as closed-day coverage.

    `listings`: nur die Notierungen des Auftrags (rc.364). Gebraucht wird die Sperre nur fuer sie; bis rc.363 ging jeder
    Auftrag alle je gemachten Abrufversuche durch und las fuer jeden veroeffentlichten den Beleg aus der Kurshistorie, und das kostete den groessten Teil der Bewertung, mit jedem Abruf mehr. Wechselkurs-Versuche
    bleiben vollstaendig: Ein ungeklaerter sperrt alle Fremdwaehrungen (`unknown_fx`)."""
    blocked={};unknown_fx=False
    def add(kind,ref,start,end,reason):
        values=blocked.setdefault((kind,ref),{});cursor=date.fromisoformat(start)
        while cursor<=date.fromisoformat(end):values[cursor.isoformat()]=reason;cursor+=timedelta(days=1)
    attempts=space/native.AREA/'fetch-attempts'
    if attempts.exists():
        files._check_owner(attempts,True)
        # Nur die Versuche der Notierungen des Auftrags: ueber das Verzeichnis je Notierung (rc.365), sonst ueber die Vorauswahl.
        paths=sorted(attempts.glob('*.json')) if listings is None else sorted({path for ref in listings for path in native._fetch_attempt_paths(space/native.AREA,ref)})
        for path in paths:
            attempt=native._read_fetch_attempt(path,native._context(ctx))
            if listings is not None and attempt['listing_ref'] not in listings:continue
            # "aufgeloest" statt "veroeffentlicht": Ein verworfener Stand ist
            # ebenfalls aufgeloest, nur ohne Schreibvorgang.
            stage_path=native._stage_path(space,attempt['stage_ref']);resolved=False
            # Die Veroeffentlichungsquittung beweist dasselbe wie die Stage,
            # kostet aber ein Tausendstel: Sie traegt request_ref und
            # candidate_fingerprint und ist ein Kilobyte gross, waehrend eine
            # Stage die gesamte Kursreihe enthaelt. Bei
            # vielen Stages ist das sehr viel, und diese Pruefung
            # laeuft vor jeder Bewertung,
            # und die Kosten wuchsen mit jedem Abruf (#283).
            # Ein verworfener Stand ist aufgeloest: Sein Schreibvorgang ist
            # nachweislich nie angekommen, und der Beleg sagt das. Ohne diese
            # Zeile sperrte er seinen Zeitraum weiter als "unveroeffentlichter
            # Versuch" - viele Tage blieben offen, obwohl die
            # Kurse inzwischen im Speicher lagen (#283).
            # Ein gescheiterter Abruf, dessen Fehler wiederhergestellt wurde, ist
            # ebenso aufgeloest: Der Fehlerbeleg sagt, dass nichts geschrieben
            # wurde, der Wiederherstellungsbeleg schliesst ihn ab. Das Pruefmodul
            # geht laengst darueber hinweg; nur diese Stelle sperrte weiter.
            # Das hielt viele Bereiche gesperrt, manche nur fuer
            # einen Tag - und weil ein gesperrter Tag den Vorgaenger loescht,
            # blieben Fonds danach dauerhaft ohne Wert (#368).
            area=space/native.AREA
            failure_path=area/'failures'/f"fetch-{attempt['stage_ref']}.json"
            recovery_attempt_path=area/'recovery-attempts'/f"fetch-{attempt['stage_ref']}.json"
            recovery_path=area/'recoveries'/f"fetch-{attempt['stage_ref']}.json"
            discard=area/'discards'/f"{attempt['stage_ref']}.json"
            publication=area/'publications'/f"{attempt['stage_ref']}.json"
            if discard.exists():
                resolved=True
            elif not stage_path.exists() and failure_path.exists() and recovery_attempt_path.exists() and recovery_path.exists():
                context=native._context(ctx)
                failure=native._read_fetch_failure(failure_path,attempt)
                recovery_attempt=native._read_fetch_recovery_attempt(recovery_attempt_path,attempt,failure,context)
                native._read_fetch_recovery(recovery_path,attempt,failure,recovery_attempt,context)
                resolved=True
            elif publication.exists():
                record=native._read_sealed(publication,'publication_fingerprint','desktop_market_history_review_publication_invalid')
                if record.get('status')=='published' and record.get('stage_ref')==attempt['stage_ref']:
                    receipt=market.read_daily_market_request_receipt_v1(space/'daily-market-history-v1/daily-market-history.sqlite',mctx,record['request_ref'])
                    resolved=receipt is not None and receipt.candidate_fingerprint==record['candidate_fingerprint']
            elif stage_path.exists():
                stage=native.read_desktop_market_history_review_stage_v1(space,ctx,attempt['stage_ref'])
                receipt=market.read_daily_market_request_receipt_v1(space/'daily-market-history-v1/daily-market-history.sqlite',mctx,stage['candidate']['request_ref'])
                resolved=receipt is not None and receipt.candidate_fingerprint==stage['candidate']['candidate_fingerprint']
            if not resolved and ('market',attempt['stage_ref']) not in accepted_stages:
                add('market',attempt['listing_ref'],attempt['scope_start_date'],attempt['scope_end_date'],'unpublished_attempt')
    attempts=space/'desktop-fx-history-review-v1/attempts'
    if attempts.exists():
        files._check_owner(attempts,True)
        try:
            # Shared read-only validator: no reset, recovery, grant or writer call.
            # A reviewed absence of a result is not a staged/published result.
            for row in fx_attempts.catalog(space,fctx):
                if row['state']=='published':continue
                if row['state']!='staged':
                    if not row['reviewed_no_result']:unknown_fx=True
                    continue
                if ('fx',row['attempt_ref']) not in accepted_stages:
                    stage=fx_attempts.result_read(attempts.parent/'results'/(row['attempt_ref']+'.json'),space,fctx)
                    add('fx',stage['candidate']['pair_ref'],stage['start_date'],stage['end_date'],'unpublished_attempt')
        except (RuntimeError,ValueError,KeyError,TypeError):
            invalid('stage_invalid')
    # Durable coordinator barriers survive even a native write with lost acknowledgement.
    # Reading a native receipt is not the authority to reconcile a publish_started claim.
    from migrations.reference.desktop_market_fx_batch_publication_v1 import read_market_fx_batch_progress_v1
    for entry in files.list_market_fx_batches_v1(space,ctx):
        batch=files.load_market_fx_batch_v1(space,ctx,entry['execution_ref'])['trusted_batch']
        progress=read_market_fx_batch_progress_v1(space,ctx,batch)
        for item,state in zip(batch['items'],progress['items']):
            if state['status'] not in {'provider_call_started','publish_started','failed'}:continue
            preview=item['execution_binding']['trusted_preview']
            ref=preview['listing']['listing_ref'] if item['kind']=='market' else preview['pair']['pair_ref']
            add(item['kind'],ref,item['start_date'],item['end_date'],state['status'])
    return blocked,unknown_fx


def _overlays(space,ctx,request):
    """Selected durable stages may inform a review, never a completed valuation."""
    if request['execution_ref'] is None:return {},set(),[]
    from migrations.reference.desktop_market_fx_batch_binding_v1 import read_market_fx_bound_staging_v1
    from migrations.reference.desktop_market_fx_batch_publication_v1 import read_market_fx_batch_progress_v1, _current_binding
    batch=files.load_market_fx_batch_v1(space,ctx,request['execution_ref'])['trusted_batch']
    progress=read_market_fx_batch_progress_v1(space,ctx,batch)
    listings={t['listing_ref'] for t in request['targets'] if t['listing_ref'] is not None}
    currencies={t['mapping']['provider_currency'] for t in request['targets'] if t['mapping'] is not None}
    overlays={};accepted=set();dispositions=[]
    for item,state in zip(batch['items'],progress['items']):
        p=item['execution_binding']['trusted_preview'];kind=item['kind']
        ref=p['listing']['listing_ref'] if kind=='market' else p['pair']['pair_ref']
        selected=(ref in listings if kind=='market' else p['source_currency'] in currencies and p['target_currency']=='EUR')
        overlap=item['start_date']<=request['end_date'] and item['end_date']>=request['start_date']
        disposition='not_staged' if state['status']!='staged' else 'outside_selection'
        if state['status']=='staged' and selected and overlap:
            _current_binding(space,ctx,item)
            outcome=read_market_fx_bound_staging_v1(space,ctx,item)
            if outcome is None:invalid('stage_invalid')
            stage=outcome['stage'];stage_ref=native._stage_ref(p['preview_fingerprint']) if kind=='market' else 'fxh_'+p['preview_fingerprint'][:32]
            accepted.add((kind,stage_ref));overlays.setdefault((kind,ref),[]).append(stage);disposition='review_only'
        dispositions.append({'ordinal':state['ordinal'],'kind':kind,'status':state['status'],'disposition':disposition})
    return overlays,accepted,dispositions


def _overlay_days(history, stages, date_key):
    by_date={r[date_key]:dict(r) for r in history['days']};seen=set()
    for stage in stages:
        for row in stage['candidate']['days']:
            key=row[date_key]
            if key not in by_date:continue
            if key in seen:invalid('stage_invalid')
            seen.add(key)
            if by_date[key]['day_status']=='observed' and row['day_status']!='observed':continue
            by_date[key]={**by_date[key],**row}
    return list(by_date.values())


STATE_AREA='market-valuation-state-v1'


def _state_path(space):
    return space/STATE_AREA/'valuation-state.sqlite'


# Kalenderbefunde, an denen die Bewertung eines Assets nicht scheitert, sondern
# die sie als Grund am Asset ausweist.
CALENDAR_ERRORS=frozenset({'calendar_rule_period_unsupported','calendar_profile_required','calendar_context_unverified',
                           'calendar_registry_invalid','calendar_scope_mismatch','calendar_period_uncovered'})


def _open_state(space, ctx, now):
    """Oeffnet den Bewertungsstand; legt ihn an, wenn er fehlt.

    Stammt er aus einer anderen Rechnung oder einem aelteren Aufbau, wird er
    verworfen und neu aufgebaut -
    sichtbar an einem eigenen Lauf, nicht stillschweigend weitergerechnet. Der
    Stand ist abgeleitet; ein Neuaufbau verliert nichts, was nicht in den
    kanonischen Speichern steht.
    """
    path=_state_path(space)
    if not os.path.lexists(path.parent):
        os.mkdir(path.parent,0o700);os.chmod(path.parent,0o700)
    files._check_owner(path.parent,True)
    if not os.path.lexists(path):
        valuation_state.bootstrap_market_valuation_state_v1(path,ctx,now)
        return valuation_state.open_market_valuation_state_v1(path,ctx)
    try:
        return valuation_state.open_market_valuation_state_v1(path,ctx)
    except valuation_state.MarketValuationStateBlocked as error:
        if error.code not in {'market_valuation_state_algorithm_changed','market_valuation_state_schema_changed'}:raise
        # Der Stand ist abgeleitet und wird neu gerechnet - die Einstellungen darin
        # sind es nicht. Sie ueberleben den Neuaufbau, sonst faellt eine bewusst
        # gesetzte Entscheidung bei jeder Rechenaenderung stillschweigend auf die
        # Voreinstellung zurueck (#368, 28.09.2026).
        settings=_carried_settings(path)
        path.unlink()
        valuation_state.bootstrap_market_valuation_state_v1(path,ctx,now)
        connection=valuation_state.open_market_valuation_state_v1(path,ctx)
        if settings is not None:
            connection.execute(
                'INSERT INTO snapshot_setting (singleton_id,parallel_request_count,carry_across_blocked,updated_at_utc) VALUES (1,?,?,?)',
                settings)
            connection.commit()
        return connection


def _carry_across_blocked(space, ctx, now):
    """Der Schalter des Datenraums (#368). Seit #554 in den Nutzereinstellungen: Der Bewertungsstand ist ableitbar und darf jederzeit
    neu entstehen, die Entscheidung nicht. Ein alter Wert aus dem Stand wird hier einmal uebernommen."""
    from migrations.reference import user_settings_v1 as user_settings  # noqa: PLC0415
    try:
        owner=user_settings.owner_settings_context_v1(ctx)
        user_settings.adopt_market_settings_v1(space,owner,now)
        return user_settings.market_settings_v1(space,owner)['carry_across_blocked']
    except user_settings.UserSettingsV1Error:invalid('store_invalid')


def _carried_settings(path):
    """Die Einstellungen eines Standes, der gleich neu gebaut wird - oder nichts.

    Gelesen wird ohne Bindungspruefung: Der Stand ist an dieser Stelle bereits als
    unbrauchbar erkannt, seine Einstellungen sind es nicht.
    """
    try:
        connection=sqlite3.connect(f'file:{path}?mode=ro',uri=True)
    except sqlite3.Error:
        return None
    try:
        row=connection.execute('SELECT parallel_request_count,carry_across_blocked,updated_at_utc FROM snapshot_setting WHERE singleton_id = 1').fetchone()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    return None if row is None else tuple(row)


def _listing_requests(space, listing_ref):
    """Fingerprint ueber die Anfragen einer Notierung.

    Daran erkennt der Stand, ob etwas Zurueckliegendes beruehrt wurde: Kommt eine
    Anfrage hinzu oder traegt eine Korrekturen, aendert sich dieser Wert, und nur
    dann wird der Bereich neu gerechnet statt fortgeschrieben.
    """
    import sqlite3
    path=space/'daily-market-history-v1/daily-market-history.sqlite'
    if not os.path.lexists(path):return files._sha({'contract':'market_valuation_scope_inputs_v1','requests':[]})
    connection=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
    try:
        rows=list(connection.execute(
            "SELECT q.request_ref, q.receipt_fingerprint, q.corrected_day_count FROM daily_market_history_request q "
            "JOIN market_listing_binding b ON b.listing_id = q.listing_id WHERE b.listing_ref = ? ORDER BY q.request_ref",
            (listing_ref,)))
    except sqlite3.Error:invalid('source_busy')
    finally:connection.close()
    return files._sha({'contract':'market_valuation_scope_inputs_v1','requests':rows})


def _load(root,bound,ref):
    if not isinstance(ref,str) or not re.fullmatch(r'mvp_[a-f0-9]{32}',ref):invalid()
    files._check_owner(root,True)
    if files._read(root/'.context')!={'binding':bound}:invalid('context_invalid')
    value=files._read(root/(ref+'.json'))
    if value.get('binding')!=bound or value.get('preview_ref')!=ref or value.get('fingerprint')!=files._sha({k:v for k,v in value.items() if k!='fingerprint'}):invalid('store_invalid')
    return value


def _blob(root, entry):
    name=entry['file']
    if not re.fullmatch(r'mvp_[a-f0-9]{32}-(?:asset|fx)-[0-9]+\.json',name):invalid('store_invalid')
    value=files._read(root/name)
    if files._sha(value)!=entry['fingerprint']:invalid('store_invalid')
    return value


def _public(value, draft_write=False):
    return {'preview_ref':value['preview_ref'],'status':value['status'],'start_date':value['request']['start_date'],
            'end_date':value['request']['end_date'],'rows':value['summaries'],'fx_pair_count':len(value['fx_evidence']),
            'requirements':value.get('requirements',[]),
            'simple_absence_policy':value['request'].get('simple_absence_policy',False),
            'trade_price_references':value['request'].get('use_trade_prices',False),'manual_price_entries':value['request'].get('use_manual_prices',False),
            'valuation_policy':valuation_policy(value['request'].get('valuation_policy')),
            'valuation_status':value.get('valuation_status','complete' if value['status']=='ready' else 'incomplete'),
            'silent_drop_count':0,'provider_access':False,'canonical_write':False,'valuation_draft_write':draft_write,
            'source_policy':'staged_review_only' if value['staged_source_count'] else 'published_only',
            'staged_source_count':value['staged_source_count'],'stage_dispositions':value['stage_dispositions'],'portfolio_completion':False}


def prepare(space,ctx,request,clock=lambda:datetime.now(timezone.utc)):
    required={'targets','start_date','end_date','target_currency','use_rules','max_age_days','market_exceptions','fx_exceptions','execution_ref'}
    if not isinstance(request,dict) or not required<=set(request)<=required|{'use_saved_calendars','valuation_policy','simple_absence_policy','use_trade_prices','use_manual_prices'}:invalid()
    if 'valuation_policy' in request and request['valuation_policy'] is None:invalid('policy_invalid')
    try:policy=valuation_policy(request.get('valuation_policy'))
    except ValueError:invalid('policy_invalid')
    # Ob eine Sperre die Folgetage ansteckt, gilt fuer alle Assets zugleich und
    # nicht je Aufruf: Es geht um den Umgang mit Quellluecken, nicht um ein
    # einzelnes Papier (#368, 28.09.2026).
    policy={**policy,'carry_across_blocked':_carry_across_blocked(space,ctx,clock().astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))}
    request={**request,'valuation_policy':policy}
    simple=request.get('simple_absence_policy',False)
    trade_prices=request.get('use_trade_prices',False)
    manual_price_entries=request.get('use_manual_prices',False)
    if type(simple) is not bool or type(trade_prices) is not bool or type(manual_price_entries) is not bool:invalid()
    if trade_prices and manual_price_entries:invalid('calendar_options_conflict')
    if simple and (request.get('use_saved_calendars',False) or request['use_rules'] or request['market_exceptions'] or request['fx_exceptions']):invalid('calendar_options_conflict')
    use_saved=request.get('use_saved_calendars',False)
    if type(use_saved) is not bool:invalid()
    if use_saved and (request['use_rules'] or request['market_exceptions'] or request['fx_exceptions']):invalid('calendar_options_conflict')
    start=date.fromisoformat(request['start_date']);end=date.fromisoformat(request['end_date'])
    if start.isoformat()!=request['start_date'] or end.isoformat()!=request['end_date']:invalid()
    targets=request['targets'];age=request['max_age_days']
    if not isinstance(targets,list) or not 1<=len(targets)<=10000 or not 0<=(end-start).days<=20000 or len(targets)*((end-start).days+1)>1000000:invalid('capacity_invalid')
    if request['target_currency']!='EUR' or type(request['use_rules']) is not bool or type(age) is not int or not 0<=age<=366:invalid()
    for name in ('market_exceptions','fx_exceptions'):
        if not isinstance(request[name],dict):invalid()
    seen=set()
    for item in targets:
        if set(item)!={'asset_id','asset_ref','asset_name','listing_ref','mapping','promotion_binding','disposition'}:invalid()
        if not isinstance(item['asset_id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{3,128}',item['asset_id']) or item['asset_id'] in seen:invalid()
        if not isinstance(item['asset_name'],str) or not item['asset_name'] or len(item['asset_name'])>240:invalid()
        if not isinstance(item['asset_ref'],str) or not re.fullmatch(r'asset_ref_[0-9]{4,}',item['asset_ref']):invalid()
        if not isinstance(item['disposition'],str):invalid()
        seen.add(item['asset_id'])
    root,bound=_root(space,ctx);before=_sources(space,use_saved)
    catalog=None;calendar_error=None
    if use_saved:
        try:catalog=read_market_calendar_catalog_v1(space,{**ctx,'actor_id':'portfolio_reader','role':'portfolio_worker'},require_context=False)
        except MarketCalendarRegistryV1Error:calendar_error='calendar_registry_invalid'
    def choose(source,scope_kind,scope_ref,exceptions,is_fx=False,start_date=None,reach=None):
        # start_date und reach nur fuer den Vektor eines Waehrungspaares, der ab
        # dem Beginn des Paares gefaltet wird statt ab dem des Assets.
        if use_saved:
            if calendar_error:raise ValueError(calendar_error)
            return saved_calendar(catalog,scope_kind,scope_ref,source,start_date or request['start_date'],request['end_date'])
        return propose_calendar(source,reach or lookback,request['end_date'],exceptions,fx=is_fx,use_rules=request['use_rules'] and not is_fx)
    def normalized(rows,date_key,value_key,profile,for_valuation=False):
        # A saved profile may begin at the requested boundary. Never borrow a
        # predecessor from before its validity window.
        return [{'date':r[date_key],'status':('source_gap' if for_valuation and simple and policy['mode']=='last_valid' and r['day_status']=='non_trading_day' else r['day_status']),'value':r[value_key]} for r in rows
                if profile['valid_from']<=r[date_key]<=profile['valid_to']]
    requirements=[]
    def requirement(kind,consumer,rows,cal,blocks,stages,date_key,value_key):
        barriers=dict(blocks)
        for stage in stages:
            for row in stage['candidate']['days']:barriers.setdefault(row[date_key],'staged_not_published')
        plan=calendar_requirements(normalized(rows,date_key,value_key,cal['profile']),cal['profile'],request['start_date'],request['end_date'],barriers)
        requirements.append({'kind':kind,'consumer':consumer,'calendar':cal['preset'],'disposition':'calendar_review',
            'unassessed_day_count':0,'range_count':plan['range_count'],
            'fetch_session_day_count':plan['counts'].get('fetch_needed',0),'closed_no_fetch_day_count':plan['counts'].get('closed_no_fetch',0),
            'source_gap_review_day_count':sum(plan['counts'].get(k,0) for k in ('source_gap_review','closed_source_gap_review')),
            'blocked_day_count':plan['counts'].get('blocked',0),'execution_authority':False})
        return plan
    mctx=market.MarketHistoryContext(**ctx,actor_id='portfolio_reader',role='portfolio_worker')
    fctx=fx.FxHistoryContext(**ctx,actor_id='portfolio_reader',role='portfolio_worker')
    overlays,accepted_stages,stage_dispositions=_overlays(space,ctx,request)
    blocked,unknown_fx=_pending(space,ctx,mctx,fctx,accepted_stages,
                                {item['listing_ref'] for item in targets if isinstance(item.get('listing_ref'),str)})
    lookback_age=max(age,policy['max_age_days'] or 0)
    lookback=max(date(2000,1,1),start-timedelta(days=lookback_age)).isoformat() if request['use_rules'] else (start-timedelta(days=lookback_age)).isoformat()
    fx_store=space/'fx-history-v1/fx-history.sqlite'
    pairs=None  # Lazy: EUR trade/provider prices must not need an FX reader.
    used_market=set();used_fx=set();fx_cache={};fx_evidence=[];blobs=[];summaries=[];scope_writes=[]
    ref='mvp_'+uuid.uuid4().hex
    now=clock().astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    # Der Bewertungsstand haelt die Tagesreihen; der Beleg je Asset nennt nur noch,
    # worauf er beruht. Geschrieben wird er erst, wenn die Vorbereitung ganz
    # durchgelaufen ist - ein abgebrochener Entwurf hinterlaesst keinen halben
    # Stand (#283, Schritt 3, 26.09.2026).
    with locked(root,bound), closing(_open_state(space,ctx,now)) as store:
        def save(kind,number,value):
            name=f'{ref}-{kind}-{number}.json';files._write(root/name,value)
            return {'file':name,'fingerprint':files._sha(value)}
        def fx_for(currency):
            # Der Paarkontext getrennt vom Umrechnen: Die Bewertung ueber den Stand
            # braucht Paarkennung und Richtung, nicht die gefaltete Reihe.
            nonlocal pairs
            if currency=='EUR':return (None,'direct',None,None,None)
            key=currency+'/EUR';used_fx.add(key)
            if pairs is None:pairs=fx.read_fx_pair_catalog_v1(fx_store,fctx)['pairs'] if fx_store.exists() else []
            if key not in fx_cache:
                matches=[p for p in pairs if {p['base_currency'],p['quote_currency']}=={currency,'EUR'}]
                if len(matches)>1:invalid('fx_pair_ambiguous')
                if not matches:fx_cache[key]=(None,'direct',None,None,None)
                else:
                    pair=matches[0];fh=fx.read_fx_history_v1(fx_store,fctx,pair['pair_ref'],lookback,request['end_date'])
                    fc=choose(fh,'fx_pair',pair['pair_ref'],request['fx_exceptions'].get(key,[]),True)
                    fb=blocked.get(('fx',pair['pair_ref']),{})
                    if unknown_fx:fb={r['rate_date']:'unknown_fx_attempt' for r in fh['days']}
                    fx_stages=overlays.get(('fx',pair['pair_ref']),[])
                    rate_days=_overlay_days(fh,fx_stages,'rate_date')
                    normalized_rates=normalized(rate_days,'rate_date','rate_decimal',fc['profile'],True)
                    fr=effective_series(normalized_rates,fc['profile'],request['start_date'],request['end_date'],age,fb,gap_policy=policy)
                    native_rates={r['rate_date']:r['day_status'] for r in rate_days}
                    for day,rate in fr.items():rate['native_status']=native_rates.get(day)
                    # Der wirksame Wechselkurs je Tag gehoert in den Stand: Er ist
                    # der Multiplikator fuer jedes Asset dieser Waehrung und wird
                    # dort einmal gehalten statt je Asset erneut abgelegt. Die
                    # Sperren und gestagten Staende des Paares gehen in seinen
                    # Eingangsfingerprint ein - aendern sie sich, wird das Paar neu
                    # aufgebaut statt fortgeschrieben (#283, 26.09.2026).
                    # Der Vektor gehoert dem Paar, nicht dem Asset. Bis rc.240 wurde er
                    # ab dem Beginn des gerade bewerteten Assets gefaltet; weil der
                    # Eingangsabdruck die Tage ab dessen Rueckblick enthaelt, galt er
                    # bei jedem Asset mit anderem Beginn als geaendert und wurde nur
                    # fuer dessen Zeitraum neu geschrieben. So
                    # blieb der Zeitraum des zuletzt bearbeiteten Assets uebrig
                    # (zu spaet beginnend). Gefaltet wird deshalb ab dem
                    # fruehesten Beginn, den das Paar je hatte: Der Abdruck ist dann
                    # fuer alle Assets eines Laufs derselbe, das erste baut den
                    # Vektor, die uebrigen finden ihn unveraendert vor (12.10.2026).
                    vector=(request['start_date'],normalized_rates,fc['profile'],fb,native_rates)
                    pair_from=valuation_state.read_fx_effective_from_v1(store,pair['pair_ref'])
                    if pair_from is not None and pair_from<request['start_date']:
                        try:
                            reach=date.fromisoformat(pair_from)-timedelta(days=lookback_age)
                            reach=(max(date(2000,1,1),reach) if request['use_rules'] else reach).isoformat()
                            ph=fx.read_fx_history_v1(fx_store,fctx,pair['pair_ref'],reach,request['end_date'])
                            pc=choose(ph,'fx_pair',pair['pair_ref'],request['fx_exceptions'].get(key,[]),True,pair_from,reach)
                            pb={r['rate_date']:'unknown_fx_attempt' for r in ph['days']} if unknown_fx else fb
                            pair_days=_overlay_days(ph,fx_stages,'rate_date')
                            vector=(pair_from,normalized(pair_days,'rate_date','rate_decimal',pc['profile'],True),pc['profile'],pb,
                                    {r['rate_date']:r['day_status'] for r in pair_days})
                        except ValueError as error:
                            # Deckt der Kalender des Paares dessen ganzen Zeitraum
                            # nicht, bleibt es beim Zeitraum des Assets: Die
                            # Bewertung dieses Assets darf daran nicht scheitern. Der
                            # Wasserstand nennt dann den verkuerzten Beginn.
                            if str(error) not in CALENDAR_ERRORS:raise
                    vector_start,vector_days,vector_profile,vector_blocked,vector_native=vector
                    valuation_state.apply_fx_effective_days_v1(
                        store,pair_ref=pair['pair_ref'],days=vector_days,profile=vector_profile,
                        max_age=age,policy=policy,start=vector_start,end=request['end_date'],
                        # Gemeinsame Eingaenge des Paares; Tage, Sperren und Notierungsstand je Tag bringt der Stand selbst ein und
                        # vergleicht sie nur bis zum Fortsetzungstag - ein neuer Tag wird angehaengt (rc.364).
                        consumed_request_fingerprint=files._sha({
                            'contract':'market_valuation_pair_inputs_v2','pair':pair['pair_ref'],'unknown_fx':unknown_fx,
                            'stages':[stage.get('stage_ref') for stage in fx_stages]}),
                        updated_at_utc=now,mode='incremental',blocked=vector_blocked,native_status=vector_native)
                    fp=requirement('fx',key,fh['days'],fc,fb,fx_stages,'rate_date','rate_decimal')
                    fx_cache[key]=(fr,'direct' if pair['base_currency']==currency else 'inverse',fc,fp,pair['pair_ref'])
                    # Die Quellreihe steht unveraendert im Wechselkursspeicher und
                    # wird ueber die Anfragen des Paares belegt; sie hier noch einmal
                    # abzulegen kostete viel Platz je Asset und Lauf.
                    fx_evidence.append(save('fx',len(fx_evidence)+1,{
                        'source':{**{k:v for k,v in fh.items() if k!='days'},'day_count':len(fh['days']),
                                  'first_rate_date':fh['days'][0]['rate_date'] if fh['days'] else None,
                                  'last_rate_date':fh['days'][-1]['rate_date'] if fh['days'] else None},
                        'pair_ref':pair['pair_ref'],'calendar':fc,'stages':fx_stages,'requirements':fp}))
            return fx_cache[key]

        def in_eur(prices,currency):
            rates,direction,fc,fp,_pair_ref=fx_for(currency)
            days=convert_series(prices,currency,'EUR',rates,direction)
            for d in days:d['fx_native_status']=None if rates is None else rates.get(d['date'],{}).get('native_status')
            return days,fc,fp
        for ordinal,item in enumerate(targets,1):
            source=None;calendar=None;fx_calendar=None;warning=None;reason=item['disposition'];direction='direct';rates=None;scope_ref=None
            market_plan=None;fx_plan=None
            days=[];cursor=start
            while cursor<=end:days.append({'date':cursor.isoformat(),'status':'mapping_required'});cursor+=timedelta(days=1)
            if item['mapping'] is not None and item['listing_ref'] is not None:
                current,audits=native._validate_current_mapping(space,item['mapping'])
                listing=market.read_daily_market_listing_binding_v1(space/'daily-market-history-v1/daily-market-history.sqlite',mctx,item['listing_ref'])
                promotion=native._promotion_binding(item['promotion_binding'],listing,current,native._context(ctx))
                native._validate_promotion_audit(promotion,current,audits)
                if current['asset_id']!=item['asset_id'] or not native._listing_catalog_current(space,native._context(ctx),listing,current):invalid('mapping_invalid')
                # Ein Lauf verkuerzt einen schon bewerteten Zeitraum nicht. Verlangt er
                # einen spaeteren Beginn, als der Bereich schon traegt, wird ab dem
                # vorhandenen Beginn gerechnet. Bis rc.243 schrieb ein Lauf "ab erster
                # Transaktion" den Bereich nur ab der ersten Buchung neu und verwarf
                # die Tage davor: So haette der naechste
                # gewoehnliche Lauf die am Vortag weit zurueck gerechneten
                # Tageswerte Asset fuer Asset wieder geloescht (12.10.2026).
                scope_from=valuation_state.read_valuation_scope_from_v1(store,item['asset_id'],item['listing_ref'])
                scope_start,scope_reach=request['start_date'],lookback
                if scope_from is not None and scope_from<request['start_date']:
                    reach=date.fromisoformat(scope_from)-timedelta(days=lookback_age)
                    scope_start,scope_reach=scope_from,(max(date(2000,1,1),reach) if request['use_rules'] else reach).isoformat()
                source=market.read_daily_market_history_v1(space/'daily-market-history-v1/daily-market-history.sqlite',mctx,item['listing_ref'],scope_reach,request['end_date'])
                _,_,_,context_fp=context_values(ctx)
                if source['asset_ref']!=public_ref('asf_',context_fp,item['asset_id']) or source['quote_currency']!=current['provider_currency']:invalid('mapping_invalid')
                used_market.add(source['market_code'])
                try:
                    try:
                        calendar=choose(source,'listing',item['listing_ref'],request['market_exceptions'].get(source['market_code'],[]),False,scope_start,scope_reach)
                    except ValueError as error:
                        # Deckt der Kalender den frueheren Beginn nicht, bleibt es bei
                        # dem verlangten Zeitraum: Die Bewertung des Assets darf an
                        # Tagen, die dieser Lauf nicht verlangt, nicht scheitern.
                        if scope_start==request['start_date'] or str(error) not in CALENDAR_ERRORS:raise
                        scope_start,scope_reach=request['start_date'],lookback
                        source=market.read_daily_market_history_v1(space/'daily-market-history-v1/daily-market-history.sqlite',mctx,item['listing_ref'],lookback,request['end_date'])
                        calendar=choose(source,'listing',item['listing_ref'],request['market_exceptions'].get(source['market_code'],[]))
                    warning=calendar['warning'];mb=dict(blocked.get(('market',item['listing_ref']),{}))
                    price_days=_overlay_days(source,overlays.get(('market',item['listing_ref']),[]),'trading_date')
                    # Eine Kapitalmassnahme im Abruf macht jeden seiner Tage pruefpflichtig,
                    # weil unbereinigte Kurse ueber einen Split hinweg nicht vergleichbar
                    # sind: Vor einem 10:1-Split steht der zehnfache Betrag. Der bereinigte
                    # Kurs der Quelle ist splitkonsistent und wird deshalb verwendet, wo er
                    # vorliegt; nur ohne ihn bleibt der Tag gesperrt. Jeder so bewertete Tag
                    # ist als splitbereinigt gekennzeichnet (Entscheidung 22.09.2026).
                    split_adjusted=set()
                    for row in price_days:
                        if row['valuation_status']!='blocked_corporate_action':continue
                        if row.get('adjusted_close_decimal') is None:
                            mb[row['trading_date']]='blocked_corporate_action'
                        else:
                            split_adjusted.add(row['trading_date'])
                    value_key='close_decimal'
                    if split_adjusted:
                        price_days=[{**row,'close_decimal':row['adjusted_close_decimal']} if row['trading_date'] in split_adjusted else row
                                    for row in price_days]
                    normalized_prices=normalized(price_days,'trading_date',value_key,calendar['profile'],True)
                    market_plan=requirement('market',item['asset_name'],source['days'],calendar,mb,overlays.get(('market',item['listing_ref']),[]),'trading_date','close_decimal')
                    rates,fx_direction,fx_calendar,fx_plan,pair_ref=fx_for(source['quote_currency'])
                    native_prices={r['trading_date']:r['day_status'] for r in price_days}
                    reason='valued'
                    if source['quote_currency']!='EUR' and pair_ref is None:
                        # Ohne gebundenes Paar gibt es keinen Bereich im Stand: Die
                        # Umrechnung fehlt, und das gehoert sichtbar in die Zeilen,
                        # nicht als leerer Bereich in den Stand.
                        days=convert_series(effective_series(normalized_prices,calendar['profile'],request['start_date'],request['end_date'],age,mb,gap_policy=policy),
                                            source['quote_currency'],'EUR',None,'direct')
                        for d in days:
                            d['fx_native_status']=None
                            d['price_native_status']=native_prices.get(d['date'])
                            if d['date'] in split_adjusted and d.get('effective_price') is not None:
                                d['price_source_kind']='split_adjusted_close'
                    else:
                        # Der Bewertungsstand rechnet den Tagesschritt und haelt das
                        # Ergebnis. Die Zeilen kommen von dort zurueck, statt sie hier
                        # ein zweites Mal herzuleiten und als Blob abzulegen
                        # (#283, Schritt 3, 26.09.2026).
                        scope=valuation_state.apply_valuation_scope_days_v1(
                            store,asset_id=item['asset_id'],listing_ref=item['listing_ref'],
                            quote_currency=source['quote_currency'],
                            provider_symbol=current['provider_symbol'],pair_ref=pair_ref,
                            direction='identity' if pair_ref is None else fx_direction,
                            price_days=normalized_prices,profile=calendar['profile'],max_age=age,
                            policy=policy,blocked=mb,start=scope_start,end=request['end_date'],
                            consumed_request_fingerprint=_listing_requests(space,item['listing_ref']),
                            # Gemeinsame Eingaenge der Notierung (offene Pruefstufen); Kurse, Sperren, Herkunft und Split-Bereinigung
                            # je Tag vergleicht der Stand nur bis zum Fortsetzungstag - ein neuer Tag wird angehaengt (rc.364).
                            barrier_fingerprint=files._sha({
                                'contract':'market_valuation_scope_barriers_v2',
                                'stages':[stage.get('stage_ref') for stage in overlays.get(('market',item['listing_ref']),[])]}),
                            updated_at_utc=now,mode='incremental',price_native_status=native_prices,
                            price_source_kind={day:'split_adjusted_close' for day in split_adjusted})
                        scope_ref=scope['scope_ref'];scope_writes.append(scope)
                        days=valuation_state.read_valuation_rows_v1(store,scope_ref,request['start_date'],request['end_date'])
                except ValueError as error:
                    if str(error) not in CALENDAR_ERRORS:raise
                    reason=str(error)
                    days=[{'date':d['date'],'status':reason} for d in days]
            elif item['disposition']=='unit_value':
                asset,snapshot=trades.read_asset_configuration(space,ctx,item['asset_id'],'unit_value')
                source={'source_kind':'configured_unit_value','quote_currency':asset['price_currency'],'canonical_fingerprint':snapshot['source_fingerprint']}
                calendar=propose_calendar({'market_code':'UNIT','timezone_name':'UTC','calendar_code':'continuous_24_7'},lookback,request['end_date'],[],use_rules=False)
                calendar['preset']='configured_unit_value'
                prices=effective_series([{'date':d['date'],'status':'observed','value':'1'} for d in days],calendar['profile'],request['start_date'],request['end_date'],0)
                days,fx_calendar,fx_plan=in_eur(prices,source['quote_currency']);reason='unit_value'
                for d in days:d['price_source_kind']='configured_unit_value'
            elif item['disposition']=='manual':
                reason='trade_price_confirmation_required'
                days=[{'date':d['date'],'status':reason} for d in days]
                if manual_price_entries:
                    # Eigene Kursangaben des Eigentuemers: beliebig grosse Luecken sind
                    # erlaubt, der zuletzt eingetragene Wert wird fortgeschrieben und
                    # bleibt als Ersatzwert gekennzeichnet (#283 Punkt 2).
                    source=manual_prices.read_manual_source(space,ctx,item['asset_id'],lookback,request['end_date'])
                    calendar=propose_calendar({'market_code':'MANUAL','timezone_name':'UTC','calendar_code':'continuous_24_7'},lookback,request['end_date'],[],use_rules=False)
                    calendar['preset']='owner_recorded_manual_price';warning='manual_prices_are_not_market_quotes'
                    prices=effective_series(source['rows'],calendar['profile'],request['start_date'],request['end_date'],age,source['barriers'],gap_policy=policy)
                    days,fx_calendar,fx_plan=in_eur(prices,source['quote_currency']);reason='owner_recorded_manual_price'
                    for d in days:
                        d['price_source_kind']='owner_recorded_manual_price'
                        if prices[d['date']]['value'] is not None:d['price_basis']='owner_recorded_manual_price'
                        d['price_native_status']='manual' if prices[d['date']]['original_value'] is not None else 'carried'
                        if d['status'] in ('native','converted'):
                            d['substitution_used']=True;d['valuation_status']='substituted'
                elif trade_prices:
                    source=trades.read_trade_source(space,ctx,item['asset_id'],lookback,request['end_date'])
                    calendar=propose_calendar({'market_code':'TRADE','timezone_name':'UTC','calendar_code':'continuous_24_7'},lookback,request['end_date'],[],use_rules=False)
                    calendar['preset']='trade_price_reference';warning='trade_prices_are_not_market_quotes'
                    prices=effective_series(source['rows'],calendar['profile'],request['start_date'],request['end_date'],age,source['barriers'],gap_policy=policy)
                    days,fx_calendar,fx_plan=in_eur(prices,source['quote_currency']);reason='trade_price_reference'
                    for d in days:
                        d['price_source_kind']='confirmed_trade_price_reference'
                        if prices[d['date']]['value'] is not None:d['price_basis']='trade_price_reference'
                        d['price_native_status']='trade' if prices[d['date']]['original_value'] is not None else 'no_trade'
                        if d['status'] in ('native','converted'):
                            d['substitution_used']=True;d['valuation_status']='substituted'
            if market_plan is None:
                requirements.append({'kind':'market','consumer':item['asset_name'],'disposition':reason,
                                     'unassessed_day_count':len(days),'execution_authority':False})
            converted=sum(d['status'] in {'converted','native'} for d in days)
            summaries.append({'ordinal':ordinal,'asset_ref':item['asset_ref'],'asset_name':item['asset_name'],
                'disposition':reason,'day_count':len(days),'valued_day_count':converted,'unavailable_day_count':len(days)-converted,
                'market_imputed_day_count':sum(d.get('price_basis')=='imputed_closed_day' for d in days),
                'fx_imputed_day_count':sum(d.get('fx_basis')=='imputed_closed_day' for d in days),
                'market_substituted_day_count':sum(d.get('price_basis') in SUBSTITUTE_BASES for d in days),
                'fx_substituted_day_count':sum(d.get('fx_basis') in SUBSTITUTE_BASES for d in days),
                'substituted_day_count':sum(d.get('substitution_used',False) for d in days),
                'split_adjusted_day_count':sum(d.get('price_source_kind')=='split_adjusted_close' for d in days),
                'valuation_status':'incomplete' if converted<len(days) else 'substituted' if any(d.get('substitution_used',False) for d in days) else 'complete',
                'calendar':None if calendar is None else calendar['preset'],'calendar_warning':warning})
            # Der Beleg nennt, worauf die Bewertung beruht - die Tagesreihe selbst
            # steht im Stand. Vorher lag sie hier als grosser Blob je Asset und Lauf
            # und wurde beim Abschluss erneut gelesen und nachgehasht. Die Quellreihe
            # steht unveraendert im Kursspeicher; sie hier zu spiegeln belegte
            # nichts, was dort nicht sicherer stuende (#283, Schritt 3, 26.09.2026).
            blobs.append(save('asset',ordinal,{'source':None if source is None else {
                    **{k:v for k,v in source.items() if k!='days'},'day_count':len(source.get('days',()))},
                'calendar':calendar,'fx_calendar':fx_calendar,'stages':overlays.get(('market',item['listing_ref']),[]),
                'scope_ref':scope_ref,'rows':None if scope_ref else days,
                'market_requirements':market_plan,'fx_requirements':fx_plan}))
        assessed_fx={r['consumer'] for r in requirements if r['kind']=='fx'}
        expected_fx={t['mapping']['provider_currency']+'/EUR' for t in targets if t['mapping'] is not None and t['mapping']['provider_currency']!='EUR'}
        for key in sorted(expected_fx-assessed_fx):
            requirements.append({'kind':'fx','consumer':key,'disposition':'fx_requirements_unavailable',
                                 'unassessed_day_count':(end-start).days+1,'execution_authority':False})
        if set(request['market_exceptions'])-used_market or set(request['fx_exceptions'])-used_fx:invalid('unused_exceptions')
        if _sources(space,use_saved)!=before:invalid('stale')
        value={'version':1,'preview_ref':ref,'binding':bound,'request':request,'sources':before,'blobs':blobs,
               'fx_evidence':fx_evidence,'summaries':summaries,'requirements':requirements,'staged_source_count':len(accepted_stages),'stage_dispositions':stage_dispositions,'status':'ready' if all(s['unavailable_day_count']==0 for s in summaries) else 'incomplete'}
        value['valuation_status']='incomplete' if value['status']=='incomplete' else 'substituted' if any(s['substituted_day_count'] for s in summaries) else 'complete'
        value['fingerprint']=files._sha(value);files._write(root/(ref+'.json'),value)
        if scope_writes:
            # Was dieser Lauf am Stand getan hat: wie viele Tage neu hinzukamen und
            # wie viele schon vorhandene er neu gerechnet hat. Die Tabelle gibt es
            # seit dem Bau des Stands, beschrieben wurde sie nie - ob das Anhaengen
            # im Alltag greift, liess sich deshalb nur aus dem Code schaetzen.
            rewritten=sum(row['recomputed_day_count'] for row in scope_writes)
            valuation_state.record_valuation_state_job_v1(
                store,request_mode='incremental' if all(row['mode']=='incremental' for row in scope_writes) else 'full_rebuild',
                prior_job_ref=valuation_state.read_latest_valuation_state_job_ref_v1(store),scope_count=len(scope_writes),
                appended_day_count=max(0,sum(row['written_day_count'] for row in scope_writes)-rewritten),
                recomputed_day_count=rewritten,requested_at_utc=now)
        store.commit()
    return _public(value,True)


def _retention_plan(root,bound):
    """Welche abgeschlossenen Laeufe traegt die heutige Aussage - und welche nicht.

    Bewertet wird assetweise, und die Betriebsbereitschaft nimmt je Asset den
    juengsten Beleg (portfolio_operational_readiness_v1). Aeltere Belege desselben
    Assets sind damit Historie: Sie stuetzen keine gegenwaertige Aussage, werden
    aber bei jedem 'list' mitsamt Vorschau und Blobs gelesen.

    Fail-closed: Ist ein Beleg, eine Vorschau oder ein Blobverweis unlesbar, gibt
    es keinen Plan. Auf einem halben Bild wird nichts geloescht (#283, 26.09.2026).
    """
    files._check_owner(root,True)
    if files._read(root/'.context')!={'binding':bound}:invalid('context_invalid')
    newest={};group={};completed={};keep=set()
    for path in sorted(root.glob('completed-*.json')):
        receipt=files._read(path);ref=receipt.get('preview_ref');done=receipt.get('completed_at_utc')
        if not isinstance(done,str) or not files._utc(done):invalid('store_invalid')
        value=_load(root,bound,ref)
        if receipt.get('fingerprint')!=value['fingerprint']:invalid('store_invalid')
        completed[ref]=done
        names=[path.name,ref+'.json']
        for entry in value['blobs']+value['fx_evidence']:
            name=entry['file']
            if not re.fullmatch(r'mvp_[a-f0-9]{32}-(?:asset|fx)-[0-9]+\.json',name):invalid('store_invalid')
            if not (root/name).is_file():invalid('store_invalid')
            names.append(name)
        group[ref]=names
        for row in value['summaries']:
            asset=row.get('asset_name')
            if not isinstance(asset,str):continue
            if asset not in newest or done>newest[asset][0]:newest[asset]=(done,ref)
    keep={ref for _,ref in newest.values()}
    if completed:keep.add(max(completed,key=lambda r:(completed[r],r)))
    superseded=sorted(set(completed)-keep)
    held={name for ref in keep for name in group[ref]}
    # Eine Vorschau ohne Beleg ist eine abgebrochene Vorbereitung, kein Ergebnis.
    unfinished={}
    for path in sorted(root.glob('mvp_*.json')):
        if not re.fullmatch(r'mvp_[a-f0-9]{32}\.json',path.name) or path.stem in completed:continue
        value=_load(root,bound,path.stem);names=[path.name]
        for entry in value['blobs']+value['fx_evidence']:
            if (root/entry['file']).is_file():names.append(entry['file'])
        unfinished[path.stem]=names
    claimed=held|{n for ref in superseded for n in group[ref]}|{n for names in unfinished.values() for n in names}
    # Die Quittungen frueherer Aufbewahrungen dokumentieren, was entfernt wurde.
    # Sie gehoeren keinem Lauf und waeren sonst beim naechsten Mal selbst faellig.
    stray=sorted(path.name for path in root.iterdir()
                 if path.is_file() and not path.name.startswith('.')
                 and not path.name.startswith('retention-') and path.name not in claimed)
    remove=sorted({n for ref in superseded for n in group[ref]}|{n for names in unfinished.values() for n in names}|set(stray))
    if held&set(remove):invalid('store_invalid')
    def weigh(names):return sum((root/n).stat().st_size for n in names if (root/n).is_file())
    plan={'contract_version':'desktop_market_valuation_retention_v1','binding':bound,
          'asset_count':len(newest),'kept_run_count':len(keep),
          'superseded_run_count':len(superseded),'unfinished_preview_count':len(unfinished),
          'unreferenced_file_count':len(stray),'removed_file_count':len(remove),
          'kept_byte_count':weigh(sorted(held)),'removed_byte_count':weigh(remove),
          'kept_runs':sorted(keep),'removed_files':remove}
    plan['plan_fingerprint']=files._sha(plan)
    return plan


def _retention_apply(root,bound,expected,now):
    """Den geplanten Bestand entfernen - und nur genau diesen.

    Der Plan wird unter der Sperre neu erhoben. Weicht er vom bestaetigten ab,
    ist zwischenzeitlich ein Lauf hinzugekommen oder entfallen; dann bricht der
    Vorgang ab, statt eine andere Menge zu loeschen.
    """
    with locked(root,bound):
        plan=_retention_plan(root,bound)
        if plan['plan_fingerprint']!=expected:invalid('stale')
        for name in plan['removed_files']:
            path=root/name
            if not path.is_file():invalid('store_invalid')
            files._check_owner(path,False)
            os.unlink(path)
        files._sync_directory(root)
        receipt={'contract_version':'desktop_market_valuation_retention_v1','binding':bound,
                 'applied_at_utc':now.strftime('%Y-%m-%dT%H:%M:%SZ'),
                 'kept_runs':plan['kept_runs'],'removed_file_count':plan['removed_file_count'],
                 'removed_byte_count':plan['removed_byte_count'],
                 'superseded_run_count':plan['superseded_run_count'],
                 'unfinished_preview_count':plan['unfinished_preview_count'],
                 'unreferenced_file_count':plan['unreferenced_file_count'],
                 'plan_fingerprint':expected}
        receipt['receipt_fingerprint']=files._sha(receipt)
        files._write(root/('retention-'+receipt['applied_at_utc'].replace(':','')+'.json'),receipt)
    return {k:v for k,v in receipt.items() if k!='kept_runs'}


def operate(data_space_path,context,command,payload,*,clock=lambda:datetime.now(timezone.utc)):
    ctx=files._context(context);space=files._space(data_space_path,ctx);root,bound=_root(space,ctx)
    if command=='prepare':return prepare(space,ctx,payload,clock)
    if command=='portfolio-input':
        if set(payload)!={'preview_ref','as_of_date'}:invalid()
        from workers.reference.desktop_completed_market_snapshot_v1 import read_for_run
        return read_for_run(space,ctx,payload['preview_ref'],payload['as_of_date'])
    if command=='retain-plan':
        if payload!={'read_only':True}:invalid()
        if not os.path.lexists(root):return {'contract_version':'desktop_market_valuation_retention_v1','removed_file_count':0,'removed_byte_count':0}
        return {k:v for k,v in _retention_plan(root,bound).items() if k not in ('removed_files','kept_runs')}
    if command=='retain-apply':
        if set(payload)!={'plan_fingerprint','confirmed'}:invalid()
        if payload['confirmed'] is not True:invalid('confirmation_required')
        if not isinstance(payload['plan_fingerprint'],str):invalid()
        if not os.path.lexists(root):invalid('store_invalid')
        return _retention_apply(root,bound,payload['plan_fingerprint'],clock().astimezone(timezone.utc))
    if command=='list':
        if payload!={'read_only':True}:invalid()
        if not os.path.lexists(root):return {'completed':[]}
        files._check_owner(root,True)
        if files._read(root/'.context')!={'binding':bound}:invalid('context_invalid')
        output=[];source_cache={}
        for path in sorted(root.glob('completed-*.json')):
            receipt=files._read(path);value=_load(root,bound,receipt['preview_ref'])
            if receipt.get('fingerprint')!=value['fingerprint']:invalid('store_invalid')
            use_saved=value['request'].get('use_saved_calendars',False)
            if use_saved not in source_cache:
                try:source_cache[use_saved]=_sources(space,use_saved)
                except (ValueError,OSError,files.MarketFxBatchExecutionError):source_cache[use_saved]=None
            output.append({**_public(value),'freshness':'current' if value['sources']==source_cache[use_saved] else 'stale'})
        return {'completed':output}
    allowed={'detail':{'preview_ref','ordinal'},'confirm':{'preview_ref','confirmed'},'publish':{'confirmation'}}
    if command not in allowed or set(payload)!=allowed[command]:invalid()
    ref=payload['confirmation']['preview_ref'] if command=='publish' else payload['preview_ref']
    value=_load(root,bound,ref)
    if command=='detail':
        ordinal=payload['ordinal']
        if type(ordinal) is not int or not 1<=ordinal<=len(value['blobs']):invalid()
        blob=_blob(root,value['blobs'][ordinal-1])
        rows=blob['rows']
        if blob.get('scope_ref'):
            # Die Tagesliste ist eine Abfrage, keine Neuberechnung.
            with closing(valuation_state.open_market_valuation_state_v1(_state_path(space),ctx)) as store:
                rows=valuation_state.read_valuation_rows_v1(store,blob['scope_ref'],
                    value['request']['start_date'],value['request']['end_date'])
        return {'rows':rows,'calendar':blob['calendar'],'fx_calendar':blob['fx_calendar'],
                'valuation_policy':valuation_policy(value['request'].get('valuation_policy')),
                'market_requirements':blob.get('market_requirements'),'fx_requirements':blob.get('fx_requirements')}
    if value['staged_source_count']:invalid('staged_not_published')
    now=clock().astimezone(timezone.utc)
    if command=='confirm':
        if payload['confirmed'] is not True:invalid('confirmation_required')
        if _sources(space,value['request'].get('use_saved_calendars',False))!=value['sources']:invalid('stale')
        return {'confirmation':{'preview_ref':ref,'binding':bound,'fingerprint':value['fingerprint'],
            'issued_at_utc':now.strftime('%Y-%m-%dT%H:%M:%SZ'),'expires_at_utc':(now+timedelta(seconds=600)).strftime('%Y-%m-%dT%H:%M:%SZ')}}
    grant=payload['confirmation']
    if (set(grant)!={'preview_ref','binding','fingerprint','issued_at_utc','expires_at_utc'} or grant['binding']!=bound or grant['fingerprint']!=value['fingerprint']
        or not files._utc(grant['issued_at_utc'])<=now<=files._utc(grant['expires_at_utc'])
        or not 0<(files._utc(grant['expires_at_utc'])-files._utc(grant['issued_at_utc'])).total_seconds()<=600):invalid('confirmation_required')
    with locked(root,bound):
        for entry in value['blobs']+value['fx_evidence']:_blob(root,entry)
        path=root/('completed-'+ref+'.json')
        if path.exists():
            prior=files._read(path)
            if prior.get('fingerprint')!=value['fingerprint']:invalid('store_invalid')
        else:
            if _sources(space,value['request'].get('use_saved_calendars',False))!=value['sources']:invalid('stale')
            files._write(path,{'preview_ref':ref,'fingerprint':value['fingerprint'],'completed_at_utc':now.strftime('%Y-%m-%dT%H:%M:%SZ')})
    return {**_public(value),'valuation_draft_write':False,'valuation_publication':True}
