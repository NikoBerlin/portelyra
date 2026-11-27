new_desktop_workflow_service_v1 <- function(project_root, runtime, role) {
  context <- if (is.list(runtime)) runtime$context else NULL
  required <- c("tenant_id", "user_id", "data_space_id", "data_root")
  if (!is.list(context) || !all(required %in% names(context)) ||
      !is.character(role) || length(role) != 1L || !role %in% c("viewer", "tax_viewer", "analysis_viewer")) {
    stop("desktop_workflow_display_context_invalid", call. = FALSE)
  }
  structure(list(
    project_root = project_root,
    context = spotdisplay::new_desktop_product_display_context_v1(
      context$data_root, role, context$tenant_id,
      context$user_id, context$data_space_id
    )
  ), class = "spot_desktop_workflow_service_v1")
}

desktop_workflow_read_latest_v1 <- function(service) {
  if (!inherits(service, "spot_desktop_workflow_service_v1")) stop("desktop_workflow_display_context_invalid", call. = FALSE)
  spotdisplay::read_desktop_workflow_latest_v1(service$context, service$project_root)
}

desktop_workflow_display_state_v1 <- function(model = NULL, error_code = NULL) {
  if (!is.null(error_code)) return(list(kind = "error", code = error_code, model = NULL))
  if (is.null(model)) return(list(kind = "empty", code = "desktop_workflow_not_published", model = NULL))
  list(kind = model$status, code = NULL, model = model)
}
