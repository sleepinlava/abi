#!/usr/bin/env Rscript
# ============================================================================
# run_deseq2.R — ABI rnaseq_expression DESeq2 execution script
# ============================================================================
# Usage:
#   Rscript run_deseq2.R \
#     --counts count_matrix.tsv \
#     --metadata sample_metadata.tsv \
#     --output results/ \
#     --comparison treatment_vs_control \
#     --design "~ condition" \
#     --alpha 0.05
#
# Outputs:
#   {output}/deseq2_results.tsv      — gene_id, baseMean, log2FoldChange,
#                                      lfcSE, stat, pvalue, padj, comparison
#   {output}/normalized_expression.tsv — gene_id + per-sample normalized counts
#
# Requirements:
#   - R >= 4.0
#   - Bioconductor package: DESeq2
#     Install: BiocManager::install("DESeq2")
# ============================================================================

# ── CLI argument parsing / 命令行参数解析 ──────────────────────────────────
args <- commandArgs(trailingOnly = TRUE)

parse_arg <- function(name, default = NULL) {
  idx <- which(args == name)
  if (length(idx) == 0 || idx == length(args)) return(default)
  args[idx + 1]
}

counts_file  <- parse_arg("--counts")
metadata_file <- parse_arg("--metadata")
output_dir   <- parse_arg("--output", ".")
comparison   <- parse_arg("--comparison", "treatment_vs_control")
design_text  <- parse_arg("--design", "~ condition")
alpha        <- as.numeric(parse_arg("--alpha", "0.05"))

# ── Validation / 验证 ─────────────────────────────────────────────────────
if (is.null(counts_file) || is.null(metadata_file)) {
  stop("Usage: Rscript run_deseq2.R --counts <file> --metadata <file> ",
       "--output <dir> --comparison <name> --design <formula> --alpha <float>\n",
       call. = FALSE)
}

if (!file.exists(counts_file)) {
  stop("Count matrix file not found: ", counts_file, call. = FALSE)
}

if (!file.exists(metadata_file)) {
  stop("Metadata file not found: ", metadata_file, call. = FALSE)
}

if (alpha <= 0 || alpha > 1) {
  stop("alpha must be in (0, 1], got: ", alpha, call. = FALSE)
}

# ── Load libraries / 加载库 ────────────────────────────────────────────────
suppressPackageStartupMessages({
  library(DESeq2)
})

# ── Read input data / 读取输入数据 ─────────────────────────────────────────
count_matrix <- as.matrix(read.table(
  counts_file, header = TRUE, row.names = 1,
  sep = "\t", check.names = FALSE, stringsAsFactors = FALSE
))
# Ensure integer counts
count_matrix <- round(count_matrix)
mode(count_matrix) <- "integer"

metadata <- read.table(
  metadata_file, header = TRUE, sep = "\t",
  check.names = FALSE, stringsAsFactors = FALSE
)

# ── Parse comparison string / 解析比较字符串 ───────────────────────────────
# Expected format: "group1_vs_group2" or "treated_vs_untreated"
comp_parts <- strsplit(comparison, "_vs_")[[1]]
if (length(comp_parts) != 2) {
  stop("comparison must be in 'group1_vs_group2' format, got: ",
       comparison, call. = FALSE)
}
numerator   <- comp_parts[1]
denominator <- comp_parts[2]

# ── Align metadata with count matrix / 对齐元数据与计数矩阵 ────────────────
# metadata must have 'sample_id' and 'condition' columns
if (!("sample_id" %in% colnames(metadata))) {
  stop("Metadata file must contain a 'sample_id' column", call. = FALSE)
}
if (!("condition" %in% colnames(metadata))) {
  stop("Metadata file must contain a 'condition' column", call. = FALSE)
}

design_formula <- tryCatch(
  as.formula(design_text),
  error = function(e) stop("Invalid DESeq2 design formula '", design_text,
                            "': ", conditionMessage(e), call. = FALSE)
)
design_variables <- all.vars(design_formula)
if (!("condition" %in% design_variables)) {
  stop("DESeq2 design must include 'condition' to support --comparison; got: ",
       design_text, call. = FALSE)
}
missing_design_columns <- setdiff(design_variables, colnames(metadata))
if (length(missing_design_columns) > 0) {
  stop("DESeq2 design references missing metadata column(s): ",
       paste(missing_design_columns, collapse = ", "), call. = FALSE)
}

