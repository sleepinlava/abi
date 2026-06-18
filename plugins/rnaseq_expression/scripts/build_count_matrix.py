#!/usr/bin/env python3
"""Build a gene-level count matrix and sample metadata from featureCounts outputs.

Called as an ABI tool step between featureCounts and DESeq2::

    python build_count_matrix.py \\
        --expression-dir /path/to/03_expression \\
        --sample-sheet /path/to/sample_sheet.tsv \\
        --output-dir /path/to/04_differential_expression

Inputs
------
*f* ``--expression-dir``
    The root directory containing per-sample featureCounts output
    subdirectories (e.g. ``03_expression/S1/S1.featureCounts.txt``).
    Each subdirectory name is used as the ``sample_id``.
*f* ``--sample-sheet``
    Sample sheet TSV with columns ``sample_id``, ``group``, ``condition``.
*f* ``--output-dir``
    Directory where ``count_matrix.tsv`` and ``sample_metadata.tsv``
    will be written.

Outputs
-------
* ``count_matrix.tsv`` —  gene_id × sample_id matrix
* ``sample_metadata.tsv`` — sample_id, group, condition for DESeq2
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build count matrix and sample metadata for DESeq2"
    )
    p.add_argument(
        "--expression-dir",
        required=True,
        help="Root directory containing per-sample featureCounts subdirectories (e.g. 03_expression/)",
    )
    p.add_argument(
        "--sample-sheet",
        required=True,
        help="Sample sheet TSV with sample_id, group, condition columns",
    )
    p.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for count_matrix.tsv and sample_metadata.tsv",
    )
    return p


def parse_sample_sheet(path: str) -> list[dict[str, str]]:
    """Read a sample sheet TSV and return rows as dicts."""
    rows: list[dict[str, str]] = []
    with open(path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if not reader.fieldnames:
            raise ValueError(f"Empty sample sheet: {path}")
        for row in reader:
            rows.append(dict(row))
    return rows


def collect_gene_counts(expression_dir: str) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Walk expression_dir subdirectories and collect per-gene counts.

    Returns:
        gene_counts: {gene_id: {sample_id: count}}
        sample_ids: ordered list of sample IDs encountered
    """
    gene_counts: dict[str, dict[str, str]] = defaultdict(dict)
    sample_ids: list[str] = []

    root = Path(expression_dir)
    if not root.is_dir():
        print(f"ERROR: expression directory not found: {root}", file=sys.stderr)
        return gene_counts, sample_ids

    for subdir in sorted(root.iterdir()):
        if not subdir.is_dir():
            continue
        sample_id = subdir.name
        fc_files = sorted(subdir.glob("*.featureCounts.txt"))
        if not fc_files:
            print(f"WARNING: no *.featureCounts.txt in {subdir}", file=sys.stderr)
            continue
        fc_file = fc_files[0]
        sample_ids.append(sample_id)

        with open(fc_file, encoding="utf-8") as fh:
            reader = csv.DictReader(
                (line for line in fh if not line.startswith("#")), delimiter="\t"
            )
            for row in reader:
                gene_id = row.get("Geneid", "").strip()
                if not gene_id:
                    continue
                count_keys = [
                    k
                    for k in row
                    if k not in ("Geneid", "Chr", "Start", "End", "Strand", "Length")
                ]
                count = row.get(count_keys[-1], "0") if count_keys else "0"
                gene_counts[gene_id][sample_id] = count

    return gene_counts, sample_ids


def write_count_matrix(
    gene_counts: dict[str, dict[str, str]],
    sample_ids: list[str],
    output_dir: Path,
) -> Path:
    """Write count_matrix.tsv (gene_id × samples)."""
    all_genes = sorted(gene_counts.keys())
    path = output_dir / "count_matrix.tsv"
    with path.open("w", encoding="utf-8") as out:
        out.write("gene_id\t" + "\t".join(sample_ids) + "\n")
        for gene in all_genes:
            counts = [gene_counts[gene].get(s, "0") for s in sample_ids]
            out.write(f"{gene}\t" + "\t".join(counts) + "\n")
    return path


def write_sample_metadata(
    sample_sheet_rows: list[dict[str, str]],
    output_dir: Path,
) -> Path:
    """Write sample_metadata.tsv (sample_id, group, condition)."""
    path = output_dir / "sample_metadata.tsv"
    with path.open("w", encoding="utf-8") as out:
        out.write("sample_id\tgroup\tcondition\n")
        for row in sample_sheet_rows:
            sid = row.get("sample_id", "").strip()
            group = row.get("group", "").strip()
            condition = row.get("condition", "").strip()
            if sid:
                out.write(f"{sid}\t{group}\t{condition}\n")
    return path


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Parse sample sheet for metadata
    sample_rows = parse_sample_sheet(args.sample_sheet)
    print(f"Parsed {len(sample_rows)} samples from sample sheet")

    # 2. Collect gene counts from featureCounts directories
    gene_counts, sample_ids = collect_gene_counts(args.expression_dir)
    print(f"Collected {len(gene_counts)} genes from {len(sample_ids)} samples")

    if not gene_counts:
        print("ERROR: No gene counts collected. Check featureCounts outputs.",
              file=sys.stderr)
        sys.exit(1)

    # 3. Write outputs
    matrix_path = write_count_matrix(gene_counts, sample_ids, output_dir)
    print(f"Wrote count matrix: {matrix_path} ({len(gene_counts)} genes × {len(sample_ids)} samples)")

    meta_path = write_sample_metadata(sample_rows, output_dir)
    print(f"Wrote sample metadata: {meta_path}")


if __name__ == "__main__":
    main()
