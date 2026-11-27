# Wiederherstellen im Einrichtungsdialog (#559 Teil 2, rc.408): „Aus einem vorhandenen Backup übernehmen“ beim ersten Start.
#
# Festlegungen (13.11.2026): Die Quelle bleibt immer unveraendert; ein Backup aus einem neueren Programmstand wird
# nicht uebernommen; die Zeitplaene fragt der Dialog neu (keine Zustimmung wird still uebernommen); kommt das Backup aus dem
# verschluesselten Ordner, ist der Passwortschutz vorbelegt. Passwort und Wiederherstellungsschluessel nur im Speicher dieser Sitzung.
#
# Ablauf: Quelle (Klartext-Ordner, verschluesselter Ordner mit Passwort oder Schluessel) -> Backup waehlen -> pruefen und in das gerade
# eingerichtete Home uebernehmen (desktop_release_restore_fresh_v1) -> nur Zeitplan und Passwortschutz -> Start. Den Plan der normalen
# Einrichtung nutzt dieser Weg bewusst nicht: Umfang, Steuer und Kurse kommen aus dem Backup und duerfen nicht neu gesetzt werden.

DESKTOP_SETUP_RESTORE_RELOCATION_V1 <- c(not_needed = "am ursprünglichen Ort, nichts zu binden", recorded = "an den neuen Ort gebunden",
  present = "war schon gebunden", unverified = "noch nicht gebunden – siehe Handbuch „Backup zurückspielen“",
  not_possible = "Bindung nicht möglich – siehe Handbuch „Backup zurückspielen“")

.desktop_setup_restore_state_root_v1 <- function() {
  state <- Sys.getenv("XDG_STATE_HOME", unset = "")
  if (!nzchar(state)) state <- file.path(path.expand("~"), ".local", "state")
  file.path(state, "portelyra")
}

# Die echten Wege; im Test ersetzbar.
#
# Quellen werden hier nur gelesen, deshalb ohne Pruefung von Besitzer und Rechten der Quelle (rc.410, Festlegung 13.11.2026: der Weg soll
# auch von einem USB-Stick oder einer anderen Partition gehen): Ein Medium ohne Rechteverwaltung (FAT, exFAT, NTFS) zeigt jede Datei als
# fuer alle lesbar, ein Datentraeger eines anderen Rechners traegt eine fremde Besitzerkennung, eine Kopie von dort behaelt beides. Der
# Kern prueft Lesbarkeit, Form und jede Pruefsumme; die Rechte im Home setzt das Zurueckspielen aus dem Manifest.
.desktop_setup_restore_services_v1 <- function(project_root, home, services = list()) {
  protection <- function(command, payload) desktop_protection_cli_v1(project_root, home, command, payload)
  listing <- function(root) spotcore::desktop_release_backup_list_v1(project_root, root, source_permissions = "ignored")
  defaults <- list(
    # Was es gibt: Backups im Klartext-Ordner (gelesen) und ob ein verschluesselter Ordner da ist (erst nach dem Oeffnen lesbar).
    sources = function() {
      base <- .desktop_setup_restore_state_root_v1()
      plain <- file.path(base, "backups")
      listed <- if (dir.exists(plain)) tryCatch(listing(plain), error = function(error) NULL) else NULL
      list(plain_root = if (is.list(listed) && length(listed$bundles)) plain else NULL,
           plain = if (is.list(listed)) listed$bundles else list(),
           encrypted = file.exists(file.path(base, "backups.crypt", "gocryptfs.conf")))
    },
    # `cipher`: ein verschluesselter Ordner an anderer Stelle (Ordnerwahl, rc.410); NULL ist der Backup-Ordner von Portelyra.
    open = function(secret, kind, cipher = NULL) protection("restore-open", c(list(secret = secret, kind = kind), if (!is.null(cipher)) list(cipher = cipher))),
    # Ein vom Nutzer genannter Ordner: verschluesselt (gocryptfs.conf) oder ein Ordner mit Backups (nur Kopfdaten gelesen). Nennt der
    # Nutzer ein einzelnes Backup statt des Ordners darueber, gilt der Ordner darueber - gezeigt wird dann nur dieses Backup.
    inspect = function(path) {
      if (file.exists(file.path(path, "gocryptfs.conf"))) return(list(kind = "encrypted"))
      single <- all(file.exists(file.path(path, c("SUCCESS", "backup-manifest.json")))) && dir.exists(file.path(path, "payload"))
      if (!single) return(list(kind = "plain", root = path, bundles = listing(path)$bundles))
      list(kind = "plain", root = dirname(path), bundles = Filter(function(row) identical(row$name, basename(path)), listing(dirname(path))$bundles))
    },
    close = function(mount) protection("restore-close", list(mount = mount)),
    list = listing,
    check = function(bundle) spotcore::desktop_release_backup_check_v1(project_root, bundle, source_permissions = "ignored"),
    restore = function(bundle) spotcore::desktop_release_restore_fresh_v1(project_root, home, bundle, source_permissions = "ignored"),
    set_aside = function() protection("set-aside-backups", list(confirmed = TRUE)))
  utils::modifyList(defaults, services)
}

