#!/usr/bin/env sh
set -eu

prefix=$1
target=$2

if [ -s "$target" ]; then
  exit 0
fi

for candidate in \
  "$prefix.hifiadapterfilt.fastq.gz" \
  "$prefix.filt.fastq.gz" \
  "$prefix.filtered.fastq.gz" \
  "$prefix.fastq.gz" \
  "$prefix.filt.fastq"; do
  if [ -s "$candidate" ]; then
    cp "$candidate" "$target"
    exit 0
  fi
done

for candidate in "$prefix"*filt*.fastq*; do
  if [ -s "$candidate" ]; then
    cp "$candidate" "$target"
    exit 0
  fi
done

echo "No HiFiAdapterFilt filtered FASTQ found for prefix: $prefix" >&2
exit 1
