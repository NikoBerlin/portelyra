# Stand der Aktualisierung fuer den Block links in allen Apps (#540, rc.366): was laeuft, seit wann, wie weit - was zuletzt fertig
# wurde und welche Uhrzeiten geplant sind.
#
# Gebildet wird er hier aus Sperre, Stand und Zeitplan von „Alles aktualisieren“ (data_refresh_all_store_v1). Die Data-App zeigt
# ihn direkt; fuer Cockpit, Steuer und Analyse veroeffentlicht ihn der Hintergrundlauf (scripts/desktop_refresh_all.R) beim
# Start, bei jedem Schrittwechsel, alle paar Assets und am Ende - geprueft in Python (workers/reference/activity_status_publication_v1.py,
# Vertrag contracts/activity-status/v1). Ist nichts gesperrt oder laeuft der Sammellauf der eigenen Sitzung, veroeffentlicht die
# Data-App selbst, damit auch ein geaenderter Zeitplan und der Sammellauf in den anderen Apps erscheinen. Keine Kennungen des
# Bestands, keine Betraege, kein Provider, kein Netz.

# R vor 4.4 (Ubuntu 24.04 bringt 4.3.3) kennt `%||%` nicht in base, Shiny liefert ihn nicht (Endabnahme 19.11.2026).
if (!exists("%||%", mode = "function")) `%||%` <- function(x, y) if (is.null(x)) y else x
DATA_ACTIVITY_KIND_OF_ORIGIN_V1 <- c(app = "refresh", timer = "refresh", timer_moment = "moment", app_sweep = "sweep",
                                     data_basis_names = "names", maintenance = "maintenance")
DATA_ACTIVITY_TONES_V1 <- c("positive", "neutral", "warning", "error")

