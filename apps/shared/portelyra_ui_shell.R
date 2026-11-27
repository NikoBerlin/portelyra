portelyra_app_registry <- function(presentation_context = NULL, project_root = NULL) {
  translated <- function(key, fallback) {
    if (is.null(presentation_context) || is.null(project_root)) return(fallback)
    presentation_label_v1(key, presentation_context, project_root, fallback)
  }
  list(
    data = list(
      label = translated("nav.data", "Daten"),
      short_label = "D",
      purpose = translated("nav.data.purpose", "Assets, Konten, Transaktionen und Imports verwalten"),
      capability = "Kontrollierte Schreibaktionen",
      url_env = "PORTELYRA_APP_URL_DATA"
    ),
    cockpit = list(
      # Grundlagen statt Ergebnisse (rc.313, #478); heisst seit rc.418 wieder „Cockpit“ und zeigt die Datenbasis (#490). Kennung "cockpit".
      label = translated("nav.cockpit", "Cockpit"),
      short_label = "C",
      purpose = translated("nav.cockpit.purpose", "Bestände, Cash laut Auszug und Stand je Datenart einsehen"),
      capability = "Nur abgeschlossene Stände",
      url_env = "PORTELYRA_APP_URL_COCKPIT"
    ),
    tax = list(
      label = translated("nav.tax", "Steuer"),
      short_label = "S",
      purpose = translated("nav.tax.purpose", "Regelmodule wählen und abgeschlossene Projektionen nachvollziehen"),
      capability = "Kontrollierte Steuereinstellungen · abgeschlossene Projektionen",
      url_env = "PORTELYRA_APP_URL_TAX"
    ),
    analysis = list(
      label = translated("nav.analysis", "Analyse"),
      short_label = "A",
      purpose = translated("nav.analysis.purpose", "Bewertung und offengelegte Kennzahlen untersuchen"),
      capability = "Nur abgeschlossene Analysen",
      url_env = "PORTELYRA_APP_URL_ANALYSIS"
    )
  )
}

portelyra_ui_css <- function() {
  paste(
    ":root{--pl-bg:#f4f7f5;--pl-surface:#fff;--pl-surface-soft:#edf3ef;--pl-text:#17241d;--pl-muted:#5d6b63;--pl-line:#d8e2dc;--pl-brand:#155b43;--pl-brand-dark:#0d3f2f;--pl-accent:#d9a441;--pl-danger:#9a3f3f;--pl-warning:#8a641f;--pl-radius:18px;--pl-shadow:0 12px 30px rgba(23,36,29,.08)}",
    "*{box-sizing:border-box}body{margin:0;background:var(--pl-bg);color:var(--pl-text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}",
    ".container-fluid{padding:0}.pl-shell{display:grid;grid-template-columns:264px minmax(0,1fr);min-height:100vh}.pl-sidebar{background:var(--pl-brand-dark);color:#fff;padding:28px 20px;display:flex;flex-direction:column;gap:28px}.pl-brand{display:flex;align-items:center;gap:12px}.pl-brand-mark{width:40px;height:40px;border-radius:13px;background:linear-gradient(145deg,var(--pl-accent),#f0d48d);color:var(--pl-brand-dark);display:grid;place-items:center;font-weight:800}.pl-brand-name{font-size:1.2rem;font-weight:750;letter-spacing:.01em}.pl-brand-subtitle{font-size:.78rem;color:#bed1c7}.pl-nav{display:grid;gap:8px}.pl-nav-item{display:grid;grid-template-columns:34px 1fr;gap:10px;align-items:center;padding:10px 12px;border-radius:13px;color:#dbe8e1;text-decoration:none;border:1px solid transparent}.pl-nav-item:hover{color:#fff;background:rgba(255,255,255,.07);text-decoration:none}.pl-nav-item[aria-current='page']{background:#fff;color:var(--pl-brand-dark);box-shadow:0 8px 18px rgba(0,0,0,.12)}.pl-nav-item.pl-nav-unavailable:not([aria-current='page']){cursor:default;opacity:.72}.pl-nav-icon{width:30px;height:30px;border-radius:10px;background:rgba(255,255,255,.1);display:grid;place-items:center;font-weight:750}.pl-nav-item[aria-current='page'] .pl-nav-icon{background:var(--pl-surface-soft)}.pl-nav-label{font-weight:680}.pl-nav-purpose{display:block;font-size:.7rem;font-weight:450;line-height:1.25;opacity:.75}.pl-sidebar-note{margin-top:auto;padding:14px;border:1px solid rgba(255,255,255,.14);border-radius:14px;color:#c8d9d0;font-size:.76rem;line-height:1.45}.pl-main{min-width:0;padding:34px clamp(20px,4vw,58px) 52px}.pl-topbar{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;margin-bottom:28px}.pl-eyebrow{text-transform:uppercase;letter-spacing:.12em;color:var(--pl-brand);font-size:.72rem;font-weight:800;margin-bottom:8px}.pl-title{font-size:clamp(1.9rem,4vw,3rem);line-height:1.05;margin:0 0 10px;font-weight:780;letter-spacing:-.035em}.pl-description{max-width:760px;color:var(--pl-muted);font-size:1rem;line-height:1.55;margin:0}.pl-capabilities{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.pl-chip{display:inline-flex;align-items:center;min-height:28px;padding:5px 10px;border-radius:999px;background:var(--pl-surface-soft);color:var(--pl-brand-dark);font-size:.72rem;font-weight:700;border:1px solid var(--pl-line)}.pl-actions{display:flex;flex-wrap:wrap;gap:9px;justify-content:flex-end}.pl-content{display:grid;grid-template-columns:minmax(0,1fr);gap:22px}.pl-card{background:var(--pl-surface);border:1px solid var(--pl-line);border-radius:var(--pl-radius);padding:22px;box-shadow:var(--pl-shadow)}.pl-card h2,.pl-card h3{margin-top:0}.pl-section-head{display:flex;justify-content:space-between;align-items:end;gap:16px;margin-bottom:16px}.pl-section-title{font-size:1.12rem;font-weight:760;margin:0}.pl-section-copy{color:var(--pl-muted);margin:5px 0 0;font-size:.86rem}.pl-step-grid,.pl-kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.pl-kpi{padding:17px;border:1px solid var(--pl-line);border-radius:15px;background:#fbfdfb;min-width:0}.pl-kpi-label{color:var(--pl-muted);font-size:.75rem;font-weight:750;text-transform:uppercase;letter-spacing:.045em}.pl-kpi-value{font-size:clamp(1.25rem,2.4vw,1.75rem);font-weight:790;letter-spacing:-.025em;margin:7px 0 4px;overflow-wrap:anywhere}.pl-kpi-detail{color:var(--pl-muted);font-size:12px;line-height:1.35}.pl-kpi-positive .pl-kpi-value{color:var(--pl-brand)}.pl-kpi-negative .pl-kpi-value{color:var(--pl-warning)}.pl-step{padding:16px;border:1px solid var(--pl-line);border-radius:15px;background:#fbfdfb;display:flex;flex-direction:column;gap:10px}.pl-step-number{width:28px;height:28px;border-radius:9px;background:var(--pl-brand);color:#fff;display:grid;place-items:center;font-size:.75rem;font-weight:800}.pl-step-title{font-weight:750}.pl-step-copy{font-size:.8rem;color:var(--pl-muted);line-height:1.4;min-height:45px}.pl-status{border-radius:14px;padding:13px 15px;border:1px solid var(--pl-line);background:var(--pl-surface-soft);display:flex;gap:10px;align-items:flex-start}.pl-status-dot{width:9px;height:9px;border-radius:50%;background:var(--pl-brand);margin-top:5px;flex:0 0 auto}.pl-status-positive{background:#eef8f2;border-color:#b9d8c5}.pl-status-positive .pl-status-dot{background:var(--pl-brand)}.pl-status-warning{background:#fff8e8;border-color:#ead39a}.pl-status-warning .pl-status-dot{background:var(--pl-warning)}.pl-status-error{background:#fff0f0;border-color:#e5baba}.pl-status-error .pl-status-dot{background:var(--pl-danger)}.pl-status-title{font-weight:750}.pl-status-copy{font-size:.82rem;color:var(--pl-muted);margin-top:2px}.pl-workspace-tabs>.tabbable>.nav-tabs{border-bottom:1px solid var(--pl-line);display:flex;gap:4px;margin-bottom:18px}.pl-workspace-tabs>.tabbable>.nav-tabs>li{float:none}.pl-workspace-tabs>.tabbable>.nav-tabs>li>a{border:0;border-radius:10px 10px 0 0;color:var(--pl-muted);font-weight:700;margin:0}.pl-workspace-tabs>.tabbable>.nav-tabs>li.active>a,.pl-workspace-tabs>.tabbable>.nav-tabs>li>a:hover{background:var(--pl-surface-soft);color:var(--pl-brand-dark);border:0}.pl-data-kpis{margin:16px 0}.pl-deferred-capability{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-top:18px}.pl-deferred-capability .pl-status{flex:1}.pl-transaction-editor{margin-top:22px;padding-top:20px;border-top:1px solid var(--pl-line)}.pl-transaction-editor h3,.pl-master-import-center h3{font-size:1.02rem;margin:0 0 5px}.pl-master-import-center .pl-kpi-grid{margin-top:16px}.pl-form-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:18px 0}.pl-form-grid>.form-group,.pl-form-grid>.shiny-panel-conditional>.form-group{margin-bottom:0}.pl-form-grid>.shiny-panel-conditional{min-width:0}.pl-editor-actions{display:flex;align-items:center;flex-wrap:wrap;gap:12px;margin:4px 0 16px}.pl-editor-actions .form-group{margin:0}.pl-table-wrap{overflow:auto;max-height:32rem;max-height:min(32rem,65vh);overscroll-behavior:contain}.pl-table-wrap thead th{position:sticky;top:0;background:var(--pl-surface,#fff);z-index:1}.pl-sidebar-runtime{margin-top:auto;font-size:.8rem;overflow-wrap:anywhere}.pl-sidebar-runtime .pl-status{color:var(--pl-text);margin-top:8px}.pl-sidebar-runtime .pl-status-title{font-size:.85rem}.pl-sidebar:has(.pl-sidebar-runtime){position:sticky;top:0;height:100vh;overflow:auto;align-self:start}.pl-sidebar:has(.pl-sidebar-runtime) .pl-sidebar-note{margin-top:0}.pl-card table{width:100%;margin-bottom:0}.pl-card .table>thead>tr>th{border-bottom:1px solid var(--pl-line);color:var(--pl-muted);font-size:.75rem;text-transform:uppercase;letter-spacing:.04em}.pl-card .table>tbody>tr>td{border-top:1px solid #edf1ee}.btn{border-radius:11px;font-weight:700;border-width:1px;padding:8px 13px}.btn-default{background:#fff;border-color:var(--pl-line);color:var(--pl-text)}.btn.btn-primary{background:var(--pl-brand);border-color:var(--pl-brand);color:#fff}.btn.btn-primary:hover,.btn.btn-primary:focus,.btn.btn-primary:active{background:var(--pl-brand-dark);border-color:var(--pl-brand-dark);color:#fff}.form-group{margin-bottom:0}.checkbox label{font-weight:620;color:var(--pl-text)}pre{background:#14251d;color:#dce9e2;border:0;border-radius:14px;padding:16px}.pl-readonly{border-left:4px solid var(--pl-brand)}.pl-write-boundary{border-left:4px solid var(--pl-accent)}.pl-trade-plot-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.pl-trade-plot-grid .pl-section-title{font-size:16px}.pl-trade-plot-grid .pl-section-copy{font-size:12px;line-height:1.4}.pl-trade-plot{display:block;width:100%;height:280px;background:linear-gradient(#fff,#f8faf9);border:1px solid var(--pl-line);border-radius:12px}.pl-trade-plot-range{display:flex;justify-content:space-between;color:var(--pl-muted);font-size:12px;padding-top:5px}.pl-trade-plot-legend{display:grid;gap:7px;list-style:none;padding:10px 0 0;margin:0;color:var(--pl-muted);font-size:12px;line-height:1.4}.pl-trade-plot-legend li{display:flex;gap:7px;align-items:flex-start}.pl-trade-plot-swatch{width:18px;height:3px;border-radius:99px;flex:0 0 auto;margin-top:7px}.pl-trade-plot-grid details{margin-top:12px;font-size:12px}.pl-trade-plot-grid summary{cursor:pointer;font-weight:700;color:var(--pl-brand-dark)}.pl-market-plot-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.pl-market-plot{display:block;width:100%;height:280px;background:linear-gradient(#fff,#f8faf9);border:1px solid var(--pl-line);border-radius:12px}.pl-market-plot-range{display:flex;justify-content:space-between;color:var(--pl-muted);font-size:12px;padding-top:5px}.pl-market-plot-legend{display:grid;gap:7px;list-style:none;padding:10px 0 0;margin:0;color:var(--pl-muted);font-size:12px;line-height:1.4}.pl-market-plot-legend li{display:flex;gap:7px;align-items:flex-start}.pl-market-plot-swatch{width:18px;height:3px;border-radius:99px;flex:0 0 auto;margin-top:7px}.pl-market-plot-grid details{margin-top:12px;font-size:12px}.pl-market-allocation{display:grid;gap:12px}.pl-market-allocation-row{display:grid;gap:5px}.pl-market-allocation-label{font-size:12px;color:var(--pl-muted)}.pl-market-allocation-row svg{width:100%;height:18px;background:var(--pl-surface-soft);border-radius:99px}",
    # Block links (#540): Aktualisierung, „Läuft gerade“, Einstellungen - hell auf dunkel wie die Navigation.
    ".pl-activity{display:grid;gap:14px;font-size:.8rem;color:#dbe8e1;border-top:1px solid rgba(255,255,255,.14);padding-top:16px}.pl-activity-seg{display:grid;gap:5px}",
    ".pl-activity-head{font-size:.68rem;font-weight:800;text-transform:uppercase;letter-spacing:.09em;color:#bed1c7}.pl-activity-line{line-height:1.4;overflow-wrap:anywhere}",
    ".pl-activity-muted{color:#a9c0b4}.pl-activity-warning{color:#f0d48d}.pl-activity-error{color:#f4b8b8}.pl-activity-live strong{color:#fff}",
    ".pl-activity-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--pl-accent);margin-right:6px;vertical-align:1px;animation:pl-activity-pulse 1.6s ease-in-out infinite}",
    "@keyframes pl-activity-pulse{0%,100%{opacity:1}50%{opacity:.3}}@media(prefers-reduced-motion:reduce){.pl-activity-dot{animation:none}}",
    ".pl-activity-bar{display:block;width:100%;height:6px;border:0;border-radius:99px;background:rgba(255,255,255,.16);overflow:hidden;-webkit-appearance:none;appearance:none}",
    ".pl-activity-bar::-webkit-progress-bar{background:rgba(255,255,255,.16)}.pl-activity-bar::-webkit-progress-value{background:var(--pl-accent)}.pl-activity-bar::-moz-progress-bar{background:var(--pl-accent)}",
    ".pl-activity-actions{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:3px}.pl-activity .btn{padding:5px 11px;font-size:.78rem;border-radius:9px}",
    ".pl-activity .btn-default{background:transparent;color:#fff;border-color:rgba(255,255,255,.38)}.pl-activity .btn-default:hover,.pl-activity .btn-default:focus{background:rgba(255,255,255,.1);color:#fff}",
    ".pl-activity .btn-primary{background:var(--pl-accent);border-color:var(--pl-accent);color:var(--pl-brand-dark)}.pl-activity .btn-primary:hover,.pl-activity .btn-primary:focus{background:#f0d48d;border-color:#f0d48d;color:var(--pl-brand-dark)}",
    ".pl-steps{margin:10px 0 12px}.pl-steps-bar{height:6px;border-radius:3px;background:var(--pl-line,#d9e2dc);overflow:hidden}.pl-steps-fill{height:100%;background:var(--pl-accent,#e8c36a);transition:width .4s}.pl-steps ol{list-style:none;margin:8px 0 0;padding:0}.pl-steps li{display:flex;justify-content:space-between;gap:12px;padding:3px 0}.pl-steps li::before{content:'\\25CB';margin-right:8px;color:var(--pl-muted)}.pl-steps li.pl-step-done::before{content:'\\2713';color:var(--pl-brand,#1f5c45)}.pl-steps li.pl-step-running::before{content:'\\25D4';color:var(--pl-accent-dark,#9a6b00)}.pl-steps .pl-step-label{flex:1}.pl-steps .pl-step-state{color:var(--pl-muted);font-size:.9em}.pl-steps li.pl-step-running .pl-step-label{font-weight:600}",
    ".pl-choice-later .radio.disabled label{color:var(--pl-muted);cursor:not-allowed}.pl-choice-later{margin-top:-6px;margin-bottom:10px}.pl-choice-detail{margin:-4px 0 8px 24px}",
    ".pl-activity .btn.disabled{opacity:.55;cursor:default}.pl-activity .pl-field-hint{color:#dbe8e1}.pl-activity-session{color:#fff}",
    ".pl-activity-running:has(.pl-activity-session:not([hidden])) .pl-activity-idle{display:none}",
    ".pl-sidebar:has(.pl-activity){position:sticky;top:0;height:100vh;overflow:auto;align-self:start}.pl-sidebar:has(.pl-activity) .pl-sidebar-note{margin-top:0}",
    # Umfang je Portfolio (#542): Plaetze, die nur bei veroeffentlichtem Umfang etwas zeigen. Leer nehmen sie keinen Raum ein -
    # ohne Umfang sieht jede Seite aus wie bisher.
    ".pl-scope-slot:empty{display:none}",
    "details{margin:12px 0;border:1px solid var(--pl-line);border-radius:11px;padding:10px 12px}details>summary{display:list-item;list-style:disclosure-closed inside;cursor:pointer;padding:10px;border-radius:8px;background:var(--pl-surface-soft);color:var(--pl-brand-dark);font-weight:700}details[open]>summary{list-style-type:disclosure-open;margin-bottom:12px}details>summary:hover{background:#dcece2}details>summary::marker{color:var(--pl-brand)}",
    # Ein zugeklappter Bereich mit dieser Klasse gilt fuer Shiny als verborgen: Seine
    # Ausgaben werden erst berechnet und uebertragen, wenn er geoeffnet wird. Ohne
    # die Regel haelt Shiny den Inhalt eines zugeklappten <details> fuer sichtbar,
    # weil er nicht ueber display:none ausgeblendet ist - grosse Cash-Tabellen
# gingen so bei jedem Sitzungsstart in den Browser.
    "details.pl-lazy:not([open])>:not(summary){display:none}",
    # Aufklappbare Zelle in einer Tabelle (#529 Punkt 7) und Jahresbereiche (#529 Punkt 4): schlichter als ein Kartenbereich.
    "details.pl-cell-more{margin:0;border:0;padding:0}details.pl-cell-more>summary{padding:0;margin:0;background:transparent;font-weight:600}details.pl-cell-more>summary:hover{background:transparent;text-decoration:underline}details.pl-cell-more[open]>summary{margin-bottom:4px}details.pl-cell-more ul{margin:0;padding-left:18px}",
    "details.pl-year>summary{font-weight:600}details.pl-year>summary strong{font-weight:780}",
    # Notizkaestchen (#507, Variante A, Festlegung 23.10.2026): Lesart und Bedienung aufklappbar unter Titel und Kurzsatz, Vorgabe zu.
    "details.pl-note{margin:10px 0 4px;border:1px solid #e2d6b3;border-radius:10px;padding:0;background:#f8f4e7}",
    "details.pl-note>summary{list-style:none;display:flex;gap:8px;align-items:center;padding:7px 12px;border-radius:10px;background:transparent;color:var(--pl-text);font-weight:600;font-size:13px}",
    "details.pl-note>summary::-webkit-details-marker{display:none}",
    "details.pl-note>summary::before{content:'i';display:inline-grid;place-items:center;width:18px;height:18px;border-radius:50%;border:1.5px solid currentColor;font:italic 600 11px Georgia,serif;flex:0 0 auto}",
    "details.pl-note>summary::after{content:'\\25BE';margin-left:auto;color:var(--pl-muted);transition:transform .15s}",
    "details.pl-note[open]>summary::after{transform:rotate(180deg)}",
    ".pl-note-body{padding:0 12px 10px;font-size:13px;line-height:1.5;color:var(--pl-text)}.pl-note-body p{margin:0 0 6px;max-width:82ch}.pl-note-body p:last-child{margin-bottom:0}",
    "@media(prefers-reduced-motion:reduce){details.pl-note>summary::after{transition:none}}",
    # Lange Vorgaenge (#457): ein Hinweis unten in der Mitte, solange der Server nach einem Klick rechnet.
    ".pl-busy-hint{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:2000;max-width:min(680px,calc(100vw - 32px));background:var(--pl-brand-dark);color:#fff;border-radius:12px;padding:11px 16px;box-shadow:0 12px 30px rgba(0,0,0,.25);font-size:.88rem;line-height:1.4}.pl-busy-hint[hidden]{display:none}.pl-busy-locked{opacity:.6;cursor:progress}.pl-elapsed{font-variant-numeric:tabular-nums}",
    "a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible,.btn:focus-visible{outline:3px solid rgba(217,164,65,.85)!important;outline-offset:2px}",
    "@media(max-width:1080px){.pl-step-grid,.pl-kpi-grid,.pl-trade-plot-grid,.pl-market-plot-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.pl-shell{grid-template-columns:220px minmax(0,1fr)}}",
    "@media(max-width:760px){.pl-sidebar:has(.pl-sidebar-runtime),.pl-sidebar:has(.pl-activity){position:static;height:auto;overflow:visible}.pl-sidebar-runtime{display:block;margin-top:0}.pl-shell{display:block}.pl-sidebar{padding:16px;gap:16px}.pl-nav{grid-template-columns:repeat(4,minmax(0,1fr))}.pl-nav-item{display:flex;justify-content:center;padding:8px}.pl-nav-label-wrap,.pl-sidebar-note{display:none}.pl-main{padding:24px 16px 40px}.pl-topbar{display:block}.pl-actions{justify-content:flex-start;margin-top:18px}.pl-step-grid,.pl-kpi-grid,.pl-trade-plot-grid,.pl-market-plot-grid{grid-template-columns:1fr}.pl-workspace-tabs>.tabbable>.nav-tabs{overflow-x:auto}.pl-deferred-capability{align-items:stretch;flex-direction:column}.pl-form-grid{grid-template-columns:1fr}.pl-card{padding:17px}.pl-title{font-size:2rem}}",
    sep = ""
  )
}

