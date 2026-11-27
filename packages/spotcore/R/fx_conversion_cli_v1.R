fx_conversion_cli_main_v1 <- function(
  arguments = commandArgs(trailingOnly = TRUE), project_root = NULL
) {
  fail <- function(code) {
    cat(paste0("fx_conversion_blocked:", code, "\n"), file = stderr())
    invisible(2L)
  }
  boundary_fail <- function() {
    cat("fx_conversion_failed:fx_history_boundary_failed\n", file = stderr())
    invisible(1L)
  }
  tryCatch({
    if (!is.character(arguments) || length(arguments) != 2L ||
        !identical(arguments[[1L]], "--job") || !nzchar(arguments[[2L]])) {
      return(fail("fx_history_job_invalid"))
    }
    if (!is.character(project_root) || length(project_root) != 1L || is.na(project_root)) {
      return(boundary_fail())
    }
    root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
    worker <- file.path(root, "scripts", "fx_conversion.py")
    python <- Sys.which("python3")
    if (!nzchar(python) || !file.exists(worker)) return(boundary_fail())
    output <- suppressWarnings(system2(
      python, c("-B", "-E", "-s", shQuote(worker), "--job", shQuote(arguments[[2L]])),
      stdout = TRUE, stderr = TRUE, wait = TRUE
    ))
    status <- attr(output, "status")
    if (is.null(status)) status <- 0L
    completed <- grep("^fx_conversion_completed:(complete|partial|no_conversion_required)$", output, value = TRUE)
    blocked <- grep("^fx_conversion_blocked:fx_history_[a-z_]+$", output, value = TRUE)
    failed <- grep("^fx_conversion_failed:fx_history_boundary_failed$", output, value = TRUE)
    if (identical(as.integer(status), 0L) && length(output) == 1L && length(completed) == 1L) {
      cat(paste0(completed, "\n")); return(invisible(0L))
    }
    if (identical(as.integer(status), 2L) && length(output) == 1L && length(blocked) == 1L) {
      cat(paste0(blocked, "\n"), file = stderr()); return(invisible(2L))
    }
    if (length(failed) == 1L || !identical(as.integer(status), 0L)) return(boundary_fail())
    boundary_fail()
  }, error = function(error) boundary_fail())
}
