# Passwortschutz in den Einstellungen der Data-App (#535, rc.396): einrichten, Wiederherstellungsschluessel einmal zeigen, Klartext
# entfernen, Passwort aendern. Entsperrt wird vor dem Start auf einer eigenen Seite (apps/shared/desktop_protection_v1.R).
#
# Festlegungen (03.11. und 10.11.2026): konsequent (verschluesselter Ordner, nicht nur eine Sperre der Apps), abwaehlbar,
# ein Passwort fuer alle Portfolios, ein Wiederherstellungsschluessel fuer Daten und Backups, Klartext nach Pruefung und Backup loeschen.

data_protection_ui_v1 <- function() htmltools::tagAppendAttributes(id = "data-protection-card", portelyra_card("Passwortschutz", help = "passwortschutz",
  copy = "Verschlüsselt Ihren Datenbestand und Ihre Backups. Ohne Passwort ist nichts lesbar, auch nicht in Kopien auf einer Sicherungsplatte.",
  note = portelyra_note_v1(title = "Was geschützt ist und was nicht", id = "data-protection",
    "Geschützt: alle Portfolios, Buchungen, Kurse und Einstellungen sowie die Backups. Die entsperrte Ansicht liegt unter /run/user/… und damit außerhalb von Sicherungen wie Déjà Dup oder Back In Time.",
    "Nicht geschützt: Ihr eigener Belegordner mit den Original-PDFs (Portelyra liest ihn nur), die Programmbibliothek und die Release-Archive.",
    paste("Eigene Kopien außerhalb des Backup-Ordners von Portelyra (etwa dauerhafte Sicherungen an anderer Stelle) bleiben, wie sie sind, und damit",
          "lesbar. Nach dem Einrichten von Hand löschen oder auf ein verschlüsseltes Medium verschieben."),
    "Gegen Schadsoftware im eigenen Benutzerkonto hilft kein Passwort, solange der Bestand entsperrt ist. Gegen Diebstahl des ausgeschalteten Rechners hilft zusätzlich die Festplattenverschlüsselung.",
    "Vorerst nur unter Linux (gocryptfs). Unter macOS und Windows: FileVault bzw. BitLocker."),
  shiny::uiOutput("protection_state"),
  shiny::uiOutput("protection_body")))