.data_activity_utc_v1 <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value) || !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", value)) return(NULL)
  value
}
.data_activity_time_v1 <- function(value) {
  value <- .data_activity_utc_v1(value)
  if (is.null(value)) NA else suppressWarnings(as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
}
.data_activity_stamp_v1 <- function(time) format(time, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
.data_activity_count_v1 <- function(value) {
  value <- suppressWarnings(as.integer(value))
  if (length(value) == 1L && !is.na(value) && value >= 0L) value else NULL
}
.data_activity_text_v1 <- function(value, limit) {
  if (!is.character(value) || length(value) != 1L || is.na(value)) return(NULL)
  value <- trimws(gsub("[[:cntrl:]]+", " ", value))
  if (!nzchar(value)) return(NULL)
  if (nchar(value) > limit) paste0(substr(value, 1L, limit - 1L), "…") else value
}

# Die Schritte, die dieser Lauf wirklich durchgeht: nur die gewaehlten (Momentaufnahme), ohne Quellluecken, wenn nicht gewaehlt.
.data_activity_codes_v1 <- function(state) {
  codes <- vapply(state$steps, function(step) as.character(step$code)[1L], character(1L))
  only <- as.character(unlist(state$only))
  if (length(only)) codes <- codes[codes %in% only]
  if (!isTRUE(state$retry_gaps)) codes <- setdiff(codes, "gaps")
  codes
}

# Voraussichtliches Ende: der laufende Schritt nach seinem bisherigen Tempo (ab drei erledigten Assets) oder nach seiner Dauer im
# letzten Lauf, dazu die Dauer der folgenden Schritte im letzten Lauf. Fehlt einem davon die Dauer, gibt es keine Schaetzung -
# lieber nichts als eine zu kurze. Auf die Minute gerundet, damit nicht jeder Takt einen neuen Stand ergibt.
data_activity_expected_end_v1 <- function(state, now = Sys.time()) {
  steps <- state$steps; index <- suppressWarnings(as.integer(state$index))
  if (!length(steps) || length(index) != 1L || is.na(index) || index < 1L || index > length(steps)) return(NULL)
  last <- if (is.list(state$last)) state$last else list()
  seconds_of <- function(code) {
    value <- suppressWarnings(as.numeric(last[[code]]))
    if (length(value) == 1L && !is.na(value) && value >= 0) value else NA_real_
  }
  step <- steps[[index]]
  started <- suppressWarnings(as.numeric(step$started_ms))
  elapsed <- if (length(started) == 1L && !is.na(started)) max(0, as.numeric(now) - started / 1000) else 0
  done <- .data_activity_count_v1(step$done); total <- .data_activity_count_v1(step$total)
  current <- if (!is.null(total) && !is.null(done) && total > 0L && done >= 3L && elapsed > 0) elapsed / done * max(0L, total - done)
             else max(0, seconds_of(as.character(step$code)) - elapsed)
  codes <- .data_activity_codes_v1(state)
  following <- if (index < length(steps)) vapply(steps[(index + 1L):length(steps)], function(item) as.character(item$code)[1L], character(1L)) else character()
  rest <- sum(vapply(following[following %in% codes], seconds_of, numeric(1L)))
  if (is.na(current) || is.na(rest)) return(NULL)
  end <- as.POSIXct(round((as.numeric(now) + current + rest) / 60) * 60, origin = "1970-01-01", tz = "UTC")
  .data_activity_stamp_v1(end)
}

.data_activity_running_row_v1 <- function(holder, state, sweep_progress, now) {
  origin <- as.character(holder$origin)[1L]
  kind <- if (isTRUE(origin %in% names(DATA_ACTIVITY_KIND_OF_ORIGIN_V1))) unname(DATA_ACTIVITY_KIND_OF_ORIGIN_V1[[origin]]) else "other"
  row <- list(kind = kind,
              origin = if (isTRUE(origin %in% c("app", "app_sweep", "data_basis_names"))) "app" else if (isTRUE(origin %in% c("timer", "timer_moment"))) "timer" else "other",
              started_at_utc = .data_activity_utc_v1(holder$started_at_utc), step_label = NULL, step_position = NULL, step_count = NULL,
              done = NULL, total = NULL, expected_end_utc = NULL)
  if (kind %in% c("refresh", "moment") && is.list(state) && isTRUE(state$running) && length(state$steps)) {
    index <- suppressWarnings(as.integer(state$index))
    if (length(index) == 1L && !is.na(index) && index >= 1L && index <= length(state$steps)) {
      step <- state$steps[[index]]
      codes <- .data_activity_codes_v1(state)
      position <- match(as.character(step$code)[1L], codes)
      # Mit ["..."] <- list(): Ein NULL bleibt als Feld stehen (JSON null); $<- NULL striche es.
      row["started_at_utc"] <- list(.data_activity_utc_v1(state$started_at_utc) %||% row$started_at_utc)
      row["step_label"] <- list(.data_activity_text_v1(as.character(step$label)[1L], 80L))
      if (!is.na(position)) { row$step_position <- as.integer(position); row$step_count <- length(codes) }
      done <- .data_activity_count_v1(step$done); total <- .data_activity_count_v1(step$total)
      if (identical(step$status, "running") && !is.null(done) && !is.null(total) && done <= total) { row$done <- done; row$total <- total }
      row["expected_end_utc"] <- list(data_activity_expected_end_v1(state, now))
    }
  }
  if (identical(kind, "sweep") && is.list(sweep_progress)) {
    done <- .data_activity_count_v1(sweep_progress$done); total <- .data_activity_count_v1(sweep_progress$total)
    if (!is.null(done) && !is.null(total) && done <= total) { row$done <- done; row$total <- total }
  }
  row
}

# Zuletzt beendet: aus dem Stand, solange kein neuer Lauf ihn ueberschrieben hat, sonst aus last-run.json (schreibt der Lauf an
# seinem Ende). Laeuft der Stand ohne lebende Sperre, endete der Lauf ohne Abschluss.
.data_activity_last_v1 <- function(state, finished, holder) {
  summary <- function(value) {
    at <- .data_activity_utc_v1(value$finished_at_utc)
    if (is.null(at)) return(NULL)
    started <- .data_activity_time_v1(value$started_at_utc); ended <- .data_activity_time_v1(at)
    seconds <- if (!is.na(started) && !is.na(ended)) max(0L, as.integer(round(as.numeric(difftime(ended, started, units = "secs"))))) else NULL
    notice <- if (is.list(value$notice)) value$notice else list()
    tone <- as.character(notice$tone)[1L]
    list(finished_at_utc = at, title = .data_activity_text_v1(as.character(notice$title)[1L], 120L) %||% "Beendet",
         tone = if (isTRUE(tone %in% DATA_ACTIVITY_TONES_V1)) tone else "neutral", seconds = seconds)
  }
  if (is.list(state) && isTRUE(state$running)) {
    if (!(is.list(holder) && identical(holder$run_id, state$run_id))) {
      at <- .data_activity_utc_v1(state$updated_at_utc)
      if (!is.null(at)) return(list(finished_at_utc = at, title = "Lauf unterbrochen", tone = "warning", seconds = NULL))
    }
    return(if (is.list(finished)) summary(finished) else NULL)
  }
  if (is.list(state)) { value <- summary(state); if (!is.null(value)) return(value) }
  if (is.list(finished)) summary(finished) else NULL
}

.data_activity_next_v1 <- function(value) {
  enabled <- is.list(value) && isTRUE(value$enabled)
  times <- if (is.list(value) && exists(".data_refresh_all_schedule_times_of_v1", mode = "function")) .data_refresh_all_schedule_times_of_v1(value) else character()
  times <- utils::head(sort(unique(as.character(times[grepl("^([01][0-9]|2[0-3]):[0-5][0-9]$", times)]))), 6L)
  list(enabled = enabled, times = as.list(times))
}

# store: data_refresh_all_store_v1; sweep_progress: list(done, total) des Sammellaufs dieser Sitzung oder NULL.
data_activity_status_v1 <- function(store, sweep_progress = NULL, now = Sys.time()) {
  holder <- tryCatch(store$holder(), error = function(error) NULL)
  states <- list(refresh = tryCatch(store$read_state("refresh"), error = function(error) NULL),
                 moment = tryCatch(store$read_state("moment"), error = function(error) NULL))
  finished <- list(refresh = tryCatch(store$read_last_run("refresh"), error = function(error) NULL),
                   moment = tryCatch(store$read_last_run("moment"), error = function(error) NULL))
  running <- list()
  if (is.list(holder)) {
    # Der Stand des Laufs, der gerade sperrt - je nach Art in state.json oder state-moment.json.
    state <- Filter(function(value) is.list(value) && identical(value$run_id, holder$run_id), states)
    running <- list(.data_activity_running_row_v1(holder, if (length(state)) state[[1L]] else NULL, sweep_progress, now))
  }
  schedule <- tryCatch(store$read_schedule(), error = function(error) NULL)
  list(running = running,
       last = list(refresh = .data_activity_last_v1(states$refresh, finished$refresh, holder),
                   moment = .data_activity_last_v1(states$moment, finished$moment, holder)),
       `next` = list(refresh = .data_activity_next_v1(schedule), moment = .data_activity_next_v1(if (is.list(schedule)) schedule$moment else NULL)))
}

# Veroeffentlicht den Stand ueber scripts/desktop_activity_status.py, wenn er sich geaendert hat. Geprueft wird hoechstens alle
# `check_seconds`; innerhalb eines Schritts kommt ein neuer Fortschritt hoechstens alle `min_seconds`, ein Schrittwechsel sofort.
# Ein Fehler beim Veroeffentlichen haelt nie den Lauf an - die Anzeige ist Auskunft, kein Teil der Rechnung.
data_activity_publisher_v1 <- function(project_root, context, build, check_seconds = 2, min_seconds = 20, runner = NULL, clock = Sys.time) {
  python <- Sys.which("python3")
  cli <- file.path(project_root, "scripts", "desktop_activity_status.py")
  # Wie in der Data-App und im Hintergrundlauf: spotcore ist dort angehaengt.
  space <- tryCatch(runtime_data_space_path(context), error = function(error) NULL)
  payload_context <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id)
  run <- runner %||% function(payload) {
    if (!nzchar(python) || !file.exists(cli) || is.null(space)) return(list(status = "blocked", code = "activity_status_publication_failed"))
    encoded <- as.character(jsonlite::toJSON(payload, auto_unbox = TRUE, null = "null", na = "null", digits = NA))
    output <- tryCatch(suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), "publish"), stdout = TRUE, stderr = FALSE, input = encoded)),
                       error = function(error) character())
    tryCatch(jsonlite::fromJSON(output[[length(output)]], simplifyVector = FALSE), error = function(error) list(status = "blocked"))
  }
  memory <- new.env(parent = emptyenv())
  memory$checked <- -Inf; memory$published <- -Inf; memory$digest <- NULL; memory$key <- NULL
  key_of <- function(status) paste(vapply(status$running, function(row) paste(row$kind, row$step_position %||% "-", sep = ":"), character(1L)), collapse = ";")
  tick <- function(force = FALSE) {
    now <- as.numeric(clock())
    if (!force && now - memory$checked < check_seconds) return(invisible("waiting"))
    memory$checked <- now
    status <- tryCatch(build(), error = function(error) NULL)
    if (!is.list(status)) return(invisible("failed"))
    digest <- digest::digest(status)
    if (identical(digest, memory$digest)) return(invisible("unchanged"))
    key <- key_of(status)
    if (!force && identical(key, memory$key) && now - memory$published < min_seconds) return(invisible("deferred"))
    result <- tryCatch(run(list(context = payload_context, data_space_path = space, status = status,
                                published_at_utc = .data_activity_stamp_v1(as.POSIXct(now, origin = "1970-01-01", tz = "UTC")))),
                       error = function(error) list(status = "blocked"))
    memory$published <- now; memory$key <- key
    if (is.list(result) && identical(result$status, "completed")) { memory$digest <- digest; return(invisible("published")) }
    invisible("failed")
  }
  list(tick = tick)
}

