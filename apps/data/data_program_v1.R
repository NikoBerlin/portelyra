# Reiter „Programm“ der Einstellungen (#562, #586; 0.3.3, Festlegung 25.11.2026): Version, „Neu in dieser Version“ und der Browser, in
# dem Portelyra sich oeffnet. Dazu einmal nach einem Update die Karte „Neu in Version …“ oben in Data. Gespeichert wird in den
# Einstellungen der Installation (apps/shared/desktop_installation_v1.R), nicht im Datenbestand. Ohne Programmordner (Entwicklungsstart,
# Tests ohne Home) zeigt der Reiter die Version und sagt, warum die Wahl fehlt.

# Juengstes abgeschlossenes Upgrade aus den Quittungen des Programmordners (<home>/upgrade-receipts, je Upgrade eine Datei). Gelesen werden
# nur die juengsten Dateien; massgeblich ist der Zeitpunkt in der Quittung. NULL ohne Quittung.
data_program_last_upgrade_v1 <- function(home, newest = 12L) {
  files <- list.files(file.path(home, "upgrade-receipts"), pattern = "^upgrade-[0-9a-f]+[.]json$", full.names = TRUE)
  if (!length(files)) return(NULL)
  files <- files[order(file.info(files)$mtime, decreasing = TRUE)][seq_len(min(as.integer(newest), length(files)))]
  receipts <- Filter(function(receipt) is.list(receipt) && identical(receipt$operation, "upgrade") && identical(receipt$status, "completed") &&
                       is.character(receipt$completed_at_utc) && length(receipt$completed_at_utc) == 1L &&
                       is.character(receipt$new_product_version) && length(receipt$new_product_version) == 1L,
                     lapply(files, function(path) tryCatch(jsonlite::fromJSON(path, simplifyVector = FALSE), error = function(error) NULL)))
  if (!length(receipts)) return(NULL)
  receipts[[order(vapply(receipts, function(receipt) receipt$completed_at_utc, character(1L)), decreasing = TRUE)[[1L]]]]
}

# Einmal je Version: TRUE, wenn die laufende Version per Update kam (juengste Quittung nennt sie) und „Neu in dieser Version“ dafuer noch
# nicht gezeigt wurde. Vermerkt wird beim ersten Blick, auch wenn nichts zu zeigen ist (frische Installation) - spaetere Sitzungen suchen
# dann nicht mehr. Eine unlesbare Einstellungsdatei bleibt unberuehrt; dann erscheint die Karte nicht.
data_program_whats_new_due_v1 <- function(home, version, last = data_program_last_upgrade_v1(home)) {
  if (!is.character(version) || length(version) != 1L || is.na(version)) return(FALSE)
  current <- desktop_installation_settings_read_v1(home)
  if (!current$status %in% c("absent", "available")) return(FALSE)
  if (identical(current$settings$whats_new_seen_version, version)) return(FALSE)
  due <- is.list(last) && identical(last$new_product_version, version)
  invisible(tryCatch(desktop_installation_settings_write_v1(home, list(whats_new_seen_version = version)), error = function(error) NULL))
  due
}

# Oeffnet die Einstellungen beim Reiter „Programm“ (Block links in Data; aus den anderen Apps ueber #pl-open=program).
data_program_open_js_v1 <- function() data_settings_open_target_js_v1("data-program-version")
data_program_notes_link_v1 <- function() shiny::tags$a(href = "#", id = "program_notes_open", class = "pl-activity-link",
                                                         onclick = paste0(data_program_open_js_v1(), "return false;"), "Neu in dieser Version")
data_program_notice_link_v1 <- function() shiny::tags$a(href = "#", class = "pl-activity-link",
                                                          onclick = paste0(data_settings_open_target_js_v1("data-program-updates"), "return false;"), "Ansehen")

