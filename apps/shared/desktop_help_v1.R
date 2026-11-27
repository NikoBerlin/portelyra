# Hilfe in jeder App (#488, rc.436; Festlegung 18.11.2026): Das Handbuch liegt als Markdown im Programm
# (docs/handbuch/) und erscheint offline in einer Seitenleiste ueber der App, immer passend zur installierten Version.
#
# - Der Knopf "Hilfe" steht links im gemeinsamen Block (desktop_activity_sidebar_ui_v1) und oeffnet die Seite der App, beim Abschnitt
#   des gerade offenen Reiters: Die Ueberschriften der App-Seite heissen wie die Reiter, ohne Nummer ("1. Transaktionen" -> "Transaktionen").
# - Ein "?" an einer Karte (portelyra_card(help = "seite#anker")) springt zu ihrem Abschnitt.
# - Gerendert wird erst beim Oeffnen und nur eine Seite (Sitzungsstart unberuehrt). Verweise zwischen Handbuchseiten bleiben in der
#   Leiste; Verweise ins Netz oeffnen einen neuen Tab; Verweise auf Dateien des Repos werden zu Text. Bilder liefert die App selbst aus.
# - Reine Darstellung: liest nur Dateien unter docs/handbuch/, keine Daten des Portfolios.

PL_HELP_APP_PAGES_V1 <- c(data = "app-data", cockpit = "app-cockpit", tax = "app-steuer", analysis = "app-analyse")
PL_HELP_PAGE_RE_V1 <- "^([a-z0-9-]+/)?([a-z0-9-]+|README)$"
PL_HELP_RESOURCE_V1 <- "pl-handbuch"

desktop_help_dir_v1 <- function(project_root) file.path(project_root, "docs", "handbuch")

desktop_help_pages_v1 <- function(project_root) {
  dir <- desktop_help_dir_v1(project_root)
  if (!dir.exists(dir)) return(character())
  pages <- sub("[.]md$", "", list.files(dir, pattern = "[.]md$", recursive = TRUE))
  sort(pages[grepl(PL_HELP_PAGE_RE_V1, pages)])
}

# Anker wie bei GitHub: klein, Satzzeichen weg, Leerzeichen zu Bindestrichen - dieselben Verweise gelten im Repo und in der App.
desktop_help_slug_v1 <- function(text) {
  value <- tolower(enc2utf8(as.character(text)))
  value <- gsub("[^\\p{L}\\p{N} _-]", "", value, perl = TRUE)
  gsub(" ", "-", value, fixed = TRUE)
}

# Anker aus einem Verweis: commonmark kodiert Umlaute (%C3%B6), die Ueberschriften tragen sie roh. Nur Zeichen eines Ankers bleiben.
.desktop_help_anchor_text_v1 <- function(href_anchor) {
  value <- tryCatch(utils::URLdecode(href_anchor), error = function(error) "")
  Encoding(value) <- "UTF-8"
  if (!validUTF8(value)) return("")
  gsub("[^\\p{L}\\p{N}_-]", "", value, perl = TRUE)
}

.desktop_help_text_v1 <- function(html) {
  value <- gsub("<[^>]+>", "", html)
  entities <- c("&amp;" = "&", "&lt;" = "<", "&gt;" = ">", "&quot;" = "\"", "&#39;" = "'")
  for (name in names(entities)) value <- gsub(name, entities[[name]], value, fixed = TRUE)
  trimws(value)
}

.desktop_help_resolve_v1 <- function(page, target) {
  base <- if (grepl("/", page, fixed = TRUE)) sub("/[^/]*$", "", page) else ""
  parts <- c(if (nzchar(base)) strsplit(base, "/", fixed = TRUE)[[1L]], strsplit(target, "/", fixed = TRUE)[[1L]])
  out <- character()
  for (part in parts) {
    if (identical(part, "..")) { if (!length(out)) return(NA_character_); out <- out[-length(out)] }
    else if (nzchar(part) && !identical(part, ".")) out <- c(out, part)
  }
  paste(out, collapse = "/")
}

.desktop_help_replace_v1 <- function(html, pattern, replace) {
  matches <- gregexpr(pattern, html, perl = TRUE)[[1L]]
  if (matches[[1L]] < 0L) return(html)
  lengths <- attr(matches, "match.length"); pieces <- character(); last <- 1L
  for (index in seq_along(matches)) {
    start <- matches[[index]]; stop <- start + lengths[[index]] - 1L
    pieces <- c(pieces, substr(html, last, start - 1L), replace(substr(html, start, stop)))
    last <- stop + 1L
  }
  paste0(paste(pieces, collapse = ""), substr(html, last, nchar(html)))
}

