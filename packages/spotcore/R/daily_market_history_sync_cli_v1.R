daily_market_history_sync_cli_main_v1 <- function(
  arguments = commandArgs(trailingOnly = TRUE), project_root = NULL
) {
  fail <- function(code) {
    cat(paste0("daily_market_history_sync_blocked:", code, "\n"), file = stderr())
    invisible(2L)
  }
  boundary_fail <- function() {
    cat("daily_market_history_sync_failed:market_sync_boundary_failed\n", file = stderr())
    invisible(1L)
  }
  tryCatch({
    if (!is.character(arguments) || !length(arguments) || length(arguments) %% 2L != 0L) {
      return(fail("market_sync_input_invalid"))
    }
    allowed <- c("--job", "--evidence-output")
    values <- list()
    index <- 1L
    while (index <= length(arguments)) {
      key <- arguments[[index]]
      if (!key %in% allowed || key %in% names(values) || index == length(arguments)) {
        return(fail("market_sync_input_invalid"))
      }
      values[[key]] <- arguments[[index + 1L]]
      index <- index + 2L
    }
    if (!"--job" %in% names(values)) return(fail("market_sync_input_invalid"))
    if (!is.character(project_root) || length(project_root) != 1L || is.na(project_root)) {
      return(boundary_fail())
    }
    root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
    worker <- file.path(root, "scripts", "daily_market_history_sync.py")
    python <- Sys.which("python3")
    if (!nzchar(python) || !file.exists(worker)) {
      return(boundary_fail())
    }
    worker_arguments <- c("-B", "-E", "-s", shQuote(worker), "--job", shQuote(values[["--job"]]))
    if ("--evidence-output" %in% names(values)) {
      worker_arguments <- c(worker_arguments, "--evidence-output", shQuote(values[["--evidence-output"]]))
    }
    output <- suppressWarnings(system2(
      python, worker_arguments, stdout = TRUE, stderr = TRUE, wait = TRUE
    ))
    status <- attr(output, "status")
    if (is.null(status)) status <- 0L
    completed <- grep("^daily_market_history_sync_completed:[a-z_]+$", output, value = TRUE)
    blocked <- grep("^daily_market_history_sync_blocked:market_sync_[a-z_]+$", output, value = TRUE)
    failed <- grep("^daily_market_history_sync_failed:market_sync_boundary_failed$", output, value = TRUE)
    if (identical(as.integer(status), 0L) && length(output) == 1L && length(completed) == 1L) {
      cat(paste0(completed, "\n")); return(invisible(0L))
    }
    if (identical(as.integer(status), 2L) && length(output) == 1L && length(blocked) == 1L) {
      cat(paste0(blocked, "\n"), file = stderr()); return(invisible(2L))
    }
    if (length(failed) == 1L || !identical(as.integer(status), 0L)) {
      cat("daily_market_history_sync_failed:market_sync_boundary_failed\n", file = stderr())
      return(invisible(1L))
    }
    boundary_fail()
  }, error = function(error) {
    cat("daily_market_history_sync_failed:market_sync_boundary_failed\n", file = stderr())
    invisible(1L)
  })
}
