# Gefuehrter Rundgang im Demo (#578, 0.3.4): acht Schritte aus „Erste Schritte“ ueber die vier Apps, mit Schrittanzeige, rotem Pfeil
# und Rahmen am Bedienelement, „Zurück“, „Weiter“, „Zeig es mir“ und „Beenden“.
#
# - Nur im Demo: Das Startskript setzt dort die Option portelyra.desktop.demo (scripts/portelyra_desktop.R); der Block links zeigt dann
#   „Rundgang starten“. Beim ersten Oeffnen des Demos beginnt der Rundgang in Data von selbst (einmal je Browser, localStorage).
# - Festlegung 26.11.2026: Der Nutzer fuellt selbst aus. „Zeig es mir“ oeffnet die Stelle (Reiter, Bereich, Importart, Institut);
#   danach fuehrt der Rundgang Teilschritt fuer Teilschritt mit einem Vorschlag, der im Demo sicher passt, und merkt am Bildschirm, wenn
#   ein Teilschritt erledigt ist (Feld gefuellt, Haekchen gesetzt, Meldung der App erschienen). Der Rundgang schreibt nie selbst: Er
#   klickt nur Reiter und Aufklapper; Buchen, Importieren, Aktualisieren und Backup bestaetigt der Nutzer wie sonst.
# - Der Stand wandert beim Wechsel der App im Teil hinter „#“ mit (#rundgang=N): Pfad und Abfrage der Adresse muessen der Startpruefung
#   wegen unveraendert bleiben (vgl. #pl-open in apps/shared/desktop_activity_v1.R). Innerhalb einer App haelt ihn sessionStorage.
# - Ankerpunkte und Erfolgsmeldungen sind Kennungen und Texte der Apps; tests/contracts/test_desktop_tour_v1.R prueft sie an den Quellen,
#   test_desktop_tour_browser_v1.py im echten Browser, dev/tour_probe den ganzen Gang am frischen Demo.

DESKTOP_TOUR_APPS_V1 <- c("current", "data", "cockpit", "tax", "analysis")
DESKTOP_TOUR_ACTIONS_V1 <- c("open", "tab", "radio", "select", "focus")
DESKTOP_TOUR_CONDITIONS_V1 <- c("value", "equals", "checked", "absent", "upload", "text")

