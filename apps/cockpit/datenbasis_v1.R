# Die Datenbasis (rc.313/rc.314, #478): was hinterlegt und wie es eingestellt ist - ohne Werte und ohne GuV.
#
# Stufe 1 (rc.313) las den juengsten Stichtags-Snapshot: Bestand in Stueck je Asset, Cash je Konto laut Auszug, Frische je Ebene,
# dazu die Bereitschaft des letzten Abschlusses. Stufe 2 (rc.314) liest die eigene Veroeffentlichung `data_basis`, die
# „Alles aktualisieren“ in der Data-App zum Schluss schreibt: Staende je Datenart, Konten mit ihren Buchungen, Assets mit
# Kurszuordnung und Kursstand, Wechselkurse, Belege je Jahr und die Einstellungen (Steuer je Jahr, Steuerangaben je Institut, die
# Eingaben des letzten Abschlusses samt Gebuehrenquelle, Bewertung je Coin und Wallet, FIFO-Wallets, Anlage, Anzeige).
# Ein Teil, den die Data-App nicht lesen konnte, steht als „nicht lesbar“ da, nie als leer oder null.

DATENBASIS_ASSET_TYPES_V1 <- c(crypto = "Krypto", equity = "Aktien", fund = "Fonds", etf = "ETF", commodity = "Rohstoffe",
                               derivative = "Derivate", fx = "Devisen", bond = "Anleihen")
DATENBASIS_ACCOUNT_TYPES_V1 <- c(securities = "Depot", cash = "Cash-Konto", bank = "Bankkonto", crypto_wallet = "Krypto-Wallet",
                                 external = "Extern", other = "Sonstiges")
DATENBASIS_VALUATION_V1 <- c(external_market = "Marktdaten", manual = "eigene Kursangaben", transaction_only = "nur Transaktionen",
                             unit_value = "Einheitswert")
DATENBASIS_FX_SOURCES_V1 <- c(market_plugin = "Anbieter", manual_reviewed_evidence = "eigene geprüfte Angabe")
DATENBASIS_DOCUMENT_KINDS_V1 <- c(account_statement = "Kontoauszug", securities_statement = "Depotauszug", transaction_export = "Transaktionsexport",
                                  tax_certificate = "Jahressteuerbescheinigung", income_statement = "Erträgnisaufstellung", advance_lump_sum = "Vorabpauschale",
                                  confirmation = "Bestätigung / Abrechnung", other = "Sonstiges")
# Kurze Namen der eigenen Steuerangaben je Jahr; was hier fehlt, nennt die Liste der Steuer-Karte.
DATENBASIS_TAX_PARAMETERS_V1 <- c(personal_income_tax_rate = "persönlicher Steuersatz", capital_income_tax_rate = "Abgeltungsteuersatz (eigene Angabe)",
                                  solidarity_surcharge_rate = "Solidaritätszuschlag (eigene Angabe)", church_tax_applicable = "Kirchensteuer",
                                  church_tax_rate = "Kirchensteuersatz")
DATENBASIS_INSTITUTION_FIELDS_V1 <- c(capital_income_allowance = "Freistellungsauftrag", creditable_foreign_withholding_tax = "Anrechenbare Quellensteuer",
                                      opening_equity_loss_carryforward = "Verlusttopf Aktien zum 1.1.",
                                      opening_general_capital_loss_carryforward = "Verlusttopf allgemein zum 1.1.")
DATENBASIS_SECTION_LABELS_V1 <- c(stands = "Stände je Datenart", accounts = "Konten und Buchungen", assets = "Assets und Kurse",
                                  fx = "Wechselkurse", statements = "Belege", settings = "Einstellungen")

