# Stichtags-Snapshot zu einem anderen Tag und Einstellung der Momentaufnahme (rc.313, #478).
#
# Gehandelt wird in Data, gelesen in der Analyse. Bis rc.312 plante und veroeffentlichte das Cockpit Snapshots
# und rief fuer die Momentaufnahme Kurse ab; damit war es die Ausnahme von der Regel, dass nur die Data-App schreibt. Den Snapshot
# zum juengsten vollstaendig bewerteten Tag und die Momentaufnahme veroeffentlicht „Alles aktualisieren“. Hier steht nur, was davon
# abweicht: ein anderer Stichtag. Dazu die Zahl gleichzeitiger Abrufe fuer die Momentaufnahme. Beides nur mit den Expertenwerkzeugen.
# Angesehen werden die veroeffentlichten Staende in der Analyse („Stichtag“, „Momentaufnahme“).

data_snapshot_publish_ui_v1 <- function() shiny::tags$details(class = "pl-disclosure pl-lazy", id = "snapshot_other_details",
  shiny::tags$summary("Snapshot zu anderem Stichtag · Momentaufnahme (für Fachleute)"),
  shiny::p(class = "pl-section-copy", paste(
    "„Alles aktualisieren“ veröffentlicht den Snapshot zum jüngsten vollständig bewerteten Tag und zum Schluss die Momentaufnahme.",
    "Hier lässt sich ein Snapshot zu einem anderen Stichtag festhalten. Ansehen lassen sich alle Stände in der Analyse unter „Stichtag“.")),
  shiny::div(class = "pl-field-row",
    shiny::dateInput("snapshot_other_as_of", "Stichtag", value = Sys.Date() - 1, format = "dd.mm.yyyy", weekstart = 1),
    shiny::actionButton("snapshot_other_plan", "Snapshot planen", class = "btn-default"),
    shiny::checkboxInput("snapshot_other_confirm", "Plan geprüft – genau diesen Stand veröffentlichen", FALSE),
    shiny::actionButton("snapshot_other_publish", "Veröffentlichen", class = "btn-primary")),
  shiny::p(class = "pl-field-hint", paste(
    "Der Plan schreibt nichts. Veröffentlicht wird genau der geprüfte Inhalt;",
    "ändert sich der Bewertungsstand dazwischen, bricht der Vorgang ab.")),
  shiny::uiOutput("snapshot_other_state"),
  shiny::div(class = "pl-table-wrap", shiny::tableOutput("snapshot_other_freshness")),
  shiny::tags$h4("Momentaufnahme: gleichzeitige Abrufe"),
  shiny::div(class = "pl-field-row",
    shiny::numericInput("snapshot_other_parallel", "Gleichzeitige Abrufe", value = 8, min = 1, max = 32, step = 1),
    shiny::actionButton("snapshot_other_parallel_save", "Speichern", class = "btn-default")),
  portelyra_note_v1(title = "Gleichzeitige Abrufe", id = "data-intraday-parallel", paste(
    "Der Abruf wartet auf die Quelle, nicht auf den Rechner: Mehrere gleichzeitige Abrufe sind meist",
    "deutlich schneller als einzeln. Mehr hilft",
    "nur, solange die Quelle mitmacht.")),
  shiny::uiOutput("snapshot_other_parallel_state"))

