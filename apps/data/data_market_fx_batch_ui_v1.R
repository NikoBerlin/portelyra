# Resolver receives server-owned catalog snapshots and callbacks, never display-name authority.
data_market_fx_batch_targets_v1 <- function(batch, inventory, resolve_asset, resolve_mapping, recover_promotion) {
  if (!is.list(batch$items) || !is.list(inventory$rows) ||
      !all(vapply(list(resolve_asset, resolve_mapping, recover_promotion), is.function, logical(1L))))
    data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
  lapply(batch$items, function(item) {
    if (!is.character(item$source_currency) || length(item$source_currency) != 1L ||
        !is.character(item$target_currency) || length(item$target_currency) != 1L ||
        !grepl("^[A-Z]{3}$", item$source_currency) || !grepl("^[A-Z]{3}$", item$target_currency) ||
        !identical(item$route, paste0(item$source_currency, "→", item$target_currency)))
      data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    if (identical(item$kind, "fx")) return(list(kind = "fx", public_item = item,
      source_currency = item$source_currency, target_currency = item$target_currency))
    if (!identical(item$kind, "market") || is.null(item$consumer_ref))
      data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    matches <- Filter(function(row) identical(row$asset_ref, item$consumer_ref), inventory$rows)
    if (length(matches) != 1L || is.null(matches[[1L]]$mapping_ref))
      data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    row <- matches[[1L]]
    asset_id <- resolve_asset(row$asset_ref)
    mapping <- resolve_mapping(row$mapping_ref)
    # Seit rc.394 jeder Anbieter mit Tageskursen; das prueft schon die Zuordnung (resolve_mapping).
    if (!identical(mapping$asset_id, asset_id) ||
        !identical(mapping$provider_currency, item$source_currency))
      data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    promotion <- recover_promotion(mapping$mapping_id)
    if (!is.list(promotion) || !identical(promotion$mapping_id, mapping$mapping_id))
      data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    list(kind = "market", public_item = item, listing_ref = promotion$listing_ref, mapping = mapping,
      promotion_binding = list(listing_ref = promotion$listing_ref, listing_fingerprint = promotion$listing_fingerprint,
        mapping_id = promotion$mapping_id, mapping_revision = as.integer(promotion$mapping_revision), mapping_fingerprint = promotion$mapping_fingerprint))
  })
}

data_market_fx_batch_progress_frame_v1 <- function(progress) {
  if (is.null(progress) || !length(progress$items)) return(data.frame())
  labels <- c(pending = "Wartend · noch nicht abgerufen", staged = "Vorgemerkt · Prüfung offen",
    provider_call_started = "Abrufausgang unbekannt · Abgleich erforderlich", publish_started = "Ausgang des Schreibvorgangs unbekannt · Abgleich erforderlich",
    published = "Veröffentlicht", failed = "Fehler belegt · abgeglichen · kein Wiederholungsabruf")
  do.call(rbind, lapply(progress$items, function(row) data.frame(Bereich = as.character(row$ordinal), Art = row$kind,
    Verbraucher = row$consumer, Route = row$route, Von = row$start_date, Bis = row$end_date,
    Status = unname(labels[[row$status]]), Fehlernachweis = if (is.null(row$failure_code)) "—" else row$failure_code,
    check.names = FALSE, stringsAsFactors = FALSE)))
}

# Selection is authority over exact persisted ordinals, never over display names.
data_market_fx_batch_review_ordinals_v1 <- function(selection, progress) {
  if (!is.character(selection) || !length(selection) || anyNA(selection) || anyDuplicated(selection) ||
      any(!grepl("^[1-9][0-9]{0,4}$", selection)) || is.null(progress))
    data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
  available <- vapply(Filter(function(row) identical(row$status, "staged"), progress$items), `[[`, integer(1L), "ordinal")
  ordinals <- sort(as.integer(selection))
  if (!all(ordinals %in% available)) data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
  ordinals
}