desktop_tour_steps_v1 <- function(example = "~/.local/share/portelyra-demo/beispielbeleg/trade-republic-transactions.csv") list(
  list(id = "start", app = "current", title = "Willkommen im Demo", anchor = "nav.pl-nav",
       text = paste("Ein eigenes Portelyra mit erfundenem Bestand auf echten Assets – was Sie hier tun, berührt Ihre Daten nie. Links",
                    "wechseln Sie zwischen den Apps: „Daten“ erfasst und rechnet, Cockpit, Steuer und Analyse zeigen den veröffentlichten",
                    "Stand. Die Eingaben machen Sie selbst; der Rundgang sagt bei jedem Feld, was passt.")),
  list(id = "refresh", app = "data", title = "Alles aktualisieren", anchor = "#refresh_all_toggle",
       text = paste("Holt fehlende Kurse, rechnet Bestand, Tageshistorie und Steuer und veröffentlicht den Stand für Cockpit, Steuer und",
                    "Analyse. Danach rechnet Portelyra nur noch, was sich geändert hat."),
       show = list(list(do = "open", toggle = "refresh_all_toggle", panel = "refresh-all-panel")),
       tasks = list(
         list(text = "Das Häkchen „Bestätigen: …“ setzen – gestartet wird erst mit Ihrer Bestätigung.", point = list("#refresh_all_confirm"),
              done = list(kind = "checked", input = "refresh_all_confirm")),
         list(text = "„Alles aktualisieren“ klicken.", point = list("#refresh_all_start"),
              done = list(kind = "text", target = "#refresh_all_state", pattern = "Läuft im Hintergrund|\\(Ende "))),
       after = paste("Der Lauf rechnet für sich weiter; Sie können gleich zum nächsten Schritt. Wie weit er ist, steht links unter",
                     "„Läuft gerade“ – beim ersten Mal dauert es einige Minuten.")),
  list(id = "history", app = "analysis", title = "Verlauf", anchor = "#analysis_tab a[data-value=\"verlauf\"]",
       text = "Gesamtvermögen, Marktwert, Einstand und Cash je Tag, darunter die unrealisierte GuV der Positionen, die Sie noch halten.",
       show = list(list(do = "tab", set = "analysis_tab", value = "verlauf")),
       point = list(".tab-pane[data-value=\"verlauf\"] .pl-section-head"),
       after = "Fehlt ein Wert, steht dort „nicht verfügbar“ mit dem Grund – Portelyra schätzt nichts."),
  list(id = "returns", app = "analysis", title = "Rendite", anchor = "#analysis_tab a[data-value=\"rendite\"]",
       text = "Die zeitgewichtete Rendite (TWR) und der interne Zinsfuß (IZF) je Zeitraum, vor Steuern.",
       show = list(list(do = "tab", set = "analysis_tab", value = "rendite")),
       point = list(".tab-pane[data-value=\"rendite\"] .pl-section-head"),
       after = paste("Die TWR misst die Anlage unabhängig davon, wann Sie eingezahlt haben; der IZF ist Ihre persönliche Rendite mit allen",
                     "Ein- und Auszahlungen.")),
  list(id = "booking", app = "data", title = "Eine Buchung erfassen", anchor = "#transactions_view a[data-value=\"manual\"]",
       text = "Unter „1. Transaktionen“ → „Manuell“ buchen Sie von Hand – zum Üben einen Kauf des ETF.",
       show = list(list(do = "tab", set = "asset_center_step", value = "transactions"), list(do = "tab", set = "transactions_view", value = "manual"),
                   list(do = "focus", input = "asset_center_asset")),
       tasks = list(
         list(text = "Asset: „MSCI“ tippen und den „iShares Core MSCI World UCITS ETF“ wählen.", point = list("#asset_center_asset"),
              done = list(kind = "value", input = "asset_center_asset")),
         list(text = "Ereignis „Kauf“ lassen und als Konto „Demo-Depot“ wählen.", point = list("#activity_account"),
              done = list(kind = "value", input = "activity_account")),
         list(text = "Zeitangabe „Nur Datum bekannt“ und als Transaktionsdatum den heutigen Tag im Kalender wählen.", point = list("#activity_time_evidence"),
              done = list(all = list(list(kind = "value", input = "activity_date"),
                                     list(any = list(list(kind = "equals", input = "activity_time_evidence", value = "date_only"),
                                                     list(kind = "value", input = "activity_time")))))),
         list(text = "Menge 1 und Stückpreis 130 eintragen – etwa der Kurs der letzten Käufe.", point = list("#activity_quantity"),
              done = list(all = list(list(kind = "value", input = "activity_quantity"), list(kind = "value", input = "activity_unit_price")))),
         list(text = "„Transaktion prüfen“ klicken: Die Vorschau zeigt, was gebucht wird, und nennt jeden Grund dagegen.", point = list("#activity_prepare"),
              done = list(kind = "text", target = "#activity_command_feedback", pattern = "Buchungsvorschau bereit|Transaktion gespeichert"),
              warn = list(when = list(kind = "text", target = "#activity_command_feedback", pattern = "abgelehnt|blockiert"),
                          text = "Die App nennt unter der Maske den Grund. Eingaben anpassen und erneut „Transaktion prüfen“.")),
         list(text = "„Speichern“ bucht genau diese Vorschau.", point = list("#activity_execute"),
              done = list(kind = "text", target = "#activity_command_feedback", pattern = "Transaktion gespeichert"))),
       after = paste("Gebucht. Eine falsche Buchung korrigieren oder stornieren Sie; die frühere bleibt erhalten. „Alles aktualisieren“",
                     "rechnet die neue Buchung in Verlauf und Steuer ein.")),
  list(id = "import", app = "data", title = "Einen Beleg importieren", anchor = "#transactions_view a[data-value=\"import\"]",
       text = "Das Demo bringt einen erfundenen Beleg im Format von Trade Republic mit: einen Kauf und eine Dividende.",
       show = list(list(do = "tab", set = "asset_center_step", value = "transactions"), list(do = "tab", set = "transactions_view", value = "import"),
                   list(do = "radio", input = "import_kind", value = "securities"),
                   list(do = "select", input = "securities_import_adapter", value = "trade_republic_v1")),
       tasks = list(
         list(text = paste0("„Belege auswählen“ und die Datei ", example, " öffnen. Der Ordner ist versteckt: Im Dateidialog zeigt Strg+H ihn, ",
                            "oder Strg+L und den Pfad einfügen."), point = list("#securities_import_files"),
              done = list(kind = "upload", input = "securities_import_files")),
         list(text = "„Belege prüfen“ klicken – das liest die Datei und schreibt nichts.", point = list("#securities_import_review"),
              done = list(kind = "text", target = "#securities_import_state", pattern = "Depot zuordnen|Neue Vorgänge gefunden|schon gebucht")),
         list(text = "Dem Depot aus dem Beleg das „Demo-Depot“ zuordnen.", point = list("#securities_import_depots select", "#securities_import_depots"),
              done = list(kind = "value", target = "#securities_import_depots select")),
         list(text = "Noch einmal „Belege prüfen“ – jetzt zählt Portelyra die neuen Vorgänge.", point = list("#securities_import_review"),
              done = list(kind = "text", target = "#securities_import_state", pattern = "Neue Vorgänge gefunden|Vorschau bereit|Alles gebucht")),
         list(text = paste("Die gefundenen Vorgänge mit dem Beleg vergleichen und das Häkchen „Ich habe die Vorschau mit den Belegen verglichen“",
                           "setzen – nur beim ersten Import mit diesem Leser."), point = list("#securities_import_reader_ack"),
              done = list(any = list(list(kind = "checked", input = "securities_import_reader_ack"),
                                     list(kind = "absent", input = "securities_import_reader_ack")))),
         list(text = "„Neue Vorgänge vorbereiten“ klicken – das zeigt die Vorschau.", point = list("#securities_import_prepare"),
              done = list(kind = "text", target = "#securities_import_state", pattern = "Vorschau bereit|Alles gebucht")),
         list(text = "„Neue Vorgänge buchen“ bucht genau diese Vorschau.", point = list("#securities_import_execute"),
              done = list(kind = "text", target = "#securities_import_state", pattern = "Alles gebucht"))),
       skip = list(when = list(kind = "text", target = "#securities_import_state", pattern = "^(?![\\s\\S]*Alles gebucht)[\\s\\S]*· 0 neu · [1-9]"),
                   text = "Der Beleg ist schon gebucht – ein zweiter Import derselben Datei bucht nichts doppelt."),
       after = "Gebucht: ein Kauf und eine Dividende. Ein zweiter Import derselben Datei erkennt beide als schon gebucht."),
  list(id = "tax", app = "tax", title = "Den Steuerbericht ansehen", anchor = "#simple_report_build",
       text = "Die einfache Fassung belegt Veräußerungen je Lot, Erträge und Bestände je Konto, mit Haltedauer und Jahresfrist.",
       show = list(),
       tasks = list(
         list(text = "Steuerjahr wählen – im Demo etwa das Vorjahr – und „Report erstellen“ klicken.", point = list("#simple_report_build"),
              done = list(kind = "text", target = "#simple_report_state", pattern = "Report [0-9]{4} erstellt"),
              warn = list(when = list(kind = "text", target = "#simple_report_state", pattern = "FIFO-Stand|nicht erstellt"),
                          text = paste("Der Bestand hat sich seit dem letzten „Alles aktualisieren“ geändert. In „Daten“ links „Alles",
                                       "aktualisieren“ ausführen und den Report danach neu erstellen.")))),
       after = paste("Darunter steht der Report; „Ausführliche Fassung erstellen“ hängt Jahresrechnung und Rechenblätter an. Das Demo rechnet",
                     "mit einem erfundenen persönlichen Steuersatz von 30 %.")),
  list(id = "backup", app = "data", title = "Ein Backup anlegen", anchor = "#settings_toggle",
       text = "Unter „Einstellungen“ → „Sicherheit und Speicher“ legen Sie Backups an und spielen sie zurück.",
       show = list(list(do = "open", toggle = "settings_toggle", panel = "settings-panel"), list(do = "tab", set = "settings_tabs", value = "security")),
       tasks = list(
         list(text = "Das Kästchen „Verstanden: …“ setzen.", point = list("#backups_create_understood", "#data-backups-card"),
              done = list(kind = "checked", input = "backups_create_understood")),
         list(text = "„Backup anlegen“ klicken; Portelyra läuft dabei weiter.", point = list("#backups_create"),
              done = list(kind = "text", target = "#backups_state", pattern = "Backup läuft|Letztes Backup angelegt"),
              warn = list(when = list(kind = "text", target = "#backups_state", pattern = "nicht angelegt"),
                          text = "Über der Karte steht, warum das Backup nicht angelegt wurde."))),
       after = paste("Das Backup liegt auf diesem Rechner. Eine Kopie außerhalb, etwa auf einem USB-Stick, bewahren Sie selbst auf.")))

