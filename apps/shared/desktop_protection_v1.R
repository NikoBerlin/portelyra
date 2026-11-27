# Passwortschutz (#535, rc.396): Aufruf des Kerns und die Startseite „Portelyra entsperren“.
#
# Festlegungen (10.11.2026): Entsperren auf einer eigenen lokalen Startseite vor den Apps; ein Wiederherstellungsschluessel
# fuer Daten und Backups; Passwoerter nur ueber eine Pipe an den Kern (system2(input = ...) schriebe eine Temporaerdatei, rc.389).

DESKTOP_PROTECTION_MESSAGES_V1 <- c(
  desktop_protection_password_wrong = "Das Passwort stimmt nicht.",
  desktop_protection_wait = "Nach mehreren falschen Eingaben bitte kurz warten.",
  desktop_protection_mount_failed = "Der verschlüsselte Ordner ließ sich nicht einhängen. Ist gocryptfs installiert und FUSE verfügbar?",
  desktop_protection_tool_missing = "Für den Passwortschutz fehlt gocryptfs. Unter Linux: Paket „gocryptfs“ installieren.",
  desktop_protection_runtime_dir_invalid = "Der Ordner für die entsperrte Ansicht (/run/user/…) ist nicht nutzbar.",
  desktop_protection_recovery_key_invalid = "Der Wiederherstellungsschlüssel stimmt nicht.",
  desktop_protection_password_too_short = "Das neue Passwort ist zu kurz (mindestens 10 Zeichen).",
  desktop_protection_password_mismatch = "Die beiden neuen Passwörter stimmen nicht überein.",
  desktop_protection_state_invalid = "Der Zustand des Passwortschutzes ist nicht lesbar.",
  desktop_protection_backup_required = "Vor dem Löschen des Klartexts bitte ein Backup im verschlüsselten Backup-Ordner anlegen.",
  desktop_protection_copy_mismatch = "Die verschlüsselte Kopie stimmt nicht mit dem Klartext überein; nichts wurde gelöscht.",
  desktop_protection_already_enabled = "Der Passwortschutz ist schon eingerichtet.",
  desktop_protection_confirmation_required = "Bitte zuerst bestätigen.",
  desktop_protection_no_data_space = "Es gibt noch keinen Datenraum. Bitte zuerst den Datenraum anlegen.",
  desktop_protection_keyring_unavailable = "Der Schlüsselbund ist nicht erreichbar oder enthält das Passwort nicht – bitte mit dem Passwort entsperren.",
  desktop_protection_keyring_stale = "Das Passwort im Schlüsselbund passt nicht mehr – bitte mit dem Passwort entsperren und „Mit der Anmeldung entsperren“ neu einschalten.",
  desktop_protection_disk_space = "Zum Erneuern des Schlüssels fehlt Platz: Alte und neue Ordner liegen zeitweise nebeneinander.",
  desktop_protection_rekey_pending = "Das Erneuern des Schlüssels ist angefordert; entsperrt wird dafür auf der Startseite.",
  desktop_protection_password_after_sleep = "Nach dem Ruhezustand wird mit dem Passwort entsperrt.",
  desktop_protection_unreadable_stale = "Der Befund hat sich seit der Vorschau geändert.",
  desktop_protection_unreadable_not_quarantinable = "Darunter ist ein unlesbarer Eintrag, der weder ein abgeleiteter Lauf noch ein unfertiger Zwischenstand ist; ihn nimmt Portelyra nicht in Quarantäne.",
  desktop_protection_unreadable_none = "Es gibt keinen unlesbaren Eintrag mehr.",
  desktop_protection_unreadable_request_invalid = "Der Auftrag für die Quarantäne war nicht lesbar und wurde verworfen.",
  desktop_protection_backups_folder_exists = paste("Es gibt schon einen verschlüsselten Backup-Ordner (backups.crypt), etwa von einer früheren",
    "Einrichtung. Bitte umbenennen oder verschieben; er lässt sich mit dem alten Passwort oder Wiederherstellungsschlüssel weiter öffnen."))

