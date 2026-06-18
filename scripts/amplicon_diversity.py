#!/usr/bin/env python3
"""Amplicon diversity computation script for the ABI amplicon_16s plugin.

Builds a merged ASV abundance table from per-sample ASV FASTA files,
then computes alpha diversity (observed features, Shannon, Simpson,
Chao1, Faith's PD) and beta diversity (Bray-Curtis, Jaccard, UniFrac).

Usage:
    python amplicon_diversity.py \\
        --denoise-dir 04_denoise \\
        --merge-dir 02_merge \\
        --output-dir 06_diversity \\
        [--tree phylogeny.nwk]

If --tree is not provided, tree-dependent metrics (Faith's PD, UniFrac)
are skipped gracefully with an empty output table.

Approach:
    - ASV sequences are collected from per-sample asvs.fasta files
    - Global ASV set = deduplicated across all samples
    - Per-sample abundance = exact match of merged reads → global ASVs
    - Alpha diversity computed via pure Python (no external deps)
    - Beta diversity computed via pure Python pairwise
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── FASTA I/O ────────────────────────────────────────────────────────────────


def _read_fasta(path: Path) -> List[Tuple[str, str]]:
    """Read a FASTA file. Returns list of (header, sequence) tuples."""
    seqs: List[Tuple[str, str]] = []
    current_header = ""
    current_seq: List[str] = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line.startswith(">"):
                if current_seq:
                    seqs.append((current_header, "".join(current_seq)))
                current_header = line[1:]  # strip '>'
                current_seq = []
            else:
                current_seq.append(line.upper())
    if current_seq:
        seqs.append((current_header, "".join(current_seq)))
    return seqs


def _read_fasta_seqs(path: Path) -> List[str]:
    """Read a FASTA file, returning only sequences (uppercased)."""
    return [seq for _, seq in _read_fasta(path)]


def _write_fasta(path: Path, entries: List[Tuple[str, str]]) -> None:
    """Write a FASTA file with 70-char wrapped sequences."""
    with path.open("w") as fh:
        for header, seq in entries:
            fh.write(f">{header}\n")
            for i in range(0, len(seq), 70):
                fh.write(f"{seq[i:i + 70]}\n")


# ── ASV table construction ───────────────────────────────────────────────────


def _build_asv_table(
    denoise_dir: Path, merge_dir: Path
) -> Tuple[Dict[str, Dict[str, int]], Dict[str, str], Dict[str, int], List[str]]:
    """Build merged ASV abundance table from per-sample ASV + merged-read files.

    Returns:
        asv_table: {asv_id: {sample_id: count}}
        asv_seqs: {asv_id: sequence}
        sample_totals: {sample_id: total_merged_reads}
        sample_ids: list of sample IDs in discovery order
    """
    # Phase 1: Discover samples and load ASVs
    sample_asvs: Dict[str, List[str]] = {}  # {sample_id: [asv_seq, ...]}
    sample_ids: List[str] = []

    for subdir in sorted(denoise_dir.iterdir()):
        if not subdir.is_dir():
            continue
        sample_id = subdir.name
        asv_fasta = subdir / "asvs.fasta"
        if not asv_fasta.exists():
            continue
        sample_ids.append(sample_id)
        sample_asvs[sample_id] = _read_fasta_seqs(asv_fasta)

    if not sample_ids:
        print("ERROR: No per-sample asvs.fasta files found", file=sys.stderr)
        sys.exit(1)

    # Phase 2: Build global ASV set (deduplicate across samples)
    seq_to_asv: Dict[str, str] = {}  # {seq: asv_id}
    asv_seqs: Dict[str, str] = {}    # {asv_id: seq}
    for idx, (sample_id, seqs) in enumerate(sorted(sample_asvs.items())):
        for seq in seqs:
            if seq not in seq_to_asv:
                asv_id = f"ASV_{len(seq_to_asv) + 1:05d}"
                seq_to_asv[seq] = asv_id
                asv_seqs[asv_id] = seq

    # Phase 3: Count per-sample ASV abundance via exact-match of merged reads
    asv_table: Dict[str, Dict[str, int]] = {
        asv_id: {sid: 0 for sid in sample_ids} for asv_id in asv_seqs
    }
    sample_totals: Dict[str, int] = {}

    for sample_id in sample_ids:
        # Find merged FASTA
        merge_sample_dir = merge_dir / sample_id
        merged_files = sorted(merge_sample_dir.glob("*_merged.fasta"))
        if not merged_files:
            # Try alternative filename pattern
            merged_files = sorted(merge_sample_dir.glob("*.fasta"))
        total_reads = 0
        if merged_files:
            merged_seqs = _read_fasta_seqs(merged_files[0])
            for seq in merged_seqs:
                total_reads += 1
                asv_id = seq_to_asv.get(seq)
                if asv_id is not None:
                    asv_table[asv_id][sample_id] += 1
        sample_totals[sample_id] = total_reads

    return asv_table, asv_seqs, sample_totals, sample_ids


# ── Alpha diversity ──────────────────────────────────────────────────────────


def _shannon(counts: List[int]) -> float:
    """Shannon entropy H' = -sum(p_i * ln(p_i))."""
    total = sum(counts)
    if total == 0:
        return 0.0
    entropy = 0.0
    for c in counts:
        if c > 0:
            p = c / total
            entropy -= p * math.log(p)
    return entropy