portelyra_navigation <- function(active_app, presentation_context = NULL, project_root = NULL) {
  registry <- portelyra_app_registry(presentation_context, project_root)
  if (!active_app %in% names(registry)) stop("portelyra_ui_active_app_invalid", call. = FALSE)
  shiny::tags$nav(
    class = "pl-nav",
    `aria-label` = "Portelyra Apps",
    lapply(names(registry), function(app_id) {
      item <- registry[[app_id]]
      configured_url <- Sys.getenv(item$url_env, unset = "")
      desktop_ports <- getOption("portelyra.desktop.ports")
      if (!nzchar(configured_url) && !is.null(desktop_ports) && app_id %in% names(desktop_ports)) {
        configured_url <- paste0("http://127.0.0.1:", as.integer(desktop_ports[[app_id]]))
      }
      available <- identical(app_id, active_app) || nzchar(configured_url)
      href <- if (identical(app_id, active_app)) "#main-content" else if (available) configured_url else "#"
      shiny::tags$a(
        class = paste("pl-nav-item", if (!available) "pl-nav-unavailable" else ""),
        href = href,
        `aria-current` = if (identical(app_id, active_app)) "page" else NULL,
        `aria-disabled` = if (!available) "true" else NULL,
        `data-portelyra-nav` = if (available && !identical(app_id, active_app)) "app" else NULL,
        # Welche App (#578): Der Rundgang im Demo erkennt daran die offene App und den Link zur naechsten.
        `data-portelyra-app` = app_id,
        shiny::tags$span(class = "pl-nav-icon", item$short_label, `aria-hidden` = "true"),
        shiny::tags$span(
          class = "pl-nav-label-wrap",
          shiny::tags$span(class = "pl-nav-label", item$label),
          shiny::tags$span(class = "pl-nav-purpose", item$purpose)
        )
      )
    })
  )
}

portelyra_status_panel <- function(title, copy = NULL, tone = c("neutral", "positive", "warning", "error")) {
  tone <- match.arg(tone)
  shiny::div(
    class = paste("pl-status", if (tone == "neutral") "" else paste0("pl-status-", tone)),
    role = if (tone == "error") "alert" else "status",
    shiny::span(class = "pl-status-dot", `aria-hidden` = "true"),
    shiny::div(
      shiny::div(class = "pl-status-title", title),
      if (!is.null(copy)) shiny::div(class = "pl-status-copy", copy)
    )
  )
}

portelyra_kpi_item <- function(label, value, detail = NULL, tone = c("neutral", "positive", "negative")) {
  tone <- match.arg(tone)
  shiny::div(
    class = paste("pl-kpi", paste0("pl-kpi-", tone)),
    shiny::div(class = "pl-kpi-label", label),
    shiny::div(class = "pl-kpi-value", value),
    if (!is.null(detail)) shiny::div(class = "pl-kpi-detail", detail)
  )
}

# Notizkaestchen (#507, Variante A): Hinweise zur Lesart oder Bedienung aufklappbar, Vorgabe zu. Mit 'id' merkt sich der Browser,
# ob es offen war. Warnungen, fehlende Werte ("nicht verfuegbar") und Bestaetigungen vor dem Schreiben gehoeren nie hinein.
portelyra_note_v1 <- function(..., title = "So lesen Sie diese Karte", id = NULL) {
  paragraphs <- lapply(list(...), function(item) if (is.character(item)) shiny::p(item) else item)
  shiny::tags$details(class = "pl-note", `data-note` = id, shiny::tags$summary(title), shiny::div(class = "pl-note-body", paragraphs))
}

portelyra_card <- function(title, ..., copy = NULL, class = NULL, note = NULL, help = NULL) {
  # help = "seite#anker": ein "?" neben dem Titel oeffnet die Hilfe bei diesem Abschnitt (#488, apps/shared/desktop_help_v1.R).
  mark <- if (is.character(help) && length(help) == 1L && nzchar(help)) shiny::tags$a(
    href = "#", class = "pl-help-link pl-help-mark", `data-help-page` = sub("#.*$", "", help),
    `data-help-anchor` = if (grepl("#", help, fixed = TRUE)) sub("^[^#]*#", "", help) else "",
    title = "Hilfe zu diesem Abschnitt", `aria-label` = paste("Hilfe:", title), "?")
  shiny::tags$section(
    class = paste("pl-card", if (is.null(class)) "" else class),
    shiny::div(
      class = "pl-section-head",
      shiny::div(
        shiny::tags$h2(class = "pl-section-title", title, mark),
        if (!is.null(copy)) shiny::p(class = "pl-section-copy", copy)
      )
    ),
    note,
    ...
  )
}

# Feste Kennungen fuer Reiter (#579). Shinys Bootstrap-Barrierefreiheit gibt jedem Reiter-Link ohne Kennung "ui-tab-" plus eine Zufallszahl
# von 1 bis 1000 und prueft keine Dopplung: Bei fuenf Reitern traegt rund jeder hundertste Seitenaufbau zwei gleiche Kennungen (Asset-Center
# 09.10.2026, Einstellungs-Unterreiter 20.11.2026). Einen Reiter mit Kennung laesst die Bibliothek unberuehrt - also bekommt hier jeder
# Reiter-Link ohne Kennung eine feste: <Kennung der Reiterleiste>_tab_<n>, ausserhalb einer Leiste pl_tab_<n>. Fuer jede App ueber
# portelyra_app_shell; das Asset-Center vergibt seine schon vorher (data_asset_center_tab_link_ids_v1), die bleiben.
portelyra_tab_link_ids_v1 <- function(tag) {
  counts <- list()
  walk <- function(node, bar) {
    if (inherits(node, "shiny.tag")) {
      id <- node$attribs[["id"]]
      if (identical(node$name, "ul") && !is.null(id)) bar <- id
      if (identical(node$name, "a") && is.null(id) && (identical(node$attribs[["data-toggle"]], "tab") || identical(node$attribs[["data-bs-toggle"]], "tab"))) {
        prefix <- if (is.null(bar)) "pl" else bar
        counts[[prefix]] <<- if (is.null(counts[[prefix]])) 1L else counts[[prefix]] + 1L
        node$attribs$id <- paste0(prefix, "_tab_", counts[[prefix]])
      }
      node$children <- lapply(node$children, walk, bar = bar)
    } else if (is.list(node) && !inherits(node, "html_dependency") && !is.function(node)) {
      node[] <- lapply(node, walk, bar = bar)
    }
    node
  }
  walk(tag, NULL)
}

