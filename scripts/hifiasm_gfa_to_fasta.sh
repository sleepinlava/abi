#!/usr/bin/env sh
set -eu

prefix=$1
target=$2

for candidate in \
  "$prefix.bp.p_ctg.gfa" \
  "$prefix.p_ctg.gfa" \
  "$prefix.bp.hap1.p_ctg.gfa" \
  "$prefix.bp.hap2.p_ctg.gfa" \
  "$prefix"*.gfa; do
  if [ ! -e "$candidate" ]; then
    continue
  fi
  awk '/^S/ { print ">" $2; print $3 }' "$candidate" > "$target"
  if [ -s "$target" ]; then
    exit 0
  fi
done

echo "No hifiasm GFA with segment records found for prefix: $prefix" >&2
exit 1