datenbasis_ui_v1 <- function() {
  table <- function(id, height = NULL) shiny::div(class = "pl-table-wrap", style = if (is.null(height)) NULL else paste0("max-height:", height, "px;overflow:auto"),
                                                   shiny::tableOutput(id))
  shiny::tagList(
    shiny::p(class = "pl-section-copy", paste(
      "Grundlagen statt Ergebnisse: was hinterlegt ist, woher es kommt, wie weit es reicht und wie alles eingestellt ist – so, wie es",
      "zuletzt veröffentlicht wurde. Werte, GuV, Stichtag und Momentaufnahme zeigt die Analyse.")),
    shiny::uiOutput("datenbasis_state"),
    # Rubriken als Reiter wie in Data (#422, Festlegung 27.10.2026): vorher neun Karten untereinander.
    shiny::div(class = "pl-workspace-tabs", shiny::tabsetPanel(id = "datenbasis_section",
      shiny::tabPanel("1. Stände", value = "stands",
        portelyra_card("Stand je Datenart", help = "app-cockpit#stände", copy = "Bis wann jede Datenart reicht. Cash kommt mit den Auszügen, Rewards mit dem Import, Kurse mit dem Abruf.",
          table("datenbasis_stands"),
          shiny::tags$details(shiny::tags$summary("Frische je Ebene im jüngsten Stichtags-Snapshot"), table("datenbasis_freshness"))),
        portelyra_card("Bereitschaft des Abschlusses", help = "app-cockpit#stände", copy = "Welche Stufen der letzte Abschluss erreicht hat.",
          shiny::uiOutput("datenbasis_closing"), table("datenbasis_stages"))),
      shiny::tabPanel("2. Konten und Cash", value = "accounts",
        portelyra_card("Konten und Buchungen", help = "app-cockpit#konten-und-cash", copy = paste(
          "Je Konto die Buchungen nach Art und ihr Zeitraum, bei Cash-Konten die eingelesenen Auszüge. Beträge stehen hier nicht."),
          table("datenbasis_accounts", 560),
          # Ruhende und geschlossene Konten zugeklappt (#529 Punkt 1); sie zaehlen weiter, stehen aber nicht im Weg.
          shiny::uiOutput("datenbasis_accounts_more")),
        portelyra_card("Cash je Konto laut Auszug", help = "app-cockpit#konten-und-cash", copy = "Saldo und Datum je Konto, belegt aus dem Auszug oder aus Bewegungen abgeleitet.",
          shiny::checkboxInput("datenbasis_show_small_cash", "Kleinstbestände zeigen", FALSE), shiny::uiOutput("datenbasis_small_cash"),
          table("datenbasis_cash", 420))),
      shiny::tabPanel("3. Assets und Kurse", value = "assets",
        portelyra_card("Bestand je Asset", help = "app-cockpit#assets-und-kurse", copy = paste(
          "Stückzahl zum Stichtag des jüngsten Snapshots; ob das Asset im Marktwert zählt und, wenn nicht, warum. Liegt ein Asset",
          "auf mehreren Konten, klappt „Konten“ auf, wie viel wo liegt."),
          shiny::div(class = "pl-table-wrap", style = "max-height:520px;overflow:auto", shiny::uiOutput("datenbasis_holdings"))),
        portelyra_card("Assets, Kurszuordnung und Kursstand", help = "app-cockpit#assets-und-kurse", copy = paste(
          "Wie jedes Asset bewertet wird, an welcher Notierung seine Kurse hängen und wie weit sie reichen. Archivierte Assets stehen nur da,",
          "solange sie im Bestand sind."),
          table("datenbasis_assets", 560), shiny::uiOutput("datenbasis_assets_note")),
        portelyra_card("Wechselkurse", help = "app-cockpit#assets-und-kurse", copy = "Je Währungspaar die Tage mit Kurs, ihre Quelle und der Zeitraum, in dem die Bewertung sie nutzt.",
          table("datenbasis_fx"))),
      shiny::tabPanel("4. Belege", value = "statements",
        portelyra_card("Belege der Ablage je Jahr", help = "app-cockpit#belege", copy = paste(
          "Je Jahr, Institut und Konto die Belege und die Monate: belegt, unbestätigt, als nicht vorhanden erklärt oder offen (Bewegung",
          "ohne Beleg). Ein Monat ohne Bewegung zählt nicht; ein Beleg für mehrere Konten zählt bei jedem Konto, beim Institut einmal."),
          shiny::uiOutput("datenbasis_statements"))),
      shiny::tabPanel("5. Einstellungen", value = "settings",
        portelyra_card("Einstellungen", help = "app-cockpit#einstellungen", copy = "Was die Rechnung steuert. Geändert wird es in der App „Daten“; hier steht der zuletzt veröffentlichte Stand.",
          # Umfang je Portfolio (#542): nur bei veroeffentlichtem Umfang.
          shiny::uiOutput("datenbasis_scope", class = "pl-scope-slot"),
          shiny::tags$h4("Steuer je Jahr"), table("datenbasis_tax_years"),
          shiny::tags$h4("Steuerangaben je Institut"), shiny::uiOutput("datenbasis_institution_tax"),
          shiny::tags$h4("Abschluss"), table("datenbasis_run_center"),
          shiny::tags$h4("Bewertung je Coin und Wallet"), table("datenbasis_crypto_methods", 360),
          shiny::tags$h4("FIFO-Wallets aus mehreren Konten"), table("datenbasis_fifo_wallets"),
          shiny::tags$h4("Cash-Konten zur Anlage"), table("datenbasis_investment_scope", 360),
          shiny::tags$h4("Anzeige"), table("datenbasis_display"))))))
}

.datenbasis_text_v1 <- function(value, fallback = "–") {
  if (is.null(value) || length(value) != 1L || is.na(value) || !nzchar(as.character(value))) fallback else as.character(value)
}
.datenbasis_day_v1 <- function(value) {
  text <- .datenbasis_text_v1(value, "")
  parsed <- if (nzchar(text)) tryCatch(as.Date(text), error = function(error) NA) else NA
  if (is.na(parsed)) "–" else format(parsed, "%d.%m.%Y")
}
.datenbasis_span_v1 <- function(from, to) {
  if (is.null(from) && is.null(to)) return("–")
  paste(.datenbasis_day_v1(from), "–", .datenbasis_day_v1(to))
}
.datenbasis_label_v1 <- function(labels, value) {
  text <- .datenbasis_text_v1(value, "")
  if (!nzchar(text)) "–" else if (text %in% names(labels)) unname(labels[[text]]) else text
}
.datenbasis_yes_no_v1 <- function(value, unset = "nicht festgelegt") if (isTRUE(value)) "ja" else if (isFALSE(value)) "nein" else unset
.datenbasis_frame_v1 <- function(rows, columns) {
  if (!length(rows)) return(data.frame())
  frame <- as.data.frame(do.call(rbind, lapply(rows, function(row) unlist(row, use.names = FALSE))), stringsAsFactors = FALSE)
  names(frame) <- columns
  frame
}
# Ein Teil, den die Data-App nicht lesen konnte, steht als solcher da - nicht als leere Tabelle.
.datenbasis_unreadable_v1 <- function() data.frame(Hinweis = "Nicht lesbar, als die Datenbasis veröffentlicht wurde. Der nächste „Alles aktualisieren“ versucht es erneut.",
                                                   check.names = FALSE)
.datenbasis_section_v1 <- function(basis, name) if (is.list(basis) && is.list(basis$sections)) basis$sections[[name]] else NULL

# Stand je Datenart aus der Datenbasis - dieselbe Tabelle wie in „Alles aktualisieren“ (apps/shared/data_stands_ui_v1.R). `modules`:
# die Bausteine eines veroeffentlichten Umfangs (#542) oder NULL - ein abgeschalteter steht als „nicht geführt, wie gewählt (Umfang)“ da.
datenbasis_stands_frame_v1 <- function(basis, modules = NULL) {
  part <- .datenbasis_section_v1(basis, "stands")
  if (is.null(part)) return(data.frame())
  if (!identical(part$status, "available")) return(.datenbasis_unreadable_v1())
  data_stands_frame_v1(part, modules)
}

# Welche Gruppe ein Konto bildet (#529 Punkt 1): aktiv, ruhend (inaktiv seit) oder geschlossen bzw. archiviert. Die beiden letzten
# stehen zugeklappt unter den aktiven; Bestand und Buchungen zaehlen weiter.
datenbasis_account_group_v1 <- function(row) {
  if (!is.null(row$closed_on) || !identical(row$account_status, "active")) "closed" else if (!is.null(row$inactive_since)) "resting" else "active"
}
DATENBASIS_OPENING_ORIGINS_V1 <- c(statement = "aus Auszug belegt", check_balance = "aus Prüf-Saldo abgeleitet", assumed = "angenommen, ohne Saldo",
                                   manual = "eigene Angabe")
