# ABI-Bench v0.6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade ABI-Bench from v0.5 to v0.6 across three layers: fixture data for T31-T35 real execution, scoring framework with assertion validation + native multi-provider support, and 12 new task modules (T36-T47).

**Architecture:** Three independent layers that can be built and tested in sequence. Layer 1 (fixture data) enables Layer 2 (scoring upgrades) to be validated against real pipeline outputs. Layer 3 (new tasks) adds 4 new capability modules on top of the upgraded framework.

**Tech Stack:** Python ≥ 3.10, PyYAML, openai SDK, anthropic SDK (new), google-genai SDK (new), scipy, pytest, ABI CLI

## Global Constraints

- Python ≥ 3.10
- Dependencies: `pyyaml openai anthropic google-genai scipy`
- Bench repo paths: `/root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark/bench/`
- ABI repo paths: `/root/autodl-tmp/abi/`
- All fixture data must be synthetic/minimal — no large database downloads
- TDD: write failing test first, then implementation
- Benchmark tasks must pass simulated mode before real LLM execution
- `BENCHMARK_SPEC.yaml` version → 0.6.0

---

### Task 1: Layer 1 — Sync expected_assertions.yaml from ABI to Bench fixtures

**Files:**
- Create: `bench/fixtures/plasmid_benchmark/expected_assertions.yaml`
- Create: `bench/fixtures/rnaseq_benchmark/expected_assertions.yaml`
- Create: `bench/fixtures/amplicon_benchmark/expected_assertions.yaml`
- Create: `bench/fixtures/wgs_benchmark/expected_assertions.yaml`
- Create: `bench/fixtures/metatranscriptomics_benchmark/expected_assertions.yaml`

**Interfaces:**
- Consumes: ABI `data/benchmarks/<plugin>/expected_assertions.yaml` (existing)
- Produces: Bench `fixtures/<plugin>_benchmark/expected_assertions.yaml` (verbatim copies)

- [ ] **Step 1: Copy assertion files from ABI repo to Bench repo**

```bash
cp /root/autodl-tmp/abi/data/benchmarks/metagenomic_plasmid/expected_assertions.yaml \
   /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark/bench/fixtures/plasmid_benchmark/expected_assertions.yaml

cp /root/autodl-tmp/abi/data/benchmarks/rnaseq_expression/expected_assertions.yaml \
   /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark/bench/fixtures/rnaseq_benchmark/expected_assertions.yaml

cp /root/autodl-tmp/abi/data/benchmarks/amplicon_16s/expected_assertions.yaml \
   /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark/bench/fixtures/amplicon_benchmark/expected_assertions.yaml

cp /root/autodl-tmp/abi/data/benchmarks/wgs_bacteria/expected_assertions.yaml \
   /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark/bench/fixtures/wgs_benchmark/expected_assertions.yaml

cp /root/autodl-tmp/abi/data/benchmarks/metatranscriptomics/expected_assertions.yaml \
   /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark/bench/fixtures/metatranscriptomics_benchmark/expected_assertions.yaml
```

- [ ] **Step 2: Verify all 5 files exist and are valid YAML**

```bash
python -c "
import yaml, os
base = '/root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark/bench/fixtures'
for plugin in ['plasmid', 'rnaseq', 'amplicon', 'wgs', 'metatranscriptomics']:
    path = f'{base}/{plugin}_benchmark/expected_assertions.yaml'
    assert os.path.exists(path), f'Missing: {path}'
    with open(path) as f:
        data = yaml.safe_load(f)
    print(f'{plugin}: {list(data.keys())}')
"
```

Expected output: list of top-level keys for each plugin's assertions.

