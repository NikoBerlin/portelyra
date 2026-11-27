# Steuerangaben je Institut und Jahr: Freistellungsauftrag, anrechenbare Quellensteuer, Verlusttoepfe zum Jahresbeginn.
#
# Der Freibetrag gilt je Institut (ohne Eintrag 0 Euro), nicht global fuer das Jahr. Kapitalertraege rechnet das Regelmodul je Institut; die Werte dafuer stehen hier, je Institut so,
# wie es an den Konten steht. Private Veraeusserungsgeschaefte und sonstige Einkuenfte rechnen ueber alle Institute.
# Die Angaben liegen neben den Stammdaten (institution-tax-settings-v1): Buchungsbestand, FIFO und Bewertung bleiben
# unberuehrt. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
data_institution_tax_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^institution_tax_settings_[a-z_]+$", code)) code <- "institution_tax_settings_store_invalid"
  stop(structure(list(message = code, call = NULL, code = code),
    class = c("spot_data_institution_tax_error_v1", "error", "condition")))
}
# Die vier Angaben je Institut - dieselben Kennungen wie im Regelmodul - mit ihrem Namen in der Karte.
data_institution_tax_fields_v1 <- function() c(
  capital_income_allowance = "Freistellungsauftrag in €",
  creditable_foreign_withholding_tax = "Anrechenbare Quellensteuer in €",
  opening_equity_loss_carryforward = "Verlusttopf Aktien zum 1.1. in €",
  opening_general_capital_loss_carryforward = "Verlusttopf allgemein zum 1.1. in €")
data_institution_tax_no_institution_v1 <- function() "ohne Institutsangabe"
data_institution_tax_error_text_v1 <- function(code) switch(as.character(code),
  institution_tax_settings_input_invalid = "Ein Betrag ist nicht gültig: nicht negativ, höchstens zwei Nachkommastellen.",
  institution_tax_settings_institution_unknown = "Ein Institut steht an keinem Konto mehr. Bitte oben „Einstellungen lesen“ drücken.",
  institution_tax_settings_confirmation_required = "Die Angaben wurden nicht bestätigt.",
  "Der Speicher der Steuerangaben je Institut ließ sich nicht lesen oder schreiben. Konten und Buchungen sind davon nicht berührt.")