data_program_ui_v1 <- function() shiny::tagList(
  htmltools::tagAppendAttributes(id = "data-program-version", portelyra_card("Version", help = "app-data#programm",
    copy = "Welche Version von Portelyra auf diesem Rechner läuft und was sie mitbringt.",
    shiny::uiOutput("program_version"))),
  # Update-Suche (#562 Paket 3): ein Klick fragt genau einmal bei GitHub ab; automatisch nur mit Zustimmung, hoechstens einmal am Tag.
  htmltools::tagAppendAttributes(id = "data-program-updates", portelyra_card("Updates", help = "update#aus-der-app",
    copy = "Ob es eine neuere Version von Portelyra gibt. Gesucht wird bei GitHub; eingespielt wird nichts ohne Ihre Bestätigung.",
    shiny::uiOutput("program_update_state"),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("program_update_check", "Nach Updates suchen", class = "btn-primary")),
    shiny::uiOutput("program_update_result"),
    # Herunterladen, pruefen, bestaetigen, einspielen (#562 Paket 4).
    shiny::uiOutput("program_update_apply"),
    shiny::tags$details(class = "pl-program-update-consent", open = NA, shiny::tags$summary("Automatisch suchen"),
      shiny::uiOutput("program_update_consent"),
      shiny::div(class = "pl-editor-actions", shiny::actionButton("program_update_consent_save", "Auswahl speichern", class = "btn-default")),
      shiny::uiOutput("program_update_consent_feedback")))),
  htmltools::tagAppendAttributes(id = "data-program-browser", portelyra_card("Browser", help = "app-data#programm",
    copy = "In welchem Browser sich Portelyra öffnet. Die Wahl gilt für diese Installation und alle Portfolios.",
    shiny::uiOutput("program_browser"),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("program_browser_save", "Browser speichern", class = "btn-primary")),
    shiny::uiOutput("program_browser_feedback"))),
  # Lizenzhinweis (#590): Copyright, Weitergabe, keine Gewaehrleistung, Lizenztext - fest im Reiter, ohne Daten des Portfolios.
  htmltools::tagAppendAttributes(id = "data-program-license", portelyra_card("Lizenz", help = "lizenz",
    copy = "Unter welchen Bedingungen Sie Portelyra nutzen, weitergeben und verändern dürfen.",
    desktop_license_notice_ui_v1(),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("program_license_show", "Lizenztext anzeigen", class = "btn-default")))))

# Der Lizenztext im Dialog, offline aus dem Programmordner; fehlt er (Programm vor 0.3.4), nennt der Dialog die Adresse bei gnu.org.
data_program_license_modal_v1 <- function(text) shiny::modalDialog(
  title = "Lizenztext: GNU Affero General Public License, Version 3", size = "l", easyClose = TRUE,
  footer = shiny::modalButton("Schließen"),
  if (is.null(text)) portelyra_status_panel("Lizenztext nicht im Programmordner",
    paste("Diese Installation bringt die Datei LICENSE noch nicht mit. Der Text steht unter", DESKTOP_LICENSE_URL_V1), "warning")
  else shiny::tags$pre(class = "pl-license-text", style = "max-height: 65vh; overflow: auto; white-space: pre-wrap;", text))

# Platz oben in Data fuer „Neu in Version …“; leer nimmt er keinen Raum ein.
data_program_whats_new_slot_v1 <- function() shiny::uiOutput("program_whats_new", class = "pl-scope-slot")
# Einmal fuer Installationen ohne Antwort (#562): die Frage nach der Update-Suche, ohne Vorauswahl.
data_program_consent_slot_v1 <- function() shiny::uiOutput("program_consent_card", class = "pl-scope-slot")

# Die Versionshinweise eines gefundenen Updates: aus dem Netz, deshalb nur als reiner Text (Festlegung 25.11.2026).
data_program_release_notes_ui_v1 <- function(notes) {
  notes <- Filter(function(note) is.list(note) && is.character(note$version), if (is.list(notes)) notes else list())
  if (!length(notes)) return(NULL)
  shiny::tagList(lapply(rev(notes), function(note) shiny::tagList(
    shiny::tags$h4(paste("Version", note$version), if (is.character(note$published_at)) shiny::span(class = "pl-field-hint", paste0(" · veröffentlicht am ", pl_day_v1(note$published_at)))),
    if (is.character(note$text) && nzchar(note$text)) shiny::div(class = "pl-program-release-notes", note$text)
    else shiny::p(class = "pl-field-hint", "Ohne Versionshinweise."))))
}