# Keep only samples present in both metadata and count matrix
sample_cols <- colnames(count_matrix)
metadata <- metadata[metadata$sample_id %in% sample_cols, , drop = FALSE]
if (nrow(metadata) < 2) {
  stop("Need at least 2 samples (1 per group) for DESeq2; got ",
       nrow(metadata), call. = FALSE)
}

# Reorder count matrix columns to match metadata order
count_matrix <- count_matrix[, metadata$sample_id, drop = FALSE]

# Verify the comparison groups exist in the metadata
conditions <- unique(metadata$condition)
if (!(numerator %in% conditions)) {
  stop("Comparison numerator '", numerator,
       "' not found in metadata conditions: ",
       paste(conditions, collapse = ", "), call. = FALSE)
}
if (!(denominator %in% conditions)) {
  stop("Comparison denominator '", denominator,
       "' not found in metadata conditions: ",
       paste(conditions, collapse = ", "), call. = FALSE)
}

# ── Run DESeq2 / 运行 DESeq2 ──────────────────────────────────────────────
metadata$condition <- factor(metadata$condition)
# Set the reference level to the denominator
metadata$condition <- relevel(metadata$condition, ref = denominator)
for (column in setdiff(design_variables, "condition")) {
  metadata[[column]] <- factor(metadata[[column]])
}

dds <- DESeqDataSetFromMatrix(
  countData = count_matrix,
  colData   = metadata,
  design    = design_formula
)

# Remove genes with zero counts across all samples (causes size factor failure)
nonzero <- rowSums(counts(dds)) > 0
dds <- dds[nonzero, ]

# Filter low-count genes: keep genes with counts in at least 2 samples
# Relaxed threshold for low-depth/sparse data
smallest_group_size <- min(table(metadata$condition))
min_count <- min(10, max(2, floor(mean(rowSums(counts(dds))) / 4)))
keep <- rowSums(counts(dds) >= min_count) >= min(2, smallest_group_size)
# If filter removes all genes, skip filtering
if (sum(keep) >= 2) dds <- dds[keep, ]

dds <- estimateSizeFactors(dds, type = "poscounts")
no_replicates <- smallest_group_size < 2
if (no_replicates) {
  # No replicates: simple fold changes with pseudocount
  norm_counts <- counts(dds, normalized = TRUE)
  grp1 <- rowMeans(norm_counts[, metadata$condition == denominator, drop = FALSE])
  grp2 <- rowMeans(norm_counts[, metadata$condition == numerator,   drop = FALSE])
  lfc <- log2((grp2 + 1) / (grp1 + 1))
  res <- data.frame(
    baseMean       = rowMeans(norm_counts),
    log2FoldChange = lfc,
    lfcSE          = NA_real_,
    stat           = NA_real_,
    pvalue         = NA_real_,
    padj           = NA_real_,
    row.names      = rownames(norm_counts)
  )
} else {
  dds <- DESeq(dds, fitType = "mean")
  # Extract results for the comparison
  res <- results(dds, contrast = c("condition", numerator, denominator),
                 alpha = alpha)
}

# ── Write output files / 写入输出文件 ──────────────────────────────────────
dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

# 1. Differential expression results
de_out <- data.frame(
  gene_id        = rownames(res),
  baseMean       = res$baseMean,
  log2FoldChange = res$log2FoldChange,
  lfcSE          = res$lfcSE,
  stat           = res$stat,
  pvalue         = res$pvalue,
  padj           = res$padj,
  comparison     = comparison,
  stringsAsFactors = FALSE
)
# Replace NA padj with 1.0 (genes with zero counts in one group)
de_out$padj[is.na(de_out$padj)] <- 1.0

write.table(
  de_out,
  file      = file.path(output_dir, "deseq2_results.tsv"),
  sep       = "\t",
  row.names = FALSE,
  quote     = FALSE
)

# 2. Normalized expression matrix
norm_counts <- counts(dds, normalized = TRUE)
norm_out <- data.frame(
  gene_id = rownames(norm_counts),
  norm_counts,
  check.names = FALSE,
  stringsAsFactors = FALSE
)

write.table(
  norm_out,
  file      = file.path(output_dir, "normalized_expression.tsv"),
  sep       = "\t",
  row.names = FALSE,
  quote     = FALSE
)

cat(sprintf(
  "DESeq2 completed: %d genes tested, %d significantly DE (padj < %.2f)\n",
  nrow(de_out), sum(de_out$padj < alpha, na.rm = TRUE), alpha
))
cat(sprintf("Results:    %s\n", file.path(output_dir, "deseq2_results.tsv")))
cat(sprintf("Normalized: %s\n", file.path(output_dir, "normalized_expression.tsv")))