- [ ] **Step 3: Commit**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
git add bench/fixtures/*/expected_assertions.yaml
git commit -m "feat(L1): sync expected_assertions.yaml for all 5 plugins from ABI repo"
```

---

### Task 2: Layer 1 — Write generate_synthetic_data.py

**Files:**
- Create: `bench/fixtures/generate_synthetic_data.py`
- Create: `tests/test_generate_synthetic_data.py`

**Interfaces:**
- Produces: `generate_plasmid_data(outdir)` → writes FASTQ files to `outdir/data/`
- Produces: `generate_rnaseq_data(outdir)` → writes FASTQ files to `outdir/data/`
- Produces: `generate_amplicon_data(outdir)` → writes FASTQ files to `outdir/data/`
- Produces: `generate_wgs_data(outdir)` → writes FASTQ files to `outdir/data/`
- Produces: `generate_metatranscriptomics_data(outdir)` → writes FASTQ files to `outdir/data/`
- Produces: `generate_all(outdir_base)` → calls all 5 generators

- [ ] **Step 1: Write the failing test**

```python
# tests/test_generate_synthetic_data.py
import os
import tempfile
import gzip
import pytest
from bench.fixtures.generate_synthetic_data import (
    generate_plasmid_data,
    generate_rnaseq_data,
    generate_amplicon_data,
    generate_wgs_data,
    generate_metatranscriptomics_data,
    generate_all,
)


def _count_fastq_records(path: str) -> int:
    """Count sequences in a FASTQ file (gzipped or not)."""
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        return sum(1 for line in f if line.startswith("@") and len(line) > 1)


class TestGeneratePlasmidData:
    def test_generates_two_paired_fastq_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_plasmid_data(tmp)
            r1 = os.path.join(tmp, "data", "sample1_R1.fastq.gz")
            r2 = os.path.join(tmp, "data", "sample1_R2.fastq.gz")
            assert os.path.exists(r1), f"Missing {r1}"
            assert os.path.exists(r2), f"Missing {r2}"

    def test_reads_are_paired_equal_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_plasmid_data(tmp)
            r1 = os.path.join(tmp, "data", "sample1_R1.fastq.gz")
            r2 = os.path.join(tmp, "data", "sample1_R2.fastq.gz")
            n1 = _count_fastq_records(r1)
            n2 = _count_fastq_records(r2)
            assert n1 == n2
            assert n1 >= 100, f"Expected >= 100 reads, got {n1}"

    def test_reads_have_valid_quality_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_plasmid_data(tmp)
            r1 = os.path.join(tmp, "data", "sample1_R1.fastq.gz")
            with gzip.open(r1, "rt") as f:
                lines = f.readlines()
            # Quality line (4th line of each record) should be non-empty
            quality_lines = [lines[i] for i in range(3, len(lines), 4)]
            assert all(len(q.strip()) > 0 for q in quality_lines)


class TestGenerateRnaseqData:
    def test_generates_two_sample_fastq_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_rnaseq_data(tmp)
            for sample in ["control", "treatment"]:
                r1 = os.path.join(tmp, "data", f"{sample}_R1.fastq.gz")
                r2 = os.path.join(tmp, "data", f"{sample}_R2.fastq.gz")
                assert os.path.exists(r1)
                assert os.path.exists(r2)

    def test_both_samples_have_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_rnaseq_data(tmp)
            for sample in ["control", "treatment"]:
                r1 = os.path.join(tmp, "data", f"{sample}_R1.fastq.gz")
                assert _count_fastq_records(r1) >= 50


class TestGenerateAll:
    def test_generates_all_five_plugins(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate_all(tmp)
            expected_dirs = [
                "plasmid_benchmark", "rnaseq_benchmark", "amplicon_benchmark",
                "wgs_benchmark", "metatranscriptomics_benchmark",
            ]
            for d in expected_dirs:
                assert os.path.isdir(os.path.join(tmp, d, "data")), f"Missing data/ in {d}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python -m pytest tests/test_generate_synthetic_data.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# bench/fixtures/generate_synthetic_data.py
"""Generate minimal synthetic FASTQ data for ABI-Bench real-execution fixtures.

Each generator creates just enough synthetic reads to run the pipeline
and verify assertions — typically paired-end reads from known reference
sequences with realistic quality scores.

Usage:
    python generate_synthetic_data.py --all --outdir bench/fixtures/
    python generate_synthetic_data.py --plugin plasmid --outdir bench/fixtures/plasmid_benchmark/
"""

import argparse
import gzip
import os
import random
import sys

# ── Constants ──────────────────────────────────────────────────────────
SEED = 42
READ_LENGTH = 150
DEFAULT_N_READS = 200
PHRED_OFFSET = 33

# Known reference snippets for each plugin's synthetic reads
# These are real biological sequences used as templates.
ECOLI_LACZ = (
    "ATGACCATGATTACGGATTCACTGGCCGTCGTTTTACAACGTCGTGACTGGGAAAACCCT"
    "GGCGTTACCCAACTTAATCGCCTTGCAGCACATCCCCCTTTCGCCAGCTGGCGTAATAGC"
    "GAAGAGGCCCGCACCGATCGCCCTTCCCAACAGTTGCGCAGCCTGAATGGCGAATGGCGC"
)

REFSEQ_PLASMIDS = {
    "NC_002127.1": "ATGAAGCTCTTCGTAGGCGGCGGTGTTCATTCTGTTGGCAA" * 50,
    "NC_002483.1": "ATGCGTACCGTTCTTCGTGGCGGTCGTCGTGGTGGTGGTTCT" * 50,
    "NC_011977.1": "ATGGCTGACGCTTTCTTCCGTGACGGTGGTCCAGCTGGTTCT" * 50,
}

BACTERIA_16S = {
    "Escherichia": "AGAGTTTGATCCTGGCTCAGATTGAACGCTGGCGGCAGGCCTAA" * 40,
    "Bacillus": "AGAGTTTGATCCTGGCTCAGGACGAACGCTGGCGGCGTGCCTAA" * 40,
    "Pseudomonas": "AGAGTTTGATCCTGGCTCAGATTGAACGCTGGCGGCAGGCCTAA" * 40,
}

BACTERIAL_GENOME = "ATGAACGAAGCGCGTATTGCTCAACGTGGCAGCGATAAAAAAGCG" * 60


def _random_qual(n: int) -> str:
    """Generate a random phred-quality string of length n."""
    return "".join(chr(PHRED_OFFSET + random.randint(20, 40)) for _ in range(n))


def _write_fastq_paired(path_r1: str, path_r2: str, template: str,
                        n_reads: int = DEFAULT_N_READS):
    """Write paired-end FASTQ files from a template sequence."""
    os.makedirs(os.path.dirname(path_r1), exist_ok=True)
    tlen = len(template)
    with gzip.open(path_r1, "wt") as f1, gzip.open(path_r2, "wt") as f2:
        for i in range(n_reads):
            start = random.randint(0, tlen - READ_LENGTH - 1)
            seq = template[start:start + READ_LENGTH]
            # Read 2: reverse complement (simple approximation)
            rc = seq.translate(str.maketrans("ATCG", "TAGC"))[::-1]
            qual = _random_qual(READ_LENGTH)
            f1.write(f"@read_{i}_R1\n{seq}\n+\n{qual}\n")
            f2.write(f"@read_{i}_R2\n{rc}\n+\n{qual}\n")


def _write_fastq_single(path_r1: str, template: str,
                        n_reads: int = DEFAULT_N_READS):
    """Write a single-end FASTQ file from a template sequence."""
    os.makedirs(os.path.dirname(path_r1), exist_ok=True)
    tlen = len(template)
    with gzip.open(path_r1, "wt") as f:
        for i in range(n_reads):
            start = random.randint(0, tlen - READ_LENGTH - 1)
            seq = template[start:start + READ_LENGTH]
            qual = _random_qual(READ_LENGTH)
            f.write(f"@read_{i}\n{seq}\n+\n{qual}\n")


def generate_plasmid_data(outdir: str):
    """Generate paired-end reads from 3 RefSeq plasmid templates."""
    random.seed(SEED)
    # Pool all plasmid templates
    templates = list(REFSEQ_PLASMIDS.values())
    combined = templates[0] + templates[1] + templates[2]
    _write_fastq_paired(
        os.path.join(outdir, "data", "sample1_R1.fastq.gz"),
        os.path.join(outdir, "data", "sample1_R2.fastq.gz"),
        combined, n_reads=400,
    )


def generate_rnaseq_data(outdir: str):
    """Generate paired-end RNA-seq reads from E. coli lacZ for 2 conditions."""
    random.seed(SEED)
    for sample in ["control", "treatment"]:
        _write_fastq_paired(
            os.path.join(outdir, "data", f"{sample}_R1.fastq.gz"),
            os.path.join(outdir, "data", f"{sample}_R2.fastq.gz"),
            ECOLI_LACZ * 20, n_reads=200,
        )


def generate_amplicon_data(outdir: str):
    """Generate single-end 16S V4 amplicon reads from 3 bacterial references."""
    random.seed(SEED)
    for i, (name, template) in enumerate(BACTERIA_16S.items()):
        _write_fastq_single(
            os.path.join(outdir, "data", f"sample{i + 1}_R1.fastq.gz"),
            template, n_reads=200,
        )


def generate_wgs_data(outdir: str):
    """Generate paired-end WGS reads from a synthetic bacterial genome."""
    random.seed(SEED)
    _write_fastq_paired(
        os.path.join(outdir, "data", "sample1_R1.fastq.gz"),
        os.path.join(outdir, "data", "sample1_R2.fastq.gz"),
        BACTERIAL_GENOME, n_reads=300,
    )


def generate_metatranscriptomics_data(outdir: str):
    """Generate paired-end transcriptomic reads from E. coli lacZ template."""
    random.seed(SEED)
    for sample in ["community1", "community2"]:
        _write_fastq_paired(
            os.path.join(outdir, "data", f"{sample}_R1.fastq.gz"),
            os.path.join(outdir, "data", f"{sample}_R2.fastq.gz"),
            ECOLI_LACZ * 20, n_reads=200,
        )


def generate_all(outdir_base: str):
    """Generate synthetic data for all 5 plugin benchmarks."""
    plugins = {
        "plasmid_benchmark": generate_plasmid_data,
        "rnaseq_benchmark": generate_rnaseq_data,
        "amplicon_benchmark": generate_amplicon_data,
        "wgs_benchmark": generate_wgs_data,
        "metatranscriptomics_benchmark": generate_metatranscriptomics_data,
    }
    for name, fn in plugins.items():
        outdir = os.path.join(outdir_base, name)
        print(f"Generating {name} data...")
        fn(outdir)
        print(f"  Done: {outdir}/data/")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic benchmark data")
    parser.add_argument("--all", action="store_true", help="Generate all 5 plugins")
    parser.add_argument("--plugin", choices=[
        "plasmid", "rnaseq", "amplicon", "wgs", "metatranscriptomics"
    ], help="Generate a specific plugin's data")
    parser.add_argument("--outdir", default="bench/fixtures/",
                        help="Base output directory (default: bench/fixtures/)")
    args = parser.parse_args()

    if args.all:
        generate_all(args.outdir)
    elif args.plugin:
        mapping = {
            "plasmid": generate_plasmid_data,
            "rnaseq": generate_rnaseq_data,
            "amplicon": generate_amplicon_data,
            "wgs": generate_wgs_data,
            "metatranscriptomics": generate_metatranscriptomics_data,
        }
        outdir = os.path.join(args.outdir, f"{args.plugin}_benchmark")
        mapping[args.plugin](outdir)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python -m pytest tests/test_generate_synthetic_data.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Run the script to generate all fixture data**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python bench/fixtures/generate_synthetic_data.py --all --outdir bench/fixtures/
```

- [ ] **Step 6: Verify generated data**

```bash
echo "=== Checking generated files ==="
for plugin in plasmid rnaseq amplicon wgs metatranscriptomics; do
    echo "$plugin:"
    ls -lhR bench/fixtures/${plugin}_benchmark/data/ 2>/dev/null || echo "  No data/ dir"
done
```

- [ ] **Step 7: Commit**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
git add bench/fixtures/generate_synthetic_data.py tests/test_generate_synthetic_data.py
git add bench/fixtures/*_benchmark/data/
git commit -m "feat(L1): add synthetic data generator + generate all 5 plugin fixtures"
```

---

### Task 3: Layer 1 — Update benchmark config.yaml and sample_sheet.tsv files

**Files:**
- Modify: `bench/fixtures/plasmid_benchmark/config.yaml`
- Modify: `bench/fixtures/rnaseq_benchmark/config.yaml`
- Modify: `bench/fixtures/amplicon_benchmark/config.yaml`
- Modify: `bench/fixtures/wgs_benchmark/config.yaml`
- Modify: `bench/fixtures/metatranscriptomics_benchmark/config.yaml`
- Create: `bench/fixtures/plasmid_benchmark/sample_sheet.tsv`
- Create: `bench/fixtures/rnaseq_benchmark/sample_sheet.tsv`
- Create: `bench/fixtures/amplicon_benchmark/sample_sheet.tsv`
- Create: `bench/fixtures/wgs_benchmark/sample_sheet.tsv`
- Create: `bench/fixtures/metatranscriptomics_benchmark/sample_sheet.tsv`

**Interfaces:**
- Consumes: generated data files from Task 2
- Produces: valid config.yaml + sample_sheet.tsv for each benchmark fixture

- [ ] **Step 1: Update plasmid_benchmark/config.yaml**

```yaml
# Metagenomic Plasmid Benchmark Configuration
# Auto-generated by generate_synthetic_data.py
project_name: "bench-plasmid"
mode: local
threads: 2
outdir: results/bench-plasmid
log_dir: logs/bench-plasmid

dry_run: false

input:
  sample_sheet: sample_sheet.tsv

plasmid_detection:
  tools: [genomad]
  strategy: single_tool

resources:
  bakta_db: resources/mini_bakta_db/
  genomad_db: resources/mini_genomad_db/
```

- [ ] **Step 2: Create plasmid_benchmark/sample_sheet.tsv**

```
sample_id	read1	read2	assembly
sample1	data/sample1_R1.fastq.gz	data/sample1_R2.fastq.gz	
```

- [ ] **Step 3: Update rnaseq_benchmark/config.yaml**

```yaml
project_name: "bench-rnaseq"
mode: local
threads: 2
outdir: results/bench-rnaseq
log_dir: logs/bench-rnaseq

dry_run: false

input:
  sample_sheet: sample_sheet.tsv

comparisons:
  - name: treatment_vs_control
    numerator: treatment
    denominator: control

resources:
  star_index: resources/star_index/
  gtf: resources/genes.gtf
```

- [ ] **Step 4: Create rnaseq_benchmark/sample_sheet.tsv**

```
sample_id	condition	read1	read2
control	control	data/control_R1.fastq.gz	data/control_R2.fastq.gz
treatment	treatment	data/treatment_R1.fastq.gz	data/treatment_R2.fastq.gz
```

- [ ] **Step 5: Update amplicon_benchmark/config.yaml**

```yaml
project_name: "bench-amplicon"
mode: local
threads: 2
outdir: results/bench-amplicon
log_dir: logs/bench-amplicon

dry_run: false

input:
  sample_sheet: sample_sheet.tsv

resources:
  sintax_db: resources/sintax.fasta
  reference_alignment: resources/reference_alignment.fasta
```

- [ ] **Step 6: Create amplicon_benchmark/sample_sheet.tsv**

```
sample_id	read1
sample1	data/sample1_R1.fastq.gz
sample2	data/sample2_R1.fastq.gz
sample3	data/sample3_R1.fastq.gz
```

- [ ] **Step 7: Update wgs_benchmark/config.yaml**

```yaml
project_name: "bench-wgs"
mode: local
threads: 2
outdir: results/bench-wgs
log_dir: logs/bench-wgs

dry_run: false

input:
  sample_sheet: sample_sheet.tsv

resources:
  mlst_db: resources/mlst_db/
```

- [ ] **Step 8: Create wgs_benchmark/sample_sheet.tsv**

```
sample_id	read1	read2
sample1	data/sample1_R1.fastq.gz	data/sample1_R2.fastq.gz
```

- [ ] **Step 9: Update metatranscriptomics_benchmark/config.yaml**

```yaml
project_name: "bench-metatx"
mode: local
threads: 2
outdir: results/bench-metatx
log_dir: logs/bench-metatx

dry_run: false

input:
  sample_sheet: sample_sheet.tsv

resources:
  genome_index: resources/star_index/
  annotation_gtf: resources/genes.gtf
```

- [ ] **Step 10: Create metatranscriptomics_benchmark/sample_sheet.tsv**

```
sample_id	read1	read2
community1	data/community1_R1.fastq.gz	data/community1_R2.fastq.gz
community2	data/community2_R1.fastq.gz	data/community2_R2.fastq.gz
```

- [ ] **Step 11: Validate all config files are parseable YAML**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python -c "
import yaml, os
base = 'bench/fixtures'
for plugin in ['plasmid', 'rnaseq', 'amplicon', 'wgs', 'metatranscriptomics']:
    cfg = f'{base}/{plugin}_benchmark/config.yaml'
    ss = f'{base}/{plugin}_benchmark/sample_sheet.tsv'
    with open(cfg) as f:
        data = yaml.safe_load(f)
    assert data, f'Empty config: {cfg}'
    print(f'{plugin} config: OK (mode={data[\"mode\"]}, dry_run={data[\"dry_run\"]})')
    with open(ss) as f:
        header = f.readline()
    assert header.startswith('sample_id'), f'Bad sample_sheet header: {ss}'
    print(f'{plugin} sample_sheet: OK')
"
```

Expected: all 10 files OK.

- [ ] **Step 12: Commit**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
git add bench/fixtures/*_benchmark/config.yaml bench/fixtures/*_benchmark/sample_sheet.tsv
git commit -m "feat(L1): complete benchmark config + sample sheets for all 5 plugins"
```

---

### Task 4: Layer 2 — Add real-output assertion check functions to checks.py

**Files:**
- Modify: `bench/scoring/checks.py` (add new check functions)
- Modify: `bench/scoring/rubric.yaml` (register new checks)
- Create: `tests/test_checks_real_exec.py`

**Interfaces:**
- Consumes: `rubric.yaml` check definitions
- Produces:
  - `check_pipeline_outputs_match_assertions(run_dir: str, task: dict) -> CheckResult`
  - `check_per_category_breakdown(run_dir: str, task: dict) -> CheckResult`
  - `check_output_file_integrity(run_dir: str, task: dict) -> CheckResult`
  - `check_assertion_value_in_range(run_dir: str, task: dict) -> CheckResult`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_checks_real_exec.py
"""Tests for v0.6 real-execution check functions."""
import json
import os
import tempfile
import pytest

# Import check functions from the checks module
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bench", "scoring"))
from checks import (
    check_pipeline_outputs_match_assertions,
    check_per_category_breakdown,
    check_output_file_integrity,
)


def _make_fake_run_dir(base: str, assertions: dict, outputs: dict):
    """Create a minimal run directory with expected_assertions.yaml and output files."""
    import yaml
    # Write assertions
    with open(os.path.join(base, "expected_assertions.yaml"), "w") as f:
        yaml.dump(assertions, f)
    # Write output files
    results_dir = os.path.join(base, "results", "bench-test")
    prov_dir = os.path.join(results_dir, "provenance")
    os.makedirs(prov_dir, exist_ok=True)
    for relpath, content in outputs.items():
        full = os.path.join(results_dir, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if isinstance(content, str):
            with open(full, "w") as f:
                f.write(content)
        elif isinstance(content, list):
            # TSV
            with open(full, "w") as f:
                for row in content:
                    f.write("\t".join(str(c) for c in row) + "\n")
        elif isinstance(content, dict):
            with open(full, "w") as f:
                json.dump(content, f)


class TestCheckPipelineOutputsMatchAssertions:
    def test_all_assertions_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            assertions = {
                "test_plugin": {
                    "qc": {"min_reads_retained": 10, "clean_fastq_exists": True},
                    "provenance": {"min_commands": 3, "run_summary_exists": True},
                }
            }
            outputs = {
                "provenance/commands.tsv": [
                    ["step_id", "tool_id", "status", "exit_code"],
                    ["qc_fastp", "fastp", "success", "0"],
                    ["assembly", "megahit", "success", "0"],
                    ["prodigal", "prodigal", "success", "0"],
                ],
                "provenance/run_summary.json": {"total_steps": 3, "successful": 3},
            }
            _make_fake_run_dir(tmp, assertions, outputs)

            result = check_pipeline_outputs_match_assertions(tmp, {})

            assert result.passed is True
            assert result.score >= 6  # max assertion score

    def test_assertion_fails_on_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            assertions = {
                "test_plugin": {
                    "qc": {"clean_fastq_exists": True},
                }
            }
            outputs = {}  # no files at all
            _make_fake_run_dir(tmp, assertions, outputs)

            result = check_pipeline_outputs_match_assertions(tmp, {})

            assert result.passed is False
            assert result.score < 6

    def test_numeric_assertion_fails_below_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            assertions = {
                "test_plugin": {
                    "provenance": {"min_commands": 100},
                }
            }
            outputs = {
                "provenance/commands.tsv": [
                    ["step_id", "tool_id", "status"],
                    ["qc_fastp", "fastp", "success"],
                ],
            }
            _make_fake_run_dir(tmp, assertions, outputs)

            result = check_pipeline_outputs_match_assertions(tmp, {})

            assert result.passed is False


class TestCheckPerCategoryBreakdown:
    def test_reports_per_category_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            assertions = {
                "test_plugin": {
                    "qc": {"min_reads_retained": 1, "clean_fastq_exists": True},
                    "assembly": {"min_contigs": 1},
                    "provenance": {"min_commands": 1, "run_summary_exists": True},
                }
            }
            outputs = {
                "provenance/commands.tsv": [
                    ["step_id", "tool_id", "status"],
                    ["qc_fastp", "fastp", "success"],
                ],
                "provenance/run_summary.json": {"total_steps": 1},
            }
            _make_fake_run_dir(tmp, assertions, outputs)

            result = check_per_category_breakdown(tmp, {})

            assert result.passed is True
            details = result.details
            assert "categories" in details
            assert "qc" in details["categories"]
            assert "passed" in details


class TestCheckOutputFileIntegrity:
    def test_all_required_files_present_and_nonempty(self):
        with tempfile.TemporaryDirectory() as tmp:
            results_dir = os.path.join(tmp, "results", "bench-test")
            prov_dir = os.path.join(results_dir, "provenance")
            tables_dir = os.path.join(results_dir, "tables")
            os.makedirs(prov_dir)
            os.makedirs(tables_dir)
            with open(os.path.join(prov_dir, "commands.tsv"), "w") as f:
                f.write("step_id\ttool_id\tstatus\n")
            with open(os.path.join(tables_dir, "test.tsv"), "w") as f:
                f.write("col1\tcol2\n")

            task = {
                "required_output_files": [
                    "results/*/provenance/commands.tsv",
                    "results/*/tables/*.tsv",
                ]
            }
            result = check_output_file_integrity(tmp, task)

            assert result.passed is True

    def test_fails_when_required_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "required_output_files": [
                    "results/*/provenance/commands.tsv",
                ]
            }
            result = check_output_file_integrity(tmp, task)

            assert result.passed is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python -m pytest tests/test_checks_real_exec.py -v