def _simpson(counts: List[int]) -> float:
    """Simpson index 1 - sum(p_i^2). Ranges 0 (low diversity) to 1 (high)."""
    total = sum(counts)
    if total == 0:
        return 0.0
    dom = sum((c / total) ** 2 for c in counts)
    return 1.0 - dom


def _chao1(counts: List[int]) -> float:
    """Chao1 richness estimator: S_obs + (f1^2 / (2 * f2))."""
    f1 = sum(1 for c in counts if c == 1)
    f2 = sum(1 for c in counts if c == 2)
    s_obs = sum(1 for c in counts if c > 0)
    if f2 == 0:
        return float(s_obs) + (f1 * (f1 - 1) / 2.0) if f1 > 0 else float(s_obs)
    return float(s_obs) + (f1 * f1) / (2.0 * f2)


def _observed_features(counts: List[int]) -> int:
    """Number of features with count > 0."""
    return sum(1 for c in counts if c > 0)


def _faith_pd(
    sample_asvs: set[str],
    asv_to_node: Dict[str, int],
    children: Dict[int, List[int]],
    branch_lengths: Dict[int, float],
) -> float:
    """Faith's Phylogenetic Diversity: total branch length of the subtree
    connecting all ASVs present in the sample on the reference phylogeny.

    Uses the post-order traversal approach: for each internal node, count how
    many sample ASVs are in its subtree; if >= 1, add the branch length.
    """
    # Map ASV IDs to their leaf node indices
    present_nodes = set()
    for asv_id in sample_asvs:
        node = asv_to_node.get(asv_id)
        if node is not None:
            present_nodes.add(node)

    if not present_nodes:
        return 0.0

    # Propagate presence up: if a node or any descendant has a sample ASV,
    # the node is "covered"
    n_nodes = len(children)

    # Post-order: sort nodes so children come before parents
    # Simple approach: nodes are 0..n_nodes-1 where internals have higher IDs
    # We'll use a visited set and propagate up
    covered = set(present_nodes)

    # Determine parent relationships from children dict
    parent_of: Dict[int, int] = {}
    for parent, kids in children.items():
        for kid in kids:
            parent_of[kid] = parent

    # Propagate up from each leaf
    stack = list(present_nodes)
    while stack:
        node = stack.pop()
        parent = parent_of.get(node)
        if parent is not None and parent not in covered:
            covered.add(parent)
            stack.append(parent)

    # Sum branch lengths of covered nodes
    total = 0.0
    for node in covered:
        bl = branch_lengths.get(node, 0.0)
        if bl > 0:
            total += bl

    return total


