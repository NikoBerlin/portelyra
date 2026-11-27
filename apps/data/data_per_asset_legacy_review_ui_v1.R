data_per_asset_legacy_review_module_ui_v1 <- function(id) {
  ns <- shiny::NS(id)
  shiny::tagList(
    shiny::uiOutput(ns("state")),
    shiny::div(class="pl-step-grid",
      shiny::div(class="pl-step", shiny::span(class="pl-step-number", "1"), shiny::div(class="pl-step-title", "Asset-Quelle öffnen"),
                 shiny::div(class="pl-step-copy", "Die serverseitig freigegebene Quelle wird nur gelesen und enthält genau ein Asset aus dem Altbestand."),
                 shiny::actionButton(ns("open"), "Freigegebene Quelle öffnen", class="btn-default")),
      shiny::div(class="pl-step", shiny::span(class="pl-step-number", "2"), shiny::div(class="pl-step-title", "Alle Zeilen entscheiden"),
                 shiny::div(class="pl-step-copy", "Jede Zeile bleibt bereit, wartet auf eine Entscheidung oder ist blockiert; nichts wird ausgelassen."),
                 shiny::actionButton(ns("prepare"), "Vorschau der Abstimmung prüfen", class="btn-default")),
      shiny::div(class="pl-step", shiny::span(class="pl-step-number", "3"), shiny::div(class="pl-step-title", "Paket der Probe"),
                 shiny::div(class="pl-step-copy", "Nur ein Plan, in dem alle Zeilen bereit sind, kann einmalig in den separaten Datenraum der Probe geschrieben werden."),
                 shiny::checkboxInput(ns("confirm"), "Genau diesen Plan für die Probe einmalig bestätigen", FALSE),
                 shiny::actionButton(ns("apply"), "Bestätigt in die Probe übernehmen", class="btn-primary"))
    ),
    shiny::uiOutput(ns("source_summary")),
    shiny::div(class="pl-form-grid",
      shiny::selectInput(ns("asset"), "Ziel-Asset", c("Bitte Quelle öffnen"=""))
    ),
    shiny::uiOutput(ns("companion_review")),
    shiny::uiOutput(ns("account_bindings")),
    shiny::tags$h3("Zeilenentscheidungen"),
    shiny::uiOutput(ns("row_reviews")),
    shiny::uiOutput(ns("preview_summary")),
    shiny::conditionalPanel(
      condition=sprintf("output['%s']", ns("product_enabled")),
      shiny::div(class="pl-write-boundary",
        shiny::tags$h3("Separate Übernahme in den Bestand"),
        shiny::p(class="pl-section-copy", "Erst nach einer Prüfung, in der alle Zeilen bereit sind, wird eine neue Vorschau für den Bestand gegen Schema 201 erzeugt. Die Bestätigung ist getrennt vom Schritt der Probe; Schema 201 bleibt bytegleich."),
        shiny::actionButton(ns("product_prepare"), "Vorschau der Übernahme in den Bestand prüfen", class="btn-default"),
        shiny::checkboxInput(ns("product_confirm"), "Genau diese Übernahme in den Bestand einmalig bestätigen", FALSE),
        shiny::actionButton(ns("product_apply"), "Bestätigte Buchungen übernehmen", class="btn-primary")
      )
    ),
    shiny::tags$h3("Vollständige Disposition"),
    shiny::div(class="pl-table-wrap", shiny::tableOutput(ns("preview_rows"))),
    shiny::tags$h3("FIFO / GuV / Erträge / Gebühren / Transfer"),
    shiny::div(class="pl-table-wrap", shiny::tableOutput(ns("reconciliation")))
  )
}

.data_per_asset_review_ui_choices <- function(items, empty="Bitte wählen") {
  if (is.null(items) || !length(items)) return(stats::setNames("", empty))
  c(stats::setNames("", empty), stats::setNames(vapply(items, `[[`, character(1L), "ref"), make.unique(vapply(items, `[[`, character(1L), "label"), sep=" · ")))
}
.data_per_asset_review_ui_value <- function(input, id) {
  value <- input[[id]]; if (is.null(value)) "" else value
}
.data_per_asset_review_ui_slug <- function(ref) sub("[^A-Za-z0-9_]", "_", ref)