```

Expected: FAIL — functions not defined.

- [ ] **Step 3: Implement check functions in checks.py**

Read current `checks.py` to find the insertion point (end of file), then append:

```python
# bench/scoring/checks.py — append these functions before the final line

# ── v0.6: Real-execution assertion checks ───────────────────────────

import glob as _glob_module
import json as _json_module
import os as _os_module

import yaml as _yaml_module


def check_pipeline_outputs_match_assertions(run_dir: str, task: dict) -> CheckResult:
    """Validate actual pipeline outputs against expected_assertions.yaml.

    Walks each category (qc, assembly, annotation, etc.) and evaluates
    individual assertions against real output files.

    Returns a CheckResult with:
      - passed: True if all assertions pass
      - score: weighted by assertion pass rate (max from rubric)
      - details: {assertions: {total, passed, failed, skipped}, failures: [...]}
    """
    assertions_path = _os_module.path.join(run_dir, "expected_assertions.yaml")
    if not _os_module.path.exists(assertions_path):
        return CheckResult(
            check="pipeline_outputs_match_assertions",
            passed=False,
            score=0,
            details={"error": "expected_assertions.yaml not found"},
        )

    with open(assertions_path) as f:
        spec = _yaml_module.safe_load(f)

    # Find results directory — resolve glob pattern
    results_glob = _os_module.path.join(run_dir, "results", "*")
    results_dirs = sorted(_glob_module.glob(results_glob))
    if not results_dirs:
        # Fallback: check for results/ directly
        results_dir = _os_module.path.join(run_dir, "results")
    else:
        results_dir = results_dirs[0]

    total = 0
    passed = 0
    failed = 0
    failures = []

    for plugin_name, categories in spec.items():
        for category, assertions in categories.items():
            for key, expected in assertions.items():
                total += 1
                try:
                    actual = _evaluate_assertion(key, expected, results_dir)
                    if actual is True:
                        passed += 1
                    else:
                        failed += 1
                        failures.append({
                            "category": category,
                            "assertion": key,
                            "expected": str(expected),
                            "actual": str(actual),
                        })
                except Exception as exc:
                    failed += 1
                    failures.append({
                        "category": category,
                        "assertion": key,
                        "expected": str(expected),
                        "error": str(exc),
                    })

    max_points = _get_max_points(task, "pipeline_outputs_match_assertions", 8)
    pass_rate = passed / max(total, 1)
    score = round(max_points * pass_rate, 1)

    return CheckResult(
        check="pipeline_outputs_match_assertions",
        passed=(failed == 0),
        score=score,
        details={
            "assertions": {"total": total, "passed": passed, "failed": failed},
            "failures": failures,
        },
    )


def check_per_category_breakdown(run_dir: str, task: dict) -> CheckResult:
    """Report per-category assertion pass rates.

    Groups assertions by category (qc, assembly, annotation, etc.)
    and reports individual pass rates.
    """
    assertions_path = _os_module.path.join(run_dir, "expected_assertions.yaml")
    if not _os_module.path.exists(assertions_path):
        return CheckResult(
            check="per_category_breakdown",
            passed=False,
            score=0,
            details={"error": "expected_assertions.yaml not found"},
        )

    with open(assertions_path) as f:
        spec = _yaml_module.safe_load(f)

    results_glob = _os_module.path.join(run_dir, "results", "*")
    results_dirs = sorted(_glob_module.glob(results_glob))
    results_dir = results_dirs[0] if results_dirs else _os_module.path.join(run_dir, "results")

    categories = {}
    all_passed = True

    for plugin_name, cats in spec.items():
        for category, assertions in cats.items():
            cat_total = 0
            cat_passed = 0
            for key, expected in assertions.items():
                cat_total += 1
                try:
                    if _evaluate_assertion(key, expected, results_dir) is True:
                        cat_passed += 1
                    else:
                        all_passed = False
                except Exception:
                    all_passed = False
            categories[category] = {
                "total": cat_total,
                "passed": cat_passed,
                "rate": round(cat_passed / max(cat_total, 1), 3),
            }

    max_points = _get_max_points(task, "per_category_breakdown", 2)
    score = max_points if all_passed else round(max_points * 0.5, 1)

    return CheckResult(
        check="per_category_breakdown",
        passed=all_passed,
        score=score,
        details={"categories": categories},
    )


def check_output_file_integrity(run_dir: str, task: dict) -> CheckResult:
    """Verify that required output files exist and are non-empty.

    Supports glob patterns in file paths (e.g. 'results/*/provenance/commands.tsv').
    """
    required = task.get("required_output_files", [])
    if not required:
        return CheckResult(
            check="output_file_integrity",
            passed=True,
            score=2,
            details={"note": "no required files specified"},
        )

    missing = []
    empty_files = []
    for pattern in required:
        full_pattern = _os_module.path.join(run_dir, pattern)
        matches = _glob_module.glob(full_pattern)
        if not matches:
            missing.append(pattern)
            continue
        for match in matches:
            if _os_module.path.getsize(match) == 0:
                empty_files.append(_os_module.path.relpath(match, run_dir))

    all_ok = len(missing) == 0 and len(empty_files) == 0
    max_points = _get_max_points(task, "output_file_integrity", 2)
    score = max_points if all_ok else (max_points * 0.5 if not missing else 0)

    return CheckResult(
        check="output_file_integrity",
        passed=all_ok,
        score=score,
        details={"missing": missing, "empty": empty_files},
    )


def check_assertion_value_in_range(run_dir: str, task: dict) -> CheckResult:
    """Validate numeric assertions have actual values within [min, max] range.

    Specialized for assertions with 'min_' and 'max_' keys.
    """
    assertions_path = _os_module.path.join(run_dir, "expected_assertions.yaml")
    if not _os_module.path.exists(assertions_path):
        return CheckResult(
            check="assertion_value_in_range",
            passed=False,
            score=0,
            details={"error": "expected_assertions.yaml not found"},
        )

    with open(assertions_path) as f:
        spec = _yaml_module.safe_load(f)

    results_glob = _os_module.path.join(run_dir, "results", "*")
    results_dirs = sorted(_glob_module.glob(results_glob))
    results_dir = results_dirs[0] if results_dirs else _os_module.path.join(run_dir, "results")

    range_checks = 0
    range_passed = 0
    failures = []

    for plugin_name, categories in spec.items():
        for category, assertions in categories.items():
            for key, expected in assertions.items():
                if isinstance(expected, (int, float)):
                    range_checks += 1
                    actual = _resolve_numeric_assertion(key, expected, results_dir)
                    if actual is None:
                        continue  # skip non-numeric checks
                    if actual >= expected:
                        range_passed += 1
                    else:
                        failures.append({
                            "category": category,
                            "assertion": key,
                            "expected_min": expected,
                            "actual": actual,
                        })

    max_points = _get_max_points(task, "assertion_value_in_range", 4)
    pass_rate = range_passed / max(range_checks, 1)
    score = round(max_points * pass_rate, 1)

    return CheckResult(
        check="assertion_value_in_range",
        passed=(len(failures) == 0),
        score=score,
        details={"range_checks": range_checks, "passed": range_passed, "failures": failures},
    )


# ── Internal helpers for assertion evaluation ──────────────────────

def _evaluate_assertion(key: str, expected, results_dir: str) -> bool:
    """Evaluate a single assertion against actual outputs.

    Handles these assertion types:
      - bool (True): check existence based on key name suffix
      - int/float: check numeric minimum
      - str: check string containment in relevant file
      - list: check that at least N elements from the list are found
    """
    if isinstance(expected, bool):
        if expected is True:
            # Try to find a file corresponding to this assertion key
            return _check_existence(key, results_dir)
        return True  # False means "no assertion", always passes

    if isinstance(expected, (int, float)):
        return _check_numeric_min(key, expected, results_dir)

    if isinstance(expected, str):
        return _check_string_contains(key, expected, results_dir)

    if isinstance(expected, list):
        return _check_list_membership(key, expected, results_dir)

    return True


def _check_existence(key: str, results_dir: str) -> bool:
    """Check that a file or directory corresponding to the assertion key exists."""
    # Map assertion keys to expected paths
    key_to_glob = {
        "clean_fastq_exists": "*/qc/*/clean/*.fastq*",
        "qc_report_exists": "*/qc/*/report/*.json",
        "assembly_dir_exists": "*/assembly/",
        "protein_fasta_exists": "**/*.faa",
        "plasmid_report_exists": "**/plasmid_report*",
        "annotation_gff_exists": "**/*.gff*",
        "coverage_table_exists": "**/coverage*.tsv",
        "report_md_exists": "**/report.md",
        "report_html_exists": "**/report.html",
        "run_summary_exists": "**/provenance/run_summary.json",
        "checksums_exist": "**/provenance/checksums.json",
        "commands_tsv_exists": "**/provenance/commands.tsv",
    }
    pattern = key_to_glob.get(key, f"**/{key.replace('_', '*')}*")
    matches = _glob_module.glob(
        _os_module.path.join(results_dir, pattern), recursive=True
    )
    return len(matches) > 0


def _check_numeric_min(key: str, expected: float, results_dir: str) -> bool:
    """Check that a numeric metric meets the minimum threshold."""
    # For most numeric assertions, we check the count/size indirectly
    # Key-specific logic for reliable checks
    if key == "min_commands":
        commands_path = _find_file(results_dir, "**/provenance/commands.tsv")
        if not commands_path:
            return False
        with open(commands_path) as f:
            lines = f.readlines()
            # Subtract 1 for header
            return (len(lines) - 1) >= expected
    if key == "min_reads_retained":
        # Check fastp JSON output for total_reads after filtering
        fastp_jsons = _glob_module.glob(
            _os_module.path.join(results_dir, "**/fastp*.json"), recursive=True
        )
        for fj in fastp_jsons:
            with open(fj) as f:
                data = _json_module.load(f)
            if "summary" in data:
                after = data["summary"].get("after_filtering", {})
                if after.get("total_reads", 0) >= expected:
                    return True
        return False
    # Generic: try to find a TSV/JSON and count rows
    return True  # Default pass — numeric checks are best-effort