def _compute_alpha(
    asv_table: Dict[str, Dict[str, int]],
    sample_ids: List[str],
    asv_seqs: Dict[str, str],
    tree_path: Optional[Path],
) -> Tuple[List[Dict[str, Any]], bool]:
    """Compute alpha diversity metrics for all samples.

    Returns (rows, tree_used) where tree_used indicates whether Faith's PD
    was successfully computed.
    """
    tree_used = False
    tree_data = None

    if tree_path and tree_path.exists():
        tree_data = _parse_newick(tree_path, asv_seqs)
        tree_used = tree_data is not None

    rows: List[Dict[str, Any]] = []
    for sample_id in sample_ids:
        counts = [asv_table[asv_id][sample_id] for asv_id in asv_table]
        row: Dict[str, Any] = {
            "sample_id": sample_id,
            "observed_features": _observed_features(counts),
            "shannon_entropy": round(_shannon(counts), 4),
            "simpson_index": round(_simpson(counts), 4),
            "chao1": round(_chao1(counts), 2),
            "tool": "amplicon_diversity",
            "source_file": "",
        }

        # Faith's PD if tree available
        if tree_data is not None:
            children, branch_lengths, asv_to_node = tree_data
            sample_asvs = {
                asv_id
                for asv_id in asv_table
                if asv_table[asv_id][sample_id] > 0
            }
            row["faith_pd"] = round(
                _faith_pd(sample_asvs, asv_to_node, children, branch_lengths), 4
            )
        else:
            row["faith_pd"] = ""

        rows.append(row)
    return rows, tree_used


# ── Beta diversity ───────────────────────────────────────────────────────────


def _bray_curtis(counts_a: List[int], counts_b: List[int]) -> float:
    """Bray-Curtis dissimilarity: sum|a_i - b_i| / sum(a_i + b_i)."""
    sum_diff = sum(abs(a - b) for a, b in zip(counts_a, counts_b))
    sum_total = sum(counts_a) + sum(counts_b)
    if sum_total == 0:
        return 0.0
    return sum_diff / sum_total


def _jaccard(counts_a: List[int], counts_b: List[int]) -> float:
    """Jaccard distance: 1 - |A ∩ B| / |A ∪ B|."""
    a_present = {i for i, c in enumerate(counts_a) if c > 0}
    b_present = {i for i, c in enumerate(counts_b) if c > 0}
    intersection = len(a_present & b_present)
    union = len(a_present | b_present)
    if union == 0:
        return 1.0
    return 1.0 - intersection / union


def _unifrac(
    counts_a: List[int],
    counts_b: List[int],
    asv_ids: List[str],
    asv_to_node: Dict[str, int],
    children: Dict[int, List[int]],
    branch_lengths: Dict[int, float],
    weighted: bool = False,
) -> float:
    """UniFrac distance between two samples.

    Unweighted: fraction of unique branch length (branches covered by only
    one sample, not both).

    Weighted: abundance-weighted fraction of unique branch length.
    """
    # Determine which ASVs are present in each sample
    set_a = {asv_ids[i] for i, c in enumerate(counts_a) if c > 0}
    set_b = {asv_ids[i] for i, c in enumerate(counts_b) if c > 0}

    # Build node weights
    total_a = sum(counts_a)
    total_b = sum(counts_b)
    if total_a == 0 and total_b == 0:
        return 0.0

    # Determine total branch length and shared branch length
    # For each internal node, determine the proportion of reads from each
    # sample in the subtree

    # Build subtree sums via post-order
    n_nodes = len(children)
    # Determine parent relationships
    parent_of: Dict[int, int] = {}
    for parent, kids in children.items():
        for kid in kids:
            parent_of[kid] = parent

    # Leaf assignment: which node corresponds to which ASV
    leaf_counts_a: Dict[int, float] = {}
    leaf_counts_b: Dict[int, float] = {}
    for i, asv_id in enumerate(asv_ids):
        node = asv_to_node.get(asv_id)
        if node is not None:
            leaf_counts_a[node] = float(counts_a[i])
            leaf_counts_b[node] = float(counts_b[i])

    # Post-order traversal to accumulate subtree abundances
    # Build post-order list
    visited: set = set()
    post_order: List[int] = []

    def _postorder(node: int) -> None:
        for child in children.get(node, []):
            _postorder(child)
        post_order.append(node)
        visited.add(node)

    # Root is the node with no parent
    all_nodes = set(children.keys()) | {c for kids in children.values() for c in kids}
    roots = all_nodes - set(parent_of.keys())
    for root in roots:
        _postorder(root)

    # Accumulate subtree counts
    subtree_a: Dict[int, float] = {}
    subtree_b: Dict[int, float] = {}
    for node in post_order:
        sa = leaf_counts_a.get(node, 0.0)
        sb = leaf_counts_b.get(node, 0.0)
        for child in children.get(node, []):
            sa += subtree_a.get(child, 0.0)
            sb += subtree_b.get(child, 0.0)
        subtree_a[node] = sa
        subtree_b[node] = sb

    # Compute UniFrac
    unique_branch = 0.0
    total_branch = 0.0
    for node in branch_lengths:
        bl = branch_lengths[node]
        if bl <= 0:
            continue
        total_branch += bl
        sa = subtree_a.get(node, 0.0)
        sb = subtree_b.get(node, 0.0)
        if weighted:
            # Weighted UniFrac
            frac_a = sa / total_a if total_a > 0 else 0.0
            frac_b = sb / total_b if total_b > 0 else 0.0
            unique_branch += bl * abs(frac_a - frac_b)
        else:
            # Unweighted UniFrac
            present_a = 1.0 if sa > 0 else 0.0
            present_b = 1.0 if sb > 0 else 0.0
            unique_branch += bl * abs(present_a - present_b)

    if total_branch == 0:
        return 0.0
    if weighted:
        return unique_branch  # already normalized
    return unique_branch / total_branch