# Nicht angeboten (Festlegung 25.11.2026): Ein falsch benanntes Archiv, ein Tag ohne Versionsnummer oder ein umgezogenes Repo liessen die
# Suche sonst still „aktuell“ melden. Genannt werden neuere Versionen ohne passendes Archiv und Eintraege, deren Tag keine Versionsnummer
# ist; den Rat zum Terminal gibt es nur, wenn nichts angeboten wird.
data_program_skipped_ui_v1 <- function(status, version, offered = FALSE) {
  skipped <- Filter(is.list, if (is.list(status) && is.list(status$skipped)) status$skipped else list())
  newer <- desktop_update_skipped_newer_v1(status, version)
  unreadable <- unique(unlist(lapply(skipped, function(item) {
    if (identical(item$reason, "tag_invalid") && is.character(item$tag) && length(item$tag) == 1L && !is.na(item$tag)) item$tag
  }), use.names = FALSE))
  if (!length(newer) && !length(unreadable)) return(NULL)
  lines <- c(vapply(newer, function(item) paste0("Version ", item, " steht bei GitHub, aber ohne das Archiv portelyra-", item,
                                                  ".tar.gz dieses Projekts; deshalb bietet Portelyra sie nicht an."), character(1L), USE.NAMES = FALSE),
             vapply(unreadable, function(item) paste0("Ein Eintrag bei GitHub mit der Bezeichnung „", item,
                                                      "“ trägt keine gültige Versionsnummer und wurde übergangen."), character(1L), USE.NAMES = FALSE),
             if (!isTRUE(offered)) "Bitte später noch einmal suchen; bleibt der Hinweis, hilft das Handbuch „Update einspielen“ beim Aktualisieren im Terminal.")
  htmltools::tagAppendAttributes(portelyra_status_panel("Nicht angeboten", paste(lines, collapse = " "), tone = "warning"), class = "pl-program-skipped")
}

# Ergebnis einer Suche (gespeichert oder eben geklickt) als Karte.
data_program_update_result_ui_v1 <- function(status, version) {
  if (!is.list(status) || !is.character(status$result) || length(status$result) != 1L) return(NULL)
  if (identical(status$result, "available") && desktop_program_version_newer_v1(status$version, version)) {
    archive <- status$archive
    return(shiny::tagList(
      portelyra_status_panel(paste0("Version ", status$version, " verfügbar"),
        paste0("Diese Installation hat Version ", version, ".",
               if (is.list(archive) && is.numeric(archive$size)) paste0(" Archiv ", format(round(archive$size / 1048576, 1), decimal.mark = ","), " MB.") else "",
               " Darunter laden Sie es herunter und spielen es nach einer Prüfung ein."), tone = "positive"),
      data_program_release_notes_ui_v1(status$notes), data_program_skipped_ui_v1(status, version, offered = TRUE)))
  }
  if (status$result %in% c("available", "current")) {
    skipped <- data_program_skipped_ui_v1(status, version)
    if (!is.null(skipped))
      return(shiny::tagList(portelyra_status_panel("Keine einspielbare neuere Version", paste0("Diese Installation hat Version ", version, "."),
                                                   tone = "warning"), skipped))
    return(portelyra_status_panel("Portelyra ist aktuell", paste0("Version ", version, " ist die neueste."), tone = "positive"))
  }
  portelyra_status_panel("Suche gescheitert", desktop_update_failure_text_v1(status$failure), tone = "warning")
}