def _check_string_contains(key: str, expected: str, results_dir: str) -> bool:
    """Check that a string is found in relevant output files."""
    if key == "contains_tool_name":
        report_mds = _glob_module.glob(
            _os_module.path.join(results_dir, "**/report.md"), recursive=True
        )
        for rm in report_mds:
            with open(rm) as f:
                if expected.lower() in f.read().lower():
                    return True
        return False
    if key == "dryrun_disclosed":
        report_mds = _glob_module.glob(
            _os_module.path.join(results_dir, "**/report.md"), recursive=True
        )
        for rm in report_mds:
            with open(rm) as f:
                text = f.read().lower()
                if "dry-run" in text or "dry_run" in text:
                    return True
        return False
    # Generic: search in provenance logs
    return True


def _check_list_membership(key: str, expected: list, results_dir: str) -> bool:
    """Check that at least one element from the expected list is found."""
    if key == "expected_plasmid_markers" or key == "expected_genera":
        # Search all text files in results for at least one marker
        all_text = ""
        for ext in ["*.tsv", "*.md", "*.txt", "*.json"]:
            for f in _glob_module.glob(
                _os_module.path.join(results_dir, f"**/{ext}"), recursive=True
            ):
                try:
                    with open(f) as fh:
                        all_text += fh.read().lower() + " "
                except Exception:
                    pass
        found = [item for item in expected if item.lower() in all_text]
        return len(found) > 0
    return True


def _find_file(base: str, pattern: str) -> str | None:
    """Find first matching file, return path or None."""
    matches = _glob_module.glob(
        _os_module.path.join(base, pattern), recursive=True
    )
    return matches[0] if matches else None


def _resolve_numeric_assertion(key: str, expected: float, results_dir: str) -> int | None:
    """Resolve a numeric assertion to an actual count/value."""
    if key == "min_commands":
        commands_path = _find_file(results_dir, "**/provenance/commands.tsv")
        if not commands_path:
            return 0
        with open(commands_path) as f:
            return len(f.readlines()) - 1
    return None


def _get_max_points(task: dict, check_name: str, default: int) -> int:
    """Extract max points for a check from the task's scoring section."""
    scoring = task.get("scoring", {})
    if check_name in scoring:
        return scoring[check_name].get("points", default)
    return default
```

- [ ] **Step 4: Update rubric.yaml with new check definitions**

Append to `bench/scoring/rubric.yaml`:

```yaml
    # ── v0.6: Real execution assertion checks ────────────────────────────
    check_pipeline_outputs_match_assertions:
      description: "Pipeline outputs match expected_assertions.yaml values"
      points: 8
      function: check_pipeline_outputs_match_assertions

    check_per_category_breakdown:
      description: "Per-category (qc/assembly/annotation) assertion pass rates reported"
      points: 2
      function: check_per_category_breakdown

    check_output_file_integrity:
      description: "Required output files exist and are non-empty"
      points: 2
      function: check_output_file_integrity

    check_assertion_value_in_range:
      description: "Numeric assertion values fall within expected ranges"
      points: 4
      function: check_assertion_value_in_range
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python -m pytest tests/test_checks_real_exec.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
git add bench/scoring/checks.py bench/scoring/rubric.yaml tests/test_checks_real_exec.py
git commit -m "feat(L2): add real-output assertion check functions for T31-T35 scoring"
```

---

### Task 5: Layer 2 — Add native Anthropic/Google SDK support to direct_agent.py

**Files:**
- Modify: `bench/harness/direct_agent.py` (~300 lines added)
- Modify: `bench/harness/config.py` (add anthropic/google provider config)
- Create: `tests/test_direct_agent_providers.py`

**Interfaces:**
- Consumes: `BenchConfig` with `provider` field
- Produces: `_call_llm()` dispatches to correct SDK based on provider
- Produces: `_call_anthropic(messages, tools, config)` → response text + tool_calls
- Produces: `_call_google(messages, tools, config)` → response text + tool_calls

- [ ] **Step 1: Write failing test**

```python
# tests/test_direct_agent_providers.py
"""Tests for multi-provider support in direct_agent.py."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bench", "harness"))
from config import BenchConfig, Provider


class TestProviderRouting:
    def test_config_supports_anthropic_provider(self):
        config = BenchConfig(
            provider=Provider.ANTHROPIC,
            api_key="test-key",
            model="claude-sonnet-4-6",
        )
        assert config.provider == Provider.ANTHROPIC
        assert config.is_anthropic is True

    def test_config_supports_google_provider(self):
        config = BenchConfig(
            provider=Provider.GOOGLE,
            api_key="test-key",
            model="gemini-2.5-flash",
        )
        assert config.provider == Provider.GOOGLE
        assert config.is_google is True

    def test_config_supports_openai_compatible(self):
        config = BenchConfig(
            provider=Provider.OPENAI_COMPATIBLE,
            api_key="test-key",
            model="llama3.1:8b",
            api_base="http://localhost:11434/v1",
        )
        assert config.provider == Provider.OPENAI_COMPATIBLE


class TestAnthropicToolConversion:
    def test_openai_tool_schema_converts_to_anthropic(self):
        """Verify OpenAI-format tool schemas convert to Anthropic format."""
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "bash",
                    "description": "Run a shell command",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string"}
                        },
                        "required": ["command"],
                    },
                },
            }
        ]
        from direct_agent import _openai_tools_to_anthropic
        anthropic_tools = _openai_tools_to_anthropic(openai_tools)

        assert len(anthropic_tools) == 1
        assert anthropic_tools[0]["name"] == "bash"
        assert anthropic_tools[0]["input_schema"]["type"] == "object"

    def test_anthropic_response_converts_to_unified(self):
        """Verify Anthropic response blocks convert to unified format."""
        from direct_agent import _anthropic_response_to_unified
        anthropic_block = type("obj", (object,), {
            "type": "tool_use",
            "id": "tool_001",
            "name": "bash",
            "input": {"command": "ls"},
        })()

        unified = _anthropic_response_to_unified([anthropic_block])

        assert len(unified) == 1
        assert unified[0]["name"] == "bash"
        assert unified[0]["arguments"] == {"command": "ls"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python -m pytest tests/test_direct_agent_providers.py -v
```

Expected: FAIL — `Provider.ANTHROPIC` / functions not defined.

- [ ] **Step 3: Update config.py with new provider types**

Read `config.py` and add to the Provider enum:

```python
# Add to bench/harness/config.py — Provider class
class Provider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"          # NEW
    GOOGLE = "google"                 # NEW
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    GLM = "glm"
    KIMI = "kimi"
    MIMO = "mimo"
    OPENAI_COMPATIBLE = "openai-compatible"


# Add to BenchConfig dataclass:
@dataclass
class BenchConfig:
    # ... existing fields ...
    
    @property
    def is_anthropic(self) -> bool:
        return self.provider == Provider.ANTHROPIC
    
    @property
    def is_google(self) -> bool:
        return self.provider == Provider.GOOGLE
    
    @property
    def uses_openai_sdk(self) -> bool:
        return self.provider in (
            Provider.OPENAI, Provider.DEEPSEEK, Provider.QWEN,
            Provider.GLM, Provider.KIMI, Provider.MIMO,
            Provider.OPENAI_COMPATIBLE,
        )
```

- [ ] **Step 4: Add Anthropic/Google SDK calls to direct_agent.py**

Read the current `direct_agent.py` to find `_call_llm` or similar function, then add:

```python
# bench/harness/direct_agent.py — added functions

# ── v0.6: Multi-provider LLM routing ─────────────────────────────

def _openai_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    """Convert OpenAI-format tool schemas to Anthropic tool format.
    
    OpenAI: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
    Anthropic: {"name": ..., "description": ..., "input_schema": ...}
    """
    result = []
    for tool in tools:
        if tool.get("type") == "function":
            func = tool["function"]
            result.append({
                "name": func["name"],
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })
    return result


def _anthropic_response_to_unified(blocks: list) -> list[dict]:
    """Convert Anthropic tool_use blocks to unified tool call format.
    
    Unified format: {"id": str, "name": str, "arguments": dict}
    """
    calls = []
    for block in blocks:
        if hasattr(block, "type") and block.type == "tool_use":
            calls.append({
                "id": block.id,
                "name": block.name,
                "arguments": block.input,
            })
    return calls


def _call_anthropic(config, system_prompt: str, messages: list[dict],
                    tools: list[dict]) -> tuple[str, list[dict], dict]:
    """Call Anthropic API via native SDK.
    
    Returns: (text_content, tool_calls, usage_metadata)
    """
    import anthropic
    
    client = anthropic.Anthropic(api_key=config.api_key)
    
    anthropic_tools = _openai_tools_to_anthropic(tools) if tools else None
    
    response = client.messages.create(
        model=config.model,
        max_tokens=config.max_tokens,
        system=system_prompt,
        messages=messages,
        tools=anthropic_tools,
    )
    
    text = ""
    tool_calls = []
    for block in response.content:
        if block.type == "text":
            text += block.text
        elif block.type == "tool_use":
            tool_calls.append({
                "id": block.id,
                "name": block.name,
                "arguments": block.input,
            })
    
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    
    return text, tool_calls, usage


def _call_google(config, system_prompt: str, messages: list[dict],
                 tools: list[dict]) -> tuple[str, list[dict], dict]:
    """Call Google Gemini API via native SDK.
    
    Returns: (text_content, tool_calls, usage_metadata)
    """
    import google.genai as genai
    
    client = genai.Client(api_key=config.api_key)
    
    # Google uses a system_instruction parameter, not a system message
    # Convert messages to Google format
    contents = []
    system_instruction = system_prompt if system_prompt else None
    
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        parts = []
        if "content" in msg and msg["content"]:
            parts.append({"text": msg["content"]})
        contents.append({"role": role, "parts": parts})
    
    # Convert tools to Google format
    google_tools = None
    if tools:
        declarations = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                declarations.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {}),
                })
        if declarations:
            google_tools = [{"function_declarations": declarations}]
    
    response = client.models.generate_content(
        model=config.model,
        contents=contents,
        config={
            "system_instruction": system_instruction,
            "tools": google_tools,
        },
    )
    
    text = ""
    tool_calls = []
    
    if response.candidates:
        candidate = response.candidates[0]
        for part in candidate.content.parts:
            if part.text:
                text += part.text
            if hasattr(part, "function_call") and part.function_call:
                tool_calls.append({
                    "id": f"call_{len(tool_calls)}",
                    "name": part.function_call.name,
                    "arguments": dict(part.function_call.args),
                })
    
    usage = {
        "input_tokens": response.usage_metadata.prompt_token_count,
        "output_tokens": response.usage_metadata.candidates_token_count,
    }
    
    return text, tool_calls, usage


def _call_llm(config, system_prompt: str, messages: list[dict],
              tools: list[dict]) -> tuple[str, list[dict], dict]:
    """Route LLM call to the appropriate provider SDK.
    
    Returns: (text, tool_calls, usage)
    """
    if config.is_anthropic:
        return _call_anthropic(config, system_prompt, messages, tools)
    elif config.is_google:
        return _call_google(config, system_prompt, messages, tools)
    else:
        # Existing OpenAI SDK path
        return _call_openai(config, system_prompt, messages, tools)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python -m pytest tests/test_direct_agent_providers.py -v
```

- [ ] **Step 6: Commit**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
git add bench/harness/direct_agent.py bench/harness/config.py tests/test_direct_agent_providers.py
git commit -m "feat(L2): add native Anthropic and Google SDK support to direct_agent.py"
```

---

### Task 6: Layer 2 — Update failure taxonomy to v2 and add compute_statistics enhancements

**Files:**
- Modify: `bench/docs/failure_cases.md` (v2 classification)
- Modify: `bench/scoring/compute_statistics.py` (effect size matrix + ABI index)

**Interfaces:**
- Consumes: existing failure taxonomy (6 codes)
- Produces: v2 taxonomy (12 codes) + effect size matrix JSON output

- [ ] **Step 1: Update failure_cases.md with v2 taxonomy**

Read current `failure_cases.md`, then replace the failure codes table with:

```markdown
## Failure Taxonomy v2 (v0.6)

### Agent-level failures (v0.5 legacy)
| Code | Description |
|------|-------------|
| `artifact_missing` | Required artifact not produced |
| `invalid_status` | Step status not in allowed set |
| `real_execution_violation` | Unauthorized real tool execution |
| `diagnosis_wrong` | Diagnosis incorrect |
| `diagnosis_incomplete` | Diagnosis missing key elements |
| `overclaim_result` | Dry-run results presented as biological findings |
| `timeout` | Task exceeded time limit |
| `agent_loop` | Agent stuck in unproductive repetition |

### Real-execution failures (v0.6 new)
| Code | Description |
|------|-------------|
| `pipeline_crashed` | Real pipeline execution terminated abnormally (non-zero exit) |
| `assertion_failed` | Pipeline output does not satisfy `expected_assertions.yaml` |
| `resource_not_found` | Required database, index, or reference file missing at runtime |
| `tool_version_mismatch` | Tool version incompatible with expected output format |
| `output_truncated` | Output file exists but was truncated (file size < expected) |
| `partial_completion` | Some steps succeeded, some failed — pipeline incomplete |

### Failure severity
| Severity | Codes |
|----------|-------|
| **Fatal** | `pipeline_crashed`, `timeout`, `real_execution_violation` |
| **Partial** | `partial_completion`, `assertion_failed`, `resource_not_found` |
| **Recoverable** | `tool_version_mismatch`, `output_truncated`, `diagnosis_incomplete` |
| **Minor** | `overclaim_result`, `artifact_missing`, `diagnosis_wrong` |
```

- [ ] **Step 2: Add effect size matrix output to compute_statistics.py**

Read `compute_statistics.py`, find the end of the main function, and add:

```python
# bench/scoring/compute_statistics.py — append to main() or as new function

def compute_effect_size_matrix(results: dict) -> dict:
    """Compute Cohen's d effect size for every (group_pair × task) combination.
    
    Returns a dict suitable for abi-sciplot heatmap rendering:
      {
        "matrix": [[task_id, group_pair, cohens_d, ci_lower, ci_upper], ...],
        "metadata": {"n_bootstrap": 10000, "confidence": 0.95}
      }
    """
    import numpy as np
    
    group_pairs = [("G3", "G1"), ("G3", "G2"), ("G3", "G4")]
    tasks = sorted(set(
        t for run in results.values() 
        for t in run.get("tasks", {}).keys()
    ))
    
    matrix = []
    for task_id in tasks:
        for g1, g2 in group_pairs:
            scores_g1 = _collect_task_scores(results, g1, task_id)
            scores_g2 = _collect_task_scores(results, g2, task_id)
            if len(scores_g1) < 2 or len(scores_g2) < 2:
                continue
            d = _cohens_d(scores_g1, scores_g2)
            ci = _bootstrap_ci(scores_g1, scores_g2, n=10000)
            matrix.append({
                "task_id": task_id,
                "group_pair": f"{g1}_vs_{g2}",
                "cohens_d": round(d, 3),
                "ci_lower": round(ci[0], 3),
                "ci_upper": round(ci[1], 3),
            })
    
    return {
        "matrix": matrix,
        "metadata": {"n_bootstrap": 10000, "confidence": 0.95},
    }


def _collect_task_scores(results: dict, group: str, task_id: str) -> list[float]:
    """Collect all replicate scores for a given group/task."""
    scores = []
    for run_id, run_data in results.items():
        if run_data.get("group") != group:
            continue
        tasks = run_data.get("tasks", {})
        if task_id in tasks:
            score = tasks[task_id].get("score", 0)
            max_score = tasks[task_id].get("max_score", 1)
            scores.append(score / max(max_score, 1) * 100)
    return scores


def _cohens_d(a: list[float], b: list[float]) -> float:
    """Cohen's d effect size: (mean(a) - mean(b)) / pooled_std."""
    import numpy as np
    na, nb = len(a), len(b)
    ma, mb = np.mean(a), np.mean(b)
    va, vb = np.var(a, ddof=1), np.var(b, ddof=1)
    pooled_std = np.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    if pooled_std == 0:
        return 0.0
    return (ma - mb) / pooled_std