.desktop_setup_restore_code_v1 <- function(error) {
  code <- tryCatch(as.character(error$code), error = function(e) character())
  if (!(length(code) == 1L && nzchar(code))) code <- conditionMessage(error)
  if (length(code) == 1L && grepl("^[a-z][a-z0-9_]{2,80}$", code)) code else "desktop_setup_restore_failed"
}
.desktop_setup_restore_message_v1 <- function(code) {
  text <- if (is.null(code) || length(code) != 1L) "" else as.character(code)
  switch(text,
    desktop_release_restore_newer_version = "Dieses Backup stammt aus einem neueren Programmstand. Bitte zuerst Portelyra aktualisieren.",
    desktop_release_backup_integrity_invalid = "Das Backup ist beschädigt oder unvollständig. Bitte ein anderes wählen.",
    desktop_release_manifest_invalid = "Das Backup ist beschädigt oder unvollständig. Bitte ein anderes wählen.",
    desktop_release_restore_target_not_empty = "Hier gibt es schon einen Datenbestand. Wiederherstellen geht nur beim ersten Start.",
    desktop_release_permissions_invalid = paste("Der Ordner oder Dateien darin sind für Sie nicht lesbar. Bitte die Leserechte prüfen –",
      "etwa bei einem Datenträger von einem anderen Rechner oder Benutzerkonto."),
    desktop_release_root_invalid = "Der Ordner ist nicht lesbar oder kein Ordner.",
    desktop_release_symlink_rejected = "Im Backup liegt ein symbolischer Verweis. Portelyra folgt in einem Backup keinen Verweisen.",
    desktop_setup_restore_folder_invalid = "Bitte den vollständigen Pfad eines vorhandenen Ordners nennen, etwa /home/…/Backups.",
    desktop_protection_password_wrong = "Das Passwort stimmt nicht.",
    desktop_protection_recovery_key_invalid = "Der Wiederherstellungsschlüssel stimmt nicht.",
    desktop_protection_backups_absent = "Es gibt keinen verschlüsselten Backup-Ordner.",
    desktop_protection_tool_missing = "Für verschlüsselte Backups fehlt gocryptfs auf diesem Rechner.",
    desktop_protection_backups_in_use = paste("Der verschlüsselte Backup-Ordner ist gerade von einer anderen Portelyra-Installation auf diesem Konto geöffnet.",
      "Er wird nicht umbenannt. Den Passwortschutz jetzt mit „Nein“ überspringen oder die andere Installation zuerst beenden."),
    desktop_setup_restore_failed = "Das Wiederherstellen ist nicht gelungen.",
    pl_error_text_v1(text))
}
.desktop_setup_restore_size_v1 <- function(bytes) {
  value <- suppressWarnings(as.numeric(bytes)); if (length(value) != 1L || is.na(value)) return("–")
  if (value >= 1024^3) sprintf("%s GB", format(round(value / 1024^3, 1), decimal.mark = ",", nsmall = 1L))
  else sprintf("%s MB", format(round(value / 1024^2, 1), decimal.mark = ",", nsmall = 1L))
}
.desktop_setup_restore_label_v1 <- function(row) {
  when <- tryCatch(format(as.POSIXct(row$created_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), "%d.%m.%Y %H:%M", tz = ""),
                   error = function(error) as.character(row$created_at_utc))
  paste0(row$name, " · ", when, " · ", row$product_version, " · ", .desktop_setup_restore_size_v1(row$byte_count),
         if (isTRUE(row$newer_version)) " · neuerer Programmstand – nicht übernehmbar" else "")
}

