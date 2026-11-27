#!/usr/bin/env Rscript

arguments <- commandArgs(trailingOnly = FALSE)
file_argument <- sub("^--file=", "", arguments[grep("^--file=", arguments)][1L])
root <- if (length(file_argument) == 1L && !is.na(file_argument)) {
  normalizePath(file.path(dirname(file_argument), ".."), winslash = "/", mustWork = TRUE)
} else {
  normalizePath(".", winslash = "/", mustWork = TRUE)
}

suppressPackageStartupMessages({
  if (!requireNamespace("DBI", quietly = TRUE) ||
      !requireNamespace("digest", quietly = TRUE) ||
      !requireNamespace("jsonlite", quietly = TRUE) ||
      !requireNamespace("RSQLite", quietly = TRUE)) {
    cat("realized_fifo_projection_failed:realized_fifo_boundary_failed\n", file = stderr())
    quit(save = "no", status = 1L, runLast = FALSE)
  }
})

source(file.path(root, "packages/spotcore/R/exact_decimal_v1.R"), local = .GlobalEnv)
source(file.path(root, "packages/spotcore/R/calculation_evidence_v1.R"), local = .GlobalEnv)
source(file.path(root, "packages/spotcore/R/realized_fifo_projection_v1.R"), local = .GlobalEnv)
status <- realized_fifo_cli_main_v1(commandArgs(trailingOnly = TRUE))
quit(save = "no", status = status, runLast = FALSE)