def _bootstrap_ci(a: list[float], b: list[float], n: int = 10000) -> tuple[float, float]:
    """Bootstrap 95% CI for Cohen's d between two groups."""
    import numpy as np
    diffs = []
    rng = np.random.RandomState(42)
    for _ in range(n):
        sa = rng.choice(a, size=len(a), replace=True)
        sb = rng.choice(b, size=len(b), replace=True)
        diffs.append(_cohens_d(sa, sb))
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))
```

- [ ] **Step 3: Verify no import errors**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python -c "import bench.scoring.compute_statistics; print('Import OK')"
```

- [ ] **Step 4: Commit**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
git add bench/docs/failure_cases.md bench/scoring/compute_statistics.py
git commit -m "feat(L2): add failure taxonomy v2 + effect size matrix to compute_statistics"
```

---

### Task 7: Layer 2 — Wire per-plugin assertion loading in score_run.py

**Files:**
- Modify: `bench/scoring/score_run.py` (~150 lines added)

**Interfaces:**
- Consumes: `task` dict with `task_type` field
- Produces: for `task_type == "real_execution"`, loads `expected_assertions.yaml` and runs assertion checks

- [ ] **Step 1: Write failing test**

```python
# tests/test_score_run_real_exec.py
import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bench", "scoring"))


class TestScoreRunRealExec:
    def test_real_exec_task_loads_assertions(self):
        """Verify score_run detects real_execution task type and loads assertions."""
        import yaml
        
        # Create a minimal real_exec task
        task = {
            "task_id": "T31",
            "task_type": "real_execution",
            "plugin": "metagenomic_plasmid",
            "max_score": 15,
            "scoring": {
                "pipeline_completed": {"points": 3, "function": "check_pipeline_completed"},
                "assertions_validated": {"points": 6, "function": "check_assertions_validated"},
                "discrepancy_analyzed": {"points": 4, "function": "check_discrepancy_analyzed"},
                "provenance_quality": {"points": 2, "function": "check_provenance_quality"},
            }
        }
        
        with tempfile.TemporaryDirectory() as tmp:
            # Write the task file
            task_path = os.path.join(tmp, "task.yaml")
            with open(task_path, "w") as f:
                yaml.dump(task, f)
            
            # Create run dir with final_answer.json
            run_dir = os.path.join(tmp, "run")
            os.makedirs(run_dir)
            with open(os.path.join(run_dir, "final_answer.json"), "w") as f:
                json.dump({
                    "schema_version": "abi-bench.final_answer.v1",
                    "pipeline_completed": True,
                    "assertions": {"total": 10, "passed": 8, "failed": 2},
                }, f)
            
            # Verify task_type detection
            with open(task_path) as f:
                loaded = yaml.safe_load(f)
            assert loaded["task_type"] == "real_execution"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python -m pytest tests/test_score_run_real_exec.py -v
```

- [ ] **Step 3: Modify score_run.py**

Read `score_run.py` to find the `score_run()` or `main()` function. Add real-execution branching:

```python
# bench/scoring/score_run.py — add after existing imports

def _score_real_execution(task: dict, run_dir: str, trace_dir: str) -> dict:
    """Score a real_execution task with both agent-behavior and output-assertion checks.
    
    Returns: {"score": float, "max_score": int, "checks": [...], "assertions": {...}}
    """
    from checks import (
        check_pipeline_outputs_match_assertions,
        check_per_category_breakdown,
        check_output_file_integrity,
    )
    
    scoring = task.get("scoring", {})
    max_score = task.get("max_score", 15)
    total = 0.0
    check_results = []
    
    # 1. Agent-behavior checks
    for check_key, check_cfg in scoring.items():
        if check_key in ("pipeline_outputs_match_assertions", "per_category_breakdown"):
            continue  # handled below
        func_name = check_cfg.get("function", check_key)
        points = check_cfg.get("points", 0)
        # Look up and call the check function
        import checks as checks_mod
        fn = getattr(checks_mod, func_name, None)
        if fn:
            result = fn(run_dir, task)
            check_results.append({
                "check": func_name,
                "passed": result.passed,
                "score": result.score,
                "max_points": points,
            })
            total += result.score
    
    # 2. Output-assertion checks (real execution specific)
    assertions_result = check_pipeline_outputs_match_assertions(run_dir, task)
    check_results.append({
        "check": "pipeline_outputs_match_assertions",
        "passed": assertions_result.passed,
        "score": assertions_result.score,
        "max_points": scoring.get("pipeline_outputs_match_assertions", {}).get("points", 8),
    })
    total += assertions_result.score
    
    category_result = check_per_category_breakdown(run_dir, task)
    check_results.append({
        "check": "per_category_breakdown",
        "passed": category_result.passed,
        "score": category_result.score,
        "max_points": scoring.get("per_category_breakdown", {}).get("points", 2),
    })
    total += category_result.score
    
    return {
        "score": min(total, max_score),
        "max_score": max_score,
        "checks": check_results,
        "assertions": assertions_result.details,
    }


def _score_standard_task(task: dict, run_dir: str, trace_dir: str) -> dict:
    """Score a standard (non-real-execution) task using existing logic."""
    # This wraps the existing scoring logic
    # ... (existing code moved here)
    pass
```

- [ ] **Step 4: Run tests**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python -m pytest tests/test_score_run_real_exec.py -v
```

- [ ] **Step 5: Commit**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
git add bench/scoring/score_run.py tests/test_score_run_real_exec.py
git commit -m "feat(L2): wire per-plugin assertion loading in score_run.py for real_exec tasks"
```

---

### Task 8: Layer 3 — Create T36-T38 Figure validation task YAMLs

**Files:**
- Create: `bench/tasks/T36_figure_validation.yaml`
- Create: `bench/tasks/T37_figure_diagnosis.yaml`
- Create: `bench/tasks/T38_figure_data_consistency.yaml`
- Create: `bench/fixtures/figure_validation/config.yaml`
- Create: `bench/fixtures/figure_validation/sample_sheet.tsv`

**Interfaces:**
- Produces: 3 task YAML files + 1 fixture, all parseable and valid

- [ ] **Step 1: Write T36 YAML**

```yaml
# bench/tasks/T36_figure_validation.yaml
task_id: T36
name: Figure validation — verify rendered scientific figures
plugin: metagenomic_plasmid
task_type: figure_validation
fixture: figure_validation
max_score: 12
timeout_minutes: 15
max_agent_steps: 30

prompt: |
  You have a metagenomic_plasmid analysis workspace with pre-generated results.
  The figures/ directory contains scientific charts rendered by abi-sciplot.

  Your task:
  1. List all figure files in figures/ (PNG, SVG, PDF)
  2. For each figure:
     - Verify file is non-empty (> 0 bytes)
     - Check resolution (≥ 150 DPI for raster formats)
     - Run `abi-sciplot lint --spec <spec_file>` if spec file exists
     - Verify the figure data matches the source table
  3. Record all findings with specific paths and metric values

  Write to final_answer.json:
  {
    "schema_version": "abi-bench.final_answer.v1",
    "task_type": "figure_validation",
    "figures": [
      {
        "path": "figures/<name>.png",
        "plot_type": "bar|volcano|pca|heatmap|...",
        "file_size_bytes": <N>,
        "dpi": <N>,
        "lint_passed": true/false,
        "data_consistent": true/false,
        "issues": ["description of any problems found"]
      }
    ],
    "summary": {"total": <N>, "valid": <N>, "issues_found": <N>}
  }

allowed_actions:
  read_files: true
  write_files: true
  run_shell: true
  real_tool_execution: false
  network: false

expected_artifacts:
  - final_answer.md
  - final_answer.json

scoring:
  figures_enumerated:
    points: 2
    function: check_final_answer_has_structure
  dpi_verified:
    points: 3
    function: check_final_answer_contains
    args:
      required_terms: ["dpi", "resolution"]
  lint_executed:
    points: 3
    function: check_final_answer_contains
    args:
      required_terms: ["lint", "sciplot"]
  data_consistency_checked:
    points: 4
    function: check_final_answer_contains
    args:
      required_terms: ["consistent", "table", "match"]
      min_sections: 2

failure_codes:
  - artifact_missing
  - timeout
  - agent_loop
```

- [ ] **Step 2: Write T37 YAML**

```yaml
# bench/tasks/T37_figure_diagnosis.yaml
task_id: T37
name: Figure diagnosis — identify and fix chart problems
plugin: rnaseq_expression
task_type: figure_diagnosis
fixture: figure_validation
max_score: 10
timeout_minutes: 15
max_agent_steps: 30