desktop_protection_message_v1 <- function(code, detail = NULL) {
  text <- if (is.character(code) && length(code) == 1L && code %in% names(DESKTOP_PROTECTION_MESSAGES_V1)) DESKTOP_PROTECTION_MESSAGES_V1[[code]]
    else "Der Passwortschutz meldet einen Fehler."
  if (identical(code, "desktop_protection_wait") && is.list(detail) && is.numeric(detail$seconds))
    text <- sprintf("Nach mehreren falschen Eingaben bitte %d Sekunden warten.", as.integer(detail$seconds))
  paste0(text, " (", code, ")")
}

# Ist der Einhaengeordner gerade eingehaengt? Liest nur /proc/self/mountinfo (kein Python je Abfrage). Nicht feststellbar zaehlt als
# eingehaengt: Eine Warnung ohne Befund waere schlimmer als keine.
desktop_protection_mounted_v1 <- function(path, mountinfo = "/proc/self/mountinfo") {
  lines <- tryCatch(readLines(mountinfo, warn = FALSE), error = function(error) NULL)
  if (!length(lines)) return(TRUE)
  target <- gsub(" ", "\\040", path, fixed = TRUE)
  any(vapply(strsplit(lines, " ", fixed = TRUE), function(parts) length(parts) >= 5L && identical(parts[[5L]], target), logical(1L)))
}

# Bestand weg bei laufender App (#587: nie ohne Vorwarnung). Jede Sitzung prueft alle
# paar Sekunden. Fehlt die Einhaengung, wird der leere Ordner versiegelt (weitere Schreibvorgaenge scheitern laut) und ein Dialog erscheint.
# Nach dem Ruhezustand fragt er nach dem Passwort, und die Seite bleibt stehen, damit angefangene Eingaben erhalten bleiben. Sonst bietet er
# "Wieder verbinden" und laedt danach neu. Ist der Bestand wieder da, auch aus einer anderen App, schliesst er sich von selbst.
desktop_protection_guard_v1 <- function(session, project_root, home, mount, interval_ms = 3000L, mounted = desktop_protection_mounted_v1,
                                        runner = NULL, reload = function() session$reload()) {
  lost <- shiny::reactiveVal(FALSE)
  slept <- FALSE
  enter <- shiny::tags$script(shiny::HTML(paste0(
    "setTimeout(function(){var f=document.getElementById('pl_protection_password');if(!f)return;f.focus();",
    "f.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();",
    "Shiny.setInputValue('pl_protection_password',f.value);document.getElementById('pl_protection_unlock').click();}});},200);")))
  dialog <- function(problem = NULL, ask = slept) shiny::modalDialog(
    title = if (slept) "Portelyra war im Ruhezustand gesperrt" else "Ihr Datenbestand ist nicht verbunden",
    if (slept) shiny::p("Bitte geben Sie Ihr Passwort ein, um weiterzuarbeiten. Ihre Eingaben auf dieser Seite bleiben erhalten.")
    else shiny::tagList(
      shiny::p("Portelyra kann Ihren verschlüsselten Bestand gerade nicht lesen. Ihre gespeicherten Daten sind davon nicht betroffen."),
      shiny::p("Bitte geben Sie jetzt nichts ein: Bis zum Wiederverbinden lässt sich nichts speichern.")),
    if (!is.null(problem)) shiny::p(role = "alert", shiny::strong(problem)),   # laeuft ausserhalb der Hülle der Apps, ohne deren Bausteine
    if (ask) shiny::tagList(shiny::passwordInput("pl_protection_password", "Passwort", width = "100%"), enter),
    footer = if (ask) shiny::actionButton("pl_protection_unlock", "Entsperren", class = "btn-primary")
             else shiny::actionButton("pl_protection_reconnect", "Wieder verbinden", class = "btn-primary"),
    easyClose = FALSE, fade = FALSE)
  back <- function() { shiny::removeModal(session = session); lost(FALSE); if (!slept) reload(); slept <<- FALSE }
  shiny::observe({
    shiny::invalidateLater(interval_ms, session)
    here <- isTRUE(mounted(mount)); gone <- shiny::isolate(lost())
    if (here && gone) back()
    if (!here && !gone) {
      state <- desktop_protection_cli_v1(project_root, home, "seal-if-lost", runner = runner)
      slept <<- isTRUE(state$result$sleep_note$locked)
      lost(TRUE)
      shiny::showModal(dialog(), session = session)
    }
  })
  shiny::observeEvent(session$input$pl_protection_reconnect, {
    result <- desktop_protection_cli_v1(project_root, home, "unlock-keyring", runner = runner)
    if (identical(result$status, "completed") && isTRUE(result$result$unlocked)) back()
    else shiny::showModal(dialog("Über den Schlüsselbund ließ sich nicht entsperren. Bitte geben Sie Ihr Passwort ein.", ask = TRUE), session = session)
  }, ignoreInit = TRUE)
  shiny::observeEvent(session$input$pl_protection_unlock, {
    password <- session$input$pl_protection_password
    shiny::updateTextInput(session, "pl_protection_password", value = "")
    result <- desktop_protection_cli_v1(project_root, home, "unlock", list(password = if (is.character(password)) password else ""), runner = runner)
    if (identical(result$status, "completed") && isTRUE(result$result$unlocked)) {
      desktop_protection_cli_v1(project_root, home, "catch-up-after-sleep", runner = runner)   # ausgefallene Zeitlaeufe holt Portelyra selbst nach
      back()
    }
    else shiny::showModal(dialog(desktop_protection_message_v1(result$code, result$detail), ask = TRUE), session = session)
  }, ignoreInit = TRUE)
  invisible(NULL)
}

