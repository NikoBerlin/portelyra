# A bound profile is not proof that every future closure was already reviewed.
# Use the same date set for visible choices and the explicit select-proposals action.
data_calendar_binding_choices_v1 <- function(rows, target) {
  if(is.null(target)||!(target$kind %in% c('listing','fx_pair'))) return(character())
  proposed<-Filter(function(r)identical(r$scope_kind,target$kind) &&
    identical(r$consumer_ref,target$consumer) && identical(r$source_status,'source_gap') &&
    !isTRUE(r$context_confirmation_required) &&
    !identical(r$disposition,'calendar_correction_proposed') &&
    !identical(r$reason,'special_open') &&
    (identical(target$kind,'fx_pair')||isTRUE(r$rule_closure_candidate)),rows)
  sort(unique(vapply(proposed,`[[`,character(1L),'date')))
}

# Public-only presentation: retained decisions and new selections are distinct.
data_calendar_binding_summary_v1 <- function(p) {
  if(is.null(p)) return(data.frame())
  data.frame(Markt=p$market_code,Zeitzone=p$timezone_name,
    Gültig_von=p$valid_from,Gültig_bis=p$valid_to,
    Beibehalten=p$retained_closure_count,Neu=p$added_closure_count,
    Schließtage_gesamt=p$closure_count,Sonderöffnungen=p$special_open_count,
    Entfernt=p$removed_day_count,Providerzugriff='nein',History_Write='nein',check.names=FALSE)
}
data_calendar_binding_days_v1 <- function(p) {
  if(is.null(p)) return(data.frame())
  rows<-lapply(p$closure_rows,function(r)data.frame(Datum=r$date,
    Entscheidung=if(identical(r$origin,'retained'))'Beibehalten'else'Neu zur Bestätigung',
    Status='Schließtag',Grund=r$reason,check.names=FALSE))
  for(d in p$special_open_dates) rows[[length(rows)+1L]]<-data.frame(Datum=d,
    Entscheidung='Beibehalten',Status='Sonderöffnung',Grund='Gespeicherte Kalenderentscheidung',check.names=FALSE)
  if(!length(rows)) return(data.frame())
  result<-do.call(rbind,rows);result[order(result$Datum),,drop=FALSE]
}

# Private previews stay in the session service; input changes revoke them.
new_data_calendar_gap_review_service_v1 <- function(project_root, context, cli_runner = NULL) {
  python <- Sys.which("python3")
  cli <- file.path(normalizePath(project_root), "scripts", "desktop_calendar_gap_review.py")
  base <- list(space = runtime_data_space_path(context), context = list(tenant_id = context$tenant_id,
    user_id = context$user_id, data_space_id = context$data_space_id, actor_id = "market_worker", role = "market_worker"))
  cache <- new.env(parent = emptyenv())
  abort <- function(code = "data_calendar_gap_review_preview_required") stop(structure(
    list(message = code, call = NULL, code = code), class = c("error", "condition")))
  run <- function(cmd, payload) {
    if (!is.null(cli_runner)) x <- cli_runner(cmd, c(base, payload)) else {
      old <- Sys.umask("0077"); err <- tempfile("calendar-boundary-")
      on.exit({Sys.umask(old); unlink(err)}, add = TRUE)
      o <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), cmd),
        stdout = TRUE, stderr = err, input = as.character(jsonlite::toJSON(c(base, payload), auto_unbox = TRUE, null = "null"))))
      x <- tryCatch(jsonlite::fromJSON(tail(o, 1), simplifyVector = FALSE), error = function(e) NULL)
      if (file.info(err)$size > 0) x <- NULL
    }
    if (is.null(x) || !identical(x$status, "completed")) abort(if (is.null(x$code)) "data_calendar_gap_review_boundary_failed" else x$code)
    x$result
  }
  invalidate <- function() { rm(list = ls(cache), envir = cache); invisible(NULL) }
  prepare <- function(kind, cmd, payload) {
    if (exists(kind, cache, inherits = FALSE)) rm(list = kind, envir = cache)
    x <- run(cmd, payload); assign(kind, x, cache); x$public
  }
  apply <- function(kind, public, confirmed, now) {
    if (!exists(kind, cache, inherits = FALSE)) abort()
    x <- get(kind, cache, inherits = FALSE)
    if (!identical(public, x$public) || !isTRUE(confirmed)) abort()
    # Consume before invoking a writer; an ambiguous failure must not auto-retry.
    rm(list = kind, envir = cache)
    run(paste0(kind, "_apply"), list(trusted = x$trusted, public = public, confirmed = TRUE, completed = now))
  }
  list(invalidate = invalidate,
    preview_batch = function(ref, dates, now) prepare('batch', 'batch_preview',
      list(listing_ref=ref, dates=as.list(dates), created=now)),
    apply_batch = function(public, confirmed, now) apply('batch', public, confirmed, now),
    preview_binding = function(source, target, dates, from, to, now) prepare("binding", "binding_preview",
      list(source = source, target = target, dates = as.list(dates), valid_from = from, valid_to = to, created = now)),
    preview_listing_binding = function(ref, dates, from, to, now) prepare("binding", "listing_binding_preview",
      list(listing_ref = ref, dates = as.list(dates), valid_from = from, valid_to = to, created = now)),
    apply_binding = function(public, confirmed, now) apply("binding", public, confirmed, now),
    preview_correction = function(source, target, day, now) prepare("correction", "correction_preview",
      list(source = source, target = target, date = day, created = now)),
    preview_listing_correction = function(ref, day, now) prepare("correction", "listing_correction_preview",
      list(listing_ref = ref, date = day, created = now)),
    apply_correction = function(public, confirmed, now) apply("correction", public, confirmed, now))
}