data_protection_server_v1 <- function(input, output, session, project_root, home, runner = NULL, stopper = NULL) {
  status <- shiny::reactiveVal(NULL)
  feedback <- shiny::reactiveVal(NULL)
  key <- shiny::reactiveVal(NULL)          # der Wiederherstellungsschluessel, nur in dieser Sitzung und nur bis zum Beenden
  difference <- shiny::reactiveVal(NULL)   # nach dem Einrichten noch in den Klartext geschrieben: wie viele Dateien, wann zuletzt
  call <- function(command, payload = list()) desktop_protection_cli_v1(project_root, home, command, payload, runner)
  refresh <- function() status(call("status"))
  shiny::observeEvent(input$settings_panel_open, if (isTRUE(input$settings_panel_open)) refresh(), ignoreNULL = FALSE)
  panel <- function(value) if (is.list(value)) portelyra_status_panel(value$title, value$copy, tone = value$tone) else NULL
  cleared <- shiny::reactiveVal(0L)
  skipped <- function() {
    cleared()
    marker <- file.path(home, "protection-skipped.json")
    value <- tryCatch(jsonlite::fromJSON(marker, simplifyVector = FALSE), error = function(error) NULL)
    if (!is.list(value) || !length(value$skipped)) return(NULL)
    why <- c(desktop_protection_keyring_unavailable = "Schlüsselbund nicht erreichbar", desktop_protection_keyring_stale = "Passwort im Schlüsselbund veraltet",
             desktop_protection_rekey_pending = "Erneuern des Schlüssels angefordert",
             desktop_protection_password_after_sleep = "nach dem Ruhezustand noch nicht entsperrt")
    times <- vapply(utils::tail(value$skipped, 3L), function(row) paste0(pl_moment_v1(row$at_utc), " (", if (identical(row$kind, "moment")) "Momentaufnahme" else "Alles aktualisieren",
      if (is.character(row$reason) && row$reason %in% names(why)) paste0(" · ", why[[row$reason]]) else "", ")"), character(1L))
    shiny::div(class = "pl-editor-actions", portelyra_status_panel("Zeitläufe ausgefallen, weil Portelyra gesperrt war",
      paste0("Zuletzt: ", paste(times, collapse = "; "), ". „Alles aktualisieren“ holt das Fehlende nach."), tone = "warning"),
      shiny::actionButton("protection_skipped_clear", "Hinweis ausblenden", class = "btn-default"))
  }
  shiny::observeEvent(input$protection_skipped_clear, { unlink(file.path(home, "protection-skipped.json")); cleared(cleared() + 1L) })
  output$protection_state <- shiny::renderUI({
    value <- status(); if (is.null(value)) return(shiny::p(class = "pl-field-hint", "Wird beim Öffnen der Einstellungen gelesen."))
    if (!identical(value$status, "completed")) return(panel(list(title = "Zustand nicht lesbar", copy = desktop_protection_message_v1(value$code, value$detail), tone = "warning")))
    result <- value$result
    shiny::tagList(
      if (!isTRUE(result$enabled)) shiny::p(class = "pl-field-hint", "Der Passwortschutz ist aus: Der Datenbestand liegt unverschlüsselt im Portelyra-Ordner.")
      else shiny::p(class = "pl-field-hint", paste0("Der Passwortschutz ist an (eingerichtet am ", pl_day_v1(result$created_at_utc),
        "). Ihr Bestand ist entsperrt und bleibt es, bis Sie sich am Rechner abmelden, ihn herunterfahren oder er in den Ruhezustand geht.")),
      data_protection_stray_ui_v1(result), skipped(), panel(feedback()))
  })
  output$protection_body <- shiny::renderUI({
    value <- status(); if (!is.list(value) || !identical(value$status, "completed")) return(NULL)
    result <- value$result
    if (!is.null(key())) return(shiny::div(class = "pl-field-group",
      shiny::h4(class = "pl-section-title", "Ihr Wiederherstellungsschlüssel – nur jetzt sichtbar"),
      shiny::tags$pre(style = "font-size:1.15rem;user-select:all;", key()),
      portelyra_status_panel("Bitte aufschreiben und sicher verwahren", paste(
        "Mit diesem Schlüssel setzen Sie ein neues Passwort, falls Sie es vergessen. Er öffnet alle Daten und Backups ohne Passwort, auch Kopien",
        "auf einer Sicherungsplatte, und bleibt nach einer Passwortänderung gültig. Verwahren Sie ihn so sicher wie die Daten selbst.",
        "Portelyra speichert ihn nicht. Sind Passwort und Schlüssel beide verloren, sind die Daten verloren."), tone = "warning"),
      shiny::checkboxInput("protection_key_noted", "Ich habe den Wiederherstellungsschlüssel aufgeschrieben.", FALSE),
      shiny::p(class = "pl-field-hint", paste("Danach beendet sich Portelyra. Beim nächsten Start fragt eine eigene Seite nach dem Passwort; beim ersten",
        "Start legt Portelyra ein Backup im verschlüsselten Ordner an. Den bisherigen unverschlüsselten Bestand entfernen Sie danach hier.")),
      shiny::div(class = "pl-editor-actions", shiny::actionButton("protection_finish", "Portelyra beenden", class = "btn-primary"))))
    if (!isTRUE(result$enabled)) return(shiny::div(class = "pl-field-group",
      shiny::passwordInput("protection_password", "Passwort (mindestens 10 Zeichen)"),
      shiny::passwordInput("protection_repeat", "Passwort wiederholen"),
      shiny::checkboxInput("protection_understood", paste("Mir ist klar: Ohne Passwort und Wiederherstellungsschlüssel sind die Daten verloren.",
        "Während des Einrichtens (einige Minuten) bearbeite ich nichts anderes."), FALSE),
      # Mit der Anmeldung entsperren (#553, Festlegung 11.11.2026: vorangekreuzt).
      shiny::checkboxInput("protection_keyring", "Mit der Anmeldung am Rechner entsperren (Passwort im Schlüsselbund)", TRUE),
      shiny::p(class = "pl-field-hint", paste("Dann laufen Zeitpläne auch bei beendetem Portelyra, und der Start braucht kein Passwort, solange Sie am",
        "Rechner angemeldet sind; nach dem Ruhezustand fragt Portelyra nach dem Passwort. Ausgeschaltet oder abgemeldet bleibt alles verschlüsselt. Wer sich am Rechner automatisch ohne Passwort anmeldet,",
        "hebt damit den Schutz faktisch auf.")),
      shiny::p(class = "pl-field-hint", paste("Portelyra kopiert den Datenbestand und die vorhandenen Backups in verschlüsselte Ordner und prüft jede Datei.",
        "Der unverschlüsselte Bestand bleibt bis zum ausdrücklichen Entfernen liegen.")),
      shiny::div(class = "pl-editor-actions", shiny::actionButton("protection_enable", "Passwortschutz einrichten", class = "btn-primary"))))
    shiny::tagList(
      if (!isTRUE(result$plaintext_removed)) shiny::div(class = "pl-field-group",
        shiny::h4(class = "pl-section-title", "Unverschlüsselten Bestand entfernen"),
        if (isTRUE(result$first_backup_due)) portelyra_status_panel("Zuerst ein Backup", paste("Im verschlüsselten Backup-Ordner liegt noch kein Backup, das nach dem",
          "Einrichten entstand. Portelyra legt es beim nächsten Start an; bitte einmal beenden und neu starten."), tone = "neutral")
        else shiny::tagList(
          shiny::p(class = "pl-field-hint", paste("Portelyra prüft noch einmal, dass seit dem Einrichten nichts mehr in den unverschlüsselten Bestand",
            "geschrieben wurde, und löscht ihn dann samt der alten, unverschlüsselten Backups. Auf SSDs können Reste bleiben; das deckt die",
            "Festplattenverschlüsselung ab.")),
          shiny::checkboxInput("protection_finalize_confirm", "Unverschlüsselten Bestand jetzt löschen", FALSE),
          if (is.list(difference())) shiny::checkboxInput("protection_finalize_accept", sprintf(paste(
            "Trotzdem löschen: Die %s seit dem Einrichten geänderten Dateien (zuletzt %s) fehlen im verschlüsselten Stand, mit dem Portelyra",
            "seit dem Neustart arbeitet."), pl_number_v1(difference()$changed_count, 0L), pl_moment_v1(difference()$newest_utc)), FALSE),
          shiny::div(class = "pl-editor-actions", shiny::actionButton("protection_finalize", "Entfernen", class = "btn-default")))),
      data_protection_lock_ui_v1(result),
      data_protection_keyring_ui_v1(result),
      data_protection_old_ciphers_ui_v1(result),
      data_protection_rekey_ui_v1(result),
      shiny::tags$details(class = "pl-disclosure", id = "protection-password-change", shiny::tags$summary("Passwort ändern"),
        shiny::passwordInput("protection_old", "Bisheriges Passwort"),
        shiny::passwordInput("protection_new", "Neues Passwort (mindestens 10 Zeichen)"),
        shiny::passwordInput("protection_new_repeat", "Neues Passwort wiederholen"),
        shiny::p(class = "pl-field-hint", paste("Der Wiederherstellungsschlüssel bleibt derselbe. Das Passwort schützt nur die Schlüsseldatei: Wer eine",
          "ältere Kopie des Ordners (etwa aus einer Sicherung) und das alte Passwort hat, öffnet damit weiter. Ist ein Passwort oder der Schlüssel",
          "bekannt geworden, hilft erst „Schlüssel erneuern“ (alles neu verschlüsseln), das später kommt.")),
        shiny::div(class = "pl-editor-actions", shiny::actionButton("protection_change", "Passwort ändern", class = "btn-default"))))
  })
  clear <- function(ids) for (id in ids) shiny::updateTextInput(session, id, value = "")
  shiny::observeEvent(input$protection_enable, {
    password <- input$protection_password; repeat_value <- input$protection_repeat
    clear(c("protection_password", "protection_repeat"))
    if (!isTRUE(input$protection_understood)) return(feedback(list(title = "Bitte bestätigen", copy = "Bitte den Hinweis zum Verlust der Daten bestätigen.", tone = "warning")))
    backups <- file.path(Sys.getenv("XDG_STATE_HOME", unset = file.path(Sys.getenv("HOME"), ".local", "state")), "portelyra", "backups")
    result <- call("enable", list(password = password, `repeat` = repeat_value, confirmed = TRUE, backups_source = if (dir.exists(backups)) backups else NULL,
                                  keyring = !identical(input$protection_keyring, FALSE)))   # Vorgabe an (Festlegung 11.11.2026)
    if (!identical(result$status, "completed")) return(feedback(list(title = "Nicht eingerichtet", copy = desktop_protection_message_v1(result$code, result$detail), tone = "warning")))
    key(result$result$recovery_key)
    feedback(list(title = "Passwortschutz eingerichtet", copy = paste0(sprintf("%s Dateien verschlüsselt kopiert und geprüft, dazu %s Dateien der Backups.",
      pl_number_v1(result$result$file_count, 0L), pl_number_v1(result$result$backup_file_count, 0L)),
      if (isTRUE(result$result$keyring_failed)) " Der Schlüsselbund war nicht erreichbar: „Mit der Anmeldung entsperren“ ist aus und lässt sich später einschalten." else ""),
      tone = if (isTRUE(result$result$keyring_failed)) "warning" else "positive"))
    refresh()
  })
  shiny::observeEvent(input$protection_finish, {
    if (!isTRUE(input$protection_key_noted)) return(feedback(list(title = "Bitte bestätigen", copy = "Bitte bestätigen, dass der Schlüssel aufgeschrieben ist.", tone = "warning")))
    key(NULL)
    call("lock")
    feedback(list(title = "Portelyra beendet sich", copy = "Bitte Portelyra neu starten; die Startseite fragt dann nach dem Passwort.", tone = "neutral"))
    if (is.function(stopper)) stopper()
  })
  shiny::observeEvent(input$protection_finalize, {
    if (!isTRUE(input$protection_finalize_confirm)) return(feedback(list(title = "Bitte bestätigen", copy = "Bitte das Löschen bestätigen.", tone = "warning")))
    accept <- is.list(difference()) && isTRUE(input$protection_finalize_accept)
    result <- call("finalize", c(list(confirmed = TRUE), if (accept) list(accept_difference = TRUE)))
    changed <- identical(result$code, "desktop_protection_copy_mismatch") && is.list(result$detail) && is.numeric(result$detail$changed_count)
    difference(if (changed) result$detail else NULL)
    feedback(if (identical(result$status, "completed")) list(title = "Unverschlüsselter Bestand entfernt", copy = sprintf("%s Einträge gelöscht.",
      pl_number_v1(result$result$removed_entry_count, 0L)), tone = "positive")
      else if (changed) list(title = "Nicht entfernt: Klartext seit dem Einrichten geändert", copy = sprintf(paste(
        "Nach dem Einrichten und vor dem Neustart wurden noch %s Dateien im unverschlüsselten Bestand geändert, zuletzt %s – etwa durch einen",
        "Zeitlauf. Portelyra arbeitet seit dem Neustart mit dem verschlüsselten Stand; diese Änderungen sind dort nicht enthalten. Meist sind es",
        "Ergebnisse, die „Alles aktualisieren“ neu erzeugt. Wurde in dieser Zeit gebucht, die Buchung im verschlüsselten Stand prüfen."),
        pl_number_v1(result$detail$changed_count, 0L), pl_moment_v1(result$detail$newest_utc)), tone = "warning")
      else list(title = "Nicht entfernt", copy = desktop_protection_message_v1(result$code, result$detail), tone = "warning"))
    refresh()
  })
  shiny::observeEvent(input$protection_change, {
    old <- input$protection_old; new <- input$protection_new; repeat_value <- input$protection_new_repeat
    clear(c("protection_old", "protection_new", "protection_new_repeat"))
    result <- call("change-password", list(old = old, new = new, `repeat` = repeat_value))
    feedback(if (identical(result$status, "completed")) list(title = "Passwort geändert", copy = paste0("Gilt ab dem nächsten Entsperren; der Wiederherstellungsschlüssel bleibt.",
        if (isTRUE(result$result$keyring_updated)) " Der Schlüsselbund ist mitgeändert." else if (identical(result$result$keyring_updated, FALSE))
          " Der Schlüsselbund war nicht erreichbar: „Mit der Anmeldung entsperren“ ist jetzt aus." else ""), tone = "positive")
      else list(title = "Passwort nicht geändert", copy = desktop_protection_message_v1(result$code, result$detail), tone = "warning"))
  })
  # Mit der Anmeldung entsperren (#553): einschalten mit dem Passwort (geprueft gegen den Hauptschluessel), ausschalten leert den Eintrag.
  shiny::observeEvent(input$protection_keyring_on, {
    password <- input$protection_keyring_password; clear("protection_keyring_password")
    result <- call("keyring", list(enabled = TRUE, password = password))
    feedback(if (identical(result$status, "completed")) list(title = "Mit der Anmeldung entsperren: an", copy = paste("Start und Zeitpläne entsperren selbst, solange Sie am",
      "Rechner angemeldet sind."), tone = "positive") else list(title = "Nicht eingeschaltet", copy = desktop_protection_message_v1(result$code, result$detail), tone = "warning"))
    refresh()
  })
  shiny::observeEvent(input$protection_keyring_off, {
    result <- call("keyring", list(enabled = FALSE))
    feedback(if (identical(result$status, "completed")) list(title = "Mit der Anmeldung entsperren: aus", copy = paste("Das Passwort ist aus dem Schlüsselbund entfernt.",
      "Entsperrt wird auf der Startseite; Zeitpläne laufen nur, solange der Bestand entsperrt ist."), tone = "neutral")
      else list(title = "Nicht ausgeschaltet", copy = desktop_protection_message_v1(result$code, result$detail), tone = "warning"))
    refresh()
  })
  # Sperren (#587): Der Bestand bleibt bis zur Abmeldung offen; strenger per Einstellung oder von Hand.
  shiny::observeEvent(input$protection_lock_on_quit, {
    value <- status(); wanted <- isTRUE(input$protection_lock_on_quit)
    if (!is.list(value) || !identical(value$status, "completed") || identical(isTRUE(value$result$lock_on_quit), wanted)) return(invisible())
    result <- call("lock-on-quit", list(enabled = wanted))
    feedback(if (identical(result$status, "completed")) list(title = if (wanted) "Beim Beenden sperren: an" else "Beim Beenden sperren: aus",
      copy = if (wanted) "Portelyra sperrt Ihren Bestand, sobald es beendet ist; läuft noch ein Zeitplan, an dessen Ende."
             else "Ihr Bestand bleibt entsperrt, bis Sie sich am Rechner abmelden, ihn herunterfahren oder er in den Ruhezustand geht.", tone = "neutral")
      else list(title = "Nicht geändert", copy = desktop_protection_message_v1(result$code, result$detail), tone = "warning"))
    refresh()
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$protection_lock_now, shiny::showModal(shiny::modalDialog(title = "Jetzt sperren?",
    shiny::p("Portelyra beendet sich dabei. Beim nächsten Start wird wieder entsperrt, mit Schlüsselbund ohne Eingabe, sonst mit Ihrem Passwort.",
             "Ein Zeitplan öffnet den Bestand über den Schlüsselbund nur für seinen Lauf und sperrt ihn danach wieder."),
    footer = shiny::tagList(shiny::modalButton("Abbrechen"), shiny::actionButton("protection_lock_now_confirm", "Sperren und beenden", class = "btn-primary")))))
  shiny::observeEvent(input$protection_lock_now_confirm, {
    shiny::removeModal()
    result <- call("request-lock")
    if (!identical(result$status, "completed")) return(feedback(list(title = "Nicht gesperrt", copy = desktop_protection_message_v1(result$code, result$detail), tone = "warning")))
    feedback(list(title = "Portelyra beendet sich", copy = "Ihr Bestand wird gesperrt, sobald die Apps angehalten sind.", tone = "neutral"))
    if (is.function(stopper)) stopper()
  })
  shiny::observeEvent(input$protection_stray_ack, { call("stray-ack"); refresh() })
  # Schluessel erneuern (#552): anstossen, dann beendet sich Portelyra; die Startseite erneuert beim naechsten Start.
  shiny::observeEvent(input$protection_rekey_request, {
    if (!isTRUE(input$protection_rekey_confirm)) return(feedback(list(title = "Bitte bestätigen", copy = "Bitte bestätigen, dass Portelyra sich dafür beendet.", tone = "warning")))
    result <- call("request-rekey", list(confirmed = TRUE))
    if (!identical(result$status, "completed")) return(feedback(list(title = "Nicht angestoßen", copy = desktop_protection_message_v1(result$code, result$detail), tone = "warning")))
    call("lock")
    feedback(list(title = "Portelyra beendet sich", copy = "Bitte neu starten; die Startseite erneuert dann den Schlüssel.", tone = "neutral"))
    if (is.function(stopper)) stopper()
  })
  shiny::observeEvent(input$protection_rekey_cancel, { call("cancel-rekey"); refresh() })
  shiny::observeEvent(input$protection_old_remove, {
    if (!isTRUE(input$protection_old_confirm)) return(feedback(list(title = "Bitte bestätigen", copy = "Bitte das Entfernen bestätigen.", tone = "warning")))
    result <- call("remove-old", list(confirmed = TRUE))
    feedback(if (identical(result$status, "completed")) list(title = "Alte Ordner entfernt", copy = sprintf("%s Einträge gelöscht.", pl_number_v1(result$result$removed_entry_count, 0L)),
      tone = "positive") else list(title = "Nicht entfernt", copy = desktop_protection_message_v1(result$code, result$detail), tone = "warning"))
    refresh()
  })
  invisible(list(status = status, refresh = refresh))
}

# Mit der Anmeldung entsperren (#553): Zustand und Schalter.
# Sperren (#587): bleibt bis zur Abmeldung offen; strenger per Einstellung oder von Hand.
data_protection_lock_ui_v1 <- function(result) {
  shiny::div(class = "pl-field-group", id = "protection-lock",
    shiny::h4(class = "pl-section-title", "Sperren"),
    shiny::p(class = "pl-field-hint", paste("Von Ihnen entsperrt bleibt Ihr Bestand offen, bis Sie sich am Rechner abmelden, ihn herunterfahren oder er in den",
      "Ruhezustand geht, auch wenn Portelyra beendet ist. In dieser Zeit schützt ihn die Bildschirmsperre Ihres Rechners.",
      "Öffnet ein Zeitplan den gesperrten Bestand, sperrt er ihn nach seinem Lauf wieder.")),
    shiny::checkboxInput("protection_lock_on_quit", "Beim Beenden von Portelyra sperren", isTRUE(result$lock_on_quit)),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("protection_lock_now", "Jetzt sperren", class = "btn-default")))
}

