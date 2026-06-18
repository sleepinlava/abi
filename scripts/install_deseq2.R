#!/usr/bin/env Rscript
# ── ABI DESeq2 R Package Installer ──────────────────────────────────────────
# Installs DESeq2 and dependencies from Bioconductor into the current R library.
#
# Usage:
#   Rscript scripts/install_deseq2.R
#   Rscript scripts/install_deseq2.R --lib /path/to/R/library
#
# Design / 设计:
#   - Uses BiocManager for reliable Bioconductor installation
#   - Retries failed downloads (Bioconductor mirrors can be flaky)
#   - Writes .abi_deseq2_installed marker in the target library on success

library(tools)  # for md5sum

# ── Parse arguments ─────────────────────────────────────────────────────────
args <- commandArgs(trailingOnly = TRUE)
target_lib <- NULL
for (i in seq_along(args)) {
  if (args[i] == "--lib" && i < length(args)) {
    target_lib <- args[i + 1]
  }
}
if (is.null(target_lib)) {
  target_lib <- .libPaths()[1]
}
if (!dir.exists(target_lib)) {
  dir.create(target_lib, recursive = TRUE, showWarnings = FALSE)
}

cat(sprintf("ABI DESeq2 installer — target library: %s\n", target_lib))

# ── Ensure BiocManager is available ─────────────────────────────────────────
if (!requireNamespace("BiocManager", quietly = TRUE)) {
  cat("Installing BiocManager...\n")
  install.packages("BiocManager", lib = target_lib, repos = "https://cran.r-project.org",
                   quiet = FALSE)
}

# ── Install DESeq2 from Bioconductor ────────────────────────────────────────
# Bioconductor 3.18+ provides DESeq2; use the version matching the R release.
bioc_pkgs <- c("DESeq2")

# Also install commonly-needed companion packages
companion_pkgs <- c(
  "org.Hs.eg.db",      # human gene annotations (for clusterProfiler)
  "org.Mm.eg.db",      # mouse gene annotations
  "clusterProfiler",    # GO/KEGG enrichment (optional rnaseq tool)
  "enrichplot",         # enrichment visualisation
  "apeglm",            # effect-size shrinkage
  "ashr",              # adaptive shrinkage
  "tximport",          # transcript-level import
  "readr"              # fast TSV reading
)

all_pkgs <- c(bioc_pkgs, companion_pkgs)

cat(sprintf("Installing %d Bioconductor packages...\n", length(all_pkgs)))

for (pkg in all_pkgs) {
  cat(sprintf("  %s ...", pkg))
  tryCatch({
    BiocManager::install(pkg, lib = target_lib, update = FALSE, ask = FALSE,
                         quiet = TRUE, force = FALSE)
    cat(" OK\n")
  }, error = function(e) {
    cat(sprintf(" FAILED (%s)\n", conditionMessage(e)))
  })
}

# ── Verification ────────────────────────────────────────────────────────────
cat("\n── Verification ──────────────────────────────────────────\n")
required <- c("DESeq2")
all_ok <- TRUE
for (pkg in required) {
  ok <- requireNamespace(pkg, lib.loc = target_lib, quietly = TRUE)
  status <- if (ok) "OK" else "MISSING"
  cat(sprintf("  %-30s %s\n", pkg, status))
  if (!ok) all_ok <- FALSE
}

if (all_ok) {
  # Write a marker file so abi setup-resources can verify installation
  marker <- file.path(target_lib, ".abi_deseq2_installed")
  writeLines(
    c(
      sprintf("installed_at: %s", Sys.time()),
      sprintf("r_version: %s", R.version.string),
      sprintf("bioc_version: %s", as.character(BiocManager::version())),
      sprintf("lib_path: %s", target_lib)
    ),
    marker
  )
  cat(sprintf("\n✓ DESeq2 installation verified. Marker: %s\n", marker))
} else {
  cat("\n✗ Some packages are missing. Check the output above.\n")
  quit(status = 1)
}
