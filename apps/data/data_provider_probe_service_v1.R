data_provider_probe_service_error_codes_v1 <- function() c(
  "data_provider_probe_service_invalid", "data_provider_probe_preview_required",
  "data_provider_probe_confirmation_required", "data_provider_probe_confirmation_consumed",
  "data_provider_probe_boundary_failed"
)

.data_provider_probe_abort_v1 <- function(code) {
  if (!code %in% data_provider_probe_service_error_codes_v1() && !grepl("^desktop_provider_probe_[a-z_]+$", code)) code <- "data_provider_probe_boundary_failed"
  stop(structure(list(message = code, call = NULL, code = code), class = c("spot_data_provider_probe_error_v1", "error", "condition")))
}

new_data_provider_probe_service_v1 <- function(project_root, context) {
  if (!is.character(project_root) || length(project_root) != 1L || !dir.exists(project_root) ||
      !isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) ||
      !identical(context$runtime_mode, "desktop_product") || !identical(context$role, "desktop_owner")) {
    .data_provider_probe_abort_v1("data_provider_probe_service_invalid")
  }
  project_root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(project_root, "scripts", "desktop_provider_probe.py")
  data_space <- runtime_data_space_path(context)
  if (!nzchar(python) || !file.exists(cli) || !dir.exists(data_space) || nzchar(Sys.readlink(cli)) || nzchar(Sys.readlink(data_space))) {
    .data_provider_probe_abort_v1("data_provider_probe_service_invalid")
  }
  previews <- new.env(hash = TRUE, parent = emptyenv()); probes <- new.env(hash = TRUE, parent = emptyenv())
  context_payload <- list(tenant_id=context$tenant_id,user_id=context$user_id,data_space_id=context$data_space_id,actor_id="market_worker",role="market_worker")
  run_cli <- function(command, payload) {
    encoded <- as.character(jsonlite::toJSON(payload, auto_unbox=TRUE, null="null", digits=NA))
    output <- tryCatch(suppressWarnings(system2(python,c("-B","-E","-s",shQuote(cli),shQuote(command)),stdout=TRUE,stderr=TRUE,input=encoded)),error=function(error)structure(character(),status=1L))
    status <- attr(output,"status");if(is.null(status))status<-0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output,1L),simplifyVector=FALSE),error=function(error)NULL)
    if(is.null(parsed)) .data_provider_probe_abort_v1("data_provider_probe_boundary_failed")
    if(as.integer(status)!=0L||isTRUE(parsed$status%in%c("blocked","failed"))) .data_provider_probe_abort_v1(if(is.null(parsed$code))"data_provider_probe_boundary_failed"else parsed$code)
    parsed
  }
  preview <- function(mapping, start_date, end_date, created_at_utc) {
    result<-run_cli("preview",list(context=context_payload,mapping=mapping,start_date=start_date,end_date=end_date,created_at_utc=created_at_utc));trusted<-result$trusted_preview;public<-result$public_preview
    if(!is.list(trusted)||!is.list(public)||!identical(public$status,"pending_confirmation")) .data_provider_probe_abort_v1("data_provider_probe_boundary_failed")
    ref<-paste0("probep_",substr(digest::digest(as.character(jsonlite::toJSON(trusted,auto_unbox=TRUE,null="null",digits=NA)),algo="sha256",serialize=FALSE),1L,32L));public$preview_ref<-ref;assign(ref,list(consumed=FALSE,public=public,trusted=trusted),envir=previews);public
  }
  execute <- function(public_preview, confirmed) {
    if(!isTRUE(confirmed)) .data_provider_probe_abort_v1("data_provider_probe_confirmation_required")
    if(!is.list(public_preview)||!is.character(public_preview$preview_ref)||length(public_preview$preview_ref)!=1L||!exists(public_preview$preview_ref,envir=previews,inherits=FALSE)) .data_provider_probe_abort_v1("data_provider_probe_preview_required")
    stored<-get(public_preview$preview_ref,envir=previews,inherits=FALSE);if(isTRUE(stored$consumed)) .data_provider_probe_abort_v1("data_provider_probe_confirmation_consumed");if(!identical(stored$public,public_preview)) .data_provider_probe_abort_v1("data_provider_probe_preview_required")
    stored$consumed<-TRUE;assign(public_preview$preview_ref,stored,envir=previews);python_public<-stored$public;python_public$preview_ref<-NULL
    result<-run_cli("apply",list(context=context_payload,data_space_path=data_space,trusted_preview=stored$trusted,public_preview=python_public,confirmed=TRUE))$result
    if(!is.list(result)||!identical(result$status,"completed")) .data_provider_probe_abort_v1("data_provider_probe_boundary_failed")
    handle<-paste0("probe_ref_",substr(stored$trusted$request_ref,5L,36L));assign(handle,list(request_ref=stored$trusted$request_ref,mapping_ref_fingerprint=stored$trusted$mapping_fingerprint,result=result),envir=probes)
    c(list(probe_handle=handle),result)
  }
  recover <- function(mapping) {
    result<-run_cli("recover",list(context=context_payload,data_space_path=data_space,mapping=mapping))
    if(identical(result$status,"absent"))return(NULL)
    public<-result$result
    if(!is.list(public)||!identical(public$status,"completed")||!is.character(result$request_ref)) .data_provider_probe_abort_v1("data_provider_probe_boundary_failed")
    handle<-paste0("probe_ref_",substr(result$request_ref,5L,36L));assign(handle,list(request_ref=result$request_ref,mapping_ref_fingerprint=mapping$mapping_fingerprint,result=public),envir=probes)
    c(list(probe_handle=handle),public)
  }
  resolve_probe <- function(handle) {
    if(!is.character(handle)||length(handle)!=1L||!exists(handle,envir=probes,inherits=FALSE)) .data_provider_probe_abort_v1("data_provider_probe_preview_required")
    get(handle,envir=probes,inherits=FALSE)
  }
  structure(list(contract_version="data_provider_probe_service_v1",preview=preview,execute=execute,recover=recover,resolve_probe=resolve_probe,browser_paths_exposed=FALSE,browser_context_exposed=FALSE,automatic_provider_access=FALSE,automatic_retry=FALSE),class=c("spot_data_provider_probe_service_v1","list"))
}
