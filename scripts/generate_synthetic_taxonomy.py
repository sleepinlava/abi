#!/usr/bin/env python3
"""Generate a minimal synthetic 16S taxonomy database for testing vsearch SINTAX.

Produces a FASTA file with SINTAX-formatted taxonomy headers covering the
most common bacterial phyla/classes.  Each "sequence" is a 200-400 bp fragment
of real 16S rRNA conserved regions (not random — derived from E. coli rrnB).

Usage:
    python scripts/generate_synthetic_taxonomy.py
    python scripts/generate_synthetic_taxonomy.py --output /path/to/sintax.fa --entries 200

The output is suitable for:
    vsearch --sintax asvs.fasta --db sintax.fa --tabbedout taxonomy.tsv

Design note: this is a TESTING database.  Taxonomic assignments from it are
not biologically meaningful.  For real analysis, download the RDP training set
(v16, ~50 MB) via ``scripts/download_rdp_sintax.sh``.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

# ── 16S rRNA conserved region fragments (E. coli rrnB V3-V4 region) ──────
# These are real 16S sequences that vsearch SINTAX can match against.
_TEMPLATE_16S = (
    "ATTGAACGCTGGCGGCAGGCCTAACACATGCAAGTCGAACGGTAACAGGAAGCAGCTTGCTGCTTTGCTGACGAG"
    "TGGCGGACGGGTGAGTAATGTCTGGGAAACTGCCTGATGGAGGGGGATAACTACTGGAAACGGTAGCTAATACCG"
    "CATAACGTCGCAAGACCAAAGAGGGGGACCTTCGGGCCTCTTGCCATCAGATGTGCCCAGATGGGATTAGCTAGT"
    "AGGTGGGGTAACGGCTCACCTAGGCGACGATCCCTAGCTGGTCTGAGAGGATGACCAGCCACACTGGAACTGAGA"
    "CACGGTCCAGACTCCTACGGGAGGCAGCAGTGGGGAATATTGCACAATGGGCGCAAGCCTGATGCAGCCATGCCG"
    "CGTGTATGAAGAAGGCCTTCGGGTTGTAAAGTACTTTCAGCGGGGAGGAAGGGAGTAAAGTTAATACCTTTGCTC"
    "ATTGACGTTACCCGCAGAAGAAGCACCGGCTAACTCCGTGCCAGCAGCCGCGGTAATACGGAGGGTGCAAGCGTT"
    "AATCGGAATTACTGGGCGTAAAGCGCACGCAGGCGGTTTGTTAAGTCAGATGTGAAATCCCCGGGCTCAACCTGG"
    "GAACTGCATCTGATACTGGCAAGCTTGAGTCTCGTAGAGGGGGGTAGAATTCCAGGTGTAGCGGTGAAATGCGTA"
    "GAGATCTGGAGGAATACCGGTGGCGAAGGCGGCCCCCTGGACGAAGACTGACGCTCAGGTGCGAAAGCGTGGGGA"
    "GCAAACAGGATTAGATACCCTGGTAGTCCACGCCGTAAACGATGTCGACTTGGAGGTTGTGCCCTTGAGGCGTGG"
    "CTTCCGGAGCTAACGCGTTAAGTCGACCGCCTGGGGAGTACGGCCGCAAGGTTAAAACTCAAATGAATTGACGGG"
    "GGCCCGCACAAGCGGTGGAGCATGTGGTTTAATTCGATGCAACGCGAAGAACCTTACCTGGTCTTGACATCCACG"
)

# ── Bacterial taxonomy tree (common genera by phylum) ─────────────────────
_TAXONOMY_TREE: dict[str, list[tuple[str, str]]] = {
    "d:Bacteria,p:Proteobacteria,c:Gammaproteobacteria,o:Enterobacterales,f:Enterobacteriaceae": [
        ("g:Escherichia", "s:coli"),
        ("g:Salmonella", "s:enterica"),
        ("g:Klebsiella", "s:pneumoniae"),
        ("g:Shigella", "s:flexneri"),
        ("g:Enterobacter", "s:cloacae"),
    ],
    "d:Bacteria,p:Proteobacteria,c:Gammaproteobacteria,o:Pseudomonadales,f:Pseudomonadaceae": [
        ("g:Pseudomonas", "s:aeruginosa"),
        ("g:Pseudomonas", "s:putida"),
        ("g:Pseudomonas", "s:fluorescens"),
    ],
    "d:Bacteria,p:Proteobacteria,c:Gammaproteobacteria,o:Vibrionales,f:Vibrionaceae": [
        ("g:Vibrio", "s:cholerae"),
        ("g:Vibrio", "s:parahaemolyticus"),
    ],
    "d:Bacteria,p:Proteobacteria,c:Alphaproteobacteria,o:Rhizobiales,f:Rhizobiaceae": [
        ("g:Rhizobium", "s:leguminosarum"),
        ("g:Agrobacterium", "s:tumefaciens"),
        ("g:Bradyrhizobium", "s:japonicum"),
    ],
    "d:Bacteria,p:Proteobacteria,c:Alphaproteobacteria,o:Rickettsiales,f:Anaplasmataceae": [
        ("g:Wolbachia", "s:pipientis"),
        ("g:Ehrlichia", "s:chaffeensis"),
    ],
    "d:Bacteria,p:Firmicutes,c:Bacilli,o:Lactobacillales,f:Lactobacillaceae": [
        ("g:Lactobacillus", "s:acidophilus"),
        ("g:Lactobacillus", "s:plantarum"),
        ("g:Lactobacillus", "s:rhamnosus"),
        ("g:Leuconostoc", "s:mesenteroides"),
        ("g:Pediococcus", "s:pentosaceus"),
    ],
    "d:Bacteria,p:Firmicutes,c:Bacilli,o:Bacillales,f:Bacillaceae": [
        ("g:Bacillus", "s:subtilis"),
        ("g:Bacillus", "s:cereus"),
        ("g:Bacillus", "s:anthracis"),
    ],
    "d:Bacteria,p:Firmicutes,c:Bacilli,o:Bacillales,f:Staphylococcaceae": [
        ("g:Staphylococcus", "s:aureus"),
        ("g:Staphylococcus", "s:epidermidis"),
    ],
    "d:Bacteria,p:Firmicutes,c:Bacilli,o:Lactobacillales,f:Streptococcaceae": [
        ("g:Streptococcus", "s:pneumoniae"),
        ("g:Streptococcus", "s:pyogenes"),
        ("g:Lactococcus", "s:lactis"),
    ],
    "d:Bacteria,p:Firmicutes,c:Clostridia,o:Clostridiales,f:Clostridiaceae": [
        ("g:Clostridium", "s:perfringens"),
        ("g:Clostridium", "s:difficile"),
        ("g:Clostridium", "s:botulinum"),
    ],
    "d:Bacteria,p:Bacteroidetes,c:Bacteroidia,o:Bacteroidales,f:Bacteroidaceae": [
        ("g:Bacteroides", "s:fragilis"),
        ("g:Bacteroides", "s:thetaiotaomicron"),
    ],
    "d:Bacteria,p:Bacteroidetes,c:Bacteroidia,o:Bacteroidales,f:Porphyromonadaceae": [
        ("g:Porphyromonas", "s:gingivalis"),
        ("g:Parabacteroides", "s:distasonis"),
    ],
    "d:Bacteria,p:Bacteroidetes,c:Flavobacteriia,o:Flavobacteriales,f:Flavobacteriaceae": [
        ("g:Flavobacterium", "s:psychrophilum"),
        ("g:Flavobacterium", "s:columnare"),
    ],
    "d:Bacteria,p:Actinobacteria,c:Actinobacteria,o:Actinomycetales,f:Micrococcaceae": [
        ("g:Micrococcus", "s:luteus"),
        ("g:Arthrobacter", "s:globiformis"),
    ],
    "d:Bacteria,p:Actinobacteria,c:Actinobacteria,o:Actinomycetales,f:Corynebacteriaceae": [
        ("g:Corynebacterium", "s:diphtheriae"),
    ],
    "d:Bacteria,p:Actinobacteria,c:Actinobacteria,o:Bifidobacteriales,f:Bifidobacteriaceae": [
        ("g:Bifidobacterium", "s:bifidum"),
        ("g:Bifidobacterium", "s:longum"),
        ("g:Bifidobacterium", "s:adolescentis"),
    ],
    "d:Bacteria,p:Cyanobacteria,c:Cyanophyceae,o:Synechococcales,f:Synechococcaceae": [
        ("g:Synechococcus", "s:elongatus"),
        ("g:Prochlorococcus", "s:marinus"),
    ],
    "d:Bacteria,p:Cyanobacteria,c:Cyanophyceae,o:Nostocales,f:Nostocaceae": [
        ("g:Nostoc", "s:commune"),
        ("g:Anabaena", "s:variabilis"),
    ],
    "d:Bacteria,p:Spirochaetes,c:Spirochaetia,o:Spirochaetales,f:Spirochaetaceae": [
        ("g:Borrelia", "s:burgdorferi"),
        ("g:Treponema", "s:pallidum"),
    ],
    "d:Bacteria,p:Chlamydiae,c:Chlamydiia,o:Chlamydiales,f:Chlamydiaceae": [
        ("g:Chlamydia", "s:trachomatis"),
    ],
    # Archaea
    "d:Archaea,p:Euryarchaeota,c:Methanobacteria,o:Methanobacteriales,f:Methanobacteriaceae": [
        ("g:Methanobacterium", "s:formicicum"),
        ("g:Methanobrevibacter", "s:smithii"),
        ("g:Methanosphaera", "s:stadtmanae"),
    ],
    "d:Archaea,p:Euryarchaeota,c:Halobacteria,o:Halobacteriales,f:Halobacteriaceae": [
        ("g:Halobacterium", "s:salinarum"),
        ("g:Haloferax", "s:volcanii"),
    ],
    "d:Archaea,p:Crenarchaeota,c:Thermoprotei,o:Sulfolobales,f:Sulfolobaceae": [
        ("g:Sulfolobus", "s:acidocaldarius"),
        ("g:Sulfolobus", "s:solfataricus"),
    ],
}


def _mutate_seq(seq: str, n_mutations: int, rng: random.Random) -> str:
    """Introduce point mutations to simulate genus/species divergence."""
    bases = list(seq)
    for _ in range(n_mutations):
        pos = rng.randint(0, len(bases) - 1)
        bases[pos] = rng.choice("ACGT")
    return "".join(bases)


def generate_synthetic_taxonomy(
    output_path: Path,
    n_entries: int = 200,
    seed: int = 42,
) -> int:
    """Generate a SINTAX-formatted taxonomy FASTA.

    Returns the number of sequences written.
    """
    rng = random.Random(seed)
    lineages = list(_TAXONOMY_TREE.items())

    # Expand each lineage into every genus-species combination
    all_entries: list[tuple[str, str, str]] = []
    for lineage, genera in lineages:
        for genus, species in genera:
            tax = f"{lineage},{genus},{species}"
            seq_id = f"{genus.split(':')[1]}_{species.split(':')[1]}"
            all_entries.append((seq_id, tax, _TEMPLATE_16S))

    # Pad with variants if we need more entries
    while len(all_entries) < n_entries:
        lineage, genera = rng.choice(lineages)
        genus, species = rng.choice(genera)
        tax = f"{lineage},{genus},{species}"
        seq_id = f"{genus.split(':')[1]}_{species.split(':')[1]}_v{len(all_entries)}"
        all_entries.append((seq_id, tax, _TEMPLATE_16S))

    rng.shuffle(all_entries)
    count = 0

    with output_path.open("w", encoding="utf-8") as fh:
        for seq_id, tax, template in all_entries[:n_entries]:
            # Degree of mutation increases at species level to create
            # realistic inter-species variation
            n_mut = rng.randint(30, 80)
            seq = _mutate_seq(template, n_mut, rng)
            # Take a random fragment of varying length
            frag_len = rng.randint(200, min(400, len(seq)))
            start = rng.randint(0, len(seq) - frag_len)
            fragment = seq[start : start + frag_len]
            fh.write(f">{seq_id}_{count};tax={tax}\n")
            fh.write(f"{fragment}\n")
            count += 1

    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a synthetic 16S taxonomy DB for vsearch SINTAX testing"
    )
    parser.add_argument(
        "--output", default="data/taxonomy/synthetic_sintax.fa",
        help="Output FASTA path (default: data/taxonomy/synthetic_sintax.fa)",
    )
    parser.add_argument(
        "--entries", type=int, default=200,
        help="Number of reference sequences (default: 200)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    count = generate_synthetic_taxonomy(
        output_path, n_entries=args.entries, seed=args.seed,
    )

    marker = output_path.parent / ".abi_synthetic_taxonomy_generated"
    marker.write_text(
        f"entries: {count}\n"
        f"purpose: testing_only\n"
        f"note: For real analysis, use abi setup-resources --type amplicon_16s "
        f"to download the RDP training set.\n"
    )

    print(f"Generated {count} synthetic 16S sequences → {output_path}")
    print(f"Size: {output_path.stat().st_size / 1024:.1f} KB")
    print(
        "NOTE: This is a TESTING database. For real analysis, run: "
        "abi setup-resources --type amplicon_16s"
    )


if __name__ == "__main__":
    main()