datenbasis_account_counts_v1 <- function(basis) {
  part <- .datenbasis_section_v1(basis, "accounts")
  groups <- if (is.list(part) && identical(part$status, "available")) vapply(part$rows, datenbasis_account_group_v1, character(1L)) else character()
  c(active = sum(groups == "active"), resting = sum(groups == "resting"), closed = sum(groups == "closed"))
}
datenbasis_accounts_frame_v1 <- function(basis, group = "active") {
  part <- .datenbasis_section_v1(basis, "accounts")
  if (is.null(part)) return(data.frame())
  if (!identical(part$status, "available")) return(.datenbasis_unreadable_v1())
  picked <- Filter(function(row) identical(datenbasis_account_group_v1(row), group), part$rows)
  if (!length(picked)) return(data.frame())
  rows <- lapply(picked, function(row) {
    count <- function(field) as.integer(if (is.null(row[[field]])) 0L else row[[field]])
    bookings <- count("booking_count")
    kinds <- c(Handel = count("trade_count"), `Erträge` = count("income_count"), Bewegungen = count("movement_count"))
    kinds <- kinds[kinds > 0L]
    cash_type <- isTRUE(row$account_type %in% c("cash", "bank"))
    periods <- count("statement_period_count")
    state <- if (!is.null(row$closed_on)) paste0(" (geschlossen seit ", .datenbasis_day_v1(row$closed_on), ")")
             else if (!identical(row$account_status, "active")) " (archiviert)"
             else if (!is.null(row$inactive_since)) paste0(" (inaktiv seit ", .datenbasis_day_v1(row$inactive_since), ")") else ""
    origin <- .datenbasis_text_v1(row$opening_origin, "")
    opening <- if (!cash_type || is.null(row$opening_balance_decimal)) "" else paste0(pl_amount_v1(row$opening_balance_decimal, .datenbasis_text_v1(row$opening_currency, ""), 2L, "–"),
      if (origin %in% names(DATENBASIS_OPENING_ORIGINS_V1)) paste0(" · ", DATENBASIS_OPENING_ORIGINS_V1[[origin]]) else "")
    list(.datenbasis_text_v1(row$institution_label, "ohne Institut"),
         paste0(row$account_label, state),
         .datenbasis_label_v1(DATENBASIS_ACCOUNT_TYPES_V1, row$account_type),
         if (!bookings) "–" else paste0(bookings, if (length(kinds)) paste0(" (", paste(names(kinds), kinds, collapse = " · "), ")") else ""),
         if (count("asset_count")) as.character(count("asset_count")) else "–",
         if (!bookings) "–" else .datenbasis_span_v1(row$first_date, row$last_date),
         if (!periods && !count("cash_event_count")) "–"
         else paste0(periods, if (periods == 1L) " Zeitraum" else " Zeiträume", if (!is.null(row$cash_through)) paste0(", bis ", .datenbasis_day_v1(row$cash_through)) else "",
                     if (count("cash_event_count")) paste0(" · ", count("cash_event_count"), " Bewegungen") else ""),
         if (cash_type && !is.null(row$reconciled_from)) .datenbasis_day_v1(row$reconciled_from) else "", opening,
         if (cash_type) .datenbasis_yes_no_v1(row$in_investment) else "",
         .datenbasis_text_v1(row$fifo_wallet_label, ""))
  })
  .datenbasis_frame_v1(rows, c("Institut", "Konto", "Art", "Buchungen", "Assets", "Zeitraum", "Cash laut Auszug", "Abgeglichen ab", "Anfangssaldo",
                               "Zur Anlage", "FIFO-Wallet"))
}

datenbasis_assets_frame_v1 <- function(basis) {
  part <- .datenbasis_section_v1(basis, "assets")
  if (is.null(part)) return(data.frame())
  if (!identical(part$status, "available")) return(.datenbasis_unreadable_v1())
  rows <- lapply(part$rows, function(row) {
    listing <- row$listing
    valuation <- .datenbasis_label_v1(DATENBASIS_VALUATION_V1, row$valuation_method)
    if (identical(row$valuation_method, "manual") && !is.null(row$manual_price_count))
      valuation <- paste0(valuation, " (", row$manual_price_count, if (!is.null(row$manual_price_last)) paste0(", zuletzt ", .datenbasis_day_v1(row$manual_price_last)) else "", ")")
    notation <- if (!is.list(listing)) (if (identical(row$valuation_method, "external_market")) "keine Zuordnung" else "–")
      else paste0(paste(c(listing$provider_symbol, listing$exchange_code, listing$provider_currency), collapse = " · "),
                  if (!identical(listing$verification_status, "verified")) " · ungeprüft" else "", if (!isTRUE(listing$enabled)) " · abgeschaltet" else "")
    prices <- if (is.null(row$valued_from) && is.null(row$valued_through)) (if (identical(row$valuation_method, "external_market")) "noch keine" else "–")
              else .datenbasis_span_v1(row$valued_from, row$valued_through)
    list(paste0(row$asset_label, if (!identical(row$asset_status, "active")) " (archiviert)" else ""),
         .datenbasis_label_v1(DATENBASIS_ASSET_TYPES_V1, row$asset_type), valuation,
         # Kursanbieter je Asset (rc.384, #495): der Name, nicht die Kennung der Zuordnung.
         if (is.list(listing)) pl_price_provider_series_label_v1(listing$provider_id, listing$provider_symbol) else "–", notation, prices,
         if (isTRUE(row$held)) "ja" else "nein", if (isTRUE(row$isin_present)) "ja" else "–")
  })
  .datenbasis_frame_v1(rows, c("Asset", "Klasse", "Bewertung", "Anbieter", "Notierung", "Kurse", "Im Bestand", "ISIN"))
}

# Fussnote zur Future-Naeherung (rc.388), nur wenn ein Asset an einem Terminkontrakt haengt.
datenbasis_assets_note_v1 <- function(basis) {
  part <- .datenbasis_section_v1(basis, "assets")
  if (is.null(part) || !identical(part$status, "available")) return(NULL)
  pl_price_series_future_note_v1(vapply(part$rows, function(row) is.list(row$listing) && pl_price_series_is_future_v1(row$listing$provider_id, row$listing$provider_symbol), logical(1L)))
}