portelyra_app_shell <- function(
  active_app, title, description, ..., actions = NULL, capabilities = character(),
  presentation_context = NULL, project_root = NULL, sidebar_status = NULL, sidebar_activity = NULL
) {
  registry <- portelyra_app_registry(presentation_context, project_root)
  if (!active_app %in% names(registry)) stop("portelyra_ui_active_app_invalid", call. = FALSE)
  shiny::fluidPage(
    shiny::tags$head(
      shiny::tags$meta(name = "viewport", content = "width=device-width, initial-scale=1"),
      shiny::tags$meta(name = "referrer", content = "no-referrer"),
      shiny::tags$style(shiny::HTML(portelyra_ui_css())),
      # Englische Standardtexte von Shiny (0.3.4, #578): der Hinweis am Datumsfeld und die Meldung nach dem Hochladen einer Datei.
      shiny::tags$script(shiny::HTML(paste0(
        "(function(){var busy=false;function de(){busy=false;",
        "document.querySelectorAll('.shiny-date-input input[title^=\"Date format\"]').forEach(function(i){i.title='Datum als TT.MM.JJJJ';});",
        "document.querySelectorAll('.shiny-file-input-progress .progress-bar').forEach(function(b){if(b.textContent==='Upload complete'){b.textContent='Hochgeladen';}});}",
        "function soon(){if(!busy){busy=true;window.requestAnimationFrame(de);}}",
        "document.addEventListener('DOMContentLoaded',function(){de();new MutationObserver(soon).observe(document.body,{childList:true,subtree:true,characterData:true});});})();"
      ))),
      shiny::tags$script(shiny::HTML(paste0(
        "document.addEventListener('DOMContentLoaded',function(){",
        "const value=new URLSearchParams(window.location.search).get('launch_token');",
        "if(!value||!/^dls_[a-f0-9]{64}$/.test(value)){return;}",
        "document.querySelectorAll('a[data-portelyra-nav=app]').forEach(function(link){",
        "const target=new URL(link.href);target.searchParams.set('launch_token',value);link.href=target.toString();",
        "});});"
      )))
      ,
      # Oeffnen und Schliessen eines solchen Bereichs als Eingabe <id>_open melden,
      # fuer Inhalte, die der Server erst dann fuellt. Dass die Ausgaben darin
      # sichtbar werden, bemerkt erst Shiny ab 1.9 selbst an der Groessenaenderung; Shiny 1.8 (Ubuntu 24.04) braucht ein
      # 'shown'/'hidden' wie beim Reiterwechsel (Nachprobe rc.440) - fuer jedes details, nicht nur pl-lazy. toggle
      # steigt nicht auf, deshalb in der Einfangphase.
      # Lange Vorgaenge (#457): Waehrend eines Aufrufs ist die Sitzung blockiert und die Seite stumm. Haelt der Server nach einem
      # Klick laenger als 1,5 s an, nennt ein Hinweis den Knopf und zaehlt die Zeit im Browser hoch; der Knopf ist solange gesperrt.
      # Elemente mit data-since (Millisekunden seit 1970) zeigen ihre Laufzeit und zaehlen ebenfalls im Browser weiter - auch dann,
      # wenn der Server gerade nichts sendet.
      shiny::tags$script(shiny::HTML(paste0(
        "(function(){var click=null,current=null,delay=null,ticker=null,box=null;",
        "function fmt(ms){var s=Math.max(0,Math.floor(ms/1000)),m=Math.floor(s/60),r=s%60;return m+':'+(r<10?'0':'')+r;}",
        "function hint(){if(!box){box=document.createElement('div');box.className='pl-busy-hint';box.setAttribute('role','status');box.setAttribute('aria-live','polite');box.hidden=true;document.body.appendChild(box);}return box;}",
        "function rest(ms){if(ms<-60000){return 'dauert länger als der letzte Lauf';}if(ms<60000){return '≈ unter 1 Min. Rest';}var m=Math.round(ms/60000);",
        "return '≈ '+(m<90?m+' Min.':Math.floor(m/60)+':'+(m%60<10?'0':'')+(m%60)+' Std.')+' Rest';}",
        # Der lange Vorgang dieser Seite erscheint auch im Block links unter „Läuft gerade“ (#540).
        "function mirror(text){document.querySelectorAll('.pl-activity-session').forEach(function(el){el.textContent=text||'';el.hidden=!text;});}",
        "function tick(){document.querySelectorAll('[data-since]').forEach(function(el){var t=Number(el.getAttribute('data-since'));if(t>0){el.textContent=fmt(Date.now()-t);}});",
        "document.querySelectorAll('[data-until]').forEach(function(el){var t=Number(el.getAttribute('data-until'));if(t>0){el.textContent=rest(t-Date.now());}});",
        "if(current){hint().textContent='„'+current.label+'“ wird bearbeitet · seit '+fmt(Date.now()-current.at)+' · größere Vorgänge können einige Minuten dauern.';",
        "mirror('„'+current.label+'“ · diese Seite · seit '+fmt(Date.now()-current.at));}}",
        "setInterval(tick,1000);",
        "document.addEventListener('click',function(e){var b=e.target&&e.target.closest?e.target.closest('.action-button'):null;if(!b){return;}",
        "click={el:b,label:(b.textContent||'').trim().slice(0,80),at:Date.now(),locked:!b.disabled};},true);",
        "function idle(){clearTimeout(delay);delay=null;if(box){box.hidden=true;}mirror('');if(current){if(current.locked){current.el.disabled=false;}current.el.classList.remove('pl-busy-locked');current=null;}click=null;}",
        "function busy(){if(!click||Date.now()-click.at>3000||delay||current){return;}var c=click;delay=setTimeout(function(){delay=null;current=c;",
        "if(c.locked){c.el.disabled=true;}c.el.classList.add('pl-busy-locked');hint().hidden=false;tick();},1500);}",
        "document.addEventListener('DOMContentLoaded',function(){if(!window.jQuery){return;}window.jQuery(document).on('shiny:busy',busy).on('shiny:idle',idle);});",
        "})();"
      ))),
      # Notizkaestchen (#507): offen oder zu je Kaestchen im Browser merken; Kaestchen aus Server-Ausgaben werden nachgezogen.
      shiny::tags$script(shiny::HTML(paste0(
        "(function(){function key(d){return 'pl-note:'+d.getAttribute('data-note');}",
        "function restore(root){(root||document).querySelectorAll('details.pl-note[data-note]').forEach(function(d){",
        "try{var v=window.localStorage.getItem(key(d));if(v==='1'){d.open=true;}else if(v==='0'){d.open=false;}}catch(e){}});}",
        "document.addEventListener('toggle',function(event){var d=event.target;if(!d||d.tagName!=='DETAILS'||!d.classList.contains('pl-note')||!d.getAttribute('data-note')){return;}",
        "try{window.localStorage.setItem(key(d),d.open?'1':'0');}catch(e){}},true);",
        "document.addEventListener('DOMContentLoaded',function(){restore();if(window.jQuery){window.jQuery(document).on('shiny:value',function(e){setTimeout(function(){restore(e.target);},0);});}});",
        "})();"
      ))),
      # Datei-Felder auf Deutsch (#488/#490): Shiny beschriftet Knopf und Feld englisch ("Browse...", "No file selected"), wo ein Aufruf
      # nichts Eigenes setzt - auch in Ausgaben, die der Server spaeter fuellt.
      shiny::tags$script(shiny::HTML(paste0(
        "(function(){function de(root){(root||document).querySelectorAll('.btn-file').forEach(function(b){b.childNodes.forEach(function(n){",
        "if(n.nodeType===3&&n.textContent.trim()==='Browse...'){n.textContent='Durchsuchen … ';}});});",
        "(root||document).querySelectorAll('input[placeholder=\"No file selected\"]').forEach(function(i){i.placeholder='Keine Datei gewählt';});}",
        "document.addEventListener('DOMContentLoaded',function(){de();if(window.jQuery){window.jQuery(document).on('shiny:value',function(e){setTimeout(function(){de(e.target);},0);});}});",
        "})();"
      ))),
      shiny::tags$script(shiny::HTML(paste0(
        "document.addEventListener('toggle',function(event){var d=event.target;",
        "if(d&&d.tagName==='DETAILS'&&window.jQuery){window.jQuery(d).trigger(d.open?'shown':'hidden');}",
        "if(!d||d.tagName!=='DETAILS'||!d.classList.contains('pl-lazy')||!d.id){return;}",
        "if(window.Shiny&&window.Shiny.setInputValue){window.Shiny.setInputValue(d.id+'_open',d.open);}",
        "},true);"
      )))
    ),
    shiny::div(
      class = "pl-shell",
      shiny::tags$aside(
        class = "pl-sidebar",
        shiny::div(
          class = "pl-brand",
          shiny::div(class = "pl-brand-mark", "P", `aria-hidden` = "true"),
          shiny::div(
            shiny::div(class = "pl-brand-name", "Portelyra"),
            shiny::div(
              class = "pl-brand-subtitle",
              if (is.null(presentation_context) || is.null(project_root)) "Portfolio klar geführt" else presentation_label_v1("shell.subtitle", presentation_context, project_root, "Portfolio klar geführt")
            )
          )
        ),
        portelyra_navigation(active_app, presentation_context, project_root),
        # Aktualisierung, „Läuft gerade“ und Einstellungen (#540, apps/shared/desktop_activity_v1.R).
        sidebar_activity,
        if (!is.null(sidebar_status)) shiny::div(class = "pl-sidebar-runtime", role = "status", `aria-live` = "polite", sidebar_status),
        shiny::div(
          class = "pl-sidebar-note",
          shiny::strong(registry[[active_app]]$capability),
          shiny::tags$br(),
          if (is.null(presentation_context) || is.null(project_root)) {
            "App-Grenzen bleiben getrennt. Kursabrufe und Vollberechnungen starten nicht durch eine Anzeige."
          } else presentation_label_v1(
            "shell.boundary", presentation_context, project_root,
            "App-Grenzen bleiben getrennt. Kursabrufe und Vollberechnungen starten nicht durch eine Anzeige."
          )
        )
      ),
      shiny::tags$main(
        id = "main-content",
        class = "pl-main",
        tabindex = "-1",
        shiny::tags$header(
          class = "pl-topbar",
          shiny::div(
            shiny::div(class = "pl-eyebrow", paste("Portelyra", registry[[active_app]]$label, sep = " · ")),
            shiny::tags$h1(class = "pl-title", title),
            shiny::p(class = "pl-description", description),
            if (length(capabilities)) shiny::div(
              class = "pl-capabilities",
              lapply(capabilities, function(value) shiny::span(class = "pl-chip", value))
            )
          ),
          if (!is.null(actions)) shiny::div(class = "pl-actions", actions)
        ),
        shiny::div(class = "pl-content", portelyra_tab_link_ids_v1(shiny::tagList(...)))
      )
    )
  )
}

# Einheitliche Darstellung in allen vier Apps (#529 Punkt 8, #490): Datum TT.MM.JJJJ,
# Stückzahlen ohne Nullen am Ende, Beträge mit Einheit.
#
# Reine Darstellung. Die exakten Werte der Artefakte bleiben unberührt; gerundet wird nur
# für die Anzeige, kaufmännisch und auf der Zeichenkette, nicht über Gleitkommazahlen.
# Alle Funktionen arbeiten elementweise; was kein lesbarer Wert ist, bleibt, wie es ist,
# und ein fehlender Wert erscheint als Strich, nie als 0.

.pl_format_text_v1 <- function(value) {
  if (is.null(value) || !length(value)) return(character(0))
  text <- as.character(unlist(value, use.names = FALSE))
  text[is.na(text)] <- ""
  trimws(text)
}

