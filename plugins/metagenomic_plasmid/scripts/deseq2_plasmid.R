args <- commandArgs(trailingOnly = TRUE)

arg_value <- function(flag) {
  index <- match(flag, args)
  if (is.na(index) || index == length(args)) stop(paste("Missing", flag))
  args[[index + 1]]
}

abundance_path <- arg_value("--abundance")
metadata_path <- arg_value("--metadata")
output_path <- arg_value("--output")

output_columns <- c(
  "plasmid_id", "group_a", "group_b", "log2_fold_change",
  "p_value", "q_value", "method", "warnings"
)
empty_output <- function() {
  dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)
  write.table(
    setNames(data.frame(matrix(ncol = length(output_columns), nrow = 0)), output_columns),
    output_path,
    sep = "\t",
    quote = FALSE,
    row.names = FALSE
  )
}

abundance <- read.delim(abundance_path, check.names = FALSE, stringsAsFactors = FALSE)
metadata <- read.delim(metadata_path, check.names = FALSE, stringsAsFactors = FALSE)
if (!all(c("sample_id", "plasmid_id") %in% names(abundance)) ||
    !all(c("sample_id", "group") %in% names(metadata))) {
  stop("Required columns are missing from abundance or metadata input")
}

use_raw_counts <- "raw_count" %in% names(abundance) && any(nzchar(abundance$raw_count))
value_column <- if (use_raw_counts) "raw_count" else "coverage"
if (!value_column %in% names(abundance)) {
  empty_output()
  quit(status = 0)
}
abundance$value <- suppressWarnings(as.numeric(abundance[[value_column]]))
abundance$value[is.na(abundance$value)] <- 0
abundance$value <- round(pmax(abundance$value, 0))

counts <- xtabs(value ~ plasmid_id + sample_id, data = abundance)
metadata <- metadata[!is.na(metadata$group) & nzchar(metadata$group), c("sample_id", "group")]
metadata <- metadata[!duplicated(metadata$sample_id), ]
shared <- intersect(colnames(counts), metadata$sample_id)
if (length(shared) == 0 || nrow(counts) == 0) {
  empty_output()
  quit(status = 0)
}
counts <- counts[, shared, drop = FALSE]
metadata <- metadata[match(shared, metadata$sample_id), , drop = FALSE]
metadata$group <- factor(metadata$group)
if (nlevels(metadata$group) < 2) {
  empty_output()
  quit(status = 0)
}

suppressPackageStartupMessages(library(DESeq2))
all_results <- list()
groups <- levels(metadata$group)
comparison_index <- 1
for (left_index in seq_len(length(groups) - 1)) {
  for (right_index in seq.int(left_index + 1, length(groups))) {
    group_a <- groups[[left_index]]
    group_b <- groups[[right_index]]
    keep <- metadata$group %in% c(group_a, group_b)
    subset_metadata <- droplevels(metadata[keep, , drop = FALSE])
    subset_counts <- counts[, keep, drop = FALSE]
    dds <- DESeqDataSetFromMatrix(
      countData = subset_counts,
      colData = data.frame(group = subset_metadata$group, row.names = subset_metadata$sample_id),
      design = ~ group
    )
    dds <- DESeq(dds, quiet = TRUE)
    result <- results(dds, contrast = c("group", group_a, group_b))
    frame <- data.frame(
      plasmid_id = rownames(result),
      group_a = group_a,
      group_b = group_b,
      log2_fold_change = result$log2FoldChange,
      p_value = result$pvalue,
      q_value = result$padj,
      method = "DESeq2",
      warnings = if (use_raw_counts) "" else "Rounded coverage used as count proxy",
      stringsAsFactors = FALSE
    )
    all_results[[comparison_index]] <- frame
    comparison_index <- comparison_index + 1
  }
}

combined <- do.call(rbind, all_results)
dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)
write.table(combined, output_path, sep = "\t", quote = FALSE, row.names = FALSE, na = "")
