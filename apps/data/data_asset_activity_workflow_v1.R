# Session-local routing/intent only. Native commands retain all write authority.
# Shared product form routing; batch authority lives in persistent native v2 drafts.
new_data_asset_activity_workflow_v1 <- function(context_key, initial_form = list()) {
  scalar <- function(x) is.character(x) && length(x) == 1L && !is.na(x) && nzchar(x)
  refs_valid <- function(x) is.character(x) && !anyNA(x) && all(nzchar(x)) && !anyDuplicated(x)
  fail <- function(code) stop(code, call. = FALSE)
  if (!scalar(context_key) || !is.list(initial_form)) fail("activity_workflow_context_invalid")
  owner <- new.env(parent = emptyenv())
  current_context <- context_key
  selected <- character()
  action <- "create"
  form <- initial_form
  baseline <- initial_form
  loaded <- FALSE
  revision <- 0L
  pending_load <- NULL
  pending_preview <- NULL
  prepared <- NULL

  invalidate <- function() {
    revision <<- revision + 1L
    pending_load <<- NULL
    pending_preview <<- NULL
    prepared <<- NULL
  }
  dirty <- function() !identical(form, baseline)
  view <- function() {
    multiple <- length(selected) > 1L
    actions <- if (!length(selected)) "create" else if (multiple) "void" else c("correct", "void")
    list(context_key = current_context, selected_refs = selected, action = action,
         allowed_actions = actions, dirty = dirty(), form_loaded = loaded,
         form_editable = identical(action, "create") || (identical(action, "correct") && loaded),
         can_prepare = action != "correct" || loaded,
         block_reason = if (action == "correct" && !loaded) "selected_event_load_required" else NULL,
         preview_ready = !is.null(prepared))
  }
  ticket <- function(kind) list(owner = owner, kind = kind, context_key = current_context,
                                selected_refs = selected, action = action, revision = revision)
  valid_ticket <- function(value, expected) !is.null(expected) && identical(value, expected)

  select <- function(context_key, refs, available_refs, discard = FALSE) {
    if (!scalar(context_key) || !refs_valid(refs) || !refs_valid(available_refs) ||
        !all(refs %in% available_refs) || !is.logical(discard) || length(discard) != 1L || is.na(discard))
      fail("activity_workflow_selection_invalid")
    # Selection order is not an implicit execution order for a future batch.
    refs <- sort(refs)
    if (identical(current_context, context_key) && identical(selected, refs))
      return(list(status = "unchanged", state = view()))
    if (dirty() && !discard) return(list(status = "discard_required", state = view()))
    invalidate()
    current_context <<- context_key
    selected <<- refs
    action <<- if (!length(refs)) "create" else if (length(refs) == 1L) "correct" else "void"
    # Never carry a correction's values into a silently reclassified new booking.
    form <<- list()
    baseline <<- list()
    loaded <<- FALSE
    list(status = "selected", state = view())
  }
  set_action <- function(value) {
    if (!scalar(value) || !value %in% view()$allowed_actions) fail("activity_workflow_action_invalid")
    if (!identical(value, action)) {
      invalidate()
      action <<- value
    }
    view()
  }
  begin_load <- function(discard = FALSE) {
    if (length(selected) != 1L || !identical(action, "correct")) fail("activity_workflow_load_invalid")
    if (!is.logical(discard) || length(discard) != 1L || is.na(discard)) fail("activity_workflow_load_invalid")
    if (dirty() && !discard) return(list(status = "discard_required", ticket = NULL))
    invalidate()
    loaded <<- FALSE
    pending_load <<- ticket("load")
    list(status = "load_requested", ticket = pending_load)
  }
  accept_load <- function(request, replacement_form) {
    if (!valid_ticket(request, pending_load)) return(FALSE)
    if (!is.list(replacement_form)) fail("activity_workflow_form_invalid")
    invalidate()
    form <<- replacement_form
    baseline <<- replacement_form
    loaded <<- TRUE
    TRUE
  }
  set_form <- function(value) {
    if (!is.list(value) || !isTRUE(view()$form_editable)) fail("activity_workflow_form_invalid")
    if (!identical(value, form)) {
      invalidate()
      form <<- value
    }
    view()
  }
  begin_preview <- function() {
    if (!isTRUE(view()$can_prepare)) fail("activity_workflow_prepare_blocked")
    invalidate()
    pending_preview <<- ticket("preview")
    # This request is server-local, never an authorization supplied by the browser.
    list(ticket = pending_preview, context_key = current_context, selected_refs = selected,
         action = action, form = if (action == "void") NULL else form)
  }
  accept_preview <- function(request, native_preview) {
    if (!valid_ticket(request, pending_preview)) return(FALSE)
    if (!is.list(native_preview) || !length(native_preview)) fail("activity_workflow_preview_invalid")
    prepared <<- native_preview
    pending_preview <<- NULL
    TRUE
  }
  revoke <- function() {
    invalidate()
    view()
  }
  mark_saved <- function() {
    # Called only after a successful native result, never on an uncertain write.
    invalidate()
    baseline <<- form
    view()
  }
  list(view = view, select = select, set_action = set_action,
       begin_load = begin_load, accept_load = accept_load, set_form = set_form,
       form = function() form, begin_preview = begin_preview, accept_preview = accept_preview,
       prepared = function() prepared, revoke = revoke, mark_saved = mark_saved)
}