data_per_asset_legacy_review_module_server_v1 <- function(id, center, clock=function() format(as.POSIXct(Sys.time(), tz="UTC"), "%Y-%m-%dT%H:%M:%SZ", tz="UTC"), product_adapter=NULL) {
  shiny::moduleServer(id, function(input, output, session) {
    source_model <- shiny::reactiveVal(NULL); preview <- shiny::reactiveVal(NULL); result <- shiny::reactiveVal(NULL)
    product_preview <- shiny::reactiveVal(NULL); product_result <- shiny::reactiveVal(NULL)
    state <- shiny::reactiveVal(list(kind="idle", title="Prüfung je Asset bereit", copy="Beim Start wird keine Quelle des Altbestands geöffnet und kein Ziel geschrieben."))
    blocked <- function(error, title="Prüfung je Asset blockiert", invalidate_sandbox=TRUE, invalidate_product=TRUE) {
      if (isTRUE(invalidate_sandbox)) preview(NULL)
      if (isTRUE(invalidate_product)) product_preview(NULL)
      shiny::updateCheckboxInput(session, "confirm", value=FALSE); shiny::updateCheckboxInput(session, "product_confirm", value=FALSE)
      code <- if (inherits(error, "spot_per_asset_review_error")) error$code else "per_asset_review_adapter_failed"
      state(list(kind="error", title=title, copy=pl_error_text_v1(code)))
    }
    invalidate <- function() {
      if (!is.null(preview())) {
        data_per_asset_review_invalidate_v1(center); preview(NULL); product_preview(NULL); product_result(NULL); shiny::updateCheckboxInput(session, "confirm", value=FALSE); shiny::updateCheckboxInput(session, "product_confirm", value=FALSE)
        state(list(kind="warning", title="Vorschau verworfen", copy="Eine Auswahl oder Zeilenentscheidung wurde geändert; eine neue Vorschau ist erforderlich."))
      }
    }
    shiny::observeEvent(input$open, {
      tryCatch({
        model <- data_per_asset_review_open_v1(center); source_model(model); preview(NULL); result(NULL); product_preview(NULL); product_result(NULL)
        shiny::updateSelectInput(session, "asset", choices=.data_per_asset_review_ui_choices(model$target_assets))
        state(list(kind=if (model$status=="blocked") "warning" else "completed", title="Quelle des Assets geöffnet", copy=paste(model$counts$source_row_count, "Zeilen wurden vollständig für die lokale Entscheidung gebunden.")))
      }, error=blocked)
    }, ignoreInit=TRUE)
    shiny::observeEvent(input$asset, invalidate, ignoreInit=TRUE)
    shiny::observe({
      model <- source_model(); if (is.null(model)) return()
      dependencies <- c("asset", "companion_action", "companion_name_action", "companion_manual_name", "companion_isin", "companion_wkn", "companion_note")
      dependencies <- c(dependencies, unlist(lapply(model$source_accounts, function(account) paste0("binding_", .data_per_asset_review_ui_slug(account$ref))), use.names=FALSE))
      row_prefixes <- c("decision_", "basis_mode_", "basis_amount_mode_", "basis_", "acquisition_evidence_", "acquisition_date_", "acquisition_time_", "acquisition_zone_", "acquisition_utc_", "movement_context_", "fee_treatment_", "memo_action_", "duplicate_action_", "dividend_mode_", "gross_total_", "same_day_sequence_")
      dependencies <- c(dependencies, unlist(lapply(model$rows, function(row) paste0(row_prefixes, .data_per_asset_review_ui_slug(row$ref))), use.names=FALSE))
      lapply(dependencies, function(name) input[[name]])
      isolate(invalidate())
    })
    output$companion_review <- shiny::renderUI({
      model <- source_model(); if (is.null(model) || is.null(model$companion)) return(NULL)
      candidate <- model$companion
      shiny::tagList(
        shiny::tags$h3("Optionale Begleitdatei assets.csv"),
        shiny::p(class="pl-section-copy", paste(
          "Exakte Asset-Verknüpfung verfügbar · Felder zu Kursanbieter und Notierung ausgeschlossen:", candidate$provider_listing_field_count,
          "· Steuerhinweis vorhanden, aber ausgeschlossen:", if (candidate$tax_hint_present) "ja" else "nein"
        )),
        shiny::div(class="pl-form-grid",
          shiny::selectInput(session$ns("companion_action"), "Begleitdatei verwenden", c("Nicht übernehmen (Standard)"="skip", "Explizit binden"="bind"), selected="skip"),
          shiny::selectInput(session$ns("companion_name_action"), "Anzeigename", c("Vorschlag sichtbar bestätigen"="accept_candidate", "Manuell ersetzen"="replace_manually"), selected="accept_candidate"),
          shiny::textInput(session$ns("companion_manual_name"), "Manueller Anzeigename", value=""),
          shiny::checkboxInput(session$ns("companion_isin"), paste("ISIN einzeln bestätigen:", if (is.null(candidate$isin_candidate)) "nicht vorhanden" else candidate$isin_candidate), FALSE),
          shiny::checkboxInput(session$ns("companion_wkn"), paste("WKN einzeln bestätigen:", if (is.null(candidate$wkn_candidate)) "nicht vorhanden" else candidate$wkn_candidate), FALSE),
          shiny::checkboxInput(session$ns("companion_note"), "Notiz einzeln bestätigen", FALSE)
        )
      )
    })
    output$account_bindings <- shiny::renderUI({
      model <- source_model(); if (is.null(model) || !length(model$source_accounts)) return(NULL)
      shiny::tagList(shiny::tags$h3("Ausdrückliche Kontozuordnung"), lapply(model$source_accounts, function(account) {
        shiny::selectInput(session$ns(paste0("binding_", .data_per_asset_review_ui_slug(account$ref))), account$label,
                           choices=.data_per_asset_review_ui_choices(model$target_accounts))
      }))
    })
    output$row_reviews <- shiny::renderUI({
      model <- source_model(); if (is.null(model)) return(NULL)
      shiny::tagList(lapply(model$rows, function(row) {
        slug <- .data_per_asset_review_ui_slug(row$ref)
        shiny::div(class="pl-write-boundary pl-per-asset-row",
          shiny::tags$h4(paste0("#", row$ordinal, " · ", row$event_label, " · ", row$date, " · ", row$time)),
          shiny::p(class="pl-section-copy", paste("Ausgang:", row$disposition, "· Entscheidungen:", paste(row$decision_codes, collapse=", "), "· Blocker:", paste(row$blocker_codes, collapse=", "))),
          shiny::div(class="pl-form-grid",
            shiny::selectInput(session$ns(paste0("decision_", slug)), "Zeile prüfen", c("Bitte entscheiden"="unresolved", "Nachweis bestätigen"="accept"), selected="unresolved"),
            shiny::selectInput(session$ns(paste0("basis_mode_", slug)), "Nachweis der Basis", c("Nicht anwendbar/offen"="", "Bewertung als Basis bestätigt"="valuation_confirmed_as_basis", "Basis belegt"="provided_basis", "Basis fehlt"="basis_missing"), selected=if (row$event_type=="reward") "valuation_confirmed_as_basis" else if (row$event_type=="deposit") "provided_basis" else ""),
            shiny::selectInput(session$ns(paste0("basis_amount_mode_", slug)), "Basis-Betragsmodus", c("Nicht anwendbar/offen"="", "Menge × Stückpreis aus der Quelle"="source_quantity_unit_price", "Manueller Gesamtbetrag"="manual_total", "Nicht anwendbar"="not_applicable"), selected=if (row$event_type %in% c("reward", "deposit")) "source_quantity_unit_price" else ""),
            shiny::textInput(session$ns(paste0("basis_", slug)), "Belegte Gesamtbasis", value=""),
            shiny::selectInput(session$ns(paste0("acquisition_evidence_", slug)), "Ursprüngliche Anschaffungszeit", c("Nicht anwendbar/offen"="", "Nur Datum"="date_only", "Exakt"="exact"), selected=if (row$event_type=="deposit") "date_only" else ""),
            shiny::textInput(session$ns(paste0("acquisition_date_", slug)), "Ursprüngliches Erwerbsdatum", value=if (row$event_type=="deposit") "2024-02-01" else "", placeholder="2024-02-01"),
            shiny::textInput(session$ns(paste0("acquisition_time_", slug)), "Ursprüngliche Erwerbsuhrzeit", value="", placeholder="09:30:00"),
            shiny::textInput(session$ns(paste0("acquisition_zone_", slug)), "Anschaffungs-Zeitzone", value=if (row$event_type=="deposit") "Europe/Berlin" else "", placeholder="Europe/Berlin"),
            shiny::textInput(session$ns(paste0("acquisition_utc_", slug)), "Anschaffung UTC (bei exakt)", value="", placeholder="2024-02-01T08:30:00Z"),
            shiny::selectInput(session$ns(paste0("movement_context_", slug)), "Anlass", c("Nicht anwendbar/offen"="", "Unklassifiziert"="unclassified", "Schenkung"="gift", "Erbschaft"="inheritance", "Schuldtilgung"="debt_settlement", "Spende"="donation", "Zahlung"="payment", "Verwahrausgang"="custody_exit", "Sonstiges"="other"), selected=if (row$event_type=="deposit") "unclassified" else if (row$event_type=="withdrawal") "custody_exit" else ""),
            shiny::selectInput(session$ns(paste0("fee_treatment_", slug)), "Behandlung der Gebühr", c("Nicht anwendbar/offen"="", "Asset-Menge"="principal_asset_quantity", "Basiswährung"="monetary_basis_currency", "Separates Ereignis erforderlich"="separate_event_required"), selected=if (row$event_type %in% c("withdrawal", "transfer") && row$fee_decimal!="—") "principal_asset_quantity" else ""),
            shiny::selectInput(session$ns(paste0("memo_action_", slug)), "Notiz aus der Quelle", c("Nicht anwendbar/offen"="", "Übernehmen"="accept_source", "Nicht übernehmen"="skip"), selected=if (nzchar(row$memo)) "accept_source" else ""),
            shiny::selectInput(session$ns(paste0("duplicate_action_", slug)), "Duplikatentscheidung", c("Nicht anwendbar/offen"="", "Trotzdem bestätigt behalten"="keep_confirmed")),
            shiny::selectInput(session$ns(paste0("dividend_mode_", slug)), "Dividendenmodus", c("Nicht anwendbar/offen"="", "Menge × brutto je Einheit"="quantity_unit_price", "Brutto gesamt"="gross_total")),
            shiny::textInput(session$ns(paste0("gross_total_", slug)), "Dividende brutto gesamt", value=""),
            shiny::textInput(session$ns(paste0("same_day_sequence_", slug)), "Ausdrückliche FIFO-Reihenfolge am selben Tag", value="")
          ),
          shiny::p(class="pl-section-copy", paste("Angaben der Quelle unveränderlich · Menge:", row$quantity_decimal, "· Stückpreis:", row$unit_price_decimal, "· Gebühr:", row$fee_decimal, "· Zeitnachweis:", row$time_evidence))
        )
      }))
    })
    collect_form <- function() {
      model <- source_model(); if (is.null(model)) stop(.per_asset_review_condition("per_asset_review_source_missing"))
      companion_review <- if (is.null(model$companion)) NULL else list(
        action=.data_per_asset_review_ui_value(input, "companion_action"),
        display_name_action=.data_per_asset_review_ui_value(input, "companion_name_action"),
        manual_display_name=.data_per_asset_review_ui_value(input, "companion_manual_name"),
        accept_isin=isTRUE(input$companion_isin), accept_wkn=isTRUE(input$companion_wkn), accept_note=isTRUE(input$companion_note)
      )
      bindings <- lapply(model$source_accounts, function(account) list(source_account_ref=account$ref, target_account_ref=.data_per_asset_review_ui_value(input, paste0("binding_", .data_per_asset_review_ui_slug(account$ref)))))
      rows <- lapply(model$rows, function(row) {
        slug <- .data_per_asset_review_ui_slug(row$ref); get <- function(prefix) .data_per_asset_review_ui_value(input, paste0(prefix, slug))
        list(
          row_ref=row$ref, decision=get("decision_"),
          basis_evidence_mode=get("basis_mode_"), basis_amount_mode=get("basis_amount_mode_"), provided_basis_decimal=get("basis_"),
          original_acquired_time_evidence=get("acquisition_evidence_"), original_acquired_local_date=get("acquisition_date_"),
          original_acquired_local_time=get("acquisition_time_"), original_acquired_time_zone=get("acquisition_zone_"),
          original_acquired_at_utc=get("acquisition_utc_"), movement_context_code=get("movement_context_"), fee_treatment=get("fee_treatment_"),
          memo_action=get("memo_action_"), duplicate_action=get("duplicate_action_"), dividend_input_mode=get("dividend_mode_"),
          dividend_gross_total_decimal=get("gross_total_"), same_day_fifo_sequence=get("same_day_sequence_")
        )
      })
      list(source_ref=model$source_ref, target_asset_ref=.data_per_asset_review_ui_value(input, "asset"), companion_review=companion_review, source_account_bindings=bindings, row_reviews=rows)
    }
    shiny::observeEvent(input$prepare, {
      tryCatch({ value <- data_per_asset_review_prepare_v1(center, collect_form(), clock()); preview(value); result(NULL); product_preview(NULL); product_result(NULL); shiny::updateCheckboxInput(session, "confirm", value=FALSE); shiny::updateCheckboxInput(session, "product_confirm", value=FALSE)
                 state(list(kind=if (value$status=="ready") "pending_confirmation" else "warning", title=if (value$status=="ready") "Plan für die Probe · alle Zeilen bereit" else "Entscheidungen unvollständig", copy=paste(value$counts$ready_count, "bereit ·", value$counts$decision_required_count, "Entscheidung nötig ·", value$counts$blocked_count, "blockiert"))) }, error=blocked)
    }, ignoreInit=TRUE)
    shiny::observeEvent(input$apply, {
      tryCatch({ value <- preview(); if (is.null(value)) .per_asset_review_abort("per_asset_review_preview_missing"); if (!isTRUE(input$confirm)) .per_asset_review_abort("per_asset_review_confirmation_required")
                 data_per_asset_review_confirm_v1(center, value$preview_ref); applied <- data_per_asset_review_apply_v1(center, value$preview_ref); result(applied); shiny::updateCheckboxInput(session, "confirm", value=FALSE)
                 state(list(kind="completed", title="Unveränderliches Paket der Probe abgeschlossen", copy=paste(applied$row_count, "Zeilen ·", applied$artifact_count, "Nachweisdateien · kein Schreiben in Stammdaten oder Cash"))) }, error=blocked)
    }, ignoreInit=TRUE)
    shiny::observeEvent(input$product_prepare, {
      tryCatch({
        if (is.null(product_adapter)) .per_asset_review_abort("per_asset_review_adapter_invalid")
        value <- data_per_asset_review_product_prepare_v1(center, product_adapter); product_preview(value); product_result(NULL)
        shiny::updateCheckboxInput(session, "product_confirm", value=FALSE)
        state(list(kind=if (value$status=="ready_for_confirmation") "pending_confirmation" else "completed",
          title=if (value$status=="ready_for_confirmation") "Vorschau der Übernahme in den Bestand bereit" else "Übernahme in den Bestand bereits abgeschlossen",
          copy=paste(value$event_count, "Asset-Ereignisse · Schema 201 wird nur gelesen · kein automatisches Cash")))
      }, error=function(error) blocked(error, invalidate_sandbox=FALSE))
    }, ignoreInit=TRUE)
    shiny::observeEvent(input$product_apply, {
      tryCatch({
        value <- product_preview(); if (is.null(value)) .per_asset_review_abort("per_asset_review_preview_missing")
        if (!isTRUE(input$product_confirm)) .per_asset_review_abort("per_asset_review_confirmation_required")
        data_per_asset_review_product_confirm_v1(center, value$product_preview_ref)
        applied <- data_per_asset_review_product_apply_v1(center, product_adapter, value$product_preview_ref, clock())
        product_result(applied); shiny::updateCheckboxInput(session, "product_confirm", value=FALSE)
        state(list(kind="completed", title="Buchungen im Bestand abgeschlossen",
          copy=paste(applied$event_count, "neue Ereignisse · Schema 201 unverändert · Cash-Buchungszeilen 0")))
      }, error=function(error) blocked(error, "Übernahme in den Bestand blockiert", invalidate_sandbox=FALSE, invalidate_product=FALSE))
    }, ignoreInit=TRUE)
    output$product_enabled <- shiny::reactive(!is.null(product_adapter)); shiny::outputOptions(output, "product_enabled", suspendWhenHidden=FALSE)
    output$state <- shiny::renderUI({ value <- state(); portelyra_status_panel(value$title, value$copy, tone=if (value$kind=="error") "error" else if (value$kind %in% c("warning", "pending_confirmation")) "warning" else "neutral") })
    output$source_summary <- shiny::renderUI({ model <- source_model(); if (is.null(model)) return(NULL); shiny::div(class="pl-kpi-grid", portelyra_kpi_item("Zeilen", model$counts$source_row_count), portelyra_kpi_item("Entscheidung offen", model$counts$decision_required_count), portelyra_kpi_item("Blockiert", model$counts$blocked_count)) })
    output$preview_summary <- shiny::renderUI({ value <- preview(); if (is.null(value)) return(NULL); portelyra_status_panel(paste("Abstimmung", value$status), "Trade-Ereignisse erzeugen keine automatische Cash-Gegenbuchung.", tone=if (value$status=="ready") "warning" else "error") })
    output$preview_rows <- shiny::renderTable({ value <- preview(); if (is.null(value)) return(data.frame()); do.call(rbind, lapply(value$rows, function(row) data.frame(Zeile=row$ordinal, Datum=row$date, Zeit=row$time, Typ=row$event_label, Disposition=row$disposition, Entscheidung=paste(row$decision_codes, collapse=", "), Blocker=paste(row$blocker_codes, collapse=", "), Asset=row$asset_effect, FIFO=row$fifo_effect, GuV=row$guv_effect, Income=row$income_effect, Gebühr=row$fee_effect, Transfer=row$transfer_effect, check.names=FALSE))) }, striped=TRUE, bordered=FALSE)
    output$reconciliation <- shiny::renderTable({
      value <- preview(); if (is.null(value)) return(data.frame())
      reconciliation <- value$reconciliation
      exact_rows <- list(
        list(Fakt="Status", Wert=reconciliation$status),
        list(Fakt="Offene FIFO-Lots", Wert=as.character(reconciliation$remaining_lot_count)),
        list(Fakt="Belege abgehender Lots", Wert=as.character(reconciliation$outgoing_receipt_count)),
        list(Fakt="Transfer-Lot-Belege", Wert=as.character(reconciliation$transfer_receipt_count)),
        list(Fakt="Restmenge", Wert=reconciliation$cost_average$remaining_quantity),
        list(Fakt="Verbleibende FIFO-Basis", Wert=reconciliation$cost_average$remaining_fifo_basis),
        list(Fakt="FIFO-Durchschnittskosten", Wert=reconciliation$cost_average$cost_average),
        list(Fakt="Monetäre Gebühren", Wert=paste(reconciliation$totals$monetary_fee, reconciliation$totals$monetary_fee_currency)),
        list(Fakt="Asset-Gebührmenge", Wert=reconciliation$totals$asset_fee_quantity),
        list(Fakt="Dividendenerträge", Wert=paste(reconciliation$totals$dividend_income, reconciliation$totals$income_currency)),
        list(Fakt="Reward-Erträge", Wert=paste(reconciliation$totals$reward_income, reconciliation$totals$income_currency)),
        list(Fakt="Cash-Buchungszeilen", Wert=as.character(reconciliation$cash_posting_count))
      )
      do.call(rbind, lapply(exact_rows, function(row) data.frame(Fakt=row$Fakt, Wert=row$Wert, check.names=FALSE)))
    }, striped=TRUE, bordered=FALSE)
    list(source=source_model, preview=preview, result=result, product_preview=product_preview, product_result=product_result, state=state, collect_form=collect_form)
  })
}