# Im Demo-Home (#487) keine Update-Suche: das Startskript setzt die Option portelyra.desktop.demo.
DATA_PROGRAM_DEMO_TEXT_V1 <- "Im Demo-Portfolio sucht Portelyra nicht nach Updates; das übernimmt Ihre eigene Installation."
data_program_server_v1 <- function(input, output, session, project_root, home, detect = function() desktop_browsers_detect_v1(),
                                   now = Sys.time, update_runner = NULL, poll_ms = 30000L, demo = isTRUE(getOption("portelyra.desktop.demo")),
                                   check_runner = NULL, spawn_runner = NULL,
                                   unit_of = function(home) tryCatch(getFromNamespace(".desktop_product_app_unit_v1", "spotcore")(home, kind = "update"),
                                                                     error = function(error) NULL),
                                   port_of = function() { ports <- getOption("portelyra.desktop.ports")
                                     if (!is.null(ports) && "data" %in% names(ports)) as.integer(ports[["data"]]) else NA_integer_ }) {
  version <- desktop_program_version_v1(project_root)
  changelog <- desktop_program_changelog_v1(project_root, version)
  home_ok <- is.character(home) && length(home) == 1L && !is.na(home) && nzchar(home) && dir.exists(home)
  revision <- shiny::reactiveVal(0L)
  settings <- shiny::reactive({
    revision()
    if (home_ok) desktop_installation_settings_read_v1(home) else list(status = "unavailable", settings = list(browser = "default"), raw = list())
  })
  browsers <- shiny::reactive({ revision(); tryCatch(detect(), error = function(error) list()) })

  output$program_version <- shiny::renderUI({
    last <- if (home_ok) tryCatch(data_program_last_upgrade_v1(home), error = function(error) NULL) else NULL
    updated <- is.list(last) && identical(last$new_product_version, version)
    shiny::tagList(
      shiny::p(shiny::strong(if (is.na(version)) "Version nicht verfügbar" else paste("Portelyra", version)),
               if (updated) paste0(" · eingespielt am ", pl_moment_v1(last$completed_at_utc),
                                   if (is.character(last$old_product_version)) paste0(", vorher ", last$old_product_version) else "")),
      shiny::tags$details(class = "pl-program-whats-new", open = NA, shiny::tags$summary("Neu in dieser Version"),
                          desktop_program_notes_ui_v1(changelog)))
  })

  output$program_browser <- shiny::renderUI({
    current <- settings()
    chosen <- current$settings$browser
    found <- browsers()
    choices <- c("Standardbrowser des Systems (Vorgabe)" = "default")
    for (id in names(found)) choices[[desktop_browser_label_v1(found[[id]])]] <- id
    missing <- !identical(chosen, "default") && is.null(found[[chosen]])
    if (missing) choices[[paste0(DESKTOP_BROWSERS_V1[[chosen]]$label, " – nicht gefunden")]] <- chosen
    shiny::tagList(
      if (!home_ok) portelyra_status_panel("Wahl nicht verfügbar", "Dieses Portelyra läuft ohne Programmordner (etwa beim Entwickeln); der Browser lässt sich hier nicht festlegen.", "warning"),
      if (identical(current$status, "unreadable")) portelyra_status_panel("Einstellungen der Installation nicht lesbar", "Bis zum nächsten Speichern gilt die Vorgabe; Speichern legt sie neu an.", "warning"),
      if (identical(current$status, "newer")) portelyra_status_panel("Einstellungen einer neueren Version", "Diese Version ändert sie nicht, damit die neuere Version ihre Werte behält. Es gilt die Vorgabe.", "warning"),
      if (identical(current$status, "rejected")) portelyra_status_panel("Einstellungen der Installation abgewiesen", "Die Datei ist ein Verweis auf eine andere Datei; Portelyra liest und schreibt sie deshalb nicht. Es gilt die Vorgabe.", "warning"),
      if (missing) portelyra_status_panel(paste(DESKTOP_BROWSERS_V1[[chosen]]$label, "nicht gefunden"),
                                          "Er ist auf diesem Rechner nicht mehr installiert. Portelyra öffnet deshalb im Standardbrowser des Systems, bis Sie einen anderen wählen.", "warning"),
      shiny::radioButtons("program_browser_choice", "Portelyra öffnen in", choices = choices, selected = chosen),
      shiny::p(class = "pl-field-hint", "Angeboten werden nur Browser, die auf diesem Rechner installiert sind, auch als Snap oder Flatpak. Geprüft wird Portelyra mit Firefox; andere aktuelle Browser sollten funktionieren."),
      shiny::p(class = "pl-field-hint", "Die Wahl gilt ab dem nächsten Öffnen, auch beim zweiten Klick auf den Starter. Wer Portelyra im Terminal mit --browser startet, bestimmt damit den Browser für diesen Start."))
  })

  shiny::observeEvent(input$program_license_show, shiny::showModal(data_program_license_modal_v1(desktop_license_text_v1(project_root))),
                      ignoreInit = TRUE)

  feedback <- shiny::reactiveVal(NULL)
  output$program_browser_feedback <- shiny::renderUI(data_action_feedback_panel_v1(feedback()))
  refused <- function(copy) feedback(list(title = "Nicht gespeichert", copy = copy, tone = "error"))
  shiny::observeEvent(input$program_browser_save, {
    choice <- input$program_browser_choice
    if (!home_ok) return(refused("Dieses Portelyra läuft ohne Programmordner."))
    if (!is.character(choice) || length(choice) != 1L || !choice %in% DESKTOP_BROWSER_NAMES_V1) return(refused("Bitte einen Browser wählen."))
    if (!identical(choice, "default") && is.null(browsers()[[choice]])) {
      return(refused(paste0(DESKTOP_BROWSERS_V1[[choice]]$label, " ist auf diesem Rechner nicht installiert.")))
    }
    result <- tryCatch(desktop_installation_settings_write_v1(home, list(browser = choice), now = now()), error = function(error) error)
    if (inherits(result, "error")) {
      code <- tryCatch(as.character(result$code), error = function(error) "")
      return(refused(switch(code,
        desktop_installation_settings_newer = "Die Einstellungen stammen von einer neueren Version von Portelyra.",
        desktop_installation_settings_rejected = "Die Einstellungsdatei ist ein Verweis auf eine andere Datei.",
        "Die Einstellungen der Installation ließen sich nicht schreiben.")))
    }
    label <- if (identical(choice, "default")) "Standardbrowser des Systems" else desktop_browser_label_v1(browsers()[[choice]])
    feedback(list(title = "Gespeichert", copy = paste0(label, ". Gilt ab dem nächsten Öffnen von Portelyra."), tone = "positive"))
    revision(revision() + 1L)
  }, ignoreInit = TRUE)

  # Einmal nach einem Update: „Neu in Version …“ oben in Data, bis „Ausblenden“ oder zum Ende der Sitzung.
  whats_new <- shiny::reactiveVal(home_ok && isTRUE(tryCatch(data_program_whats_new_due_v1(home, version), error = function(error) FALSE)))
  output$program_whats_new <- shiny::renderUI({
    if (!isTRUE(whats_new())) return(NULL)
    htmltools::tagAppendAttributes(id = "data-program-whats-new", portelyra_card(paste("Neu in Version", version),
      copy = "Portelyra wurde aktualisiert. Diese Liste steht auch in den Einstellungen unter „Programm“.",
      desktop_program_notes_ui_v1(changelog),
      shiny::div(class = "pl-editor-actions", shiny::actionButton("program_whats_new_hide", "Ausblenden", class = "btn-default"))))
  })
  shiny::observeEvent(input$program_whats_new_hide, whats_new(FALSE), ignoreInit = TRUE)
  # Die Plaetze oben sind leer ausgeblendet (.pl-scope-slot:empty); ohne diese Angabe hielte Shiny sie fuer verborgen und berechnete sie
  # nie - sie blieben leer und damit verborgen (Generalprobe 25.11.2026: die Frage nach der Update-Suche erschien nicht).
  shiny::outputOptions(output, "program_whats_new", suspendWhenHidden = FALSE)

  # --- Update-Suche (#562 Paket 3). Ohne Klick und ohne Zustimmung geht von hier nichts ins Netz: abgefragt wird nur im Klick unten;
  # die taegliche Suche startet das Startskript. Angezeigt wird der gespeicherte Stand (update-status.json) oder das Ergebnis des Klicks.
  update_saved <- if (home_ok) shiny::reactivePoll(poll_ms, session,
    checkFunc = function() { info <- file.info(file.path(home, "update-status.json")); paste(info$mtime, info$size) },
    valueFunc = function() desktop_update_status_read_v1(home)) else shiny::reactive(NULL)
  update_clicked <- shiny::reactiveVal(NULL)
  update_status <- shiny::reactive({
    clicked <- update_clicked()
    if (is.list(clicked) && is.list(clicked$status)) clicked$status else update_saved()
  })
  shiny::observeEvent(input$program_update_check, {
    if (isTRUE(demo)) return(update_clicked(list(blocked = DATA_PROGRAM_DEMO_TEXT_V1)))
    if (!home_ok) return(update_clicked(list(blocked = "Dieses Portelyra läuft ohne Programmordner; gesucht wird nur in einer Installation.")))
    if (is.na(version)) return(update_clicked(list(blocked = desktop_update_failure_text_v1("update_version_unknown"))))
    reply <- tryCatch(desktop_update_cli_v1(project_root, "check", list(home = home, running = version, trigger = "click"), update_runner),
                      error = function(error) list(status = "blocked", code = "desktop_update_state_invalid"))
    if (identical(reply$status, "completed") && is.list(reply$result)) update_clicked(list(status = reply$result))
    else update_clicked(list(blocked = desktop_update_failure_text_v1(if (is.character(reply$code)) reply$code else "")))
  }, ignoreInit = TRUE)
  output$program_update_state <- shiny::renderUI({
    if (isTRUE(demo)) return(shiny::p(class = "pl-field-hint", DATA_PROGRAM_DEMO_TEXT_V1))
    status <- update_status()
    if (!is.list(status) || !is.character(status$checked_at_utc)) return(shiny::p(class = "pl-field-hint", "Noch nicht gesucht."))
    shiny::p(class = "pl-field-hint", paste0("Zuletzt gesucht: ", pl_moment_v1(status$checked_at_utc), " Uhr (",
                                             if (identical(status$trigger, "daily")) "automatisch" else "auf Klick", ")."))
  })
  output$program_update_result <- shiny::renderUI({
    clicked <- update_clicked()
    if (is.list(clicked) && is.character(clicked$blocked)) return(portelyra_status_panel("Suche nicht gestartet", clicked$blocked, tone = "warning"))
    data_program_update_result_ui_v1(update_status(), version)
  })
  output$program_update_consent <- shiny::renderUI({
    if (isTRUE(demo)) return(shiny::p(class = "pl-field-hint", DATA_PROGRAM_DEMO_TEXT_V1))
    consent <- settings()$settings$update_consent
    shiny::tagList(
      shiny::radioButtons("program_update_consent_choice", "Nach neuen Versionen suchen",
        choices = c("Einmal am Tag automatisch suchen" = "daily", "Nur, wenn ich auf „Nach Updates suchen“ klicke" = "manual"),
        selected = if (isTRUE(consent)) "daily" else if (identical(consent, FALSE)) "manual" else character(0)),
      shiny::p(class = "pl-field-hint", DESKTOP_UPDATE_PRIVACY_V1),
      if (is.null(consent)) shiny::p(class = "pl-field-hint", "Noch nicht entschieden: Bis dahin sucht Portelyra nur auf Klick."))
  })
  consent_feedback <- shiny::reactiveVal(NULL)
  output$program_update_consent_feedback <- shiny::renderUI(data_action_feedback_panel_v1(consent_feedback()))
  save_consent <- function(consent, via) {
    if (isTRUE(demo)) return(list(title = "Nicht gespeichert", copy = DATA_PROGRAM_DEMO_TEXT_V1, tone = "error"))
    if (!home_ok) return(list(title = "Nicht gespeichert", copy = "Dieses Portelyra läuft ohne Programmordner.", tone = "error"))
    written <- tryCatch(desktop_installation_settings_write_v1(home, list(update_check = list(consent = consent, via = via)), now = now()),
                        error = function(error) error)
    if (inherits(written, "error")) return(list(title = "Nicht gespeichert", copy = "Die Einstellungen der Installation ließen sich nicht schreiben.", tone = "error"))
    revision(revision() + 1L)
    list(title = "Gespeichert", tone = "positive",
         copy = if (consent) "Portelyra sucht einmal am Tag automatisch nach neuen Versionen." else "Portelyra sucht nur, wenn Sie auf „Nach Updates suchen“ klicken.")
  }
  shiny::observeEvent(input$program_update_consent_save, {
    choice <- input$program_update_consent_choice
    if (!is.character(choice) || length(choice) != 1L || !choice %in% c("daily", "manual")) {
      return(consent_feedback(list(title = "Nicht gespeichert", copy = "Bitte eine der beiden Möglichkeiten wählen.", tone = "error")))
    }
    consent_feedback(save_consent(identical(choice, "daily"), "settings"))
  }, ignoreInit = TRUE)
  # Einmal fuer Installationen ohne Antwort (etwa nach dem Update von 0.3.2): dieselbe Frage wie im Einrichtungsdialog, ohne Vorauswahl.
  consent_hidden <- shiny::reactiveVal(FALSE)
  output$program_consent_card <- shiny::renderUI({
    current <- settings()
    undecided <- current$status %in% c("absent", "available") && is.null(current$settings$update_consent)
    if (!home_ok || isTRUE(demo) || isTRUE(consent_hidden()) || !undecided) return(NULL)
    htmltools::tagAppendAttributes(id = "data-program-consent", portelyra_card("Nach neuen Versionen suchen?",
      copy = "Portelyra kann selbst nachsehen, ob es eine neuere Version gibt, und es links anzeigen.",
      shiny::p(DESKTOP_UPDATE_PRIVACY_V1),
      shiny::div(class = "pl-editor-actions",
        shiny::actionButton("program_consent_yes", "Ja, einmal am Tag suchen", class = "btn-default"),
        shiny::actionButton("program_consent_no", "Nein, nur auf Knopfdruck", class = "btn-default"),
        shiny::actionButton("program_consent_later", "Später fragen", class = "btn-default")),
      shiny::p(class = "pl-field-hint", "Ändern lässt es sich jederzeit in den Einstellungen unter „Programm“.")))
  })
  shiny::observeEvent(input$program_consent_yes, consent_feedback(save_consent(TRUE, "card")), ignoreInit = TRUE)
  shiny::observeEvent(input$program_consent_no, consent_feedback(save_consent(FALSE, "card")), ignoreInit = TRUE)
  shiny::observeEvent(input$program_consent_later, consent_hidden(TRUE), ignoreInit = TRUE)
  shiny::outputOptions(output, "program_consent_card", suspendWhenHidden = FALSE)
  # --- Einspielen aus der App (#562 Paket 4): herunterladen (Groesse, digest), pruefen wie Schritt 1 von `update` (Signatur gegen die
  # installierte Vertrauensliste), bestaetigen, dann `update --page` in eigener Einheit. Ohne Bestaetigung startet nichts.
  apply_state <- shiny::reactiveVal(NULL)
  apply_warn <- shiny::reactiveVal(FALSE)
  offered <- shiny::reactive({
    status <- update_status()
    if (is.list(status) && identical(status$result, "available") && desktop_program_version_newer_v1(status$version, version)) status else NULL
  })
  output$program_update_apply <- shiny::renderUI({
    status <- offered(); state <- apply_state()
    if (isTRUE(demo) || !home_ok || is.null(status)) return(NULL)
    if (is.list(state) && identical(state$stage, "started")) {
      return(portelyra_status_panel(paste0("Update auf Version ", state$version, " läuft"), paste("Portelyra beendet sich gleich, legt ein Backup an,",
        "spielt die neue Version ein und startet neu. Eine eigene Seite zeigt die Schritte; dieses Fenster können Sie danach schließen."), tone = "positive"))
    }
    if (is.list(state) && identical(state$stage, "ready") && identical(state$version, status$version)) {
      return(shiny::tagList(
        portelyra_status_panel(paste0("Version ", status$version, " heruntergeladen und geprüft"),
          paste0("Größe", if (isTRUE(state$digest_checked)) ", Prüfsumme" else "", " und Signatur stimmen.",
                 " Beim Einspielen beendet sich Portelyra, legt ein Backup an und prüft es, spielt die neue Version ein, prüft sie,",
                 " behält die drei jüngsten Backups und startet neu. Das dauert einige Minuten."), tone = "positive"),
        if (isTRUE(apply_warn())) portelyra_status_panel("Noch nicht bestätigt", "Bitte das Kästchen setzen.", tone = "warning"),
        shiny::checkboxInput("program_update_confirm", "Ich habe verstanden: Portelyra beendet sich für das Update und startet danach neu.", FALSE, width = "100%"),
        shiny::div(class = "pl-editor-actions", shiny::actionButton("program_update_apply_now", "Update jetzt einspielen", class = "btn-primary"))))
    }
    size <- if (is.list(status$archive) && is.numeric(status$archive$size)) paste0(" (", format(round(status$archive$size / 1048576, 1), decimal.mark = ","), " MB)") else ""
    shiny::tagList(
      if (is.list(state) && identical(state$stage, "failed")) portelyra_status_panel(state$title, state$text, tone = "warning"),
      shiny::p(class = "pl-field-hint", paste0("Lädt das Archiv von GitHub", size, " und prüft Größe, Prüfsumme und Signatur. Eingespielt wird erst nach Ihrer Bestätigung.")),
      shiny::div(class = "pl-editor-actions", shiny::actionButton("program_update_download", "Herunterladen und prüfen", class = "btn-default")))
  })
  shiny::observeEvent(input$program_update_download, {
    status <- offered()
    if (is.null(status) || isTRUE(demo) || !home_ok) return()
    fail <- function(title, text) apply_state(list(stage = "failed", title = title, text = text))
    got <- tryCatch(desktop_update_cli_v1(project_root, "download", list(home = home, version = status$version, running = version), update_runner,
                                          timeout = 960), error = function(error) list(status = "blocked", code = "desktop_update_state_invalid"))
    if (!identical(got$status, "completed") || !is.list(got$result) || !is.character(got$result$file)) {
      return(fail("Nicht heruntergeladen", desktop_update_failure_text_v1(if (is.character(got$code)) got$code else "")))
    }
    checked <- tryCatch(desktop_update_installed_check_v1(project_root, home, got$result$file, check_runner),
                        error = function(error) list(status = "blocked", code = "desktop_product_boundary_failed"))
    if (!identical(checked$status, "checked") || !isTRUE(checked$newer) || !identical(checked$product_version, status$version)) {
      code <- if (is.character(checked$code)) checked$code else if (identical(checked$status, "checked")) "desktop_product_upgrade_unavailable" else "desktop_product_boundary_failed"
      return(fail("Nicht eingespielt", paste0("Die Prüfung mit der installierten Vertrauensliste hat das Archiv abgewiesen: ",
                                             tryCatch(pl_error_text_v1(code), error = function(error) code))))
    }
    apply_warn(FALSE)
    apply_state(list(stage = "ready", version = status$version, file = got$result$file, digest_checked = isTRUE(got$result$digest_checked)))
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$program_update_apply_now, {
    state <- apply_state()
    if (!is.list(state) || !identical(state$stage, "ready") || isTRUE(demo)) return()
    if (!isTRUE(input$program_update_confirm)) return(apply_warn(TRUE))
    port <- port_of()
    if (is.na(port)) return(apply_state(list(stage = "failed", title = "Nicht gestartet", text = "Das Update aus der App geht nur in einem gestarteten Portelyra.")))
    started <- tryCatch(desktop_update_spawn_v1(project_root, home, state$file, state$version, port, unit_of(home), spawn_runner),
                        error = function(error) list(status = "blocked", code = "spawn_failed"))
    if (identical(started$status, "started")) apply_state(list(stage = "started", version = state$version))
    else apply_state(list(stage = "failed", title = "Update nicht gestartet", text = paste0("Der Start des Updates ist gescheitert (", started$code, ").")))
  }, ignoreInit = TRUE)
  # Meldung im Block links (wie in den anderen Apps); der Link oeffnet hier die Karte „Updates“.
  desktop_program_server_v1(input, output, session, if (home_ok) home else "", version, data_program_notice_link_v1())
  invisible(list(version = version, settings = settings, whats_new = whats_new, update_status = update_status))
}