.pl_format_utc_v1 <- function(text) {
  stamp <- sub("\\.[0-9]+Z$", "Z", text)
  parsed <- as.POSIXct(stamp, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  short <- is.na(parsed)
  parsed[short] <- as.POSIXct(stamp[short], format = "%Y-%m-%dT%H:%MZ", tz = "UTC")
  parsed
}

PL_FORMAT_DAY_RE_V1 <- "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
PL_FORMAT_UTC_RE_V1 <- "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}([.][0-9]+)?)?Z$"
PL_FORMAT_DECIMAL_RE_V1 <- "^[+-]?[0-9]+([.][0-9]+)?$"

# Tag als TT.MM.JJJJ. Ein UTC-Zeitpunkt zeigt den Tag in der Ortszeit.
pl_day_v1 <- function(value, fallback = "–") {
  text <- .pl_format_text_v1(value)
  if (!length(text)) return(fallback)
  out <- text
  day <- grepl(PL_FORMAT_DAY_RE_V1, text) & !is.na(suppressWarnings(as.Date(text, format = "%Y-%m-%d")))
  out[day] <- paste0(substr(text[day], 9L, 10L), ".", substr(text[day], 6L, 7L), ".", substr(text[day], 1L, 4L))
  stamp <- grepl(PL_FORMAT_UTC_RE_V1, text)
  if (any(stamp)) {
    parsed <- .pl_format_utc_v1(text[stamp])
    out[stamp] <- ifelse(is.na(parsed), text[stamp], format(parsed, "%d.%m.%Y", tz = ""))
  }
  out[!nzchar(text)] <- fallback
  out
}

# Zeitpunkt als „TT.MM.JJJJ HH:MM“ in Ortszeit; ein reiner Tag bleibt ein Tag.
pl_moment_v1 <- function(value, fallback = "–") {
  text <- .pl_format_text_v1(value)
  if (!length(text)) return(fallback)
  out <- pl_day_v1(text, fallback)
  stamp <- grepl(PL_FORMAT_UTC_RE_V1, text)
  if (any(stamp)) {
    parsed <- .pl_format_utc_v1(text[stamp])
    out[stamp] <- ifelse(is.na(parsed), text[stamp], format(parsed, "%d.%m.%Y %H:%M", tz = ""))
  }
  out
}

.pl_format_group_v1 <- function(integer) {
  vapply(integer, function(value) {
    n <- nchar(value)
    if (n <= 3L) return(value)
    first <- n %% 3L
    if (!first) first <- 3L
    starts <- c(1L, seq.int(first + 1L, n, by = 3L))
    paste(substring(value, starts, c(first, starts[-1L] + 2L)), collapse = ".")
  }, character(1L), USE.NAMES = FALSE)
}

.pl_format_increment_v1 <- function(digits) {
  chars <- strsplit(digits, "", fixed = TRUE)[[1L]]
  carry <- 1L
  for (index in rev(seq_along(chars))) {
    next_value <- as.integer(chars[[index]]) + carry
    chars[[index]] <- as.character(next_value %% 10L)
    carry <- next_value %/% 10L
    if (!carry) break
  }
  paste0(if (carry) "1" else "", paste(chars, collapse = ""))
}

# Eine exakte Dezimalzahl („-1234.5600“) deutsch: auf `digits` Stellen kaufmännisch gerundet
# und aufgefüllt, mit `digits = NULL` alle Stellen ohne Nullen am Ende.
.pl_format_decimal_one_v1 <- function(text, digits = NULL) {
  negative <- startsWith(text, "-")
  unsigned <- sub("^[+-]", "", text)
  parts <- strsplit(unsigned, ".", fixed = TRUE)[[1L]]
  integer <- sub("^0+(?=[0-9])", "", parts[[1L]], perl = TRUE)
  fraction <- if (length(parts) > 1L) parts[[2L]] else ""
  if (is.null(digits)) {
    fraction <- sub("0+$", "", fraction)
  } else {
    if (nchar(fraction) > digits) {
      up <- substr(fraction, digits + 1L, digits + 1L) >= "5"
      fraction <- substr(fraction, 1L, digits)
      if (up) {
        joined <- .pl_format_increment_v1(paste0(integer, fraction))
        integer <- substr(joined, 1L, nchar(joined) - digits)
        fraction <- substr(joined, nchar(joined) - digits + 1L, nchar(joined))
        if (!nzchar(integer)) integer <- "0"
      }
    }
    fraction <- paste0(fraction, strrep("0", max(0L, digits - nchar(fraction))))
  }
  zero <- !grepl("[1-9]", paste0(integer, fraction))
  rendered <- paste0(.pl_format_group_v1(integer), if (nzchar(fraction)) paste0(",", fraction) else "")
  if (negative && !zero) paste0("-", rendered) else rendered
}

.pl_format_numbers_v1 <- function(value, digits, fallback) {
  text <- .pl_format_text_v1(value)
  if (!length(text)) return(fallback)
  out <- text
  plain <- grepl(PL_FORMAT_DECIMAL_RE_V1, text)
  out[plain] <- vapply(text[plain], .pl_format_decimal_one_v1, character(1L), digits = digits, USE.NAMES = FALSE)
  ratio <- grepl("^-?[0-9]+/[1-9][0-9]*$", text)
  if (any(ratio)) {
    out[ratio] <- vapply(strsplit(text[ratio], "/", fixed = TRUE), function(parts) {
      number <- as.numeric(parts[[1L]]) / as.numeric(parts[[2L]])
      .pl_format_decimal_one_v1(formatC(number, format = "f", digits = if (is.null(digits)) 12L else digits + 2L), digits)
    }, character(1L))
  }
  out[!nzchar(text)] <- fallback
  out
}

# Stückzahl: alle Stellen des exakten Werts, ohne Nullen am Ende („25“ statt „25,00000000“).
pl_quantity_v1 <- function(value, fallback = "–") .pl_format_numbers_v1(value, NULL, fallback)

# Zahl ohne Einheit mit festen Nachkommastellen (Kurse, Kennzahlen).
pl_number_v1 <- function(value, digits = 2L, fallback = "–") .pl_format_numbers_v1(value, as.integer(digits), fallback)

# Einheit einer Währung: Euro als „€“, sonst der ISO-Code.
pl_currency_unit_v1 <- function(currency) {
  code <- .pl_format_text_v1(currency)
  ifelse(code == "EUR", "€", code)
}

# Betrag mit Einheit: „1.234,56 €“, „-12,30 USD“. Ohne Währung bleibt es bei der Zahl.
pl_amount_v1 <- function(value, currency = "EUR", digits = 2L, fallback = "–") {
  text <- .pl_format_text_v1(value)
  if (!length(text)) return(fallback)
  number <- .pl_format_numbers_v1(text, as.integer(digits), fallback)
  unit <- rep_len(pl_currency_unit_v1(if (is.null(currency) || !length(currency)) "" else currency), length(text))
  numeric <- grepl(PL_FORMAT_DECIMAL_RE_V1, text) | grepl("^-?[0-9]+/[1-9][0-9]*$", text)
  ifelse(numeric & nzchar(unit), paste(number, unit), number)
}

# Kurs je Stück mit Einheit: auf höchstens `max_digits` Stellen gerundet, mindestens zwei Nachkommastellen, weitere nur,
# wo sie etwas sagen („123,45 €“ statt „123,45000000“, aber „0,00012345 €“).
pl_price_v1 <- function(value, currency = "EUR", fallback = "–", max_digits = 8L) {
  text <- .pl_format_text_v1(value)
  if (!length(text)) return(fallback)
  number <- .pl_format_numbers_v1(text, as.integer(max_digits), fallback)
  number <- sub("(,[0-9]*[1-9])0+$", "\\1", sub(",0+$", "", number))
  plain <- grepl(PL_FORMAT_DECIMAL_RE_V1, text)
  short <- plain & !grepl(",[0-9]{2,}$", number)
  number[short] <- vapply(number[short], function(item) if (grepl(",", item, fixed = TRUE)) paste0(item, "0") else paste0(item, ",00"),
                          character(1L), USE.NAMES = FALSE)
  unit <- rep_len(pl_currency_unit_v1(if (is.null(currency) || !length(currency)) "" else currency), length(text))
  ifelse(plain & nzchar(unit), paste(number, unit), number)
}

# Anteil als Prozent: `value` ist ein Anteil (0.125 → „12,5 %“) oder mit `scale = "percent"` schon in Prozent.
pl_percent_v1 <- function(value, digits = 2L, scale = c("fraction", "percent"), fallback = "–") {
  scale <- match.arg(scale)
  text <- .pl_format_text_v1(value)
  if (!length(text)) return(fallback)
  out <- text
  plain <- grepl(PL_FORMAT_DECIMAL_RE_V1, text)
  if (any(plain)) {
    shifted <- if (identical(scale, "fraction")) vapply(text[plain], .pl_format_shift_v1, character(1L), USE.NAMES = FALSE) else text[plain]
    out[plain] <- paste(vapply(shifted, .pl_format_decimal_one_v1, character(1L), digits = as.integer(digits), USE.NAMES = FALSE), "%")
  }
  out[!nzchar(text)] <- fallback
  out
}

# Dezimalpunkt um zwei Stellen nach rechts (Anteil → Prozent), exakt auf der Zeichenkette.
.pl_format_shift_v1 <- function(text) {
  negative <- startsWith(text, "-")
  parts <- strsplit(sub("^[+-]", "", text), ".", fixed = TRUE)[[1L]]
  fraction <- paste0(if (length(parts) > 1L) parts[[2L]] else "", "00")
  shifted <- paste0(parts[[1L]], substr(fraction, 1L, 2L), if (nchar(fraction) > 2L) paste0(".", substr(fraction, 3L, nchar(fraction))) else "")
  shifted <- sub("[.]$", "", shifted)
  paste0(if (negative) "-" else "", shifted)
}

# Gemeinsame Bezeichnungen für Kennungen, die in mehreren Apps in Tabellen stehen (#490). Unbekannte bleiben als Kennung
# stehen, damit nichts verschwindet; ein fehlender Wert wird zum Strich.
PL_ASSET_TYPE_LABELS_V1 <- c(equity = "Aktie", etf = "ETF", fund = "Fonds", bond = "Anleihe", crypto = "Krypto",
  commodity = "Rohstoff", cash = "Cash", fx = "Devisen", index = "Index", derivative = "Derivat", other = "Sonstiges")
PL_EVENT_TYPE_LABELS_V1 <- c(buy = "Kauf", sell = "Verkauf", dividend = "Dividende", stock_dividend = "Stockdividende",
  reward = "Reward", deposit = "Zugang", withdrawal = "Abgang", transfer = "Transfer", interest = "Zins",
  advance_lump_sum = "Vorabpauschale", split = "Split", fee = "Gebühr")
PL_ACCOUNT_TYPE_LABELS_V1 <- c(securities = "Depot", cash = "Cash-Konto", bank = "Bankkonto", crypto_wallet = "Krypto-Wallet",
  external = "Extern", other = "Sonstiges")
# Kursanbieter (rc.384, #495): Name statt Kennung; der Name steht im Manifest des Plugins, die Anzeige-Apps lesen keine Plugins.
PL_PRICE_PROVIDER_LABELS_V1 <- c(yahoo = "Yahoo Finance", eodhd = "EODHD", twelve_data = "Twelve Data")
PL_RECORD_STATUS_LABELS_V1 <- c(active = "aktiv", archived = "archiviert", retired = "stillgelegt", closed = "geschlossen",
  inactive = "inaktiv", draft = "Entwurf")
pl_price_provider_label_v1 <- function(provider_id, fallback = "–") pl_label_v1(PL_PRICE_PROVIDER_LABELS_V1, provider_id, fallback)
# Was ein Kursanbieter nicht leistet und was der Nutzer deshalb selbst tun muss (rc.394, #495; Festlegung 10.11.2026: Yahoo ist die
# Vorgabe, bei EODHD muss auf das Nachziehen von Splits hingewiesen werden). Gezeigt dort, wo der Anbieter gewaehlt wird.
PL_PRICE_PROVIDER_NOTES_V1 <- c(eodhd = paste(
  "EODHD nur ab einem Datum einsetzen: Kostenlos liefert es etwa ein Jahr Kurse. Die Zuordnung hier anlegen und einrichten, dann unter",
  "„Bewertung über die Zeit“ mit „Ab Datum wechseln“ wirksam machen; die Kurse davor bleiben bei Yahoo. EODHD meldet keine Aktiensplits:",
  "Teilt sich eine Aktie, bitte den Split selbst unter Stammdaten → Kapitalmaßnahmen erfassen, sonst fällt der Kurs am Split-Tag ohne",
  "Hinweis. Kostenlos sind 20 Abrufe am Tag. Im täglichen Zeitlauf ruft Portelyra EODHD erst ab, wenn Sie es unter Kursanbieter →",
  "Kosten freigeben; von Hand holt „Alles aktualisieren“ die Kurse. Yahoo bleibt die Vorgabe."))
# Anbieter, die nur "ab Datum" eingesetzt werden (Festlegung 10.11.2026), mit der Tiefe ihrer kostenlosen Historie in Tagen. Mit
# "Ganze Historie neu" blieben alle aelteren Tage ohne Kurs - die alte Reihe springt nicht ein.
PL_PRICE_PROVIDERS_FROM_DATE_ONLY_V1 <- c(eodhd = 365L)
# Yahoo als Standardanbieter fuer abgerufene Marktpreise (Festlegung 10.11.2026): Wo Kurse abgerufen statt selbst gesetzt werden, soll
# klar sein, dass Yahoo auch Wechselkurse und Momentkurse liefert und weitere Anbieter nur Tageskurse einzelner Assets.
PL_PRICE_PROVIDER_DEFAULT_NOTE_V1 <- paste(
  "Yahoo Finance ist der Standardanbieter für abgerufene Marktpreise: Es liefert die Tageskurse, die Wechselkurse für die Umrechnung",
  "in Euro und die Momentkurse der Momentaufnahme. Weitere Anbieter wie EODHD liefern nur Tageskurse für einzelne Assets;",
  "Wechselkurse und Momentkurse kommen weiter von Yahoo. Ohne Abruf bewerten Sie mit eigenen Kursen bzw. Trade-Kursen oder nur",
  "über Transaktionen.")
# Anbieter ohne Momentkurs (Manifest ohne "quote"; ein Test gleicht die Liste mit den Plugins ab). Die Momentaufnahme zeigt fuer
# ihre Positionen den letzten Tagesschluss - gewollt, aber erkennbar.
PL_PRICE_PROVIDERS_WITHOUT_QUOTE_V1 <- c("eodhd")
pl_price_provider_note_v1 <- function(provider_id) {
  id <- .pl_format_text_v1(provider_id)
  if (is.null(id) || !id %in% names(PL_PRICE_PROVIDER_NOTES_V1)) NULL else unname(PL_PRICE_PROVIDER_NOTES_V1[[id]])
}
# Kursreihen, die nur naehern (rc.388, #495): bei Yahoo sind Symbole auf "=F" Terminkontrakte (Gold GC=F, Silber SI=F, Platin PL=F).
# Physische Ware handelt mit Aufgeld und Spanne; die Anbieter-Spalte sagt es, eine Fussnote erklaert es.
PL_PRICE_SERIES_FUTURE_PATTERNS_V1 <- c(yahoo = "=F$")
PL_PRICE_SERIES_FUTURE_NOTE_V1 <- paste(
  "Future-Näherung: Kurs des laufenden Terminkontrakts an der Börse, in die Portfoliowährung umgerechnet. Physische Ware wie",
  "Barren und Münzen wird mit Aufgeld und Spanne gehandelt; der Wert zeigt den Metall- bzw. Warenwert ohne Aufgeld.")
pl_price_series_is_future_v1 <- function(provider_id, symbol) {
  provider <- .pl_format_text_v1(provider_id)
  text <- .pl_format_text_v1(symbol)
  if (length(provider) != 1L || length(text) != 1L || !provider %in% names(PL_PRICE_SERIES_FUTURE_PATTERNS_V1)) return(FALSE)
  grepl(PL_PRICE_SERIES_FUTURE_PATTERNS_V1[[provider]], text)
}
pl_price_provider_series_label_v1 <- function(provider_id, symbol, fallback = "–") {
  label <- pl_price_provider_label_v1(provider_id, fallback)
  if (pl_price_series_is_future_v1(provider_id, symbol)) paste0(label, " · Future-Näherung") else label
}
pl_price_series_future_note_v1 <- function(flags) if (any(as.logical(flags))) shiny::p(class = "pl-field-hint", PL_PRICE_SERIES_FUTURE_NOTE_V1) else NULL
pl_label_v1 <- function(labels, value, fallback = "–") {
  text <- .pl_format_text_v1(value)
  if (!length(text)) return(fallback)
  out <- ifelse(text %in% names(labels), unname(labels[text]), text)
  out[!nzchar(text)] <- fallback
  out
}

# Tabelle aus Zeilen, deren Zellen Text oder ein Baustein sind (etwa eine aufklappbare Zelle, #529 Punkt 7). Text wird
# maskiert; das Aussehen ist das von renderTable.
pl_table_v1 <- function(columns, rows) {
  shiny::tags$table(class = "table shiny-table table-striped spacing-xs", style = "width:100%",
    shiny::tags$thead(shiny::tags$tr(lapply(columns, shiny::tags$th))),
    shiny::tags$tbody(lapply(rows, function(row) shiny::tags$tr(lapply(row, shiny::tags$td)))))
}
pl_frame_table_v1 <- function(frame) {
  if (!is.data.frame(frame) || !ncol(frame)) return(NULL)
  pl_table_v1(names(frame), lapply(seq_len(nrow(frame)), function(index) lapply(frame, function(column) as.character(column[[index]]))))
}
# Aufklappbare Zelle: Zusammenfassung sichtbar, die Liste darunter erst auf Klick.
pl_cell_more_v1 <- function(summary, items) {
  shiny::tags$details(class = "pl-cell-more", shiny::tags$summary(summary), shiny::tags$ul(lapply(items, shiny::tags$li)))
}
# Je Jahr ein Bereich mit dem Jahr als Ueberschrift, das neueste offen, die aelteren zugeklappt (#529 Punkt 4, #531 Punkt 3).
# `groups`: Liste aus list(title, summary, body), neuestes zuerst.
pl_year_groups_v1 <- function(groups) {
  shiny::tagList(lapply(seq_along(groups), function(index) {
    group <- groups[[index]]
    summary <- if (is.character(group$summary) && length(group$summary) == 1L && nzchar(group$summary)) paste0(" · ", group$summary) else ""
    shiny::tags$details(class = "pl-year", open = if (index == 1L) NA else NULL,
      shiny::tags$summary(shiny::tags$strong(group$title), summary), group$body)
  }))
}

# Fehlertexte (#490): je Code ein deutscher Satz mit Grund und naechstem Schritt, der Code folgt in Klammern. Gesucht wird erst der
# genaue Code, dann die laengste passende Endung an einer Wortgrenze ("_"). Interne Pruefschritte (kind = internal) und Unbekanntes
# nennen den Fehlercode mit der Bitte, ihn zu melden. Die Abdeckung prueft tests/contracts/test_ui_error_texts_v1.R.
PL_ERROR_TEXTS_V1 <- utils::read.csv(text = r"---(match,pattern,kind,reason,next_step
exact,activity_draft_source_superseded,user,Der Entwurf gehört zu einem älteren Stand des Buchungsbestands.,Die Entwürfe neu laden und den Entwurf neu erstellen.
exact,asset_activity_correction_predecessor_missing,user,Die gewählte Buchung ist nicht mehr die aktuelle.,Die Liste neu laden und die Buchung erneut wählen.
exact,asset_activity_csv_mapping_required,user,Für ein Asset oder Konto der Datei fehlt die Zuordnung.,Jedem Asset und Konto der Datei ein vorhandenes zuordnen.
exact,asset_activity_csv_row_blocked,user,"Eine Zeile verletzt Reihenfolge, Währung oder Buchungsregeln.",Die angezeigte Zeile in der Datei korrigieren und erneut einlesen.
exact,asset_activity_state_source_stale,user,Der FIFO-Stand ist nicht mehr aktuell.,„Alles aktualisieren“ starten; es schreibt den FIFO-Stand fort.
exact,asset_grouping_asset_scope_invalid,user,Das Asset gehört nicht zu diesem Portfolio.,Ein Asset dieses Portfolios wählen.
exact,asset_grouping_cycle_detected,user,Die Gruppe würde sich selbst enthalten.,Eine andere übergeordnete Gruppe wählen.
exact,asset_grouping_effective_order_invalid,user,Das Datum „Gültig ab“ passt nicht zu den vorhandenen Zuordnungen.,Ein späteres Datum wählen.
exact,asset_grouping_group_not_empty,user,Die Gruppe enthält noch Assets.,"Erst die Zuordnungen entfernen, dann die Gruppe stilllegen."
exact,asset_grouping_group_not_leaf,user,Diese Gruppenzuordnung ist so nicht möglich.,Die übergeordnete Gruppe prüfen.
exact,asset_grouping_parent_invalid,user,Diese Gruppenzuordnung ist so nicht möglich.,Die übergeordnete Gruppe prüfen.
exact,asset_grouping_reference_role_invalid,user,Die gewählte Referenz passt nicht zu dieser Rolle.,Eine passende Referenz wählen.
exact,asset_grouping_scheme_not_empty,user,Die Einteilung enthält noch Gruppen.,"Erst die Gruppen stilllegen, dann die Einteilung."
exact,asset_quantity_scale_no_increase,user,Die Mengengenauigkeit des Assets reicht schon aus.,Die Buchung ohne Anhebung fortsetzen.
exact,asset_quantity_scale_required_exceeds_limit,user,Die Menge braucht mehr als 24 Nachkommastellen.,Die Menge prüfen und kürzen.
exact,cash_coverage_complete_opening_required,user,Für „vollständig abgestimmt“ fehlt der Anfangssaldo.,Den Anfangssaldo eintragen.
exact,cash_coverage_complete_reconciliation_required,user,Für „vollständig abgestimmt“ fehlt der Abstimmungsnachweis.,Den Saldo laut Auszug prüfen (Karte „Saldo prüfen“).
exact,cash_coverage_flow_classification_invalid,user,Eine Angabe zum Cash-Zeitraum ist ungültig.,"Art, Betrag und Datum prüfen."
exact,cash_coverage_income_invalid,user,Eine Angabe zum Cash-Zeitraum ist ungültig.,"Art, Betrag und Datum prüfen."
exact,cash_coverage_mode_invalid,user,Die gewählte Art der Abdeckung ist hier nicht möglich.,Eine andere Art wählen oder den Stand des Kontos prüfen.
exact,cash_coverage_transfer_invalid,user,Eine Angabe zum Cash-Zeitraum ist ungültig.,"Art, Betrag und Datum prüfen."
exact,cash_statement_multiple_accounts,user,Der Export nennt mehrere Konten.,Je Konto einen eigenen Export erstellen und einlesen.
exact,cash_statement_source_invalid,user,Die Datei ließ sich nicht als Auszug lesen.,Datei und gewähltes Institut prüfen.
exact,catalog_command_dependency_active,user,"Daran hängen noch aktive Einträge, etwa Konten oder Buchungen.",Erst die abhängigen Einträge stilllegen.
exact,desktop_asset_activity_canonical_changed,user,Die Stammdaten haben sich geändert; der Buchungsbestand muss angeglichen werden.,„Abschlussplan prüfen“ ausführen oder „Alles aktualisieren“ starten; beides gleicht an.
exact,desktop_cash_coverage_mode_invalid,user,Die gewählte Art der Abdeckung ist hier nicht möglich.,Eine andere Art wählen oder den Stand des Kontos prüfen.
exact,desktop_cash_coverage_predecessor_missing,user,Der gewählte Zeitraum ist nicht mehr der aktuelle.,Die Liste neu laden und den Zeitraum erneut wählen.
exact,desktop_catalog_isin_invalid,user,Die ISIN ist ungültig.,Die zwölfstellige ISIN prüfen.
exact,desktop_catalog_isin_taken,user,Diese ISIN gehört schon zu einem anderen Asset.,Das vorhandene Asset verwenden.
exact,desktop_market_fx_batch_calendar_saved_profile_required,user,"Für die Übergabe des Kalenders fehlen gespeicherte, geprüfte Profile.",Erst die Profile prüfen und speichern.
exact,desktop_market_fx_batch_calendar_staged_not_published,user,Ein vorheriger Abruf ist noch nicht übernommen.,"Ihn zuerst übernehmen, dann erneut abrufen."
exact,desktop_market_fx_batch_selection_blocked,user,Gewählte Bereiche warten nicht mehr oder können gerade nicht starten.,Die Liste neu laden und erneut wählen.
exact,desktop_market_history_review_fetch_interrupted,user,Der Kursabruf wurde unterbrochen.,Den Abruf erneut starten.
exact,desktop_market_history_review_rejected,user,Der geprüfte Vorschlag wurde verworfen.,Bei Bedarf neu abrufen.
exact,desktop_market_history_review_source_not_listed,user,Diese Quelle ist für das Asset nicht eingerichtet.,Die Kurszuordnung prüfen.
exact,desktop_onboarding_repository_not_empty,user,Der Datenraum ist nicht leer; die erste Einrichtung braucht einen leeren.,Den vorhandenen Datenraum weiter verwenden.
exact,desktop_onboarding_repository_uninitialized,user,Der Datenraum ist noch nicht angelegt.,Die Einrichtung abschließen.
exact,desktop_product_cli_input_invalid,user,Der Befehl oder eine Option ist ungültig.,Befehl und Optionen prüfen.
exact,desktop_product_dependency_missing,user,Ein benötigtes Programm oder R-Paket fehlt.,"Die Installation von Portelyra erneut ausführen; bleibt der Fehler, bitte melden."
exact,desktop_product_home_inside_project,user,Der Datenordner liegt im Programmordner.,Einen Datenordner außerhalb des Programmordners wählen.
exact,desktop_product_install_failed,user,Die Installation ist gescheitert.,"Die Ausgabe des Befehls prüfen; bleibt der Fehler, bitte melden."
exact,desktop_product_not_initialized,user,Portelyra ist hier noch nicht eingerichtet.,Die Einrichtung starten.
exact,desktop_product_permissions_invalid,user,Die Zugriffsrechte des Datenordners sind zu offen.,Den Ordner nur für das eigene Benutzerkonto freigeben.
exact,desktop_product_platform_unsupported,user,Portelyra läuft nur unter Linux.,Ein unterstütztes Linux verwenden.
exact,desktop_product_rollback_incompatible,user,Die ältere Version kann den heutigen Datenstand nicht sicher schreiben.,Bei der aktuellen Version bleiben.
exact,desktop_product_update_busy,user,"Portelyra arbeitet gerade, etwa an einer Buchung oder einem Import.",Abwarten und erneut versuchen.
exact,desktop_product_update_preflight_failed,user,Der neue Stand startet nicht.,Mit rollback zum bisherigen Stand zurückkehren und den Fehler melden.
exact,desktop_product_update_stop_failed,user,Portelyra hat sich nicht rechtzeitig beendet; nichts wurde eingespielt.,Portelyra beenden und das Update erneut starten.
exact,desktop_protection_already_enabled,user,Der Passwortschutz ist schon eingeschaltet.,Nichts weiter zu tun.
exact,desktop_protection_backup_required,user,Vor dem Löschen des Klartexts ist ein Backup im verschlüsselten Ordner nötig.,Erst ein Backup anlegen (Daten → „Einstellungen“ → „Sicherheit und Speicher“ → „Backups“).
exact,desktop_protection_backups_absent,user,Es gibt keinen verschlüsselten Backup-Ordner in diesem Benutzerkonto.,Den Passwortschutz prüfen.
exact,desktop_protection_backups_folder_exists,user,"Es gibt schon einen verschlüsselten Backup-Ordner, etwa von einer früheren Einrichtung.","Den vorhandenen Ordner prüfen; die Einrichtung bietet an, wie es weitergeht."
exact,desktop_protection_backups_in_use,user,Der verschlüsselte Backup-Ordner ist gerade von einer anderen Portelyra-Installation geöffnet.,"Die andere Installation beenden, dann erneut versuchen."
exact,desktop_protection_busy,user,Ein verschlüsselter Ordner ist schon eingehängt.,"Die andere Portelyra-Sitzung beenden, dann erneut versuchen."
exact,desktop_protection_copy_mismatch,user,Die verschlüsselte Kopie stimmt nicht mit dem Original überein; nichts wurde gelöscht.,"Den Vorgang erneut starten; bleibt der Fehler, bitte melden."
exact,desktop_protection_disk_space,user,Zum Erneuern des Schlüssels fehlt Platz: Alte und neue Ordner liegen zeitweise nebeneinander.,"Platz schaffen, dann erneut versuchen."
exact,desktop_protection_keyring_stale,user,Das Passwort im Schlüsselbund passt nicht mehr.,Auf der Startseite entsperren und „Mit der Anmeldung entsperren“ neu einschalten.
exact,desktop_protection_keyring_unavailable,user,Der Schlüsselbund ist nicht erreichbar oder enthält das Passwort nicht.,Auf der Startseite mit dem Passwort entsperren.
exact,desktop_protection_mount_failed,user,Der verschlüsselte Ordner ließ sich nicht einhängen.,"Portelyra neu starten; bleibt der Fehler, bitte melden."
exact,desktop_protection_no_data_space,user,Es gibt noch keinen Datenraum.,Zuerst die App „Daten“ einmal öffnen und den Datenraum anlegen.
exact,desktop_protection_not_enabled,user,Der Passwortschutz ist nicht eingeschaltet.,Ihn bei Bedarf in den Einstellungen einschalten.
exact,desktop_protection_password_after_sleep,user,Nach dem Ruhezustand wird mit dem Passwort entsperrt.,Das Passwort eingeben; danach gilt auch der Schlüsselbund wieder.
exact,desktop_protection_password_mismatch,user,Die beiden Passwörter stimmen nicht überein.,Beide Felder gleich ausfüllen.
exact,desktop_protection_password_too_short,user,Das Passwort ist zu kurz (mindestens 10 Zeichen).,Ein längeres Passwort wählen.
exact,desktop_protection_password_wrong,user,Das Passwort stimmt nicht.,Das Passwort erneut eingeben.
exact,desktop_protection_recovery_key_invalid,user,Der Wiederherstellungsschlüssel stimmt nicht.,Den Schlüssel erneut eingeben.
exact,desktop_protection_rekey_pending,user,Das Erneuern des Schlüssels ist angefordert.,Auf der Startseite entsperren; dabei wird der Schlüssel erneuert.
exact,desktop_protection_runtime_dir_invalid,user,Der Ordner für die entsperrte Ansicht (/run/user/…) ist nicht nutzbar.,"Ab- und wieder anmelden, dann erneut versuchen."
exact,desktop_protection_tool_missing,user,Für den Passwortschutz fehlt das Programm gocryptfs.,"gocryptfs über die Paketverwaltung installieren, dann erneut versuchen."
exact,desktop_protection_unreadable_none,user,"Es gibt keinen unlesbaren Eintrag mehr.","Nichts weiter zu tun."
exact,desktop_protection_unreadable_not_quarantinable,user,"Darunter ist ein unlesbarer Eintrag, der weder ein abgeleiteter Lauf noch ein unfertiger Zwischenstand ist; ihn nimmt Portelyra nicht in Quarantäne.","Nichts selbst verschieben oder löschen; den Pfad melden (Handbuch „Backups“, „Unlesbarer Eintrag“)."
exact,desktop_protection_unreadable_request_invalid,user,"Der Auftrag für die Quarantäne war nicht lesbar und wurde verworfen.","Erneut prüfen und bestätigen."
exact,desktop_protection_unreadable_stale,user,"Der Befund hat sich seit der Vorschau geändert.","Erneut „Prüfen“ klicken und die neue Vorschau bestätigen."
exact,desktop_protection_wait,user,Nach mehreren falschen Eingaben ist eine kurze Pause nötig.,"Kurz warten, dann erneut versuchen."
exact,desktop_release_acceptance_artifact_missing,user,Für die Abnahme fehlt ein abgeschlossener Abschluss.,Erst „Alles aktualisieren“ ausführen.
exact,desktop_release_backup_conflict,user,Am Ziel des Backups liegt schon etwas.,Einen anderen Ordner wählen oder in einer Minute erneut versuchen.
exact,desktop_release_backup_source_changed,user,Während des Backups hat sich der Datenraum geändert.,"Warten, bis kein Vorgang mehr läuft, dann das Backup erneut starten."
exact,desktop_release_backup_target_unprotected,user,"Mit Passwortschutz muss das Backup im entsperrten, verschlüsselten Backup-Ordner liegen.",Portelyra entsperren und den vorgesehenen Backup-Ordner verwenden.
exact,desktop_release_permissions_invalid,user,Die Zugriffsrechte des Ordners sind zu offen.,Den Ordner nur für das eigene Benutzerkonto freigeben.
exact,desktop_release_signature_invalid,user,Die Signatur des Update-Archivs passt nicht zu seinem Inhalt; das Archiv wurde verändert.,"Nicht einspielen, das Archiv von der Quelle neu beziehen."
exact,desktop_release_signature_untrusted,user,Das Update-Archiv ist nicht mit einem Schlüssel von Portelyra signiert.,"Nicht einspielen, das Archiv nur von der Portelyra-Quelle beziehen."
exact,desktop_release_update_entry_untrusted,user,Ein Update muss aus dem installierten Portelyra gestartet werden.,Den Befehl wie im Handbuch „Signaturschlüssel“ beschrieben aus dem installierten Portelyra aufrufen.
exact,desktop_release_signing_copy_unconfirmed,internal,Die Sicherungskopie des Signaturschlüssels ist nicht bestätigt.,
exact,desktop_release_signing_declined,internal,Die Signatur wurde im Bestätigungsfenster abgelehnt oder nicht rechtzeitig bestätigt.,
exact,desktop_release_signing_failed,internal,Das Signieren des Release ist fehlgeschlagen.,
exact,desktop_release_signing_key_not_loaded,internal,Der Signaturschlüssel ist im Signatur-Agenten nicht geladen.,
exact,desktop_release_signing_key_untrusted,internal,Der eingerichtete Signaturschlüssel steht nicht in der Vertrauensliste.,
exact,desktop_release_signing_not_set_up,internal,Es ist kein Signaturschlüssel eingerichtet.,
exact,desktop_release_signing_required_for_public_release,internal,Ein öffentliches Release (Version ohne -rc) wird nur signiert gebaut; zuerst den Schlüssel einrichten.,
exact,desktop_release_release_conflict,user,"Ein Release-Archiv mit diesem Namen, aber anderer Version gibt es schon.",Einen anderen Dateinamen wählen.
exact,desktop_release_restore_conflict,user,Am Ziel des Wiederherstellens liegt schon etwas.,Einen leeren oder neuen Ordner wählen.
exact,desktop_release_restore_context_mismatch,user,Das Backup gehört zu einem anderen Datenraum.,Ein Backup dieses Datenraums wählen oder in ein frisches Home wiederherstellen.
exact,desktop_release_restore_newer_version,user,Das Backup stammt aus einer neueren Portelyra-Version.,"Erst Portelyra aktualisieren, dann wiederherstellen."
exact,desktop_release_restore_target_not_empty,user,Das Ziel für das Wiederherstellen ist nicht leer.,Einen leeren oder neuen Ordner wählen.
exact,desktop_release_session_invalid,user,Portelyra läuft gerade oder ein anderer Vorgang hält den Datenraum.,"Portelyra beenden, dann erneut versuchen."
exact,desktop_release_source_unreadable,user,"Ein Eintrag im Datenraum lässt sich nicht lesen (Ein-/Ausgabefehler), meist nach einem Neustart mitten in einem Lauf.","Im Handbuch „Backups“ den Abschnitt „Unlesbarer Eintrag“ befolgen, dann erneut versuchen."
exact,desktop_release_source_unsettled,user,Im Datenraum ist ein Vorgang nicht abgeschlossen.,"Portelyra starten, den Vorgang abschließen lassen, dann erneut versuchen."
exact,desktop_run_center_last_run_unreadable,user,Der letzte Abschluss lässt sich nicht lesen.,"Einen neuen Abschluss starten, etwa mit „Alles aktualisieren“."
exact,desktop_run_center_market_valuation_changed,user,Die Bewertung hat sich seit dem Abschlussplan geändert.,Den Abschlussplan neu prüfen und erneut bestätigen.
exact,desktop_run_center_no_resumable_job,user,Es gibt keinen unterbrochenen Abschluss zum Fortsetzen.,Einen neuen Abschluss starten.
exact,desktop_setup_folder_invalid,user,"Der Ordner taugt nicht als Belegordner: Er muss vorhanden sein, außerhalb des Datenbestands liegen und darf keine Verknüpfung sein.","Einen anderen Ordner wählen oder das Feld leer lassen und den Belegordner später im Eingang festlegen."
exact,desktop_workflow_analysis_blocked,user,Der Abschluss hielt bei der Analyse an.,"„Alles aktualisieren“ erneut starten; bleibt der Fehler, bitte melden."
exact,desktop_workflow_fifo_blocked,user,Der Abschluss hielt bei FIFO an: Die Buchungen ergeben keinen gültigen FIFO-Stand.,"Die Buchungen prüfen (etwa ein Verkauf ohne vorherigen Bestand), dann „Alles aktualisieren“."
exact,desktop_workflow_full_rebuild_required,user,Vor dem ersten fortschreibenden Abschluss braucht es einen vollständigen Neuaufbau.,Den Abschluss einmal als „Vollständiger Neuaufbau“ ausführen.
exact,desktop_workflow_fx_blocked,user,Der Abschluss hielt bei den Devisenkursen an.,"Devisenkurse abrufen, dann „Alles aktualisieren“."
exact,desktop_workflow_grouping_blocked,user,Der Abschluss hielt bei der Gruppierung an.,"Die eigenen Gruppen prüfen, dann „Alles aktualisieren“."
exact,desktop_workflow_market_blocked,user,Der Abschluss hielt bei den Kursen an.,"Kurse abrufen oder eintragen, dann „Alles aktualisieren“."
exact,desktop_workflow_publication_blocked,user,Der Abschluss hielt beim Veröffentlichen an.,"„Alles aktualisieren“ erneut starten; bleibt der Fehler, bitte melden."
exact,desktop_workflow_tax_blocked,user,Der Abschluss hielt bei der Steuer an.,"Regelmodul und steuerliche Einordnung prüfen, dann „Alles aktualisieren“."
exact,desktop_workflow_valuation_blocked,user,Der Abschluss hielt bei der Bewertung an.,"Kurse und Bewertungsart der Assets prüfen, dann „Alles aktualisieren“."
exact,display_no_latest,user,Es gibt noch keinen veröffentlichten Stand.,"In der App „Daten“ „Alles aktualisieren“ ausführen, dann neu lesen."
exact,manual_market_coverage_extra,user,Es gibt einen Kurs für ein Asset ohne offenen Bestand.,Den überzähligen Kurs entfernen.
exact,manual_market_coverage_missing,user,Für eine offene Position fehlt ein Kurs.,Den Kurs abrufen oder eintragen.
exact,plugin_signature_missing,user,Das Paket trägt keine Portelyra-Signatur.,Nur Pakete mit Portelyra-Signatur installieren.
exact,plugin_signature_untrusted,user,"Die Signatur stammt von keinem Schlüssel der Vertrauensliste, oder der Schlüssel ist noch nicht eingerichtet.","Nur Pakete von Portelyra verwenden; bis der Schlüssel eingerichtet ist, lässt sich nichts installieren."
exact,plugin_signature_invalid,user,Die Signatur passt nicht zum Inhalt des Pakets; es wurde nach dem Signieren verändert.,Das Paket erneut von der Quelle beziehen.
exact,plugin_signature_tool_missing,user,"Die Signatur lässt sich nicht prüfen, weil ssh-keygen fehlt.",Das Paket openssh-client installieren und erneut prüfen.
exact,tax_module_install_input_invalid,user,Die gewählte Datei ist keine lesbare ZIP-Datei oder zu groß.,Die ZIP-Datei des Steuermoduls wählen.
exact,tax_module_package_invalid,user,Die Datei hat nicht den Aufbau eines Steuermodul-Pakets.,Das Paket erneut von der Quelle beziehen.
exact,tax_module_package_file_mismatch,user,Eine Datei des Pakets weicht von ihrer signierten Prüfsumme ab oder fehlt.,Das Paket erneut von der Quelle beziehen.
exact,tax_module_unsupported,user,Mit diesem Steuermodul kann diese Portelyra-Version noch nicht rechnen.,Portelyra aktualisieren oder ein passendes Modul wählen.
exact,tax_module_manifest_invalid,user,Die Beschreibung des Moduls ist ungültig oder passt nicht zum Paket.,Das Paket erneut von der Quelle beziehen.
exact,tax_module_values_inconsistent,user,"Die Jahreswerte, mit denen das Modul rechnet, stimmen nicht mit seiner Tabelle überein.",Dieses Paket nicht verwenden und es melden.
exact,tax_module_selftest_failed,user,Die Testfälle des Pakets rechnen anders als angegeben.,Dieses Paket nicht verwenden und es melden.
exact,tax_module_already_installed,user,Diese Fassung ist schon installiert oder mitgeliefert.,Sie steht im Kasten „Regelmodul“ zur Übernahme bereit.
exact,tax_module_confirmation_required,user,Installiert wird nur mit Ihrer Bestätigung.,Das Häkchen setzen und erneut installieren.
exact,tax_module_preview_stale,user,Das Paket oder der Stand hat sich seit der Prüfung geändert.,Das Paket erneut prüfen.
exact,tax_module_install_store_invalid,user,Der Bereich der Steuermodule im Datenraum ist nicht schreibbar.,"Den Datenraum entsperren, dann erneut versuchen."
exact,plugin_credentials_check_unsupported,user,Das Plugin kann einen Zugang nicht selbst prüfen.,Den Zugang mit einem Abruf testen.
exact,plugin_credentials_choice_required,user,"Für das Plugin gibt es mehrere Zugänge, aber keine Wahl.",Unter Daten → „Einstellungen“ → „Plugins und Zugänge“ → „Zugänge“ einen Zugang wählen.
exact,plugin_credentials_fields_changed,user,Das Plugin verlangt andere Felder als eingetragen.,Den Zugang mit den neuen Feldern neu eintragen.
exact,plugin_credentials_hosts_unconfirmed,user,"Das Plugin will eine Adresse ansprechen, die für den Zugang nicht bestätigt ist.",Den Zugang mit den neuen Adressen erneut bestätigen.
exact,plugin_credentials_keyring_failed,user,Der Schlüsselbund hat das Ablegen oder Entfernen abgelehnt.,"Den Schlüsselbund entsperren, dann erneut versuchen."
exact,plugin_credentials_missing,user,"Für das Plugin ist kein Zugang eingetragen, oder sein Wert fehlt im Schlüsselbund.",Den Zugang unter Daten → „Einstellungen“ → „Plugins und Zugänge“ → „Zugänge“ eintragen.
exact,plugin_credentials_other_location,user,"Der Zugang wurde an einem anderen Ort eingetragen, etwa vor einem Umzug des Datenraums.",Den Zugang hier neu eintragen.
exact,plugin_credentials_plugin_unavailable,user,Das Plugin ist nicht geladen oder braucht keinen Zugang.,"Prüfen, ob das Plugin aktiviert ist."
exact,portfolio_csv_bundle_invalid,user,Das Austauschpaket ist beschädigt oder unvollständig.,Das Paket neu exportieren.
exact,portfolio_csv_handoff_dependency_missing,user,"Ein vorausgehender Schritt fehlt, etwa die Übernahme der Stammdaten.",Die Übergaben in der angezeigten Reihenfolge ausführen.
exact,portfolio_snapshot_v2_market_coverage_invalid,user,Kurse und Assets mit Bestand passen nicht zusammen.,"Kurse abrufen oder eintragen, dann den Snapshot erneut erstellen."
exact,portfolio_snapshot_v2_non_cash_inventory_negative,user,Ein Bestand wäre negativ.,Die Buchungen prüfen: Meist fehlt ein Kauf oder Eingang vor einem Verkauf.
exact,price_provider_failed,user,Das Kursanbieter-Plugin ist abgestürzt oder hat ein unlesbares Ergebnis geliefert.,"Später erneut versuchen; bleibt der Fehler, bitte melden."
exact,price_provider_operation_unsupported,user,Das Plugin bietet diese Funktion nicht an.,Einen anderen Kursanbieter wählen.
exact,price_provider_response_too_large,user,Die Antwort des Kursanbieters ist zu groß.,Einen kürzeren Zeitraum abrufen.
exact,price_provider_unavailable,user,Für diesen Kursanbieter gibt es kein gültiges Plugin.,"Prüfen, ob das Plugin installiert und aktiviert ist."
exact,securities_statement_source_invalid,user,Die Datei ließ sich nicht als Auszug lesen.,Datei und gewähltes Institut prüfen.
exact,statement_import_mapping_duplicate_invalid,user,Eine Zeile oder Zuordnung ist doppelt.,Die doppelte Zuordnung entfernen.
exact,statement_import_mapping_quantity_invalid,user,Die Gebühr des Rewards ist nicht kleiner als seine Menge.,Gebühr und Menge prüfen.
exact,statement_import_mapping_timezone_invalid,user,Die Zeitzone der Zeile passt nicht zur bestätigten Zeitzone.,Die Zeitzone prüfen.
exact,statement_mapping_profile_adapter_mismatch,user,Das Zuordnungsprofil gehört zu einer anderen Fassung des Lesers.,Ein neues Zuordnungsprofil anlegen.
exact,statement_mapping_profile_duplicate_invalid,user,Das Zuordnungsprofil enthält eine Zuordnung doppelt.,Die doppelte Zuordnung entfernen.
exact,statement_mapping_profile_ref_invalid,user,Das gewählte Zuordnungsprofil gibt es nicht mehr.,Ein vorhandenes Profil wählen.
exact,statement_reader_failed,user,Der Leser ist abgestürzt oder hat einen unbekannten Code gemeldet.,"Die Datei prüfen; bleibt der Fehler, bitte melden."
exact,statement_reader_id_conflict,user,Eine Leserkennung ist schon von einem anderen Plugin belegt.,Eines der beiden Plugins entfernen.
exact,statement_reader_unavailable,user,"Der Leser ist nicht installiert, oder seine Prüfsumme stimmt nicht.",Den Leser neu installieren und aktivieren.
exact,tax_classification_invalid,user,Die steuerliche Einordnung ist ungültig.,Die steuerliche Einordnung des Assets prüfen.
exact,tax_classification_required,user,Für ein Asset fehlt die steuerliche Einordnung.,Die steuerliche Einordnung des Assets ergänzen.
exact,tax_configuration_effective_date_invalid,user,Das Datum „Gültig ab“ ist ungültig oder liegt außerhalb der Jahre des Regelmoduls.,Ein Datum innerhalb der Jahre des Regelmoduls wählen.
exact,tax_configuration_selection_ambiguous,user,Für dieses Datum gelten mehrere Regelmodule.,Die Auswahl unter Daten → „4. Steuer“ → „Regelmodul“ prüfen.
exact,tax_configuration_selection_missing,user,Für dieses Datum ist kein Regelmodul gewählt.,Daten → „4. Steuer“ → „Regelmodul wählen“.
exact,tax_report_v2_currency_invalid,user,"Die Währungen von Portfolio, Buchung und FIFO passen nicht zusammen.","Die Kurswährung der betroffenen Assets prüfen; bleibt der Fehler, bitte melden."
exact,tax_report_v2_no_disposals,user,Im gewählten Steuerjahr gibt es keinen Verkauf.,Ein anderes Jahr wählen.
exact,tax_ui_classification_invalid,user,Die steuerliche Einordnung passt nicht zum gewählten Regelmodul.,Eine Einordnung des Regelmoduls wählen.
exact,tax_ui_parameter_invalid,user,"Ein Steuerwert ist ungültig, etwa Währung oder Wertebereich.",Den Wert prüfen und korrigieren.
exact,tax_ui_revision_missing,user,Die gewählte Fassung gibt es nicht mehr.,Die Ansicht neu laden.
exact,asset_activity_state_algorithm_changed,internal,,
exact,desktop_product_upgrade_recovery_required,internal,Ein Upgrade oder Rollback wurde unterbrochen und muss erst abgeschlossen werden.,
exact,portfolio_snapshot_v2_market_invalid,internal,,
exact,statement_reader_fixture_missing,internal,,
exact,statement_reader_pdf_text_missing,internal,,
suffix,account_invalid,user,Das gewählte Konto ist nicht gültig.,Das Konto neu wählen; nach Änderungen die Ansicht neu laden.
suffix,adapter_failed,user,Der Leser ist abgestürzt oder hat ein unlesbares Ergebnis geliefert.,"Die Datei prüfen; bleibt der Fehler, bitte melden."
suffix,already_committed,user,Dieser Schritt wurde schon ausgeführt.,Die Ansicht neu laden.
suffix,ambiguous,user,Die Angabe ist nicht eindeutig.,Genauer auswählen.
suffix,amount_invalid,user,Ein Betrag ist ungültig.,Den Betrag prüfen und korrigieren.
suffix,api_version_unsupported,user,Das Plugin verlangt eine neuere Portelyra-Version.,Portelyra aktualisieren oder eine passende Fassung des Plugins verwenden.
suffix,asset_invalid,user,Das gewählte Asset ist nicht gültig.,Das Asset neu wählen; nach Änderungen die Ansicht neu laden.
suffix,attempt_conflict,user,"Ein früherer, unterbrochener Versuch passt nicht zu diesem Schritt.","Den unterbrochenen Vorgang zuerst abschließen; bleibt der Fehler, bitte melden."
suffix,blocked,user,Der Schritt ist blockiert.,"Den angezeigten Grund beheben, dann erneut versuchen."
suffix,busy,user,"Gerade läuft ein anderer Vorgang, etwa „Alles aktualisieren“ oder ein Backup.","Warten, bis er beendet ist, dann erneut versuchen."
suffix,cancelled,user,Der Vorgang wurde abgebrochen.,Bei Bedarf erneut starten.
suffix,candidate_invalid,user,Der gewählte Vorschlag ist nicht mehr gültig.,Die Vorschläge neu laden und erneut wählen.
suffix,catalog_unavailable,user,Die Stammdaten lassen sich gerade nicht lesen.,"Die Ansicht neu laden; bleibt der Fehler, bitte melden."
suffix,changed,user,Die Daten haben sich inzwischen geändert.,Die Ansicht neu laden und den Schritt wiederholen.
suffix,confirmation_consumed,user,Diese Bestätigung wurde schon verwendet.,Für einen weiteren Schritt eine neue Vorschau erstellen.
suffix,confirmation_duplicate,user,Diese Bestätigung wurde schon verwendet.,Für einen weiteren Schritt eine neue Vorschau erstellen.
suffix,confirmation_expired,user,Die Bestätigung ist abgelaufen.,Die Vorschau neu erstellen und dann bestätigen.
suffix,confirmation_invalid,user,Die Bestätigung passt nicht zur gezeigten Vorschau.,Die Vorschau neu erstellen und dann bestätigen.
suffix,confirmation_mismatch,user,Die Bestätigung passt nicht zur gezeigten Vorschau.,Die Vorschau neu erstellen und dann bestätigen.
suffix,confirmation_missing,user,Der Schritt ist noch nicht bestätigt.,"Erst die Vorschau ansehen, dann bestätigen."
suffix,confirmation_required,user,Der Schritt ist noch nicht bestätigt.,"Erst die Vorschau ansehen, dann bestätigen."
suffix,conflict,user,Der Eintrag widerspricht einem vorhandenen.,Die vorhandenen Einträge prüfen und doppelte Angaben entfernen.
suffix,consumed,user,Diese Bestätigung wurde schon verwendet.,Für einen weiteren Schritt eine neue Vorschau erstellen.
suffix,context_mismatch,user,Die Auswahl gehört zu einem anderen Stand als die Ansicht.,Die Ansicht neu laden und erneut wählen.
suffix,cost_limit,user,"Die Obergrenze an Abrufen ist erreicht, oder der Anbieter hat wegen zu vieler Abrufe abgewiesen.",Später erneut versuchen oder die Obergrenze unter „Zugänge“ anheben.
suffix,credential_unavailable,user,Für den Anbieter ist kein bereiter Zugang eingetragen.,Den Zugang unter Daten → „Einstellungen“ → „Plugins und Zugänge“ → „Zugänge“ eintragen.
suffix,currency_invalid,user,Die Währung ist ungültig.,Einen dreistelligen Währungscode wie EUR oder USD angeben.
suffix,currency_mismatch,user,Die Währung passt nicht zur Kurswährung der Notierung.,Kurswährung und Kurszuordnung prüfen.
suffix,date_invalid,user,Ein Datum ist ungültig.,Das Datum prüfen und korrigieren.
suffix,decimal_invalid,user,Ein Betrag oder eine Menge ist ungültig.,Die Zahl prüfen und korrigieren.
suffix,disabled,user,Die Funktion ist ausgeschaltet.,"Sie in den Einstellungen einschalten, falls gewünscht."
suffix,duplicate,user,Der Eintrag ist doppelt.,Die vorhandenen Einträge prüfen und doppelte Angaben entfernen.
suffix,duplicate_conflict,user,Diesen Eintrag gibt es schon.,Den vorhandenen Eintrag verwenden.
suffix,empty,user,Es gibt nichts zu verarbeiten.,Eine Datei mit Inhalt wählen oder die Auswahl erweitern.
suffix,encoding_invalid,user,Die Datei hat eine unerwartete Zeichenkodierung.,Die Datei als UTF-8 speichern und erneut wählen.
suffix,entry_mismatch,user,Das Plugin weicht von seiner Prüfsumme ab und wird nicht geladen.,Das Plugin neu installieren.
suffix,exceeded,user,Eine Grenze ist überschritten.,Weniger auf einmal verarbeiten.
suffix,exists,user,Den Eintrag oder die Datei gibt es schon.,Den vorhandenen Eintrag verwenden oder einen anderen Namen wählen.
suffix,expired,user,Die Vorschau oder Bestätigung ist abgelaufen.,Die Vorschau neu erstellen und dann bestätigen.
suffix,fee_invalid,user,Eine Gebühr ist ungültig.,Die Gebühr prüfen und korrigieren.
suffix,format_invalid,user,Das Format einer Angabe oder Datei ist ungültig.,Angabe oder Datei prüfen und korrigieren.
suffix,generation_conflict,user,Der Buchungsstand hat sich inzwischen geändert.,Die Ansicht neu laden und den Schritt wiederholen.
suffix,group_inactive,user,Die Gruppe ist stillgelegt.,Eine aktive Gruppe wählen.
suffix,header_drift,user,Die Kopfzeile der Datei passt nicht zum erwarteten Aufbau.,Die passende Datei oder Vorlage wählen.
suffix,header_invalid,user,Die Kopfzeile der Datei passt nicht zum erwarteten Aufbau.,Die passende Datei oder Vorlage wählen.
suffix,idempotency_conflict,user,Diese Bestätigung wurde schon mit anderem Inhalt verwendet.,Eine neue Vorschau erstellen und bestätigen.
suffix,inactive,user,Die Funktion ist ausgeschaltet.,"Sie in den Einstellungen einschalten, falls gewünscht."
suffix,incomplete,user,Die Angaben sind noch unvollständig.,"Die fehlenden Teile ergänzen, dann erneut versuchen."
suffix,input_invalid,user,Eine Angabe ist ungültig.,Die Felder prüfen und korrigieren.
suffix,insufficient,user,Bestand oder Menge reicht nicht aus.,"Menge und Datum prüfen; fehlt eine frühere Buchung, diese zuerst erfassen."
suffix,isolation_unavailable,user,Die Abschottung fremder Plugins ist auf diesem System nicht möglich (Linux ab Kernel 6.2 mit Landlock 3 nötig).,Das System aktualisieren; bis dahin laufen fremde Plugins nicht.
suffix,keyring_unavailable,user,Der Schlüsselbund ist nicht erreichbar oder nicht eingerichtet.,"Den Schlüsselbund der Arbeitsumgebung entsperren, dann erneut versuchen."
suffix,label_invalid,user,Die Bezeichnung ist ungültig.,Eine andere Bezeichnung wählen.
suffix,limit,user,Eine Grenze ist überschritten.,Weniger auf einmal verarbeiten.
suffix,lock_unavailable,user,"Gerade läuft ein anderer Vorgang, etwa „Alles aktualisieren“ oder ein Backup.","Warten, bis er beendet ist, dann erneut versuchen."
suffix,locked,user,Portelyra ist mit dem Passwort gesperrt.,"Zuerst entsperren, dann erneut versuchen."
suffix,mismatch,user,Angaben passen nicht zueinander.,Die Eingaben prüfen; nach einer Änderung an anderer Stelle die Ansicht neu laden.
suffix,missing,user,Eine benötigte Angabe oder Datei fehlt.,Die Angaben ergänzen oder die Datei erneut wählen.
suffix,name_invalid,user,Der Name ist ungültig.,Einen anderen Namen wählen.
suffix,not_empty,user,Das Ziel ist nicht leer.,Ein leeres Ziel wählen oder den Inhalt zuerst entfernen.
suffix,not_found,user,Der Eintrag wurde nicht gefunden.,Die Ansicht neu laden; der Eintrag wurde vielleicht inzwischen geändert.
suffix,not_ready,user,Die Voraussetzungen sind noch nicht erfüllt.,"Die vorherigen Schritte abschließen, dann erneut versuchen."
suffix,outside_period,user,Das Datum liegt außerhalb des Zeitraums.,Datum oder Zeitraum prüfen.
suffix,overlap,user,Zeiträume überschneiden sich.,Die Zeiträume prüfen.
suffix,password_invalid,user,Das Passwort ist falsch.,Das Passwort erneut eingeben.
suffix,pending,user,Ein vorheriger Schritt ist noch offen.,"Ihn abschließen, dann erneut versuchen."
suffix,period_invalid,user,Der Zeitraum ist ungültig.,Anfang und Ende prüfen.
suffix,portfolio_invalid,user,Das gewählte Portfolio ist nicht gültig.,Das Portfolio neu wählen; nach Änderungen die Ansicht neu laden.
suffix,predecessor_conflict,user,Der Buchungsstand hat sich inzwischen geändert.,Die Ansicht neu laden und den Schritt wiederholen.
suffix,preview_changed,user,Die Vorschau fehlt oder ist nicht mehr aktuell.,Die Vorschau neu erstellen.
suffix,preview_invalid,user,Die Vorschau fehlt oder ist nicht mehr aktuell.,Die Vorschau neu erstellen.
suffix,preview_missing,user,Die Vorschau fehlt oder ist nicht mehr aktuell.,Die Vorschau neu erstellen.
suffix,preview_required,user,Die Vorschau fehlt oder ist nicht mehr aktuell.,Die Vorschau neu erstellen.
suffix,preview_stale,user,Die Vorschau fehlt oder ist nicht mehr aktuell.,Die Vorschau neu erstellen.
suffix,price_invalid,user,Ein Kurs oder Preis ist ungültig.,Den Wert prüfen und korrigieren.
suffix,provider_call_failed,user,Der Abruf beim Kursanbieter ist gescheitert.,Später erneut versuchen.
suffix,quantity_invalid,user,Eine Menge ist ungültig.,Die Menge prüfen und korrigieren.
suffix,range_invalid,user,Der Zeitraum ist ungültig.,Anfang und Ende prüfen.
suffix,reconciliation_mismatch,user,Der geprüfte Saldo passt nicht zu den Buchungen des Zeitraums.,Saldo laut Auszug und Buchungen prüfen; meist fehlt eine Buchung.
suffix,recovery_missing,user,Es gibt keinen passenden unterbrochenen Vorgang zum Wiederaufnehmen.,Die Liste der unterbrochenen Vorgänge neu laden.
suffix,recovery_required,user,Ein unterbrochener Vorgang muss zuerst abgeglichen werden.,Den unterbrochenen Vorgang wieder aufnehmen; die Karte zeigt ihn an. Danach erneut versuchen.
suffix,rejected,user,Die Angabe wurde abgewiesen.,Die Angaben prüfen und korrigieren.
suffix,replay,user,Diese Bestätigung wurde schon verwendet.,Für einen weiteren Schritt eine neue Vorschau erstellen.
suffix,replay_conflict,user,Diese Bestätigung wurde schon mit anderem Inhalt verwendet.,Eine neue Vorschau erstellen und bestätigen.
suffix,required,user,Eine Pflichtangabe fehlt.,Die fehlenden Angaben ergänzen.
suffix,response_invalid,user,Der Kursanbieter hat unerwartet geantwortet.,Später erneut versuchen.
suffix,restart_unavailable,user,Es gibt keinen unterbrochenen Vorgang zum Fortsetzen.,Den Vorgang neu beginnen.
suffix,revision_conflict,user,Der Eintrag wurde inzwischen geändert.,Die Ansicht neu laden und den Schritt wiederholen.
suffix,scheduled_disabled,user,Dieser Kursanbieter ist für den täglichen Zeitlauf nicht freigegeben.,Die Freigabe für den Zeitlauf beim Kursanbieter erteilen oder von Hand abrufen.
suffix,scheme_inactive,user,Die Einteilung ist stillgelegt.,Eine aktive Einteilung wählen.
suffix,scope_mismatch,user,Die Auswahl gehört zu einem anderen Stand als die Ansicht.,Die Ansicht neu laden und erneut wählen.
suffix,selection_invalid,user,Die Auswahl ist nicht mehr gültig.,Neu auswählen.
suffix,session_conflict,user,"Portelyra läuft schon, oder ein anderer Vorgang ist aktiv.","Den anderen Vorgang beenden oder abwarten, dann erneut versuchen."
suffix,source_rejected,user,"Die Quelle hat den Abruf abgewiesen, etwa wegen zu vieler Abrufe.",Etwas später erneut abrufen.
suffix,stale,user,Die Daten haben sich inzwischen geändert.,Die Ansicht neu laden und den Schritt wiederholen.
suffix,state_conflict,user,Der aktuelle Zustand erlaubt diesen Schritt nicht mehr.,Die Ansicht neu laden und den Schritt wiederholen.
suffix,superseded,user,Der Eintrag wurde inzwischen ersetzt.,Die Ansicht neu laden.
suffix,supersession_conflict,user,Der Buchungsstand hat sich inzwischen geändert.,Die Ansicht neu laden und den Schritt wiederholen.
suffix,symbol_invalid,user,Das Symbol ist ungültig.,Das Symbol beim Kursanbieter prüfen.
suffix,symlink_rejected,user,Verknüpfungen (Symlinks) werden aus Sicherheitsgründen nicht gelesen.,Die Datei selbst wählen.
suffix,target_invalid,user,Das gewählte Ziel ist nicht gültig.,Ein anderes Ziel wählen.
suffix,time_invalid,user,Datum oder Uhrzeit ist ungültig.,Datum und Uhrzeit prüfen und korrigieren.
suffix,timeout,user,Die Zeit für den Schritt ist abgelaufen.,Später erneut versuchen.
suffix,timezone_invalid,user,Die Zeitzone ist ungültig.,Die Zeitzone prüfen.
suffix,timezone_mismatch,user,Der Kursanbieter meldet eine andere Börsenzeitzone als die Notierung.,Die Kurszuordnung prüfen (Symbol und Börse).
suffix,too_large,user,Die Datei ist zu groß.,Eine kleinere Datei wählen.
suffix,transaction_profile_unsupported,user,"Eine Buchung hat eine Form, die dieser Bericht noch nicht verarbeitet.","Bitte melden, welche Buchung betroffen ist."
suffix,transport_failed,user,Der Kursanbieter war nicht erreichbar.,Die Netzverbindung prüfen und später erneut versuchen.
suffix,unavailable,user,Ein benötigter Dienst oder Stand ist gerade nicht verfügbar.,"Später erneut versuchen; bleibt der Fehler, bitte melden."
suffix,unknown,user,Der Eintrag ist unbekannt.,Die Ansicht neu laden; der Eintrag wurde vielleicht inzwischen geändert.
suffix,unsupported,user,Das wird nicht unterstützt.,Eine unterstützte Variante wählen.
suffix,value_invalid,user,Eine Angabe ist ungültig.,Die Felder prüfen und korrigieren.
suffix,write_failed,user,Das Speichern ist gescheitert.,"Freien Speicherplatz prüfen, dann erneut versuchen."
suffix,year_invalid,user,Das Jahr ist ungültig.,Ein vorhandenes Jahr wählen.
suffix,acceptance_failed,internal,,
suffix,active_invalid,internal,,
suffix,artifact_invalid,internal,,
suffix,audit_invalid,internal,,
suffix,authority_invalid,internal,,
suffix,authority_present,internal,,
suffix,binding_invalid,internal,,
suffix,boundary_failed,internal,,
suffix,boundary_invalid,internal,,
suffix,calculation_invalid,internal,,
suffix,calendar_invalid,internal,,
suffix,canonical_invalid,internal,,
suffix,capability_invalid,internal,,
suffix,cardinality_invalid,internal,,
suffix,catalog_invalid,internal,,
suffix,closure_invalid,internal,,
suffix,command_conflict,internal,,
suffix,command_failed,internal,,
suffix,command_invalid,internal,,
suffix,conservation_invalid,internal,,
suffix,context_invalid,internal,,
suffix,contract_invalid,internal,,
suffix,coverage_invalid,internal,,
suffix,digest_invalid,internal,,
suffix,discard_invalid,internal,,
suffix,domain_invalid,internal,,
suffix,effect_conflict,internal,,
suffix,entity_state_invalid,internal,,
suffix,environment_invalid,internal,,
suffix,evidence_invalid,internal,,
suffix,executor_invalid,internal,,
suffix,failpoint,internal,,
suffix,fifo_invalid,internal,,
suffix,fifo_mismatch,internal,,
suffix,fingerprint_invalid,internal,,
suffix,fixture_invalid,internal,,
suffix,full_rebuild_mismatch,internal,,
suffix,generation_invalid,internal,,
suffix,home_invalid,internal,,
suffix,host_not_allowed,internal,,
suffix,identity_invalid,internal,,
suffix,install_conflict,internal,,
suffix,integrity_invalid,internal,,
suffix,job_conflict,internal,,
suffix,job_invalid,internal,,
suffix,leak,internal,,
suffix,ledger_invalid,internal,,
suffix,lineage_invalid,internal,,
suffix,manifest_invalid,internal,,
suffix,materialization_failed,internal,,
suffix,migration_failed,internal,,
suffix,not_authorized,internal,,
suffix,not_completed,internal,,
suffix,open_failed,internal,,
suffix,output_conflict,internal,,
suffix,output_invalid,internal,,
suffix,overlay_invalid,internal,,
suffix,path_invalid,internal,,
suffix,payload_invalid,internal,,
suffix,permission_invalid,internal,,
suffix,placement_conflict,internal,,
suffix,plan_conflict,internal,,
suffix,plan_invalid,internal,,
suffix,probe_invalid,internal,,
suffix,process_failed,internal,,
suffix,profile_invalid,internal,,
suffix,project_invalid,internal,,
suffix,projection_invalid,internal,,
suffix,protection_invalid,internal,,
suffix,provenance_invalid,internal,,
suffix,publication_failed,internal,,
suffix,publication_invalid,internal,,
suffix,read_model_invalid,internal,,
suffix,reader_invalid,internal,,
suffix,receipt_conflict,internal,,
suffix,receipt_invalid,internal,,
suffix,reconciliation_invalid,internal,,
suffix,recovery_invalid,internal,,
suffix,redundancy_invalid,internal,,
suffix,reference_invalid,internal,,
suffix,registry_conflict,internal,,
suffix,registry_invalid,internal,,
suffix,repository_invalid,internal,,
suffix,result_invalid,internal,,
suffix,revision_invalid,internal,,
suffix,role_invalid,internal,,
suffix,role_not_authorized,internal,,
suffix,role_order_invalid,internal,,
suffix,root_invalid,internal,,
suffix,row_invalid,internal,,
suffix,runtime_invalid,internal,,
suffix,schema_invalid,internal,,
suffix,schema_unsupported,internal,,
suffix,seal_invalid,internal,,
suffix,semantics_invalid,internal,,
suffix,sequence_invalid,internal,,
suffix,service_invalid,internal,,
suffix,shape_invalid,internal,,
suffix,sign_invalid,internal,,
suffix,simulated_interruption,internal,,
suffix,snapshot_invalid,internal,,
suffix,source_invalid,internal,,
suffix,source_mismatch,internal,,
suffix,stage_invalid,internal,,
suffix,staged_import_invalid,internal,,
suffix,state_invalid,internal,,
suffix,storage_invalid,internal,,
suffix,store_exists,internal,,
suffix,store_invalid,internal,,
suffix,subprocess_failed,internal,,
suffix,target_exists,internal,,
suffix,transaction_failed,internal,,
suffix,upgrade_required,internal,Der Speicherstand passt nicht zu dieser Version.,
suffix,valuation_invalid,internal,,
suffix,version_invalid,internal,,
suffix,worker_failed,internal,,
suffix,worker_unavailable,internal,Ein Hintergrundschritt ist nicht verfügbar.,
suffix,workspace_invalid,internal,,
)---", stringsAsFactors = FALSE, encoding = "UTF-8", na.strings = character(), colClasses = "character")

pl_error_rule_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) || !nzchar(code)) return(NULL)
  rules <- PL_ERROR_TEXTS_V1
  exact <- which(rules$match == "exact" & rules$pattern == code)
  if (length(exact)) return(as.list(rules[exact[[1L]], ]))
  suffix <- which(rules$match == "suffix" & (rules$pattern == code | endsWith(code, paste0("_", rules$pattern))))
  if (!length(suffix)) return(NULL)
  as.list(rules[suffix[[which.max(nchar(rules$pattern[suffix]))]], ])
}