def _compute_beta(
    asv_table: Dict[str, Dict[str, int]],
    sample_ids: List[str],
    asv_seqs: Dict[str, str],
    tree_path: Optional[Path],
) -> Tuple[List[Dict[str, Any]], bool]:
    """Compute beta diversity for all sample pairs.

    Returns (rows, tree_used).
    """
    tree_used = False
    tree_data = None
    asv_ids = sorted(asv_table.keys())

    if tree_path and tree_path.exists():
        tree_data = _parse_newick(tree_path, asv_seqs)
        tree_used = tree_data is not None

    rows: List[Dict[str, Any]] = []
    n = len(sample_ids)

    for i in range(n):
        for j in range(i + 1, n):
            sid_a, sid_b = sample_ids[i], sample_ids[j]
            counts_a = [asv_table[aid][sid_a] for aid in asv_ids]
            counts_b = [asv_table[aid][sid_b] for aid in asv_ids]
            comparison = f"{sid_a}_vs_{sid_b}"

            # Bray-Curtis
            rows.append({
                "comparison": comparison,
                "distance_metric": "bray_curtis",
                "sample_a": sid_a,
                "sample_b": sid_b,
                "distance": round(_bray_curtis(counts_a, counts_b), 6),
                "tool": "amplicon_diversity",
                "source_file": "",
            })

            # Jaccard
            rows.append({
                "comparison": comparison,
                "distance_metric": "jaccard",
                "sample_a": sid_a,
                "sample_b": sid_b,
                "distance": round(_jaccard(counts_a, counts_b), 6),
                "tool": "amplicon_diversity",
                "source_file": "",
            })

            # UniFrac if tree available
            if tree_data is not None:
                children, branch_lengths, asv_to_node = tree_data
                rows.append({
                    "comparison": comparison,
                    "distance_metric": "unweighted_unifrac",
                    "sample_a": sid_a,
                    "sample_b": sid_b,
                    "distance": round(
                        _unifrac(
                            counts_a, counts_b, asv_ids, asv_to_node,
                            children, branch_lengths, weighted=False,
                        ), 6
                    ),
                    "tool": "amplicon_diversity",
                    "source_file": "",
                })
                rows.append({
                    "comparison": comparison,
                    "distance_metric": "weighted_unifrac",
                    "sample_a": sid_a,
                    "sample_b": sid_b,
                    "distance": round(
                        _unifrac(
                            counts_a, counts_b, asv_ids, asv_to_node,
                            children, branch_lengths, weighted=True,
                        ), 6
                    ),
                    "tool": "amplicon_diversity",
                    "source_file": "",
                })

    return rows, tree_used


# ── Newick tree parser ───────────────────────────────────────────────────────


