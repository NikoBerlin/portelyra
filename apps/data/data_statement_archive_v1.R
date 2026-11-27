# Ablage fuer Original-Auszuege in der Data-App: Dienst, Bereich und Ablauf.
#
# Festlegung (13.10.2026): Auszuege im Programm hinterlegen, bestaetigen und wieder abrufen; je Konto und Monat sehen,
# was belegt ist. Vorgaben: beliebig viele Dateien, keine Kopien fuer saubere Zeitraeume, jahresweise arbeiten und
# monatsweise ausweisen, nichts verlangen, was es nicht gibt, Institut als Oberklasse mit den Konten darunter.
# Die Ablage liegt neben Stammdaten und Buchungsbestand und beruehrt beide nicht. Kein Providerzugriff, kein Netzzugriff.
data_statement_archive_abort_v1 <- function(code) {
  # Seit rc.317 auch die Codes des Eingangs (#513).
  if (!is.character(code) || length(code) != 1L || !grepl("^statement_(archive|intake)_[a-z_]+$", code)) code <- "statement_archive_store_invalid"
  stop(structure(list(message = code, call = NULL, code = code),
    class = c("spot_data_statement_archive_error_v1", "error", "condition")))
}
data_statement_archive_kinds_v1 <- function() c(Kontoauszug = "account_statement", Depotauszug = "securities_statement",
  Transaktionsexport = "transaction_export", Jahressteuerbescheinigung = "tax_certificate", `Erträgnisaufstellung` = "income_statement",
  Vorabpauschale = "advance_lump_sum", `Bestätigung / Abrechnung` = "confirmation", Sonstiges = "other")
# Jahresdokumente (#536, Festlegung 04.11.2026) liegen in der Ablage, decken aber keinen Monat im Raster - ebenso "Sonstiges".
data_statement_archive_year_kinds_v1 <- function() c("tax_certificate", "income_statement", "advance_lump_sum")
data_statement_archive_kind_label_v1 <- function(kind) {
  kinds <- data_statement_archive_kinds_v1(); hit <- names(kinds)[kinds == kind]
  if (length(hit) == 1L) hit else "—"
}
# Stand eines Monats: Zeichen fuer das Raster und Wort fuer die Legende.
data_statement_archive_month_states_v1 <- function() list(
  confirmed = c("●", "belegt, bestätigt"), unconfirmed = c("◐", "hinterlegt, unbestätigt"),
  not_available = c("✕", "nicht mehr vorhanden (manuell bestätigt)"), open = c("○", "offen: Bewegung ohne Beleg"),
  no_movement = c("·", "keine Bewegung"), not_expected = c("–", "für dieses Konto gibt es keine Auszüge"),
  closed = c("⊘", "Konto geschlossen"), inactive = c("◌", "Konto ruht (inaktiv)"))
data_statement_archive_status_label_v1 <- function(status) switch(as.character(status),
  unconfirmed = "hinterlegt, unbestätigt", confirmed = "bestätigt", not_available = "nicht mehr vorhanden (manuell bestätigt)",
  withdrawn = "zurückgezogen", as.character(status))