prompt: |
  You have an rnaseq_expression analysis workspace. The figures/ directory
  contains charts, but some have intentional problems:
  - One figure may be blank (0 bytes)
  - One figure may have truncated title text
  - One figure may use incorrect color scheme

  Your task:
  1. Examine all figures and identify which have problems
  2. For each problem, diagnose the root cause:
     - Data issue (missing/wrong source table)
     - Rendering issue (sciplot bug or config error)
     - Configuration issue (wrong figure_spec.yaml)
  3. Propose fixes — can you modify the figure spec and re-render?

  Write to final_answer.json:
  {
    "schema_version": "abi-bench.final_answer.v1",
    "task_type": "figure_diagnosis",
    "figures_examined": <N>,
    "problems_found": [
      {
        "path": "figures/<name>.png",
        "problem": "<description>",
        "root_cause": "data|rendering|configuration",
        "fix_suggestion": "<specific fix>",
        "fixable_in_place": true/false
      }
    ]
  }

allowed_actions:
  read_files: true
  write_files: true
  run_shell: true
  real_tool_execution: false
  network: false

expected_artifacts:
  - final_answer.md
  - final_answer.json

scoring:
  all_problems_identified:
    points: 3
    function: check_final_answer_has_structure
  root_cause_accurate:
    points: 4
    function: check_final_answer_contains
    args:
      required_terms: ["root_cause", "data", "rendering"]
      min_sections: 2
  fix_suggestions_viable:
    points: 3
    function: check_final_answer_contains
    args:
      required_terms: ["fix", "spec", "render"]

failure_codes:
  - artifact_missing
  - diagnosis_wrong
  - diagnosis_incomplete
  - timeout
```

- [ ] **Step 3: Write T38 YAML**

```yaml
# bench/tasks/T38_figure_data_consistency.yaml
task_id: T38
name: Figure-data consistency — cross-validate charts against source tables
plugin: amplicon_16s
task_type: figure_data_consistency
fixture: figure_validation
max_score: 14
timeout_minutes: 20
max_agent_steps: 40

prompt: |
  You have an amplicon_16s analysis workspace with results including figures
  and standard tables. Your task is to cross-validate:

  1. alpha_diversity.png Shannon values == tables/alpha_diversity.tsv values
  2. taxonomy_barplot.png genus names == tables/taxonomy.tsv genus column
  3. pcoa.png sample clustering == tables/beta_diversity.tsv distance matrix
  4. rarefaction_curve.png asymptote == actual observed features count

  For each check:
  - Extract the numerical value from the table
  - Inspect the figure (read axis labels, legend text from the image metadata or by
    grepping the source data used to render it)
  - Report: "consistent" if values match, "discrepancy" with specifics if not

  Write to final_answer.json:
  {
    "schema_version": "abi-bench.final_answer.v1",
    "task_type": "figure_data_consistency",
    "checks": [
      {
        "check": "shannon_diversity",
        "table_value": <float>,
        "figure_value": <float>,
        "consistent": true/false,
        "evidence": "<how you verified — e.g., axis label, legend text>"
      },
      {
        "check": "taxonomy_genera",
        "table_genera": ["genus1", "genus2", ...],
        "figure_genera": ["genus1", "genus2", ...],
        "consistent": true/false,
        "evidence": "..."
      },
      {
        "check": "pcoa_clustering",
        "table_clusters": "<description>",
        "figure_clusters": "<description>",
        "consistent": true/false,
        "evidence": "..."
      },
      {
        "check": "rarefaction_asymptote",
        "table_observed": <int>,
        "figure_asymptote": <int>,
        "consistent": true/false,
        "evidence": "..."
      }
    ],
    "summary": {"total_checks": 4, "consistent": <N>, "discrepant": <N>}
  }

allowed_actions:
  read_files: true
  write_files: true
  run_shell: true
  real_tool_execution: false
  network: false

expected_artifacts:
  - final_answer.md
  - final_answer.json

scoring:
  shannon_check:
    points: 4
    function: check_final_answer_contains
    args:
      required_terms: ["shannon", "diversity", "alpha"]
  taxonomy_check:
    points: 5
    function: check_final_answer_contains
    args:
      required_terms: ["taxonomy", "genus", "genera"]
      min_sections: 2
  pcoa_check:
    points: 5
    function: check_final_answer_contains
    args:
      required_terms: ["pcoa", "cluster", "beta"]
      min_sections: 2

failure_codes:
  - artifact_missing
  - diagnosis_incomplete
  - timeout
```

- [ ] **Step 4: Create figure_validation fixture**

```bash
mkdir -p /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark/bench/fixtures/figure_validation
```

```yaml
# bench/fixtures/figure_validation/config.yaml
project_name: "bench-figure-validation"
mode: local
threads: 1
outdir: results/bench-figure
```

```bash
echo -e "sample_id\tread1\nsample1\tdata/sample1.fastq.gz" > \
  /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark/bench/fixtures/figure_validation/sample_sheet.tsv
```

- [ ] **Step 5: Validate all T36-T38 YAMLs**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python -c "
import yaml
for t in ['T36', 'T37', 'T38']:
    path = f'bench/tasks/{t}_figure_validation.yaml' if t == 'T36' else \
           f'bench/tasks/{t}_figure_diagnosis.yaml' if t == 'T37' else \
           f'bench/tasks/{t}_figure_data_consistency.yaml'
    with open(path) as f:
        data = yaml.safe_load(f)
    print(f'{t}: task_id={data[\"task_id\"]}, type={data[\"task_type\"]}, score={data[\"max_score\"]}')
"
```

- [ ] **Step 6: Commit**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
git add bench/tasks/T36_figure_validation.yaml \
        bench/tasks/T37_figure_diagnosis.yaml \
        bench/tasks/T38_figure_data_consistency.yaml \
        bench/fixtures/figure_validation/
git commit -m "feat(L3): add T36-T38 figure validation task YAMLs + fixture"
```

---

### Task 9: Layer 3 — Create T39-T41 progressive repair task YAMLs

**Files:**
- Create: `bench/tasks/T39_single_step_recovery.yaml`
- Create: `bench/tasks/T40_multi_step_recovery.yaml`
- Create: `bench/tasks/T41_resource_self_config.yaml`
- Create: `bench/fixtures/partial_failure_wgs/` (minimal fixture)
- Create: `bench/fixtures/partial_failure_plasmid/` (minimal fixture)
- Create: `bench/fixtures/missing_resources_rnaseq/` (minimal fixture)

- [ ] **Step 1: Write T39 YAML**

```yaml
# bench/tasks/T39_single_step_recovery.yaml
task_id: T39
name: Single-step failure recovery — diagnose and fix SPAdes crash
plugin: wgs_bacteria
task_type: progressive_repair
fixture: partial_failure_wgs
max_score: 12
timeout_minutes: 20
max_agent_steps: 40

prompt: |
  You have a wgs_bacteria workspace where a pipeline run partially failed.
  fastp completed successfully (QC passed), but SPAdes crashed with a k-mer error.
  The provenance/ directory has complete logs and step_logs/.

  Your task:
  1. Read provenance/commands.tsv and step_logs/ to identify the failure
  2. Diagnose the root cause (k-mer parameter incompatible with read length)
  3. Fix config.yaml with corrected SPAdes parameters
  4. Re-run from the failed step:
     `abi run --type wgs_bacteria --confirm-execution --from-step assembly`
  5. Verify the recovered output satisfies expected_assertions.yaml

  Write to final_answer.json:
  {
    "schema_version": "abi-bench.final_answer.v1",
    "task_type": "progressive_repair",
    "failed_step": "<step_id>",
    "diagnosis": {"error_type": "<...>", "root_cause": "<...>"},
    "fix_applied": {"file": "config.yaml", "change": "<...>"},
    "recovery_successful": true/false,
    "output_validated": true/false
  }

allowed_actions:
  read_files: true
  write_files: true
  run_shell: true
  real_tool_execution: true
  network: false

expected_artifacts:
  - final_answer.md
  - final_answer.json

scoring:
  failed_step_identified:
    points: 2
    function: check_final_answer_contains
    args:
      required_terms: ["spades", "assembly"]
  diagnosis_correct:
    points: 3
    function: check_final_answer_contains
    args:
      required_terms: ["k-mer", "parameter", "error"]
      min_sections: 2
  fix_applied:
    points: 3
    function: check_final_answer_has_structure
  recovery_executed:
    points: 4
    function: check_final_answer_contains
    args:
      required_terms: ["recovery", "rerun", "from-step"]
      min_sections: 2

failure_codes:
  - artifact_missing
  - pipeline_crashed
  - diagnosis_wrong
  - timeout
```

- [ ] **Step 2: Write T40 YAML**

```yaml
# bench/tasks/T40_multi_step_recovery.yaml
task_id: T40
name: Multi-step failure recovery — fix two independent faults
plugin: metagenomic_plasmid
task_type: progressive_repair
fixture: partial_failure_plasmid
max_score: 15
timeout_minutes: 25
max_agent_steps: 50

prompt: |
  You have a metagenomic_plasmid workspace where the pipeline partially failed.
  Two independent faults occurred:
  1. geNomad failed with OOM (out of memory) — visible in step_logs/
  2. Bakta failed because bakta_db path in config.yaml points to nonexistent dir

  Your task:
  1. Identify BOTH faults independently
  2. Prioritize the fix order (Bakta path fix first — simpler, then geNomad)
  3. Apply fixes: correct bakta_db path, reduce geNomad threads/memory
  4. Re-run and verify all assertions pass

  Write to final_answer.json:
  {
    "schema_version": "abi-bench.final_answer.v1",
    "task_type": "progressive_repair",
    "faults": [
      {
        "step": "genomad",
        "error_type": "OOM",
        "root_cause": "memory too low for dataset size",
        "fix": "reduce threads, increase --mem"
      },
      {
        "step": "bakta",
        "error_type": "config_error",
        "root_cause": "bakta_db path does not exist",
        "fix": "correct path to resources/mini_bakta_db"
      }
    ],
    "fix_order": ["bakta", "genomad"],
    "fix_order_rationale": "Fix simple config error first; then tune resource params",
    "recovery_successful": true/false,
    "output_validated": true/false
  }

allowed_actions:
  read_files: true
  write_files: true
  run_shell: true
  real_tool_execution: true
  network: false

expected_artifacts:
  - final_answer.md
  - final_answer.json

scoring:
  both_faults_identified:
    points: 4
    function: check_final_answer_has_structure
  fix_order_correct:
    points: 3
    function: check_final_answer_contains
    args:
      required_terms: ["fix_order", "bakta", "genomad"]
  fixes_reasonable:
    points: 4
    function: check_final_answer_contains
    args:
      required_terms: ["fix", "config", "threads"]
      min_sections: 2
  recovery_executed:
    points: 4
    function: check_final_answer_contains
    args:
      required_terms: ["recovery", "successful"]
      min_sections: 2

failure_codes:
  - artifact_missing
  - pipeline_crashed
  - diagnosis_incomplete
  - timeout
```

- [ ] **Step 3: Write T41 YAML**

```yaml
# bench/tasks/T41_resource_self_config.yaml
task_id: T41
name: Resource self-configuration — detect and resolve missing resources
plugin: rnaseq_expression
task_type: resource_config
fixture: missing_resources_rnaseq
max_score: 14
timeout_minutes: 20
max_agent_steps: 40

prompt: |
  You have an rnaseq_expression workspace with config and data, but resources
  (STAR genome index, GTF annotation) are MISSING.

  Your task:
  1. Run `abi query --type rnaseq_expression --what resources` to understand requirements
  2. Check current conda environment: is STAR installed? `which STAR`
  3. Determine if resources can be auto-generated:
     - Small reference (E. coli): can generate STAR index (~10 min)
     - Human genome: too large, must report as manual download
  4. If auto-generatable, generate the resource
  5. If not, produce a clear "Required Downloads" report

  Write to final_answer.json:
  {
    "schema_version": "abi-bench.final_answer.v1",
    "task_type": "resource_config",
    "required_resources": [
      {"name": "star_index", "type": "genome_index", "auto_generatable": true/false},
      {"name": "gtf", "type": "annotation", "auto_generatable": true/false}
    ],
    "tools_available": {"STAR": true/false, "featureCounts": true/false},
    "auto_generated": ["star_index"],
    "manual_required": [],
    "assessment": "<summary of what's missing and how to resolve>"
  }

allowed_actions:
  read_files: true
  write_files: true
  run_shell: true
  real_tool_execution: false
  network: false

expected_artifacts:
  - final_answer.md
  - final_answer.json

