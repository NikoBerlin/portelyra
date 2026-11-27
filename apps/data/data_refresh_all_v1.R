# „Alles aktualisieren“ (#463): ein Lauf fuer einen frischen Stand, mit einer Bestaetigung. Stufe 2 haengt den Abschluss im
# Run Center an, mit den Eingaben des letzten bestaetigten Laufs; neu ist nur der Stichtag (Festlegung 19.10.2026). Die
# Marktwerte rechnet der Abschluss aus dem Bewertungsstand (Kurshistorie) und dem FIFO-Stand; eine abgeschlossene Bewertung
# bindet er nicht ein (Festlegung 20.10.2026 - die Karte „Exakter EUR-Marktwert“ ist ein eigenes Issue).
#
# Ein Klick fuehrt zu einem frischen FIFO-, Markt- und Steuerstand. Festlegungen: Der Kursabruf beim Anbieter gehoert dazu und steht in der Bestaetigung; Stichtag ist heute,
# die Staende je Datenart stehen daneben; der Ort ist die Data-App, weil nur sie schreibt.
#
# Die Schritte rufen die Kerne, die es schon gibt - FIFO-Fortschreibung, den Sammellauf des Asset-Centers, die Tageshistorie
# und die Snapshot-Veroeffentlichung. Dieses Modul fuehrt sie nur der Reihe nach aus: Was aktuell ist, wird uebersprungen und so
# benannt; ein Fehler haelt den Lauf mit Grund an, damit nichts danach still veraltet. Die Bausteine kommen als Funktionen
# herein (deps), damit sich der Ablauf ohne Provider und ohne Datenraum pruefen laesst.

# Momentaufnahme (rc.313, Festlegung 24.10.2026): zum Schluss aktuelle Kurse abrufen und das Bild von jetzt fuer die Analyse
# veroeffentlichen - tagesfrisch, aber kein Tagesschluss. Kurshistorie und Bewertung schreibt der Abruf nicht fort.
DATA_REFRESH_ALL_STEPS_V1 <- c(fifo = "FIFO-Stand", prices = "Kurse und Bewertung", gaps = "Quelllücken erneut abfragen", history = "Tageshistorie",
                               snapshot = "Snapshot", closing = "Abschluss", moment = "Momentaufnahme", stands = "Stände und Datenbasis")

data_refresh_all_card_ui_v1 <- function() portelyra_card(
  "Alles aktualisieren",
  copy = "Bringt alle Ergebnisse auf den neuesten Stand: Steuer je Ereignis und je Jahr, Bewertung mit projizierter Steuer, Tageshistorie, Stichtags-Snapshot und Momentaufnahme für die Analyse, dazu die Datenbasis.",
  note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-refresh-all", paste(
    "Danach rechnet der Abschluss für Cockpit, Steuer und Analyse; zum Schluss holt der Lauf aktuelle Kurse und veröffentlicht die Momentaufnahme – das Bild von jetzt, tagesfrisch, aber kein Tagesschluss. Ganz am Ende veröffentlicht er die Datenbasis: was hinterlegt und wie es eingestellt ist. Einzeln anstoßen muss man nichts davon.",
    "Ein Lauf für einen frischen Stand: FIFO-Stand fortschreiben, fehlende Kurse und Wechselkurse abrufen und bewerten (je Asset ab seiner ersten Buchung bis zum letzten abgeschlossenen Handelstag seiner Notierung),",
    "Tageshistorie fortschreiben, den Snapshot zum jüngsten vollständig bewerteten Tag veröffentlichen und zum selben Tag den Abschluss rechnen – mit den Eingaben des letzten bestätigten Abschlusses.",
    "Er fragt auch Quelllücken der letzten 10 Tage an gehaltenen Assets erneut ab – die Quelle liefert sie oft verzögert nach; der Haken schaltet das ab.",
    "Was schon aktuell ist, wird übersprungen. Ein Fehler hält den Lauf mit Grund an; ein neuer Lauf holt dann nur noch das Fehlende.",
    "Cash und Rewards kommen nur aus Auszügen und Importen – wie weit sie reichen, steht in der Tabelle.",
    "Der Lauf läuft für sich: Andere Apps öffnen, diese Seite neu laden oder schließen hält ihn nicht an. Jede Seite der App „Daten“ zeigt ihn wieder.")),
  class = "pl-write-boundary",
  shiny::uiOutput("refresh_all_stands_title"),
  shiny::div(class = "pl-table-wrap", shiny::tableOutput("refresh_all_stands")),
  shiny::div(class = "pl-editor-actions",
    shiny::checkboxInput("refresh_all_confirm",
      "Bestätigen: Kurse beim Anbieter abrufen (nur lesend: fehlende Tage und zum Schluss die aktuellen Kurse) und Bewertungen, Tageshistorie, Snapshot, den Abschluss (Eingaben des letzten bestätigten Laufs), die Momentaufnahme und die Datenbasis schreiben", FALSE),
    shiny::checkboxInput("refresh_all_retry_gaps",
      "Zusätzlich Quelllücken der letzten 10 Tage beim Anbieter erneut abfragen (nur gehaltene Assets, nur lesend)", TRUE),
    shiny::actionButton("refresh_all_start", "Alles aktualisieren", class = "btn-primary"),
    shiny::actionButton("refresh_all_stop", "Anhalten", class = "btn-default"),
    shiny::actionButton("refresh_all_stands_read", "Stände neu lesen", class = "btn-default")),
  shiny::uiOutput("refresh_all_state"),
  shiny::div(class = "pl-table-wrap", shiny::tableOutput("refresh_all_steps")))

data_refresh_all_initial_v1 <- function() lapply(names(DATA_REFRESH_ALL_STEPS_V1), function(code)
  list(code = code, label = unname(DATA_REFRESH_ALL_STEPS_V1[[code]]), status = "waiting", copy = "", started_ms = NULL, seconds = NULL))

# Dauer als m:ss (#457).
data_refresh_all_duration_v1 <- function(seconds) {
  if (is.null(seconds) || length(seconds) != 1L || is.na(seconds)) return("")
  seconds <- max(0L, as.integer(round(seconds)))
  sprintf("%d:%02d", seconds %/% 60L, seconds %% 60L)
}

.data_refresh_all_day_v1 <- function(value) {
  if (is.null(value) || length(value) != 1L || is.na(value) || !nzchar(as.character(value))) return("–")
  parsed <- tryCatch(as.Date(as.character(value)), error = function(error) NA)
  if (is.na(parsed)) "–" else format(parsed, "%d.%m.%Y")
}

data_refresh_all_status_label_v1 <- function(status) switch(as.character(status),
  waiting = "wartet", running = "läuft", done = "erledigt", skipped = "übersprungen", warning = "erledigt, mit Hinweis",
  notice = "übersprungen, mit Hinweis",
  halted = "angehalten", stopped = "auf Wunsch angehalten", as.character(status))

# Die Schritte als Tabelle (#457): Ein laufender Schritt zaehlt seine Zeit im Browser hoch (data-since, Zeitgeber der Huelle), auch
# waehrend die Sitzung blockiert ist; daneben die Dauer desselben Schritts im letzten Lauf als Richtwert. Die Zellen sind HTML,
# alle Texte maskiert.
data_refresh_all_steps_frame_v1 <- function(steps, last = list()) {
  if (!length(steps)) return(data.frame())
  esc <- function(value) as.character(htmltools::htmlEscape(as.character(value)))
  took <- vapply(steps, function(step) {
    if (identical(step$status, "running") && !is.null(step$started_ms))
      return(sprintf('<span class="pl-elapsed" data-since="%.0f">%s</span>', step$started_ms,
                     data_refresh_all_duration_v1((as.numeric(Sys.time()) * 1000 - step$started_ms) / 1000)))
    data_refresh_all_duration_v1(step$seconds)
  }, character(1L))
  before <- vapply(steps, function(step) { value <- last[[step$code]]; if (is.null(value)) "" else paste0("\u2248 ", data_refresh_all_duration_v1(value)) }, character(1L))
  data.frame(Schritt = esc(vapply(steps, function(step) step$label, character(1L))),
             Stand = esc(vapply(steps, function(step) data_refresh_all_status_label_v1(step$status), character(1L))),
             Dauer = took, `letzter Lauf` = esc(before),
             Ergebnis = esc(vapply(steps, function(step) as.character(step$copy), character(1L))),
             stringsAsFactors = FALSE, check.names = FALSE)
}

# Je Datenart, bis wann sie reicht: gemeinsam mit der Datenbasis (apps/shared/data_stands_ui_v1.R, seit rc.314).
data_refresh_all_stands_frame_v1 <- function(stands) data_stands_frame_v1(stands)

