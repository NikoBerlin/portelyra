# RStudio entry point for the installed owner-local Portelyra Product.
# Usage:
#   source("start_portelyra.R")
#   portelyra <- portelyra_start()
#   portelyra_status(portelyra)
#   portelyra_stop(portelyra)

.portelyra_rstudio_project_root_v1 <- function() {
  candidates <- unique(c(getwd(), tryCatch(rstudioapi::getActiveProject(), error = function(error) "")))
  candidates <- candidates[nzchar(candidates)]
  matches <- Filter(function(path) file.exists(file.path(path, "Portelyra.Rproj")) && file.exists(file.path(path, "scripts", "portelyra_desktop.R")), candidates)
  if (length(matches) != 1L) stop("portelyra_rstudio_project_invalid", call. = FALSE)
  normalizePath(matches[[1L]], winslash = "/", mustWork = TRUE)
}

portelyra_start <- function(port = 3838L, open_browser = TRUE) {
  if (!requireNamespace("processx", quietly = TRUE)) stop("portelyra_rstudio_processx_missing", call. = FALSE)
  port <- suppressWarnings(as.integer(port))
  if (length(port) != 1L || is.na(port) || port < 1024L || port > 65532L) stop("portelyra_rstudio_port_invalid", call. = FALSE)
  current <- getOption("portelyra.rstudio.process")
  if (inherits(current, "process") && current$is_alive()) stop("portelyra_rstudio_already_running", call. = FALSE)
  root <- .portelyra_rstudio_project_root_v1()
  arguments <- c("--vanilla", file.path(root, "scripts", "portelyra_desktop.R"), "start", "--port", as.character(port))
  if (!isTRUE(open_browser)) arguments <- c(arguments, "--no-browser")
  # Datenraum wie beim Starter und in der Installation (#488, rc.436): PORTELYRA_DESKTOP_HOME, wenn gesetzt, sonst die Vorgabe der
  # Desktop-CLI ($XDG_DATA_HOME/portelyra bzw. ~/.local/share/portelyra). Ein anderes Home nur bewusst, vor dem Start:
  #   Sys.setenv(PORTELYRA_DESKTOP_HOME = "<pfad>")
  process <- processx::process$new(
    Sys.which("Rscript"), arguments,
    env = c(Sys.getenv(), PYTHONDONTWRITEBYTECODE = "1"),
    stdout = "|", stderr = "|", cleanup = TRUE, cleanup_tree = TRUE,
    windows_hide_window = TRUE
  )
  options(portelyra.rstudio.process = process)
  structure(list(process = process, ports = port + 0:3, project_root = root), class = "portelyra_rstudio_process_v1")
}

.portelyra_rstudio_handle_v1 <- function(handle = getOption("portelyra.rstudio.process")) {
  process <- if (inherits(handle, "portelyra_rstudio_process_v1")) handle$process else handle
  if (!inherits(process, "process")) stop("portelyra_rstudio_process_invalid", call. = FALSE)
  process
}

portelyra_status <- function(handle = getOption("portelyra.rstudio.process")) {
  process <- .portelyra_rstudio_handle_v1(handle)
  list(alive = process$is_alive(), exit_status = process$get_exit_status(), output = process$read_output_lines(), errors = process$read_error_lines())
}

portelyra_stop <- function(handle = getOption("portelyra.rstudio.process"), timeout = 10) {
  process <- .portelyra_rstudio_handle_v1(handle)
  if (process$is_alive()) {
    process$interrupt()
    process$wait(timeout = as.integer(timeout * 1000L))
    if (process$is_alive()) process$kill_tree()
  }
  options(portelyra.rstudio.process = NULL)
  invisible(process$get_exit_status())
}
