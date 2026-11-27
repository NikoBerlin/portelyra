# Backups in den Einstellungen der Data-App (#559, rc.407): anlegen, auflisten, ausduennen - ohne Kommandozeile. Mindeststandard der
# ersten oeffentlichen Beta (Festlegung 13.11.2026): Eine fremde Person muss ihre Daten ohne Kommandozeile sichern koennen.
#
# Festlegungen (13.11.2026): „Backup anlegen“ laeuft sofort mit Wartungssperre (Schreibwege und Zeitplaene pausieren
# kurz, danach Backup und Pruefung); Ausduennen mit einstellbarer Zahl (1-10, Vorgabe 3), nur mit Plan und Bestaetigung.
# Wiederherstellen kommt im Einrichtungsdialog (#559 Teil 2).

DATA_BACKUPS_KEEP_DEFAULT_V1 <- 3L
DATA_BACKUPS_PHASES_V1 <- c(pause = "wartet auf die Wartungssperre", backup = "sichert den Datenbestand", check = "prüft das Backup", done = "fertig")

data_backups_ui_v1 <- function() htmltools::tagAppendAttributes(id = "data-backups-card", portelyra_card("Backups", help = "backups",
  copy = "Sichert Ihren Datenbestand in den Backup-Ordner von Portelyra und prüft das Backup gleich danach. Portelyra läuft dabei weiter.",
  note = portelyra_note_v1(title = "Was ein Backup enthält und was nicht", id = "data-backups",
    "Enthalten: alle Portfolios, Buchungen, Kurse, Abschlüsse, Einstellungen und Steuerangaben dieses Datenraums.",
    "Nicht enthalten: Ihr eigener Belegordner mit den Original-PDFs, die Programmbibliothek und die Zeitpläne (diese fragt die Einrichtung nach einem Wiederherstellen neu).",
    "Mit Passwortschutz liegen die Backups im verschlüsselten Ordner. Sie lassen sich nur mit Passwort oder Wiederherstellungsschlüssel öffnen.",
    "Während des Backups pausieren „Alles aktualisieren“, Zeitpläne und Sammelläufe. Gerade laufende Schreibvorgänge warten oder melden sich mit Grund."),
  shiny::uiOutput("backups_state"),
  shiny::uiOutput("backups_body")))

# Die echten Wege; im Test ersetzbar. `busy()` nennt einen laufenden Lauf beim Namen oder NULL.
data_backups_deps_v1 <- function(project_root, home, busy = function() NULL) {
  root <- function() desktop_backups_root_v1(project_root, home)
  list(
    root = root,
    list = function(path) spotcore::desktop_release_backup_list_v1(project_root, path, home),
    spawn = function() desktop_backups_spawn_v1(project_root, home),
    job = function() desktop_backups_job_read_v1(home),
    busy = busy,
    # Der Plan prueft jedes Backup vollstaendig (bei verschluesselten Backups einige Minuten): deshalb im Hintergrund.
    # Immer mit dem eigenen Home (rc.410): Der Ordner gehoert allen Homes des Kontos; ausgeduennt wird nur der eigene Datenraum.
    prune_plan = function(path, keep) spotcore::desktop_release_backup_prune_v1(project_root, path, as.character(keep), home = home),
    prune_apply = function(path, keep, plan) spotcore::desktop_release_backup_prune_v1(project_root, path, as.character(keep), plan, "PRUNE_OWNER_BACKUPS", home = home),
    background = function(expression) parallel::mcparallel(expression),
    # Unlesbare Eintraege (#568): Befund nach dem Entsperren, Vorschau, bestaetigter Auftrag fuer den naechsten Start.
    unreadable_status = function() { value <- desktop_protection_cli_v1(project_root, home, "status"); if (identical(value$status, "completed")) value$result else NULL },
    unreadable_preview = function() desktop_protection_cli_v1(project_root, home, "unreadable-preview"),
    unreadable_request = function(fingerprint) desktop_protection_cli_v1(project_root, home, "unreadable-request",
                                                                         list(preview_fingerprint = fingerprint, confirmed = TRUE)),
    collect = function(job) { value <- parallel::mccollect(job, wait = FALSE); if (is.null(value)) NULL else value[[1L]] }
  )
}