# Fuer den Block links der Data-App: liest den Stand direkt (marker bildet ihn, read gibt ihn zurueck) und veroeffentlicht ihn,
# wenn niemand sperrt oder der Sammellauf dieser Sitzung sperrt. Waehrend eines Hintergrundlaufs veroeffentlicht nur dieser.
# Nicht beim ersten Lesen: Der Aufruf nach Python gehoert nicht in den Sitzungsstart.
data_activity_source_v1 <- function(store, publisher = NULL, sweep_progress = function() NULL, own_lock = function() NULL) {
  current <- NULL; first <- TRUE
  list(
    marker = function() {
      progress <- tryCatch(sweep_progress(), error = function(error) NULL)
      current <<- data_activity_status_v1(store, progress)
      holder <- tryCatch(store$holder(), error = function(error) NULL)
      mine <- tryCatch(own_lock(), error = function(error) NULL)
      if (!first && !is.null(publisher) && (is.null(holder) || (is.character(mine) && identical(holder$run_id, mine))))
        tryCatch(publisher$tick(), error = function(error) NULL)
      first <<- FALSE
      digest::digest(current)
    },
    read = function() c(list(status = "available"), current))
}

# Aus Cockpit, Steuer oder Analyse kommend (#pl-open=refresh|settings|program in der Adresse): den Bereich aufklappen, sobald die Sitzung
# steht, und den Zusatz wieder entfernen, damit Neuladen ihn nicht erneut oeffnet. "program" (#562) oeffnet die Einstellungen beim Reiter
# „Programm“ (Version und „Neu in dieser Version“).
data_activity_open_from_hash_v1 <- function() shiny::tags$script(shiny::HTML(paste0(
  "(function(){var m=/pl-open=(refresh|settings|program)/.exec(window.location.hash||'');if(!m){return;}var done=false;",
  "var ids=m[1]==='refresh'?['refresh_all_toggle','refresh-all-panel']:['settings_toggle','settings-panel'];",
  "function go(){if(done){return;}var b=document.getElementById(ids[0]),p=document.getElementById(ids[1]);if(!b||!p){return;}done=true;",
  "if(p.hasAttribute('hidden')){b.click();}",
  "if(m[1]==='program'){var a=document.querySelector('#settings-panel a[data-value=\"program\"]');if(a&&window.jQuery){jQuery(a).tab('show');}",
  "setTimeout(function(){var t=document.getElementById('data-program-version');if(t){t.scrollIntoView({behavior:'smooth',block:'start'});}},150);}",
  "try{history.replaceState(null,'',window.location.pathname+window.location.search);}catch(e){}}",
  "$(document).one('shiny:sessioninitialized',function(){$(document).one('shiny:idle',function(){setTimeout(go,200);});setTimeout(go,4000);});})();")))
