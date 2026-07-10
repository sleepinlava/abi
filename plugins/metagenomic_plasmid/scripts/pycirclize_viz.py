#!/usr/bin/env python3
"""Generate a circular plasmid map using pycirclize."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Generate circular plasmid map")
    parser.add_argument("--annotations", required=True, help="Path to annotations TSV")
    parser.add_argument("--typing", required=True, help="Path to typing TSV")
    parser.add_argument("--contigs", required=True, help="Path to plasmid contigs FASTA")
    parser.add_argument("--sample", required=True, help="Sample ID for output filename")
    parser.add_argument("--outdir", required=True, help="Output directory")
    args = parser.parse_args()

    try:
        import pandas as pd
        from pycirclize import Circos
    except ImportError as e:
        print(f"Missing dependency: {e}", file=sys.stderr)
        sys.exit(1)

    _ann = pd.read_csv(args.annotations, sep="\t")
    _typing = pd.read_csv(args.typing, sep="\t")

    # Read contig names from FASTA
    contig_ids = []
    with open(args.contigs) as f:
        for line in f:
            if line.startswith(">"):
                contig_ids.append(line[1:].split()[0])

    # Use the contig IDs as sectors
    sectors = {cid: 500 for cid in contig_ids} if contig_ids else {"plasmid": 500}
    circos = Circos(sectors)
    circos.savefig(f"{args.outdir}/{args.sample}.circular_map.png")


if __name__ == "__main__":
    main()
