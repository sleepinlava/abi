#!/usr/bin/env Rscript
# ── ABI DESeq2 Companion Package Installer ───────────────────────────────────
# Installs optional companion packages for DESeq2 workflows (clusterProfiler,
# enrichplot, gene annotation DBs, etc.) from Bioconductor.
#
# DESeq2 and tximport are now installed via conda (bioconductor-deseq2,
# bioconductor-tximport in envs/rnaseq.yml).  This script installs only the
# optional extras and always exits 0 — missing companions are non-fatal.
#
# Usage:
#   Rscript scripts/install_deseq2.R
#   Rscript scripts/install_deseq2.R --lib /path/to/R/library

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

# Ensure target_lib is first so BiocManager installs there
.libPaths(c(target_lib, .libPaths()))
cat(sprintf("ABI companion installer — target library: %s\n", target_lib))

# ── Verify DESeq2 (should already be installed via conda) ───────────────────
if (!requireNamespace("DESeq2", quietly = TRUE)) {
  cat("WARNING: DESeq2 not found in library paths.\n")
  cat("It should have been installed via conda (bioconductor-deseq2).\n")
  cat("Library paths:", paste(.libPaths(), collapse = ", "), "\n")
}

# ── Ensure BiocManager is available ─────────────────────────────────────────
if (!requireNamespace("BiocManager", quietly = TRUE)) {
  install.packages("BiocManager", lib = target_lib,
                   repos = "https://cran.r-project.org", quiet = FALSE)
  loadNamespace("BiocManager")
}

# ── Optional companion packages (best-effort, non-fatal) ────────────────────
optional_pkgs <- c(
  "clusterProfiler",   # GO/KEGG enrichment
  "enrichplot",        # enrichment visualisation
  "org.Hs.eg.db",      # human gene annotations
  "org.Mm.eg.db",      # mouse gene annotations
  "apeglm",            # effect-size shrinkage
  "ashr"               # adaptive shrinkage
)

cat(sprintf("Installing %d optional companion packages...\n", length(optional_pkgs)))
failed <- c()

for (pkg in optional_pkgs) {
  cat(sprintf("  %-25s ...", pkg))
  tryCatch({
    BiocManager::install(pkg, update = FALSE, ask = FALSE,
                         quiet = FALSE, force = FALSE)
    cat(" OK\n")
  }, error = function(e) {
    cat(sprintf(" SKIPPED (%s)\n", conditionMessage(e)))
    failed <<- c(failed, pkg)
  })
}

# ── Summary ─────────────────────────────────────────────────────────────────
cat("\n── Summary ───────────────────────────────────────────────\n")
cat(sprintf("  Installed: %d/%d\n", length(optional_pkgs) - length(failed),
            length(optional_pkgs)))
if (length(failed) > 0) {
  cat(sprintf("  Skipped: %s\n", paste(failed, collapse = ", ")))
  cat("  (companion packages are optional — DESeq2 will still work)\n")
}

# Write marker file
marker <- file.path(target_lib, ".abi_deseq2_installed")
writeLines(
  c(
    sprintf("installed_at: %s", Sys.time()),
    sprintf("r_version: %s", R.version.string),
    sprintf("lib_path: %s", target_lib),
    sprintf("deseq2_from: conda"),
    sprintf("companions_installed: %d/%d",
            length(optional_pkgs) - length(failed), length(optional_pkgs))
  ),
  marker
)
cat(sprintf("\n✓ Done. Marker: %s\n", marker))