DESKTOP_TOUR_END_V1 <- list(title = "Rundgang beendet",
  text = paste("Zurück im Tab der Einrichtung richten Sie Ihr eigenes Portfolio ein. Das „?“ an einer Karte öffnet die Hilfe an der",
               "passenden Stelle; den Rundgang starten Sie links jederzeit neu."))
DESKTOP_TOUR_MISSING_V1 <- "Diese Stelle ist gerade nicht zu sehen. „Zeig es mir“ öffnet sie, sonst den Reiter selbst wählen."

# Der Beispielbeleg liegt im Demo-Home (apps/shared/desktop_demo_home_v1.R); gezeigt mit „~“ fuer den persoenlichen Ordner.
desktop_tour_example_v1 <- function(home = Sys.getenv("PORTELYRA_DESKTOP_HOME_INTERNAL", unset = "")) {
  if (!nzchar(home)) return("~/.local/share/portelyra-demo/beispielbeleg/trade-republic-transactions.csv")
  path <- file.path(sub("/+$", "", home), "beispielbeleg", "trade-republic-transactions.csv")
  own <- sub("/+$", "", path.expand("~"))
  if (nzchar(own) && startsWith(path, paste0(own, "/"))) paste0("~", substring(path, nchar(own) + 1L)) else path
}

desktop_tour_data_json_v1 <- function(steps = desktop_tour_steps_v1(desktop_tour_example_v1())) {
  json <- as.character(jsonlite::toJSON(list(steps = steps, end = DESKTOP_TOUR_END_V1, missing = DESKTOP_TOUR_MISSING_V1), auto_unbox = TRUE))
  gsub("</", "<\\/", json, fixed = TRUE)
}