.data_backups_size_v1 <- function(bytes) {
  value <- suppressWarnings(as.numeric(bytes))
  if (length(value) != 1L || is.na(value)) return("–")
  if (value >= 1024^3) sprintf("%s GB", format(round(value / 1024^3, 1), decimal.mark = ",", nsmall = 1L))
  else sprintf("%s MB", format(round(value / 1024^2, 1), decimal.mark = ",", nsmall = 1L))
}
.data_backups_code_v1 <- function(error) {
  code <- tryCatch(as.character(error$code), error = function(e) character())
  if (length(code) == 1L && nzchar(code)) code else "desktop_release_boundary_failed"
}

data_backups_frame_v1 <- function(bundles) {
  if (!length(bundles)) return(data.frame())
  data.frame(
    Backup = vapply(bundles, function(row) as.character(row$name), character(1L)),
    Angelegt = vapply(bundles, function(row) pl_moment_v1(row$created_at_utc), character(1L)),
    Programmstand = vapply(bundles, function(row) as.character(row$product_version), character(1L)),
    `Größe` = vapply(bundles, function(row) .data_backups_size_v1(row$byte_count), character(1L)),
    Dateien = vapply(bundles, function(row) format(as.integer(row$file_count), big.mark = ".", decimal.mark = ","), character(1L)),
    Datenraum = vapply(bundles, function(row) if (isTRUE(row$own_data_space)) "dieser" else if (isFALSE(row$own_data_space)) "ein anderer" else "–", character(1L)),
    Hinweis = vapply(bundles, function(row) if (isTRUE(row$newer_version)) "aus einem neueren Programmstand – wird nicht wiederhergestellt" else "", character(1L)),
    stringsAsFactors = FALSE, check.names = FALSE)
}