# Lag beim Entsperren etwas im leeren Bestandsordner (#587), steht es hier: nie still weggeraeumt.
data_protection_stray_ui_v1 <- function(result) {
  note <- result$stray_note
  if (!is.list(note) || !is.numeric(note$file_count)) return(NULL)
  shiny::div(class = "pl-editor-actions", portelyra_status_panel("Dateien aus einer Zeit ohne Verbindung zum Bestand", sprintf(paste(
    "Beim Entsperren am %s lagen %s Dateien im leeren Bestandsordner. Sie entstanden, während der Bestand nicht verbunden war, und sind nicht",
    "darin enthalten. Meist sind es Zwischenstände. Haben Sie in dieser Zeit etwas gebucht, prüfen Sie bitte, ob es fehlt. Die Dateien liegen",
    "bis zum Abmelden in einem geschützten Ordner im Arbeitsspeicher."), pl_moment_v1(note$at_utc), pl_number_v1(note$file_count, 0L)), tone = "warning"),
    shiny::actionButton("protection_stray_ack", "Hinweis ausblenden", class = "btn-default"))
}

data_protection_keyring_ui_v1 <- function(result) {
  on <- isTRUE(result$keyring_unlock)
  shiny::div(class = "pl-field-group", id = "protection-keyring",
    shiny::h4(class = "pl-section-title", "Mit der Anmeldung entsperren"),
    shiny::p(class = "pl-field-hint", if (on) paste("An: Das Passwort liegt im Schlüsselbund. Start, Zeitpläne und Updates entsperren selbst, solange Sie am",
      "Rechner angemeldet sind; nach dem Ruhezustand fragt Portelyra nach dem Passwort. Wer sich automatisch ohne Passwort anmeldet, hebt damit den Schutz faktisch auf.")
      else "Aus: Entsperrt wird auf der Startseite; Zeitpläne laufen nur, solange der Bestand entsperrt ist."),
    if (!isTRUE(result$keyring_tool)) portelyra_status_panel("Schlüsselbund nicht verfügbar", "Für den Schlüsselbund fehlt secret-tool (Paket „libsecret-tools“).", tone = "neutral")
    else if (on) shiny::div(class = "pl-editor-actions", shiny::actionButton("protection_keyring_off", "Ausschalten", class = "btn-default"))
    else shiny::tagList(shiny::passwordInput("protection_keyring_password", "Passwort"),
      shiny::div(class = "pl-editor-actions", shiny::actionButton("protection_keyring_on", "Einschalten", class = "btn-default"))))
}