data_market_fx_batch_pending_rows_v1 <- function(preview, progress) {
  if (!is.null(progress)) return(Filter(function(row) identical(row$status, "pending"), progress$items))
  lapply(seq_along(preview$items), function(i) c(list(ordinal=as.integer(i), status="pending"), preview$items[[i]]))
}

data_market_fx_batch_fetch_ordinals_v1 <- function(selection, preview, progress) {
  if (!is.character(selection) || !length(selection) || anyNA(selection) || anyDuplicated(selection) ||
      any(!grepl("^[1-9][0-9]{0,4}$", selection)) || is.null(preview))
    data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
  available <- vapply(data_market_fx_batch_pending_rows_v1(preview, progress), `[[`, integer(1L), "ordinal")
  ordinals <- sort(as.integer(selection))
  if (!all(ordinals %in% available)) data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
  ordinals
}

# Focus only the review display; the complete candidate and every day remain intact.
data_market_fx_batch_review_focus_v1 <- function(item, frame) {
  selected <- if (item$kind == "market") vapply(item$public_review$series, function(row)
    row$candidate_day_status == "source_gap" || is.null(row$effective_close_decimal) ||
      row$comparison_status == "correction_candidate" || any(unlist(row$warning_codes) %in% c(
        "market_review_corporate_action_pending", "market_review_observation_on_non_trading_day",
        "market_review_current_observation_retained")), logical(1L))
    else vapply(item$daily_rows, function(row) row$day_status == "source_gap", logical(1L))
  frame[selected, , drop=FALSE]
}

data_market_fx_batch_table_v1 <- function(frame) shiny::div(class="pl-table-wrap",
  shiny::tags$table(class="table table-striped",
    shiny::tags$thead(shiny::tags$tr(lapply(names(frame),shiny::tags$th))),
    shiny::tags$tbody(lapply(seq_len(nrow(frame)),function(i)
      shiny::tags$tr(lapply(frame[i,,drop=FALSE],function(v)shiny::tags$td(as.character(v))))))))

