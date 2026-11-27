unrealized_valuation_cli_main_v1 <- function(
  arguments = commandArgs(trailingOnly = TRUE), project_root = NULL
) {
  fail <- function(code) {
    cat(paste0("unrealized_valuation_blocked:", code, "\n"), file = stderr())
    invisible(2L)
  }
  boundary_fail <- function() {
    cat("unrealized_valuation_failed:unrealized_valuation_boundary_failed\n", file = stderr())
    invisible(1L)
  }
  tryCatch({
    if (!is.character(arguments) || length(arguments) != 2L ||
        !identical(arguments[[1L]], "--job") || !nzchar(arguments[[2L]])) {
      return(fail("unrealized_valuation_job_invalid"))
    }
    if (!is.character(project_root) || length(project_root) != 1L || is.na(project_root)) {
      return(boundary_fail())
    }
    root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
    worker <- file.path(root, "scripts", "unrealized_valuation.py")
    python <- Sys.which("python3")
    if (!nzchar(python) || !file.exists(worker)) return(boundary_fail())
    output <- suppressWarnings(system2(
      python, c("-B", "-E", "-s", shQuote(worker), "--job", shQuote(arguments[[2L]])),
      stdout = TRUE, stderr = TRUE, wait = TRUE
    ))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    completed <- grep("^unrealized_valuation_completed:(completed|partial|blocked)$", output, value = TRUE)
    blocked <- grep("^unrealized_valuation_blocked:unrealized_valuation_[a-z_]+$", output, value = TRUE)
    if (identical(as.integer(status), 0L) && length(output) == 1L && length(completed) == 1L) {
      cat(paste0(completed, "\n")); return(invisible(0L))
    }
    if (identical(as.integer(status), 2L) && length(output) == 1L && length(blocked) == 1L) {
      cat(paste0(blocked, "\n"), file = stderr()); return(invisible(2L))
    }
    boundary_fail()
  }, error = function(error) boundary_fail())
}
