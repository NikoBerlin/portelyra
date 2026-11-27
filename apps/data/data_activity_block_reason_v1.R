# Aus dem Grund eines blockierten Entwurfs wird ein Satz fuer den Eigentuemer (#420).
#
# Der Kern weiss genau, warum er ablehnt; auf dem Weg zur Oberflaeche blieb davon
# ein Sammelcode und "Aktion blockiert". Der Grund kommt vom nur lesenden Aufruf
# activity-draft-explain (migrations/reference/desktop_activity_block_reason_v1.py)
# und traegt interne Kennungen von Konto und Asset. Hier werden daraus
# Bezeichnungen: `label(kind, internal_id)` liefert sie aus der Auswahl der
# Sitzung oder NULL. Kennungen, Pfade und Fingerprints gehen nicht in den Text.

.data_activity_block_reason_scalar_v1 <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value)
}

.data_activity_block_reason_date_v1 <- function(value) {
  if (!.data_activity_block_reason_scalar_v1(value) || !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", value)) return("einem späteren Tag")
  paste(substr(value, 9L, 10L), substr(value, 6L, 7L), substr(value, 1L, 4L), sep = ".")
}

.data_activity_block_reason_event_types_v1 <- function() c(
  buy = "Kauf", sell = "Verkauf", dividend = "Dividende", stock_dividend = "Stockdividende",
  reward = "Reward", deposit = "Einlieferung", withdrawal = "Auslieferung", transfer = "Transfer"
)

# Der innerste Fehlercode bleibt in Klammern stehen: Mit ihm laesst sich ein Fall
# nachschlagen, auch wenn der Satz davor ihn schon erklaert.
.data_activity_block_reason_code_v1 <- function(explanation) {
  codes <- unlist(explanation$codes)
  if (is.character(codes) && length(codes) && all(grepl("^[a-z][a-z0-9_]{2,120}$", codes))) codes[[length(codes)]] else "activity_draft_domain_invalid"
}

data_activity_block_reason_text_v1 <- function(explanation, label = function(kind, internal_id) NULL) {
  if (!is.list(explanation) || !identical(as.integer(explanation$activity_block_reason_version), 1L) ||
      !.data_activity_block_reason_scalar_v1(explanation$status) || !is.function(label)) {
    stop("data_activity_block_reason_invalid", call. = FALSE)
  }
  name <- function(kind, internal_id, fallback) {
    value <- if (.data_activity_block_reason_scalar_v1(internal_id)) tryCatch(label(kind, internal_id), error = function(error) NULL) else NULL
    if (.data_activity_block_reason_scalar_v1(value)) value else fallback
  }
  code <- .data_activity_block_reason_code_v1(explanation)
  after <- if (identical(explanation$action_type, "void")) "nach dem Storno" else if (identical(explanation$action_type, "create")) "mit dieser Buchung" else "nach dieser Änderung"
  if (identical(explanation$status, "no_longer_blocked")) {
    return(list(code = code, title = "Erneut prüfen",
      copy = "Bei der letzten Prüfung lehnte der Kern ab; inzwischen ginge dieselbe Buchung durch. Bitte die Vorschau neu erstellen."))
  }
  if (!identical(explanation$status, "explained")) {
    return(list(code = code, title = "Aktion blockiert", copy = pl_error_text_v1(code)))
  }
  detail <- explanation$detail
  types <- .data_activity_block_reason_event_types_v1()
  result <- switch(if (.data_activity_block_reason_scalar_v1(explanation$reason)) explanation$reason else "domain_rejected",
    custody_inventory_insufficient = {
      blocking <- if (is.list(detail)) detail$blocking_event else NULL
      if (is.list(blocking)) {
        account <- name("account", blocking$account_ref, "dem Konto")
        type <- if (.data_activity_block_reason_scalar_v1(blocking$event_type) && blocking$event_type %in% names(types)) types[[blocking$event_type]] else "Buchung"
        day <- .data_activity_block_reason_date_v1(blocking$local_date)
        missing <- if (.data_activity_block_reason_scalar_v1(detail$missing_quantity_decimal)) sprintf(" – es fehlen %s", detail$missing_quantity_decimal) else ""
        available <- if (.data_activity_block_reason_scalar_v1(detail$available_quantity_decimal)) detail$available_quantity_decimal else "weniger"
        if (isTRUE(detail$blocking_event_is_changed_event)) list(
          title = sprintf("Bestand auf %s reicht nicht", account),
          copy = sprintf("Diese Buchung selbst braucht am %s %s auf %s; dort liegen zu diesem Zeitpunkt nur %s%s.",
            day, blocking$quantity_decimal, account, available, missing))
        else list(
          title = sprintf("Bestand auf %s reichte danach nicht", account),
          copy = sprintf("Am %s braucht ein %s %s auf %s; %s lägen dort nur %s%s. Zuerst jene Buchung umstellen oder korrigieren, dann diese.",
            day, type, blocking$quantity_decimal, account, after, available, missing))
      } else if (is.list(detail) && .data_activity_block_reason_scalar_v1(detail$blocking_local_date)) list(
        title = "Verwahrbestand reichte danach nicht",
        copy = sprintf("Am %s reicht der Bestand eines Kontos %s für eine Buchung dieses Tages nicht mehr. Welche es ist, ließ sich nicht eindeutig bestimmen, weil die Buchungen des Tages keine genaue Uhrzeit tragen.",
          .data_activity_block_reason_date_v1(detail$blocking_local_date), after))
      else list(
        title = "Verwahrbestand reichte danach nicht",
        copy = sprintf("Der Bestand eines Kontos reicht %s für eine Buchung nicht mehr – etwa einen späteren Verkauf oder Transfer von diesem Konto.", after))
    },
    inventory_insufficient = {
      blocking <- if (is.list(detail)) detail$blocking_event else NULL
      if (is.list(blocking)) {
        type <- if (.data_activity_block_reason_scalar_v1(blocking$event_type) && blocking$event_type %in% names(types)) types[[blocking$event_type]] else "Buchung"
        missing <- if (.data_activity_block_reason_scalar_v1(detail$missing_quantity_decimal)) sprintf(" – es fehlen %s", detail$missing_quantity_decimal) else ""
        available <- if (.data_activity_block_reason_scalar_v1(detail$available_quantity_decimal)) detail$available_quantity_decimal else "weniger"
        list(title = "Bestand des Assets reicht nicht",
          copy = if (isTRUE(detail$blocking_event_is_changed_event)) sprintf("Diese Buchung selbst braucht am %s %s; über alle Konten liegen zu diesem Zeitpunkt nur %s%s.",
            .data_activity_block_reason_date_v1(blocking$local_date), blocking$quantity_decimal, available, missing)
          else sprintf("Am %s braucht ein %s %s; %s lägen über alle Konten nur %s%s. Zuerst jene Buchung korrigieren, dann diese.",
            .data_activity_block_reason_date_v1(blocking$local_date), type, blocking$quantity_decimal, after, available, missing))
      } else list(title = "Bestand des Assets reicht nicht",
        copy = sprintf("Der Bestand des Assets reicht %s für eine Buchung nicht mehr – über alle Konten gerechnet.", after))
    },
    order_evidence_required = list(title = "Gleicher Zeitpunkt – Reihenfolge fehlt",
      copy = "Mehrere Buchungen desselben Assets tragen denselben Zeitpunkt. Der Kern braucht ihre Reihenfolge, bevor er rechnen kann; bei Rewards aus einem Auszug lässt sie sich über „Zeitgleiche Rewards klären“ bestätigen. Ist die andere Buchung schon gebucht, versetzt die Prüfung des Laufs den Reward um ganze Sekunden – außer sie trägt dasselbe Konto und dieselbe Menge (dann ist es vermutlich derselbe Reward)."),
    event_duplicate = list(title = "Diese Buchung gibt es schon",
      copy = "Eine Buchung mit derselben Kennung ist bereits vorhanden."),
    quantity_scale_exceeded = {
      fields <- c(quantity_decimal = "Menge", asset_fee_quantity_decimal = "Mengengebühr", eligible_quantity_decimal = "dividendenberechtigte Menge")
      field <- if (is.list(detail) && .data_activity_block_reason_scalar_v1(detail$field) && detail$field %in% names(fields)) fields[[detail$field]] else "Menge"
      list(title = "Mengenskala des Assets reicht nicht",
        copy = sprintf("%s erlaubt %d Dezimalstellen, die %s hat %d. Die Mengenskala muss zuerst angehoben werden; das wird angeboten, wenn dieselbe Menge im Formular „Neue Transaktion“ von Hand erfasst wird.",
          name("asset", if (is.list(detail)) detail$asset_ref else NULL, "Das Asset"), as.integer(detail$quantity_scale), field, as.integer(detail$decimal_places)))
    },
    amount_fields_conflict = {
      modes <- c(quantity_unit_price = "Menge × Stückpreis", gross_total = "Brutto-Gesamtbetrag", not_applicable = "Nicht anwendbar")
      mode <- if (is.list(detail) && .data_activity_block_reason_scalar_v1(detail$amount_input_mode) && detail$amount_input_mode %in% names(modes)) modes[[detail$amount_input_mode]] else "der gewählten Betragsart"
      wanted <- switch(if (is.list(detail) && .data_activity_block_reason_scalar_v1(detail$amount_input_mode)) detail$amount_input_mode else "",
        quantity_unit_price = "genau der Stückpreis, kein Brutto-Gesamtbetrag", gross_total = "genau der Brutto-Gesamtbetrag, kein Stückpreis",
        not_applicable = "weder Stückpreis noch Brutto-Gesamtbetrag", "genau ein Betragsfeld")
      list(title = "Betragsangaben passen nicht zur Betragsart", copy = sprintf("Zur Betragsart „%s“ gehört %s.", mode, wanted))
    },
    field_not_accepted = {
      fields <- c(monetary_fee_decimal = "keine Geldgebühr", eligible_quantity_decimal = "keine dividendenberechtigte Menge")
      what <- if (is.list(detail) && .data_activity_block_reason_scalar_v1(detail$field) && detail$field %in% names(fields)) fields[[detail$field]] else "diese Angabe nicht"
      type <- if (is.list(detail) && .data_activity_block_reason_scalar_v1(detail$event_type) && detail$event_type %in% names(types)) types[[detail$event_type]] else "dieser Buchungsart"
      list(title = "Angabe gehört nicht zu dieser Buchungsart", copy = sprintf("Bei %s nimmt der Kern %s an. Das Feld leeren und erneut prüfen.", type, what))
    },
    list(title = "Vom Kern abgelehnt",
      copy = "Der Kern lehnt diese Buchung ab. Der genaue Grund ist für diesen Fall noch nicht aufgeschlüsselt.")
  )
  list(code = code, title = result$title, copy = paste0(result$copy, " (", code, ")"))
}

# Der Grund aus dem Adapter, noch mit internen Kennungen: bleibt im Serverprozess.
data_activity_block_reason_signal_v1 <- function(explanation) {
  stop(structure(list(message = "data_activity_block_reason", call = NULL, explanation = explanation),
    class = c("spot_data_activity_block_reason_signal", "error", "condition")))
}

# Der Satz fuer die Oberflaeche. `code` ist der innerste Fehlercode des Kerns.
data_activity_block_reason_abort_v1 <- function(explanation, label = function(kind, internal_id) NULL) {
  text <- data_activity_block_reason_text_v1(explanation, label)
  stop(structure(list(message = text$code, call = NULL, code = text$code, title = text$title, copy = text$copy),
    class = c("spot_desktop_product_block_reason_error", "error", "condition")))
}