data_market_fx_batch_server_v1 <- function(input, output, session, service, resolve_targets, now_utc, notice, on_publication) {
  preview <- shiny::reactiveVal(NULL); progress <- shiny::reactiveVal(NULL); review <- shiny::reactiveVal(NULL)
  confirmed <- shiny::reactiveVal(FALSE); confirmed_ordinals <- shiny::reactiveVal(NULL)
  attempted <- shiny::reactiveVal(FALSE); executions <- shiny::reactiveVal(list())
  review_generation <- shiny::reactiveVal(0L); publication_ack <- shiny::reactiveVal(NULL)
  write_pending <- shiny::reactiveVal(FALSE); needs_reload <- shiny::reactiveVal(FALSE)
  unknown <- function() any(vapply(progress()$items, function(row)
    row$status %in% c("provider_call_started", "publish_started"), logical(1L)))
  require_ready <- function(recovery = FALSE) {
    if (isTRUE(needs_reload()) || (!recovery && unknown()))
      data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
  }
  status <- shiny::reactiveVal("Noch kein ausführbarer Sammelabruf vorbereitet. Abruf und Veröffentlichung bleiben getrennt.")
  expire <- function(now) format(as.POSIXct(now, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") + 600,
                                 "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  reset <- function() {
    had_grant <- isTRUE(confirmed()); had_review <- !is.null(review())
    confirmed(FALSE); confirmed_ordinals(NULL); publication_ack(NULL); review(NULL); service$invalidate()
    for (id in c("batch_fetch_confirm", "batch_publish_confirm", "batch_recover_confirm"))
      if (isTRUE(input[[id]])) shiny::updateCheckboxInput(session, id, value = FALSE)
    if (had_grant) status("Abrufbestätigung widerrufen · geänderte Auswahl vor einem Abruf erneut bestätigen.")
    else if (had_review) status("Prüfung verworfen · Auswahl oder Einstellungen geändert. Vorgemerkte Ergebnisse erneut prüfen; kein Abruf nötig.")
  }
  safe <- function(operation) tryCatch(operation(), error = function(error) {
    if (isTRUE(write_pending())) needs_reload(TRUE)
    write_pending(FALSE); reset()
    code <- tryCatch(data_market_fx_batch_abort_v1(error$code), error = function(safe_error) safe_error$code)
    next_step <- if (needs_reload()) "Ausgang zunächst durch Laden des gespeicherten Sammelabrufs prüfen; weitere Aktionen bleiben gesperrt."
      else "Keine aktuelle Freigabe. Auswahl und Bestätigung vor einer neuen Aktion prüfen."
    status(paste("Aktion blockiert:", code, "· keine automatische Wiederholung.", next_step))
    notice(list(tone = "error", title = "Sammelabruf für Kurse und FX blockiert", copy = status()))
    invisible(NULL)
  })
  accept <- function(value) {
    force(value) # execute/read before invalidating any in-memory grant (R promises)
    reset(); write_pending(FALSE); needs_reload(FALSE)
    progress(value); attempted(TRUE); preview(service$fetch_preview())
    status(paste(sum(vapply(value$items, function(row) row$status == "published", logical(1L))), "von", value$item_count,
      "Bereichen veröffentlicht ·", sum(vapply(value$items, function(row) row$status == "staged", logical(1L))),
      "vorgemerkt ·", sum(vapply(value$items, function(row) row$status == "pending", logical(1L))),
      "wartend · nichts still verworfen · kein erneuter Abruf bei Veröffentlichung."))
    notice(list(tone="neutral", title="Sammelabruf für Kurse und FX aktualisiert", copy=status()))
    invisible(value)
  }
  prepare <- function(batch) {
    require_ready()
    if (!is.null(progress()) && !progress()$status %in% c("published", "completed_with_failures"))
      data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    reset(); preview(NULL); progress(NULL); attempted(FALSE)
    if (!identical(batch$status, "ready_for_confirmation")) return(invisible(NULL))
    value <- service$prepare(batch, resolve_targets(batch), now_utc())
    preview(value)
    status("Private Ziele und Bereiche gebunden · bisher kein Abruf beim Kursanbieter. Genau diese sichtbare Vorschau bestätigen.")
    invisible(value)
  }
  prepare_calendar <- function(preview_ref) {
    require_ready()
    if (!is.null(progress()) && !progress()$status %in% c("published", "completed_with_failures"))
      data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    reset(); preview(NULL); progress(NULL); attempted(FALSE)
    value <- service$prepare_calendar(preview_ref, now_utc())
    preview(value)
    status(paste(value$item_count,"native Abrufbereiche kalendergebunden vorbereitet · Schließtage sind keine Kursabdeckung · Abrufbestätigung bleibt separat."))
    invisible(value)
  }
  invalidate <- function() {
    reset()
    if (is.null(progress())) preview(NULL) # persisted executions keep their immutable original scope
  }
  shiny::observeEvent(input$batch_confirm_fetch, safe(function() {
    require_ready()
    if (is.null(preview()) || (attempted() && is.null(progress()))) data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    ordinals <- data_market_fx_batch_fetch_ordinals_v1(input$batch_fetch_ordinals, preview(), progress())
    now <- now_utc(); service$confirm_fetch(preview(), isTRUE(input$batch_fetch_confirm), now, expire(now), ordinals=ordinals)
    confirmed_ordinals(ordinals); confirmed(TRUE)
    # A selection reset and a fresh explicit confirmation can share one flush.
    # Supersede its queued FALSE update, otherwise the browser revokes this new grant.
    shiny::updateCheckboxInput(session, "batch_fetch_confirm", value=TRUE)
    status(paste(length(ordinals), "ausgewählte Abrufbereiche bestätigt. Nur diese Bereiche können jetzt stagen; alle anderen bleiben unverändert."))
  }))
  shiny::observeEvent(input$batch_fetch_confirm, {
    if (!isTRUE(input$batch_fetch_confirm)) {
      had_grant <- isTRUE(confirmed()); confirmed(FALSE); confirmed_ordinals(NULL); service$invalidate_fetch()
      if (had_grant) status("Abrufbestätigung widerrufen · vor einem Abruf erneut ausdrücklich bestätigen.")
    }
  }, ignoreNULL = FALSE, priority = 150)
  shiny::observeEvent(input$batch_fetch_ordinals, { reset() }, ignoreNULL = FALSE, priority = 100)
  shiny::observeEvent(input$batch_execute, safe(function() {
    require_ready()
    if (!isTRUE(confirmed()) || is.null(preview())) data_market_fx_batch_abort_v1("data_market_fx_batch_confirmation_required")
    ordinals <- data_market_fx_batch_fetch_ordinals_v1(input$batch_fetch_ordinals, preview(), progress())
    if (!identical(ordinals, confirmed_ordinals())) data_market_fx_batch_abort_v1("data_market_fx_batch_confirmation_required")
    resume <- !is.null(progress()); confirmed(FALSE); attempted(TRUE); publication_ack(NULL); review(NULL)
    write_pending(TRUE)
    accept(shiny::withProgress(message = "Ausgewählte Bereiche für Kurse und FX · lokal beim Eigentümer vormerken", value = 0,
      service$execute(now_utc(), resume = resume, ordinals = ordinals)))
  }))
  shiny::observeEvent(input$batch_list, safe(function() {
    reset(); values <- service$list_executions(); executions(values)
    choices <- stats::setNames(vapply(values, `[[`, character(1L), "execution_ref"),
      vapply(seq_along(values), function(i) paste("Gespeicherter Sammelabruf", i, "·", values[[i]]$status,
        "·", values[[i]]$execution_ref), character(1L)))
    shiny::updateSelectInput(session, "batch_saved", choices = c("Bitte wählen" = "", choices), selected = "")
    status(paste(length(values), "gespeicherte Sammelabrufe gelesen · kein Abruf · kein Schreiben."))
  }))
  shiny::observeEvent(input$batch_load, safe(function() {
    refs <- vapply(executions(), `[[`, character(1L), "execution_ref")
    if (is.null(input$batch_saved) || !input$batch_saved %in% refs) data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    accept(service$read(input$batch_saved))
  }))
  shiny::observeEvent(input$batch_review_ordinals, { reset() }, ignoreNULL = FALSE, priority = 100)
  shiny::observeEvent(input$batch_review, safe(function() {
    require_ready()
    reset(); ordinals <- data_market_fx_batch_review_ordinals_v1(input$batch_review_ordinals, progress())
    value <- service$review(ordinals)
    if (!identical(vapply(value$items, `[[`, integer(1L), "ordinal"), ordinals))
      data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    if (review_generation() == .Machine$integer.max) data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    review_generation(review_generation() + 1L)
    review(value); status(paste(length(ordinals), "ausgewählte Bereiche geprüft · jetzt unten in der Prüfung bestätigen und ohne Abruf veröffentlichen. Andere Bereiche bleiben unverändert."))
  }))
  # Each mounted checkbox acknowledges one review generation. Late events from a
  # removed checkbox cannot grant or revoke authority for its replacement.
  shiny::observeEvent(input$batch_publication_ack, {
    event <- input$batch_publication_ack
    if (!is.list(event) || !identical(sort(names(event)), c("confirmed", "generation")) ||
        !is.numeric(event$generation) || length(event$generation) != 1L || is.na(event$generation) ||
        !is.logical(event$confirmed) || length(event$confirmed) != 1L || is.na(event$confirmed)) {
      publication_ack(NULL); return()
    }
    if (!identical(event$generation, as.numeric(review_generation())) &&
        !identical(event$generation, review_generation())) return()
    publication_ack(if (isTRUE(event$confirmed) && !is.null(review()))
      list(generation=review_generation(), review=review()) else NULL)
  }, ignoreNULL = FALSE, priority = 50)
  shiny::observeEvent(input$batch_publish, safe(function() {
    require_ready()
    value <- review(); if (is.null(value)) data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    ack <- publication_ack()
    if (is.null(ack) || !identical(ack$generation, review_generation()) || !identical(ack$review, value))
      data_market_fx_batch_abort_v1("data_market_fx_batch_confirmation_required")
    if (!identical(data_market_fx_batch_review_ordinals_v1(input$batch_review_ordinals, progress()),
                   vapply(value$items, `[[`, integer(1L), "ordinal")))
      data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    now <- now_utc(); write_pending(TRUE)
    result <- service$publish(value, TRUE, now, expire(now))
    accept(result); on_publication() # invalidates coverage only; never FIFO/Snapshot/Cash/Tax writes
  }))
  shiny::observeEvent(input$batch_recover, safe(function() {
    require_ready(recovery=TRUE)
    value <- progress(); if (is.null(value)) data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    unknown <- Filter(function(row) row$status %in% c("provider_call_started", "publish_started"), value$items)
    selected <- Filter(function(row) identical(as.character(row$ordinal), input$batch_recovery_item), unknown)
    if (length(selected) != 1L) data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    row <- selected[[1L]]; domain <- if (row$status == "publish_started") "publication" else "staging"
    if (!isTRUE(input$batch_recover_confirm)) data_market_fx_batch_abort_v1("data_market_fx_batch_confirmation_required")
    write_pending(TRUE)
    accept(service$recover(row$ordinal, domain, isTRUE(input$batch_recover_confirm)))
    if (domain == "publication") on_publication()
  }))
  output$batch_status <- shiny::renderUI(shiny::p(class = "pl-section-copy", status()))
  output$batch_bound_ranges <- shiny::renderTable({
    value <- preview(); if (is.null(value)) return(data.frame())
    data_asset_center_market_fx_fetch_batch_frame_v1(value)
  }, striped = TRUE)
  output$batch_binding_targets <- shiny::renderTable({
    value <- preview(); if (is.null(value) || !length(value$target_reviews)) return(data.frame())
    do.call(rbind, lapply(value$target_reviews, function(row) data.frame(Bereich = as.character(row$ordinal),
      Verbraucher = row$consumer, Auswahl = if (is.null(row$consumer_ref)) "FX-Paar" else row$consumer_ref,
      Provider = row$provider_id, Symbol = row$provider_symbol, Quellwährung = row$provider_currency,
      Quellrichtung = row$source_route, Verwendung = row$direction, check.names = FALSE, stringsAsFactors = FALSE)))
  }, striped = TRUE)
  output$batch_calendar_dispositions <- shiny::renderTable({
    rows <- preview()$calendar_dispositions
    if (!length(rows)) return(data.frame())
    do.call(rbind,lapply(rows,function(row)data.frame(Bereich=row$kind,Verbraucher=row$consumer,
      Auswahl=if(is.null(row$consumer_ref))"FX"else row$consumer_ref,Disposition=row$disposition,Tage=as.character(row$day_count),check.names=FALSE)))
  }, striped = TRUE)
  output$batch_blockers <- shiny::renderTable({
    value <- preview(); if (is.null(value) || !length(value$blockers)) return(data.frame())
    do.call(rbind, lapply(value$blockers, function(row) data.frame(Asset = row$asset_name,
      Offener_Bedarf = row$disposition, Nächste_Aktion = row$next_action, check.names = FALSE, stringsAsFactors = FALSE)))
  }, striped = TRUE)
  output$batch_progress <- shiny::renderTable(data_market_fx_batch_progress_frame_v1(progress()), striped = TRUE)
  # Separate mount from actions/review: creating a review must not reset the selection.
  output$batch_review_selection <- shiny::renderUI({
    rows <- Filter(function(row) identical(row$status, "staged"), progress()$items)
    if (!length(rows)) return(shiny::p("Keine vorgemerkten Ergebnisse offen. Veröffentlichte Bereiche benötigen keine weitere Prüfung."))
    shiny::checkboxGroupInput("batch_review_ordinals", "Vorgemerkte Bereiche ausdrücklich auswählen",
      choices = stats::setNames(vapply(rows, function(row) as.character(row$ordinal), character(1L)),
        vapply(rows, function(row) paste("Bereich", row$ordinal, "·", row$consumer, "·", row$route,
          "·", row$start_date, "bis", row$end_date), character(1L))), selected = character())
  })
  output$batch_fetch_selection <- shiny::renderUI({
    rows <- data_market_fx_batch_pending_rows_v1(preview(), progress())
    if (!length(rows)) return(shiny::p("Keine wartenden Bereiche im geladenen Sammelabruf."))
    if (unknown() || needs_reload()) return(shiny::p("Vor weiteren Abrufen den gespeicherten Ausgang klären."))
    # Mount once per batch progress, not again when a confirmation changes buttons.
    shiny::tagList(shiny::checkboxGroupInput("batch_fetch_ordinals", "Wartende Bereiche ausdrücklich zum Abruf auswählen",
      choices = stats::setNames(vapply(rows, function(row) as.character(row$ordinal), character(1L)),
        vapply(rows, function(row) paste("Bereich", row$ordinal, "·", row$consumer, "·", row$route,
          "·", row$start_date, "bis", row$end_date, "· höchstens 1 Abruf beim Kursanbieter"), character(1L))), selected = character()),
      shiny::checkboxInput("batch_fetch_confirm", "Genau die ausgewählten wartenden Bereiche einmalig bestätigen", FALSE))
  })
  output$batch_review_action <- shiny::renderUI({
    if (needs_reload() || unknown() || !any(vapply(progress()$items, function(row) row$status == "staged", logical(1L)))) return(NULL)
    if (!is.null(review())) return(shiny::p("Prüfung bereit · diese angezeigten Ergebnisse unten bestätigen. Eine geänderte Auswahl erfordert eine neue Prüfung."))
    shiny::actionButton("batch_review", "Ausgewählte vorgemerkte Ergebnisse prüfen", class="btn-primary")
  })
  output$batch_fetch_actions <- shiny::renderUI({
    p <- preview(); value <- progress()
    if (is.null(p) || needs_reload() || unknown() || !is.null(review()) ||
        !identical(p$status,"ready_for_confirmation") ||
        !((!attempted() && is.null(value)) || length(data_market_fx_batch_pending_rows_v1(p,value)))) return(NULL)
    if (!confirmed()) shiny::actionButton("batch_confirm_fetch", "Ausgewählte Abrufe bestätigen", class="btn-primary")
    else shiny::actionButton("batch_execute", "Nur ausgewählte Bereiche bestätigt abrufen und vormerken", class="btn-primary")
  })
  output$batch_publication_actions <- shiny::renderUI({
    if (is.null(review())) return(NULL)
    checkbox <- htmltools::tagQuery(shiny::checkboxInput("batch_publish_confirm",
      "Genau diese angezeigten Prüfungen zur Veröffentlichung bestätigen", FALSE))$find("input")$addAttrs(
        onchange=sprintf("Shiny.setInputValue('batch_publication_ack',{generation:%d,confirmed:this.checked},{priority:'event'});", review_generation()))$allTags()
    shiny::tagList(checkbox, shiny::actionButton("batch_publish",
      "Bestätigte Prüfungen ohne neuen Abruf veröffentlichen", class="btn-primary"))
  })
  output$batch_actions <- shiny::renderUI({
    value <- progress(); p <- preview()
    if (is.null(p)) return(NULL)
    states <- if (is.null(value)) character() else vapply(value$items, `[[`, character(1L), "status")
    unknown <- states %in% c("provider_call_started", "publish_started")
    actions <- list()
    if (needs_reload()) return(shiny::p("Zunächst den gespeicherten Sammelabruf ohne Abruf laden. Ein möglicherweise begonnener Vorgang darf nicht wiederholt werden."))
    if (any(unknown)) {
      rows <- value$items[unknown]
      actions <- c(actions, list(shiny::selectInput("batch_recovery_item", "Unbekannten Ausgang abgleichen",
        stats::setNames(vapply(rows, function(row) as.character(row$ordinal), character(1L)),
          vapply(rows, function(row) paste("Bereich", row$ordinal, row$route, row$start_date, "bis", row$end_date), character(1L)))),
        shiny::checkboxInput("batch_recover_confirm", "Nur gespeicherte Nachweise abgleichen – nicht erneut abrufen", FALSE),
        shiny::actionButton("batch_recover", "Gespeicherten Ausgang ohne erneuten Abruf abgleichen")))
    }
    if (any(states == "failed")) actions <- c(actions, list(shiny::p(
      "Belegte Abruffehler wurden ohne erneuten Abruf abgeglichen. Diese Bereiche bleiben fachlich offen; keine vollständige Abdeckung. Nur unbegonnene Bereiche dürfen nach neuer Bestätigung fortgesetzt werden.")))
    if (!is.null(value) && identical(value$status, "published")) actions <- c(actions, list(shiny::p(
      "Dieser Sammelabruf ist veröffentlicht. Jetzt die gespeicherte Abdeckung erneut prüfen; Quelllücken und weitere Assets können noch offen sein. FIFO-/Snapshot-Abschluss bleibt separat.")))
    do.call(shiny::tagList, actions)
  })
  output$batch_review_details <- shiny::renderUI({
    value <- review(); if (is.null(value)) return(NULL)
    do.call(shiny::tagList, lapply(value$items, function(item) {
      frame <- if (item$kind == "market") data_market_history_review_rows_v1(item$public_review) else {
        do.call(rbind, lapply(item$daily_rows, function(row) data.frame(Datum = row$rate_date,
          Status = row$day_status, Quellkurs = if (is.null(row$rate_decimal)) "—" else row$rate_decimal,
          Qualität = row$quality_status, check.names = FALSE, stringsAsFactors = FALSE)))
      }
      summary <- if (item$kind == "market") {
        s <- item$public_review$summary
        paste(item$start_date, "bis", item$end_date, "· Quellwährung", item$public_review$quote_currency,
          "·", s$calendar_day_count, "Tage ·", s$observed_candidate_count, "beobachtet ·",
          s$non_trading_day_count, "Nichthandelstage ·", s$source_gap_count, "Quelllücken ·",
          s$correction_candidate_count, "Korrekturen ·", s$unavailable_effective_close_count,
          "ohne effektiven Close ·", s$warning_count, "Warncodes")
      } else paste(item$start_date, "bis", item$end_date, "·", length(item$daily_rows), "FX-Tage ·",
        sum(vapply(item$daily_rows, function(row) identical(row$day_status, "observed"), logical(1L))), "beobachtet ·",
        sum(vapply(item$daily_rows, function(row) identical(row$day_status, "non_trading_day"), logical(1L))), "Nichthandelstage ·",
        sum(vapply(item$daily_rows, function(row) identical(row$day_status, "source_gap"), logical(1L))), "Quelllücken")
      focus <- data_market_fx_batch_review_focus_v1(item,frame)
      warnings <- if(item$kind == "market") unlist(item$public_review$warning_codes,use.names=FALSE) else character()
      shiny::tagList(shiny::tags$h4(paste("Bereich", item$ordinal, item$consumer, item$route)),
        shiny::p(class = "pl-section-copy", summary),
        if (item$kind == "fx") shiny::p("Quellkurse in der gespeicherten Paarrichtung; bei inverser Route noch keine Umrechnung."),
        if(length(warnings)) shiny::p("Warncodes: ",paste(warnings,collapse=" · ")),
        if(nrow(focus)) shiny::tags$details(open="open",
          shiny::tags$summary(paste(nrow(focus),"Prüffälle · Quelllücken, fehlende Werte oder besondere Warnungen")),
          shiny::p("Quelllücken sind nicht automatisch Feiertage. Veröffentlichung übernimmt den angezeigten Kandidaten; Kalenderkorrekturen bleiben separat."),
          data_market_fx_batch_table_v1(focus)),
        shiny::tags$details(shiny::tags$summary("Vollständige Tageswerte anzeigen"),data_market_fx_batch_table_v1(frame)))
    }))
  })
  list(prepare = prepare, prepare_calendar = prepare_calendar, invalidate = invalidate, progress = progress,
    preview = preview, review = review, review_generation = review_generation, needs_reload = needs_reload)
}