# Noch keine Buchungen (#565): Nach der Einrichtung gibt es keinen Buchungsbestand. Bis rc.405 hielt der FIFO-Schritt dann mit
# asset_activity_state_ledger_invalid an, und ein Zeitlauf meldete bis zur ersten Buchung bei jedem Lauf einen Fehler. Jetzt warten die
# Schritte, die Buchungen brauchen, neutral; "Staende und Datenbasis" laeuft. Erkennungsmerkmal: Die Bindung des Buchungsbestands ist
# "absent" (dieselbe Abfrage wie die Angleichung an geaenderte Stammdaten).
DATA_REFRESH_ALL_AWAITING_BOOKINGS_V1 <- "wartet auf die ersten Buchungen"
DATA_REFRESH_ALL_AWAITING_STEPS_V1 <- c("fifo", "prices", "gaps", "history", "snapshot", "closing", "moment")

# Das Ergebnis des Sammellaufs als ein Satz. Uebersprungene (Erstnotiz spaeter, Wechselkurs-Paar fehlt) sind Auskunft.
# Abgebrochene und zurueckgestellte Assets halten den Lauf seit rc.405 nur noch an, wenn kein einziges Asset neue Kurse bekam (Anbieter
# oder Netz weg): Dann aenderten die Schritte danach nichts. Sonst geht der Lauf mit Hinweis weiter. Bis rc.404 hielt schon ein Asset
# alles an: ein unterbrochener Abruf eines Assets liess Historie, Snapshot und Abschluss
# stehen, auch fuer alle Assets, die ihre Kurse hatten. Still unvollstaendig wird dadurch nichts: Der
# Snapshot nimmt den juengsten vollstaendig bewerteten Tag und nennt die Luecken danach mit Asset und Datum.
data_refresh_all_sweep_outcome_v1 <- function(results, reason = function(row) "") {
  status <- vapply(results, function(row) as.character(row$status), character(1L))
  open <- results[status %in% c("failed", "deferred")]
  completed <- sum(status == "completed"); skipped <- sum(status == "skipped")
  summary <- paste0(completed, " Assets bewertet", if (skipped) paste0(" · ", skipped, " übersprungen") else "")
  if (length(open)) {
    names <- vapply(utils::head(open, 5L), function(row) {
      why <- tryCatch(as.character(reason(row)), error = function(error) "")
      paste0(as.character(row$asset_name), if (length(why) == 1L && nzchar(why)) paste0(" (", why, ")") else "")
    }, character(1L))
    listed <- paste0(summary, " · ", length(open), " ohne neue Kurse: ", paste(names, collapse = "; "),
      if (length(open) > 5L) paste0(" und ", length(open) - 5L, " weitere") else "")
    if (!completed)
      return(list(status = "halted", copy = paste0(listed, ". Ohne neue Kurse ändern die Schritte danach nichts; ein neuer Lauf holt das Fehlende.")))
    return(list(status = "warning", copy = paste0(listed, ". Der Lauf geht weiter: Snapshot und Abschluss nehmen den jüngsten vollständig ",
      "bewerteten Tag und nennen, was danach fehlt. Ein neuer Lauf holt nur noch das Fehlende.")))
  }
  list(status = "done", copy = summary)
}

# Das Fenster fuer den Nachabruf der Quellluecken (#477): die letzten 10 Tage bis gestern. So weit traegt der Snapshot einen
# aelteren Kurs; aeltere Luecken aendern kein aktuelles Bild. Das Ende kuerzt die Planung je Notierung auf den letzten
# abgeschlossenen Handelstag (#475).
DATA_REFRESH_ALL_GAP_DAYS_V1 <- 10L
data_refresh_all_gap_window_v1 <- function(today) {
  day <- as.Date(today)
  list(start = as.character(day - DATA_REFRESH_ALL_GAP_DAYS_V1), end = as.character(day - 1L))
}

# Die Tagesgrenze nach dem Stichtag, hoechstens jetzt - wie im Run Center: Der FIFO-Lauf weist einen Cutoff in der Zukunft ab.
data_refresh_all_cutoff_v1 <- function(day, now_utc) {
  cutoff <- format(as.Date(day) + 1L, "%Y-%m-%dT00:00:00Z")
  if (cutoff > now_utc) now_utc else cutoff
}

# Umfang mit Steuerbericht, Abschluss ohne Steuermodul, und nichts, was Portelyra selbst abgeschaltet haette: zwei Angaben des Nutzers,
# die nicht zusammenpassen. Der Hinweis nennt beide Wege; gerechnet wird, was im Run Center bestaetigt ist.
DATA_REFRESH_ALL_TAX_UNSET_V1 <- "Steuerbericht ist im Umfang gewählt, der Abschluss rechnet aber ohne Steuermodul (im Abschluss nicht gewählt oder noch keines eingerichtet). Mit Steuer: Daten → „4. Steuer“ einrichten und im Abschluss das Steuermodul wählen. Ohne Steuer: im Umfang „Steuerbericht“ abwählen"
# Der Umfang eines Portfolios (rc.410) - nicht der wirksame des Datenraums. Gesucht ueber die Kennung oder, in den Anzeigen, ueber den
# Namen (nur wenn er unter den Portfolios eindeutig ist). NULL: nicht lesbar oder nicht eindeutig.
data_refresh_all_portfolio_modules_v1 <- function(project_root, context, portfolio_id = NULL, label = NULL) {
  python <- Sys.which("python3"); cli <- file.path(project_root, "scripts", "desktop_portfolio_configuration.py")
  space <- tryCatch(runtime_data_space_path(context), error = function(error) "")
  if (!nzchar(python) || !file.exists(cli) || !nzchar(space)) return(NULL)
  payload <- list(context = list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
                                 actor_id = context$actor_id, role = "desktop_owner"), data_space_path = space)
  output <- tryCatch(suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), "read"), stdout = TRUE, stderr = FALSE,
    input = as.character(jsonlite::toJSON(payload, auto_unbox = TRUE)))), error = function(error) character())
  parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
  rows <- if (is.list(parsed) && identical(parsed$status, "completed")) parsed$result$portfolios else NULL
  data_refresh_all_portfolio_modules_of_v1(rows, portfolio_id, label)
}
data_refresh_all_portfolio_modules_of_v1 <- function(rows, portfolio_id = NULL, label = NULL) {
  if (!is.list(rows)) return(NULL)
  found <- Filter(function(row) is.list(row) && (if (is.character(portfolio_id)) identical(row$portfolio_id, portfolio_id) else identical(row$label, label)), rows)
  if (length(found) != 1L || !is.list(found[[1L]]$configuration) || !is.list(found[[1L]]$configuration$modules)) return(NULL)
  lapply(found[[1L]]$configuration$modules, isTRUE)
}
# Die uebernommenen Eingaben mit den Steuervorgaben, die Portelyra wegen des Umfangs selbst abgeschaltet hatte (Steuerbericht wieder gewaehlt).
DATA_REFRESH_ALL_TAX_FIELDS_V1 <- c("capital_income_tax_rate", "personal_income_tax_rate", "solidarity_surcharge_rate", "church_tax_applicable", "church_tax_rate")
data_refresh_all_with_tax_v1 <- function(inputs, policy) {
  form <- inputs$form
  form$tax_mode <- policy$mode
  for (key in DATA_REFRESH_ALL_TAX_FIELDS_V1) form[key] <- list(policy[[key]])
  inputs$form <- form; inputs$tax_mode <- policy$mode; inputs["church_tax_applicable"] <- list(policy$church_tax_applicable)
  inputs$tax_restored <- TRUE
  inputs
}
# Die uebernommenen Eingaben ohne Steuermodul: wie "Nicht auswaehlen" im Run Center - Kirchensteuer und Saetze leer.
data_refresh_all_without_tax_v1 <- function(inputs) {
  form <- inputs$form
  form$tax_mode <- "disabled"
  for (key in DATA_REFRESH_ALL_TAX_FIELDS_V1) form[key] <- list(NULL)
  inputs$form <- form; inputs$tax_mode <- "disabled"; inputs["church_tax_applicable"] <- list(NULL); inputs$without_tax_report <- TRUE
  inputs
}