data_statement_archive_month_valid_v1 <- function(value) is.character(value) && length(value) == 1L && !is.na(value) && grepl("^(19|20)[0-9]{2}-(0[1-9]|1[0-2])$", value)
data_statement_archive_month_choices_v1 <- function(current_year = as.integer(format(Sys.Date(), "%Y"))) {
  years <- seq.int(as.integer(current_year) + 1L, as.integer(current_year) - 12L)
  unlist(lapply(years, function(year) sprintf("%04d-%02d", year, 12:1)))
}
data_statement_archive_text_v1 <- function(value) {
  if (is.null(value) || !is.character(value) || length(value) != 1L || is.na(value)) return(NULL)
  text <- gsub("[ \t]+", " ", trimws(value))
  if (nzchar(text)) text else NULL
}
new_data_statement_archive_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_statement_archive.py")
  space <- runtime_data_space_path(context)
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_statement_archive_abort_v1("statement_archive_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
    actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      data_statement_archive_abort_v1(if (is.null(parsed$code)) "statement_archive_store_invalid" else parsed$code)
    parsed$result
  }
  checked <- function(result, states) {
    if (!is.list(result) || !is.character(result$status) || !result$status %in% states || isTRUE(result$canonical_write))
      data_statement_archive_abort_v1("statement_archive_store_invalid")
    result
  }
  account_valid <- function(value) is.character(value) && length(value) >= 1L && !anyNA(value) && all(grepl("^acc_[a-z0-9_]{4,60}$", value)) && !anyDuplicated(value)
  document_valid <- function(value) is.character(value) && length(value) == 1L && !is.na(value) && grepl("^sdoc_[a-f0-9]{32}$", value)
  placement <- function(period_from, period_to, account_ids, institution_label, note) {
    if (!data_statement_archive_month_valid_v1(period_from) || !data_statement_archive_month_valid_v1(period_to) || period_to < period_from || !account_valid(account_ids))
      data_statement_archive_abort_v1("statement_archive_input_invalid")
    list(period_from = period_from, period_to = period_to, account_ids = as.list(unname(account_ids)),
      institution_label = data_statement_archive_text_v1(institution_label), note = data_statement_archive_text_v1(note))
  }
  confirmed_only <- function(confirmed) if (!isTRUE(confirmed)) data_statement_archive_abort_v1("statement_archive_confirmation_required")
  structure(list(
    contract_version = "data_statement_archive_service_v1",
    overview = function(year) {
      year <- suppressWarnings(as.integer(year))
      if (length(year) != 1L || is.na(year) || year < 1990L || year > 2100L) data_statement_archive_abort_v1("statement_archive_input_invalid")
      result <- checked(run("overview", list(year = year)), "ready")
      if (!is.list(result$institutions) || !is.list(result$documents) || !identical(as.integer(result$year), year)) data_statement_archive_abort_v1("statement_archive_store_invalid")
      result
    },
    store = function(source_path, original_name, document_kind, period_from, period_to, account_ids, institution_label, note, recorded_at_utc, confirmed) {
      kinds <- unname(data_statement_archive_kinds_v1())
      if (!is.character(source_path) || length(source_path) != 1L || is.na(source_path) || !file.exists(source_path) || nzchar(Sys.readlink(source_path)) ||
          !is.character(original_name) || length(original_name) != 1L || is.na(original_name) || !nzchar(trimws(original_name)) ||
          !is.character(document_kind) || length(document_kind) != 1L || !document_kind %in% kinds) data_statement_archive_abort_v1("statement_archive_input_invalid")
      document <- c(list(document_kind = document_kind), placement(period_from, period_to, account_ids, institution_label, note))
      confirmed_only(confirmed)
      checked(run("store", list(source_path = normalizePath(source_path, winslash = "/", mustWork = TRUE), original_name = original_name, document = document,
        recorded_at_utc = recorded_at_utc, confirmed = TRUE)), c("stored", "unchanged"))
    },
    declare = function(period_from, period_to, account_ids, institution_label, note, recorded_at_utc, confirmed) {
      declaration <- placement(period_from, period_to, account_ids, institution_label, note)
      confirmed_only(confirmed)
      checked(run("declare", list(declaration = declaration, recorded_at_utc = recorded_at_utc, confirmed = TRUE)), "declared")
    },
    # Stand eines Dokuments aendern: "confirmed", "unconfirmed" oder "withdrawn".
    set_status = function(document_ref, status, recorded_at_utc, confirmed) {
      if (!document_valid(document_ref) || !is.character(status) || length(status) != 1L || !status %in% c("confirmed", "unconfirmed", "withdrawn"))
        data_statement_archive_abort_v1("statement_archive_input_invalid")
      confirmed_only(confirmed)
      checked(run("revise", list(document_ref = document_ref, changes = list(status = status), recorded_at_utc = recorded_at_utc, confirmed = TRUE)), c("revised", "unchanged"))
    },
    # Art eines Dokuments aendern (#536): neuer Stand, der alte bleibt in der Ablage.
    set_kind = function(document_ref, document_kind, recorded_at_utc, confirmed) {
      if (!document_valid(document_ref) || !is.character(document_kind) || length(document_kind) != 1L || !document_kind %in% unname(data_statement_archive_kinds_v1()))
        data_statement_archive_abort_v1("statement_archive_input_invalid")
      confirmed_only(confirmed)
      checked(run("revise", list(document_ref = document_ref, changes = list(document_kind = document_kind), recorded_at_utc = recorded_at_utc, confirmed = TRUE)), c("revised", "unchanged"))
    },
    expect = function(account_id, statements_expected, recorded_at_utc, confirmed) {
      if (!account_valid(account_id) || length(account_id) != 1L || !is.logical(statements_expected) || length(statements_expected) != 1L || is.na(statements_expected))
        data_statement_archive_abort_v1("statement_archive_input_invalid")
      confirmed_only(confirmed)
      checked(run("expect", list(account_id = account_id, statements_expected = statements_expected, recorded_at_utc = recorded_at_utc, confirmed = TRUE)), c("recorded", "unchanged"))
    },
    close = function(year, account_ids, declare_rest, recorded_at_utc, confirmed) {
      year <- suppressWarnings(as.integer(year))
      if (length(year) != 1L || is.na(year) || !account_valid(account_ids) || !is.logical(declare_rest) || length(declare_rest) != 1L || is.na(declare_rest))
        data_statement_archive_abort_v1("statement_archive_input_invalid")
      confirmed_only(confirmed)
      checked(run("close", list(year = year, account_ids = as.list(unname(account_ids)), declare_rest = declare_rest, recorded_at_utc = recorded_at_utc, confirmed = TRUE)), "closed")
    },
    file = function(document_ref) {
      if (!document_valid(document_ref)) data_statement_archive_abort_v1("statement_archive_input_invalid")
      result <- checked(run("file", list(document_ref = document_ref)), "ready")
      if (!is.character(result$path) || length(result$path) != 1L || !file.exists(result$path)) data_statement_archive_abort_v1("statement_archive_file_invalid")
      result
    },
    # Quelle der Importe (#434): die hinterlegten Dateien fuer Konten und Jahre, je Datei einmal, mit Pruefwert.
    files = function(account_ids, year_from, year_to, kinds = NULL) {
      years <- suppressWarnings(as.integer(c(year_from, year_to)))
      if (!account_valid(account_ids) || length(years) != 2L || anyNA(years) || (!is.null(kinds) && (!is.character(kinds) || !length(kinds) ||
          !all(kinds %in% unname(data_statement_archive_kinds_v1()))))) data_statement_archive_abort_v1("statement_archive_input_invalid")
      result <- checked(run("files", list(account_ids = as.list(unname(account_ids)), year_from = years[[1L]], year_to = years[[2L]],
        kinds = if (is.null(kinds)) NULL else as.list(unname(kinds)))), "ready")
      if (!is.list(result$files)) data_statement_archive_abort_v1("statement_archive_store_invalid")
      result$files
    },
    # Datei eines zurueckgezogenen Dokuments endgueltig entfernen (#434).
    remove = function(document_ref, recorded_at_utc, confirmed) {
      if (!document_valid(document_ref)) data_statement_archive_abort_v1("statement_archive_input_invalid")
      confirmed_only(confirmed)
      checked(run("remove", list(document_ref = document_ref, recorded_at_utc = recorded_at_utc, confirmed = TRUE)), c("removed", "unchanged"))
    },
    # Vorschlag je Datei (#434): Art, Zeitraum und Konten aus dem Inhalt. Schreibt nichts.
    suggest = function(paths, names) {
      if (!is.character(paths) || !is.character(names) || length(paths) != length(names) || !length(paths)) data_statement_archive_abort_v1("statement_archive_input_invalid")
      result <- checked(run("suggest", list(sources = lapply(seq_along(paths), function(index) list(path = normalizePath(paths[[index]], winslash = "/", mustWork = TRUE), name = names[[index]])))), "ready")
      if (!is.list(result$files) || length(result$files) != length(paths)) data_statement_archive_abort_v1("statement_archive_store_invalid")
      result
    },
    # Konto geschlossen seit (#513): ein Tag "JJJJ-MM-TT" oder NULL (wieder offen).
    closure = function(account_id, closed_on, recorded_at_utc, confirmed) {
      if (!account_valid(account_id) || length(account_id) != 1L || !(is.null(closed_on) || (is.character(closed_on) && length(closed_on) == 1L &&
          grepl("^(19|20)[0-9]{2}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$", closed_on)))) data_statement_archive_abort_v1("statement_archive_input_invalid")
      confirmed_only(confirmed)
      checked(run("closure", list(account_id = account_id, closed_on = closed_on, recorded_at_utc = recorded_at_utc, confirmed = TRUE)), c("recorded", "unchanged"))
    },
    # Konto inaktiv seit (#529 Punkt 1): ein Tag "JJJJ-MM-TT" oder NULL (wieder aktiv).
    inactivity = function(account_id, inactive_since, recorded_at_utc, confirmed) {
      if (!account_valid(account_id) || length(account_id) != 1L || !(is.null(inactive_since) || (is.character(inactive_since) && length(inactive_since) == 1L &&
          grepl("^(19|20)[0-9]{2}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$", inactive_since)))) data_statement_archive_abort_v1("statement_archive_input_invalid")
      confirmed_only(confirmed)
      checked(run("inactivity", list(account_id = account_id, inactive_since = inactive_since, recorded_at_utc = recorded_at_utc, confirmed = TRUE)), c("recorded", "unchanged"))
    },
    # Zustand je Konto (geschlossen seit, inaktiv seit, geruht bis zum Reaktivieren) - fuer Eingang, Importe und Datenbasis. Liest nur.
    account_states = function() {
      result <- checked(run("account-states", list()), "ready")
      if (!is.list(result$accounts)) data_statement_archive_abort_v1("statement_archive_store_invalid")
      result$accounts
    },
    # Monatlicher Eingang (#513): Belegordner, Rezepte, pruefen (liest nur) und je Institut ablegen.
    intake_folder = function(folder, recorded_at_utc, confirmed) {
      if (!(is.null(folder) || (is.character(folder) && length(folder) == 1L && !is.na(folder) && nzchar(folder)))) data_statement_archive_abort_v1("statement_archive_input_invalid")
      confirmed_only(confirmed)
      checked(run("intake-folder", list(folder = folder, recorded_at_utc = recorded_at_utc, confirmed = TRUE)), c("recorded", "unchanged"))
    },
    intake_read = function() {
      result <- checked(run("intake-read", list()), "ready")
      if (!is.list(result$recipes)) data_statement_archive_abort_v1("statement_archive_store_invalid")
      result
    },
    # include_withdrawn (rc.320): zurueckgezogene Dateien erneut vorschlagen, nur auf ausdrueckliche Wahl.
    intake_scan = function(include_withdrawn = FALSE) {
      result <- checked(run("intake-scan", list(include_withdrawn = isTRUE(include_withdrawn))), "ready")
      if (!is.list(result$institutions)) data_statement_archive_abort_v1("statement_archive_store_invalid")
      result
    },
    intake_store = function(folder_name, fingerprint, recorded_at_utc, confirmed, include_withdrawn = FALSE) {
      if (!is.character(folder_name) || length(folder_name) != 1L || !nzchar(folder_name) || !is.character(fingerprint) || length(fingerprint) != 1L ||
          !grepl("^[a-f0-9]{64}$", fingerprint)) data_statement_archive_abort_v1("statement_archive_input_invalid")
      confirmed_only(confirmed)
      checked(run("intake-store", list(folder_name = folder_name, fingerprint = fingerprint, recorded_at_utc = recorded_at_utc, confirmed = TRUE,
        include_withdrawn = isTRUE(include_withdrawn))), c("stored", "unchanged"))
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_data_statement_archive_service_v1", "list"))
}
# Die Konten der Oberflaeche mit ihrer Kennung: Auswahl -> Kennung und zurueck. Die Kennung bleibt im Prozess.
# Die Kennungen der ruhenden Konten (#529 Punkt 1) - leer, wenn die Ablage fehlt oder nicht lesbar ist.
data_resting_account_ids_v1 <- function(service) {
  if (is.null(service)) return(character())
  states <- tryCatch(service$account_states(), error = function(error) list())
  names(Filter(function(state) is.list(state) && !is.null(state$inactive_since), states))
}
# `states` (#529 Punkt 1): Zustand je Kennung aus service$account_states(). Ein ruhendes Konto traegt den Zusatz "(ruht)";
# mit skip_inactive = TRUE faellt es weg - so bieten Eingang und Importe es nicht an, die Ablage zeigt es zum Wiederaktivieren.
data_statement_archive_accounts_v1 <- function(accounts, resolve_id, states = NULL, skip_inactive = FALSE) {
  rows <- list()
  for (account in accounts) {
    if (!is.list(account) || identical(account$status, "archived")) next
    id <- tryCatch(resolve_id(account$ref), error = function(error) NULL)
    if (!is.character(id) || length(id) != 1L) next
    resting <- is.list(states) && is.list(states[[id]]) && !is.null(states[[id]]$inactive_since)
    if (resting && isTRUE(skip_inactive)) next
    institution <- data_statement_archive_text_v1(account$institution_label)
    rows[[length(rows) + 1L]] <- list(ref = account$ref, id = id, name = paste0(as.character(account$display_name), if (resting) " (ruht)" else ""),
                                      institution = if (is.null(institution)) "" else institution)
  }
  rows[order(vapply(rows, function(row) tolower(row$name), character(1L)))]
}
data_statement_archive_institutions_v1 <- function(rows) {
  labels <- unique(vapply(rows, function(row) row$institution, character(1L)))
  named <- sort(labels[nzchar(labels)]); choices <- stats::setNames(named, named)
  if (any(!nzchar(labels))) choices <- c(choices, `ohne Institutsangabe` = "")
  choices
}
# Welches Institut die Auswahl zeigt: beim ersten Fuellen das erste der Liste, danach das gewaehlte, solange es noch dazugehoert.
# Der leere Wert ist zugleich der Platzhalter der Auswahl und die Gruppe "ohne Institutsangabe" - er darf nicht von selbst gewaehlt sein.
data_statement_archive_default_institution_v1 <- function(choices, current, filled) {
  if (!length(choices)) return(NULL)
  if (isTRUE(filled) && is.character(current) && length(current) == 1L && current %in% choices) current else unname(choices[[1L]])
}
# Das Jahresraster: je Institut seine Konten, je Konto zwoelf Monate. Kennungen stehen nicht darin.
data_statement_archive_grid_v1 <- function(overview) {
  states <- data_statement_archive_month_states_v1()
  lapply(overview$institutions, function(group) list(
    institution = if (is.null(group$institution_label)) "ohne Institutsangabe" else as.character(group$institution_label),
    accounts = lapply(group$accounts, function(account) list(name = paste0(as.character(account$account_label),
      if (!is.null(account$closed_on)) paste0(" (geschlossen seit ", format(as.Date(account$closed_on), "%d.%m.%Y"), ")") else "",
      if (!is.null(account$inactive_since)) paste0(" (inaktiv seit ", pl_day_v1(account$inactive_since), ")") else "",
      if (!is.null(account$was_inactive_since)) paste0(" (ruhte ", pl_day_v1(account$was_inactive_since), "–", pl_day_v1(account$reactivated_on),
        ": Auszüge nachladen)") else ""),
      cells = vapply(account$months, function(cell) {
        state <- states[[as.character(cell$status)]]; mark <- if (is.null(state)) "?" else state[[1L]]
        if (isTRUE(cell$via_institution) && cell$status %in% c("confirmed", "unconfirmed", "not_available")) paste0(mark, "ᴵ") else mark
      }, character(1L))))))
}
data_statement_archive_document_rows_v1 <- function(overview, account_rows) {
  ids <- vapply(account_rows, function(row) row$id, character(1L))
  names_by_id <- stats::setNames(vapply(account_rows, function(row) row$name, character(1L)), ids)
  institution_by_id <- stats::setNames(vapply(account_rows, function(row) if (is.null(row$institution)) "" else as.character(row$institution), character(1L)), ids)
  lapply(overview$documents, function(document) {
    accounts <- vapply(document$account_ids, function(id) { name <- unname(names_by_id[as.character(id)]); if (is.na(name)) "archiviertes Konto" else name }, character(1L))
    institutions <- vapply(document$account_ids, function(id) { label <- unname(institution_by_id[as.character(id)]); if (is.na(label)) "" else label }, character(1L))
    # Welchem Institut und Konto ein Beleg gehoert (#529 Punkt 6): „Institut: Konto, Konto“, ohne Institutsangabe nur die Konten.
    grouped <- vapply(unique(sort(institutions)), function(label) {
      names <- paste(sort(accounts[institutions == label]), collapse = ", ")
      if (nzchar(label)) paste0(label, ": ", names) else names }, character(1L))
    list(document_ref = as.character(document$document_ref),
      period = if (identical(document$period_from, document$period_to)) as.character(document$period_from) else paste0(document$period_from, " – ", document$period_to),
      kind = data_statement_archive_kind_label_v1(document$document_kind), kind_code = as.character(document$document_kind),
      institutions = unique(c(institutions, if (is.null(document$institution_label)) character() else as.character(document$institution_label))),
      scope = if (is.null(document$institution_label)) paste(grouped, collapse = " · ") else sprintf("%s (ganzes Institut, %d Konten)", document$institution_label, length(accounts)),
      file = if (is.null(document$original_name)) "ohne Datei" else as.character(document$original_name),
      status = data_statement_archive_status_label_v1(document$status), has_file = !is.null(document$file_sha256),
      note = if (is.null(document$note)) "" else as.character(document$note))
  })
}
# Die Liste je Jahr (#536, Festlegung 04.11.2026): nur das oben gewaehlte Institut ("" = ohne Institutsangabe) und wahlweise eine Art.
# `institution` NULL heisst: noch nicht gewaehlt - dann alle.
data_statement_archive_filter_documents_v1 <- function(rows, institution = NULL, kind = "") {
  Filter(function(row) (is.null(institution) || institution %in% row$institutions || (!nzchar(institution) && !length(Filter(nzchar, row$institutions)))) &&
    (!is.character(kind) || length(kind) != 1L || !nzchar(kind) || identical(row$kind_code, kind)), rows)
}
data_statement_archive_document_frame_v1 <- function(rows) data.frame(
  Zeitraum = vapply(rows, function(row) row$period, character(1L)), Art = vapply(rows, function(row) row$kind, character(1L)),
  `Gilt für` = vapply(rows, function(row) row$scope, character(1L)), Datei = vapply(rows, function(row) row$file, character(1L)),
  Stand = vapply(rows, function(row) row$status, character(1L)), Notiz = vapply(rows, function(row) if (nzchar(row$note)) row$note else "—", character(1L)),
  check.names = FALSE, stringsAsFactors = FALSE)
# Mit "Gilt für" (#536): Zwei Dokumente zur selben Datei unterscheiden sich sonst nur in der Tabelle.
data_statement_archive_document_choices_v1 <- function(rows) stats::setNames(vapply(rows, function(row) row$document_ref, character(1L)),
  vapply(rows, function(row) sprintf("%s · %s · %s · %s · %s", row$period, row$kind, row$file, row$status, row$scope), character(1L)))
data_statement_archive_grid_html_v1 <- function(grid, year) {
  if (!length(grid)) return(NULL)
  months <- c("Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez")
  rows <- list()
  for (group in grid) {
    rows[[length(rows) + 1L]] <- shiny::tags$tr(shiny::tags$td(colspan = 13L, shiny::tags$strong(group$institution)))
    for (account in group$accounts) rows[[length(rows) + 1L]] <- shiny::tags$tr(shiny::tags$td(account$name), lapply(account$cells, function(cell) shiny::tags$td(style = "text-align:center", cell)))
  }
  states <- data_statement_archive_month_states_v1()
  shiny::tagList(
    shiny::div(style = "overflow-x:auto;margin-bottom:8px", shiny::tags$table(class = "table shiny-table table-striped table-bordered",
      shiny::tags$thead(shiny::tags$tr(shiny::tags$th(sprintf("Konto · %s", year)), lapply(months, shiny::tags$th))), shiny::tags$tbody(rows))),
    shiny::p(class = "pl-field-hint", paste0(paste(vapply(states, function(state) paste(state[[1L]], state[[2L]]), character(1L)), collapse = " · "),
      " · ᴵ über ein Dokument, das am ganzen Institut hängt")))
}
data_statement_archive_ui_v1 <- function(current_year = as.integer(format(Sys.Date(), "%Y"))) {
  years <- as.character(seq.int(as.integer(current_year), as.integer(current_year) - 12L)); months <- data_statement_archive_month_choices_v1(current_year)
  shiny::tags$details(class = "pl-disclosure pl-lazy", id = "statement_archive_details",
    shiny::tags$summary("Auszüge und Belege je Konto"),
    portelyra_note_v1(title = "So funktioniert die Ablage", id = "data-statement-archive", shiny::p("Original-Auszüge hinterlegen, bestätigen und wieder abrufen. Eine Datei wird einmal abgelegt und gilt für ihren Zeitraum und die angehakten Konten;",
      " das Raster zeigt je Konto und Monat, was belegt ist. Offen ist ein Monat nur, wenn das Konto dort Bewegungen hat und nichts ihn abdeckt.",
      " Einen Monat decken Kontoauszug, Depotauszug, Transaktionsexport und Abrechnung; Jahresdokumente (Jahressteuerbescheinigung, Erträgnisaufstellung,",
      " Vorabpauschale) und Sonstiges liegen in der Ablage und im ZIP des Steuerjahres, decken aber keinen Monat.",
      " Buchungen, Bestände und Stammdaten ändern sich dadurch nicht.")),
    shiny::selectInput("statement_archive_year", "Jahr", choices = years, selected = years[[min(2L, length(years))]]),
    shiny::uiOutput("statement_archive_overview"),
    shiny::tags$h4("Hinterlegen oder erklären"),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("statement_archive_institution", "Institut", choices = c("wird geladen \u2026" = "")),
      shiny::selectInput("statement_archive_kind", "Art des Dokuments", choices = data_statement_archive_kinds_v1()),
      shiny::selectInput("statement_archive_from", "Zeitraum von (Monat)", choices = months, selected = sprintf("%s-01", years[[min(2L, length(years))]])),
      shiny::selectInput("statement_archive_to", "Zeitraum bis (Monat)", choices = months, selected = sprintf("%s-12", years[[min(2L, length(years))]]))),
    shiny::uiOutput("statement_archive_account_picker"),
    shiny::fileInput("statement_archive_files", "Dateien (beliebig viele; jede wird ein Dokument mit diesen Angaben)", multiple = TRUE, width = "100%"),
    # Wie beim Belegimport: Der Browser liefert alle Dateien des Ordners samt Unterordnern (#464).
    htmltools::tagQuery(shiny::fileInput("statement_archive_folder", "… oder einen Ordner samt Unterordnern", multiple = TRUE, width = "100%",
      buttonLabel = "Ordner wählen …"))$find("#statement_archive_folder")$addAttrs(webkitdirectory = NA, directory = NA)$allTags(),
    shiny::p(class = "pl-field-hint", "Jede Datei bis 1 GB (die Grenze je Datei im Backup). Systemdateien wie Thumbs.db, desktop.ini oder versteckte Dateien werden übersprungen."),
    shiny::textInput("statement_archive_note", "Notiz (optional)", value = "", width = "100%"),
    # Sammelzuordnung (#434): je Datei Art, Zeitraum und Konten aus dem Inhalt vorschlagen, statt sie einzutippen.
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("statement_archive_suggest", "Zeitraum und Konto aus dem Inhalt vorschlagen", class = "btn-default")),
    shiny::uiOutput("statement_archive_suggestions"),
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("statement_archive_store", "Dateien hinterlegen", class = "btn-primary"),
      shiny::actionButton("statement_archive_declare", "Für diesen Zeitraum: Auszug nicht mehr vorhanden", class = "btn-default")),
    shiny::tags$h4("Jahr abschließen"),
    shiny::p(class = "pl-field-hint", "Bestätigt alle hinterlegten Dateien, die das gewählte Jahr und die angehakten Konten berühren. Ein Dokument wird als Ganzes bestätigt – auch für seine übrigen Konten."),
    shiny::checkboxInput("statement_archive_declare_rest", "Übrige offene Monate der angehakten Konten als „nicht mehr vorhanden“ erklären", FALSE),
    # Ein Klick nimmt Konten aus der Lueckenanzeige, schliesst oder legt sie still: erst nach einem Haekchen (unter derselben
    # Kontoauswahl wie „Dateien hinterlegen“, Datum vorbelegt mit heute).
    shiny::checkboxInput("statement_archive_expect_confirm", "Ja, für die angehakten Konten gibt es keine Auszüge", FALSE),
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("statement_archive_close", "Jahr für die angehakten Konten abschließen", class = "btn-default"),
      shiny::actionButton("statement_archive_expect_off", "Für die angehakten Konten gibt es keine Auszüge", class = "btn-default"),
      shiny::actionButton("statement_archive_expect_on", "Angehakte Konten wieder in die Lückenanzeige", class = "btn-default")),
    # Konto geschlossen seit (#513, Festlegung 25.10.2026): ab dem Monat danach keine Auszuege erwartet, der Eingang nimmt das Konto nicht mehr.
    shiny::tags$h4("Konto geschlossen"),
    shiny::p(class = "pl-field-hint", paste("Ab dem Monat nach dem Tag erwartet die Ablage für die angehakten Konten keine Auszüge mehr, und der monatliche Eingang nimmt sie nicht mehr an.",
      "Buchungen und Belege davor bleiben, wie sie sind. „Für die angehakten Konten gibt es keine Auszüge“ bleibt für Konten, die nie Auszüge haben – etwa ein Schließfach.")),
    shiny::div(class = "pl-form-grid", suppressWarnings(shiny::dateInput("statement_archive_closed_on", "Konto geschlossen seit", value = NA, format = "dd.mm.yyyy", language = "de", weekstart = 1))),
    shiny::checkboxInput("statement_archive_close_confirm", "Ja, die angehakten Konten sind seit diesem Tag geschlossen", FALSE),
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("statement_archive_account_close", "Angehakte Konten: geschlossen seit diesem Tag", class = "btn-default"),
      shiny::actionButton("statement_archive_account_reopen", "Schließung der angehakten Konten zurücknehmen", class = "btn-default")),
    # Konto inaktiv seit (#529 Punkt 1, Festlegung 31.10.2026): voruebergehend, mit Tag; Bestand und Buchungen bleiben.
    shiny::tags$h4("Konto ruht (inaktiv)"),
    shiny::p(class = "pl-field-hint", paste("Für Konten, die bestehen, aber gerade ruhen, etwa ein Tagesgeld ohne Bewegung.",
      "Ab dem Monat nach dem Tag erwartet die Ablage keine Auszüge; Eingang, Ablage und Importe bieten die Konten nicht mehr an. Bestand und Buchungen bleiben und zählen weiter.",
      "Wieder aktiviert, sind die Monate seit dem Tag wieder offen – die Ablage nennt, ab wann Auszüge nachzuladen sind. Geschlossen ist endgültig, inaktiv vorübergehend.")),
    shiny::div(class = "pl-form-grid", suppressWarnings(shiny::dateInput("statement_archive_inactive_since", "Konto inaktiv seit", value = NA, format = "dd.mm.yyyy", language = "de", weekstart = 1))),
    shiny::checkboxInput("statement_archive_rest_confirm", "Ja, die angehakten Konten ruhen seit diesem Tag", FALSE),
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("statement_archive_account_rest", "Angehakte Konten: inaktiv seit diesem Tag", class = "btn-default"),
      shiny::actionButton("statement_archive_account_wake", "Angehakte Konten wieder aktivieren", class = "btn-default")),
    # Die Meldung ist eine eigene Ausgabe: Nach einer abgewiesenen Eingabe bleibt das Gewaehlte stehen.
    shiny::uiOutput("statement_archive_notice"),
    # Nicht nur Jahresdokumente (#536): alles, dessen Zeitraum das Jahr beruehrt - fuer das oben gewaehlte Institut.
    shiny::tags$h4(shiny::textOutput("statement_archive_documents_title", inline = TRUE)),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("statement_archive_document_kind_filter", "Art", choices = c("Alle Arten" = "", data_statement_archive_kinds_v1()))),
    shiny::p(class = "pl-field-hint", "Gezeigt werden die Dokumente des oben unter „Institut“ gewählten Instituts, deren Zeitraum das Jahr berührt."),
    shiny::selectInput("statement_archive_document", "Dokument", choices = c("Noch keine Dokumente" = ""), width = "100%"),
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("statement_archive_confirm", "Bestätigen", class = "btn-primary"),
      shiny::actionButton("statement_archive_unconfirm", "Bestätigung zurücknehmen", class = "btn-default"),
      shiny::actionButton("statement_archive_withdraw", "Dokument zurückziehen", class = "btn-default"),
      shiny::downloadButton("statement_archive_download", "Datei abrufen", class = "btn-default")),
    # Art aendern (#536): ohne Zurueckziehen und neu Hinterlegen; der fruehere Stand bleibt.
    shiny::div(class = "pl-field-row",
      shiny::selectInput("statement_archive_new_kind", "Neue Art des gewählten Dokuments", choices = data_statement_archive_kinds_v1()),
      shiny::actionButton("statement_archive_change_kind", "Art ändern", class = "btn-default")),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("statement_archive_documents")),
    # Endgueltig entfernen (#434): nur Dateien zurueckgezogener Dokumente, die kein anderes Dokument mehr traegt.
    shiny::tags$h4("Zurückgezogene Dateien endgültig entfernen"),
    shiny::p(class = "pl-field-hint", "Ein zurückgezogenes Dokument behält seine Datei in der Ablage, bis sie hier entfernt wird. Danach ist sie nicht mehr abrufbar; die Einträge bleiben. Wer dieselbe Datei später wieder hinterlegt, hat sie wieder."),
    shiny::selectInput("statement_archive_withdrawn", "Zurückgezogenes Dokument mit Datei", choices = c("Keine im gewählten Jahr" = ""), width = "100%"),
    shiny::checkboxInput("statement_archive_remove_confirm", "Diese Datei endgültig aus der Ablage entfernen", FALSE),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("statement_archive_remove", "Datei endgültig entfernen", class = "btn-default")))
}
# Warum ein Vorschlag unvollstaendig ist (#434).
data_statement_archive_reason_text_v1 <- function(reason) switch(as.character(reason),
  unreadable = "Datei nicht lesbar", too_large = "größer als 20 MB – bitte von Hand", no_period = "kein Zeitraum erkennbar – bitte von Hand",
  no_account = "kein Konto eindeutig – bitte von Hand", "")