# `service`: der Snapshot-Dienst (plan, publish, freshness); `intraday`: der Dienst der Momentaufnahme (nur die Einstellung).
data_snapshot_publish_server_v1 <- function(input, output, session, service, intraday, now_utc) {
  notice <- shiny::reactiveVal(NULL); plan <- shiny::reactiveVal(NULL); parallel_notice <- shiny::reactiveVal(NULL)
  failed <- function(error) {
    notice(list(tone = "error", title = "Vorgang abgebrochen",
                copy = pl_error_text_v1(if (is.null(error$code)) conditionMessage(error) else error$code)))
    NULL
  }
  # Beim ersten Aufklappen: Vorgabe-Stichtag ist der juengste Tag mit Wert im Stand (#373), dazu die gespeicherten Abrufe.
  shiny::observeEvent(input$snapshot_other_details_open, {
    if (!isTRUE(input$snapshot_other_details_open)) return()
    latest <- if (is.null(service)) NULL else tryCatch(service$freshness(format(Sys.Date(), "%Y-%m-%d"))$latest_valued_date, error = function(error) NULL)
    if (is.character(latest) && length(latest) == 1L && nzchar(latest)) shiny::updateDateInput(session, "snapshot_other_as_of", value = as.Date(latest))
    parallel <- if (is.null(intraday)) NA_integer_ else tryCatch(as.integer(intraday$parallel_requests()), error = function(error) NA_integer_)
    if (length(parallel) == 1L && !is.na(parallel)) shiny::updateNumericInput(session, "snapshot_other_parallel", value = parallel)
  }, ignoreInit = TRUE, once = TRUE)
  shiny::observeEvent(input$snapshot_other_as_of, { plan(NULL); shiny::updateCheckboxInput(session, "snapshot_other_confirm", value = FALSE) }, ignoreInit = TRUE)
  shiny::observeEvent(input$snapshot_other_plan, {
    if (is.null(service)) {
      notice(list(tone = "error", title = "Snapshot nicht verfügbar", copy = "Der Bewertungsstand fehlt. Zuerst „Alles aktualisieren“ ausführen."))
      return()
    }
    value <- tryCatch(service$plan(format(input$snapshot_other_as_of, "%Y-%m-%d"), now_utc()), error = failed)
    if (is.null(value)) return()
    plan(value); shiny::updateCheckboxInput(session, "snapshot_other_confirm", value = FALSE)
    beyond <- isTRUE(value$beyond_valued_window)
    notice(list(
      tone = if (beyond) "error" else if (identical(value$snapshot_status, "complete")) "neutral" else "warning",
      title = if (beyond) "Stichtag jenseits des bewerteten Zeitraums"
              else paste0("Plan bereit · ", if (identical(value$snapshot_status, "complete")) "vollständig" else "unvollständig"),
      copy = if (beyond) paste0("Für diesen Tag steht im Bewertungsstand noch kein Kurstag; jede Position erschiene als Lücke. Bewertet ist bis ",
                                if (is.null(value$latest_valued_date)) "— (noch gar nichts)" else format(as.Date(value$latest_valued_date), "%d.%m.%Y"), ".")
             else paste0(value$counts$valued_position_count, " bewertete Positionen · ", value$counts$excluded_position_count,
                         " nicht enthalten · Frische ", desktop_snapshot_status_label_v1(value$freshness$overall_status), ".")))
  })
  shiny::observeEvent(input$snapshot_other_publish, {
    current <- plan()
    if (is.null(current)) { notice(list(tone = "warning", title = "Kein geprüfter Plan", copy = "Zuerst planen, dann bestätigen, dann veröffentlichen.")); return() }
    if (!isTRUE(input$snapshot_other_confirm)) {
      notice(list(tone = "warning", title = "Bestätigung fehlt", copy = "Das Häkchen bestätigt genau diesen Stand. Danach erneut veröffentlichen."))
      return()
    }
    # Ein Snapshot ohne eine einzige bewertete Position verdeckt als juengster Stand den letzten brauchbaren.
    if (isTRUE(current$beyond_valued_window) || identical(as.integer(current$counts$valued_position_count), 0L)) {
      notice(list(tone = "error", title = "Nichts zu veröffentlichen", copy = paste0("Für den ", format(as.Date(current$as_of_date), "%d.%m.%Y"),
        " ist keine einzige Position bewertet; deshalb wird kein Snapshot veröffentlicht.")))
      return()
    }
    value <- tryCatch(service$publish(current$as_of_date, current$plan_fingerprint, TRUE, now_utc()), error = failed)
    if (is.null(value)) return()
    plan(NULL); shiny::updateCheckboxInput(session, "snapshot_other_confirm", value = FALSE)
    already <- identical(value$status, "already_published")
    notice(list(tone = "neutral", title = if (already) "Dieser Stand war bereits veröffentlicht" else "Snapshot veröffentlicht",
      copy = paste0("Stichtag ", format(as.Date(value$as_of_date), "%d.%m.%Y"), " · ",
                    if (identical(value$snapshot_status, "complete")) "vollständig" else "unvollständig",
                    if (already) ". Derselbe Inhalt liegt schon unveränderlich vor; es wurde nichts geändert." else ". Der Stand ist unveränderlich festgehalten.",
                    " Ansehen in der Analyse unter „Stichtag“.")))
  })
  output$snapshot_other_state <- shiny::renderUI({ current <- notice(); if (is.list(current)) portelyra_status_panel(current$title, current$copy, tone = current$tone) })
  output$snapshot_other_freshness <- shiny::renderTable({ current <- plan(); if (is.null(current)) return(NULL); desktop_snapshot_freshness_frame_v1(current) },
                                                        striped = TRUE, spacing = "xs", width = "100%")
  # Gleichzeitige Abrufe der Momentaufnahme: gespeichert im Stand der Momentaufnahme, gelesen beim ersten Aufklappen.
  shiny::observeEvent(input$snapshot_other_parallel_save, {
    wanted <- suppressWarnings(as.integer(input$snapshot_other_parallel))
    if (is.null(intraday) || is.na(wanted) || wanted < 1L || wanted > 32L) {
      parallel_notice(list(tone = "error", title = "Nicht gespeichert", copy = "Erlaubt sind 1 bis 32 gleichzeitige Abrufe.")); return()
    }
    ok <- !is.null(tryCatch(intraday$set_parallel_requests(wanted, now_utc()), error = function(error) NULL))
    parallel_notice(if (ok) list(tone = "positive", title = "Gespeichert", copy = paste0(wanted, " gleichzeitige Abrufe beim nächsten „Alles aktualisieren“."))
                    else list(tone = "error", title = "Nicht gespeichert", copy = "Die Einstellung ließ sich nicht schreiben."))
  })
  output$snapshot_other_parallel_state <- shiny::renderUI({ current <- parallel_notice(); if (is.list(current)) portelyra_status_panel(current$title, current$copy, tone = current$tone) })
  invisible(list(plan = plan, notice = notice))
}