# Ein Aufruf des Kerns. `payload` ohne "home"; Antwort: list(status, result | code, detail).
desktop_protection_cli_v1 <- function(project_root, home, command, payload = list(), runner = NULL) {
  json <- as.character(jsonlite::toJSON(c(list(home = home), payload), auto_unbox = TRUE, null = "null"))
  if (is.function(runner)) return(runner(command, json))
  python <- Sys.which("python3"); cli <- file.path(project_root, "scripts", "desktop_protection.py")
  if (!nzchar(python) || !file.exists(cli)) return(list(status = "blocked", code = "desktop_protection_tool_missing"))
  out <- tempfile("pl-protection-", fileext = ".json")
  on.exit(unlink(out), add = TRUE)
  line <- paste(shQuote(python), "-B -E -s", shQuote(cli), shQuote(command), ">", shQuote(out), "2>/dev/null")
  connection <- pipe(line, open = "wb")
  tryCatch({ writeBin(charToRaw(enc2utf8(json)), connection); close(connection) }, error = function(error) try(close(connection), silent = TRUE))
  output <- if (file.exists(out)) readLines(out, warn = FALSE, encoding = "UTF-8") else character()
  parsed <- tryCatch(jsonlite::fromJSON(utils::tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
  if (!is.list(parsed) || !is.character(parsed$status)) list(status = "blocked", code = "desktop_protection_state_invalid") else parsed
}

# Die Startseite. `on_unlocked()` laeuft nach erfolgreichem Entsperren (der Start beendet dann die Seite und startet die Apps). Mit `rekey`
# (#552, in der Karte angefordert) steht oben der Abschnitt "Schluessel erneuern": Er laeuft hier, bevor etwas anderes den Bestand oeffnet.
desktop_protection_unlock_ui_v1 <- function(css = "", rekey = FALSE) shiny::fluidPage(
  shiny::tags$head(shiny::tags$meta(name = "viewport", content = "width=device-width, initial-scale=1"),
                   shiny::tags$meta(name = "referrer", content = "no-referrer"), shiny::tags$title("Portelyra entsperren"),
                   shiny::tags$style(shiny::HTML(css))),
  shiny::div(class = "pl-unlock", style = "max-width:34rem;margin:4rem auto;padding:0 1rem;",
    shiny::h2("Portelyra entsperren"),
    if (isTRUE(rekey)) shiny::div(id = "unlock-rekey", style = "margin-bottom:2rem;",
      shiny::h3("Schlüssel erneuern"),
      shiny::p("Sie haben in den Einstellungen das Erneuern des Schlüssels angestoßen. Portelyra verschlüsselt Datenbestand und Backups mit",
               "einem neuen Hauptschlüssel, prüft jede Datei und zeigt danach den neuen Wiederherstellungsschlüssel. Das dauert je nach Größe",
               "einige Minuten; währenddessen bitte diese Seite offen lassen."),
      shiny::passwordInput("rekey_current", "Bisheriges Passwort", width = "100%"),
      shiny::passwordInput("rekey_new", "Neues Passwort (mindestens 10 Zeichen; darf das bisherige sein)", width = "100%"),
      shiny::passwordInput("rekey_repeat", "Neues Passwort wiederholen", width = "100%"),
      shiny::checkboxInput("rekey_confirm", "Ich verstehe: Der bisherige Wiederherstellungsschlüssel gilt danach nicht mehr.", FALSE),
      shiny::actionButton("rekey_submit", "Schlüssel erneuern und entsperren", class = "btn-primary"),
      shiny::uiOutput("rekey_result"),
      shiny::p(class = "pl-field-hint", style = "margin-top:1rem;", "Nur entsperren (unten) bricht das Erneuern ab; es lässt sich in den Einstellungen erneut anstoßen.")),
    shiny::p("Ihr Datenbestand ist verschlüsselt. Nach dem Entsperren startet Portelyra wie gewohnt. Er bleibt entsperrt, bis Sie sich am Rechner abmelden, ihn herunterfahren oder er in den Ruhezustand geht."),
    shiny::passwordInput("unlock_password", "Passwort", width = "100%"),
    shiny::actionButton("unlock_submit", "Entsperren", class = if (isTRUE(rekey)) "btn-default" else "btn-primary"),
    shiny::uiOutput("unlock_state"),
    shiny::tags$details(id = "unlock-recover", style = "margin-top:2rem;",
      shiny::tags$summary("Passwort vergessen?"),
      shiny::p("Mit dem Wiederherstellungsschlüssel, den Portelyra beim Einrichten einmal angezeigt hat, setzen Sie ein neues Passwort. Der",
               "Schlüssel öffnet alle Daten ohne Passwort – bewahren Sie ihn so sicher auf wie die Daten selbst."),
      shiny::textInput("unlock_recovery_key", "Wiederherstellungsschlüssel", width = "100%", placeholder = "acht Gruppen zu acht Zeichen"),
      shiny::passwordInput("unlock_new_password", "Neues Passwort (mindestens 10 Zeichen)", width = "100%"),
      shiny::passwordInput("unlock_new_repeat", "Neues Passwort wiederholen", width = "100%"),
      shiny::actionButton("unlock_recover", "Neues Passwort setzen und entsperren", class = "btn-default"))))

desktop_protection_unlock_server_v1 <- function(project_root, home, on_unlocked, runner = NULL, rekey = FALSE) function(input, output, session) {
  state <- shiny::reactiveVal(NULL)
  rekeyed <- shiny::reactiveVal(NULL)   # list(key, password) nach dem Erneuern, bis "aufgeschrieben"
  rekey_feedback <- shiny::reactiveVal(NULL)
  call <- function(command, payload = list()) desktop_protection_cli_v1(project_root, home, command, payload, runner)
  panel <- function(title, copy, tone) if (exists("portelyra_status_panel", mode = "function")) portelyra_status_panel(title, copy, tone = tone)
    else shiny::div(shiny::strong(title), shiny::p(copy))
  output$unlock_state <- shiny::renderUI({ value <- state(); if (is.null(value)) NULL else panel(value$title, value$copy, value$tone) })
  unlock <- function(password, cancel_rekey = FALSE) {
    result <- call("unlock", list(password = password))
    if (identical(result$status, "completed") && isTRUE(result$result$unlocked)) {
      # Nur entsperrt, obwohl das Erneuern angefordert war: Anforderung zurueckziehen (Festlegung 11.11.2026), sonst sperrte sie den Schluesselbund.
      if (isTRUE(cancel_rekey)) call("cancel-rekey")
      state(list(title = "Entsperrt", copy = paste0("Portelyra startet; die App „Daten“ öffnet sich gleich in einem neuen Tab. Diesen Tab können Sie schließen.",
        if (isTRUE(cancel_rekey)) " Das Erneuern des Schlüssels ist abgebrochen; es lässt sich in den Einstellungen erneut anstoßen." else ""), tone = "positive"))
      on_unlocked()
    } else state(list(title = "Nicht entsperrt", copy = desktop_protection_message_v1(result$code, result$detail), tone = "warning"))
  }
  shiny::observeEvent(input$unlock_submit, {
    password <- input$unlock_password
    shiny::updateTextInput(session, "unlock_password", value = "")
    if (!is.character(password) || !nzchar(password)) return(state(list(title = "Passwort fehlt", copy = "Bitte das Passwort eingeben.", tone = "warning")))
    unlock(password, cancel_rekey = isTRUE(rekey))
  })
  shiny::observeEvent(input$unlock_recover, {
    key <- input$unlock_recovery_key; new <- input$unlock_new_password; repeat_value <- input$unlock_new_repeat
    for (id in c("unlock_new_password", "unlock_new_repeat")) shiny::updateTextInput(session, id, value = "")
    result <- call("recover", list(recovery_key = key, new = new, `repeat` = repeat_value))
    if (!identical(result$status, "completed"))
      return(state(list(title = "Kein neues Passwort", copy = desktop_protection_message_v1(result$code, result$detail), tone = "warning")))
    shiny::updateTextInput(session, "unlock_recovery_key", value = "")
    unlock(new, cancel_rekey = isTRUE(rekey))
  })
  # Schluessel erneuern (#552): erst der neue Wiederherstellungsschluessel, dann - nach "aufgeschrieben" - entsperren mit dem neuen Passwort.
  output$rekey_result <- shiny::renderUI({
    done <- rekeyed(); note <- rekey_feedback()
    if (is.null(done)) return(if (is.list(note)) panel(note$title, note$copy, note$tone) else NULL)
    shiny::div(style = "margin-top:1rem;",
      shiny::h4("Ihr neuer Wiederherstellungsschlüssel – nur jetzt sichtbar"),
      shiny::tags$pre(style = "font-size:1.15rem;user-select:all;", done$key),
      panel("Bitte aufschreiben und sicher verwahren", paste("Der bisherige Schlüssel gilt nicht mehr. Ältere Kopien der alten Ordner, etwa in Back In",
        "Time, öffnen weiter mit dem alten Passwort oder Schlüssel, bis sie dort gelöscht sind. Die alten Ordner entfernen Sie nach dem ersten",
        "Backup in den Einstellungen unter „Sicherheit und Speicher“ → „Passwortschutz“."), "warning"),
      shiny::checkboxInput("rekey_noted", "Ich habe den neuen Wiederherstellungsschlüssel aufgeschrieben.", FALSE),
      shiny::actionButton("rekey_continue", "Weiter: entsperren und starten", class = "btn-primary"))
  })
  shiny::observeEvent(input$rekey_submit, {
    current <- input$rekey_current; new <- input$rekey_new; repeat_value <- input$rekey_repeat
    for (id in c("rekey_current", "rekey_new", "rekey_repeat")) shiny::updateTextInput(session, id, value = "")
    if (!isTRUE(input$rekey_confirm)) return(rekey_feedback(list(title = "Bitte bestätigen", copy = "Bitte bestätigen, dass der bisherige Schlüssel danach nicht mehr gilt.", tone = "warning")))
    result <- call("rekey", list(current = current, new = new, `repeat` = repeat_value, confirmed = TRUE))
    if (!identical(result$status, "completed")) return(rekey_feedback(list(title = "Nicht erneuert", copy = desktop_protection_message_v1(result$code, result$detail), tone = "warning")))
    rekeyed(list(key = result$result$recovery_key, password = new))
  })
  shiny::observeEvent(input$rekey_continue, {
    done <- rekeyed(); if (is.null(done)) return()
    if (!isTRUE(input$rekey_noted)) return(rekey_feedback(list(title = "Bitte bestätigen", copy = "Bitte bestätigen, dass der neue Schlüssel aufgeschrieben ist.", tone = "warning")))
    password <- done$password; rekeyed(NULL)
    unlock(password)
  })
}

# Start-Token fuer die Seiten vor den Apps (#563, Festlegung 13.11.2026): wie bei den Apps (scripts/portelyra_desktop.R)
# schliesst eine Sitzung ohne genau dieses Token in der Adresse, bevor die Seite etwas zeigt oder tut. 127.0.0.1 erreicht jedes
# Benutzerkonto am Rechner; ohne Token koennte ein anderes Konto hier Passwoerter probieren oder beim ersten Start einen eigenen Schutz
# einrichten. `token` NULL laesst die Seite offen (nur fuer Tests mit testServer).
desktop_page_token_valid_v1 <- function(token) is.character(token) && length(token) == 1L && !is.na(token) && grepl("^dlp_[0-9a-f]{64}$", token)
desktop_page_url_v1 <- function(port, token = NULL) paste0("http://127.0.0.1:", port, if (desktop_page_token_valid_v1(token)) paste0("?launch_token=", token) else "")
# Zugang je Oeffnen (#570, rc.433; neu je Oeffnen statt eines Zugangs fuer die ganze Sitzung). Jeder
# Start und jedes Wiederoeffnen bekommt einen neuen Zugang, der vorige verfaellt. Der Start fuehrt dafuer im Sperrordner access.json (0600):
# nur Fingerabdruecke (SHA-256), nie den Zugang selbst. Apps und Seiten pruefen jeden neuen Seitenaufruf dagegen: "valid" (der aktuelle),
# "expired" (ein abgeloester: Hinweis zeigen, sonst nichts), "invalid" (alles andere: schliessen). Im aktuellen Tab bleiben Neuladen und der
# Wechsel zwischen den Apps moeglich, weil sie den aktuellen Zugang weitertragen. Ohne Datei (Tests mit testServer, Seiten ohne Sitzung)
# gilt das feste Token wie bisher. Den Pfad nennt PORTELYRA_ACCESS_FILE_INTERNAL; der Start setzt sie vor dem Forken.
desktop_access_token_v1 <- function(search) {
  if (!is.character(search) || length(search) != 1L || is.na(search)) return(NULL)
  match <- regmatches(search, regexec("^\\?launch_token=(dl[sp]_[0-9a-f]{64})$", search))[[1L]]
  if (length(match) == 2L) match[[2L]] else NULL
}
desktop_access_fingerprint_v1 <- function(token) digest::digest(enc2utf8(token), algo = "sha256", serialize = FALSE)
desktop_access_check_v1 <- function(search, token = NULL, file = Sys.getenv("PORTELYRA_ACCESS_FILE_INTERNAL", unset = "")) {
  presented <- desktop_access_token_v1(search)
  if (is.null(presented)) return("invalid")
  if (nzchar(file) && file.exists(file)) {
    if (nzchar(Sys.readlink(file))) return("invalid")
    access <- tryCatch(jsonlite::fromJSON(file, simplifyVector = TRUE), error = function(error) NULL)
    if (!is.list(access) || !is.character(access$current) || length(access$current) != 1L) return("invalid")
    fingerprint <- desktop_access_fingerprint_v1(presented)
    if (identical(fingerprint, access$current)) return("valid")
    if (fingerprint %in% as.character(unlist(access$retired))) return("expired")
    return("invalid")
  }
  if (is.character(token) && length(token) == 1L && identical(presented, token)) "valid" else "invalid"
}
desktop_access_expired_ui_v1 <- function() shiny::modalDialog(
  title = "Zugang abgelaufen",
  "Portelyra wurde seither neu geöffnet; dieser Zugang gilt nicht mehr. Bitte Portelyra über den Starter öffnen (\u201ePortelyra\u201c im Anwendungsmenü).",
  footer = NULL, easyClose = FALSE)
# Ohne Zugang in der Adresse (#580: Lesezeichen, Start ohne Browser): Hinweis statt grauer Seite; die Sitzung bleibt ohne Inhalt.
desktop_access_missing_ui_v1 <- function() shiny::modalDialog(
  title = "Portelyra ohne Zugang geöffnet",
  paste("Diese Adresse braucht den Zugang, den der Starter beim Öffnen mitgibt. Bitte Portelyra über den Starter öffnen",
        "(\u201ePortelyra\u201c im Anwendungsmenü). Im Terminal nennt \u201estart --no-browser\u201c die Adresse samt Zugang."),
  footer = NULL, easyClose = FALSE)
# Fuer Apps und Seiten gleich: der aktuelle Zugang fuehrt hinein, ein abgeloester zeigt nur den Hinweis, eine Adresse ganz ohne Zugang
# ihren Hinweis (#580); ein falscher Zugang schliesst.
desktop_access_gate_v1 <- function(check, session, enter, search = NULL) {
  if (identical(check, "valid")) return(enter())
  if (identical(check, "expired")) return(shiny::showModal(desktop_access_expired_ui_v1(), session = session))
  if (is.character(search) && length(search) == 1L && !grepl("launch_token=", search, fixed = TRUE))
    return(shiny::showModal(desktop_access_missing_ui_v1(), session = session))
  session$close()
}
desktop_page_guard_v1 <- function(server, token) {
  if (is.null(token)) return(server)
  if (!desktop_page_token_valid_v1(token)) stop("desktop_page_token_invalid", call. = FALSE)
  function(input, output, session) {
    authorized <- FALSE
    shiny::observe({
      search <- session$clientData$url_search
      shiny::req(is.character(search), length(search) == 1L, !is.na(search))
      shiny::isolate(if (!authorized) {
        authorized <<- TRUE
        desktop_access_gate_v1(desktop_access_check_v1(search, token), session, function() server(input, output, session), search)
      })
    })
  }
}

# Fuer das Startskript: Ist der Schutz an und gesperrt, erst ueber den Schluesselbund entsperren (#553), sonst die Startseite auf `port`
# zeigen, bis entsperrt ist. Ohne Schutz sofort zurueck. Ein angefordertes Erneuern (#552) zeigt immer die Seite.
desktop_protection_unlock_blocking_v1 <- function(project_root, home, port, open_browser = NULL, css = "", token = NULL) {
  status <- desktop_protection_cli_v1(project_root, home, "status")
  if (!identical(status$status, "completed") || !isTRUE(status$result$enabled) || isTRUE(status$result$unlocked)) return(invisible(status))
  if (isTRUE(status$result$keyring_unlock) && !isTRUE(status$result$rekey_requested)) {
    keyring <- desktop_protection_cli_v1(project_root, home, "unlock-keyring")
    if (identical(keyring$status, "completed") && isTRUE(keyring$result$unlocked)) return(invisible(keyring))
  }
  rekey <- isTRUE(status$result$rekey_requested)
  app <- shiny::shinyApp(desktop_protection_unlock_ui_v1(css, rekey = rekey), desktop_page_guard_v1(
    desktop_protection_unlock_server_v1(project_root, home, function() later::later(function() shiny::stopApp(TRUE), 1.5), rekey = rekey), token))
  if (is.function(open_browser)) later::later(function() open_browser(desktop_page_url_v1(port, token)), 0.5)
  shiny::runApp(app, host = "127.0.0.1", port = port, launch.browser = FALSE, quiet = TRUE)
  invisible(desktop_protection_cli_v1(project_root, home, "status"))
}