# Eine Seite als HTML samt ihren Ankern. Fehlt sie, bricht es ab (desktop_help_page_unknown).
desktop_help_render_v1 <- function(project_root, page) {
  pages <- desktop_help_pages_v1(project_root)
  if (!is.character(page) || length(page) != 1L || !page %in% pages) stop("desktop_help_page_unknown", call. = FALSE)
  dir <- desktop_help_dir_v1(project_root)
  text <- paste(readLines(file.path(dir, paste0(page, ".md")), encoding = "UTF-8", warn = FALSE), collapse = "\n")
  html <- commonmark::markdown_html(enc2utf8(text), extensions = TRUE)
  # Tagfilter wie GFM, unabhaengig von der Fassung (rc.440): commonmark 1.9.1 aus Ubuntu 24.04 laesst rohes <script> durch, 2.0 nicht.
  html <- gsub("<(/?)(title|textarea|style|xmp|iframe|noembed|noframes|script|plaintext)(?=[\\s/>])", "&lt;\\1\\2", html,
               ignore.case = TRUE, perl = TRUE)
  anchors <- character()
  html <- .desktop_help_replace_v1(html, "<h([1-4])>(.*?)</h\\1>", function(tag) {
    level <- sub("^<h([1-4])>.*$", "\\1", tag)
    inner <- sub("^<h[1-4]>(.*)</h[1-4]>$", "\\1", tag)
    slug <- desktop_help_slug_v1(.desktop_help_text_v1(inner))
    candidate <- slug; counter <- 0L
    while (candidate %in% anchors) { counter <- counter + 1L; candidate <- paste0(slug, "-", counter) }
    anchors <<- c(anchors, candidate)
    sprintf("<h%s id=\"pl-help-%s\">%s</h%s>", level, candidate, inner, level)
  })
  html <- .desktop_help_replace_v1(html, "<a href=\"[^\"]*\">(.*?)</a>", function(tag) {
    href <- sub("^<a href=\"([^\"]*)\">.*$", "\\1", tag)
    label <- sub("^<a href=\"[^\"]*\">(.*)</a>$", "\\1", tag)
    if (grepl("^https?://", href)) return(sprintf("<a href=\"%s\" target=\"_blank\" rel=\"noopener noreferrer\">%s</a>", href, label))
    if (startsWith(href, "#")) {
      return(sprintf("<a href=\"#\" class=\"pl-help-link\" data-help-page=\"%s\" data-help-anchor=\"%s\">%s</a>", page, .desktop_help_anchor_text_v1(substring(href, 2L)), label))
    }
    target <- sub("#.*$", "", href); anchor <- if (grepl("#", href, fixed = TRUE)) .desktop_help_anchor_text_v1(sub("^[^#]*#", "", href)) else ""
    if (grepl("[.]md$", target)) {
      resolved <- .desktop_help_resolve_v1(page, sub("[.]md$", "", target))
      if (!is.na(resolved) && resolved %in% pages) {
        return(sprintf("<a href=\"#\" class=\"pl-help-link\" data-help-page=\"%s\" data-help-anchor=\"%s\">%s</a>", resolved, anchor, label))
      }
    }
    if (grepl("/$", target)) {   # Verweis auf einen Ordner des Handbuchs: dessen README
      folder <- .desktop_help_resolve_v1(page, sub("/$", "", target))
      readme <- if (is.na(folder)) NA_character_ else if (!nzchar(folder)) "README" else paste0(folder, "/README")
      if (!is.na(readme) && readme %in% pages) return(sprintf("<a href=\"#\" class=\"pl-help-link\" data-help-page=\"%s\" data-help-anchor=\"\">%s</a>", readme, label))
    }
    sprintf("<span class=\"pl-help-file\">%s</span>", label)
  })
  html <- .desktop_help_replace_v1(html, "<img src=\"[^\"]*\"", function(tag) {
    src <- sub("^<img src=\"([^\"]*)\"$", "\\1", tag)
    resolved <- .desktop_help_resolve_v1(page, src)
    if (!grepl("^https?://", src) && !is.na(resolved) && file.exists(file.path(dir, resolved))) {
      return(sprintf("<img loading=\"lazy\" src=\"%s/%s\"", PL_HELP_RESOURCE_V1, resolved))
    }
    "<img hidden src=\"\""
  })
  list(page = page, html = html, anchors = anchors)
}