# Nach dem Erneuern (#552): die alten verschluesselten Ordner erst nach einem Backup in den neuen entfernen.
data_protection_old_ciphers_ui_v1 <- function(result) {
  if (!isTRUE(result$old_ciphers_pending)) return(NULL)
  shiny::div(class = "pl-field-group",
    shiny::h4(class = "pl-section-title", "Alte verschlüsselte Ordner entfernen"),
    if (isTRUE(result$first_backup_due)) portelyra_status_panel("Zuerst ein Backup", paste("Im neuen Backup-Ordner liegt noch kein Backup, das nach dem",
      "Erneuern entstand. Portelyra legt es beim nächsten Start an; bitte einmal beenden und neu starten."), tone = "neutral")
    else shiny::tagList(
      shiny::p(class = "pl-field-hint", paste("Die alten Ordner öffnen weiter mit dem alten Passwort und Schlüssel. Ältere Kopien davon, etwa in einer Sicherung,",
        "bleiben lesbar, bis Sie sie dort löschen.")),
      shiny::checkboxInput("protection_old_confirm", "Alte verschlüsselte Ordner jetzt löschen", FALSE),
      shiny::div(class = "pl-editor-actions", shiny::actionButton("protection_old_remove", "Entfernen", class = "btn-default"))))
}