# Wechselkurse gehoeren zu den Marktdaten (#542): ohne sie fehlt keiner, sie werden nicht gefuehrt.
datenbasis_fx_frame_v1 <- function(basis, modules = NULL) {
  part <- .datenbasis_section_v1(basis, "fx")
  if (is.null(part)) return(data.frame())
  if (!identical(part$status, "available")) return(.datenbasis_unreadable_v1())
  if (!length(part$rows) && is.list(modules) && isFALSE(modules[["market_data"]]))
    return(data.frame(Hinweis = "Wechselkurse nicht geführt, wie gewählt (Umfang): Marktdaten sind im Umfang nicht eingeschaltet.", check.names = FALSE))
  if (!length(part$rows)) return(data.frame(Hinweis = "Noch kein Wechselkurs hinterlegt.", check.names = FALSE))
  rows <- lapply(part$rows, function(row) list(
    paste0(row$base_currency, "/", row$quote_currency), as.character(row$observed_day_count),
    .datenbasis_span_v1(row$first_date, row$last_date),
    if (length(row$source_kinds)) paste(vapply(row$source_kinds, function(kind) .datenbasis_label_v1(DATENBASIS_FX_SOURCES_V1, kind), character(1L)), collapse = ", ") else "–",
    if (is.null(row$effective_from) && is.null(row$effective_through)) "–" else .datenbasis_span_v1(row$effective_from, row$effective_through)))
  .datenbasis_frame_v1(rows, c("Paar", "Tage mit Kurs", "Zeitraum", "Quelle", "In der Bewertung"))
}

datenbasis_statements_frame_v1 <- function(basis) {
  part <- .datenbasis_section_v1(basis, "statements")
  if (is.null(part)) return(data.frame())
  if (!identical(part$status, "available")) return(.datenbasis_unreadable_v1())
  rows <- lapply(rev(part$rows), function(row) list(
    as.character(row$year), as.character(row$document_count),
    if (length(row$kinds)) paste(vapply(row$kinds, function(kind) paste0(.datenbasis_label_v1(DATENBASIS_DOCUMENT_KINDS_V1, kind$document_kind), " ", kind$count), character(1L)), collapse = " · ") else "–",
    as.character(row$confirmed_months), as.character(row$unconfirmed_months), as.character(row$not_available_months), as.character(row$open_months)))
  .datenbasis_frame_v1(rows, c("Jahr", "Belege", "Arten", "Monate belegt", "unbestätigt", "als nicht vorhanden erklärt", "offen"))
}

# Je Jahr ein Bereich (#529 Punkt 6): Institut, darunter seine Konten, mit den Zahlen je Ebene; das neueste Jahr offen. Eine Datenbasis
# vor rc.351 kennt die Gliederung nicht - dann steht je Jahr nur die Jahreszeile.
DATENBASIS_STATEMENT_COLUMNS_V1 <- c("Institut / Konto", "Belege", "Monate belegt", "unbestätigt", "als nicht vorhanden erklärt", "offen")
datenbasis_statements_ui_v1 <- function(basis) {
  part <- .datenbasis_section_v1(basis, "statements")
  if (is.null(part)) return(NULL)
  if (!identical(part$status, "available")) return(pl_frame_table_v1(.datenbasis_unreadable_v1()))
  counts <- function(row) lapply(c("document_count", "confirmed_months", "unconfirmed_months", "not_available_months", "open_months"),
                                 function(field) as.character(if (is.null(row[[field]])) 0L else row[[field]]))
  pl_year_groups_v1(lapply(rev(part$rows), function(row) {
    kinds <- if (length(row$kinds)) paste(vapply(row$kinds, function(kind) paste0(.datenbasis_label_v1(DATENBASIS_DOCUMENT_KINDS_V1, kind$document_kind), " ", kind$count), character(1L)), collapse = " · ") else ""
    lines <- list()
    for (group in row$institutions) {
      lines[[length(lines) + 1L]] <- c(list(shiny::tags$strong(.datenbasis_text_v1(group$institution_label, "ohne Institut"))), counts(group))
      for (account in group$accounts) lines[[length(lines) + 1L]] <- c(list(shiny::tags$span(style = "padding-left:1.4em", account$account_label)), counts(account))
    }
    if (is.null(row$institutions)) lines <- list(c(list("alle Konten"), counts(row)))
    list(title = as.character(row$year),
         summary = sprintf("%s %s · %s Monate belegt · %s offen", row$document_count, if (identical(as.integer(row$document_count), 1L)) "Beleg" else "Belege",
                           row$confirmed_months, row$open_months),
         body = shiny::tagList(if (nzchar(kinds)) shiny::p(class = "pl-field-hint", paste0("Arten: ", kinds)),
                               if (length(lines)) shiny::div(class = "pl-table-wrap", pl_table_v1(DATENBASIS_STATEMENT_COLUMNS_V1, lines))
                               else shiny::p(class = "pl-field-hint", "Kein Beleg und kein offener Monat.")))
  }))
}

# Einstellungen: je Teil eine Tabelle. Saetze und Betraege stehen so, wie sie eingegeben sind.
.datenbasis_settings_part_v1 <- function(basis, name) {
  part <- .datenbasis_section_v1(basis, "settings")
  if (is.null(part)) return(NULL)
  if (!identical(part$status, "available")) return(list(status = "unavailable"))
  part[[name]]
}
.datenbasis_rate_v1 <- function(value) { text <- .datenbasis_text_v1(value, ""); if (nzchar(text)) paste0(sub(".", ",", text, fixed = TRUE), " %") else "–" }
.datenbasis_amount_v1 <- function(value) { text <- .datenbasis_text_v1(value, ""); if (nzchar(text)) paste0(sub(".", ",", text, fixed = TRUE), " €") else "–" }