# Welcher Abschnitt beim Oeffnen: ein ausdruecklicher Anker, sonst der innerste offene Reiter, der einen Abschnitt hat.
desktop_help_anchor_v1 <- function(rendered, anchor = "", tabs = character()) {
  if (is.character(anchor) && length(anchor) == 1L && nzchar(anchor) && anchor %in% rendered$anchors) return(anchor)
  for (tab in rev(as.character(unlist(tabs)))) {
    slug <- desktop_help_slug_v1(sub("^[0-9]+[.] *", "", trimws(tab)))
    if (nzchar(slug) && slug %in% rendered$anchors) return(slug)
  }
  ""
}

desktop_help_link_v1 <- function(target, label = "Hilfe zu diesem Abschnitt") {
  page <- sub("#.*$", "", target); anchor <- if (grepl("#", target, fixed = TRUE)) sub("^[^#]*#", "", target) else ""
  shiny::tags$a(href = "#", class = "pl-help-link pl-help-mark", `data-help-page` = page, `data-help-anchor` = anchor,
                title = label, `aria-label` = label, "?")
}

PL_HELP_CSS_V1 <- paste0(
  ".pl-help-panel{position:fixed;top:0;right:0;bottom:0;width:min(820px,94vw);z-index:1990;background:#fff;background:var(--pl-surface,#fff);",
  "color:var(--pl-text,#1f2933);box-shadow:-12px 0 32px rgba(15,23,42,.18);display:flex;flex-direction:column;font-size:15px;line-height:1.55}",
  ".pl-help-panel a{color:var(--pl-brand,#1f5f4a)}.pl-help-bar .btn{color:var(--pl-text,#1f2933)}",
  ".pl-help-body h1{font-size:1.7em;margin:.6em 0 .4em}.pl-help-body h2{font-size:1.35em;margin:1.2em 0 .4em}",
  ".pl-help-body h3{font-size:1.12em;margin:1em 0 .3em}.pl-help-body h4{font-size:1em}.pl-help-body p,.pl-help-body li{font-size:1em}",
  ".pl-help-panel[hidden]{display:none}",
  ".pl-help-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:12px 20px;border-bottom:1px solid var(--pl-line,#d8dee6)}",
  ".pl-help-bar .pl-help-title{font-weight:600;margin-right:auto}.pl-help-version{font-weight:400;font-size:.9em;color:var(--pl-muted,#52606d);margin-left:6px}",
  ".pl-help-body{overflow:auto;padding:12px 28px 40px;flex:1 1 auto}",
  ".pl-help-body img{max-width:100%;height:auto;border:1px solid var(--pl-line,#d8dee6);border-radius:6px}",
  ".pl-help-body table{border-collapse:collapse;margin:8px 0}.pl-help-body th,.pl-help-body td{border:1px solid var(--pl-line,#d8dee6);padding:4px 8px;vertical-align:top}",
  ".pl-help-body pre{white-space:pre-wrap;background:var(--pl-surface-soft,#f4f6f8);padding:8px 10px;border-radius:6px}",
  ".pl-help-file{font-family:monospace}",
  ".pl-help-mark{display:inline-block;margin-left:8px;width:1.4em;height:1.4em;line-height:1.4em;text-align:center;border-radius:50%;",
  "border:1px solid var(--pl-line,#d8dee6);font-size:.85em;text-decoration:none;color:var(--pl-muted,#52606d)}"
)