# Knopf „Rundgang starten“ fuer den Block links, dazu Schritte, Aussehen und Skript. Nur im Demo eingebunden (desktop_activity_v1.R).
desktop_tour_ui_v1 <- function(steps = desktop_tour_steps_v1(desktop_tour_example_v1())) shiny::div(class = "pl-activity-seg pl-tour-seg",
  shiny::tags$button(type = "button", class = "btn btn-default pl-tour-start", `data-pl-tour-start` = "1", "Rundgang starten"),
  shiny::tags$script(type = "application/json", id = "pl-tour-data", shiny::HTML(desktop_tour_data_json_v1(steps))),
  shiny::tags$style(shiny::HTML(DESKTOP_TOUR_CSS_V1)),
  shiny::tags$script(shiny::HTML(DESKTOP_TOUR_JS_V1)))

DESKTOP_TOUR_CSS_V1 <- paste0(
  ":root{--pl-tour:#c62828}",
  ".pl-tour{position:fixed;right:24px;bottom:24px;z-index:1040;width:min(400px,calc(100vw - 32px));max-height:calc(100vh - 48px);overflow:auto;",
  "background:var(--pl-surface,#fff);color:var(--pl-text,#17241d);border:1px solid var(--pl-line,#d8e2dc);border-top:4px solid var(--pl-tour);",
  "border-radius:14px;box-shadow:0 18px 40px rgba(23,36,29,.22);padding:16px 18px 12px}",
  ".pl-tour.pl-tour-top{top:24px;bottom:auto}",
  ".pl-tour.pl-tour-left{right:auto;left:24px}",
  # Bootstraps .btn setzt display:inline-block und hebt damit das Attribut hidden auf; im Kasten gilt hidden immer.
  ".pl-tour [hidden],.pl-tour[hidden],.pl-tour-ring[hidden],.pl-tour-arrow[hidden]{display:none!important}",
  ".pl-tour-count{margin:0 0 4px;font-size:.85em;color:var(--pl-muted,#5d6b63)}",
  ".pl-tour-title{margin:0 0 6px;font-size:1.1em}",
  ".pl-tour-text{margin:0 0 10px;line-height:1.45}",
  # Kompakt (Probe 26.11.2026: die ganze Liste machte den Kasten so hoch, dass er das Feld verdeckte): nur der offene Teilschritt.
  ".pl-tour-part{margin:0 0 4px;font-size:.85em;color:var(--pl-muted,#5d6b63)}",
  ".pl-tour-tasks{margin:0 0 10px;padding:0;list-style:none;line-height:1.45}",
  ".pl-tour-tasks li{display:none}",
  ".pl-tour-tasks li.pl-tour-now{display:block;font-weight:600}",
  ".pl-tour-note{margin:0 0 10px;font-size:.9em;color:var(--pl-warning,#8a641f)}",
  ".pl-tour-actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center}",
  ".pl-tour.pl-tour-ready [data-tour=\"next\"]{box-shadow:0 0 0 3px rgba(198,40,40,.25)}",
  ".pl-tour-end{margin-top:8px;background:none;border:0;padding:0;color:var(--pl-muted,#5d6b63);text-decoration:underline;cursor:pointer}",
  ".pl-tour-ring{position:fixed;z-index:1039;pointer-events:none;border:3px solid var(--pl-tour);border-radius:10px;",
  "box-shadow:0 0 0 4px rgba(198,40,40,.18)}",
  ".pl-tour-arrow{position:fixed;z-index:1039;pointer-events:none;color:var(--pl-tour);width:64px;height:32px;",
  "animation:pl-tour-nudge 1.2s ease-in-out infinite}",
  ".pl-tour-arrow svg{display:block}",
  ".pl-tour-arrow.pl-tour-arrow-left svg{transform:scaleX(-1)}",
  ".pl-tour-arrow.pl-tour-arrow-left{animation-name:pl-tour-nudge-left}",
  "@keyframes pl-tour-nudge{0%,100%{transform:translateX(0)}50%{transform:translateX(6px)}}",
  "@keyframes pl-tour-nudge-left{0%,100%{transform:translateX(0)}50%{transform:translateX(-6px)}}",
  "@media(prefers-reduced-motion:reduce){.pl-tour-arrow{animation:none}}",
  ".pl-tour-start{width:100%}")