# Was vom letzten bestaetigten Lauf uebernommen wird, in Worten - und warum ein Lauf nicht uebernommen werden kann.
data_refresh_all_closing_inputs_copy_v1 <- function(inputs) {
  tax <- switch(as.character(inputs$tax_mode), disabled = if (isTRUE(inputs$without_tax_report)) "ohne Steuer (Umfang ohne Steuerbericht)"
                else if (isTRUE(inputs$tax_unset)) "ohne Steuermodul" else "ohne Steuer (wie gewählt)", de_reference_v2 = "Steuer: deutsches Referenzmodell v2",
                de_reference_v1 = "Steuer: deutsches Referenzmodell v1", as.character(inputs$tax_mode))
  church <- switch(if (is.null(inputs$church_tax_applicable)) "" else as.character(inputs$church_tax_applicable),
                   applicable = "Kirchensteuer anwendbar", not_applicable = "Kirchensteuer nicht anwendbar", NULL)
  fee <- switch(as.character(inputs$fee_source), derived_from_transactions = "Gebühr aus bisherigen Transaktionen",
                fixed_per_trade = "feste Gebühr je Trade", percentage_of_turnover = "Gebühr als Prozentsatz vom Umsatz", as.character(inputs$fee_source))
  mode <- if (identical(inputs$run_mode, "incremental")) "fortschreibend" else "vollständiger Neuaufbau"
  if (isTRUE(inputs$tax_restored)) tax <- paste0(tax, ", wieder aufgenommen (Steuerbericht gewählt)")
  paste0("Eingaben des Laufs zum ", .data_refresh_all_day_v1(inputs$last_as_of_date), " übernommen (",
         paste(c(paste("Portfolio", inputs$portfolio_label), mode, tax, church, fee), collapse = ", "), ")",
         if (as.integer(inputs$new_asset_count) > 0L) paste0(" · ", as.integer(inputs$new_asset_count), " seither neue Assets übernommen",
           if (identical(as.character(inputs$tax_mode), "disabled")) "" else ", steuerliche Einordnung aus der Vorgabe je Asset-Typ") else "")
}

data_refresh_all_closing_unusable_copy_v1 <- function(inputs) {
  day <- .data_refresh_all_day_v1(inputs$last_as_of_date)
  switch(as.character(inputs$reason),
    last_run_unfinished = paste0("Der letzte bestätigte Lauf (Stichtag ", day, ") ist nicht zu Ende gelaufen. Im Abschluss „Bestätigten Abschluss fortsetzen“ wählen, dann übernimmt dieser Schritt seine Eingaben."),
    manual_market_inputs = paste0("Der letzte bestätigte Lauf (Stichtag ", day, ") hatte eigene Kurse oder Wechselkurse; die gelten nur für seinen Stichtag. Den Abschluss bitte mit neuen Werten bestätigen."),
    portfolio_unavailable = paste0("Das Portfolio des letzten bestätigten Laufs (Stichtag ", day, ") ist nicht mehr aktiv. Den Abschluss bitte neu bestätigen."),
    "Der letzte bestätigte Lauf lässt sich nicht übernehmen. Den Abschluss bitte selbst bestätigen.")
}

# Die Eingaben des letzten Abschlusses im Run Center fuer die Datenbasis (rc.314, #478): genau die Felder, die die Veroeffentlichung
# annimmt, als kurzer Text oder NULL. Ohne bestaetigten Lauf nur der Status.
DATA_BASIS_RUN_CENTER_FIELDS_V1 <- c("status", "reason", "portfolio_label", "run_mode", "tax_mode", "capital_income_tax_rate",
  "personal_income_tax_rate", "solidarity_surcharge_rate", "church_tax_applicable", "church_tax_rate", "fee_source", "fee_fixed_decimal",
  "fee_percentage_rate_decimal", "grouping_mode", "last_as_of_date")
data_basis_run_center_v1 <- function(inputs) {
  if (!is.list(inputs) || !isTRUE(inputs$status %in% c("ready", "absent", "not_reusable"))) return(NULL)
  form <- if (is.list(inputs$form)) inputs$form else list()
  pick <- function(value) if (is.null(value) || length(value) != 1L || is.na(value) || !nzchar(as.character(value))) NULL else substr(as.character(value), 1L, 120L)
  values <- lapply(DATA_BASIS_RUN_CENTER_FIELDS_V1, function(field) pick(if (!is.null(inputs[[field]])) inputs[[field]] else form[[field]]))
  stats::setNames(values, DATA_BASIS_RUN_CENTER_FIELDS_V1)
}

# Was der Schritt "Stände und Datenbasis" geschafft hat, in Worten.
data_refresh_all_basis_copy_v1 <- function(published) {
  if (!is.list(published)) return("Stände gelesen · Datenbasis nicht veröffentlicht, der nächste Lauf versucht es erneut")
  open <- names(Filter(function(status) !identical(status, "available"), published$section_status))
  paste0("Stände gelesen, siehe oben · ",
         if (identical(published$status, "already_published")) "die Datenbasis zeigt bereits diesen Stand" else "Datenbasis veröffentlicht",
         if (length(open)) paste0(" · nicht lesbar: ", paste(vapply(open, function(name) {
           # Mit Grund (rc.343): Fehlerart und -code aus der Veroeffentlichung, damit sich ein "nicht lesbar" klaeren laesst.
           reason <- published$section_reasons[[name]]
           if (is.character(reason) && length(reason) == 1L && nzchar(reason)) sprintf("%s (Grund: %s)", name, reason) else name
         }, character(1L)), collapse = ", ")) else "")
}

# Was der Schritt "Momentaufnahme" geschafft hat, in Worten: wie viele der gehaltenen Kurse frisch sind.
data_refresh_all_moment_copy_v1 <- function(published) {
  count <- function(value) { number <- suppressWarnings(as.integer(value)); if (length(number) != 1L || is.na(number)) 0L else number }
  fresh <- count(published$observed_within_hour_count); total <- count(published$quote_count)
  paste0(fresh, " von ", total, " Kursen höchstens eine Stunde alt",
         if (identical(published$status, "already_published")) " · unverändert seit dem letzten Abruf" else " · veröffentlicht",
         " · in der Analyse unter „Momentaufnahme“")
}

# Der juengste Tag der Historie, an dem alles bewertet ist: fuer ihn wird der Snapshot veroeffentlicht.
# Die Positionen eines Snapshot-Plans ohne Wert, die nicht der Eigentuemer ausgenommen hat: „Name (Grund)“, hoechstens drei.
data_refresh_all_gap_names_v1 <- function(plan) {
  rows <- if (is.list(plan) && is.list(plan$excluded_positions)) Filter(function(row) is.list(row) && !isTRUE(row$owner_excluded), plan$excluded_positions) else list()
  if (!length(rows)) return(character())
  named <- vapply(rows, function(row) {
    name <- if (is.character(row$asset_name) && length(row$asset_name) == 1L && nzchar(row$asset_name)) row$asset_name else "ein Asset"
    reason <- if (is.character(row$reason) && length(row$reason) == 1L && nzchar(row$reason)) sub(" \\([a-z_]+\\)$", "", row$reason) else ""
    if (nzchar(reason)) paste0(name, " (", reason, ")") else name
  }, character(1L))
  if (length(named) > 3L) c(named[1:3], sprintf("%d weitere", length(named) - 3L)) else named
}
data_refresh_all_snapshot_day_v1 <- function(days) {
  complete <- Filter(function(row) identical(row$overall_status, "complete") && isTRUE(as.logical(row$market_value_complete)), days)
  if (!length(complete)) return(NULL)
  max(vapply(complete, function(row) as.character(row$day), character(1L)))
}

# Die wirksamen Bausteine des Umfangs je Portfolio (#542): Es laeuft, was ein aktives Portfolio nutzt. Gelesen ueber die CLI des Kerns;
# beim ersten Kontakt legt sie den Bestandseintrag an (alles an), am Bestand aendert sich also nichts.
data_refresh_all_modules_v1 <- function(project_root, context) {
  python <- Sys.which("python3"); cli <- file.path(project_root, "scripts", "desktop_portfolio_configuration.py")
  space <- tryCatch(runtime_data_space_path(context), error = function(error) "")
  if (!nzchar(python) || !file.exists(cli) || !nzchar(space)) return(NULL)
  payload <- list(context = list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
                                 actor_id = context$actor_id, role = "desktop_owner"), data_space_path = space)
  output <- tryCatch(suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), "read"), stdout = TRUE, stderr = FALSE,
    input = as.character(jsonlite::toJSON(payload, auto_unbox = TRUE)))), error = function(error) character())
  parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
  modules <- if (is.list(parsed) && identical(parsed$status, "completed")) parsed$result$effective$modules else NULL
  if (!is.list(modules) || !all(c("cash", "market_data", "history_analysis", "tax_report", "tax_projection", "documents") %in% names(modules))) return(NULL)
  lapply(modules, isTRUE)
}