datenbasis_tax_years_frame_v1 <- function(basis) {
  part <- .datenbasis_settings_part_v1(basis, "tax_years")
  if (is.null(part)) return(data.frame())
  if (!identical(part$status, "available")) return(.datenbasis_unreadable_v1())
  if (!length(part$rows)) return(data.frame(Hinweis = "Noch keine Steuereinstellung angelegt.", check.names = FALSE))
  several <- length(unique(vapply(part$rows, function(row) row$portfolio_label, character(1L)))) > 1L
  parameter <- function(row) {
    shown <- vapply(row$parameters, function(item) paste0(data_tax_label_v1(DATENBASIS_TAX_PARAMETERS_V1, item$parameter_code), " ",
      if (identical(item$value_kind, "applicability")) data_tax_label_v1(data_tax_applicability_labels_v1(), item$value)
      else if (identical(item$value_kind, "rate")) .datenbasis_rate_v1(item$value) else .datenbasis_amount_v1(item$value)), character(1L))
    if (length(shown)) paste(shown, collapse = " · ") else "–"
  }
  rows <- lapply(rev(part$rows), function(row) {
    annual <- Filter(function(item) identical(item$projection_mode, "realized_annual"), row$modules)
    list(paste0(row$tax_year, if (several) paste0(" · ", row$portfolio_label) else ""),
         if (length(annual)) data_tax_plugin_label_v1(annual[[1L]]$plugin_id, annual[[1L]]$plugin_version) else "kein Regelmodul gewählt",
         paste(vapply(row$readiness, function(item) paste0(data_tax_mode_label_v1(item$projection_mode), ": ", data_tax_status_label_v1(item$status)), character(1L)), collapse = " · "),
         switch(.datenbasis_text_v1(row$assessment, ""), single = "Einzelveranlagung", joint = "Zusammenveranlagung", "nicht angegeben"),
         if (isFALSE(row$portfolio_counts)) "nein" else "ja", parameter(row))
  })
  .datenbasis_frame_v1(rows, c("Jahr", "Regelmodul", "Bereitschaft", "Veranlagung", "Zählt zur Veranlagung", "Eigene Angaben"))
}

datenbasis_institution_tax_frame_v1 <- function(basis) {
  part <- .datenbasis_settings_part_v1(basis, "institution_tax")
  if (is.null(part)) return(data.frame())
  if (!identical(part$status, "available")) return(.datenbasis_unreadable_v1())
  if (!length(part$rows)) return(data.frame(Hinweis = "Keine Angaben je Institut.", check.names = FALSE))
  # Je Institut und Jahr eine Zeile, je Angabe eine Spalte; was nicht angegeben ist, steht als „–“.
  keys <- unique(vapply(part$rows, function(row) paste(row$institution_label, row$tax_year, sep = "\r"), character(1L)))
  rows <- lapply(keys, function(key) {
    mine <- Filter(function(row) identical(paste(row$institution_label, row$tax_year, sep = "\r"), key), part$rows)
    value <- function(field) { hit <- Filter(function(row) identical(row$field_code, field), mine); if (length(hit)) .datenbasis_amount_v1(hit[[1L]]$amount_decimal) else "–" }
    c(list(paste0(mine[[1L]]$institution_label, if (isTRUE(mine[[1L]]$orphaned)) " (an keinem Konto mehr)" else ""), as.character(mine[[1L]]$tax_year)),
      lapply(names(DATENBASIS_INSTITUTION_FIELDS_V1), value))
  })
  frame <- .datenbasis_frame_v1(rows, c("Institut", "Jahr", unname(DATENBASIS_INSTITUTION_FIELDS_V1)))
  frame[order(tolower(frame$Institut), -as.integer(frame$Jahr)), , drop = FALSE]
}
# Statt des Jahres in jeder Zeile eine Ueberschrift je Jahr, das neueste offen (#529 Punkt 4).
datenbasis_institution_tax_ui_v1 <- function(basis) {
  frame <- datenbasis_institution_tax_frame_v1(basis)
  if (!nrow(frame) || !"Jahr" %in% names(frame)) return(pl_frame_table_v1(frame))
  years <- sort(unique(as.integer(frame$Jahr)), decreasing = TRUE)
  pl_year_groups_v1(lapply(years, function(year) {
    mine <- frame[as.integer(frame$Jahr) == year, setdiff(names(frame), "Jahr"), drop = FALSE]
    list(title = as.character(year), summary = if (nrow(mine) == 1L) "1 Institut" else paste(nrow(mine), "Institute"),
         body = shiny::div(class = "pl-table-wrap", pl_frame_table_v1(mine)))
  }))
}

datenbasis_run_center_frame_v1 <- function(basis) {
  part <- .datenbasis_settings_part_v1(basis, "run_center")
  if (is.null(part)) return(data.frame())
  if (identical(part$status, "unavailable")) return(.datenbasis_unreadable_v1())
  if (identical(part$status, "not_read")) return(data.frame(Hinweis = "Beim letzten „Alles aktualisieren“ nicht gelesen: Der Lauf hielt vor dem Abschluss an.", check.names = FALSE))
  if (identical(part$status, "absent")) return(data.frame(Hinweis = "Für den Abschluss gibt es noch keinen bestätigten Lauf.", check.names = FALSE))
  fee <- switch(.datenbasis_text_v1(part$fee_source, ""), derived_from_transactions = "aus den bisherigen Transaktionen",
                fixed_per_trade = paste0("feste Gebühr je Trade (", .datenbasis_amount_v1(part$fee_fixed_decimal), ")"),
                percentage_of_turnover = paste0("Prozentsatz vom Umsatz (", .datenbasis_rate_v1(part$fee_percentage_rate_decimal), ")"),
                .datenbasis_text_v1(part$fee_source))
  tax <- switch(.datenbasis_text_v1(part$tax_mode, ""), disabled = "ohne Steuermodul", de_reference_v2 = "deutsches Referenzmodell v2",
                de_reference_v1 = "deutsches Referenzmodell v1", .datenbasis_text_v1(part$tax_mode))
  # Ohne eigenen Wert im Run Center gilt das Regelmodul samt Steuerangaben je Jahr; ein Strich las sich wie ein fehlender Wert (#529).
  module <- "aus dem Regelmodul (Steuerangaben je Jahr)"
  rate <- function(value) if (nzchar(.datenbasis_text_v1(value, ""))) .datenbasis_rate_v1(value) else module
  church <- switch(.datenbasis_text_v1(part$church_tax_applicable, ""), applicable = paste0("fällt an (", .datenbasis_rate_v1(part$church_tax_rate), ")"),
                   not_applicable = "fällt nicht an", module)
  values <- c(`Letzter Stichtag` = .datenbasis_day_v1(part$last_as_of_date), Portfolio = .datenbasis_text_v1(part$portfolio_label),
              Modus = if (identical(part$run_mode, "incremental")) "inkrementell" else if (identical(part$run_mode, "full")) "vollständig" else .datenbasis_text_v1(part$run_mode),
              Steuer = tax, Abgeltungsteuersatz = rate(part$capital_income_tax_rate),
              `Persönlicher Steuersatz` = rate(part$personal_income_tax_rate),
              `Solidaritätszuschlag` = rate(part$solidarity_surcharge_rate), Kirchensteuer = church,
              `Gebührenquelle (Verkauf gedacht)` = fee)
  # Die Gruppierung steht fest auf "none" (keine) und war nur als englischer Altwert zu sehen; sie erscheint nur, wenn sie gesetzt ist.
  grouping <- .datenbasis_text_v1(part$grouping_mode, "")
  if (nzchar(grouping) && !identical(grouping, "none")) values <- c(values, Gruppierung = grouping)
  frame <- data.frame(Eingabe = names(values), Wert = unname(values), stringsAsFactors = FALSE, check.names = FALSE)
  if (identical(part$status, "not_reusable"))
    frame <- rbind(frame, data.frame(Eingabe = "Hinweis", Wert = "Der letzte Lauf lässt sich nicht übernehmen; bitte den Abschluss neu bestätigen.", check.names = FALSE))
  frame
}