pl_error_text_v1 <- function(code) {
  code <- if (is.character(code) && length(code) == 1L && !is.na(code)) trimws(code) else ""
  if (!nzchar(code) || identical(code, "unbekannt")) return("Der genaue Grund ist nicht bekannt. Bitte melden Sie, was Sie zuletzt getan haben.")
  # Keine Kennung, sondern eine Meldung (etwa aus R selbst): unveraendert zeigen, als Meldung gekennzeichnet.
  if (!grepl("^[a-z][a-z0-9_]*$", code)) return(paste0("Ein Schritt ist unerwartet gescheitert. Bitte melden Sie diese Meldung: ", code))
  rule <- pl_error_rule_v1(code)
  if (!is.null(rule) && identical(rule$kind, "user")) return(paste0(rule$reason, " ", rule$next_step, " (Code: ", code, ")"))
  lead <- if (!is.null(rule) && nzchar(rule$reason)) rule$reason else "Ein Schritt ist unerwartet gescheitert."
  paste0(lead, " Bitte melden Sie diesen Fehlercode: ", code, ".")
}

# Zustand eines Abschlusses in Worten (#490); Unbekanntes bleibt als Code sichtbar.
pl_run_status_label_v1 <- function(status) {
  text <- if (is.character(status) && length(status) == 1L && !is.na(status)) status else ""
  labels <- c(completed = "abgeschlossen", partial = "teilweise", blocked = "blockiert", failed = "gescheitert", running = "läuft",
              empty = "leer", pending = "wartet", interrupted = "unterbrochen")
  if (text %in% names(labels)) labels[[text]] else paste0("(Code: ", if (nzchar(text)) text else "unbekannt", ")")
}
