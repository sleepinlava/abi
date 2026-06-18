#!/usr/bin/env python3
"""Download E. coli K-12 MG1655 reference and build STAR index for rnaseq_expression benchmarking.

Downloads NC_000913.3 genome FASTA + GTF annotation from NCBI (~5 MB total),
then runs STAR --runMode genomeGenerate to build the index.

Usage:
    python scripts/setup_rnaseq_benchmark.py                # default: resources/star_index/
    python scripts/setup_rnaseq_benchmark.py --output /path/to/star_index
    python scripts/setup_rnaseq_benchmark.py --dry-run      # show what would happen
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from urllib.request import urlretrieve

# ── Constants ────────────────────────────────────────────────────────────────
GENOME_ACC = "NC_000913.3"
GENOME_URL = "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/005/845/GCF_000005845.2_ASM584v2/GCF_000005845.2_ASM584v2_genomic.fna.gz"
GTF_URL = "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/005/845/GCF_000005845.2_ASM584v2/GCF_000005845.2_ASM584v2_genomic.gtf.gz"
# Fallback: use the refseq representative genome
GENOME_URL_FALLBACK = "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/bacteria/Escherichia_coli/reference/GCF_000005845.2_ASM584v2/GCF_000005845.2_ASM584v2_genomic.fna.gz"
GTF_URL_FALLBACK = "https://ftp.ncbi.nlm.nih.gov/genomes/refseq/bacteria/Escherichia_coli/reference/GCF_000005845.2_ASM584v2/GCF_000005845.2_ASM584v2_genomic.gtf.gz"

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "resources" / "star_index"
MARKER_FILE = ".abi_star_index_built"


def _download(url: str, dest: Path, label: str) -> bool:
    """Download a file with progress reporting. Returns True on success."""
    if dest.exists():
        print(f"  {label}: already exists ({dest.stat().st_size:,} bytes)")
        return True

    print(f"  Downloading {label}...")
    try:
        urlretrieve(url, dest)
        print(f"    → {dest.stat().st_size:,} bytes")
        return True
    except Exception as exc:
        print(f"    Download failed: {exc}")
        return False


def _sha256(path: Path) -> str:
    """Compute SHA256 of a file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def setup_reference(
    output_dir: Path,
    *,
    dry_run: bool = False,
    threads: int = 4,
) -> dict:
    """Download reference genome and GTF, build STAR index.

    Returns a dict with resource manifest entries.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    genome_gz = output_dir / f"{GENOME_ACC}.fna.gz"
    gtf_gz = output_dir / f"{GENOME_ACC}.gtf.gz"
    genome_fa = output_dir / f"{GENOME_ACC}.fna"
    gtf = output_dir / f"{GENOME_ACC}.gtf"

    manifest = {"resources": [], "star_index_dir": str(output_dir)}

    if dry_run:
        print(f"[DRY RUN] Would download genome to {genome_gz}")
        print(f"[DRY RUN] Would download GTF to {gtf_gz}")
        print(f"[DRY RUN] Would build STAR index in {output_dir}")
        return manifest

    # 1. Download genome FASTA
    ok = _download(GENOME_URL, genome_gz, "genome FASTA")
    if not ok:
        ok = _download(GENOME_URL_FALLBACK, genome_gz, "genome FASTA (fallback)")
    if not ok:
        raise RuntimeError("Failed to download genome FASTA")

    # 2. Download annotation GTF
    ok = _download(GTF_URL, gtf_gz, "annotation GTF")
    if not ok:
        ok = _download(GTF_URL_FALLBACK, gtf_gz, "annotation GTF (fallback)")
    if not ok:
        raise RuntimeError("Failed to download annotation GTF")

    # 3. Decompress
    import gzip

    if not genome_fa.exists():
        print(f"  Decompressing {genome_gz.name}...")
        with gzip.open(genome_gz, "rb") as src, genome_fa.open("wb") as dst:
            dst.write(src.read())

    if not gtf.exists():
        print(f"  Decompressing {gtf_gz.name}...")
        with gzip.open(gtf_gz, "rb") as src, gtf.open("wb") as dst:
            dst.write(src.read())

    manifest["resources"].append(
        {
            "id": "reference_genome",
            "path": str(genome_fa),
            "version": GENOME_ACC,
            "source_url": GENOME_URL,
            "sha256": _sha256(genome_fa),
        }
    )
    manifest["resources"].append(
        {
            "id": "annotation_gtf",
            "path": str(gtf),
            "version": GENOME_ACC,
            "source_url": GTF_URL,
            "sha256": _sha256(gtf),
        }
    )

    # 4. Build STAR index (skip if marker exists and index looks valid)
    marker = output_dir / MARKER_FILE
    genome_params = output_dir / "genomeParameters.txt"
    if marker.exists() and genome_params.exists():
        print("  STAR index already built (marker file found). Skipping.")
    else:
        print(f"  Building STAR index (using {threads} threads)...")
        # STAR expects the genome FASTA to NOT be compressed
        cmd = [
            "STAR",
            "--runMode",
            "genomeGenerate",
            "--genomeDir",
            str(output_dir),
            "--genomeFastaFiles",
            str(genome_fa),
            "--sjdbGTFfile",
            str(gtf),
            "--genomeSAindexNbases",
            "8",  # log2(4.6e6)/2 - 1 ≈ 8 for E. coli
            "--runThreadN",
            str(threads),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"  STAR stdout:\n{proc.stdout[-1000:]}")
            print(f"  STAR stderr:\n{proc.stderr[-1000:]}")
            raise RuntimeError(f"STAR genomeGenerate failed (exit {proc.returncode})")
        marker.write_text("built\n")
        print("  STAR index built successfully.")

    # 5. Write manifest
    manifest_path = output_dir / "resource_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\n✓ Reference setup complete: {output_dir}")
    print(f"  Resources: {len(manifest['resources'])} entries")
    return manifest


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Set up E. coli reference for rnaseq_expression benchmark"
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Output directory for STAR index (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument("--threads", type=int, default=4, help="Threads for STAR (default: 4)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    args = parser.parse_args()

    output_dir = Path(args.output)
    setup_reference(output_dir, dry_run=args.dry_run, threads=args.threads)


if __name__ == "__main__":
    main()
