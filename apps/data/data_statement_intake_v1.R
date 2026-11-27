# Monatlicher Eingang (#513, Festlegung 25.10.2026): Belegordner als Quelle, Rezept je Institut, ein Schritt je Institut.
# Ablauf: laut Rezept herunterladen und in den Unterordner des Instituts legen; "Eingang pruefen" (liest nur); je Institut die
# neuen Dateien mit einem Klick ablegen (genau die gezeigte Pruefung); danach im Import des Instituts buchen - mit den Dateien aus
# der Ablage, dort mit Vorschau und Bestaetigung wie bisher. Die Rechnung liegt in migrations/reference/statement_intake_v1.py.

# R vor 4.4 (Ubuntu 24.04 bringt 4.3.3) kennt `%||%` nicht in base, Shiny liefert ihn nicht (Endabnahme 19.11.2026).
if (!exists("%||%", mode = "function")) `%||%` <- function(x, y) if (is.null(x)) y else x
DATA_STATEMENT_INTAKE_STATES_V1 <- c(new = "neu", filed = "schon abgelegt", withdrawn = "abgelegt, zurückgezogen", removed = "früher entfernt",
  duplicate = "doppelt im Ordner", too_large = "größer als 1 GB", unreadable = "nicht lesbar")
DATA_STATEMENT_INTAKE_REASONS_V1 <- c(no_period = "kein Zeitraum erkannt", no_account = "kein eindeutiges Konto", account_closed = "Konto geschlossen", account_inactive = "Konto ruht (inaktiv); erst wieder aktivieren",
  too_large = "zu groß für den Vorschlag", unreadable = "nicht lesbar")
DATA_STATEMENT_INTAKE_KINDS_V1 <- c(securities = "Wertpapier-Belege", crypto = "Krypto-Exporte", rewards = "Rewards", cash = "Cash-Auszüge", fx = "Devisen-Belege")

data_statement_intake_ui_v1 <- function() shiny::tagList(
  portelyra_card("Monatlicher Eingang", help = "monatlicher-eingang",
    copy = "Belege aus einem Ordner außerhalb von Portelyra: je Institut prüfen, mit einem Klick ablegen, dann im Import buchen.",
    note = portelyra_note_v1(title = "So läuft der Monat", id = "data-statement-intake",
      "1. Laut Rezept des Instituts herunterladen und in seinen Unterordner des Belegordners legen (Jahre als weitere Unterordner gehen auch).",
      "2. „Eingang prüfen“ liest den Ordner, ändert nichts und zeigt je Institut: neu, schon abgelegt, nicht erkannt mit Grund.",
      "3. Je Institut „Neue Dateien ablegen“: Die Dateien werden unverändert in die Ablage kopiert (sie liegt im Backup). Umbenennen oder Löschen im Belegordner schadet danach nicht.",
      "4. „Im Import buchen“ öffnet den Import des Instituts; dort „… oder Dateien aus der Ablage nehmen“, das Institut wählen, prüfen und buchen. Danach im Raster der Ablage die offenen Monate ansehen."),
    shiny::h4(class = "pl-section-title", "Belegordner"),
    shiny::uiOutput("statement_intake_folder_state"),
    shiny::div(class = "pl-form-grid",
      shiny::textInput("statement_intake_folder", "Ordner (vollständiger Pfad)", value = "", width = "100%", placeholder = "/home/…/Belege"),
      shiny::div(style = "align-self:end;display:flex;gap:8px;flex-wrap:wrap",
        shiny::actionButton("statement_intake_folder_pick", "Ordner wählen …", class = "btn-default"),
        shiny::actionButton("statement_intake_folder_save", "Als Belegordner festlegen", class = "btn-default"))),
    shiny::p(class = "pl-field-hint", "Je Institut ein Unterordner, benannt wie das Institut (etwa „Scalable“, „ING“, „Trade Republic“). Allgemeine Unterlagen in „<Jahr>/Sonstiges“ gelten als Sonstiges dieses Jahres, Belege in „<Jahr>/Vorabpauschalen“ als Vorabpauschale (Jahr des Zuflusses: die für 2024 in 2025). Portelyra liest den Ordner nur."),
    shiny::p(class = "pl-field-hint", paste("Zugeordnet werden die Dateien über die Kontonummer im Beleg (IBAN, Depotnummer oder Adresse) und die Institutsangabe am Konto.",
      "Beides bitte bei jedem Konto eintragen (2. Stammdaten → „Konto / Wallet anlegen oder umbenennen“: Institut und „Kontonummer / IBAN / Adresse“) – sonst bleiben Dateien ohne Konto offen.")),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("statement_intake_scan", "Eingang prüfen", class = "btn-primary"),
      shiny::checkboxInput("statement_intake_withdrawn", "Zurückgezogene Dateien erneut vorschlagen", FALSE)),
    shiny::p(class = "pl-field-hint", paste("Eine in der Ablage zurückgezogene Datei schlägt der Eingang sonst nicht wieder vor – damit eine bewusst",
      "entfernte Datei nicht jeden Monat auftaucht. Wer Dateien zum Neu-Ablegen zurückgezogen hat, setzt das Häkchen und prüft neu; die alten Einträge bleiben zurückgezogen.")),
    shiny::uiOutput("statement_intake_notice"),
    shiny::uiOutput("statement_intake_overview"),
    shiny::uiOutput("statement_intake_institution_block"),
    shiny::tags$details(class = "pl-disclosure pl-lazy", id = "statement_intake_recipes_details",
      shiny::tags$summary("Rezepte aller Institute"),
      shiny::p(class = "pl-field-hint", "Was je Institut herunterzuladen ist, für welchen Zeitraum und welcher Leser es liest. Die Rezepte sind ein Entwurf – Korrekturen bitte melden."),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("statement_intake_recipes")))))