new_data_institution_tax_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_institution_tax_settings.py")
  space <- runtime_data_space_path(context)
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_institution_tax_abort_v1("institution_tax_settings_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
    actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      data_institution_tax_abort_v1(if (is.null(parsed$code)) "institution_tax_settings_store_invalid" else parsed$code)
    parsed$result
  }
  checked <- function(result, status) {
    if (!is.list(result) || !identical(result$contract_version, "institution_tax_settings_v1") || !result$status %in% status || isTRUE(result$canonical_write))
      data_institution_tax_abort_v1("institution_tax_settings_store_invalid")
    result
  }
  stamp_valid <- function(value) is.character(value) && length(value) == 1L && !is.na(value) && grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", value)
  structure(list(
    contract_version = "data_institution_tax_service_v1",
    # Institute der Stammdaten und der gueltige Stand je Institut, Jahr und Angabe.
    read = function() checked(run("read", list()), "ready"),
    # `entries`: Liste aus list(institution_label, tax_year, field_code, amount_decimal); amount_decimal NULL leert den Eintrag.
    record = function(entries, recorded_at_utc, confirmed) {
      if (!isTRUE(confirmed)) data_institution_tax_abort_v1("institution_tax_settings_confirmation_required")
      if (!is.list(entries) || !length(entries) || !stamp_valid(recorded_at_utc)) data_institution_tax_abort_v1("institution_tax_settings_input_invalid")
      checked(run("record", list(entries = unname(entries), recorded_at_utc = recorded_at_utc, confirmed = TRUE)), "recorded")
    },
    # Nach dem Umbenennen eines Instituts ziehen seine Angaben mit.
    rename = function(old_label, new_label, recorded_at_utc, confirmed) {
      if (!isTRUE(confirmed)) data_institution_tax_abort_v1("institution_tax_settings_confirmation_required")
      if (!stamp_valid(recorded_at_utc)) data_institution_tax_abort_v1("institution_tax_settings_input_invalid")
      checked(run("rename", list(old_label = old_label, new_label = new_label, recorded_at_utc = recorded_at_utc, confirmed = TRUE)),
        c("renamed", "unchanged"))
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_data_institution_tax_service_v1", "list"))
}

# Sparer-Pauschbetrag des Jahres aus dem Rechtsstand des Regelmoduls: allein und bei Zusammenveranlagung. NULL ohne Eintrag.
data_institution_tax_allowance_v1 <- function(project_root, year) {
  path <- file.path(project_root, "plugins", "tax_models", "tax_de_personal_income_tax_projection_v2", "annual-legal-values.csv")
  values <- tryCatch(utils::read.csv(path, colClasses = "character", encoding = "UTF-8"), error = function(error) NULL)
  if (!is.data.frame(values)) return(NULL)
  pick <- function(code) { hit <- values$value_decimal[values$tax_year == as.character(year) & values$value_code == code]; if (length(hit) == 1L) as.numeric(hit) else NA_real_ }
  single <- pick("capital_income_allowance_single")
  if (is.na(single)) NULL else list(single = single, joint = pick("capital_income_allowance_joint"))
}
data_institution_tax_euro_v1 <- function(value) paste(formatC(value, format = "f", digits = 2, big.mark = ".", decimal.mark = ","), "€")

# Institutsarten mit Steuerabzug (Freistellungsauftrag, Verlusttoepfe, Quellensteuer): Bank und Broker/Depotbank.
# Krypto-Boersen, Wallets, Edelmetallverwahrung und Sonstiges fuehren keinen; er gilt nur bei Banken und Depotbanken.
data_institution_tax_kinds_v1 <- function() c("bank", "broker")

# Eine Zeile je Institut der Stammdaten mit aktiven Konten - Konten ohne Institutsangabe zuletzt - und den Werten des Jahres.
# `kinds`: Institutsschluessel -> Art aus "Institute · Art und Konten" (NULL: Arten unbekannt, alle zeigen). Ohne Art bleibt ein
# Institut sichtbar (mit Hinweis), mit gespeicherten Angaben ebenso; sonst zaehlt es als ausgeblendet (Attribut "hidden").
data_institution_tax_rows_v1 <- function(model, year, kinds = NULL) {
  if (!is.list(model) || !is.list(model$institutions)) return(list())
  all_settings <- if (is.list(model$settings)) model$settings else list()
  stored <- Filter(function(row) identical(as.integer(row$tax_year), as.integer(year)), all_settings)
  with_entries <- unique(vapply(all_settings, function(row) as.character(row$institution_key), character(1L)))
  rows <- list(); hidden <- 0L
  for (institution in model$institutions) {
    if (as.integer(institution$active_account_count) < 1L) next
    key <- as.character(institution$institution_key)
    kind <- if (is.null(kinds) || !nzchar(key) || is.null(kinds[[key]]) || is.na(kinds[[key]])) "" else as.character(kinds[[key]])
    if (!is.null(kinds) && nzchar(as.character(institution$institution_label)) && nzchar(kind) &&
        !kind %in% data_institution_tax_kinds_v1() && !key %in% with_entries) { hidden <- hidden + 1L; next }
    values <- list()
    for (field in names(data_institution_tax_fields_v1())) {
      hit <- Filter(function(row) identical(row$institution_key, key) && identical(row$field_code, field), stored)
      values[[field]] <- if (length(hit)) suppressWarnings(as.numeric(hit[[1L]]$amount_decimal)) else NA_real_
    }
    label <- as.character(institution$institution_label)
    rows[[length(rows) + 1L]] <- list(key = key, label = label, shown = if (nzchar(label)) label else data_institution_tax_no_institution_v1(),
      accounts = as.integer(institution$active_account_count), values = values, kind_missing = !is.null(kinds) && nzchar(label) && !nzchar(kind))
  }
  attr(rows, "hidden") <- hidden
  rows
}
data_institution_tax_input_id_v1 <- function(field, index) sprintf("data_institution_tax_%s_%d", field, as.integer(index))
data_institution_tax_form_v1 <- function(rows, year, allowance = NULL, orphan_count = 0L) {
  if (!length(rows)) return(shiny::p(class = "pl-field-hint", "Zuerst oben „Einstellungen lesen“ drücken."))
  fields <- data_institution_tax_fields_v1()
  total <- sum(vapply(rows, function(row) { value <- row$values$capital_income_allowance; if (is.na(value)) 0 else value }, numeric(1L)))
  shiny::tagList(
    shiny::div(style = "overflow-x:auto", shiny::tags$table(class = "table shiny-table table-striped",
      shiny::tags$thead(shiny::tags$tr(lapply(c("Institut", "Konten", unname(fields)), shiny::tags$th))),
      shiny::tags$tbody(lapply(seq_along(rows), function(index) {
        row <- rows[[index]]
        shiny::tags$tr(shiny::tags$td(shiny::tags$strong(row$shown), if (isTRUE(row$kind_missing)) shiny::tags$span(class = "pl-field-hint", " · Art fehlt")), shiny::tags$td(row$accounts),
          lapply(names(fields), function(field) shiny::tags$td(shiny::numericInput(data_institution_tax_input_id_v1(field, index), NULL,
            value = row$values[[field]], min = 0, step = 0.01, width = "150px"))))
      })))),
    shiny::p(class = "pl-field-hint", sprintf("Freistellungsaufträge %s zusammen: %s%s", year, data_institution_tax_euro_v1(total),
      if (is.null(allowance)) "" else sprintf(" · Sparer-Pauschbetrag %s: %s, bei Zusammenveranlagung %s", year,
        data_institution_tax_euro_v1(allowance$single), data_institution_tax_euro_v1(allowance$joint)))),
    if (!is.null(allowance) && total > allowance$single + 1e-9) portelyra_status_panel("Mehr freigestellt als der Sparer-Pauschbetrag",
      sprintf(paste("Die Freistellungsaufträge %s übersteigen zusammen den Sparer-Pauschbetrag für Alleinstehende (%s).",
        "Die Rechnung nimmt sie, wie sie eingetragen sind; bei Zusammenveranlagung gilt %s."), year,
        data_institution_tax_euro_v1(allowance$single), data_institution_tax_euro_v1(allowance$joint)), tone = "warning"),
    if (isTRUE(attr(rows, "hidden") > 0L) || any(vapply(rows, function(row) isTRUE(row$kind_missing), logical(1L)))) shiny::p(class = "pl-field-hint", paste0(
      if (isTRUE(attr(rows, "hidden") > 0L)) sprintf("%d Institut(e) ohne Steuerabzug ausgeblendet (Krypto-Börse, Wallet, Edelmetallverwahrung, Sonstiges) – ohne Eintrag gilt 0 €. ", as.integer(attr(rows, "hidden"))) else "",
      if (any(vapply(rows, function(row) isTRUE(row$kind_missing), logical(1L)))) "„Art fehlt“: unter „Institute · Art und Konten“ festlegen, dann erscheinen hier nur Banken und Depotbanken." else "")),
    if (as.integer(orphan_count) > 0L) shiny::p(class = "pl-field-hint", sprintf(
      "%d gespeicherte Angabe(n) gehören zu einem Institut, das an keinem Konto mehr steht; die Rechnung nutzt sie nicht.", as.integer(orphan_count))))
}
# Was zu speichern ist: je geaenderter Angabe ein Eintrag. `values(field, index)` liefert die Eingabe der Karte.
# Eine unzulaessige Eingabe nennt Institut und Feld; dann wird nichts geschrieben.
data_institution_tax_plan_v1 <- function(rows, year, values) {
  entries <- list()
  fields <- data_institution_tax_fields_v1()
  for (index in seq_along(rows)) {
    row <- rows[[index]]
    for (field in names(fields)) {
      entered <- values(field, index)
      entered <- if (is.null(entered) || length(entered) != 1L || !is.numeric(entered) || is.na(entered)) NA_real_ else as.numeric(entered)
      label <- sprintf("%s, %s", row$shown, sub(" in €$", "", fields[[field]]))
      if (!is.na(entered) && (entered < 0 || entered > 9999999999)) return(list(error = sprintf("%s: Der Betrag darf nicht negativ sein.", label)))
      if (!is.na(entered) && abs(entered * 100 - round(entered * 100)) > 1e-6) return(list(error = sprintf("%s: höchstens zwei Nachkommastellen.", label)))
      before <- row$values[[field]]
      same <- (is.na(entered) && is.na(before)) || (!is.na(entered) && !is.na(before) && abs(entered - before) < 0.005)
      if (same) next
      entries[[length(entries) + 1L]] <- list(institution_label = row$label, tax_year = as.integer(year), field_code = field,
        amount_decimal = if (is.na(entered)) NULL else formatC(round(entered, 2), format = "f", digits = 2))
    }
  }
  list(entries = entries)
}

# Karte im Reiter "4. Steuer", unter "Steuerangaben je Jahr".
data_institution_tax_card_ui_v1 <- function(current_year = as.integer(format(Sys.Date(), "%Y"))) {
  # Ab 2016 wie die Steuerangaben je Jahr (#496): Die Jahresrechnung 2016-2019 braucht die Freistellung je Institut.
  years <- rev(seq.int(2016L, max(2016L, as.integer(current_year))))
  portelyra_card("Freistellung, Verlusttöpfe und Quellensteuer je Institut", help = "app-data#steuer", class = "pl-write-boundary",
    copy = "Kapitalerträge rechnet das Regelmodul je Institut – mit dem Freistellungsauftrag, den Verlusttöpfen und der anrechenbaren Quellensteuer, die dort geführt werden.",
    note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-institution-tax", paste(
      "Ohne Eintrag ist der Freistellungsauftrag 0 €. Private Veräußerungsgeschäfte und sonstige Einkünfte (Krypto) rechnen über alle Institute, mit ihren Freigrenzen.")),
    shiny::div(class = "pl-field-row",
      shiny::selectInput("data_institution_tax_year", "Steuerjahr", choices = as.character(years), selected = as.character(years[[1L]]), width = "160px")),
    shiny::uiOutput("data_institution_tax_form"),
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("data_institution_tax_save", "Angaben je Institut speichern", class = "btn-primary")),
    shiny::uiOutput("data_institution_tax_notice"),
    shiny::p(class = "pl-field-hint", paste(
      "Verlusttopf zum 1.1.: nur eintragen, wenn Sie einen Stand vorgeben wollen, etwa aus der Verlustbescheinigung des Instituts.",
      "Leer heißt: Die Jahresrechnung schreibt den Stand aus dem Vorjahr fort; 0 heißt: Der Topf beginnt leer.",
      "Gespeichert wird nur, was geändert ist; ein geleertes Feld löscht den Eintrag. Die Jahresrechnung steht in der App „Steuer“.")))
}

