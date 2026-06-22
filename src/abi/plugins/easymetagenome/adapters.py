"""ABI-native adapters for the EasyMetagenome-inspired P0 workflow.

No code from EasyMetagenome's GPLv3 shell pipeline is copied here.  These
adapters implement ABI-owned validation, command planning, normalization,
resume checks, failure diagnosis, and reporting.
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import shlex
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml


class EasyMetagenomeError(RuntimeError):
    """Base P0 workflow error."""


class ManifestValidationError(EasyMetagenomeError, ValueError):
    """The sample manifest is missing required or usable data."""


class DatabaseValidationError(EasyMetagenomeError):
    """A declared database is incomplete."""


class OutputValidationError(EasyMetagenomeError):
    """A node output is missing or empty."""


@dataclass(frozen=True)
class SampleRecord:
    sample_id: str
    r1: str
    r2: str
    group: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"sample_id": self.sample_id, "r1": self.r1, "r2": self.r2, "group": self.group}


class ManifestValidator:
    """Validate paired FASTQ metadata and emit normalized ABI artifacts."""

    aliases = {"r1": ("r1", "read1"), "r2": ("r2", "read2")}

    @classmethod
    def validate(cls, manifest: str | Path, *, check_files: bool = True) -> list[SampleRecord]:
        path = Path(manifest).resolve()
        if not path.is_file():
            raise ManifestValidationError(f"Manifest does not exist: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            first = handle.readline()
            handle.seek(0)
            delimiter = "\t" if "\t" in first else ","
            reader = csv.DictReader(handle, delimiter=delimiter)
            fields = {str(name).strip().lower(): str(name) for name in (reader.fieldnames or [])}
            if "sample_id" not in fields:
                raise ManifestValidationError("Manifest requires a sample_id column")
            selected: dict[str, str] = {}
            for canonical, aliases in cls.aliases.items():
                match = next((fields[name] for name in aliases if name in fields), None)
                if not match:
                    raise ManifestValidationError(
                        f"Manifest requires a {canonical} or read{canonical[-1]} column"
                    )
                selected[canonical] = match
            sample_field = fields["sample_id"]
            group_field = fields.get("group")
            records: list[SampleRecord] = []
            seen: set[str] = set()
            errors: list[str] = []
            for line_no, row in enumerate(reader, start=2):
                sample_id = str(row.get(sample_field) or "").strip()
                if not sample_id:
                    errors.append(f"line {line_no}: sample_id is empty")
                    continue
                if sample_id in seen:
                    errors.append(f"line {line_no}: duplicate sample_id {sample_id!r}")
                    continue
                seen.add(sample_id)
                values: dict[str, str] = {}
                for key in ("r1", "r2"):
                    raw = str(row.get(selected[key]) or "").strip()
                    candidate = Path(raw)
                    if raw and not candidate.is_absolute():
                        candidate = (path.parent / candidate).resolve()
                    values[key] = str(candidate)
                    if not raw:
                        errors.append(f"line {line_no}: {key} is empty")
                    elif check_files and (not candidate.is_file() or candidate.stat().st_size == 0):
                        errors.append(f"line {line_no}: {key} FASTQ missing or empty: {candidate}")
                records.append(
                    SampleRecord(
                        sample_id,
                        values["r1"],
                        values["r2"],
                        str(row.get(group_field) or "").strip() if group_field else "",
                    )
                )
        if errors:
            raise ManifestValidationError("Invalid manifest:\n- " + "\n- ".join(errors))
        if not records:
            raise ManifestValidationError("Manifest contains no samples")
        return records

    @classmethod
    def write_outputs(
        cls, manifest: str | Path, workdir: str | Path, *, check_files: bool = True
    ) -> dict[str, Path]:
        records = cls.validate(manifest, check_files=check_files)
        result_dir = Path(workdir) / "result"
        result_dir.mkdir(parents=True, exist_ok=True)
        normalized = result_dir / "metadata.normalized.tsv"
        with normalized.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["sample_id", "r1", "r2", "group"], delimiter="\t"
            )
            writer.writeheader()
            writer.writerows(record.as_dict() for record in records)
        report = result_dir / "input_validation.json"
        report.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "sample_count": len(records),
                    "manifest": str(Path(manifest).resolve()),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return {"normalized_manifest": normalized, "validation_report": report}


class DatabaseChecker:
    """Validate a database registry and expand environment placeholders."""

    @staticmethod
    def check(registry_path: str | Path) -> dict[str, Any]:
        registry = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or {}
        checks = registry.get("checks", [])
        missing: list[str] = []
        for item in checks:
            raw = item.get("exists") if isinstance(item, Mapping) else None
            if not raw:
                continue
            path = Path(os.path.expandvars(str(raw))).expanduser()
            if not path.exists() or (path.is_file() and path.stat().st_size == 0):
                missing.append(str(path))
        return {
            "database_id": registry.get("database_id", "unknown"),
            "status": "fail" if missing else "pass",
            "missing": missing,
            "registry": str(Path(registry_path)),
        }

    @classmethod
    def require(cls, registry_path: str | Path) -> dict[str, Any]:
        report = cls.check(registry_path)
        if report["status"] == "fail":
            raise DatabaseValidationError("Database files missing: " + ", ".join(report["missing"]))
        return report


class OutputChecker:
    """Require every declared file or directory to be non-empty."""

    @staticmethod
    def check(paths: Iterable[str | Path]) -> tuple[bool, list[str]]:
        failures: list[str] = []
        for value in paths:
            path = Path(value)
            if not path.exists():
                failures.append(f"missing: {path}")
            elif path.is_file() and path.stat().st_size == 0:
                failures.append(f"empty file: {path}")
            elif path.is_dir() and not any(path.iterdir()):
                failures.append(f"empty directory: {path}")
        return not failures, failures

    @classmethod
    def require(cls, paths: Iterable[str | Path]) -> None:
        passed, failures = cls.check(paths)
        if not passed:
            raise OutputValidationError("Output checks failed: " + "; ".join(failures))


class ResumeManager:
    """Skip a node only when all declared checks pass."""

    @staticmethod
    def should_skip(paths: Iterable[str | Path], *, resume: bool = True) -> bool:
        if not resume:
            return False
        values = list(paths)
        return bool(values) and OutputChecker.check(values)[0]


@dataclass(frozen=True)
class ToolAdapter:
    tool_id: str
    executable: str
    command_template: str
    version_args: tuple[str, ...] = ("--version",)
    failure_patterns: tuple[tuple[str, str], ...] = ()

    def version_check(self) -> dict[str, Any]:
        path = shutil.which(self.executable)
        if not path:
            return {"tool": self.tool_id, "status": "fail", "reason": "executable_not_found"}
        try:
            completed = subprocess.run(
                [self.executable, *self.version_args],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"tool": self.tool_id, "status": "fail", "reason": str(exc)}
        text = ((completed.stdout or "") + (completed.stderr or "")).strip()[:1000]
        return {
            "tool": self.tool_id,
            "status": "pass" if completed.returncode == 0 else "fail",
            "version": text,
        }

    def build_command(self, values: Mapping[str, Any]) -> list[str]:
        try:
            rendered = self.command_template.format_map(dict(values))
        except KeyError as exc:
            raise ValueError(f"{self.tool_id} command missing value: {exc.args[0]}") from exc
        return shlex.split(rendered)

    def dry_run(self, values: Mapping[str, Any]) -> str:
        return shlex.join(self.build_command(values))

    def output_check(self, paths: Iterable[str | Path]) -> tuple[bool, list[str]]:
        return OutputChecker.check(paths)

    def diagnose(self, stderr: str, returncode: int) -> str:
        for pattern, diagnosis in self.failure_patterns:
            if re.search(pattern, stderr, flags=re.IGNORECASE):
                return diagnosis
        return f"{self.tool_id} exited with status {returncode}; inspect the node stderr log."


FASTP_ADAPTER = ToolAdapter(
    "fastp",
    "fastp",
    "fastp -i {r1} -I {r2} -o {clean_r1} -O {clean_r2} -j {json} -h {html} --thread {threads}",
    failure_patterns=(("killed", "fastp was likely terminated for insufficient memory."),),
)
SEQKIT_ADAPTER = ToolAdapter(
    "seqkit",
    "seqkit",
    "seqkit stat -T {r1} {r2}",
    version_args=("version",),
)
KNEADDATA_ADAPTER = ToolAdapter(
    "kneaddata",
    "kneaddata",
    "kneaddata -i1 {clean_r1} -i2 {clean_r2} -o {output_dir} "
    "-db {host_db} -t {threads} --bypass-trim --bypass-trf --reorder "
    "--remove-intermediate-output",
    failure_patterns=(
        ("database|bowtie2.*index", "The KneadData host database is invalid or incomplete."),
    ),
)
KRAKEN2_ADAPTER = ToolAdapter(
    "kraken2",
    "kraken2",
    "kraken2 --db {kraken2_db} --paired {dehost_r1} {dehost_r2} "
    "--threads {threads} --use-names --report-zero-counts "
    "--report {report} --output {output}",
    failure_patterns=(
        (
            "database does not contain|database.*missing",
            "The Kraken2 database path is invalid or incomplete.",
        ),
        (
            "killed|cannot allocate memory",
            "Kraken2 ran out of memory; use a smaller database or request more memory.",
        ),
    ),
)
BRACKEN_ADAPTER = ToolAdapter(
    "bracken",
    "bracken",
    "bracken -d {kraken2_db} -i {kraken2_report} -r {read_length} "
    "-l {tax_level} -t {threshold} -o {bracken_table} -w {bracken_report}",
    failure_patterns=(("database|kmer", "Bracken files are missing from the Kraken2 database."),),
)
TOOL_ADAPTERS = {
    item.tool_id: item
    for item in (
        SEQKIT_ADAPTER,
        FASTP_ADAPTER,
        KNEADDATA_ADAPTER,
        KRAKEN2_ADAPTER,
        BRACKEN_ADAPTER,
    )
}


def parse_fastp_json(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for value in paths:
        path = Path(value)
        data = json.loads(path.read_text(encoding="utf-8"))
        before = data.get("summary", {}).get("before_filtering", {})
        after = data.get("summary", {}).get("after_filtering", {})
        rows.append(
            {
                "sample_id": path.name.split("_fastp", 1)[0].split(".fastp", 1)[0],
                "raw_reads": before.get("total_reads", 0),
                "clean_reads": after.get("total_reads", 0),
                "q30_rate": after.get("q30_rate", ""),
            }
        )
    return rows


def parse_kneaddata_counts(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def merge_bracken(
    files: Sequence[str | Path], output: str | Path, *, abundance_column: str = "new_est_reads"
) -> Path:
    """Merge Bracken tables by taxon, retaining one abundance column per sample."""
    taxa: dict[tuple[str, str], dict[str, Any]] = defaultdict(dict)
    sample_ids: list[str] = []
    for value in files:
        path = Path(value)
        sample_id = path.name.split(".", 1)[0]
        sample_ids.append(sample_id)
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                name = str(row.get("name") or row.get("taxonomy_name") or "").strip()
                taxid = str(row.get("taxonomy_id") or row.get("taxid") or "").strip()
                if not name:
                    continue
                taxa[(name, taxid)][sample_id] = row.get(abundance_column, "0")
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = ["name", "taxonomy_id", *sample_ids]
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for (name, taxid), values in sorted(taxa.items()):
            writer.writerow(
                {
                    "name": name,
                    "taxonomy_id": taxid,
                    **{sid: values.get(sid, "0") for sid in sample_ids},
                }
            )
    return destination


def taxonomy_diversity(
    table: str | Path, alpha_output: str | Path, beta_output: str | Path
) -> tuple[Path, Path]:
    """Compute Shannon alpha diversity and Bray-Curtis dissimilarity."""
    with Path(table).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    sample_ids = list(rows[0].keys())[2:] if rows else []
    vectors = {sample: [float(row.get(sample) or 0) for row in rows] for sample in sample_ids}
    alpha = Path(alpha_output)
    alpha.parent.mkdir(parents=True, exist_ok=True)
    with alpha.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["sample_id", "observed_taxa", "shannon"], delimiter="\t"
        )
        writer.writeheader()
        for sample, values in vectors.items():
            total = sum(values)
            proportions = [value / total for value in values if value > 0 and total > 0]
            writer.writerow(
                {
                    "sample_id": sample,
                    "observed_taxa": len(proportions),
                    "shannon": -sum(p * math.log(p) for p in proportions),
                }
            )
    beta = Path(beta_output)
    with beta.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["sample_a", "sample_b", "bray_curtis"], delimiter="\t"
        )
        writer.writeheader()
        for left_index, left in enumerate(sample_ids):
            for right in sample_ids[left_index + 1 :]:
                denominator = sum(vectors[left]) + sum(vectors[right])
                distance = (
                    sum(abs(a - b) for a, b in zip(vectors[left], vectors[right])) / denominator
                    if denominator
                    else 0.0
                )
                writer.writerow({"sample_a": left, "sample_b": right, "bray_curtis": distance})
    return alpha, beta


class ReportCollector:
    """Collect P0 outputs and provenance into JSON and Markdown."""

    @staticmethod
    def collect(
        workdir: str | Path,
        samples: Sequence[SampleRecord],
        *,
        commands: Sequence[Mapping[str, Any]] = (),
        versions: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Path]:
        root = Path(workdir)
        result = root / "result"
        expected = {
            "fastp_qc": result / "qc" / "fastp.txt",
            "host_removal": result / "qc" / "sum.txt",
            "phylum": result / "kraken2" / "bracken.P.txt",
            "genus": result / "kraken2" / "bracken.G.txt",
            "species": result / "kraken2" / "bracken.S.txt",
            "alpha": result / "kraken2" / "alpha.txt",
            "beta": result / "kraken2" / "beta.txt",
        }
        manifest = {
            "plugin": "easymetagenome",
            "sample_count": len(samples),
            "samples": [sample.as_dict() for sample in samples],
            "artifacts": {key: str(path) for key, path in expected.items() if path.exists()},
            "missing_artifacts": [key for key, path in expected.items() if not path.exists()],
            "commands": list(commands),
            "versions": list(versions),
        }
        result.mkdir(parents=True, exist_ok=True)
        manifest_path = result / "report_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        report_path = result / "report.md"
        sections = [
            "# EasyMetagenome P0 Report",
            f"\nInput samples: {len(samples)}",
            "\n## Read quality control\n\nSee `qc/fastp.txt` for raw and clean read statistics.",
            "\n## Host removal\n\nSee `qc/sum.txt` for post-decontamination read counts.",
            "\n## Kraken2 / Bracken taxonomy\n\n"
            "Phylum, genus, and species abundance tables are under `kraken2/`.",
            "\n## Alpha / Beta diversity\n\nSee `kraken2/alpha.txt` and `kraken2/beta.txt`.",
            "\n## Software versions and commands\n",
        ]
        sections.extend(
            f"- `{row.get('tool', 'unknown')}`: `{row.get('version', '')}`" for row in versions
        )
        sections.extend(
            f"- `{row.get('node', 'node')}`: `{row.get('command', '')}`" for row in commands
        )
        sections.append("\n## Result table previews\n")
        for label, path in expected.items():
            if not path.is_file():
                sections.append(f"### {label}\n\nMissing: `{path}`")
                continue
            preview = path.read_text(encoding="utf-8", errors="replace").splitlines()[:10]
            sections.append(f"### {label}\n\n```text\n" + "\n".join(preview) + "\n```")
        report_path.write_text("\n".join(sections) + "\n", encoding="utf-8")
        return {"report_manifest": manifest_path, "markdown_report": report_path}