# Bausteine des Umfangs je Portfolio (#542, rc.395): `modules` ist eine benannte Liste der wirksamen Bausteine oder NULL (alles an).
data_refresh_all_module_on_v1 <- function(modules, key) is.null(modules) || !identical(modules[[key]], FALSE)
# Der Abschluss haengt seit rc.406 an keinem Baustein mehr: Bewertung, Handels- und
# Marktanalyse gibt es fuer jeden Umfang. Bis rc.405 fiel er ohne "Steuerprojektion" ganz aus - auch fuer Nutzer, denen der
# Einrichtungsdialog einen ersten Abschluss ohne Steuer angelegt hatte. Die Steuer darin richtet sich nach dem Baustein Steuerbericht.
DATA_REFRESH_ALL_MODULE_STEPS_V1 <- list(prices = "market_data", gaps = "market_data", moment = "market_data", history = "history_analysis")
DATA_REFRESH_ALL_MODULE_LABELS_V1 <- c(market_data = "Marktdaten", history_analysis = "Verlauf und Analyse")
data_refresh_all_module_skip_v1 <- function(code, modules) {
  key <- DATA_REFRESH_ALL_MODULE_STEPS_V1[[code]]
  if (is.null(key) || data_refresh_all_module_on_v1(modules, key)) return(NULL)
  # Neutral (#564): ein abgewaehlter Baustein ist eine Wahl, kein Mangel.
  paste0("ohne „", DATA_REFRESH_ALL_MODULE_LABELS_V1[[key]], "“, wie gewählt (Einstellungen → Portfolio → Umfang)")
}

