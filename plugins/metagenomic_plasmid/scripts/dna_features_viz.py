#!/usr/bin/env python3
"""Generate DNA features visualization from plasmid FASTA."""

import argparse
import sys
from pathlib import Path

from abi.path_policy import validate_sample_id


def main():
    parser = argparse.ArgumentParser(description="DNA features visualization")
    parser.add_argument("--contigs", required=True, help="Path to plasmid contigs FASTA")
    parser.add_argument("--features", default=None, help="Optional GFF features file")
    parser.add_argument("--sample", required=True, help="Sample ID for output filename")
    parser.add_argument("--outdir", required=True, help="Output directory")
    args = parser.parse_args()
    sample_id = validate_sample_id(args.sample)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    try:
        from Bio import SeqIO
        from dna_features_viewer import BiopythonTranslator, GraphicRecord
    except ImportError as e:
        print(f"Missing dependency: {e}", file=sys.stderr)
        sys.exit(1)

    rec = SeqIO.read(args.contigs, "fasta")

    if args.features:
        translator = BiopythonTranslator()
        features = translator.translate_from(args.features)
        graph = GraphicRecord(sequence=str(rec.seq), features=features)
    else:
        graph = GraphicRecord(sequence=str(rec.seq), features=[])

    graph.plot(figure_width=10, output=str(outdir / f"{sample_id}.features.png"))


if __name__ == "__main__":
    main()