# Installiert die Beobachter und liefert body(at) fuer die Stationen "restore" und "restore_followup". `finish(results, key)` vermerkt das
# Ergebnis und startet Portelyra (wie nach „Übernehmen“); `apply_followup(steps, password)` wendet Zeitplan und Schutz an.
# `remember(value)` haelt den Zwischenstand nach dem Uebernehmen fest (Vermerk im Home und Entwurf an der Stelle "restore_followup"),
# `resumed` ist ein solcher Vermerk aus einer frueheren Sitzung oder NULL (rc.410): Ohne ihn stand nach einem Neuladen wieder die
# Startseite da, und „Los geht's“ haette Umfang, Steuer und Kurse ueber den wiederhergestellten Bestand neu gesetzt (Prüfung 13.11.2026).
desktop_setup_restore_server_v1 <- function(input, session, services, position, feedback, finish, apply_followup, remember = NULL, resumed = NULL) {
  sources <- shiny::reactiveVal(NULL)
  mount <- shiny::reactiveVal(NULL)        # eingehaengter verschluesselter Ordner (nur in dieser Sitzung)
  encrypted_list <- shiny::reactiveVal(NULL)
  restored <- shiny::reactiveVal(if (is.list(resumed)) resumed else NULL)     # Ergebnis des Uebernehmens
  from_encrypted <- shiny::reactiveVal(is.list(resumed) && isTRUE(resumed$from_encrypted))
  # Ordnerwahl (rc.410): Auf einem neuen
  # Rechner ist der Backup-Ordner von Portelyra leer. Der Nutzer nennt den Ordner selbst; gelesen wird er nur, nie veraendert.
  custom <- shiny::reactiveVal(NULL)       # list(root, kind = "plain"|"encrypted", bundles)
  warn <- function(title, copy) feedback(list(title = title, copy = copy, tone = "warning"))
  folder_path <- function(value) {
    text <- if (is.character(value) && length(value) == 1L && !is.na(value)) trimws(value) else ""
    if (!nzchar(text)) return(NULL)
    text <- sub("/+$", "", path.expand(text))
    if (!startsWith(text, "/") || grepl("[[:cntrl:]]", text) || !dir.exists(text)) return(NULL)
    # Der Nutzer nennt den Ordner bewusst: Ein symbolischer Verweis im genannten Pfad (etwa ~/Backups -> Sicherungsplatte) wird hier
    # aufgeloest und der eigentliche Ordner gezeigt. Innerhalb eines Backups folgt der Kern weiterhin keinem Verweis.
    normalizePath(text, winslash = "/", mustWork = TRUE)
  }
  custom_cipher <- function() { value <- custom(); if (is.list(value) && identical(value$kind, "encrypted")) value$root else NULL }
  available <- function() {
    value <- sources(); if (is.null(value)) { value <- tryCatch(services$sources(), error = function(error) list(plain = list(), encrypted = FALSE)); sources(value) }
    value
  }
  close_mount <- function() {
    current <- shiny::isolate(mount()); if (is.character(current)) tryCatch(services$close(current), error = function(error) NULL)
    mount(NULL); encrypted_list(NULL)
  }
  session$onSessionEnded(function() close_mount())
  shiny::observeEvent(input$setup_restore, { feedback(NULL); position("restore") })
  shiny::observeEvent(input$setup_restore_back, { close_mount(); feedback(NULL); position("welcome") })
  shiny::observeEvent(input$setup_restore_folder_read, {
    path <- folder_path(input$setup_restore_folder)
    if (is.null(path)) return(warn("Ordner nicht gefunden", .desktop_setup_restore_message_v1("desktop_setup_restore_folder_invalid")))
    seen <- tryCatch(services$inspect(path), error = function(error) list(kind = "invalid", code = .desktop_setup_restore_code_v1(error)))
    if (!isTRUE(seen$kind %in% c("plain", "encrypted"))) return(warn("Ordner nicht lesbar", .desktop_setup_restore_message_v1(seen$code)))
    close_mount()
    custom(list(root = if (is.character(seen$root) && length(seen$root) == 1L) seen$root else path, kind = seen$kind,
                bundles = if (identical(seen$kind, "plain")) seen$bundles else list()))
    if (identical(seen$kind, "plain") && !length(seen$bundles)) return(warn("Keine Backups in diesem Ordner",
      "In diesem Ordner liegen keine Backups von Portelyra. Gemeint ist der Ordner, der die einzelnen Backups enthält (etwa „backups“)."))
    feedback(NULL)
  })
  shiny::observeEvent(input$setup_restore_open, {
    secret <- input$setup_restore_secret; kind <- input$setup_restore_kind
    if (!is.character(secret) || !nzchar(secret)) return(warn("Angabe fehlt", "Bitte Passwort oder Wiederherstellungsschlüssel eingeben."))
    opened <- tryCatch(services$open(secret, if (identical(kind, "recovery_key")) "recovery_key" else "password", custom_cipher()),
                       error = function(error) list(status = "blocked", code = .desktop_setup_restore_code_v1(error)))
    session$sendInputMessage("setup_restore_secret", list(value = ""))
    if (!identical(opened$status, "completed")) return(warn("Nicht geöffnet", .desktop_setup_restore_message_v1(opened$code)))
    mount(opened$result$mount)
    listed <- tryCatch(services$list(opened$result$mount), error = function(error) list(status = "blocked", code = .desktop_setup_restore_code_v1(error)))
    encrypted_list(listed); feedback(NULL)
  })
  candidates <- function() {
    value <- available(); rows <- list()
    for (row in value$plain) rows[[length(rows) + 1L]] <- c(row, list(root = value$plain_root, encrypted = FALSE))
    chosen <- custom()
    if (is.list(chosen) && identical(chosen$kind, "plain")) for (row in chosen$bundles) rows[[length(rows) + 1L]] <- c(row, list(root = chosen$root, encrypted = FALSE, folder = TRUE))
    listed <- encrypted_list()
    if (is.list(listed) && identical(listed$status, "listed")) for (row in listed$bundles) rows[[length(rows) + 1L]] <- c(row, list(root = mount(), encrypted = TRUE))
    rows
  }
  choice_id <- function(row) paste0(if (isTRUE(row$encrypted)) "crypt:" else if (isTRUE(row$folder)) "folder:" else "plain:", row$name)
  shiny::observeEvent(input$setup_restore_apply, {
    rows <- candidates(); picked <- Filter(function(row) identical(choice_id(row), input$setup_restore_pick), rows)
    if (!length(picked)) return(warn("Kein Backup gewählt", "Bitte ein Backup aus der Liste wählen."))
    row <- picked[[1L]]
    if (isTRUE(row$newer_version)) return(warn("Nicht übernehmbar", .desktop_setup_restore_message_v1("desktop_release_restore_newer_version")))
    if (!isTRUE(input$setup_restore_understood)) return(warn("Bitte bestätigen", "Bitte bestätigen, dass dieses Backup übernommen werden soll."))
    shiny::showModal(shiny::modalDialog(title = "Backup wird geprüft und übernommen",
      shiny::p("Portelyra prüft das Backup vollständig und spielt es zurück. Das dauert je nach Größe einige Minuten; bitte warten."),
      footer = NULL, easyClose = FALSE))
    # Erst das Fenster zeigen, dann rechnen.
    session$onFlushed(function() {
      bundle <- file.path(row$root, row$name)
      outcome <- tryCatch({
        checked <- services$check(bundle)
        if (!identical(checked$status, "valid")) stop(structure(list(message = "desktop_release_backup_integrity_invalid", call = NULL,
          code = "desktop_release_backup_integrity_invalid"), class = c("setup_restore_error", "error", "condition")))
        services$restore(bundle)
      }, error = function(error) list(status = "blocked", code = .desktop_setup_restore_code_v1(error)))
      shiny::removeModal(session = session)
      if (!identical(outcome$status, "restored")) { warn("Nicht übernommen", .desktop_setup_restore_message_v1(outcome$code)); return() }
      from_encrypted(isTRUE(row$encrypted)); close_mount()
      kept <- list(name = row$name, product_version = outcome$product_version, relocation = outcome$relocation, from_encrypted = isTRUE(row$encrypted))
      restored(kept)
      if (is.function(remember)) tryCatch(remember(kept), error = function(error) NULL)
      feedback(NULL); position("restore_followup")
    }, once = TRUE)
  })
  shiny::observeEvent(input$setup_restore_finish, {
    done <- restored(); if (!is.list(done)) return()
    steps <- list()
    schedule <- input$setup_restore_schedule
    if (identical(schedule, "daily") || identical(schedule, "twice")) {
      if (!isTRUE(input$setup_restore_schedule_consent)) return(warn("Zustimmung fehlt", "Für den Zeitplan bitte die Zustimmung ankreuzen."))
      steps[[length(steps) + 1L]] <- list(key = "schedule", action = "enable", times = if (identical(schedule, "twice")) list("07:00", "19:00") else list("07:00"))
    }
    password <- NULL
    if (identical(input$setup_restore_protection, "yes")) {
      password <- input$setup_restore_password
      if (!is.character(password) || nchar(password) < 10L) return(warn("Passwort zu kurz", "Mindestens 10 Zeichen."))
      if (!identical(password, input$setup_restore_password_repeat)) return(warn("Passwörter verschieden", "Die beiden Eingaben stimmen nicht überein."))
      if (!isTRUE(input$setup_restore_protection_understood)) return(warn("Bitte bestätigen", "Bitte bestätigen, dass ohne Passwort und Schlüssel die Daten verloren sind."))
      steps[[length(steps) + 1L]] <- list(key = "protection", action = "enable", keyring = isTRUE(input$setup_restore_keyring))
      # Der alte verschluesselte Ordner liegt unter dem Namen, den der neue Schutz braucht. Er gehoert allen Installationen dieses
      # Benutzerkontos: umbenennen nur nach ausdruecklicher Rueckfrage (Festlegung 13.11.2026), nie wenn ihn gerade eine nutzt (Kern).
      if (isTRUE(available()$encrypted)) {
        if (!isTRUE(input$setup_restore_set_aside_confirm)) return(warn("Rückfrage zum verschlüsselten Backup-Ordner", paste(
          "Für den neuen Passwortschutz muss der vorhandene verschlüsselte Backup-Ordner (backups.crypt) umbenannt werden. Bitte ausdrücklich",
          "bestätigen – oder den Passwortschutz jetzt mit „Nein“ überspringen und später einrichten.")))
        aside <- tryCatch(services$set_aside(), error = function(error) list(status = "blocked", code = .desktop_setup_restore_code_v1(error)))
        if (!identical(aside$status, "completed") && !identical(aside$code, "desktop_protection_backups_absent"))
          return(warn("Passwortschutz nicht eingerichtet", .desktop_setup_restore_message_v1(aside$code)))
        if (identical(aside$status, "completed")) restored(c(restored(), list(set_aside_as = aside$result$set_aside_as)))
      }
    }
    applied <- if (length(steps)) apply_followup(steps, password) else list()
    failed <- Filter(function(item) identical(item$status, "failed"), applied)
    if (length(failed)) return(warn("Nicht vollständig eingerichtet", sprintf("Schritt „%s“: %s", failed[[1L]]$key, failed[[1L]]$code)))
    results <- c(list(list(key = "restore", status = "restored")), lapply(applied, function(item) item[intersect(names(item), c("key", "status", "code"))]))
    finish(results, attr(applied, "recovery_key"))
  })
  body <- function(at, notice) {
    if (identical(at, "restore")) {
      value <- available(); rows <- candidates()
      choices <- stats::setNames(vapply(rows, choice_id, character(1L)), vapply(rows, .desktop_setup_restore_label_v1, character(1L)))
      return(shiny::tagList(
        shiny::h3("Aus einem vorhandenen Backup übernehmen"),
        shiny::p("Portelyra spielt ein Backup in diese neue Installation zurück. Das Backup selbst bleibt unverändert. Danach fragt die",
                 "Einrichtung nur noch Zeitplan und Passwortschutz."),
        shiny::div(class = "pl-field-group",
          shiny::h4(class = "pl-section-title", "Backups in einem anderen Ordner"),
          shiny::textInput("setup_restore_folder", "Ordner (vollständiger Pfad)", value = if (is.list(custom())) custom()$root else "", width = "100%",
                           placeholder = "/home/…/Backups oder /media/…/backups.crypt"),
          shiny::p(class = "pl-field-hint", "Etwa der Backup-Ordner auf einem USB-Stick, einer Sicherungsplatte oder eine Kopie von einem anderen Rechner –",
                   "der Ordner, der die einzelnen Backups enthält, oder ein verschlüsselter Ordner „backups.crypt“. Portelyra liest ihn nur."),
          shiny::actionButton("setup_restore_folder_read", "Ordner lesen", class = "btn-default")),
        if ((isTRUE(value$encrypted) || !is.null(custom_cipher())) && is.null(mount())) shiny::div(class = "pl-field-group",
          shiny::h4(class = "pl-section-title", "Verschlüsselte Backups öffnen"),
          shiny::p(class = "pl-field-hint", if (!is.null(custom_cipher())) paste0("Ordner: ", custom_cipher()) else "Ordner: der Backup-Ordner von Portelyra auf diesem Rechner."),
          shiny::radioButtons("setup_restore_kind", NULL, c("Mit dem Passwort" = "password", "Mit dem Wiederherstellungsschlüssel" = "recovery_key"), "password"),
          shiny::passwordInput("setup_restore_secret", "Passwort oder Wiederherstellungsschlüssel"),
          shiny::p(class = "pl-field-hint", "Nur nötig, um die Liste zu lesen; geöffnet wird nur lesend. Portelyra merkt sich die Eingabe nicht."),
          shiny::actionButton("setup_restore_open", "Öffnen", class = "btn-default")),
        if (length(rows)) shiny::div(class = "pl-field-group",
          shiny::radioButtons("setup_restore_pick", "Welches Backup?", choices, selected = character()),
          shiny::checkboxInput("setup_restore_understood", "Dieses Backup prüfen und in die neue Installation übernehmen.", FALSE))
        else shiny::p(class = "pl-field-hint", if ((isTRUE(value$encrypted) || !is.null(custom_cipher())) && is.null(mount())) "Die Liste erscheint nach dem Öffnen."
                      else "Im Backup-Ordner von Portelyra auf diesem Rechner liegen keine Backups. Liegen sie woanders, den Ordner oben nennen."),
        notice,
        shiny::div(class = "pl-editor-actions",
          if (length(rows)) shiny::actionButton("setup_restore_apply", "Prüfen und übernehmen", class = "btn-primary"),
          shiny::actionButton("setup_restore_back", "Zurück", class = "btn-default"))))
    }
    done <- restored()
    relocation <- if (is.list(done) && is.character(done$relocation) && done$relocation %in% names(DESKTOP_SETUP_RESTORE_RELOCATION_V1))
      DESKTOP_SETUP_RESTORE_RELOCATION_V1[[done$relocation]] else "–"
    shiny::tagList(
      .desktop_setup_panel_v1("Backup übernommen", paste0(done$name, " (Programmstand ", done$product_version, ") · Datenbestand ", relocation,
        ". Portfolios, Buchungen, Umfang, Steuer und Kursanbieter kommen aus dem Backup."), "positive"),
      shiny::h4(class = "pl-section-title", "Soll Portelyra von selbst aktualisieren?"),
      shiny::radioButtons("setup_restore_schedule", NULL, c("Nein, nur von Hand" = "manual", "Täglich um 07:00" = "daily", "Um 07:00 und 19:00" = "twice"), "manual"),
      shiny::checkboxInput("setup_restore_schedule_consent", "Ich stimme zu, dass Portelyra zu diesen Zeiten von selbst Kurse abruft und rechnet.", FALSE),
      shiny::h4(class = "pl-section-title", "Sollen Ihre Daten mit einem Passwort geschützt werden?"),
      shiny::radioButtons("setup_restore_protection", NULL, c("Ja" = "yes", "Nein" = "no"), if (isTRUE(from_encrypted())) "yes" else "no"),
      shiny::passwordInput("setup_restore_password", "Neues Passwort (mindestens 10 Zeichen)"),
      shiny::passwordInput("setup_restore_password_repeat", "Passwort wiederholen"),
      shiny::checkboxInput("setup_restore_keyring", "Mit der Anmeldung entsperren", TRUE),
      shiny::checkboxInput("setup_restore_protection_understood", "Verstanden: Ohne Passwort und Wiederherstellungsschlüssel sind die Daten verloren.", FALSE),
      if (isTRUE(available()$encrypted)) shiny::div(class = "pl-field-group",
        .desktop_setup_panel_v1("Rückfrage: vorhandener verschlüsselter Backup-Ordner", paste(
          "Auf diesem Benutzerkonto gibt es schon einen verschlüsselten Backup-Ordner (backups.crypt). Er gehört allen Portelyra-Installationen",
          "dieses Kontos – womöglich auch einer anderen, die ihn noch braucht. Für den neuen Passwortschutz würde er in „backups.crypt.alt-…“ umbenannt;",
          "sein Inhalt bleibt unverändert und öffnet weiter mit dem alten Passwort. Eine andere Installation, die ihn nutzt, fände ihre Backups",
          "danach nicht mehr. Ist er gerade von einer anderen Installation geöffnet, benennt Portelyra ihn nie um."), "warning"),
        shiny::checkboxInput("setup_restore_set_aside_confirm",
          "Ja, backups.crypt umbenennen – keine andere Portelyra-Installation auf diesem Konto braucht ihn noch.", FALSE)),
      notice,
      shiny::div(class = "pl-editor-actions", shiny::actionButton("setup_restore_finish", "Übernehmen und Portelyra starten", class = "btn-primary")))
  }
  list(body = body, available = available)
}
