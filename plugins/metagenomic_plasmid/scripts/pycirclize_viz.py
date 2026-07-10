#!/usr/bin/env python3
"""Generate a circular plasmid map using pycirclize."""

import argparse
import sys
from pathlib import Path

from abi.path_policy import validate_sample_id


def main():
    parser = argparse.ArgumentParser(description="Generate circular plasmid map")
    parser.add_argument("--annotations", required=True, help="Path to annotations TSV")
    parser.add_argument("--typing", required=True, help="Path to typing TSV")
    parser.add_argument("--contigs", required=True, help="Path to plasmid contigs FASTA")
    parser.add_argument("--sample", required=True, help="Sample ID for output filename")
    parser.add_argument("--outdir", required=True, help="Output directory")
    args = parser.parse_args()
    sample_id = validate_sample_id(args.sample)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    try:
        import pandas as pd
        from pycirclize import Circos
    except ImportError as e:
        print(f"Missing dependency: {e}", file=sys.stderr)
        sys.exit(1)

    _ann = pd.read_csv(args.annotations, sep="\t")
    _typing = pd.read_csv(args.typing, sep="\t")

    # Read contig names and lengths from FASTA.
    sectors = {}
    current_id = None
    current_length = 0
    with open(args.contigs, encoding="utf-8") as f:
        for line in f:
            if line.startswith(">"):
                if current_id is not None:
                    sectors[current_id] = current_length
                current_id = line[1:].split()[0]
                current_length = 0
            else:
                current_length += len(line.strip())
    if current_id is not None:
        sectors[current_id] = current_length

    if not sectors:
        sectors = {"plasmid": 1}
    circos = Circos(sectors)
    circos.savefig(str(outdir / f"{sample_id}.circular_map.png"))


if __name__ == "__main__":
    main()