# `service`: new_data_institution_tax_service_v1 oder NULL. `now_utc`: Zeitstempel fuer den Eintrag.
# Gibt `read` zurueck - die Karte liest, wenn der Reiter seine Einstellungen liest.
# `kinds_service`: Institutsstamm (new_data_institution_master_service_v1) oder NULL - liefert die Art je Institut.
data_institution_tax_server_v1 <- function(input, output, session, service, project_root,
    now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), kinds_service = NULL) {
  model <- shiny::reactiveVal(NULL)
  kinds <- shiny::reactiveVal(NULL)
  notice <- shiny::reactiveVal(NULL)
  failure <- shiny::reactiveVal(NULL)
  read <- function() {
    if (is.null(service)) { failure("institution_tax_settings_store_invalid"); return(invisible(NULL)) }
    value <- tryCatch(service$read(), error = function(error) structure(list(), code = if (is.null(error$code)) "institution_tax_settings_store_invalid" else error$code))
    if (!is.null(attr(value, "code"))) { failure(attr(value, "code")); model(NULL) } else { failure(NULL); model(value) }
    # Ohne lesbaren Institutsstamm zeigt die Karte alle Institute wie bisher.
    master <- if (is.null(kinds_service)) NULL else tryCatch(kinds_service$read(), error = function(error) NULL)
    kinds(if (is.list(master) && is.list(master$institutions)) stats::setNames(
      lapply(master$institutions, function(row) if (is.null(row$kind)) NA_character_ else as.character(row$kind)),
      vapply(master$institutions, function(row) as.character(row$institution_key), character(1L))) else NULL)
    invisible(NULL)
  }
  year <- shiny::reactive({ value <- suppressWarnings(as.integer(input$data_institution_tax_year)); if (length(value) == 1L && !is.na(value)) value else as.integer(format(Sys.Date(), "%Y")) })
  rows <- shiny::reactive(data_institution_tax_rows_v1(model(), year(), kinds()))
  output$data_institution_tax_form <- shiny::renderUI({
    if (!is.null(failure())) return(portelyra_status_panel("Steuerangaben je Institut nicht lesbar", data_institution_tax_error_text_v1(failure()), tone = "warning"))
    current <- model()
    data_institution_tax_form_v1(rows(), year(), data_institution_tax_allowance_v1(project_root, year()), if (is.list(current)) current$orphan_count else 0L)
  })
  output$data_institution_tax_notice <- shiny::renderUI({
    current <- notice()
    if (is.list(current)) portelyra_status_panel(current$title, current$copy, tone = current$tone)
  })
  shiny::observeEvent(input$data_institution_tax_year, notice(NULL), ignoreInit = TRUE)
  shiny::observeEvent(input$data_institution_tax_save, {
    current <- shiny::isolate(rows())
    if (!length(current)) { notice(list(tone = "warning", title = "Noch nichts gelesen", copy = "Zuerst oben „Einstellungen lesen“ drücken.")); return() }
    plan <- data_institution_tax_plan_v1(current, year(), function(field, index) input[[data_institution_tax_input_id_v1(field, index)]])
    if (!is.null(plan$error)) { notice(list(tone = "error", title = "Nicht gespeichert", copy = plan$error)); return() }
    if (!length(plan$entries)) { notice(list(tone = "neutral", title = "Nichts geändert", copy = "Die Angaben stimmen mit dem gespeicherten Stand überein.")); return() }
    result <- tryCatch(service$record(plan$entries, now_utc(), TRUE), error = function(error) structure(list(), code = if (is.null(error$code)) "institution_tax_settings_store_invalid" else error$code))
    if (!is.null(attr(result, "code"))) { notice(list(tone = "error", title = "Nicht gespeichert", copy = data_institution_tax_error_text_v1(attr(result, "code")))); return() }
    read()
    notice(list(tone = "positive", title = sprintf("%d Angabe(n) für %s gespeichert", as.integer(result$written_count), year()),
      copy = "Die Jahresrechnung in der App „Steuer“ rechnet ab jetzt damit."))
  })
  invisible(list(read = read, model = model))
}