datenbasis_crypto_methods_frame_v1 <- function(basis) {
  part <- .datenbasis_settings_part_v1(basis, "crypto_methods")
  if (is.null(part)) return(data.frame())
  if (!identical(part$status, "available")) return(.datenbasis_unreadable_v1())
  if (!length(part$rows)) return(data.frame(Hinweis = "Keine eigene Wahl: Jeder Coin rechnet nach FIFO.", check.names = FALSE))
  rows <- lapply(part$rows, function(row) list(.datenbasis_text_v1(row$asset_label), .datenbasis_text_v1(row$account_label),
    if (identical(row$method, "average")) "Durchschnitt" else "FIFO", .datenbasis_day_v1(row$valid_from)))
  .datenbasis_frame_v1(rows, c("Coin", "Konto", "Methode", "Gültig ab"))
}

datenbasis_fifo_wallets_frame_v1 <- function(basis) {
  part <- .datenbasis_settings_part_v1(basis, "fifo_wallets")
  if (is.null(part)) return(data.frame())
  if (!identical(part$status, "available")) return(.datenbasis_unreadable_v1())
  if (!length(part$rows)) return(data.frame(Hinweis = "Keine: Jedes Konto rechnet für sich.", check.names = FALSE))
  rows <- lapply(part$rows, function(row) list(.datenbasis_text_v1(row$wallet_label), .datenbasis_text_v1(row$institution_label, "ohne Institut"),
    paste(unlist(row$member_labels), collapse = ", ")))
  .datenbasis_frame_v1(rows, c("Hauptkonto", "Institut", "Weitere Konten"))
}

datenbasis_investment_scope_frame_v1 <- function(basis) {
  part <- .datenbasis_settings_part_v1(basis, "investment_scope")
  if (is.null(part)) return(data.frame())
  if (!identical(part$status, "available")) return(.datenbasis_unreadable_v1())
  if (!length(part$rows)) return(data.frame(Hinweis = "Keine Cash-Konten.", check.names = FALSE))
  rows <- lapply(part$rows, function(row) list(.datenbasis_text_v1(row$institution_label, "ohne Institut"), row$account_label,
    .datenbasis_label_v1(DATENBASIS_ACCOUNT_TYPES_V1, row$account_type), .datenbasis_yes_no_v1(row$in_investment, "nicht festgelegt (zählt nach Kontoart)")))
  .datenbasis_frame_v1(rows, c("Institut", "Konto", "Art", "Zur Anlage"))
}

datenbasis_display_frame_v1 <- function(basis) {
  part <- .datenbasis_settings_part_v1(basis, "display")
  if (is.null(part)) return(data.frame())
  if (!identical(part$status, "available")) return(.datenbasis_unreadable_v1())
  periods <- c(`1m` = "1 Monat", `3m` = "3 Monate", qtd = "Quartal bis heute", ytd = "Jahr bis heute", `1y` = "1 Jahr", `3y` = "3 Jahre", `5y` = "5 Jahre", all = "Alles")
  zones <- .datenbasis_text_v1(part$drawdown_zones, "")
  values <- c(`Nachkommastellen in Übersichten` = as.character(part$amount_decimals),
              `Farbige Hinterlegung` = .datenbasis_yes_no_v1(part$tint, "–"),
              `Rückgangszonen der Analyse` = if (nzchar(zones)) paste0(gsub(",", " %, ", zones, fixed = TRUE), " %") else "keine",
              Expertenwerkzeuge = if (isTRUE(part$expert_tools)) "an" else "aus",
              `Zeitraum, mit dem die Analyse öffnet` = .datenbasis_label_v1(periods, part$analysis_period))
  data.frame(Einstellung = names(values), Wert = unname(values), stringsAsFactors = FALSE, check.names = FALSE)
}

# Umfang je Portfolio (#542): je Portfolio Name, Status, ob eingerichtet, und der Umfang in Worten; darueber der wirksame Umfang des
# Datenraums - ein Baustein laeuft, sobald ein aktives Portfolio ihn nutzt. Nur bei veroeffentlichtem Umfang (`scope` sonst NULL).
datenbasis_scope_frame_v1 <- function(scope) {
  rows <- if (is.list(scope) && is.list(scope$portfolios)) scope$portfolios else list()
  if (!length(rows)) return(data.frame())
  .datenbasis_frame_v1(lapply(rows, function(row) list(.datenbasis_text_v1(row$label),
    if (identical(row$status, "archived")) "archiviert" else "aktiv",
    if (isTRUE(row$configured)) "ja" else "nein – es gilt alles, bis es eingerichtet ist",
    .datenbasis_text_v1(row$scope_text))), c("Portfolio", "Status", "Eingerichtet", "Umfang"))
}
datenbasis_scope_ui_v1 <- function(scope) {
  text <- if (is.list(scope)) scope$effective_scope_text else NULL
  if (!is.character(text) || length(text) != 1L || is.na(text) || !nzchar(text)) return(NULL)
  frame <- datenbasis_scope_frame_v1(scope)
  shiny::tagList(
    shiny::tags$h4("Umfang je Portfolio"),
    shiny::p(class = "pl-field-hint", paste0("Wirksam im Datenraum: ", text, ". Ein Baustein läuft, sobald ein aktives Portfolio ihn nutzt. ",
                                             "Geändert wird der Umfang in Daten → „Einstellungen“ → „Portfolio“ → „Umfang dieses Portfolios“.")),
    if (nrow(frame)) shiny::div(class = "pl-table-wrap", pl_frame_table_v1(frame)))
}