PL_HELP_JS_V1 <- paste0(
  "(function(){function panel(){return document.getElementById('pl-help-panel');}",
  # Die Leiste haengt im Block links; dort erbte sie dessen Farben und lag unter der App. Beim Laden an das Ende der Seite.
  "document.addEventListener('DOMContentLoaded',function(){var p=panel();if(p&&p.parentNode!==document.body){document.body.appendChild(p);}});",
  "function tabs(){var out=[];document.querySelectorAll('.pl-main .nav-tabs>li.active>a').forEach(function(a){",
  "if(a.offsetParent!==null){out.push((a.textContent||'').trim());}});return out;}",
  # Shiny vor 1.9 (Ubuntu 24.04: 1.8.0) bemerkt nicht selbst, dass ein verborgenes Element sichtbar wird: melden wie ein Reiterwechsel.
  "function show(p,open){p.hidden=!open;if(window.jQuery){window.jQuery(p).trigger(open?'shown':'hidden');}}",
  "function ask(page,anchor,withTabs){var p=panel();if(!p||!window.Shiny||!window.Shiny.setInputValue){return;}show(p,true);",
  "window.Shiny.setInputValue('pl_help_request',{page:page||'',anchor:anchor||'',tabs:withTabs?tabs():[],nonce:Date.now()},{priority:'event'});}",
  "document.addEventListener('click',function(e){var t=e.target&&e.target.closest?e.target.closest('.pl-help-open,.pl-help-link,.pl-help-close'):null;",
  "if(!t){return;}e.preventDefault();if(t.classList.contains('pl-help-close')){var p=panel();if(p){show(p,false);}return;}",
  # Der Knopf im Block links schaltet um (Nachprobe rc.440): Ist die Hilfe offen, schliesst ein zweiter Klick sie.
  "if(t.classList.contains('pl-help-open')){var q=panel();if(q&&!q.hidden){show(q,false);return;}}",
  "ask(t.getAttribute('data-help-page'),t.getAttribute('data-help-anchor'),t.classList.contains('pl-help-open'));});",
  "document.addEventListener('keydown',function(e){var p=panel();if(e.key==='Escape'&&p&&!p.hidden){show(p,false);}});",
  "document.addEventListener('DOMContentLoaded',function(){if(!window.jQuery){return;}window.jQuery(document).on('shiny:value',function(e){",
  "if(e.name!=='pl_help_body'){return;}setTimeout(function(){var p=panel();if(!p){return;}var box=p.querySelector('.pl-help-body');",
  "var holder=p.querySelector('[data-help-target]');var id=holder?holder.getAttribute('data-help-target'):'';var el=id?document.getElementById(id):null;",
  "if(el){el.scrollIntoView({block:'start'});}else if(box){box.scrollTop=0;}},0);});});",
  "})();"
)

# Der Knopf im Block links und die (zunaechst verborgene) Leiste. `app` waehlt die eigene Seite; `version` (#562) steht im Titel der Leiste.
desktop_help_ui_v1 <- function(app, version = NULL) {
  page <- PL_HELP_APP_PAGES_V1[[app]]
  nav <- function(target, label) shiny::tags$a(href = "#", class = "pl-help-link btn btn-default btn-sm", `data-help-page` = target,
                                               `data-help-anchor` = "", label)
  shiny::tagList(
    shiny::tags$style(shiny::HTML(PL_HELP_CSS_V1)),
    shiny::div(class = "pl-activity-seg pl-activity-help",
      shiny::div(class = "pl-activity-actions",
        shiny::tags$button(type = "button", class = "btn btn-default pl-help-open", `data-help-page` = page, `data-help-anchor` = "",
                           "Hilfe"))),
    shiny::tags$div(id = "pl-help-panel", class = "pl-help-panel", hidden = NA, role = "dialog", `aria-label` = "Hilfe",
      shiny::div(class = "pl-help-bar",
        shiny::span(class = "pl-help-title", "Hilfe",
          if (is.character(version) && length(version) == 1L && !is.na(version)) shiny::span(class = "pl-help-version", paste0("· Portelyra ", version))),
        nav("README", "Inhalt"), nav("erste-schritte", "Erste Schritte"), nav(page, "Diese App"), nav("meldungen", "Meldungen"),
        nav("lizenz", "Lizenz"),
        shiny::tags$button(type = "button", class = "btn btn-default btn-sm pl-help-close", "Schließen")),
      shiny::uiOutput("pl_help_body", class = "pl-help-body")),
    shiny::tags$script(shiny::HTML(PL_HELP_JS_V1)))
}

desktop_help_server_v1 <- function(input, output, session, project_root, app) {
  dir <- desktop_help_dir_v1(project_root)
  if (dir.exists(dir)) shiny::addResourcePath(PL_HELP_RESOURCE_V1, normalizePath(dir, winslash = "/", mustWork = TRUE))
  default_page <- PL_HELP_APP_PAGES_V1[[app]]
  shown <- shiny::reactiveVal(NULL)
  shiny::observeEvent(input$pl_help_request, {
    request <- input$pl_help_request
    page <- if (is.list(request) && is.character(request$page) && length(request$page) == 1L && nzchar(request$page)) request$page else default_page
    rendered <- tryCatch(desktop_help_render_v1(project_root, page), error = function(error) NULL)
    if (is.null(rendered) && !identical(page, default_page)) rendered <- tryCatch(desktop_help_render_v1(project_root, default_page), error = function(error) NULL)
    anchor <- if (is.null(rendered)) "" else desktop_help_anchor_v1(rendered, if (is.list(request)) request$anchor else "", if (is.list(request)) request$tabs else character())
    shown(list(rendered = rendered, anchor = anchor, nonce = if (is.list(request)) request$nonce else NULL))
  }, ignoreInit = TRUE)
  output$pl_help_body <- shiny::renderUI({
    value <- shown()
    if (is.null(value)) return(NULL)
    if (is.null(value$rendered)) return(shiny::p("Diese Hilfeseite ist in dieser Version nicht enthalten."))
    shiny::div(`data-help-target` = if (nzchar(value$anchor)) paste0("pl-help-", value$anchor) else "", shiny::HTML(value$rendered$html))
  })
  # Auch im verborgenen Zustand rendern (Nachprobe rc.440: unter Shiny 1.8 blieb die Hilfe sonst leer); vor einer Anfrage ist sie NULL.
  shiny::outputOptions(output, "pl_help_body", suspendWhenHidden = FALSE)
  invisible(shown)
}