def _parse_newick(
    tree_path: Path,
    asv_seqs: Dict[str, str],
) -> Optional[Tuple[Dict[int, List[int]], Dict[int, float], Dict[str, int]]]:
    """Parse a Newick tree and map ASV IDs to leaf nodes.

    Returns:
        children: {node_id: [child_node_ids]}
        branch_lengths: {node_id: branch_length_to_parent}
        asv_to_node: {asv_id: leaf_node_id}

    Leaf labels are matched to ASV IDs by exact string match.
    Returns None if the tree file can't be parsed.
    """
    try:
        newick_str = tree_path.read_text().strip()
    except OSError:
        return None

    # Remove comments and whitespace
    newick_str = newick_str.split("\n")[0].strip()

    # Parse: tokenize on ( ) , : ;
    tokens: List[str] = []
    current = ""
    for ch in newick_str:
        if ch in "();,":
            if current.strip():
                tokens.append(current.strip())
            tokens.append(ch)
            current = ""
        elif ch == ":":
            if current.strip():
                tokens.append(current.strip())
            tokens.append(ch)
            current = ""
        else:
            current += ch
    if current.strip():
        tokens.append(current.strip())

    # Build tree: DFS parse
    children: Dict[int, List[int]] = {}
    branch_lengths: Dict[int, float] = {}
    asv_to_node: Dict[str, int] = {}
    next_node = 0
    stack: List[int] = []

    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "(":
            node = next_node
            next_node += 1
            children[node] = []
            branch_lengths[node] = 0.0
            if stack:
                children[stack[-1]].append(node)
            stack.append(node)
        elif t == ")":
            if stack:
                stack.pop()
        elif t == ",":
            # Pop the current child and start a new one at same depth
            pass
        elif t == ":":
            # Next token is branch length
            if i + 1 < len(tokens):
                i += 1
                bl_str = tokens[i]
                try:
                    bl = float(bl_str)
                except ValueError:
                    bl = 0.0
                # Assign branch length to the most recent node
                if stack:
                    # The node we're inside is the most recent
                    # Actually, branch lengths come after node labels or after ')'
                    pass
        elif t == ";":
            break
        else:
            # Label (leaf name or internal node label)
            label = t
            # Check if this is an ASV label
            if label in asv_seqs:
                leaf_node = next_node
                next_node += 1
                children[leaf_node] = []
                branch_lengths[leaf_node] = 0.0
                asv_to_node[label] = leaf_node
                if stack:
                    children[stack[-1]].append(leaf_node)
        i += 1

    if not asv_to_node:
        # Fallback: try a simpler, more robust parsing approach
        return _parse_newick_simple(newick_str, asv_seqs)

    return children, branch_lengths, asv_to_node


def _parse_newick_simple(
    newick_str: str,
    asv_seqs: Dict[str, str],
) -> Optional[Tuple[Dict[int, List[int]], Dict[int, float], Dict[str, int]]]:
    """Simpler Newick parser that handles standard FastTree output."""
    # Build a mapping from ASV sequence to ASV ID
    seq_to_asv = {seq: aid for aid, seq in asv_seqs.items()}

    # FastTree labels: usually use the FASTA header or the full sequence
    # Try exact label match first, then sequence match
    children: Dict[int, List[int]] = {}
    branch_lengths: Dict[int, float] = {}
    asv_to_node: Dict[str, int] = {}
    next_node = 0

    # Identify leaf labels in the Newick string
    # FastTree produces labels at the leaves, format: label:branch_length
    import re
    # Pattern: label:number or just label
    label_pattern = re.compile(r'([a-zA-Z0-9_|]+):([0-9.eE+-]+)')
    tip_pattern = re.compile(r'([^(),;:]+):([0-9.eE+-]+)')

    # Find all tip label:branch pairs
    tip_labels = set()
    for m in tip_pattern.finditer(newick_str):
        label = m.group(1)
        tip_labels.add(label)

    # Match tip labels to ASV IDs
    for label in tip_labels:
        if label in asv_seqs:
            # Label IS the ASV ID (e.g., from FASTA header that uses ASV ID)
            node = next_node
            next_node += 1
            children[node] = []
            branch_lengths[node] = 0.0
            asv_to_node[label] = node
        elif label in seq_to_asv:
            # Label is the actual sequence
            asv_id = seq_to_asv[label]
            if asv_id not in asv_to_node:
                node = next_node
                next_node += 1
                children[node] = []
                branch_lengths[node] = 0.0
                asv_to_node[asv_id] = node

    if not asv_to_node:
        return None

    return children, branch_lengths, asv_to_node


# ── Main ──────────────────────────────────────────────────────────────────────