# Die Rezepte als Tabelle (alle Institute).
data_statement_intake_recipes_frame_v1 <- function(recipes) {
  if (!length(recipes)) return(data.frame())
  data.frame(Institut = vapply(recipes, function(recipe) recipe$label, character(1L)),
    Stand = vapply(recipes, function(recipe) recipe$status_label, character(1L)),
    Herunterladen = vapply(recipes, function(recipe) paste(unlist(recipe$downloads), collapse = " · "), character(1L)),
    Zeitraum = vapply(recipes, function(recipe) recipe$period_rule, character(1L)),
    `Deckt ab` = vapply(recipes, function(recipe) recipe$covers, character(1L)),
    Leser = vapply(recipes, function(recipe) if (!length(recipe$readers)) "nur ablegen" else paste(vapply(recipe$readers, function(reader)
      paste0(DATA_STATEMENT_INTAKE_KINDS_V1[[reader$import_kind]], ": ", reader$label), character(1L)), collapse = " · "), character(1L)),
    Unterordner = vapply(recipes, function(recipe) paste(unlist(recipe$folders), collapse = ", "), character(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
}

# Je Institut eine Zeile der Uebersicht und ein Eintrag der Auswahl.
data_statement_intake_label_v1 <- function(group) {
  name <- if (is.null(group$folder)) "ohne Institutsordner" else group$folder
  recipe <- if (is.null(group$recipe_label)) "kein Rezept" else group$recipe_label
  counts <- group$counts
  refile <- as.integer(counts$refile %||% 0L)
  paste0(sprintf("%s · %s · %d neu, davon %d bereit · %d schon abgelegt", name, recipe, as.integer(counts$new), as.integer(counts$ready), as.integer(counts$filed)),
    if (refile > 0L) sprintf(" · %d erneut ablegbar", refile) else "")
}
# Zahl der Dateien, die "ablegen" ablegt: neue und - mit der Wahl - zurueckgezogene (rc.320).
data_statement_intake_storable_v1 <- function(group) as.integer(group$counts$ready) + as.integer(group$counts$refile %||% 0L)
data_statement_intake_overview_frame_v1 <- function(scan) {
  groups <- scan$institutions
  if (!length(groups)) return(data.frame())
  data.frame(Unterordner = vapply(groups, function(group) if (is.null(group$folder)) "– ohne Institutsordner –" else group$folder, character(1L)),
    Rezept = vapply(groups, function(group) if (is.null(group$recipe_label)) "kein Rezept: nur ablegen" else paste0(group$recipe_label,
      if (identical(group$recipe_status, "historical")) " (historisch)" else if (identical(group$recipe_status, "manual")) " (von Hand)" else ""), character(1L)),
    Neu = vapply(groups, function(group) as.character(group$counts$new), character(1L)),
    `bereit zum Ablegen` = vapply(groups, function(group) as.character(group$counts$ready), character(1L)),
    `nicht erkannt` = vapply(groups, function(group) as.character(group$counts$open), character(1L)),
    `schon abgelegt` = vapply(groups, function(group) as.character(group$counts$filed), character(1L)),
    `zurückgezogen` = vapply(groups, function(group) { withdrawn <- as.integer(group$counts$withdrawn %||% 0L); refile <- as.integer(group$counts$refile %||% 0L)
      if (refile > 0L) sprintf("%d (%d erneut ablegbar)", withdrawn, refile) else as.character(withdrawn) }, character(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
}
data_statement_intake_files_frame_v1 <- function(group, account_names = character()) {
  rows <- group$files
  if (!length(rows)) return(data.frame())
  text <- function(value) if (is.null(value)) "–" else as.character(value)
  data.frame(Datei = vapply(rows, function(row) as.character(row$relative_path), character(1L)),
    Stand = vapply(rows, function(row) { state <- DATA_STATEMENT_INTAKE_STATES_V1[[as.character(row$state)]]
      reason <- function() if (is.null(row$reason)) "unvollständig" else { found <- DATA_STATEMENT_INTAKE_REASONS_V1[as.character(row$reason)]; if (is.na(found)) as.character(row$reason) else found }
      # Zurueckgezogen mit Vorschlag (rc.320): nur, wenn "erneut vorschlagen" gewaehlt war - dann hat die Zeile einen Zeitraum oder einen Grund.
      offered <- identical(row$state, "withdrawn") && (isTRUE(row$complete) || !is.null(row$reason))
      if (identical(row$state, "new") && !isTRUE(row$complete)) paste0(state, " – nicht erkannt: ", reason())
      else if (offered && isTRUE(row$complete)) paste0(state, " – wird erneut abgelegt")
      else if (offered) paste0(state, " – nicht erkannt: ", reason()) else state }, character(1L)),
    `Erkannt von` = vapply(rows, function(row) text(row$reader), character(1L)),
    Art = vapply(rows, function(row) if (is.null(row$document_kind)) "–" else data_statement_archive_kind_label_v1(row$document_kind), character(1L)),
    Zeitraum = vapply(rows, function(row) if (is.null(row$period_from)) "–" else if (identical(row$period_from, row$period_to)) as.character(row$period_from)
      else paste(row$period_from, "bis", row$period_to), character(1L)),
    Konto = vapply(rows, function(row) { ids <- unlist(row$account_ids, use.names = FALSE); if (!length(ids)) "–" else paste(vapply(ids, function(id) {
      name <- unname(account_names[id]); if (length(name) != 1L || is.na(name)) "Konto" else name }, character(1L)), collapse = ", ") }, character(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
}

# Die Auswahl "Institut" (#517): Eintraege und Wahl entstehen mit der Auswahl selbst. Vorher setzte nur der Knopf "Eingang
# pruefen" die Eintraege nachtraeglich; die Pruefung nach dem Ablegen baute die Auswahl leer neu auf ("Bitte warten").
# Gewaehlt ist das Institut, mit dem man gearbeitet hat (nach dem Ablegen geht es dort mit "Im Import buchen" weiter),
# sonst das erste mit bereiten Dateien, sonst das erste.
data_statement_intake_choices_v1 <- function(groups) {
  if (!length(groups)) return(c("Keine Unterordner" = ""))
  stats::setNames(as.character(seq_along(groups)), vapply(groups, data_statement_intake_label_v1, character(1L)))
}
data_statement_intake_pick_v1 <- function(groups, folder = NULL) {
  if (!length(groups)) return("")
  if (is.character(folder) && length(folder) == 1L) {
    same <- which(vapply(groups, function(group) identical(group$folder, folder), logical(1L)))
    if (length(same)) return(as.character(same[[1L]]))
  }
  ready <- which(vapply(groups, function(group) as.integer(group$counts$ready) > 0L, logical(1L)))
  as.character(if (length(ready)) ready[[1L]] else 1L)
}

# Hinweis auf zurueckgezogene Dateien in der Uebersicht (rc.320).
data_statement_intake_withdrawn_text_v1 <- function(scan) {
  withdrawn <- as.integer(scan$totals$withdrawn %||% 0L); refile <- as.integer(scan$totals$refile %||% 0L)
  if (withdrawn == 0L) return("")
  if (isTRUE(scan$include_withdrawn)) return(sprintf(" %d zurückgezogen, davon %d erneut ablegbar.", withdrawn, refile))
  sprintf(" %d in der Ablage zurückgezogen – mit „Zurückgezogene Dateien erneut vorschlagen“ wieder ablegbar.", withdrawn)
}

# Das Rezept eines Instituts als Kasten ueber seinen Dateien.
data_statement_intake_recipe_ui_v1 <- function(recipe) {
  if (is.null(recipe)) return(shiny::p(class = "pl-field-hint",
    paste("Für diesen Unterordner gibt es kein Rezept. Seine Dateien lassen sich ablegen, wenn der Vorschlag Zeitraum und Konto erkennt; sonst bitte über die Ablage hinterlegen.",
      "Das Konto erkennt der Vorschlag an der Kontonummer im Beleg; heißt der Ordner wie die Institutsangabe genau eines Instituts, gehören Steuerunterlagen ohne Kontonummer zu dessen Konten.",
      "Ein Institut ohne Leser ist ein Fall für den experimentellen generischen Leser.")))
  shiny::div(class = "pl-card", style = "background:var(--pl-surface-alt, #f6f6f3);padding:10px 14px",
    shiny::strong(paste0("Rezept · ", recipe$label, " · ", recipe$status_label)),
    shiny::tags$ul(lapply(unlist(recipe$downloads), shiny::tags$li)),
    shiny::p(class = "pl-field-hint", paste0("Zeitraum: ", recipe$period_rule, " Deckt ab: ", recipe$covers, ".")),
    shiny::p(class = "pl-field-hint", if (!length(recipe$readers)) "Leser: keiner – nur ablegen, von Hand buchen." else paste0("Leser: ",
      paste(vapply(recipe$readers, function(reader) paste0(DATA_STATEMENT_INTAKE_KINDS_V1[[reader$import_kind]], " – ", reader$label),
        character(1L)), collapse = " · "), ".")))
}

# 'navigate(kind, adapter)' oeffnet den Import einer Art mit diesem Leser; 'choose_folder()' fragt das System nach einem Ordner
# (NULL ohne Dialog); 'active' sagt, ob der Reiter offen ist - erst dann wird gelesen.
data_statement_intake_server_v1 <- function(input, output, session, service, accounts, resolve_id, navigate = function(kind, adapter) invisible(NULL),
    choose_folder = NULL, active = shiny::reactive(TRUE),
    now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) {
  setup <- shiny::reactiveVal(NULL); scan <- shiny::reactiveVal(NULL); notice <- shiny::reactiveVal(NULL); tick <- shiny::reactiveVal(0L)
  wanted <- shiny::reactiveVal("")
  attempt <- function(expression) tryCatch(expression, spot_data_statement_archive_error_v1 = function(error) error$code, error = function(error) "statement_archive_store_invalid")
  failed <- function(title, code) notice(list(title = title, tone = "error", copy = data_statement_archive_error_text_v1(code)))
  # Gelesen wird erst, wenn der Reiter offen ist.
  shiny::observeEvent(list(active(), tick()), {
    if (!isTRUE(active()) || is.null(service)) return(invisible(NULL))
    value <- attempt(service$intake_read())
    setup(if (is.list(value)) value else structure(list(), code = value))
    if (is.list(value) && !is.null(value$folder) && !nzchar(shiny::isolate(input$statement_intake_folder) %||% "")) shiny::updateTextInput(session, "statement_intake_folder", value = value$folder)
  })
  recipes <- shiny::reactive({ value <- setup(); if (is.list(value) && length(value$recipes)) value$recipes else list() })
  recipe_of <- function(key) { hit <- Filter(function(recipe) identical(recipe$key, key), recipes()); if (length(hit) == 1L) hit[[1L]] else NULL }
  output$statement_intake_folder_state <- shiny::renderUI({
    value <- setup()
    if (is.null(service) || !is.null(attr(value, "code"))) return(portelyra_status_panel("Ablage nicht lesbar", data_statement_archive_error_text_v1("statement_archive_store_invalid"), tone = "warning"))
    if (is.null(value)) return(NULL)
    if (is.null(value$folder)) return(portelyra_status_panel("Noch kein Belegordner", "Einmal einen Ordner wählen – danach prüft „Eingang prüfen“ ihn jeden Monat.", tone = "neutral"))
    shiny::p(class = "pl-field-hint", paste0("Belegordner: ", value$folder))
  })
  shiny::observeEvent(input$statement_intake_folder_pick, {
    picked <- if (is.function(choose_folder)) tryCatch(choose_folder(), error = function(error) NULL) else NULL
    if (is.character(picked) && length(picked) == 1L && nzchar(picked)) shiny::updateTextInput(session, "statement_intake_folder", value = picked)
    else notice(list(tone = "neutral", title = "Kein Ordner gewählt", copy = "Ohne Auswahl im Dialog bitte den vollständigen Pfad ins Feld schreiben."))
  })
  shiny::observeEvent(input$statement_intake_folder_save, {
    folder <- trimws(input$statement_intake_folder %||% "")
    if (is.null(service)) return(failed("Nicht festgelegt", "statement_archive_store_invalid"))
    if (!nzchar(folder)) return(failed("Nicht festgelegt", "statement_intake_folder_invalid"))
    result <- attempt(service$intake_folder(folder, now_utc(), TRUE))
    if (!is.list(result)) return(failed("Nicht festgelegt", result))
    scan(NULL); tick(tick() + 1L)
    notice(list(tone = "positive", title = "Belegordner festgelegt", copy = paste0(result$folder, " – jetzt „Eingang prüfen“.")))
  })
  shiny::observeEvent(input$statement_intake_scan, {
    if (is.null(service)) return(failed("Nicht geprüft", "statement_archive_store_invalid"))
    result <- shiny::withProgress(message = "Belegordner wird gelesen", value = 0.3, attempt(service$intake_scan(isTRUE(input$statement_intake_withdrawn))))
    if (!is.list(result)) { scan(NULL); return(failed("Nicht geprüft", result)) }
    wanted(data_statement_intake_pick_v1(result$institutions)); scan(result); notice(NULL)
  })
  account_names <- shiny::reactive({
    rows <- tryCatch(data_statement_archive_accounts_v1(accounts(), resolve_id, if (is.null(service)) NULL else tryCatch(service$account_states(), error = function(error) NULL)),
                     error = function(error) list())
    stats::setNames(vapply(rows, function(row) row$name, character(1L)), vapply(rows, function(row) row$id, character(1L)))
  })
  output$statement_intake_overview <- shiny::renderUI({
    value <- scan(); if (is.null(value)) return(NULL)
    totals <- value$totals
    shiny::tagList(
      portelyra_status_panel(sprintf("%d neue Datei(en), %d bereit zum Ablegen", as.integer(totals$new), as.integer(totals$ready)),
        paste0(sprintf("%d Datei(en) im Belegordner, %d schon in der Ablage, %d nicht erkannt. Gelesen, nichts geändert.", as.integer(value$file_count),
          as.integer(totals$filed), as.integer(totals$open)), data_statement_intake_withdrawn_text_v1(value)),
        tone = if (as.integer(totals$ready) + as.integer(totals$refile %||% 0L) > 0L) "neutral" else "positive"),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("statement_intake_overview_table")),
      shiny::selectInput("statement_intake_institution", "Institut", choices = data_statement_intake_choices_v1(value$institutions),
        selected = shiny::isolate(wanted()), width = "100%"))
  })
  output$statement_intake_overview_table <- shiny::renderTable(data_statement_intake_overview_frame_v1(shiny::req(scan())), striped = TRUE, bordered = TRUE)
  chosen <- shiny::reactive({
    value <- scan(); index <- suppressWarnings(as.integer(input$statement_intake_institution))
    if (is.null(value) || length(index) != 1L || is.na(index) || index < 1L || index > length(value$institutions)) NULL else value$institutions[[index]]
  })
  output$statement_intake_institution_block <- shiny::renderUI({
    group <- chosen(); if (is.null(group)) return(NULL)
    recipe <- if (is.null(group$recipe_key)) NULL else recipe_of(group$recipe_key)
    ready <- as.integer(group$counts$ready); storable <- data_statement_intake_storable_v1(group)
    readers <- if (is.null(recipe)) list() else recipe$readers
    shiny::tagList(
      data_statement_intake_recipe_ui_v1(recipe),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("statement_intake_files")),
      shiny::div(class = "pl-editor-actions",
        if (storable > 0L && !is.null(group$folder)) shiny::actionButton("statement_intake_store", if (storable > ready)
          sprintf("%d Datei(en) ablegen (davon %d erneut)", storable, storable - ready) else sprintf("%d neue Datei(en) ablegen", ready), class = "btn-primary"),
        lapply(seq_along(readers), function(index) shiny::actionButton(paste0("statement_intake_book_", index),
          paste0("Im Import buchen: ", DATA_STATEMENT_INTAKE_KINDS_V1[[readers[[index]]$import_kind]], " – ", readers[[index]]$label),
          class = "btn-default"))),
      if (storable > 0L && is.null(group$folder)) shiny::p(class = "pl-field-hint", "Dateien ohne Institutsordner legt der Eingang nicht ab: bitte in den Unterordner ihres Instituts verschieben."),
      if (as.integer(group$counts$open) > 0L) shiny::p(class = "pl-field-hint", "Nicht erkannte Dateien bleiben, wo sie sind. Über „Auszüge und Belege je Konto“ (2. Stammdaten · Ablage) lassen sie sich mit eigenen Angaben hinterlegen."))
  })
  output$statement_intake_files <- shiny::renderTable(data_statement_intake_files_frame_v1(shiny::req(chosen()), account_names()), striped = TRUE, bordered = TRUE)
  shiny::observeEvent(input$statement_intake_store, {
    group <- chosen(); if (is.null(group) || is.null(service) || is.null(group$folder)) return()
    # Abgelegt wird mit derselben Wahl wie bei der gezeigten Pruefung, sonst passt ihr Pruefwert nicht.
    include <- isTRUE(scan()$include_withdrawn)
    result <- shiny::withProgress(message = "Dateien werden abgelegt", value = 0.4, attempt(service$intake_store(group$folder, group$proposal_fingerprint, now_utc(), TRUE, include)))
    if (!is.list(result)) return(failed(sprintf("%s: nichts abgelegt", group$folder), result))
    refiled <- as.integer(result$refiled_count %||% 0L)
    notice(list(tone = "positive", title = sprintf("%s: %d Datei(en) abgelegt", group$folder, as.integer(result$stored_count)),
      copy = paste0(if (refiled > 0L) sprintf("Davon %d zurückgezogene erneut. ", refiled) else "",
        if (as.integer(result$unchanged_count) > 0L) sprintf("%d lagen schon vor. ", as.integer(result$unchanged_count)) else "",
        "Jetzt „Im Import buchen“ – dort „… oder Dateien aus der Ablage nehmen“ aufklappen und das Institut wählen.")))
    # Neu pruefen: Was abgelegt ist, steht danach als "schon abgelegt" da.
    again <- attempt(service$intake_scan(include))
    if (is.list(again)) { wanted(data_statement_intake_pick_v1(again$institutions, group$folder)); scan(again) }
  })
  # Je Leser des Rezepts ein Knopf; die Knoepfe tragen die Nummer des Lesers im Rezept.
  for (reader_index in 1:6) local({
    index <- reader_index
    shiny::observeEvent(input[[paste0("statement_intake_book_", index)]], {
      group <- chosen(); recipe <- if (is.null(group) || is.null(group$recipe_key)) NULL else recipe_of(group$recipe_key)
      if (is.null(recipe) || index > length(recipe$readers)) return()
      reader <- recipe$readers[[index]]
      navigate(reader$import_kind, reader$adapter_id, recipe)
    }, ignoreInit = TRUE)
  })
  output$statement_intake_recipes <- shiny::renderTable({
    if (!isTRUE(input$statement_intake_recipes_details_open)) return(NULL)
    data_statement_intake_recipes_frame_v1(recipes())
  }, striped = TRUE, bordered = TRUE)
  output$statement_intake_notice <- shiny::renderUI({ value <- notice(); if (is.list(value)) portelyra_status_panel(value$title, value$copy, tone = value$tone) })
  invisible(list(setup = setup, scan = scan, notice = notice, chosen = chosen))
}

# Ordner waehlen ueber den Dialog des Desktops (zenity), wenn vorhanden; sonst NULL. Die App laeuft auf dem Rechner des Nutzers.
data_statement_intake_choose_folder_v1 <- function() {
  zenity <- Sys.which("zenity")
  if (!nzchar(zenity) || !nzchar(Sys.getenv("DISPLAY", Sys.getenv("WAYLAND_DISPLAY", "")))) return(NULL)
  picked <- suppressWarnings(system2(zenity, c("--file-selection", "--directory", "--title=Belegordner wählen"), stdout = TRUE, stderr = FALSE, timeout = 600))
  if (!identical(attr(picked, "status") %||% 0L, 0L) || length(picked) != 1L || !nzchar(picked)) return(NULL)
  picked
}
# "Im Import buchen" (#522): Was der Eingang ueber das Institut weiss, waehlt der Import vor - das Institut fuer "… oder Dateien aus der
# Ablage nehmen" und im Cash-Import das Konto, wenn es eindeutig ist. Zwei Cash-Konten eines Instituts unterscheidet der Leser: ein
# Tagesgeld- oder Sparkonto-Leser nimmt das Konto mit diesem Namen, die anderen die uebrigen (Revolut, Scalable, C24).
data_statement_intake_preselection_v1 <- function(recipe, adapter, accounts) {
  empty <- list(institution = NULL, cash_account = NULL)
  if (!is.list(recipe) || !is.list(accounts) || !length(accounts)) return(empty)
  words <- unique(tolower(c(unlist(recipe$folders, use.names = FALSE), as.character(recipe$label))))
  words <- words[nzchar(words)]
  escape <- function(text) gsub("([][{}()+*^$|\\\\?.])", "\\\\\\1", text)
  matches <- function(label) {
    label <- tolower(if (is.null(label) || length(label) != 1L || is.na(label)) "" else as.character(label))
    nzchar(label) && any(vapply(words, function(word) grepl(paste0("(^|[^a-z0-9])", escape(word), "([^a-z0-9]|$)"), label), logical(1L)))
  }
  own <- Filter(function(account) is.list(account) && !identical(account$status, "archived") && matches(account$institution_label), accounts)
  institutions <- unique(vapply(own, function(account) as.character(account$institution_label), character(1L)))
  cash <- Filter(function(account) isTRUE(account$account_type %in% c("cash", "bank")), own)
  if (length(cash) > 1L) {
    savings <- function(account) grepl("tagesgeld|zins|spar|savings", tolower(as.character(account$display_name)))
    reads_savings <- grepl("tagesgeld|savings", as.character(adapter))
    cash <- Filter(function(account) identical(savings(account), reads_savings), cash)
  }
  list(institution = if (length(institutions) == 1L) institutions[[1L]] else NULL, cash_account = if (length(cash) == 1L) cash[[1L]] else NULL)
}