DESKTOP_TOUR_JS_V1 <- r"---(
(function(){
  'use strict';
  var KEY = 'pl-tour', SEEN = 'pl-tour-seen', WAIT = 6000;
  var holder = document.getElementById('pl-tour-data');
  if (!holder || window.plTourLoaded) { return; }
  window.plTourLoaded = true;
  var data = null, box = null, ring = null, arrow = null, target = null, frame = null, mem = null, aimToken = 0, booted = false;
  var ticker = null, ticked = 0, skipped = false, aimedAt = -1;
  try { data = JSON.parse(holder.textContent); } catch (e) { return; }

  function session() { try { return window.sessionStorage; } catch (e) { return null; } }
  function local() { try { return window.localStorage; } catch (e) { return null; } }
  function getState() {
    var s = session();
    if (!s) { return mem; }
    try { var v = JSON.parse(s.getItem(KEY) || 'null'); return v && v.step > 0 ? v : null; } catch (e) { return mem; }
  }
  function setState(v) {
    mem = v; var s = session();
    if (!s) { return; }
    try { if (v) { s.setItem(KEY, JSON.stringify(v)); } else { s.removeItem(KEY); } } catch (e) {}
  }
  function markSeen() { var l = local(); if (l) { try { l.setItem(SEEN, '1'); } catch (e) {} } }
  function firstVisit() {
    var l = local();
    if (!l) { return false; }
    try { if (l.getItem(SEEN)) { return false; } l.setItem(SEEN, '1'); return true; } catch (e) { return false; }
  }
  function esc(v) { return window.CSS && CSS.escape ? CSS.escape(v) : String(v).replace(/["\\]/g, '\\$&'); }
  function list(v) { return Array.isArray(v) ? v : (v ? [v] : []); }
  function here() { var a = document.querySelector('nav.pl-nav a[aria-current="page"]'); return a ? a.getAttribute('data-portelyra-app') : null; }
  function appLabel(app) {
    var a = document.querySelector('nav.pl-nav a[data-portelyra-app="' + esc(app) + '"] .pl-nav-label');
    return a ? a.textContent.trim() : app;
  }
  function appLink(app) { return document.querySelector('nav.pl-nav a[data-portelyra-nav="app"][data-portelyra-app="' + esc(app) + '"]'); }
  function withStep(href, step) {
    var i = href.indexOf('#'), base = i < 0 ? href : href.slice(0, i);
    var parts = (i < 0 ? '' : href.slice(i + 1)).split('&').filter(function (p) { return p && p.indexOf('rundgang=') !== 0; });
    if (step) { parts.push('rundgang=' + step); }
    return base + (parts.length ? '#' + parts.join('&') : '');
  }
  // Waehrend des Rundgangs tragen die Links zu den anderen Apps den Schritt mit; so bleibt er auch beim Wechsel von Hand erhalten.
  function decorate(step) {
    document.querySelectorAll('a[data-portelyra-nav="app"]').forEach(function (a) {
      var h = a.getAttribute('href'); if (h) { a.setAttribute('href', withStep(h, step)); }
    });
  }
  function fromHash() {
    var h = window.location.hash || '', m = /(?:^#|&)rundgang=(\d+)/.exec(h);
    if (!m) { return false; }
    setState({ step: parseInt(m[1], 10) });
    var rest = h.replace(/^#/, '').split('&').filter(function (p) { return p && p.indexOf('rundgang=') !== 0; }).join('&');
    try { history.replaceState(null, '', window.location.pathname + window.location.search + (rest ? '#' + rest : '')); } catch (e) {}
    return true;
  }
  function visible(n) {
    if (!n || !document.body.contains(n)) { return false; }
    var r = n.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && window.getComputedStyle(n).visibility !== 'hidden';
  }
  // Was man sieht: bei einer Auswahl mit Suchfeld der sichtbare Rahmen, bei Haekchen, Optionsknopf und Dateiauswahl das ganze Feld.
  function visual(n) {
    if (!n) { return null; }
    if (n.selectize && n.selectize.$wrapper) { var w = n.selectize.$wrapper[0]; return visible(w) ? w : null; }
    if (n.tagName === 'INPUT' && /^(checkbox|radio|file)$/.test(n.type)) {
      var c = n.closest('.checkbox, .radio, .form-group, .shiny-input-container'); return visible(c) ? c : null;
    }
    return visible(n) ? n : null;
  }
  // Reiter und aufklappbare Bereiche ueber dem Element oeffnen, aeussere zuerst.
  function reveal(n) {
    var chain = [];
    for (var p = n; p && p !== document.body; p = p.parentElement) { chain.unshift(p); }
    chain.forEach(function (p) {
      if (p.classList && p.classList.contains('tab-pane') && !p.classList.contains('active') && p.id) {
        var id = esc(p.id);
        var a = document.querySelector('a[data-toggle="tab"][href="#' + id + '"], a[data-bs-toggle="tab"][href="#' + id + '"]');
        if (a && window.jQuery && jQuery.fn.tab) { jQuery(a).tab('show'); }
      }
      if (p.tagName === 'DETAILS' && !p.open) { p.open = true; }
    });
  }
  // Bedingungen eines Teilschritts: ein Feld ist gefuellt, ein Haekchen gesetzt, eine Meldung der App erschienen.
  function field(c) { return c.input ? document.getElementById(c.input) : (c.target ? document.querySelector(c.target) : null); }
  function val(n) {
    if (!n) { return ''; }
    if (n.selectize) { var v = n.selectize.getValue(); return Array.isArray(v) ? v.join(',') : String(v || ''); }
    if (!/^(INPUT|SELECT|TEXTAREA)$/.test(n.tagName)) { var inner = n.querySelector('input, select, textarea'); return inner ? val(inner) : ''; }
    return String(n.value || '');
  }
  function holds(c) {
    if (!c) { return false; }
    if (c.all) { return list(c.all).every(holds); }
    if (c.any) { return list(c.any).some(holds); }
    var n = field(c);
    if (c.kind === 'value') { return val(n).trim() !== ''; }
    if (c.kind === 'equals') { return val(n) === c.value; }
    if (c.kind === 'checked') { return !!(n && n.checked); }
    if (c.kind === 'absent') { return !n || !visual(n); }
    if (c.kind === 'upload') {
      var bar = document.querySelector('#' + esc(c.input) + '_progress .progress-bar');
      return !!(bar && bar.style.width === '100%');
    }
    if (c.kind === 'text') { return !!(n && visible(n) && new RegExp(c.pattern).test(n.innerText || '')); }
    return false;
  }
  function build() {
    if (box) { return; }
    ring = document.createElement('div'); ring.className = 'pl-tour-ring'; ring.hidden = true; ring.setAttribute('aria-hidden', 'true');
    arrow = document.createElement('div'); arrow.className = 'pl-tour-arrow'; arrow.hidden = true; arrow.setAttribute('aria-hidden', 'true');
    arrow.innerHTML = '<svg viewBox="0 0 64 32" width="64" height="32" focusable="false"><path d="M4 16h40" stroke="currentColor" ' +
      'stroke-width="7" stroke-linecap="round"/><path d="M36 3l24 13-24 13z" fill="currentColor"/></svg>';
    box = document.createElement('section'); box.className = 'pl-tour'; box.hidden = true;
    box.setAttribute('role', 'dialog'); box.setAttribute('aria-modal', 'false'); box.setAttribute('aria-labelledby', 'pl-tour-title');
    box.innerHTML = '<p class="pl-tour-count" aria-live="polite"></p><h2 class="pl-tour-title" id="pl-tour-title"></h2>' +
      '<p class="pl-tour-text"></p><p class="pl-tour-part" hidden></p><ol class="pl-tour-tasks" hidden></ol><p class="pl-tour-note" hidden></p>' +
      '<div class="pl-tour-actions">' +
      '<button type="button" class="btn btn-default" data-tour="back">Zurück</button>' +
      '<button type="button" class="btn btn-default" data-tour="show">Zeig es mir</button>' +
      '<button type="button" class="btn btn-primary" data-tour="next">Weiter</button>' +
      '<button type="button" class="btn btn-default" data-tour="again">Noch einmal</button>' +
      '<button type="button" class="btn btn-primary" data-tour="close">Schließen</button></div>' +
      '<button type="button" class="pl-tour-end" data-tour="end">Beenden</button>';
    document.body.appendChild(ring); document.body.appendChild(arrow); document.body.appendChild(box);
    box.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('[data-tour]') : null;
      if (!b) { return; }
      var what = b.getAttribute('data-tour');
      if (what === 'back') { go(-1); } else if (what === 'next') { next(); } else if (what === 'show') { show(); }
      else if (what === 'again') { start(); } else { end(); }
    });
    box.addEventListener('keydown', function (e) { if (e.key === 'Escape') { end(); } });
    window.addEventListener('scroll', schedule, true);
    window.addEventListener('resize', schedule);
    window.setInterval(schedule, 400);
  }
  function q(sel) { return box.querySelector(sel); }
  function note(text) { var n = q('.pl-tour-note'); n.hidden = !text; n.textContent = text || ''; }
  function render(focus) {
    var st = getState();
    aimToken += 1; target = null; aimedAt = -1;
    if (ticker) { window.clearInterval(ticker); ticker = null; }
    if (!st) { if (box) { box.hidden = true; } place(); decorate(0); return; }
    build();
    var steps = data.steps, n = steps.length;
    box.hidden = false; box.classList.remove('pl-tour-ready'); note('');
    var tasks = q('.pl-tour-tasks'); tasks.hidden = true; tasks.innerHTML = ''; q('.pl-tour-part').hidden = true;
    var buttons = { back: q('[data-tour="back"]'), show: q('[data-tour="show"]'), next: q('[data-tour="next"]'),
                    again: q('[data-tour="again"]'), close: q('[data-tour="close"]'), end: q('[data-tour="end"]') };
    Object.keys(buttons).forEach(function (k) { buttons[k].hidden = true; });
    var text = q('.pl-tour-text'); text.hidden = false;
    if (st.step > n) {
      q('.pl-tour-count').textContent = '';
      q('.pl-tour-title').textContent = data.end.title; text.textContent = data.end.text;
      buttons.again.hidden = false; buttons.close.hidden = false; decorate(0); place();
      if (focus) { buttons.close.focus({ preventScroll: true }); }
      return;
    }
    var step = steps[st.step - 1], foreign = step.app !== 'current' && step.app !== here();
    var guided = !!(step.tasks && list(step.tasks).length);
    q('.pl-tour-count').textContent = 'Schritt ' + st.step + ' von ' + n;
    q('.pl-tour-title').textContent = step.title;
    text.textContent = st.shown && !guided && step.after ? step.after : step.text;
    buttons.back.hidden = st.step <= 1; buttons.end.hidden = false; buttons.next.hidden = false;
    buttons.show.hidden = foreign || !!st.shown || !(guided || list(step.show).length);
    buttons.next.textContent = foreign ? 'Zur App „' + appLabel(step.app) + '“' : (st.step === n ? 'Fertig' : 'Weiter');
    decorate(st.step);
    if (foreign) {
      note('Dieser Schritt liegt in der App „' + appLabel(step.app) + '“.'); place();
    } else if (st.shown && guided) {
      ticked = 0; skipped = false; text.hidden = true; tasks.hidden = false;
      list(step.tasks).forEach(function (t) { var li = document.createElement('li'); li.textContent = t.text; tasks.appendChild(li); });
      follow(); ticker = window.setInterval(follow, 400);
    } else {
      aim(list(st.shown && step.point ? step.point : step.anchor), true);
    }
    if (focus) { buttons.next.focus({ preventScroll: true }); }
  }
  // Teilschritte der Reihe nach: erledigt bleibt erledigt; der Pfeil zeigt auf den ersten offenen.
  function follow() {
    var st = getState(); if (!st || !st.shown) { return; }
    var step = data.steps[st.step - 1]; if (!step) { return; }
    var tasks = list(step.tasks), items = q('.pl-tour-tasks').children, text = q('.pl-tour-text');
    while (ticked < tasks.length && holds(tasks[ticked].done)) { ticked += 1; }
    // Schon erledigt, etwa ein Beleg, der schon gebucht ist: der Rest entfaellt mit eigenem Satz.
    if (step.skip && ticked < tasks.length && holds(step.skip.when)) { ticked = tasks.length; skipped = true; }
    for (var i = 0; i < items.length; i += 1) {
      items[i].className = i < ticked ? 'pl-tour-ok' : (i === ticked ? 'pl-tour-now' : '');
    }
    var part = q('.pl-tour-part');
    part.hidden = ticked >= tasks.length; part.textContent = 'Teil ' + (ticked + 1) + ' von ' + tasks.length;
    if (ticked >= tasks.length) {
      if (text.hidden) { text.hidden = false; text.textContent = (skipped ? step.skip.text : step.after) || ''; }
      note(''); box.classList.add('pl-tour-ready'); target = null; place();
      if (ticker) { window.clearInterval(ticker); ticker = null; }
      return;
    }
    var task = tasks[ticked];
    note(task.warn && holds(task.warn.when) ? task.warn.text : '');
    if (aimedAt !== ticked) { aimedAt = ticked; aimToken += 1; aim(list(task.point), true); }
  }
  function aim(selectors, scroll) {
    var token = aimToken, t0 = Date.now(), opened = {};
    (function poll() {
      if (token !== aimToken) { return; }
      var late = Date.now() - t0 > WAIT / 2, found = null;
      for (var i = 0; i < selectors.length && !found; i += 1) {
        var node = document.querySelector(selectors[i]);
        if (node && !opened[i]) { opened[i] = true; reveal(node); }
        var v = node ? visual(node) : null;
        if (v && (i === 0 || late)) { found = v; }
      }
      if (found) {
        target = found;
        if (scroll) { found.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
        place(); return;
      }
      if (Date.now() - t0 > WAIT) {
        target = null; place();
        var st = getState(), step = st && data.steps[st.step - 1];
        if (step && !step.tasks) { note(data.missing); }
        return;
      }
      window.setTimeout(poll, 150);
    })();
  }
  function schedule() { if (!frame) { frame = window.requestAnimationFrame(place); } }
  function place() {
    frame = null;
    if (!ring) { return; }
    var r = target && !box.hidden && visible(target) ? target.getBoundingClientRect() : null;
    if (!r) { ring.hidden = true; arrow.hidden = true; box.classList.remove('pl-tour-top', 'pl-tour-left'); return; }
    ring.hidden = false;
    ring.style.left = Math.round(r.left - 6) + 'px'; ring.style.top = Math.round(r.top - 6) + 'px';
    ring.style.width = Math.round(r.width + 12) + 'px'; ring.style.height = Math.round(r.height + 12) + 'px';
    arrow.hidden = false;
    var leftSide = r.left > 96 && r.right > window.innerWidth * 0.35;
    arrow.classList.toggle('pl-tour-arrow-left', !leftSide);
    arrow.style.left = Math.round(leftSide ? r.left - 76 : r.right + 12) + 'px';
    arrow.style.top = Math.round(r.top + r.height / 2 - 16) + 'px';
    // Der Kasten legt sich nicht ueber das Ziel: von vier Ecken (unten rechts zuerst) die erste, die es nicht verdeckt, sonst die mit der
    // kleinsten Ueberdeckung (Probe 26.11.2026: oben rechts lag er ueber dem Asset-Feld).
    var W = window.innerWidth, H = window.innerHeight, bw = box.offsetWidth, bh = box.offsetHeight, m = 24, pad = 16;
    var spots = [['', W - m - bw, H - m - bh], ['top', W - m - bw, m], ['left', m, H - m - bh], ['top left', m, m]], best = spots[0], least = Infinity;
    spots.forEach(function (s) {
      var w = Math.min(s[1] + bw, r.right + pad) - Math.max(s[1], r.left - pad), h = Math.min(s[2] + bh, r.bottom + pad) - Math.max(s[2], r.top - pad);
      var area = Math.max(0, w) * Math.max(0, h);
      if (area < least) { least = area; best = s; }
    });
    box.classList.toggle('pl-tour-top', best[0].indexOf('top') >= 0);
    box.classList.toggle('pl-tour-left', best[0].indexOf('left') >= 0);
  }
  function travel(app, step) {
    var a = appLink(app);
    setState({ step: step });
    if (!a) { render(true); note('Die App „' + appLabel(app) + '“ ist gerade nicht erreichbar.'); return; }
    window.location.href = withStep(a.getAttribute('href'), step);
  }
  function go(delta) {
    var st = getState(); if (!st) { return; }
    var n = data.steps.length, to = Math.max(1, Math.min(n + 1, st.step + delta));
    if (to <= n) { var step = data.steps[to - 1]; if (step.app !== 'current' && step.app !== here()) { travel(step.app, to); return; } }
    setState({ step: to }); render(true);
  }
  function next() {
    var st = getState(); if (!st) { return; }
    var step = data.steps[st.step - 1];
    if (step && step.app !== 'current' && step.app !== here()) { travel(step.app, st.step); return; }
    go(1);
  }
  function run(a, done) {
    var t0 = Date.now();
    function retry(find, act) {
      (function poll() {
        var hit = find();
        if (hit) { act(hit); done(); return; }
        if (Date.now() - t0 > WAIT) { done(); return; }
        window.setTimeout(poll, 150);
      })();
    }
    if (a.do === 'open') {
      var p = document.getElementById(a.panel);
      if (p && p.hasAttribute('hidden')) { var b = document.getElementById(a.toggle); if (b) { b.click(); } }
      done();
    } else if (a.do === 'tab') {
      retry(function () { return document.querySelector('#' + esc(a.set) + ' a[data-value="' + esc(a.value) + '"]'); },
            function (l) { reveal(l); if (window.jQuery && jQuery.fn.tab) { jQuery(l).tab('show'); } });
    } else if (a.do === 'radio') {
      retry(function () { return document.querySelector('input[type="radio"][name="' + esc(a.input) + '"][value="' + esc(a.value) + '"]'); },
            function (r) { if (!r.checked) { r.checked = true; if (window.jQuery) { jQuery(r).trigger('change'); } } });
    } else if (a.do === 'select') {
      retry(function () {
        var s = document.getElementById(a.input);
        if (!s) { return null; }
        if (s.selectize) { return s.selectize.options[a.value] ? s : null; }
        return Array.prototype.some.call(s.options || [], function (o) { return o.value === a.value; }) ? s : null;
      }, function (s) {
        if (s.selectize) { s.selectize.setValue(a.value); } else { s.value = a.value; if (window.jQuery) { jQuery(s).trigger('change'); } }
      });
    } else if (a.do === 'focus') {
      retry(function () { var s = document.getElementById(a.input); return s && visual(s) ? s : null; },
            function (s) { if (s.selectize) { s.selectize.focus(); } else { s.focus(); } });
    } else { done(); }
  }
  function show() {
    var st = getState(); if (!st) { return; }
    var step = data.steps[st.step - 1]; if (!step) { return; }
    var todo = list(step.show).slice(), token = aimToken;
    (function stepOn() {
      if (token !== aimToken) { return; }
      if (!todo.length) { setState({ step: st.step, shown: true }); render(false); return; }
      run(todo.shift(), function () { window.setTimeout(stepOn, 200); });
    })();
  }
  function start() { markSeen(); setState({ step: 1 }); render(true); }
  function end() { markSeen(); setState(null); render(false); }

  var hashed = fromHash();
  document.addEventListener('click', function (e) {
    var b = e.target && e.target.closest ? e.target.closest('[data-pl-tour-start]') : null;
    if (b) { e.preventDefault(); start(); }
  });
  function boot() {
    if (booted) { return; }
    booted = true;
    var st = getState();
    // Nach dem Neuladen ist geoeffnet nichts mehr: Der Schritt beginnt wieder vor „Zeig es mir“.
    if (st) { setState({ step: st.step }); render(false); } else if (!hashed && here() === 'data' && firstVisit()) { start(); }
  }
  if (window.jQuery) {
    jQuery(document).one('shiny:sessioninitialized', function () {
      jQuery(document).one('shiny:idle', function () { window.setTimeout(boot, 300); });
      window.setTimeout(boot, 4000);
    });
  }
  window.setTimeout(boot, 8000);
})();
)---"