# Schluessel erneuern (#552): in der Karte angestossen, auf der Startseite ausgefuehrt.
data_protection_rekey_ui_v1 <- function(result) shiny::tags$details(class = "pl-disclosure", id = "protection-rekey",
  open = if (isTRUE(result$rekey_requested)) NA else NULL,
  shiny::tags$summary("Schlüssel erneuern"),
  shiny::p(class = "pl-field-hint", paste("Wurde das Passwort oder der Wiederherstellungsschlüssel bekannt, hilft „Passwort ändern“ nicht: Das Passwort schützt",
    "nur die Schlüsseldatei. Erneuern verschlüsselt Datenbestand und Backups mit einem neuen Hauptschlüssel und zeigt einen neuen",
    "Wiederherstellungsschlüssel. Es läuft beim nächsten Start auf der Startseite, bevor die Apps laufen, und braucht zeitweise doppelt so viel",
    "Platz. Ältere Kopien der alten Ordner, etwa in einer Sicherung, öffnen weiter mit dem alten Passwort, bis Sie sie dort löschen.")),
  if (isTRUE(result$rekey_requested)) shiny::tagList(
    portelyra_status_panel("Angestoßen", "Beim nächsten Start fragt die Startseite nach bisherigem und neuem Passwort.", tone = "neutral"),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("protection_rekey_cancel", "Zurücknehmen", class = "btn-default")))
  else if (isTRUE(result$old_ciphers_pending)) shiny::p(class = "pl-field-hint", "Zuerst die alten Ordner des letzten Erneuerns entfernen.")
  else shiny::tagList(
    shiny::checkboxInput("protection_rekey_confirm", "Portelyra beendet sich dafür; beim nächsten Start erneuere ich auf der Startseite.", FALSE),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("protection_rekey_request", "Schlüssel beim nächsten Start erneuern", class = "btn-default"))))

# Portelyra aus der Data-App beenden (nach dem Einrichten des Passwortschutzes): Die Apps laufen als Kindprozesse des Startskripts; ihm
# geht ein SIGINT, dann haelt es alle Apps an. Nur wenn der Elternprozess wirklich das Startskript ist. Der Stopper wartet `delay`
# Sekunden, damit die Meldung noch im Browser ankommt.
data_protection_stopper_v1 <- function(delay = 2) function() later::later(.data_protection_stop_parent_v1, delay)

.data_protection_stop_parent_v1 <- function() {
  parent <- suppressWarnings(as.integer(trimws(system2("ps", c("-o", "ppid=", "-p", Sys.getpid()), stdout = TRUE))))
  if (length(parent) != 1L || is.na(parent) || parent <= 1L) return(invisible(FALSE))
  command <- paste(system2("ps", c("-o", "args=", "-p", parent), stdout = TRUE), collapse = " ")
  if (!grepl("portelyra_desktop\\.R", command)) return(invisible(FALSE))
  tools::pskill(parent, tools::SIGINT)
  invisible(TRUE)
}