# Read-only narrowing of an already validated Activity projection. Portfolio
# identity comes from account refs, never duplicate labels or display ordinals.
# Seit rc.335 (#422, Festlegung 27.10.2026) zeigt die Kontrolle den Bestand des Assets in jedem Konto des Portfolios, nicht nur
# im Konto des Formulars: Welches Konto gerade stand, war nicht zu erkennen, und eine Bestandskontrolle ueber mehrere Wallets
# brauchte jedes einzeln. Das Konto ist darum keine Voraussetzung mehr; ist eines gewaehlt, muss es zum Portfolio gehoeren.
data_asset_activity_context_projection_v1 <- function(catalog, projection, portfolio_ref, asset_ref, account_ref) {
  result <- function(status) list(status=status, portfolios=list())
  scalar <- function(x) is.character(x) && length(x)==1L && !is.na(x) && nzchar(x)
  if (!all(vapply(list(portfolio_ref,asset_ref),scalar,logical(1L)))) return(result('selection_required'))
  if (is.null(catalog) || is.null(projection)) return(result('unavailable'))
  matches <- function(rows, ref) Filter(function(row)identical(row$ref,ref),rows)
  if (length(matches(catalog$portfolios,portfolio_ref))!=1L || length(matches(catalog$assets,asset_ref))!=1L) return(result('blocked'))
  if (scalar(account_ref)) {
    account <- matches(catalog$accounts,account_ref)
    if (length(account)!=1L || !identical(account[[1L]]$portfolio_ref,portfolio_ref)) return(result('blocked'))
  }
  if (!projection$status %in% c('ready','empty') || !identical(projection$fifo_state,'fresh')) return(result('unavailable'))
  selected <- list()
  for (portfolio in projection$portfolios) {
    evidence <- c(portfolio$custody_positions,portfolio$events_newest_first)
    if (!length(evidence)) {
      if (length(portfolio$positions)) return(result('unavailable'))
      next
    }
    owners <- character()
    for (row in evidence) {
      identity <- matches(catalog$accounts,row$account_ref)
      if (length(identity)!=1L) return(result('unavailable'))
      owners <- c(owners,identity[[1L]]$portfolio_ref)
    }
    owners <- unique(owners)
    if (length(owners)!=1L) return(result('unavailable'))
    if (!identical(owners,portfolio_ref)) next
    portfolio$positions <- Filter(function(row)identical(row$asset_ref,asset_ref),portfolio$positions)
    portfolio$custody_positions <- Filter(function(row)identical(row$asset_ref,asset_ref),portfolio$custody_positions)
    selected[[length(selected)+1L]] <- portfolio
  }
  if (length(selected)>1L) return(result('unavailable'))
  list(status=if(length(selected) && (length(selected[[1L]]$positions) || length(selected[[1L]]$custody_positions)))'ready'else'empty',portfolios=selected)
}