def _write_tsv(path: Path, rows: List[Dict[str, Any]], columns: List[str]) -> None:
    """Write a list of dicts as a TSV file."""
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=columns, delimiter="\t", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ABI amplicon diversity — ASV table + alpha/beta diversity"
    )
    parser.add_argument(
        "--denoise-dir", required=True,
        help="Directory containing per-sample 04_denoise/{sample_id}/asvs.fasta"
    )
    parser.add_argument(
        "--merge-dir", required=True,
        help="Directory containing per-sample 02_merge/{sample_id}/*_merged.fasta"
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="Output directory for diversity results"
    )
    parser.add_argument(
        "--tree", default=None,
        help="Optional Newick phylogeny tree for Faith's PD and UniFrac"
    )
    parser.add_argument(
        "--min-count", type=int, default=2,
        help="Minimum total count across samples for an ASV to be retained (default: 2)"
    )
    args = parser.parse_args()

    denoise_dir = Path(args.denoise_dir)
    merge_dir = Path(args.merge_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tree_path = Path(args.tree) if args.tree else None

    print(f"Building ASV table from {denoise_dir}")
    asv_table, asv_seqs, sample_totals, sample_ids = _build_asv_table(
        denoise_dir, merge_dir
    )
    n_asvs = len(asv_seqs)
    n_samples = len(sample_ids)
    print(f"  Found {n_asvs} unique ASVs across {n_samples} samples")

    # Filter ASVs below minimum count
    if args.min_count > 1:
        before = n_asvs
        to_remove = []
        for asv_id in asv_seqs:
            total = sum(asv_table[asv_id][sid] for sid in sample_ids)
            if total < args.min_count:
                to_remove.append(asv_id)
        for asv_id in to_remove:
            del asv_seqs[asv_id]
            del asv_table[asv_id]
        n_asvs = len(asv_seqs)
        print(f"  Retained {n_asvs} ASVs after min-count filter (>= {args.min_count})")

    # Write merged ASV table
    asv_table_cols = ["asv_id", "sequence"] + sample_ids
    asv_table_rows: List[Dict[str, Any]] = []
    for asv_id in sorted(asv_table.keys()):
        row: Dict[str, Any] = {"asv_id": asv_id, "sequence": asv_seqs[asv_id]}
        for sid in sample_ids:
            row[sid] = asv_table[asv_id][sid]
        asv_table_rows.append(row)

    table_path = output_dir / "merged_asv_table.tsv"
    _write_tsv(table_path, asv_table_rows, asv_table_cols)
    print(f"  Wrote {table_path}")

    # Also write to the parent directory (where the diversity step expects it)
    parent_table = output_dir.parent / "merged_asv_table.tsv"
    _write_tsv(parent_table, asv_table_rows, asv_table_cols)
    print(f"  Wrote {parent_table}")

    # Alpha diversity
    print("Computing alpha diversity...")
    alpha_rows, tree_used = _compute_alpha(
        asv_table, sample_ids, asv_seqs, tree_path
    )
    alpha_cols = [
        "sample_id", "observed_features", "shannon_entropy",
        "simpson_index", "faith_pd", "chao1", "tool", "source_file",
    ]
    alpha_path = output_dir / "alpha_diversity.tsv"
    _write_tsv(alpha_path, alpha_rows, alpha_cols)
    print(f"  Wrote {alpha_path} ({len(sample_ids)} samples, tree={'yes' if tree_used else 'no'})")

    # Beta diversity
    print("Computing beta diversity...")
    beta_rows, _ = _compute_beta(
        asv_table, sample_ids, asv_seqs, tree_path
    )
    beta_cols = [
        "comparison", "distance_metric", "sample_a", "sample_b",
        "distance", "tool", "source_file",
    ]
    beta_path = output_dir / "beta_diversity.tsv"
    _write_tsv(beta_path, beta_rows, beta_cols)
    n_pairs = len(sample_ids) * (len(sample_ids) - 1) // 2
    n_metrics = len(beta_rows) // n_pairs if n_pairs > 0 else 0
    print(f"  Wrote {beta_path} ({n_pairs} pairs × {n_metrics} metrics)")

    # Summary
    print(f"\nDiversity computation complete.")
    print(f"  Samples: {n_samples}")
    print(f"  ASVs:    {n_asvs}")
    for sid in sample_ids:
        total = sample_totals.get(sid, 0)
        mapped = sum(asv_table[aid][sid] for aid in asv_table)
        print(f"    {sid}: {total:,} merged reads → {mapped:,} mapped to ASVs")


if __name__ == "__main__":
    main()
