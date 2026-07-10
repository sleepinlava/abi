#!/usr/bin/env python3
"""Generate host-plasmid network graph using pyvis."""

import argparse
import sys
from pathlib import Path

from abi.path_policy import validate_sample_id


def main():
    parser = argparse.ArgumentParser(description="Generate host-plasmid network")
    parser.add_argument("--links", required=True, help="Path to host-plasmid links TSV")
    parser.add_argument("--sample", required=True, help="Sample ID for output filename")
    parser.add_argument("--outdir", required=True, help="Output directory")
    args = parser.parse_args()
    sample_id = validate_sample_id(args.sample)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    try:
        import pandas as pd
        from pyvis.network import Network
    except ImportError as e:
        print(f"Missing dependency: {e}", file=sys.stderr)
        sys.exit(1)

    links = pd.read_csv(args.links, sep="\t")
    net = Network(height="750px", width="100%")

    # Add nodes and edges from the links table
    # Expected columns: host (source), plasmid (target), weight (optional)
    for _, row in links.iterrows():
        host = str(row.iloc[0])
        plasmid = str(row.iloc[1])
        weight = row.iloc[2] if len(row) > 2 else 1
        net.add_node(host, label=host, color="#4a90d9")
        net.add_node(plasmid, label=plasmid, color="#d94a4a")
        net.add_edge(host, plasmid, value=float(weight))

    net.show_buttons()
    net.save_graph(str(outdir / f"{sample_id}.host_plasmid_network.html"))


if __name__ == "__main__":
    main()