# Seite "Meldungen und naechste Schritte" (#488): erzeugt aus dem Fehlerkatalog der Huelle (PL_ERROR_TEXTS_V1), damit sie nie von den
# Texten der Apps abweicht. Schreiben: Rscript dev/update_handbook.R; tests/contracts/test_desktop_help_v1.R vergleicht.
PL_HELP_MESSAGE_AREAS_V1 <- c(
  desktop_protection = "Passwortschutz", desktop_release = "Installation, Start und Update", desktop_product = "Installation, Start und Update",
  desktop_onboarding = "Installation, Start und Update", desktop_setup = "Installation, Start und Update",
  desktop_workflow = "Alles aktualisieren und Abschluss", desktop_run = "Alles aktualisieren und Abschluss",
  tax_module = "Steuer", tax_configuration = "Steuer", tax_ui = "Steuer", tax_classification = "Steuer", tax_report = "Steuer",
  asset_grouping = "Buchungen und Stammdaten", asset_activity = "Buchungen und Stammdaten", asset_quantity = "Buchungen und Stammdaten",
  activity_draft = "Buchungen und Stammdaten", desktop_asset = "Buchungen und Stammdaten", desktop_catalog = "Buchungen und Stammdaten",
  catalog_command = "Buchungen und Stammdaten", cash_coverage = "Cash", cash_statement = "Cash", desktop_cash = "Cash",
  desktop_market = "Kurse", manual_market = "Kurse", price_provider = "Plugins und Zugänge", plugin_credentials = "Plugins und Zugänge",
  plugin_signature = "Plugins und Zugänge", statement_reader = "Plugins und Zugänge", statement_import = "Import",
  statement_mapping = "Import", securities_statement = "Import", portfolio_csv = "Import", portfolio_snapshot = "Anzeige", display_no = "Anzeige")
PL_HELP_MESSAGE_ORDER_V1 <- c("Installation, Start und Update", "Passwortschutz", "Buchungen und Stammdaten", "Import", "Cash", "Kurse",
                              "Alles aktualisieren und Abschluss", "Steuer", "Plugins und Zugänge", "Anzeige", "Weitere", "Allgemein")

desktop_help_messages_markdown_v1 <- function(rules = PL_ERROR_TEXTS_V1) {
  user <- rules[rules$kind == "user", , drop = FALSE]
  cell <- function(value) gsub("|", "\\|", trimws(value), fixed = TRUE)
  prefix <- sub("^([a-z]+_[a-z]+).*$", "\\1", user$pattern)
  area <- ifelse(user$match == "suffix", "Allgemein", ifelse(prefix %in% names(PL_HELP_MESSAGE_AREAS_V1), PL_HELP_MESSAGE_AREAS_V1[prefix], "Weitere"))
  code <- ifelse(user$match == "suffix", paste0("…_", user$pattern), user$pattern)
  lines <- c("# Meldungen und nächste Schritte", "",
    "Meldet eine App einen Grund, steht hier, was er bedeutet und was zu tun ist. Der Code am Ende jeder Meldung hilft beim Suchen",
    "(Strg+F). Die Seite entsteht aus denselben Texten, die die Apps zeigen.", "",
    "Steht bei einer Meldung „Bitte melden Sie diesen Fehlercode“, ist es kein Bedienfehler: Dann bitte ein Issue mit dem Code und dem,",
    "was Sie zuletzt getan haben – ohne private Daten.", "")
  for (name in PL_HELP_MESSAGE_ORDER_V1) {
    keep <- which(area == name)
    if (!length(keep)) next
    keep <- keep[order(code[keep])]
    heading <- if (identical(name, "Allgemein")) "Allgemein (gilt für viele Bereiche)" else name
    lines <- c(lines, paste("##", heading), "", "| Meldung | Nächster Schritt | Code |", "|---|---|---|",
               sprintf("| %s | %s | `%s` |", cell(user$reason[keep]), cell(user$next_step[keep]), code[keep]), "")
  }
  paste0(paste(lines, collapse = "\n"), "\n")
}