# Bestand in Stueck - ohne Kurs, Wert und Einstand. Positionen im Marktwert und ausgenommene Positionen in einer Liste.
datenbasis_holdings_frame_v1 <- function(snapshot) {
  if (!is.list(snapshot)) return(data.frame())
  text <- function(value, fallback = "–") if (is.null(value) || length(value) != 1L || is.na(value) || !nzchar(as.character(value))) fallback else as.character(value)
  kind <- function(value) { label <- DATENBASIS_ASSET_TYPES_V1[text(value, "")]; if (is.na(label)) text(value) else unname(label) }
  # Alle Stellen des exakten Bestands, ohne Nullen am Ende (#529 Punkt 8).
  quantity <- function(value) pl_quantity_v1(value, "–")
  held <- lapply(snapshot$positions, function(row) c(text(row$asset_name, substr(text(row$asset_id), 1L, 16L)), kind(row$asset_type),
                                                     quantity(row$quantity_decimal), "ja"))
  apart <- lapply(snapshot$excluded_positions, function(row) c(text(row$asset_name, substr(text(row$asset_id), 1L, 16L)), kind(row$asset_type),
    quantity(row$quantity_decimal),
    # Nach Eigentuemerwahl ohne Marktbewertung ("nur Transaktionen") braucht keinen weiteren Grund; bei einer Luecke steht er dabei.
    if (isTRUE(row$owner_excluded)) "nein · nur mit Transaktionen geführt (Eigentümerwahl)"
    else paste0("nein · Lücke", if (nzchar(text(row$reason, ""))) paste0(": ", sub(" \\([a-z_]+\\)$", "", row$reason)) else "")))
  rows <- c(held, apart)
  if (!length(rows)) return(data.frame())
  frame <- as.data.frame(do.call(rbind, rows), stringsAsFactors = FALSE)
  names(frame) <- c("Asset", "Klasse", "Bestand (Stück)", "Im Marktwert")
  frame[order(tolower(frame$Asset)), , drop = FALSE]
}

# Je Asset die Konten (#529 Punkt 7, wie „Bestand je Konto / Wallet“ in Manuell seit rc.335). Die Mengen je Konto stammen aus der
# Datenbasis (Stichtag der Datenbasis), der Bestand aus dem Snapshot; weicht die Summe ab, weil dazwischen gebucht wurde, steht
# der Tag der Konten dabei. Ein Name, den zwei Assets tragen, bekommt keine Konten - die Zuordnung waere nicht eindeutig.
datenbasis_holdings_ui_v1 <- function(snapshot, basis = NULL) {
  frame <- datenbasis_holdings_frame_v1(snapshot)
  if (!nrow(frame)) return(NULL)
  part <- .datenbasis_section_v1(basis, "assets")
  rows <- if (is.list(part) && identical(part$status, "available")) part$rows else list()
  labels <- vapply(rows, function(row) as.character(row$asset_label), character(1L))
  day <- if (is.list(basis) && !is.null(basis$as_of_date)) .datenbasis_day_v1(basis$as_of_date) else "–"
  accounts <- lapply(seq_len(nrow(frame)), function(index) {
    hit <- which(labels == frame$Asset[[index]])
    if (length(hit) != 1L || is.null(rows[[hit]]$custody)) return("–")
    custody <- rows[[hit]]$custody
    if (!length(custody)) return("–")
    shown <- vapply(custody, function(item) paste0(item$account_label, if (!is.null(item$institution_label)) paste0(" (", item$institution_label, ")") else "",
                                                     ": ", pl_quantity_v1(item$quantity_decimal, "–")), character(1L))
    differs <- !identical(pl_quantity_v1(rows[[hit]]$held_quantity_decimal, "–"), frame[["Bestand (Stück)"]][[index]])
    note <- if (differs) paste0("Stand ", day, ", zusammen ", pl_quantity_v1(rows[[hit]]$held_quantity_decimal, "–"), " Stück") else NULL
    if (length(custody) == 1L && !differs) return(custody[[1L]]$account_label)
    pl_cell_more_v1(paste0(length(custody), if (length(custody) == 1L) " Konto" else " Konten", if (differs) paste0(" · Stand ", day) else ""), c(shown, note))
  })
  pl_table_v1(c("Asset", "Klasse", "Bestand (Stück)", "Konten", "Im Marktwert"),
              lapply(seq_len(nrow(frame)), function(index) list(frame$Asset[[index]], frame$Klasse[[index]], frame[["Bestand (Stück)"]][[index]],
                                                                accounts[[index]], frame[["Im Marktwert"]][[index]])))
}

# Kopf: Stand der Datenbasis und des Snapshots. `basis` ist list(value = ..., code = ...): value die gelesene Datenbasis, code der
# sichere Fehlercode, wenn sie fehlt oder nicht lesbar ist.
datenbasis_state_ui_v1 <- function(basis, snapshot) {
  value <- if (is.list(basis)) basis$value else NULL
  if (!is.list(value)) {
    absent <- is.list(basis) && identical(basis$code, "display_no_latest")
    return(portelyra_status_panel(if (absent) "Noch keine Datenbasis veröffentlicht" else "Datenbasis nicht lesbar",
      if (absent) "„Alles aktualisieren“ in der App „Daten“ veröffentlicht sie zum Schluss. Bis dahin stehen hier nur Bestand, Cash und Abschluss aus dem Snapshot."
      else pl_error_text_v1(.datenbasis_text_v1(basis$code, "unbekannt")), tone = if (absent) "neutral" else "warning"))
  }
  open <- names(Filter(function(part) !identical(part$status, "available"), value$sections))
  at <- tryCatch(format(as.POSIXct(value$completed_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), "%d.%m.%Y %H:%M", tz = "Europe/Berlin"), error = function(error) "–")
  shiny::tagList(
    portelyra_status_panel(paste0("Stand der Datenbasis: ", at, " Uhr"),
      paste0("Veröffentlicht mit „Alles aktualisieren“ in der App „Daten“. ",
             if (length(open)) paste0("Nicht lesbar war: ", paste(unname(DATENBASIS_SECTION_LABELS_V1[open]), collapse = ", "), ".")
             else "Alle Teile waren lesbar."), tone = if (length(open)) "warning" else "neutral"),
    if (is.list(snapshot)) shiny::p(class = "pl-field-hint", paste0("Bestand und Cash je Konto stammen aus dem jüngsten Stichtags-Snapshot vom ",
      format(as.Date(snapshot$as_of_date), "%d.%m.%Y"), if (identical(snapshot$snapshot_status, "complete")) " · vollständig" else " · unvollständig", ".")))
}