data_statement_archive_suggestion_frame_v1 <- function(result, account_rows) {
  names_by_id <- stats::setNames(vapply(account_rows, function(row) row$name, character(1L)), vapply(account_rows, function(row) row$id, character(1L)))
  rows <- result$files
  data.frame(
    Datei = vapply(rows, function(row) as.character(row$file_name), character(1L)),
    `Erkannt von` = vapply(rows, function(row) if (is.null(row$reader)) "—" else as.character(row$reader), character(1L)),
    Art = vapply(rows, function(row) if (is.null(row$document_kind)) "—" else data_statement_archive_kind_label_v1(row$document_kind), character(1L)),
    Zeitraum = vapply(rows, function(row) if (is.null(row$period_from)) "—" else if (identical(row$period_from, row$period_to)) as.character(row$period_from)
      else paste0(row$period_from, " – ", row$period_to), character(1L)),
    Konten = vapply(rows, function(row) { ids <- unlist(row$account_ids, use.names = FALSE); if (!length(ids)) "—" else paste(vapply(ids, function(id) {
      name <- unname(names_by_id[as.character(id)]); if (is.na(name)) "Konto" else name }, character(1L)), collapse = ", ") }, character(1L)),
    Vorschlag = vapply(rows, function(row) if (isTRUE(row$complete)) "vollständig" else data_statement_archive_reason_text_v1(row$reason), character(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
}
data_statement_archive_error_text_v1 <- function(code) switch(as.character(code),
  statement_archive_input_invalid = "Bitte mindestens ein Konto anhaken und einen Zeitraum wählen, dessen Ende nicht vor dem Anfang liegt.",
  statement_archive_account_unknown = "Eines der Konten gibt es in den Stammdaten nicht mehr. Bitte oben „Stammdaten neu lesen“.",
  statement_archive_document_unknown = "Dieses Dokument gibt es in der Ablage nicht mehr.",
  statement_archive_file_invalid = "Die Datei ließ sich nicht lesen oder stimmt nicht mehr mit ihrem Prüfwert überein.",
  statement_archive_file_too_large = "Die Datei ist größer als 1 GB – so groß lässt sich eine Datei im Backup nicht sichern.",
  statement_archive_file_removed = "Die Datei wurde endgültig aus der Ablage entfernt.",
  statement_archive_file_in_use = "Ein anderes Dokument trägt dieselbe Datei noch. Erst dieses zurückziehen, dann lässt sich die Datei entfernen.",
  statement_archive_confirmation_required = "Der Vorgang wurde nicht bestätigt.",
  statement_intake_folder_invalid = "Der Belegordner fehlt oder ist kein Ordner außerhalb des Datenraums. Bitte unter „Belegordner“ einen Ordner wählen.",
  statement_intake_changed = "Im Belegordner hat sich seit der Prüfung etwas geändert. Bitte „Eingang prüfen“ erneut ausführen – abgelegt wurde nichts.",
  statement_intake_too_many_files = "Im Belegordner liegen mehr als 10.000 Dateien. Bitte ältere, schon abgelegte Jahre herausnehmen – die Ablage hat sie – und erneut prüfen.",
  "Die Ablage ließ sich nicht lesen oder schreiben. Stammdaten und Buchungen sind davon nicht berührt.")
# `accounts` liefert die Konten des Katalogs, `resolve_id` die Kennung zu einer Auswahl.
data_statement_archive_server_v1 <- function(input, output, session, service, accounts, resolve_id,
    now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) {
  tick <- shiny::reactiveVal(0L); notice <- shiny::reactiveVal(NULL)
  open <- shiny::reactive(isTRUE(input$statement_archive_details_open)); filled <- shiny::reactiveVal(FALSE)
  account_rows <- shiny::reactive({ if (!open()) list() else
    data_statement_archive_accounts_v1(accounts(), resolve_id, if (is.null(service)) NULL else tryCatch(service$account_states(), error = function(error) NULL)) })
  overview <- shiny::reactive({
    tick()
    if (!open() || is.null(service) || is.null(input$statement_archive_year)) return(NULL)
    tryCatch(service$overview(input$statement_archive_year), error = function(error) structure(list(), unreadable = TRUE))
  })
  # Der Zeitraum zum Hinterlegen folgt dem gewaehlten Jahr (#536): Januar bis Dezember; vorher blieb er auf dem Jahr beim Start.
  shiny::observeEvent(input$statement_archive_year, {
    year <- input$statement_archive_year
    if (!is.character(year) || length(year) != 1L || !grepl("^(19|20)[0-9]{2}$", year)) return(invisible(NULL))
    shiny::updateSelectInput(session, "statement_archive_from", selected = sprintf("%s-01", year))
    shiny::updateSelectInput(session, "statement_archive_to", selected = sprintf("%s-12", year))
  }, ignoreInit = TRUE)
  shiny::observeEvent(account_rows(), {
    choices <- data_statement_archive_institutions_v1(account_rows())
    if (!length(choices)) return(invisible(NULL))
    shiny::updateSelectInput(session, "statement_archive_institution", choices = choices,
      selected = data_statement_archive_default_institution_v1(choices, input$statement_archive_institution, shiny::isolate(filled())))
    filled(TRUE)
  })
  members <- shiny::reactive({
    institution <- input$statement_archive_institution
    if (!is.character(institution) || length(institution) != 1L) return(list())
    Filter(function(row) identical(row$institution, institution), account_rows())
  })
  output$statement_archive_account_picker <- shiny::renderUI({
    if (!open()) return(NULL)
    rows <- members()
    if (!length(rows)) return(shiny::p(class = "pl-field-hint", "Bitte ein Institut wählen."))
    refs <- stats::setNames(vapply(rows, function(row) row$ref, character(1L)), vapply(rows, function(row) row$name, character(1L)))
    # Konten ohne Institutsangabe bilden kein Institut: kein Haekchen fuers Ganze, und vorbelegt ist keines.
    grouped <- nzchar(input$statement_archive_institution)
    shiny::tagList(
      if (grouped) shiny::checkboxInput("statement_archive_whole", "Gilt für das ganze Institut (alle seine Konten)", TRUE),
      shiny::checkboxGroupInput("statement_archive_accounts", if (grouped) "Konten" else "Konten ohne Institutsangabe", choices = refs,
        selected = if (grouped) unname(refs) else character(), inline = TRUE))
  })
  # Das Haekchen am Institut setzt alle Konten; wird ein Konto abgewaehlt, gilt das Dokument nicht mehr fuer das ganze Institut.
  shiny::observeEvent(input$statement_archive_whole, {
    refs <- vapply(members(), function(row) row$ref, character(1L))
    if (isTRUE(input$statement_archive_whole) && !setequal(input$statement_archive_accounts, refs)) shiny::updateCheckboxGroupInput(session, "statement_archive_accounts", selected = refs)
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$statement_archive_accounts, {
    refs <- vapply(members(), function(row) row$ref, character(1L))
    if (isTRUE(input$statement_archive_whole) && !setequal(input$statement_archive_accounts, refs)) shiny::updateCheckboxInput(session, "statement_archive_whole", value = FALSE)
  }, ignoreNULL = FALSE, ignoreInit = TRUE)
  chosen <- function() {
    rows <- members(); refs <- input$statement_archive_accounts
    picked <- Filter(function(row) row$ref %in% refs, rows)
    whole <- isTRUE(input$statement_archive_whole) && length(picked) == length(rows) && length(rows) > 0L && nzchar(input$statement_archive_institution)
    list(ids = vapply(picked, function(row) row$id, character(1L)), institution = if (whole) input$statement_archive_institution else NULL,
      names = vapply(picked, function(row) row$name, character(1L)))
  }
  attempt <- function(expression) tryCatch(expression, spot_data_statement_archive_error_v1 = function(error) error$code, error = function(error) "statement_archive_store_invalid")
  failed <- function(title, code) notice(list(title = title, tone = "error", copy = data_statement_archive_error_text_v1(code)))
  done <- function(title, copy) { notice(list(title = title, tone = "positive", copy = copy)); tick(tick() + 1L) }
  # Konten aus der Lueckenanzeige nehmen, schliessen oder ruhen lassen nur mit Haekchen; danach steht es wieder aus.
  confirmed_for <- function(id, label) {
    if (isTRUE(input[[id]])) return(TRUE)
    notice(list(title = "Nicht geändert", tone = "error", copy = paste0("Bitte zuerst „", label, "“ anhaken – ein Klick allein ändert hier nichts.")))
    FALSE
  }
  rearm <- function(id) shiny::updateCheckboxInput(session, id, value = FALSE)
  listed <- function(target) paste(target$names, collapse = ", ")
  # Zuletzt gewaehlt gilt - Dateien oder Ordner. Vor dem Hinterlegen ausgewertet (hoehere Prioritaet), auch wenn beides
  # in einem Schub ankommt.
  selection <- shiny::reactiveVal(NULL); suggestions <- shiny::reactiveVal(NULL)
  shiny::observeEvent(input$statement_archive_files, { selection(input$statement_archive_files); suggestions(NULL) }, priority = 10L)
  shiny::observeEvent(input$statement_archive_folder, { selection(input$statement_archive_folder); suggestions(NULL) }, priority = 10L)
  without_system_files <- function(files) {
    system_file <- grepl("^[.]|^~[$]", files$name) | tolower(files$name) %in% c("thumbs.db", "desktop.ini")
    files[!system_file, , drop = FALSE]
  }
  # Sammelzuordnung (#434): Vorschlag je Datei aus dem Inhalt; hinterlegt wird erst mit dem Knopf darunter.
  shiny::observeEvent(input$statement_archive_suggest, {
    files <- selection()
    if (is.null(service)) return(failed("Kein Vorschlag", "statement_archive_store_invalid"))
    if (is.null(files) || !is.data.frame(files) || !nrow(files)) return(notice(list(title = "Kein Vorschlag", tone = "error", copy = "Bitte zuerst eine oder mehrere Dateien wählen.")))
    files <- without_system_files(files)
    if (!nrow(files)) return(notice(list(title = "Kein Vorschlag", tone = "error", copy = "Die Auswahl enthält nur Systemdateien.")))
    result <- shiny::withProgress(message = "Dateien werden gelesen", value = 0.3, attempt(service$suggest(files$datapath, files$name)))
    if (!is.list(result)) return(failed("Kein Vorschlag", result))
    suggestions(list(files = files, result = result)); notice(NULL)
  })
  output$statement_archive_suggestions <- shiny::renderUI({
    value <- suggestions(); if (is.null(value)) return(NULL)
    complete <- as.integer(value$result$complete_count)
    shiny::tagList(
      shiny::p(class = "pl-field-hint", sprintf("%d von %d Datei(en) mit vollständigem Vorschlag. Die übrigen bitte mit den Angaben oben hinterlegen; sie bleiben dafür gewählt.",
        complete, length(value$result$files))),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("statement_archive_suggestion_table")),
      if (complete > 0L) shiny::div(class = "pl-editor-actions",
        shiny::actionButton("statement_archive_store_suggested", sprintf("%d Datei(en) mit diesen Vorschlägen hinterlegen", complete), class = "btn-primary")))
  })
  output$statement_archive_suggestion_table <- shiny::renderTable({
    value <- suggestions(); if (is.null(value)) return(NULL)
    data_statement_archive_suggestion_frame_v1(value$result, account_rows())
  }, striped = TRUE, bordered = TRUE)
  shiny::observeEvent(input$statement_archive_store_suggested, {
    value <- suggestions(); if (is.null(value) || is.null(service)) return()
    rows <- value$result$files; files <- value$files; stored <- 0L; unchanged <- 0L; done_names <- character()
    shiny::withProgress(message = "Dateien werden hinterlegt", value = 0, {
      for (index in seq_along(rows)) {
        row <- rows[[index]]
        if (!isTRUE(row$complete)) next
        result <- attempt(service$store(files$datapath[[index]], files$name[[index]], row$document_kind, row$period_from, row$period_to,
          unlist(row$account_ids, use.names = FALSE), NULL, input$statement_archive_note, now_utc(), TRUE))
        shiny::setProgress(index / length(rows))
        if (!is.list(result)) return(failed(sprintf("„%s“ nicht hinterlegt", files$name[[index]]), result))
        if (identical(result$status, "stored")) stored <- stored + 1L else unchanged <- unchanged + 1L
        done_names <- c(done_names, files$name[[index]])
      }
    })
    # Was hinterlegt ist, faellt aus der Auswahl: Der Knopf "Dateien hinterlegen" nimmt danach nur noch den Rest.
    rest <- files[!files$name %in% done_names, , drop = FALSE]
    selection(if (nrow(rest)) rest else NULL); suggestions(NULL)
    done(if (stored > 0L) "Mit Vorschlägen hinterlegt" else "Nichts Neues", sprintf("%d Datei(en) hinterlegt, %d lagen mit denselben Angaben schon vor.%s", stored, unchanged,
      if (nrow(rest)) sprintf(" %d Datei(en) ohne vollständigen Vorschlag bleiben gewählt – bitte mit den Angaben oben hinterlegen.", nrow(rest)) else ""))
  })
  shiny::observeEvent(input$statement_archive_store, {
    files <- selection(); target <- chosen()
    if (is.null(service)) return(failed("Nicht hinterlegt", "statement_archive_store_invalid"))
    if (is.null(files) || !is.data.frame(files) || !nrow(files)) return(notice(list(title = "Nicht hinterlegt", tone = "error", copy = "Bitte zuerst eine oder mehrere Dateien wählen.")))
    if (!length(target$ids)) return(failed("Nicht hinterlegt", "statement_archive_input_invalid"))
    system_file <- grepl("^[.]|^~[$]", files$name) | tolower(files$name) %in% c("thumbs.db", "desktop.ini")
    skipped <- sum(system_file); files <- files[!system_file, , drop = FALSE]
    if (!nrow(files)) return(notice(list(title = "Nicht hinterlegt", tone = "error", copy = sprintf("Die Auswahl enthält nur Systemdateien (%d), keine Auszüge.", skipped))))
    stored <- 0L; unchanged <- 0L; refused <- list(); stopped <- NULL
    shiny::withProgress(message = "Dateien werden hinterlegt", value = 0, {
      for (index in seq_len(nrow(files))) {
        result <- attempt(service$store(files$datapath[[index]], files$name[[index]], input$statement_archive_kind, input$statement_archive_from, input$statement_archive_to,
          target$ids, target$institution, input$statement_archive_note, now_utc(), TRUE))
        shiny::setProgress(index / nrow(files), detail = sprintf("%d von %d", index, nrow(files)))
        if (is.list(result)) { if (identical(result$status, "stored")) stored <- stored + 1L else unchanged <- unchanged + 1L; next }
        # Was nur diese Datei betrifft, haelt den Rest nicht an; alles andere gilt fuer jede weitere Datei genauso.
        if (!result %in% c("statement_archive_file_invalid", "statement_archive_file_too_large")) { stopped <- list(index = index, code = result); break }
        refused[[length(refused) + 1L]] <- list(name = files$name[[index]], code = result)
      }
    })
    if (stored > 0L) tick(tick() + 1L)
    counts <- sprintf("%d Datei(en) hinterlegt, %d lagen mit denselben Angaben schon vor%s.", stored, unchanged,
      if (skipped > 0L) sprintf(", %d Systemdatei(en) übersprungen", skipped) else "")
    if (!is.null(stopped)) return(notice(list(title = sprintf("Datei %d von %d nicht hinterlegt", stopped$index, nrow(files)), tone = "error",
      copy = paste(data_statement_archive_error_text_v1(stopped$code), "Davor:", counts))))
    if (length(refused)) {
      shown <- vapply(utils::head(refused, 5L), function(item) sprintf("„%s“ – %s", item$name, data_statement_archive_error_text_v1(item$code)), character(1L))
      more <- if (length(refused) > 5L) sprintf(" … und %d weitere.", length(refused) - 5L) else ""
      return(notice(list(title = sprintf("%d von %d Datei(en) nicht hinterlegt", length(refused), nrow(files)), tone = if (stored + unchanged > 0L) "warning" else "error",
        copy = paste(counts, "Nicht hinterlegt:", paste(shown, collapse = " · "), more))))
    }
    notice(list(title = if (stored > 0L) "Hinterlegt" else "Nichts Neues", tone = "positive",
      copy = paste(counts, "Neue Dokumente sind unbestätigt, bis Du sie bestätigst oder das Jahr abschließt.")))
  })
  shiny::observeEvent(input$statement_archive_declare, {
    target <- chosen()
    if (is.null(service)) return(failed("Nicht erklärt", "statement_archive_store_invalid"))
    if (!length(target$ids)) return(failed("Nicht erklärt", "statement_archive_input_invalid"))
    result <- attempt(service$declare(input$statement_archive_from, input$statement_archive_to, target$ids, target$institution, input$statement_archive_note, now_utc(), TRUE))
    if (!is.list(result)) return(failed("Nicht erklärt", result))
    done("Erklärt", sprintf("Für %s bis %s gilt bei %d Konto/Konten: Auszug nicht mehr vorhanden, von Dir bestätigt.", input$statement_archive_from, input$statement_archive_to, length(target$ids)))
  })
  shiny::observeEvent(input$statement_archive_close, {
    target <- chosen()
    if (is.null(service)) return(failed("Jahr nicht abgeschlossen", "statement_archive_store_invalid"))
    if (!length(target$ids)) return(failed("Jahr nicht abgeschlossen", "statement_archive_input_invalid"))
    result <- attempt(service$close(input$statement_archive_year, target$ids, isTRUE(input$statement_archive_declare_rest), now_utc(), TRUE))
    if (!is.list(result)) return(failed("Jahr nicht abgeschlossen", result))
    done(sprintf("Jahr %s abgeschlossen", input$statement_archive_year), sprintf("%d Dokument(e) bestätigt, %d Lücke(n) als „nicht mehr vorhanden“ erklärt.",
      as.integer(result$confirmed_document_count), as.integer(result$declared_gap_count)))
  })
  expectation <- function(expected) {
    target <- chosen()
    if (is.null(service)) return(failed("Nicht geändert", "statement_archive_store_invalid"))
    if (!length(target$ids)) return(failed("Nicht geändert", "statement_archive_input_invalid"))
    if (!expected && !confirmed_for("statement_archive_expect_confirm", "Ja, für die angehakten Konten gibt es keine Auszüge")) return()
    for (id in target$ids) { result <- attempt(service$expect(id, expected, now_utc(), TRUE)); if (!is.list(result)) return(failed("Nicht geändert", result)) }
    if (!expected) rearm("statement_archive_expect_confirm")
    done("Geändert", if (expected) sprintf("Wieder in der Lückenanzeige: %s.", listed(target))
      else sprintf("Keine Auszüge für %s; aus der Lückenanzeige genommen.", listed(target)))
  }
  closure <- function(closed_on) {
    target <- chosen()
    if (is.null(service)) return(failed("Nicht geändert", "statement_archive_store_invalid"))
    if (!length(target$ids)) return(failed("Nicht geändert", "statement_archive_input_invalid"))
    if (!is.null(closed_on) && !confirmed_for("statement_archive_close_confirm", "Ja, die angehakten Konten sind seit diesem Tag geschlossen")) return()
    for (id in target$ids) { result <- attempt(service$closure(id, closed_on, now_utc(), TRUE)); if (!is.list(result)) return(failed("Nicht geändert", result)) }
    if (!is.null(closed_on)) rearm("statement_archive_close_confirm")
    done(if (is.null(closed_on)) "Wieder offen" else "Konto geschlossen", if (is.null(closed_on)) sprintf("Erwarten wieder Auszüge: %s.", listed(target))
      else sprintf("Geschlossen seit %s: %s. Ab dem Monat danach keine Auszüge mehr erwartet.", format(as.Date(closed_on), "%d.%m.%Y"), listed(target)))
  }
  shiny::observeEvent(input$statement_archive_account_close, {
    day <- input$statement_archive_closed_on
    if (length(day) != 1L || is.na(day)) return(notice(list(title = "Nicht geändert", tone = "error", copy = "Bitte zuerst den Tag wählen, seit dem das Konto geschlossen ist.")))
    closure(format(as.Date(day), "%Y-%m-%d"))
  })
  shiny::observeEvent(input$statement_archive_account_reopen, closure(NULL))
  inactivity <- function(inactive_since) {
    target <- chosen()
    if (is.null(service)) return(failed("Nicht geändert", "statement_archive_store_invalid"))
    if (!length(target$ids)) return(failed("Nicht geändert", "statement_archive_input_invalid"))
    if (!is.null(inactive_since) && !confirmed_for("statement_archive_rest_confirm", "Ja, die angehakten Konten ruhen seit diesem Tag")) return()
    before <- tryCatch(service$account_states(), error = function(error) list())
    for (id in target$ids) { result <- attempt(service$inactivity(id, inactive_since, now_utc(), TRUE)); if (!is.list(result)) return(failed("Nicht geändert", result)) }
    if (!is.null(inactive_since)) { rearm("statement_archive_rest_confirm")
      return(done("Konto ruht", sprintf("Inaktiv seit %s: %s. Ab dem Monat danach keine Auszüge erwartet, Eingang und Importe bieten sie nicht mehr an.",
        pl_day_v1(inactive_since), listed(target)))) }
    # Wieder aktiv: Ab wann rueckwirkend Auszuege zu laden sind, steht in der Meldung (inaktiv seit ... bis heute).
    since <- unlist(lapply(target$ids, function(id) before[[id]]$inactive_since))
    done("Wieder aktiv", if (length(since)) sprintf("Wieder aktiv: %s. Auszüge und Exporte ab %s bis heute nachladen; die Monate seither stehen wieder als offen im Raster.",
      listed(target), pl_day_v1(min(since))) else sprintf("Aktiv: %s.", listed(target)))
  }
  shiny::observeEvent(input$statement_archive_account_rest, {
    day <- input$statement_archive_inactive_since
    if (length(day) != 1L || is.na(day)) return(notice(list(title = "Nicht geändert", tone = "error", copy = "Bitte zuerst den Tag wählen, seit dem das Konto ruht.")))
    inactivity(format(as.Date(day), "%Y-%m-%d"))
  })
  shiny::observeEvent(input$statement_archive_account_wake, inactivity(NULL))
  shiny::observeEvent(input$statement_archive_expect_off, expectation(FALSE))
  shiny::observeEvent(input$statement_archive_expect_on, expectation(TRUE))
  document_rows <- shiny::reactive({
    model <- overview()
    rows <- if (is.null(model) || isTRUE(attr(model, "unreadable"))) list() else data_statement_archive_document_rows_v1(model, account_rows())
    institution <- input$statement_archive_institution
    data_statement_archive_filter_documents_v1(rows, if (filled() && is.character(institution) && length(institution) == 1L) institution else NULL,
                                               input$statement_archive_document_kind_filter)
  })
  output$statement_archive_documents_title <- shiny::renderText({
    year <- input$statement_archive_year
    if (is.null(year)) "Dokumente im Jahr" else paste("Dokumente im Jahr", year)
  })
  # Die neue Art steht auf der des gewaehlten Dokuments; geaendert wird erst mit dem Knopf.
  shiny::observeEvent(input$statement_archive_document, {
    found <- Filter(function(row) identical(row$document_ref, input$statement_archive_document), document_rows())
    if (length(found) == 1L) shiny::updateSelectInput(session, "statement_archive_new_kind", selected = found[[1L]]$kind_code)
  })
  shiny::observeEvent(input$statement_archive_change_kind, {
    ref <- input$statement_archive_document; kind <- input$statement_archive_new_kind
    if (is.null(service) || !is.character(ref) || !nzchar(ref)) return(notice(list(title = "Kein Dokument gewählt", tone = "error", copy = "Bitte zuerst ein Dokument wählen.")))
    result <- attempt(service$set_kind(ref, kind, now_utc(), TRUE))
    if (!is.list(result)) return(failed("Art nicht geändert", result))
    label <- data_statement_archive_kind_label_v1(kind)
    done(if (identical(result$status, "unchanged")) "Nichts geändert" else "Art geändert",
      if (identical(result$status, "unchanged")) sprintf("Das Dokument ist schon „%s“.", label)
      else sprintf("Das Dokument ist jetzt „%s“; der frühere Stand bleibt in der Ablage.%s", label,
        if (kind %in% data_statement_archive_year_kinds_v1() || identical(kind, "other")) " Als Jahresdokument oder Sonstiges deckt es keinen Monat im Raster." else ""))
  })
  shiny::observeEvent(document_rows(), {
    rows <- document_rows()
    choices <- if (length(rows)) data_statement_archive_document_choices_v1(rows) else c("Keine Dokumente zu dieser Auswahl" = "")
    shiny::updateSelectInput(session, "statement_archive_document", choices = choices,
      selected = if (isTRUE(input$statement_archive_document %in% choices)) input$statement_archive_document else unname(choices[[1L]]))
  })
  status_change <- function(status, title) {
    ref <- input$statement_archive_document
    if (is.null(service) || !is.character(ref) || !nzchar(ref)) return(notice(list(title = "Kein Dokument gewählt", tone = "error", copy = "Bitte zuerst ein Dokument wählen.")))
    result <- attempt(service$set_status(ref, status, now_utc(), TRUE))
    if (!is.list(result)) return(failed("Stand nicht geändert", result))
    done(if (identical(result$status, "unchanged")) "Nichts geändert" else title, "Der Stand des Dokuments ist festgehalten; frühere Stände bleiben in der Ablage.")
  }
  shiny::observeEvent(overview(), {
    model <- overview(); rows <- if (is.null(model) || isTRUE(attr(model, "unreadable"))) list() else model$withdrawn_documents
    choices <- if (length(rows)) stats::setNames(vapply(rows, function(row) as.character(row$document_ref), character(1L)),
      vapply(rows, function(row) sprintf("%s · %s · %s", row$period_from, data_statement_archive_kind_label_v1(row$document_kind), row$original_name), character(1L)))
      else c("Keine im gewählten Jahr" = "")
    shiny::updateSelectInput(session, "statement_archive_withdrawn", choices = choices, selected = unname(choices[[1L]]))
  })
  shiny::observeEvent(input$statement_archive_remove, {
    ref <- input$statement_archive_withdrawn
    if (is.null(service) || !is.character(ref) || !nzchar(ref)) return(notice(list(title = "Kein Dokument gewählt", tone = "error", copy = "Bitte zuerst ein zurückgezogenes Dokument mit Datei wählen.")))
    if (!isTRUE(input$statement_archive_remove_confirm)) return(notice(list(title = "Nicht entfernt", tone = "error", copy = "Bitte zuerst bestätigen, dass die Datei endgültig entfernt werden soll.")))
    result <- attempt(service$remove(ref, now_utc(), TRUE))
    if (!is.list(result)) return(failed("Nicht entfernt", if (identical(result, "statement_archive_input_invalid")) "statement_archive_file_in_use" else result))
    shiny::updateCheckboxInput(session, "statement_archive_remove_confirm", value = FALSE)
    done(if (identical(result$status, "unchanged")) "Schon entfernt" else "Datei entfernt", "Die Datei liegt nicht mehr in der Ablage; die Einträge des Dokuments bleiben.")
  })
  shiny::observeEvent(input$statement_archive_confirm, status_change("confirmed", "Dokument bestätigt"))
  shiny::observeEvent(input$statement_archive_unconfirm, status_change("unconfirmed", "Bestätigung zurückgenommen"))
  shiny::observeEvent(input$statement_archive_withdraw, status_change("withdrawn", "Dokument zurückgezogen"))
  output$statement_archive_notice <- shiny::renderUI({
    meldung <- notice()
    if (is.list(meldung)) portelyra_status_panel(meldung$title, meldung$copy, tone = meldung$tone)
  })
  output$statement_archive_overview <- shiny::renderUI({
    if (!open()) return(NULL)
    model <- overview()
    if (is.null(service) || isTRUE(attr(model, "unreadable"))) return(portelyra_status_panel("Ablage nicht lesbar",
      "Die Ablage der Auszüge ließ sich nicht lesen. Stammdaten und Buchungen sind davon nicht berührt.", tone = "warning"))
    if (is.null(model)) return(NULL)
    counts <- model$month_status_counts
    shiny::tagList(
      shiny::p(class = "pl-field-hint", sprintf("%s: %d Monate bestätigt · %d hinterlegt, unbestätigt · %d nicht mehr vorhanden · %d offen · %d Dokument(e)", model$year,
        as.integer(counts$confirmed), as.integer(counts$unconfirmed), as.integer(counts$not_available), as.integer(counts$open), length(model$documents))),
      data_statement_archive_grid_html_v1(data_statement_archive_grid_v1(model), model$year))
  })
  output$statement_archive_documents <- shiny::renderTable({
    rows <- document_rows()
    if (!open() || !length(rows)) return(NULL)
    data_statement_archive_document_frame_v1(rows)
  }, striped = TRUE, bordered = TRUE)
  output$statement_archive_download <- shiny::downloadHandler(
    filename = function() {
      found <- Filter(function(row) identical(row$document_ref, input$statement_archive_document), document_rows())
      if (length(found) == 1L && found[[1L]]$has_file) found[[1L]]$file else "kein-dokument.txt"
    },
    content = function(file) {
      result <- service$file(input$statement_archive_document)
      if (!file.copy(result$path, file, overwrite = TRUE)) stop("statement_archive_file_invalid", call. = FALSE)
    })
  invisible(list(overview = overview, notice = notice, chosen = chosen, document_rows = document_rows, suggestions = suggestions, selection = selection))
}

# Quelle der Importe (#434): Die Leser nehmen die hinterlegten Dateien statt eines Ordners ausserhalb - eine Quelle statt zwei.
# Je Datei einmal; der Name beginnt mit dem Anfang ihres Pruefwerts, damit Pruefung und Liste der Leser sie darueber nennen.
data_statement_archive_source_ui_v1 <- function(prefix, with_institution = TRUE, current_year = as.integer(format(Sys.Date(), "%Y"))) {
  years <- as.character(seq.int(as.integer(current_year), as.integer(current_year) - 12L))
  shiny::tags$details(class = "pl-disclosure pl-lazy", id = paste0(prefix, "_archive_details"),
    shiny::tags$summary("… oder Dateien aus der Ablage nehmen"),
    shiny::p(class = "pl-field-hint", if (with_institution) "Alle hinterlegten Dateien der Konten des Instituts, deren Zeitraum die Jahre berührt; zurückgezogene nicht."
      else "Alle hinterlegten Dateien des oben gewählten Kontos, deren Zeitraum die Jahre berührt; zurückgezogene nicht."),
    shiny::div(class = "pl-form-grid",
      if (with_institution) shiny::selectInput(paste0(prefix, "_archive_institution"), "Institut", choices = c("Bitte wählen" = "")),
      shiny::selectInput(paste0(prefix, "_archive_from"), "von Jahr", years, selected = years[[min(2L, length(years))]]),
      shiny::selectInput(paste0(prefix, "_archive_to"), "bis Jahr", years, selected = years[[1L]])),
    shiny::div(class = "pl-editor-actions", shiny::actionButton(paste0(prefix, "_archive_take"), "Dateien aus der Ablage übernehmen", class = "btn-default")),
    shiny::uiOutput(paste0(prefix, "_archive_state")))
}
data_statement_archive_source_frame_v1 <- function(files) data.frame(
  name = vapply(files, function(file) sprintf("%s · %s", substr(as.character(file$file_sha256), 1L, 8L), as.character(file$original_name)), character(1L)),
  size = vapply(files, function(file) as.numeric(file.info(as.character(file$path))$size), numeric(1L)), type = "",
  datapath = vapply(files, function(file) as.character(file$path), character(1L)), stringsAsFactors = FALSE)
# `account_ids` liefert die Konten, deren Dateien gemeint sind; ohne sie waehlt man das Institut aus `accounts`.
# `preselect` (#522): ein reaktiver Wert mit dem Institut, das der Eingang vorgibt; gewaehlt, sobald die Liste geladen ist.
data_statement_archive_source_server_v1 <- function(input, output, session, prefix, service, on_take, account_ids = NULL, accounts = NULL, resolve_id = NULL, kinds = NULL,
                                                    preselect = NULL) {
  state <- shiny::reactiveVal(NULL)
  id <- function(name) paste0(prefix, "_archive_", name)
  # Erst aufgeklappt werden die Konten aufgeloest (pl-lazy meldet "<id>_open").
  rows <- shiny::reactive({ if (is.null(accounts) || !isTRUE(input[[id("details_open")]])) list() else
    tryCatch(data_statement_archive_accounts_v1(accounts(), resolve_id, tryCatch(service$account_states(), error = function(error) NULL), skip_inactive = TRUE),
             error = function(error) list()) })
  if (is.null(account_ids)) {
    shiny::observeEvent(rows(), {
      choices <- data_statement_archive_institutions_v1(rows())
      if (!length(choices)) return(invisible(NULL))
      current <- input[[id("institution")]]
      wanted <- if (is.function(preselect)) shiny::isolate(preselect()) else NULL
      shiny::updateSelectInput(session, id("institution"), choices = c("Bitte wählen" = "", choices),
        selected = if (is.character(wanted) && length(wanted) == 1L && wanted %in% choices) wanted
                   else if (is.character(current) && length(current) == 1L && current %in% choices) current else "")
    })
    if (is.function(preselect)) shiny::observeEvent(preselect(), {
      wanted <- preselect(); choices <- data_statement_archive_institutions_v1(rows())
      if (is.character(wanted) && length(wanted) == 1L && wanted %in% choices) shiny::updateSelectInput(session, id("institution"), selected = wanted)
    }, ignoreInit = TRUE)
    account_ids <- function() {
      chosen <- input[[id("institution")]]
      if (!is.character(chosen) || length(chosen) != 1L || !nzchar(chosen)) return(character())
      vapply(Filter(function(row) identical(row$institution, chosen), rows()), function(row) row$id, character(1L))
    }
  }
  shiny::observeEvent(input[[id("take")]], {
    if (is.null(service)) return(state(list(tone = "error", title = "Ablage nicht lesbar", copy = data_statement_archive_error_text_v1("statement_archive_store_invalid"))))
    ids <- tryCatch(account_ids(), error = function(error) character())
    if (!length(ids)) return(state(list(tone = "error", title = "Nichts gewählt", copy = "Bitte zuerst ein Institut bzw. ein Konto wählen.")))
    years <- sort(suppressWarnings(as.integer(c(input[[id("from")]], input[[id("to")]]))))
    if (length(years) != 2L || anyNA(years)) return(state(list(tone = "error", title = "Nichts gewählt", copy = "Bitte die Jahre wählen.")))
    files <- tryCatch(service$files(ids, years[[1L]], years[[2L]], kinds), spot_data_statement_archive_error_v1 = function(error) structure(list(), code = error$code),
      error = function(error) structure(list(), code = "statement_archive_store_invalid"))
    if (!is.null(attr(files, "code"))) return(state(list(tone = "error", title = "Ablage nicht lesbar", copy = data_statement_archive_error_text_v1(attr(files, "code")))))
    if (!length(files)) return(state(list(tone = "warning", title = "Keine Dateien in der Ablage", copy = sprintf("Für %d–%d ist zu dieser Auswahl nichts hinterlegt.", years[[1L]], years[[2L]]))))
    frame <- data_statement_archive_source_frame_v1(files)
    on_take(frame)
    state(list(tone = "neutral", title = sprintf("%d Datei(en) aus der Ablage übernommen", nrow(frame)),
      copy = "Jede Datei steht mit dem Anfang ihres Prüfwerts vor dem Namen. Jetzt mit dem Knopf der Karte prüfen; eine neue Auswahl von Dateien oder Ordner ersetzt diese."))
  })
  output[[id("state")]] <- shiny::renderUI({ value <- state(); if (is.list(value)) portelyra_status_panel(value$title, value$copy, tone = value$tone) })
  invisible(state)
}