data_backups_server_v1 <- function(input, output, session, deps, poll_ms = 2000L) {
  where <- shiny::reactiveVal(NULL)       # Ergebnis von deps$root()
  listing <- shiny::reactiveVal(NULL)     # Ergebnis von deps$list() oder list(status = "blocked", code = ...)
  job <- shiny::reactiveVal(NULL)         # der Auftrag „Backup anlegen“ (backup-job.json)
  plan <- shiny::reactiveVal(NULL)        # Plan des Ausduennens oder sein Fehler
  pruning <- shiny::reactiveVal(NULL)     # laufender Hintergrundauftrag (Plan oder Ausfuehrung)
  feedback <- shiny::reactiveVal(NULL)
  watching <- shiny::reactiveVal(FALSE)   # Fenster „Backup läuft“ offen
  unreadable <- shiny::reactiveVal(NULL)           # Zustand des Passwortschutzes mit Befund nach dem Entsperren (#568)
  unreadable_preview <- shiny::reactiveVal(NULL)   # Vorschau „Prüfen“ oder ihr Fehler
  unreadable_checking <- shiny::reactiveVal(NULL)  # laufende Vorschau im Hintergrund
  refresh <- function() {
    value <- tryCatch(deps$root(), error = function(error) list(status = "blocked", code = "desktop_backups_root_unavailable"))
    where(value)
    listing(if (identical(value$status, "ready") && dir.exists(value$root))
      tryCatch(deps$list(value$root), error = function(error) list(status = "blocked", code = .data_backups_code_v1(error)))
      else if (identical(value$status, "ready")) list(status = "listed", bundles = list(), foreign_entry_count = 0L) else NULL)
    job(tryCatch(deps$job(), error = function(error) NULL))
    unreadable(if (is.function(deps$unreadable_status)) tryCatch(deps$unreadable_status(), error = function(error) NULL) else NULL)
  }
  shiny::observeEvent(input$settings_panel_open, if (isTRUE(input$settings_panel_open)) refresh(), ignoreNULL = FALSE)
  panel <- function(value) if (is.list(value)) portelyra_status_panel(value$title, value$copy, tone = value$tone) else NULL
  keep_value <- function() {
    typed <- suppressWarnings(as.integer(shiny::isolate(input$backups_keep)))
    if (length(typed) == 1L && !is.na(typed) && typed >= 1L && typed <= 10L) typed else DATA_BACKUPS_KEEP_DEFAULT_V1
  }
  phase_text <- function(value) {
    phase <- if (is.list(value) && is.character(value$phase)) value$phase else ""
    if (phase %in% names(DATA_BACKUPS_PHASES_V1)) DATA_BACKUPS_PHASES_V1[[phase]] else "läuft"
  }
  job_panel <- function(value) {
    if (!is.list(value)) return(NULL)
    when <- pl_moment_v1(if (is.character(value$finished_at_utc)) value$finished_at_utc else value$started_at_utc)
    if (identical(value$status, "running")) return(portelyra_status_panel("Backup läuft", paste0("Seit ", pl_moment_v1(value$started_at_utc), " · ", phase_text(value)), tone = "neutral"))
    if (identical(value$status, "created")) return(portelyra_status_panel("Letztes Backup angelegt und geprüft", paste0(
      as.character(value$name), " · ", when, " · ", format(as.integer(value$file_count), big.mark = ".", decimal.mark = ","), " Dateien · ", .data_backups_size_v1(value$byte_count),
      if (isTRUE(value$protected)) " · im verschlüsselten Ordner" else ""), tone = "positive"))
    portelyra_status_panel("Letztes Backup nicht angelegt", paste0(when, " · ", desktop_backups_reason_v1(value$code, value$relative_path)), tone = "warning")
  }
  # Unlesbarer Ordner (#568): Befund, „Prüfen“, Vormerken fuer den naechsten Start. Verschoben wird erst dann, gesperrt, und nur ein
  # abgeleiteter Lauf - Primaerdaten nie.
  unreadable_panel <- function() {
    value <- unreadable(); last <- job()
    if (!is.function(deps$unreadable_preview)) return(NULL)
    if (is.list(value) && isTRUE(value$unreadable_quarantine_requested))
      return(portelyra_status_panel("Quarantäne vorgemerkt", paste(
        "Beim nächsten Start verschiebt Portelyra den unlesbaren Ordner verschlüsselt in die Quarantäne, noch vor dem Entsperren.",
        "Gelöscht wird nichts. Bis dahin entsteht kein Backup."), tone = "neutral"))
    count <- if (is.list(value) && is.list(value$unreadable_check)) suppressWarnings(as.integer(value$unreadable_check$damaged_directory_count)) else 0L
    if (length(count) != 1L || is.na(count)) count <- 0L
    failed <- is.list(last) && identical(last$code, "desktop_release_source_unreadable")
    if (count < 1L && !failed) return(NULL)
    shiny::tagList(
      portelyra_status_panel("Unlesbarer Ordner im Datenraum", paste0(
        if (count == 1L) "Beim Entsperren gefunden: 1 Ordner lässt sich nicht lesen. "
        else if (count > 1L) sprintf("Beim Entsperren gefunden: %d Ordner lassen sich nicht lesen. ", count) else "",
        "Das kommt meist von einem harten Ausschalten des Rechners. Solange er da ist, entsteht kein Backup."), tone = "warning"),
      if (is.list(unreadable_checking())) portelyra_status_panel("Wird geprüft", "Portelyra liest den Datenraum einmal ganz durch.", tone = "neutral")
      else shiny::actionButton("backups_unreadable_check", "Prüfen", class = "btn-default"),
      shiny::uiOutput("backups_unreadable_view"))
  }
  output$backups_state <- shiny::renderUI({
    value <- where(); if (is.null(value)) return(shiny::p(class = "pl-field-hint", "Wird beim Öffnen der Einstellungen gelesen."))
    if (!identical(value$status, "ready")) return(portelyra_status_panel("Backup-Ordner nicht erreichbar", desktop_backups_reason_v1(value$code), tone = "warning"))
    shiny::tagList(
      shiny::p(class = "pl-field-hint", if (isTRUE(value$protected)) "Ziel: der verschlüsselte Backup-Ordner von Portelyra (Passwortschutz)."
               else paste0("Ziel: der Backup-Ordner von Portelyra (", sub(paste0("^", path.expand("~")), "~", value$root), "), unverschlüsselt.")),
      unreadable_panel(), job_panel(job()), panel(feedback()))
  })
  shiny::observeEvent(input$backups_unreadable_check, {
    unreadable_preview(NULL)
    unreadable_checking(list(job = deps$background(tryCatch(deps$unreadable_preview(),
      error = function(error) list(status = "blocked", code = "desktop_protection_state_invalid")))))
  })
  shiny::observe({
    current <- unreadable_checking(); if (!is.list(current)) return()
    shiny::invalidateLater(poll_ms, session)
    value <- tryCatch(deps$collect(current$job), error = function(error) list(status = "blocked", code = "desktop_protection_state_invalid"))
    if (is.null(value)) return()
    unreadable_checking(NULL); unreadable_preview(value)
  })
  output$backups_unreadable_view <- shiny::renderUI({
    value <- unreadable_preview(); if (!is.list(value)) return(NULL)
    if (!identical(value$status, "completed")) return(portelyra_status_panel("Nicht geprüft", desktop_protection_message_v1(value$code), tone = "warning"))
    result <- value$result; entries <- result$entries
    if (!length(entries)) return(portelyra_status_panel("Alles lesbar", "Kein unlesbarer Ordner gefunden. Ein Backup sollte jetzt gelingen.", tone = "positive"))
    rows <- lapply(entries, function(row) shiny::tags$li(shiny::code(as.character(row$relative_path)), " – ",
      if (isTRUE(row$quarantinable) && identical(row$kind, "leftover_staging") && identical(row$area, "asset-activity-ledger-v1")) paste(
        "unfertiger Zwischenstand einer Buchung, der nie gültig war. Der gültige Buchungsstand ist unverändert. Die Buchung, die beim",
        "Ausschalten lief, ist nicht gespeichert: bitte in der Liste der Buchungen prüfen und gegebenenfalls wiederholen.")
      else if (isTRUE(row$quarantinable) && identical(row$kind, "leftover_staging")) paste(
        "unfertige Kopie einer Steuermodul-Installation. Die installierten Fassungen sind unverändert; die Installation gegebenenfalls wiederholen.")
      else if (isTRUE(row$quarantinable)) paste0("abgeleiteter Lauf des Bereichs „", row$area, "“; „Alles aktualisieren“ schreibt ihn neu.",
        if (isTRUE(row$latest)) " Auf ihn zeigt der aktuelle Stand: Der Bereich bleibt leer, bis er neu veröffentlicht ist." else "")
      else if (row$kind %in% c("derived_run", "leftover_staging")) "nicht eindeutig zuzuordnen. Nicht verschieben, bitte melden."
      else "weder abgeleiteter Lauf noch Zwischenstand. Portelyra verschiebt ihn nicht; nichts selbst löschen (Handbuch „Backups“, „Unlesbarer Eintrag“)."))
    shiny::tagList(shiny::tags$ul(rows),
      if (isTRUE(result$quarantinable)) shiny::tagList(
        shiny::checkboxInput("backups_unreadable_understood", paste(
          "Verstanden: Beim nächsten Start verschiebt Portelyra diese Ordner verschlüsselt in eine Quarantäne im Portelyra-Ordner Ihres",
          "Benutzerkontos. Gelöscht wird nichts."), FALSE),
        shiny::actionButton("backups_unreadable_request", "Für den nächsten Start vormerken", class = "btn-primary"))
      else portelyra_status_panel("Nicht von Portelyra lösbar", "Mindestens ein Eintrag ist weder abgeleiteter Lauf noch Zwischenstand. Das letzte geprüfte Backup bleibt gültig.", tone = "warning"))
  })
  shiny::observeEvent(input$backups_unreadable_request, {
    value <- unreadable_preview(); if (!is.list(value) || !identical(value$status, "completed")) return()
    if (!isTRUE(input$backups_unreadable_understood)) {
      feedback(list(title = "Bitte bestätigen", copy = "Erst die Kenntnisnahme ankreuzen, dann vormerken.", tone = "warning")); return()
    }
    done <- tryCatch(deps$unreadable_request(value$result$preview_fingerprint),
                     error = function(error) list(status = "blocked", code = "desktop_protection_state_invalid"))
    unreadable_preview(NULL)
    feedback(if (identical(done$status, "completed")) list(title = "Vorgemerkt", copy = paste(
               "Beim nächsten Start von Portelyra geht der unlesbare Ordner verschlüsselt in die Quarantäne. Danach gelingen Backups wieder."), tone = "positive")
             else list(title = "Nicht vorgemerkt", copy = desktop_protection_message_v1(done$code), tone = "warning"))
    shiny::isolate(refresh())
  })
  output$backups_body <- shiny::renderUI({
    value <- where(); if (!is.list(value) || !identical(value$status, "ready")) return(NULL)
    busy <- tryCatch(deps$busy(), error = function(error) NULL)
    running <- is.list(job()) && identical(job()$status, "running")
    shown <- listing(); bundles <- if (is.list(shown) && identical(shown$status, "listed")) shown$bundles else list()
    shiny::tagList(
      shiny::div(class = "pl-field-group",
        shiny::h4(class = "pl-section-title", "Backup anlegen"),
        if (!is.null(busy)) portelyra_status_panel("Gerade nicht möglich", busy, tone = "neutral")
        else if (running) NULL
        else shiny::tagList(
          shiny::checkboxInput("backups_create_understood", "Verstanden: Während des Backups pausieren „Alles aktualisieren“, Zeitpläne und Sammelläufe kurz.", FALSE),
          shiny::actionButton("backups_create", "Backup anlegen", class = "btn-primary"))),
      shiny::div(class = "pl-field-group",
        shiny::h4(class = "pl-section-title", sprintf("Vorhandene Backups (%d)", length(bundles))),
        if (is.list(shown) && !identical(shown$status, "listed")) portelyra_status_panel("Liste nicht lesbar", desktop_backups_reason_v1(shown$code), tone = "warning")
        else if (!length(bundles)) shiny::p(class = "pl-field-hint", "Noch keine Backups in diesem Ordner.")
        else shiny::tagList(
          shiny::tableOutput("backups_table"),
          shiny::p(class = "pl-field-hint", "Die Liste liest nur die Kopfdaten. Vollständig geprüft wird jedes Backup nach dem Anlegen und vor dem Wiederherstellen."))),
      if (length(bundles) > 1L) shiny::div(class = "pl-field-group",
        shiny::h4(class = "pl-section-title", "Ausdünnen"),
        # Der eingetippte Wert bleibt ueber jedes Neuzeichnen der Karte (rc.410): Sonst stand nach „Plan anzeigen“ wieder 3 im Feld, und ein
        # zweiter Klick haette mit 3 statt mit der gewaehlten Zahl geplant.
        shiny::numericInput("backups_keep", "Wie viele der jüngsten gültigen Backups behalten?", value = keep_value(), min = 1L, max = 10L, step = 1L),
        if (is.list(pruning())) portelyra_status_panel("Wird geprüft", "Jedes Backup wird vollständig geprüft; bei verschlüsselten Backups dauert das einige Minuten.", tone = "neutral")
        else shiny::actionButton("backups_prune_plan", "Plan anzeigen", class = "btn-default"),
        shiny::uiOutput("backups_prune_view")))
  })
  output$backups_table <- shiny::renderTable({ shown <- listing(); if (is.list(shown) && identical(shown$status, "listed")) data_backups_frame_v1(shown$bundles) else data.frame() },
                                            striped = TRUE, bordered = TRUE)
  # Anlegen: eigener Prozess, Fenster bis zum Ende; „Backup anlegen“ wirkt erst mit der Kenntnisnahme.
  shiny::observeEvent(input$backups_create, {
    if (!isTRUE(input$backups_create_understood)) {
      feedback(list(title = "Bitte bestätigen", copy = "Erst die Kenntnisnahme ankreuzen, dann „Backup anlegen“.", tone = "warning")); return()
    }
    busy <- tryCatch(deps$busy(), error = function(error) NULL)
    if (!is.null(busy)) { feedback(list(title = "Gerade nicht möglich", copy = busy, tone = "neutral")); return() }
    feedback(NULL)
    started <- tryCatch(deps$spawn(), error = function(error) list(status = "failed", code = .data_backups_code_v1(error)))
    if (!identical(started$status, "started")) {
      feedback(list(title = "Backup nicht gestartet", copy = desktop_backups_reason_v1(started$code), tone = "warning")); return()
    }
    job(started$job); watching(TRUE)
    shiny::showModal(shiny::modalDialog(title = "Backup läuft", shiny::uiOutput("backups_progress"), footer = NULL, easyClose = FALSE))
  })
  output$backups_progress <- shiny::renderUI({
    value <- job()
    shiny::tagList(
      shiny::p(paste0("Portelyra sichert den Datenbestand und prüft das Backup. Schritt: ", phase_text(value), ".")),
      shiny::p(class = "pl-field-hint", "Bitte warten; das Fenster schließt sich von selbst. Andere Apps lesen weiter."))
  })
  shiny::observe({
    if (!isTRUE(watching())) return()
    shiny::invalidateLater(poll_ms, session)
    value <- tryCatch(deps$job(), error = function(error) NULL)
    if (is.list(value)) job(value)
    if (!is.list(value) || !identical(value$status, "running")) {
      watching(FALSE); shiny::removeModal()
      shiny::isolate(refresh())
    }
  })
  # Ausduennen: Plan und Ausfuehrung im Hintergrund, Ausfuehrung nur mit genau diesem Plan.
  shiny::observeEvent(input$backups_prune_plan, {
    keep <- suppressWarnings(as.integer(input$backups_keep))
    if (length(keep) != 1L || is.na(keep) || keep < 1L || keep > 10L) {
      plan(list(status = "blocked", code = "desktop_release_input_invalid")); return()
    }
    root <- where()$root
    pruning(list(kind = "plan", keep = keep, job = deps$background(tryCatch(deps$prune_plan(root, keep), error = function(error) list(status = "blocked", code = .data_backups_code_v1(error))))))
  })
  shiny::observeEvent(input$backups_prune_confirm, {
    current <- plan(); if (!is.list(current) || !identical(current$status, "planned")) return()
    root <- where()$root
    pruning(list(kind = "apply", keep = current$keep_count, job = deps$background(tryCatch(deps$prune_apply(root, current$keep_count, current$plan_fingerprint),
      error = function(error) list(status = "blocked", code = .data_backups_code_v1(error))))))
  })
  shiny::observe({
    current <- pruning(); if (!is.list(current)) return()
    shiny::invalidateLater(poll_ms, session)
    value <- tryCatch(deps$collect(current$job), error = function(error) list(status = "blocked", code = "desktop_release_boundary_failed"))
    if (is.null(value)) return()
    pruning(NULL)
    if (identical(current$kind, "plan")) { plan(value); return() }
    plan(NULL)
    feedback(if (identical(value$status, "pruned")) list(title = "Ausgedünnt", copy = sprintf("Die %d jüngsten gültigen Backups bleiben.", as.integer(current$keep)), tone = "positive")
             else list(title = "Nicht ausgedünnt", copy = desktop_backups_reason_v1(value$code), tone = "warning"))
    shiny::isolate(refresh())
  })
  output$backups_prune_view <- shiny::renderUI({
    current <- plan(); if (!is.list(current)) return(NULL)
    if (!identical(current$status, "planned")) return(portelyra_status_panel("Kein Plan", desktop_backups_reason_v1(current$code), tone = "warning"))
    removed <- current$removed
    if (!isTRUE(current$enough_valid)) return(portelyra_status_panel("Nichts zu entfernen", sprintf(
      "Es gibt weniger als %d gültige Backups dieses Datenraums. Portelyra entfernt dann keines.", as.integer(current$keep_count)), tone = "neutral"))
    if (!length(removed)) return(portelyra_status_panel("Nichts zu entfernen", sprintf("Es gibt nicht mehr als %d gültige Backups.", as.integer(current$keep_count)), tone = "neutral"))
    shiny::tagList(
      portelyra_status_panel(sprintf("%d Backup(s) würden entfernt", length(removed)), paste0(
        paste(vapply(removed, function(row) paste0(pl_moment_v1(row$created_at_utc), " (", row$product_version, ", ", .data_backups_size_v1(row$byte_count), ")"), character(1L)), collapse = "; "),
        ". Es bleiben die ", as.integer(current$keep_count), " jüngsten gültigen Backups",
        if (as.integer(current$invalid_kept_count) > 0L) sprintf("; %d ungültige bleiben liegen und zählen nicht", as.integer(current$invalid_kept_count)) else "",
        ". Backups anderer Datenräume und aus neueren Programmständen fasst Portelyra nicht an."), tone = "warning"),
      shiny::actionButton("backups_prune_confirm", "Diesen Plan ausführen", class = "btn-primary"))
  })
  invisible(list(refresh = refresh))
}