# `threshold`: Grenze fuer Kleinstbestaende aus den Einstellungen (#534); ausgeblendet wird nur in der Anzeige.
# `scope`: der veroeffentlichte Umfang je Portfolio (#542) oder NULL - dann sieht alles aus wie bisher.
datenbasis_server_v1 <- function(input, output, session, snapshot, workflow, basis = shiny::reactive(NULL), threshold = shiny::reactive("1"),
                                 scope = shiny::reactive(NULL)) {
  modules <- shiny::reactive({ current <- scope(); if (is.list(current) && is.list(current$modules)) current$modules else NULL })
  output$datenbasis_scope <- shiny::renderUI(datenbasis_scope_ui_v1(scope()))
  shiny::outputOptions(output, "datenbasis_scope", suspendWhenHidden = FALSE)   # leer ausgeblendet (.pl-scope-slot), sonst nie berechnet
  small <- shiny::reactive(desktop_snapshot_small_holdings_v1(snapshot(), threshold()))
  cash_view <- shiny::reactive(if (isTRUE(input$datenbasis_show_small_cash)) snapshot() else small()$model)
  output$datenbasis_small_cash <- shiny::renderUI({ text <- desktop_snapshot_small_holdings_note_v1(small(), input$datenbasis_show_small_cash)
    if (!is.null(text)) shiny::p(class = "pl-field-hint", text) })
  value <- shiny::reactive({ current <- basis(); if (is.list(current)) current$value else NULL })
  # Der Ausdruck wird je Lauf neu ausgewertet: Als einfaches Argument weitergereicht, waere er ein einmal ausgewertetes Versprechen,
  # und die Tabelle bliebe nach „Neu lesen“ (und nach einem neuen Umfang, #542) beim ersten Stand stehen.
  table <- function(expr, ...) shiny::renderTable(substitute(expr), striped = TRUE, spacing = "xs", width = "100%", ..., env = parent.frame(), quoted = TRUE)
  output$datenbasis_state <- shiny::renderUI(datenbasis_state_ui_v1(basis(), snapshot()))
  output$datenbasis_stands <- table(datenbasis_stands_frame_v1(value(), modules()))
  output$datenbasis_freshness <- table(desktop_snapshot_freshness_frame_v1(snapshot()))
  output$datenbasis_accounts <- table(datenbasis_accounts_frame_v1(value()))
  output$datenbasis_accounts_more <- shiny::renderUI({
    counts <- datenbasis_account_counts_v1(value())
    shiny::tagList(
      if (counts[["resting"]] > 0L) shiny::tags$details(shiny::tags$summary(sprintf("Ruhende Konten (%d) · inaktiv, Bestand zählt weiter", counts[["resting"]])),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("datenbasis_accounts_resting"))),
      if (counts[["closed"]] > 0L) shiny::tags$details(shiny::tags$summary(sprintf("Geschlossene und archivierte Konten (%d)", counts[["closed"]])),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("datenbasis_accounts_closed"))))
  })
  output$datenbasis_accounts_resting <- table(datenbasis_accounts_frame_v1(value(), "resting"))
  output$datenbasis_accounts_closed <- table(datenbasis_accounts_frame_v1(value(), "closed"))
  output$datenbasis_holdings <- shiny::renderUI(datenbasis_holdings_ui_v1(snapshot(), value()))
  output$datenbasis_cash <- shiny::renderTable({
    frame <- desktop_snapshot_cash_frame_v1(cash_view())
    if (!nrow(frame) && is.list(modules()) && isFALSE(modules()[["cash"]])) data.frame(Hinweis = "Cash nicht geführt, wie gewählt (Umfang).", check.names = FALSE) else frame
  }, striped = TRUE, bordered = TRUE)
  output$datenbasis_assets <- table(datenbasis_assets_frame_v1(value()))
  output$datenbasis_assets_note <- shiny::renderUI(datenbasis_assets_note_v1(value()))
  output$datenbasis_fx <- table(datenbasis_fx_frame_v1(value(), modules()))
  output$datenbasis_statements <- shiny::renderUI(datenbasis_statements_ui_v1(value()))
  output$datenbasis_tax_years <- table(datenbasis_tax_years_frame_v1(value()))
  output$datenbasis_institution_tax <- shiny::renderUI(datenbasis_institution_tax_ui_v1(value()))
  output$datenbasis_run_center <- table(datenbasis_run_center_frame_v1(value()))
  output$datenbasis_crypto_methods <- table(datenbasis_crypto_methods_frame_v1(value()))
  output$datenbasis_fifo_wallets <- table(datenbasis_fifo_wallets_frame_v1(value()))
  output$datenbasis_investment_scope <- table(datenbasis_investment_scope_frame_v1(value()))
  output$datenbasis_display <- table(datenbasis_display_frame_v1(value()))
  # Der Abschluss gehoert einem Portfolio; der veroeffentlichte Umfang gilt dem ganzen Datenraum: nur bei einem aktiven Portfolio eindeutig.
  output$datenbasis_closing <- shiny::renderUI(desktop_workflow_status_ui_v1(workflow(),
    if (exists("desktop_scope_single_portfolio_modules_v1", mode = "function")) desktop_scope_single_portfolio_modules_v1(scope()) else NULL))
  output$datenbasis_stages <- shiny::renderTable(desktop_workflow_stage_frame_v1(workflow()$model), striped = TRUE, bordered = TRUE)
  invisible(NULL)
}
