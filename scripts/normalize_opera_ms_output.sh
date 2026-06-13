#!/usr/bin/env sh
set -eu

output_dir=$1
target=$2

if [ -s "$target" ]; then
  exit 0
fi

for candidate in \
  "$output_dir/contigs.fasta" \
  "$output_dir/contigs.fa" \
  "$output_dir/scaffolds.fasta" \
  "$output_dir/scaffolds.fa" \
  "$output_dir"/results/contigs.fasta \
  "$output_dir"/results/contigs.fa \
  "$output_dir"/results/scaffolds.fasta \
  "$output_dir"/results/scaffolds.fa; do
  if [ -s "$candidate" ]; then
    cp "$candidate" "$target"
    exit 0
  fi
done

for candidate in "$output_dir"/*contigs*.fa* "$output_dir"/*scaffolds*.fa*; do
  if [ -s "$candidate" ]; then
    cp "$candidate" "$target"
    exit 0
  fi
done

echo "No OPERA-MS contig FASTA found under: $output_dir" >&2
exit 1