# Die Schrittmaschine (rc.315, #510): ohne Shiny, damit derselbe Ablauf in einem eigenen Prozess laufen kann - unabhaengig vom
# Browser-Tab und spaeter zeitgesteuert. Vorher lag sie im Server der Data-App; ein Wechsel in eine andere App beendete die
# Sitzung und damit den Lauf (Festlegung 24.10.2026). `run` ist eine Umgebung statt reactiveValues; `state()` liefert den
# Stand als einfache Liste fuer die Statusdatei.
data_refresh_all_engine_v1 <- function(deps) {
  run <- new.env(parent = emptyenv())
  reset <- function() {
    run$steps <- data_refresh_all_initial_v1(); run$index <- 0L; run$running <- FALSE; run$prices_started <- FALSE
    run$notice <- NULL; run$stands <- NULL; run$started_at <- NULL; run$finished_at <- NULL; run$snapshot_day <- NULL
    run$closing_inputs <- NULL; run$retry_gaps <- FALSE; run$gap_days <- 0L; run$last <- list(); run$run_center <- NULL; run$only <- NULL
    run$modules <- NULL; run$awaiting_bookings <- NULL
  }
  reset()
  now_ms <- function() as.numeric(Sys.time()) * 1000
  # Dauer je Schritt des letzten Laufs (#457) - als Richtwert, solange ein Schritt laeuft; ohne Speicher bleibt die Spalte leer.
  read_last <- function() {
    value <- if (is.function(deps$durations_read)) tryCatch(deps$durations_read(), error = function(error) NULL) else NULL
    run$last <- if (is.list(value)) value else list()
  }
  record_durations <- function() {
    if (!is.function(deps$durations_record)) return(invisible(NULL))
    measured <- Filter(function(step) step$status %in% c("done", "warning", "notice") && !is.null(step$seconds), run$steps)
    if (!length(measured)) return(invisible(NULL))
    values <- stats::setNames(lapply(measured, function(step) as.integer(round(step$seconds))), vapply(measured, function(step) step$code, character(1L)))
    tryCatch(deps$durations_record(values), error = function(error) NULL)
    invisible(NULL)
  }
  safe_code <- function(error) {
    code <- if (is.list(error) && is.character(error$code) && length(error$code) == 1L) error$code else conditionMessage(error)
    if (is.character(code) && length(code) == 1L && grepl("^[a-z][a-z0-9_]{3,90}$", code)) code else "data_refresh_all_step_failed"
  }
  # `done`/`total`: Fortschritt im Schritt als Zahlen (#540) - fuer den Block links in allen Apps; die Worte stehen in `copy`.
  set_step <- function(status, copy, done = NULL, total = NULL) {
    steps <- run$steps; steps[[run$index]]$status <- status; steps[[run$index]]$copy <- copy
    if (!is.null(total)) { steps[[run$index]]$done <- as.integer(done); steps[[run$index]]$total <- as.integer(total) }
    if (!status %in% c("waiting", "running") && !is.null(steps[[run$index]]$started_ms))
      steps[[run$index]]$seconds <- (now_ms() - steps[[run$index]]$started_ms) / 1000
    run$steps <- steps
  }
  finish <- function(tone, title, copy) {
    run$running <- FALSE; run$finished_at <- Sys.time()
    run$notice <- list(tone = tone, title = title, copy = copy)
    record_durations()
  }
  next_step <- function(status, copy) {
    set_step(status, copy)
    run$prices_started <- FALSE
    if (run$index >= length(run$steps)) {
      warned <- any(vapply(run$steps, function(step) step$status %in% c("warning", "notice"), logical(1L)))
      total <- if (is.null(run$started_at)) "" else paste0(" in ", data_refresh_all_duration_v1(as.numeric(difftime(Sys.time(), run$started_at, units = "secs"))))
      moment <- Filter(function(step) identical(step$code, "moment"), run$steps)
      if (identical(run$only, "moment") && length(moment) && identical(moment[[1L]]$status, "skipped"))
        finish("neutral", "Momentaufnahme entfällt", moment[[1L]]$copy)
      else if (identical(run$only, "moment")) finish(if (warned) "warning" else "positive", "Momentaufnahme aktualisiert",
        paste0("Nur die Momentaufnahme", total, if (warned) "; der Hinweis steht in der Tabelle." else ".",
               " Kurshistorie, Bewertung, Tageshistorie und Abschluss bleiben, wie sie sind."))
      else if (isTRUE(run$awaiting_bookings))
        finish("neutral", "Wartet auf die ersten Buchungen", paste0("Es gibt noch keine Buchungen", total, ". Sobald Buchungen erfasst oder ",
          "eingelesen sind, holt dieser Lauf Kurse und schreibt Tageshistorie, Snapshot und Abschluss fort. Die Vorgaben dafür stehen schon."))
      else finish(if (warned) "warning" else "positive", "Alles aktualisiert",
             paste0("Der Lauf ist durch", total, if (warned) "; die Hinweise stehen in der Tabelle." else ".",
                    " Stichtag des Bildes ist heute; wie weit jede Datenart reicht, steht oben.",
                    " Analyse, Cockpit und Steuer bemerken den neuen Stand und bieten „Neu lesen“ an."))
    } else run$index <- run$index + 1L
  }
  halt <- function(copy) {
    set_step("halted", copy)
    finish("error", paste0("Angehalten bei „", run$steps[[run$index]]$label, "“"), copy)
  }
  read_stands <- function() {
    value <- tryCatch(deps$stands(deps$today()), error = function(error) NULL)
    run$stands <- value
    value
  }
  advance <- function() {
    step <- run$steps[[run$index]]
    # Einmal je Lauf vor allen Schritten, auch fuer einen Lauf nur der Momentaufnahme (#565).
    if (is.null(run$awaiting_bookings))
      run$awaiting_bookings <- is.function(deps$bookings_absent) && isTRUE(tryCatch(deps$bookings_absent(), error = function(error) FALSE))
    # Ein Lauf nur fuer die Momentaufnahme (rc.365, #516) uebergeht die anderen Schritte, ohne sie anzufassen.
    if (length(run$only) && !step$code %in% run$only) return(next_step("skipped", "nicht Teil dieses Laufs"))
    # Umfang je Portfolio (#542, rc.395): Ein abgeschalteter Baustein laesst seine Schritte aus, mit Grund. Es laeuft, was ein aktives
    # Portfolio nutzt; ohne Speicher laeuft alles wie bisher.
    off <- data_refresh_all_module_skip_v1(step$code, run$modules)
    if (!is.null(off)) return(next_step("skipped", off))
    if (isTRUE(run$awaiting_bookings) && step$code %in% DATA_REFRESH_ALL_AWAITING_STEPS_V1)
      return(next_step("skipped", DATA_REFRESH_ALL_AWAITING_BOOKINGS_V1))
    # Zwei Takte je Schritt (#457): erst "laeuft" mit Startzeit zeigen, dann rechnen. Sonst stuende ein Schritt, der eine Minute
    # rechnet, die ganze Zeit auf "wartet", und die Seite saehe aus wie haengend.
    if (identical(step$status, "waiting")) {
      steps <- run$steps; steps[[run$index]]$status <- "running"; steps[[run$index]]$copy <- "läuft"; steps[[run$index]]$started_ms <- now_ms()
      run$steps <- steps
      return(invisible(NULL))
    }
    if (identical(step$code, "fifo")) {
      checked <- deps$fifo_check()
      if (identical(checked$freshness, "fresh")) return(next_step("skipped", "bereits aktuell"))
      set_step("running", "wird fortgeschrieben")
      updated <- deps$fifo_update()
      return(next_step("done", paste0(as.integer(updated$changed_world_count), " FIFO-Welten neu gerechnet, ",
                                      as.integer(updated$reused_world_count), " unverändert")))
    }
    if (identical(step$code, "prices")) {
      if (!isTRUE(run$prices_started)) {
        blocked <- deps$prices_blocked()
        if (is.character(blocked) && length(blocked) == 1L && nzchar(blocked)) return(halt(blocked))
        set_step("running", "prüft, welchen Assets Kurstage fehlen")
        prepared <- deps$prices_prepare()
        excluded <- if (length(prepared$excluded)) paste0(" · nicht im Lauf: ", sum(as.integer(prepared$excluded)),
          " Assets ohne Marktbewertung über den Kursanbieter oder ohne geprüfte Kurszuordnung") else ""
        # Kursreihen der Bewertungs-Zeitleiste, die nicht laufen koennen, mit Namen und Grund (rc.393).
        if (length(prepared$timeline_blocked)) excluded <- paste0(excluded, " ·", sub("\\.$", "", data_market_timeline_blocked_copy_v1(prepared$timeline_blocked)))
        if (!as.integer(prepared$count)) return(next_step("skipped", paste0("keinem Asset fehlt ein Kurstag", excluded)))
        run$prices_started <- TRUE
        set_step("running", paste0("0 von ", as.integer(prepared$count), " Assets", excluded), 0L, as.integer(prepared$count))
        return(invisible(NULL))
      }
      progress <- deps$prices_progress()
      if (isTRUE(progress$running)) {
        set_step("running", paste0(length(progress$results), " von ", as.integer(progress$total), " Assets",
          if (!is.null(progress$resume_at)) paste0(" · die Quelle bremst, nächster Versuch um ", format(progress$resume_at, "%H:%M")) else ""),
          min(length(progress$results), as.integer(progress$total)), as.integer(progress$total))
        return(invisible(NULL))
      }
      outcome <- data_refresh_all_sweep_outcome_v1(progress$results, deps$prices_reason)
      if (length(progress$results) < as.integer(progress$total))
        return(halt(paste0("Der Sammellauf endete nach ", length(progress$results), " von ", as.integer(progress$total), " Assets. ", outcome$copy)))
      if (identical(outcome$status, "halted")) return(halt(outcome$copy))
      return(next_step(outcome$status, outcome$copy))
    }
    if (identical(step$code, "gaps")) {
      if (!isTRUE(run$retry_gaps)) return(next_step("skipped", "nicht gewählt"))
      window <- data_refresh_all_gap_window_v1(deps$today())
      if (!isTRUE(run$prices_started)) {
        set_step("running", "prüft, welche gehaltenen Assets Quelllücken haben")
        prepared <- deps$gaps_prepare(window)
        if (!as.integer(prepared$count))
          return(next_step("skipped", paste0("keine Quelllücke seit dem ", .data_refresh_all_day_v1(window$start), " an gehaltenen Assets")))
        run$prices_started <- TRUE; run$gap_days <- as.integer(prepared$gap_day_count)
        set_step("running", paste0("0 von ", as.integer(prepared$count), " Assets · ", run$gap_days, " Lückentage"), 0L, as.integer(prepared$count))
        return(invisible(NULL))
      }
      progress <- deps$prices_progress()
      if (isTRUE(progress$running)) {
        set_step("running", paste0(length(progress$results), " von ", as.integer(progress$total), " Assets · ", run$gap_days, " Lückentage",
          if (!is.null(progress$resume_at)) paste0(" · die Quelle bremst, nächster Versuch um ", format(progress$resume_at, "%H:%M")) else ""),
          min(length(progress$results), as.integer(progress$total)), as.integer(progress$total))
        return(invisible(NULL))
      }
      # Ohne Antwort der Quelle bleibt der alte Stand; die Luecke war vorher schon da. Das haelt den Lauf nicht an.
      remaining <- tryCatch(as.integer(deps$gaps_remaining(window)), error = function(error) NA_integer_)
      status <- vapply(progress$results, function(row) as.character(row$status), character(1L))
      open <- progress$results[status %in% c("failed", "deferred")]
      names <- vapply(utils::head(open, 5L), function(row) as.character(row$asset_name), character(1L))
      copy <- paste0(run$gap_days, " Lückentage an ", length(progress$results), " Assets erneut abgefragt · ",
        if (is.na(remaining)) "wie viele nachgeliefert sind, ist nicht lesbar" else paste0(max(0L, run$gap_days - remaining), " nachgeliefert"),
        if (length(open)) paste0(" · ohne Antwort der Quelle: ", paste(names, collapse = "; "),
          if (length(open) > 5L) paste0(" und ", length(open) - 5L, " weitere") else "") else "")
      return(next_step(if (length(open) || is.na(remaining)) "warning" else "done", copy))
    }
    if (identical(step$code, "history")) {
      set_step("running", "wird fortgeschrieben")
      result <- deps$history_update()
      deps$after_history()
      # Die Reihe fuer die Analyse (#473). Schlaegt die Veroeffentlichung fehl, bleibt die Analyse beim vorigen Stand;
      # Snapshot und Abschluss haengen nicht daran, deshalb nur ein Hinweis.
      published <- tryCatch(deps$history_publish(), error = function(error) list(status = "failed"))
      published_copy <- switch(as.character(published$status), published = " · für die Analyse veröffentlicht",
        already_published = " · die Analyse zeigt bereits diesen Stand", failed = " · Veröffentlichung für die Analyse schlug fehl, der nächste Lauf versucht es erneut", "")
      copy <- if (is.null(result$recomputed_from)) paste0("nichts geändert · reicht bis ", .data_refresh_all_day_v1(result$last_day))
        else paste0(as.integer(result$computed_day_count), " Tage ab dem ", .data_refresh_all_day_v1(result$recomputed_from),
                    " gerechnet, ", as.integer(result$written_day_count), " geändert · reicht bis ", .data_refresh_all_day_v1(result$last_day))
      return(next_step(if (identical(published$status, "failed")) "warning" else "done", paste0(copy, published_copy)))
    }
    if (identical(step$code, "snapshot")) {
      # Ohne "Verlauf und Analyse" (#542, Festlegung 10.11.2026): Der Snapshot plant direkt aus dem Bestand, zum gestrigen Tag.
      if (!data_refresh_all_module_on_v1(run$modules, "history_analysis")) {
        days <- list(); day <- format(as.Date(deps$today()) - 1L, "%Y-%m-%d")
      } else {
        history <- deps$history_read()
        days <- if (is.list(history)) history$days else list()
        day <- data_refresh_all_snapshot_day_v1(days)
        # Ohne Marktdaten sind Tage aus Transaktionskursen bewertet und nie "vollstaendig mit Marktwert": dann der juengste Tag.
        if (is.null(day) && !data_refresh_all_module_on_v1(run$modules, "market_data") && length(days)) day <- as.character(days[[length(days)]]$day)
      }
      if (is.null(day)) return(halt("Kein Tag der Tageshistorie ist vollständig bewertet; der Snapshot würde nur Lücken festhalten. Die Stände oben zeigen, was fehlt."))
      last <- if (length(days)) as.character(days[[length(days)]]$day) else day
      plan <- deps$snapshot_plan(day)
      if (isTRUE(plan$beyond_valued_window) || identical(as.integer(plan$counts$valued_position_count), 0L))
        return(halt(paste0("Für den ", .data_refresh_all_day_v1(day), " ist keine Position bewertet; nichts veröffentlicht.")))
      published <- deps$snapshot_publish(plan)
      run$snapshot_day <- day
      copy <- paste0("Stichtag ", .data_refresh_all_day_v1(day), " · ",
        if (identical(published$snapshot_status, "complete")) "vollständig" else "unvollständig",
        if (identical(published$status, "already_published")) " · lag mit gleichem Inhalt schon vor, nichts geändert" else " · veröffentlicht")
      # Wer den Snapshot aufhaelt (#537): die Positionen des juengsten Tages ohne Wert, mit Grund - etwa ein neu gekauftes Asset ohne
      # Kursquelle. Bis rc.360 nannte der Schritt nur den frueheren Stichtag.
      if (day < last) {
        gaps <- tryCatch(data_refresh_all_gap_names_v1(deps$snapshot_plan(last)), error = function(error) character())
        return(next_step("warning", paste0(copy, " · die Tage danach bis ", .data_refresh_all_day_v1(last), " sind noch nicht vollständig bewertet",
          if (length(gaps)) paste0(" – am ", .data_refresh_all_day_v1(last), " fehlt der Wert für ", paste(gaps, collapse = ", "),
                                   ". Eine fehlende Kursquelle lässt sich unter 3. Marktdaten → 1. Kursquelle einrichten") else "")))
      }
      return(next_step("done", copy))
    }
    if (identical(step$code, "closing")) {
      day <- run$snapshot_day
      # Zwei Takte: erst die Eingaben lesen und "rechnet" zeigen, dann rechnen - sonst stuende die Zeile die ganze Minute auf "wartet".
      if (is.null(run$closing_inputs)) {
        inputs <- deps$closing_inputs(day, data_refresh_all_cutoff_v1(day, deps$now_utc()))
        run$run_center <- data_basis_run_center_v1(inputs)
        if (identical(inputs$status, "absent"))
          return(next_step("notice", "Für den Abschluss gibt es noch keinen bestätigten Lauf. Den ersten einmal selbst im Abschluss prüfen und bestätigen; danach übernimmt dieser Schritt seine Eingaben."))
        if (!identical(inputs$status, "ready")) return(next_step("notice", data_refresh_all_closing_unusable_copy_v1(inputs)))
        # Noch keine Assets (frisch eingerichtet, #555 c): nichts abzuschliessen. Kein Lauf und kein "blockiert", der den ganzen Lauf
        # anhielte - der erste Abschluss entsteht, sobald Buchungen da sind; die Vorgaben stehen schon (Einrichtung bzw. letzter Lauf).
        if (is.list(inputs$form$asset_inputs) && !length(inputs$form$asset_inputs))
          return(next_step("skipped", paste("wartet auf die ersten Buchungen: Die Vorgaben für den Abschluss stehen; der erste Abschluss",
                                            "entsteht, sobald Buchungen erfasst oder eingelesen sind")))
        # Die Steuer folgt dem Baustein Steuerbericht (#564; Festlegung 13.11.2026: angezeigt wird nur, was als Baustein gewaehlt ist).
        # Seit rc.410 (Prüfung 13.11.2026) genauer:
        # - Massgeblich ist der Umfang des Portfolios, dessen Abschluss gerechnet wird - nicht der des Datenraums, der einen Baustein
        #   fuehrt, sobald irgendein aktives Portfolio ihn nutzt. Nicht lesbar: Die uebernommenen Eingaben bleiben, wie sie sind.
        # - Aus: ohne Steuermodul, auch wenn der uebernommene Lauf eines hatte; dessen Vorgaben werden vermerkt.
        # - Wieder an: genau diese vermerkten Vorgaben zurueck. Eine bewusste Wahl „Nicht auswählen“ im Run Center (kein Vermerk) bleibt -
        #   bis rc.409 holte der Lauf dann still das Steuermodul irgendeines frueheren Laufs zurueck.
        # - An, ohne Steuermodul und ohne Vermerk: unveraendert rechnen, mit Hinweis auf beide Wege.
        own <- if (is.function(deps$portfolio_modules) && is.character(inputs$portfolio_id))
          tryCatch(deps$portfolio_modules(inputs$portfolio_id), error = function(error) NULL) else NULL
        if (is.list(own)) {
          tax_on <- !identical(own[["tax_report"]], FALSE)
          saved <- if (is.function(deps$tax_override_read)) tryCatch(deps$tax_override_read(), error = function(error) NULL) else NULL
          mine <- is.list(saved) && identical(saved$portfolio_id, inputs$portfolio_id) && is.list(saved$policy) && is.character(saved$policy$mode) &&
            !identical(saved$policy$mode, "disabled")
          if (!tax_on && !identical(inputs$form$tax_mode, "disabled")) {
            policy <- c(list(mode = inputs$form$tax_mode), stats::setNames(lapply(DATA_REFRESH_ALL_TAX_FIELDS_V1, function(key) inputs$form[[key]]), DATA_REFRESH_ALL_TAX_FIELDS_V1))
            if (is.function(deps$tax_override_write)) tryCatch(deps$tax_override_write(list(portfolio_id = inputs$portfolio_id, policy = policy)), error = function(error) NULL)
            inputs <- data_refresh_all_without_tax_v1(inputs)
          } else if (tax_on && identical(inputs$form$tax_mode, "disabled")) {
            inputs <- if (mine) data_refresh_all_with_tax_v1(inputs, saved$policy) else c(inputs, list(tax_unset = TRUE))
          } else if (tax_on && mine && is.function(deps$tax_override_clear)) tryCatch(deps$tax_override_clear(), error = function(error) NULL)
        }
        run$closing_inputs <- inputs
        set_step("running", paste0("Stichtag ", .data_refresh_all_day_v1(day), " · rechnet, das dauert rund eine Minute"))
        return(invisible(NULL))
      }
      inputs <- run$closing_inputs; run$closing_inputs <- NULL
      taken <- data_refresh_all_closing_inputs_copy_v1(inputs)
      result <- deps$closing_run(inputs, day)
      # Die Datenbasis nennt den Stichtag des Laufs, der jetzt gilt - nicht den des vorigen, dessen Eingaben uebernommen wurden
      # (#529 Punkt 9).
      if (is.list(run$run_center) && isTRUE(result$status %in% c("completed", "current"))) run$run_center$last_as_of_date <- as.character(day)
      aligned <- if (isTRUE(result$aligned)) " · Buchungsbestand an geänderte Stammdaten angeglichen, an den Buchungen selbst nichts geändert" else ""
      if (identical(result$status, "invalid")) return(halt(paste0("Die übernommenen Eingaben passen nicht mehr: ", result$copy, " Den Abschluss bitte selbst prüfen.")))
      if (identical(result$status, "current"))
        return(next_step("skipped", paste0("bereits aktuell: Der letzte Lauf zum ", .data_refresh_all_day_v1(day), " hat dieselben Eingaben und Daten", aligned)))
      if (!identical(result$status, "completed"))
        return(halt(paste0("Der Abschluss zum ", .data_refresh_all_day_v1(day), " wurde blockiert. Im Abschluss steht, welche Stufe hielt. ", pl_error_text_v1(result$failure_code))))
      # Die zurueckgeholten Vorgaben stehen jetzt in einem bestaetigten Lauf: Der Vermerk hat seinen Dienst getan.
      if (isTRUE(inputs$tax_restored) && is.function(deps$tax_override_clear)) tryCatch(deps$tax_override_clear(), error = function(error) NULL)
      if (isTRUE(inputs$tax_unset))
        return(next_step("notice", paste0("Stichtag ", .data_refresh_all_day_v1(day), " · veröffentlicht · ", taken, aligned, " · ", DATA_REFRESH_ALL_TAX_UNSET_V1)))
      return(next_step("done", paste0("Stichtag ", .data_refresh_all_day_v1(day), " · veröffentlicht · ", taken, aligned)))
    }
    if (identical(step$code, "moment")) {
      if (!is.function(deps$moment_fetch) || !is.function(deps$moment_publish))
        return(next_step("notice", "Momentaufnahme nicht verfügbar: Der Bewertungsstand ist nicht lesbar."))
      deps$moment_fetch()
      published <- deps$moment_publish()
      if (identical(published$status, "no_quotes"))
        return(next_step("warning", "kein aktueller Kurs abgerufen; die letzte Momentaufnahme bleibt stehen"))
      return(next_step("done", data_refresh_all_moment_copy_v1(published)))
    }
    # Zum Schluss die Datenbasis (rc.314, #478): Sie traegt die Staende mit; gelesen wird nur einmal.
    if (is.function(deps$basis_publish)) {
      published <- tryCatch(deps$basis_publish(run$run_center), error = function(error) NULL)
      if (is.list(published) && is.list(published$stands) && identical(published$stands$status, "available")) run$stands <- published$stands
      else if (is.null(read_stands())) return(next_step("warning", "nicht lesbar; „Stände neu lesen“ versucht es erneut"))
      opened <- is.list(published) && length(Filter(function(status) !identical(status, "available"), published$section_status))
      return(next_step(if (is.list(published) && !opened) "done" else "warning", data_refresh_all_basis_copy_v1(published)))
    }
    stands <- read_stands()
    if (is.null(stands)) return(next_step("warning", "nicht lesbar; „Stände neu lesen“ versucht es erneut"))
    next_step("done", "gelesen, siehe oben")
  }
  # `only`: nur diese Schritte (rc.365: "moment" fuer den eigenen Zeitplan der Momentaufnahme); NULL heisst alle.
  start <- function(retry_gaps, only = NULL) {
    reset()
    run$index <- 1L; run$retry_gaps <- isTRUE(retry_gaps)
    run$modules <- if (is.function(deps$modules)) tryCatch(deps$modules(), error = function(error) NULL) else NULL
    run$only <- if (length(only)) intersect(as.character(only), names(DATA_REFRESH_ALL_STEPS_V1)) else NULL
    read_last()
    run$notice <- list(tone = "neutral", title = "Läuft", copy = paste(
      "Die Schritte stehen unten, mit der Zeit seit ihrem Beginn und der Dauer im letzten Lauf.",
      "Der Lauf läuft für sich: Andere Apps, Neuladen oder Schließen dieser Seite halten ihn nicht an. „Anhalten“ greift nach dem laufenden Asset oder Schritt."))
    run$started_at <- Sys.time()
    run$running <- TRUE
    invisible(NULL)
  }
  stop_run <- function() {
    if (!isTRUE(run$running)) return(invisible(NULL))
    if (run$steps[[run$index]]$code %in% c("prices", "gaps") && isTRUE(run$prices_started) && is.function(deps$prices_stop)) deps$prices_stop()
    set_step("stopped", "auf Wunsch angehalten; bereits Geschriebenes bleibt")
    finish("warning", "Angehalten", "Der Lauf wurde auf Wunsch angehalten. Ein neuer Lauf überspringt, was schon aktuell ist.")
  }
  tick <- function() {
    if (!isTRUE(run$running)) return(invisible(NULL))
    tryCatch(advance(), error = function(error) halt(pl_error_text_v1(safe_code(error))))
    invisible(NULL)
  }
  # Wartet der Lauf auf den Sammelabruf? Dann genuegt ein langsamerer Takt.
  waiting <- function() isTRUE(run$running) && run$index >= 1L && run$steps[[run$index]]$code %in% c("prices", "gaps") && isTRUE(run$prices_started)
  stamp <- function(value) if (is.null(value)) NULL else format(value, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  state <- function() list(running = isTRUE(run$running), index = as.integer(run$index), steps = run$steps, notice = run$notice,
    stands = run$stands, last = run$last, retry_gaps = isTRUE(run$retry_gaps), only = run$only,
    started_at_utc = stamp(run$started_at), finished_at_utc = stamp(run$finished_at))
  list(start = start, tick = tick, stop = stop_run, waiting = waiting, state = state, read_stands = read_stands, deps = deps,
       running = function() isTRUE(run$running))
}

# Die Karte (rc.315, #510): startet den Lauf als eigenen Prozess und zeigt seinen Stand aus der Statusdatei. Gerechnet wird hier
# nichts mehr; ein Wechsel in eine andere App, Neuladen oder Schliessen des Tabs laesst den Lauf weiterlaufen, und jede Data-Seite
# zeigt ihn wieder. deps:
# - store: data_refresh_all_store_v1 des Datenraums;
# - spawn(retry_gaps): startet den Prozess, gibt list(status = "started", run_id) oder list(status = "failed", code) zurueck;
# - blocked(): Grund, warum jetzt kein Lauf starten darf (Sammellauf im Reiter Marktdaten, offener Bewertungsentwurf), sonst NULL;
# - stands(as_of), today(), durations_read(): fuer „Stände neu lesen“ und die Richtwerte;
# - on_finished(state): einmal je beendetem Lauf, damit die Seite ihre Listen neu liest.
data_refresh_all_server_v1 <- function(input, output, session, deps) {
  view <- shiny::reactiveValues(state = NULL, holder = NULL, stands = NULL, notice = NULL, finished = NULL, watching = FALSE)
  read <- function() {
    state <- tryCatch(deps$store$read_state(), error = function(error) NULL)
    holder <- tryCatch(deps$store$holder(), error = function(error) NULL)
    view$state <- state; view$holder <- holder
    if (is.list(state) && is.list(state$stands)) view$stands <- state$stands
    # Ein Lauf ist zu Ende: einmal melden, damit Listen und Stand der Seite neu gelesen werden.
    if (is.list(state) && !isTRUE(state$running) && is.character(state$run_id) && !identical(view$finished, state$run_id)) {
      if (!is.null(view$finished) || isTRUE(view$watching)) tryCatch(if (is.function(deps$on_finished)) deps$on_finished(state), error = function(error) NULL)
      # Ein Hinweis zum laufenden Lauf („Anhalten angefordert“, „Läuft bereits“) gilt mit seinem Ende nicht mehr.
      if (!is.null(view$finished) || isTRUE(view$watching)) view$notice <- NULL
      view$finished <- state$run_id; view$watching <- FALSE
    }
    invisible(state)
  }
  # Laeuft er laut Statusdatei, aber ohne lebenden Prozess, ist er abgebrochen (etwa beim Herunterfahren des Rechners).
  running <- function() { state <- view$state; is.list(state) && isTRUE(state$running) && !is.null(view$holder) }
  orphaned <- function() { state <- view$state; is.list(state) && isTRUE(state$running) && is.null(view$holder) }
  shiny::observeEvent(input$refresh_all_start, {
    read()
    if (running()) {
      view$notice <- list(tone = "neutral", title = "Läuft bereits", copy = "Ein Lauf ist schon unterwegs; sein Stand steht unten.")
      return()
    }
    if (!isTRUE(input$refresh_all_confirm)) {
      view$notice <- list(tone = "warning", title = "Bestätigung fehlt",
        copy = "Der Lauf ruft Kurse beim Anbieter ab und schreibt Bewertungen, Tageshistorie, Snapshot, den Abschluss, die Momentaufnahme und die Datenbasis. Dafür das Häkchen setzen, dann erneut starten.")
      return()
    }
    blocked <- if (is.function(deps$blocked)) deps$blocked() else NULL
    if (is.character(blocked) && length(blocked) == 1L && nzchar(blocked)) {
      view$notice <- list(tone = "warning", title = "Jetzt nicht", copy = blocked); return()
    }
    shiny::updateCheckboxInput(session, "refresh_all_confirm", value = FALSE)
    started <- tryCatch(deps$spawn(isTRUE(input$refresh_all_retry_gaps)), error = function(error) list(status = "failed", code = conditionMessage(error)))
    if (!identical(started$status, "started")) {
      view$notice <- list(tone = "error", title = "Nicht gestartet", copy = pl_error_text_v1(started$code))
      return()
    }
    view$notice <- NULL; view$watching <- TRUE
    read()
  })
  shiny::observeEvent(input$refresh_all_stop, {
    read()
    state <- view$state
    if (!running()) return()
    tryCatch(deps$store$request_stop(state$run_id), error = function(error) NULL)
    view$notice <- list(tone = "neutral", title = "Anhalten angefordert", copy = "Der Lauf hält nach dem laufenden Asset oder Schritt an; bereits Geschriebenes bleibt.")
  })
  shiny::observeEvent(input$refresh_all_stands_read, {
    view$stands <- tryCatch(deps$stands(deps$today()), error = function(error) NULL)
  })
  # Gelesen wird beim Aufklappen des Bereichs in der Kopfzeile (#368), nicht beim Sitzungsstart.
  shiny::observeEvent(input$refresh_all_panel_open, {
    if (!isTRUE(input$refresh_all_panel_open)) return()
    read()
    if (is.null(view$stands)) view$stands <- tryCatch(deps$stands(deps$today()), error = function(error) NULL)
  }, ignoreInit = TRUE)
  # Solange ein Lauf unterwegs ist, alle zwei Sekunden den Stand lesen; sonst nur gelegentlich, falls ein anderer Tab startet.
  shiny::observe({
    shiny::invalidateLater(if (isTRUE(shiny::isolate(view$watching)) || shiny::isolate(running())) 2000L else 15000L)
    shiny::isolate(read())
  })
  output$refresh_all_stands_title <- shiny::renderUI({
    stands <- view$stands
    shiny::tags$h3(paste0("Stichtag heute, ", format(as.Date(deps$today()), "%d.%m.%Y"),
                          if (is.null(stands)) " · Stände noch nicht gelesen" else " · so weit reicht jede Datenart"))
  })
  output$refresh_all_stands <- shiny::renderTable(data_refresh_all_stands_frame_v1(view$stands), striped = TRUE, spacing = "xs")
  output$refresh_all_state <- shiny::renderUI({
    notice <- view$notice; state <- view$state
    panels <- list()
    if (is.list(notice)) panels[[length(panels) + 1L]] <- portelyra_status_panel(notice$title, notice$copy, tone = notice$tone)
    if (running()) panels[[length(panels) + 1L]] <- portelyra_status_panel("Läuft im Hintergrund", paste0(
      "Seit ", data_refresh_all_clock_v1(state$started_at_utc), " Uhr", if (identical(state$origin, "timer")) " (zeitgesteuert)" else "",
      ". Sie können die App wechseln oder diese Seite schließen; der Lauf geht weiter, und jede Seite der App „Daten“ zeigt ihn wieder."), tone = "neutral")
    else if (orphaned()) panels[[length(panels) + 1L]] <- portelyra_status_panel("Lauf unterbrochen",
      paste0("Der Lauf vom ", data_refresh_all_clock_v1(state$started_at_utc, TRUE), " Uhr endete ohne Abschluss, etwa weil der Rechner herunterfuhr. ",
             "Ein neuer Lauf überspringt, was schon aktuell ist."), tone = "warning")
    else if (is.list(state) && is.list(state$notice)) panels[[length(panels) + 1L]] <- portelyra_status_panel(
      paste0(state$notice$title, if (identical(state$origin, "timer")) " (zeitgesteuert)" else ""), paste0(state$notice$copy, if (!is.null(state$finished_at_utc)) paste0(" (Ende ", data_refresh_all_clock_v1(state$finished_at_utc, TRUE), " Uhr)") else ""),
      tone = state$notice$tone)
    if (length(panels)) shiny::tagList(panels) else NULL
  })
  output$refresh_all_steps <- shiny::renderTable({
    state <- view$state
    if (!is.list(state) || !length(state$steps) || identical(as.integer(state$index), 0L)) return(NULL)
    data_refresh_all_steps_frame_v1(state$steps, if (is.list(state$last)) state$last else list())
  }, striped = TRUE, spacing = "xs", sanitize.text.function = function(x) x)
  # halted: Der letzte Lauf hielt an einem Schritt an (#492) - dann stehen die Einzelschritte bereit.
  invisible(list(read = read, running = running, deps = deps,
    halted = function() { state <- view$state
      is.list(state) && any(vapply(state$steps, function(step) identical(step$status, "halted"), logical(1L))) }))
}

# Ortszeit eines Zeitpunkts aus der Statusdatei: "14:05" oder mit Tag "24.10.2026, 14:05".
data_refresh_all_clock_v1 <- function(value, with_day = FALSE) {
  at <- if (is.character(value) && length(value) == 1L) suppressWarnings(as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) else NA
  if (is.na(at)) return("–")
  format(at, if (with_day) "%d.%m.%Y, %H:%M" else "%H:%M", tz = "Europe/Berlin")
}

# Datenbasis nach Stammdatenpflege neu veroeffentlichen (rc.332, #422). Festlegung 27.10.2026: auf Knopfdruck, wenn die Pflege
# fertig ist - nicht bei jedem Oeffnen, denn Pruefen heisst die Datenbasis probeweise bauen.
# Veroeffentlicht wird nur, was Steuer und Analyse nicht neu rechnen muessen (Namen, neue Konten ohne Bewegung, Assets ohne
# Buchung und Bestand - auch mit Kursen, seit rc.334 -, Ablage, Anzeige). Ist mehr offen, bleibt es bei "Alles aktualisieren" - die Datenbasis zeigt nie Einstellungen oder Buchungen, mit
# denen noch nicht gerechnet wurde. Die Sperre des Laufs haelt einen gleichzeitigen Zeitlauf fern.
DATA_BASIS_SECTION_WORDS_V1 <- c(stands = "Stände je Datenart", accounts = "Konten und Buchungen", assets = "Assets und Kurse",
                                 fx = "Wechselkurse", statements = "Belege der Ablage", settings = "Einstellungen")
data_basis_names_ui_v1 <- function() shiny::div(class = "pl-basis-names",
  shiny::div(class = "pl-editor-actions",
    shiny::actionButton("data_basis_names_publish", "Datenbasis neu veröffentlichen", class = "btn-default"),
    shiny::span(class = "pl-field-hint", paste(
      "Wenn Sie mit der Pflege fertig sind: übernimmt geänderte Namen, neue Konten ohne Bewegung, Assets ohne Buchung (auch mit Kursen) und die Ablage in die Datenbasis,",
      "in Sekunden und ohne Kursabruf. Was Steuer und Analyse neu rechnen müssen, kommt mit „Alles aktualisieren“."))),
  shiny::uiOutput("data_basis_names_state"))

.data_basis_names_words_v1 <- function(codes) {
  codes <- unlist(codes, use.names = FALSE)
  if (!length(codes)) return("")
  paste(vapply(codes, function(code) if (code %in% names(DATA_BASIS_SECTION_WORDS_V1)) DATA_BASIS_SECTION_WORDS_V1[[code]] else code,
               character(1L)), collapse = ", ")
}
.data_basis_names_when_v1 <- function(utc) {
  parsed <- if (is.character(utc) && length(utc) == 1L) suppressWarnings(as.POSIXct(utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) else NA
  if (is.na(parsed)) "–" else format(parsed, "%d.%m.%Y %H:%M", tz = "")
}
data_basis_names_panel_v1 <- function(result) {
  if (is.null(result)) return(NULL)
  open_refresh <- shiny::tags$button(type = "button", class = "btn btn-default",
    onclick = "var p=document.getElementById('refresh-all-panel');if(p&&p.hasAttribute('hidden')){document.getElementById('refresh_all_toggle').click();}else if(p){p.scrollIntoView({behavior:'smooth',block:'start'});}",
    "„Alles aktualisieren“ öffnen")
  switch(as.character(result$status),
    published = portelyra_status_panel("Datenbasis neu veröffentlicht",
      paste0("Übernommen: ", .data_basis_names_words_v1(result$changed_sections), ". Das Cockpit meldet den neuen Stand."), tone = "positive"),
    already_published = portelyra_status_panel("Datenbasis ist schon auf diesem Stand", "Es gab nichts zu übernehmen."),
    blocked_calculation = shiny::tagList(portelyra_status_panel("Nicht veröffentlicht: erst „Alles aktualisieren“",
      paste0("Seit dem Stand vom ", .data_basis_names_when_v1(result$published_at_utc), " geändert, und damit rechnen Steuer und Analyse: ",
             .data_basis_names_words_v1(result$calculation_sections), ". „Alles aktualisieren“ rechnet neu und veröffentlicht die Datenbasis zum Schluss."),
      tone = "warning"), open_refresh),
    blocked_never_published = shiny::tagList(portelyra_status_panel("Noch keine Datenbasis veröffentlicht",
      "„Alles aktualisieren“ veröffentlicht sie zum ersten Mal.", tone = "warning"), open_refresh),
    blocked_unreadable = shiny::tagList(portelyra_status_panel("Die geltende Datenbasis ist nicht lesbar",
      "„Alles aktualisieren“ veröffentlicht sie neu.", tone = "warning"), open_refresh),
    refresh_running = portelyra_status_panel("„Alles aktualisieren“ läuft gerade",
      "Der Lauf veröffentlicht die Datenbasis zum Schluss selbst."),
    portelyra_status_panel("Nicht veröffentlicht", "Die Datenbasis ließ sich nicht prüfen. Nichts wurde geändert.", tone = "error"))
}

data_basis_names_server_v1 <- function(input, output, session, service, store, now_utc) {
  result <- shiny::reactiveVal(NULL)
  shiny::observeEvent(input$data_basis_names_publish, {
    if (is.null(service) || is.null(store)) { result(list(status = "failed")); return() }
    if (is.list(tryCatch(store$holder(), error = function(error) NULL))) { result(list(status = "refresh_running")); return() }
    run_id <- paste0("run_basis_names_", format(Sys.time(), "%Y%m%d%H%M%S", tz = "UTC"))
    if (!isTRUE(tryCatch(store$acquire(run_id, "data_basis_names"), error = function(error) FALSE))) { result(list(status = "refresh_running")); return() }
    on.exit(tryCatch(store$release(run_id), error = function(error) NULL), add = TRUE)
    result(tryCatch(service$basis_publish_names(now_utc()), error = function(error) list(status = "failed")))
  })
  output$data_basis_names_state <- shiny::renderUI(data_basis_names_panel_v1(result()))
  invisible(list(result = result))
}