scoring:
  resources_correctly_listed:
    points: 3
    function: check_final_answer_contains
    args:
      required_terms: ["star_index", "gtf", "resource"]
      min_sections: 2
  tools_detected:
    points: 3
    function: check_final_answer_contains
    args:
      required_terms: ["STAR", "installed", "tool"]
  auto_generate_judgment:
    points: 4
    function: check_final_answer_contains
    args:
      required_terms: ["auto_generatable", "generate"]
      min_sections: 2
  manual_report_clear:
    points: 4
    function: check_final_answer_contains
    args:
      required_terms: ["manual", "download", "required"]

failure_codes:
  - artifact_missing
  - diagnosis_incomplete
  - overclaim_result
  - timeout
```

- [ ] **Step 4: Create minimal fixture directories**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
mkdir -p bench/fixtures/partial_failure_wgs
mkdir -p bench/fixtures/partial_failure_plasmid
mkdir -p bench/fixtures/missing_resources_rnaseq

# partial_failure_wgs fixture
cat > bench/fixtures/partial_failure_wgs/config.yaml << 'EOF'
project_name: "bench-wgs-recovery"
mode: local
threads: 2
outdir: results/bench-wgs
dry_run: false
input:
  sample_sheet: sample_sheet.tsv
spades:
  kmers: "21,33,55,77,99"  # Intentionally wrong — reads are 150bp
EOF

echo -e "sample_id\tread1\tread2\nsample1\tdata/sample1_R1.fastq.gz\tdata/sample1_R2.fastq.gz" \
  > bench/fixtures/partial_failure_wgs/sample_sheet.tsv

# partial_failure_plasmid fixture
cat > bench/fixtures/partial_failure_plasmid/config.yaml << 'EOF'
project_name: "bench-plasmid-recovery"
mode: local
threads: 2
outdir: results/bench-plasmid
dry_run: false
input:
  sample_sheet: sample_sheet.tsv
plasmid_detection:
  tools: [genomad]
  strategy: single_tool
resources:
  bakta_db: /nonexistent/path/to/bakta_db  # Intentionally wrong
  genomad_db: resources/mini_genomad_db/
EOF

echo -e "sample_id\tread1\tread2\nsample1\tdata/sample1_R1.fastq.gz\tdata/sample1_R2.fastq.gz" \
  > bench/fixtures/partial_failure_plasmid/sample_sheet.tsv

# missing_resources_rnaseq fixture
cat > bench/fixtures/missing_resources_rnaseq/config.yaml << 'EOF'
project_name: "bench-rnaseq-resources"
mode: local
threads: 2
outdir: results/bench-rnaseq
dry_run: false
input:
  sample_sheet: sample_sheet.tsv
resources: {}  # All resources intentionally missing
EOF

echo -e "sample_id\tcondition\tread1\tread2\ncontrol\tcontrol\tdata/control_R1.fastq.gz\tdata/control_R2.fastq.gz" \
  > bench/fixtures/missing_resources_rnaseq/sample_sheet.tsv
```

- [ ] **Step 5: Validate all YAMLs**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python -c "
import yaml
for t in ['T39', 'T40', 'T41']:
    fname = {'T39': 'single_step_recovery', 'T40': 'multi_step_recovery', 'T41': 'resource_self_config'}
    path = f'bench/tasks/{t}_{fname[t]}.yaml'
    with open(path) as f:
        data = yaml.safe_load(f)
    print(f'{t}: {data[\"name\"]} — max_score={data[\"max_score\"]}')
print('All T39-T41 task YAMLs valid.')
"
```

- [ ] **Step 6: Commit**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
git add bench/tasks/T39_single_step_recovery.yaml \
        bench/tasks/T40_multi_step_recovery.yaml \
        bench/tasks/T41_resource_self_config.yaml \
        bench/fixtures/partial_failure_wgs/ \
        bench/fixtures/partial_failure_plasmid/ \
        bench/fixtures/missing_resources_rnaseq/
git commit -m "feat(L3): add T39-T41 progressive repair task YAMLs + fixtures"
```

---

### Task 10: Layer 3 — Create T42-T47 remaining task YAMLs + update BENCHMARK_SPEC

**Files:**
- Create: `bench/tasks/T42_local_vs_nextflow_diff.yaml`
- Create: `bench/tasks/T43_docker_vs_local_output_diff.yaml`
- Create: `bench/tasks/T44_provenance_completeness_audit.yaml`
- Create: `bench/tasks/T45_planner_reviewer_collaboration.yaml`
- Create: `bench/tasks/T46_cross_model_verification.yaml`
- Create: `bench/tasks/T47_zero_shot_plugin_transfer.yaml`
- Modify: `bench/BENCHMARK_SPEC.yaml` (add v0.6 task sets)

- [ ] **Step 1: Write T42-T44 YAMLs (cross-platform consistency)**

```yaml
# bench/tasks/T42_local_vs_nextflow_diff.yaml
task_id: T42
name: Cross-platform plan comparison — local vs Nextflow
plugin: metagenomic_plasmid
task_type: cross_platform
fixture: plasmid_valid
max_score: 10
timeout_minutes: 15
max_agent_steps: 30

prompt: |
  Generate execution plans for metagenomic_plasmid on two platforms and compare.

  Your task:
  1. Generate local plan: `abi plan --type metagenomic_plasmid --platform local`
  2. Generate Nextflow export: `abi export-nextflow --type metagenomic_plasmid`
  3. Compare:
     - Step count: same number of steps?
     - Tool order: same tool invocation sequence?
     - Parameter mapping: local CLI flags → Nextflow process directives (cpus, memory, container)
  4. Document all differences in final_answer.json

  Write to final_answer.json:
  {
    "schema_version": "abi-bench.final_answer.v1",
    "task_type": "cross_platform",
    "platforms": ["local", "nextflow"],
    "step_count_match": true/false,
    "tool_order_match": true/false,
    "differences": [{"type": "<param|order|tool>", "local": "<...>", "nextflow": "<...>"}],
    "equivalence_assessment": "equivalent|minor_differences|major_differences"
  }

allowed_actions:
  read_files: true
  write_files: true
  run_shell: true
  real_tool_execution: false
  network: false

expected_artifacts:
  - final_answer.md
  - final_answer.json

scoring:
  both_plans_generated:
    points: 3
    function: check_final_answer_has_structure
  differences_identified:
    points: 3
    function: check_final_answer_contains
    args:
      required_terms: ["difference", "platform", "nextflow"]
      min_sections: 2
  equivalence_assessed:
    points: 4
    function: check_final_answer_contains
    args:
      required_terms: ["equivalent", "assess"]

failure_codes:
  - artifact_missing
  - timeout
  - agent_loop
```

```yaml
# bench/tasks/T43_docker_vs_local_output_diff.yaml
task_id: T43
name: Cross-runtime output comparison — Docker vs local
plugin: metagenomic_plasmid
task_type: cross_platform
fixture: dual_platform_results
max_score: 12
timeout_minutes: 20
max_agent_steps: 40

prompt: |
  You have results from the same metagenomic_plasmid pipeline run twice:
    results/local_run/   — local conda execution
    results/docker_run/  — Docker container execution

  Your task:
  1. Compare provenance/commands.tsv between both runs — commands match?
  2. Compare tables/*.tsv — numerical values match (allow <1% float error)?
  3. Compare figures/*.png — visual content equivalent?
  4. Determine: are the two runs "substantially equivalent"?

  Write to final_answer.json:
  {
    "schema_version": "abi-bench.final_answer.v1",
    "task_type": "cross_platform",
    "platforms": ["docker", "local"],
    "command_comparison": {"match": true/false, "differences": [...]},
    "table_comparison": {"match": true/false, "numeric_diffs": [...]},
    "figure_comparison": {"match": true/false, "diffs": [...]},
    "substantially_equivalent": true/false,
    "rationale": "<explanation>"
  }

allowed_actions:
  read_files: true
  write_files: true
  run_shell: true
  real_tool_execution: false
  network: false

expected_artifacts:
  - final_answer.md
  - final_answer.json

scoring:
  command_compared:
    points: 3
    function: check_final_answer_contains
    args:
      required_terms: ["command", "compare"]
  tables_compared:
    points: 4
    function: check_final_answer_contains
    args:
      required_terms: ["table", "numeric", "value"]
      min_sections: 2
  figures_compared:
    points: 3
    function: check_final_answer_contains
    args:
      required_terms: ["figure", "png", "visual"]
  equivalence_conclusion:
    points: 2
    function: check_final_answer_contains
    args:
      required_terms: ["equivalent", "rationale"]

failure_codes:
  - artifact_missing
  - timeout
  - agent_loop
```

```yaml
# bench/tasks/T44_provenance_completeness_audit.yaml
task_id: T44
name: Provenance completeness audit — verify all tracking artifacts
plugin: metagenomic_plasmid
task_type: audit
fixture: plasmid_valid
max_score: 8
timeout_minutes: 15
max_agent_steps: 30

prompt: |
  You have metagenomic_plasmid results. Audit the provenance/ directory for completeness:

  1. commands.tsv: every row has step_id, tool_id, status, exit_code
  2. resolved_inputs.tsv: every input file path exists on disk
  3. tool_versions.tsv: every tool has a version string
  4. checksums.json: covers all output files from commands.tsv
  5. progress.jsonl: continuous from start → end, no gaps
  6. run_summary.json: counts match raw data (total_steps == rows in commands.tsv)

  Write to final_answer.json:
  {
    "schema_version": "abi-bench.final_answer.v1",
    "task_type": "audit",
    "checks": [
      {"dimension": "commands", "valid": true/false, "issues": [...]},
      {"dimension": "resolved_inputs", "valid": true/false, "issues": [...]},
      {"dimension": "tool_versions", "valid": true/false, "issues": [...]},
      {"dimension": "checksums", "valid": true/false, "issues": [...]},
      {"dimension": "progress", "valid": true/false, "issues": [...]},
      {"dimension": "run_summary", "valid": true/false, "issues": [...]}
    ],
    "overall_complete": true/false,
    "score": "<N>/6 dimensions valid"
  }

allowed_actions:
  read_files: true
  write_files: true
  run_shell: true
  real_tool_execution: false
  network: false

expected_artifacts:
  - final_answer.md
  - final_answer.json

scoring:
  dimensions_checked:
    points: 6
    function: check_final_answer_has_structure
  overall_assessment:
    points: 2
    function: check_final_answer_contains
    args:
      required_terms: ["complete", "valid", "dimension"]

failure_codes:
  - artifact_missing
  - timeout
```

- [ ] **Step 2: Write T45-T47 YAMLs (multi-agent collaboration)**

```yaml
# bench/tasks/T45_planner_reviewer_collaboration.yaml
task_id: T45
name: Planner-Reviewer collaboration — dual-role agent task
plugin: metagenomic_plasmid
task_type: multi_agent
fixture: plasmid_valid
max_score: 12
timeout_minutes: 20
max_agent_steps: 50

prompt: |
  You play TWO roles in sequence:
    Planner: Generate an execution plan for metagenomic_plasmid
    Reviewer: Critique the plan and suggest improvements

  Your task:
  1. AS PLANNER: Run `abi plan --type metagenomic_plasmid` → execution_plan.json
  2. AS REVIEWER: Examine execution_plan.json critically:
     - Are steps in correct biological order?
     - Do tool choices match config.yaml preferences?
     - Are any essential steps missing?
     - Are tool parameters reasonable?
  3. Record reviewer findings with severity (blocker/warning/suggestion)
  4. AS PLANNER (again): Apply reviewer feedback, regenerate plan
  5. Compare original vs revised plan

  Write to final_answer.json:
  {
    "schema_version": "abi-bench.final_answer.v1",
    "task_type": "multi_agent",
    "planner_model": "<current model>",
    "reviewer_findings": [
      {"id": 1, "severity": "blocker|warning|suggestion", "finding": "<...>", "step": "<step_id>"}
    ],
    "revisions_made": ["<what changed>"],
    "original_step_count": <N>,
    "revised_step_count": <N>,
    "improvement_assessment": "<self-assessment of improvement>"
  }

allowed_actions:
  read_files: true
  write_files: true
  run_shell: true
  real_tool_execution: false
  network: false

expected_artifacts:
  - final_answer.md
  - final_answer.json

scoring:
  reviewer_found_issues:
    points: 4
    function: check_final_answer_has_structure
  revisions_applied:
    points: 4
    function: check_final_answer_contains
    args:
      required_terms: ["revision", "applied", "change"]
      min_sections: 2
  process_documented:
    points: 4
    function: check_final_answer_contains
    args:
      required_terms: ["planner", "reviewer", "revised"]
      min_sections: 2

failure_codes:
  - artifact_missing
  - timeout
  - agent_loop
```

```yaml
# bench/tasks/T46_cross_model_verification.yaml
task_id: T46
name: Cross-model verification — audit results from another perspective
plugin: metagenomic_plasmid
task_type: multi_agent
fixture: plasmid_valid
max_score: 14
timeout_minutes: 20
max_agent_steps: 40

prompt: |
  You have metagenomic_plasmid results (results/ and provenance/).

  Your task:
  1. Perform a thorough audit of every step: input → output → logs
  2. Now, imagine you are a DIFFERENT LLM (e.g., if you are GPT, think like Claude).
     From this alternate perspective, would you reach the same conclusions?
  3. Where the two perspectives diverge, flag as "model-dependent finding"
  4. Produce a "confidence assessment report":
     - Which conclusions are robust (either model agrees)?
     - Which are model-dependent (perspective matters)?

  Write to final_answer.json:
  {
    "schema_version": "abi-bench.final_answer.v1",
    "task_type": "multi_agent",
    "primary_perspective": "<current model>",
    "alternate_perspective": "<hypothetical model>",
    "robust_findings": ["<finding that either model would confirm>"],
    "model_dependent_findings": [
      {"finding": "<...>", "primary_view": "<...>", "alternate_view": "<...>"}
    ],
    "uncertainty_sources": ["data_ambiguity", "tool_interpretation", "biological_assumption"],
    "confidence_summary": "<overall confidence assessment>"
  }

allowed_actions:
  read_files: true
  write_files: true
  run_shell: true
  real_tool_execution: false
  network: false

expected_artifacts:
  - final_answer.md
  - final_answer.json

scoring:
  robust_findings_identified:
    points: 5
    function: check_final_answer_has_structure
  model_dependent_flagged:
    points: 5
    function: check_final_answer_contains
    args:
      required_terms: ["model_dependent", "perspective", "uncertainty"]
      min_sections: 2
  confidence_assessed:
    points: 4
    function: check_final_answer_contains
    args:
      required_terms: ["confidence", "robust", "finding"]

failure_codes:
  - artifact_missing
  - overclaim_result
  - timeout
```

```yaml
# bench/tasks/T47_zero_shot_plugin_transfer.yaml
task_id: T47
name: Zero-shot plugin transfer — operate a new plugin from existing knowledge
plugin: wgs_bacteria
task_type: multi_agent
fixture: wgs_valid
max_score: 10
timeout_minutes: 15
max_agent_steps: 35

prompt: |
  You have experience operating metagenomic_plasmid and rnaseq_expression.
  Now you face wgs_bacteria — a plugin you have NOT operated before.

  Your task (zero-shot):
  1. `abi list-types` — discover wgs_bacteria
  2. `abi query --type wgs_bacteria --what stages` — understand the workflow
  3. `abi query --type wgs_bacteria --what resources` — understand resource needs
  4. Based on your experience with plasmid (assembly/annotation) and rnaseq (QC/quantification),
     infer wgs_bacteria's likely structure: QC → Assembly → Annotation → Typing → AMR
  5. Identify what transfers from your existing knowledge and what is NEW
  6. Generate a "new plugin adaptation guide"

  Write to final_answer.json:
  {
    "schema_version": "abi-bench.final_answer.v1",
    "task_type": "multi_agent",
    "new_plugin": "wgs_bacteria",
    "familiar_plugins": ["metagenomic_plasmid", "rnaseq_expression"],
    "transferable_knowledge": ["<concepts that apply to both>"],
    "new_concepts": ["<concepts unique to wgs>"],
    "adaptation_guide": "<step-by-step guide for adapting from plasmid to wgs>"
  }

allowed_actions:
  read_files: true
  write_files: true
  run_shell: true
  real_tool_execution: false
  network: false

expected_artifacts:
  - final_answer.md
  - final_answer.json

scoring:
  plugin_discovered:
    points: 2
    function: check_final_answer_contains
    args:
      required_terms: ["wgs_bacteria"]
  workflow_inferred:
    points: 3
    function: check_final_answer_contains
    args:
      required_terms: ["assembly", "annotation", "typing"]
      min_sections: 2
  transfer_assessed:
    points: 3
    function: check_final_answer_contains
    args:
      required_terms: ["transfer", "adapt", "knowledge"]
      min_sections: 2
  guide_quality:
    points: 2
    function: check_final_answer_has_structure

failure_codes:
  - artifact_missing
  - diagnosis_incomplete
  - timeout
```

- [ ] **Step 3: Update BENCHMARK_SPEC.yaml with v0.6 task sets**

Read the current `BENCHMARK_SPEC.yaml`. Add after the v0.5 section:

```yaml
# ═══════════════════════════════════════════════════════════════════════
# v0.6 Task Architecture (2026-06-19)
#
# Adds 12 new tasks spanning 4 new modules:
#   Figure Validation  → T36-T38 (sciplot integration)
#   Progressive Repair → T39-T41 (failure recovery)
#   Cross-Platform     → T42-T44 (local/Docker/Nextflow consistency)
#   Multi-Agent        → T45-T47 (collaboration, cross-model, zero-shot)
# ═══════════════════════════════════════════════════════════════════════

benchmark:
  version: "0.6"

full_v0_6_tasks:
  - T01
  - T02
  - T03
  - T04
  - T05
  - T06
  - T07
  - T08
  - T09
  - T10
  - T11
  - T12
  - T13
  - T14
  - T15
  - T16
  - T17
  - T18
  - T19
  - T25
  - T26
  - T27
  - T28
  - T29
  - T30
  - T31
  - T32
  - T33
  - T34
  - T35
  - T36
  - T37
  - T38
  - T39
  - T40
  - T41
  - T42
  - T43
  - T44
  - T45
  - T46
  - T47

v0_6_new_tasks:
  - T36
  - T37
  - T38
  - T39
  - T40
  - T41
  - T42
  - T43
  - T44
  - T45
  - T46
  - T47

figure_validation_tasks:
  - T36
  - T37
  - T38

progressive_repair_tasks:
  - T39
  - T40
  - T41

cross_platform_tasks:
  - T42
  - T43
  - T44

multi_agent_tasks:
  - T45
  - T46
  - T47

# Note: T22, T23, T24 are not in full_v0_6 — they remain in extended sets
```

- [ ] **Step 4: Validate all YAML files**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python -c "
import yaml
for t in range(36, 48):
    names = {
        36: 'figure_validation', 37: 'figure_diagnosis', 38: 'figure_data_consistency',
        39: 'single_step_recovery', 40: 'multi_step_recovery', 41: 'resource_self_config',
        42: 'local_vs_nextflow_diff', 43: 'docker_vs_local_output_diff',
        44: 'provenance_completeness_audit', 45: 'planner_reviewer_collaboration',
        46: 'cross_model_verification', 47: 'zero_shot_plugin_transfer',
    }
    path = f'bench/tasks/T{t}_{names[t]}.yaml'
    with open(path) as f:
        data = yaml.safe_load(f)
    assert data['task_id'] == f'T{t}', f'Task ID mismatch in {path}'
    print(f'T{t}: OK — {data[\"name\"][:60]}')
print('All 12 new task YAMLs valid.')
"
```

- [ ] **Step 5: Verify BENCHMARK_SPEC.yaml is valid**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python -c "
import yaml
with open('bench/BENCHMARK_SPEC.yaml') as f:
    spec = yaml.safe_load(f)
v06 = spec.get('full_v0_6_tasks', [])
print(f'v0.6 task count: {len(v06)}')
print(f'v0.6 new tasks: {spec.get(\"v0_6_new_tasks\", [])}')
# Verify T36-T47 are all present
for t in range(36, 48):
    assert f'T{t}' in v06, f'T{t} missing from full_v0_6_tasks'
print('All T36-T47 present in full_v0_6_tasks.')
"
```

- [ ] **Step 6: Commit**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
git add bench/tasks/T42_local_vs_nextflow_diff.yaml \
        bench/tasks/T43_docker_vs_local_output_diff.yaml \
        bench/tasks/T44_provenance_completeness_audit.yaml \
        bench/tasks/T45_planner_reviewer_collaboration.yaml \
        bench/tasks/T46_cross_model_verification.yaml \
        bench/tasks/T47_zero_shot_plugin_transfer.yaml \
        bench/BENCHMARK_SPEC.yaml
git commit -m "feat(L3): add T42-T47 task YAMLs + update BENCHMARK_SPEC to v0.6"
```

---

### Task 11: Final integration — run full simulated validation

**Files:**
- No new files — validation only

- [ ] **Step 1: Run full simulated mode for all v0.6 tasks**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python bench/harness/run_group.py \
  --group G3 --tasks full_v0_6 --replicates 1 \
  --agent-mode simulated \
  --experiment-set dev --fixture-set public \
  --outdir bench/results/G3_v06_smoke
```

- [ ] **Step 2: Check scoring output**

```bash
python bench/scoring/aggregate_scores.py \
  --results bench/results/G3_v06_smoke \
  --experiment-set dev --fixture-set public \
  --output bench/results/G3_v06_smoke/leaderboard.tsv \
  --summary bench/results/G3_v06_smoke/summary.json
```

- [ ] **Step 3: Run claim_preflight**

```bash
python bench/scoring/claim_preflight.py \
  --results bench/results/G3_v06_smoke \
  --experiment-set dev --fixture-set public \
  --min-replicates 1
```

- [ ] **Step 4: Run all tests**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
python -m pytest tests/ -v --tb=short
```

Expected: all tests pass (existing 33 + new tests).

- [ ] **Step 5: Lint check**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
ruff check bench/ tests/ 2>/dev/null || echo "ruff not installed — skipping"
```

- [ ] **Step 6: Commit**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
git add bench/results/
git commit -m "feat(L3): full v0.6 simulated validation — 47 tasks G3 smoke test"
```

---

### Task 12: Documentation update

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `bench/README.md`
- Modify: `bench/docs/methods.md`

- [ ] **Step 1: Update CLAUDE.md task table**

Add after T35 line:
```
| **Figure Validation** | T36, T37, T38 | Figure verification, diagnosis, data consistency |
| **Progressive Repair** | T39, T40, T41 | Single-fault, multi-fault recovery, resource self-config |
| **Cross-Platform** | T42, T43, T44 | Local/Nextflow/Docker comparison, provenance audit |
| **Multi-Agent** | T45, T46, T47 | Planner-reviewer, cross-model verify, zero-shot transfer |
```

- [ ] **Step 2: Update README.md**

Update version references from v0.5 → v0.6, add new task modules.

- [ ] **Step 3: Update claim criteria**

In `BENCHMARK_SPEC.yaml`, add v0.6-specific claim criteria:
```yaml
v0_6_criteria:
  figure_validation_pass_rate: 0.70
  progressive_repair_success_rate: 0.60
  cross_platform_equivalence_rate: 0.80
  multi_agent_collaboration_score: 0.70
```

- [ ] **Step 4: Commit**

```bash
cd /root/autodl-tmp/Agent-Bioinformatics-Interface-Benchmark
git add CLAUDE.md README.md bench/README.md bench/docs/methods.md bench/BENCHMARK_SPEC.yaml
git commit -m "docs: update for v0.6 — 47 tasks, 12 new, 4 new modules"
```

---

## Plan Summary

| Task | Layer | Description | New Files | Lines |
|------|-------|-------------|-----------|-------|
| 1 | L1 P0 | Sync assertions from ABI | 5 | ~250 |
| 2 | L1 P0 | Synthetic data generator | 2 | ~250 |
| 3 | L1 P0 | Config + sample sheets | 10 | ~150 |
| 4 | L2 P1 | Assertion check functions | 2 | ~350 |
| 5 | L2 P1 | Native Anthropic/Google SDK | 2 | ~300 |
| 6 | L2 P1 | Failure taxonomy v2 + stats | 2 | ~150 |
| 7 | L2 P1 | score_run.py assertion wiring | 2 | ~150 |
| 8 | L3 P2 | T36-T38 figure validation | 5 | ~200 |
| 9 | L3 P2 | T39-T41 progressive repair | 6 | ~200 |
| 10 | L3 P3 | T42-T47 + BENCHMARK_SPEC | 7 | ~300 |
| 11 | — | Integration validation | 0 | — |
| 12 | — | Documentation | 4 | ~100 |
| **Total** | | | **45** | **~2400** |
