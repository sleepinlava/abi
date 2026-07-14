"""Internal handlers for the ABI-native EasyMetagenome workflows."""

from __future__ import annotations

import csv
import gzip
import json
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from abi.internal import FunctionInternalHandler, InternalHandlerContext, InternalHandlerResult

from .adapters import ManifestValidator, merge_bracken, parse_fastp_json, taxonomy_diversity
from .report_manifest import write_report_manifest


def _paths(value: Any) -> list[Path]:
    if isinstance(value, (list, tuple)):
        return [Path(str(item)) for item in value if item]
    return [Path(str(value))] if value else []


def _write_rows(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["sample_id"]
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return destination


def validate_manifest_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    del context
    manifest = config["input"]["sample_sheet"]
    records = ManifestValidator.validate(manifest)
    _write_rows(step.outputs["normalized_manifest"], [record.as_dict() for record in records])
    report = {
        "status": "pass",
        "sample_count": len(records),
        "manifest": str(Path(manifest).resolve()),
    }
    report_path = Path(step.outputs["validation_report"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return InternalHandlerResult(message=f"Validated {len(records)} samples")


def fastp_summary_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    del config, context
    rows = parse_fastp_json(_paths(step.inputs.get("fastp_json")))
    _write_rows(step.outputs["summary_table"], rows)
    return InternalHandlerResult(message=f"Summarized fastp for {len(rows)} samples")


def _fastq_records(path: Path) -> int:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle) // 4


def kneaddata_summary_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    del config, context
    rows = [
        {
            "sample_id": path.name.split("_1_kneaddata", 1)[0],
            "dehost_read_pairs": _fastq_records(path),
        }
        for path in _paths(step.inputs.get("dehost_reads"))
    ]
    _write_rows(step.outputs["summary_table"], rows)
    return InternalHandlerResult(
        message=f"Summarized KneadData for {len(rows)} samples",
        tables={"host_removal_summary": rows},
    )


def bracken_merge_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    del config, context
    for level, input_key, output_key in (
        ("P", "phylum_tables", "phylum_table"),
        ("G", "genus_tables", "genus_table"),
        ("S", "species_tables", "species_table"),
    ):
        files = _paths(step.inputs.get(input_key))
        if not files:
            raise ValueError(f"No Bracken {level} tables were provided")
        merge_bracken(files, step.outputs[output_key])
    return InternalHandlerResult(message="Merged Bracken P/G/S tables")


def _filter_prevalence(source: Path, destination: Path, threshold: float) -> None:
    with source.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    fields = list(rows[0]) if rows else ["name", "taxonomy_id"]
    sample_fields = fields[2:]
    retained = [
        row
        for row in rows
        if sample_fields
        and sum(float(row.get(field) or 0) > 0 for field in sample_fields) / len(sample_fields)
        >= threshold
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(retained)


def taxonomy_filter_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    del config, context
    threshold = float(step.params.get("prevalence", 0.2))
    for source_key, output_key in (
        ("phylum_table", "filtered_phylum"),
        ("genus_table", "filtered_genus"),
        ("species_table", "filtered_species"),
    ):
        _filter_prevalence(Path(step.inputs[source_key]), Path(step.outputs[output_key]), threshold)
    return InternalHandlerResult(message="Filtered taxonomy tables by prevalence")


def taxonomy_diversity_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    del config, context
    alpha, beta = taxonomy_diversity(
        step.inputs["species_table"],
        step.outputs["alpha_table"],
        step.outputs["beta_table"],
    )
    return InternalHandlerResult(
        message="Computed Shannon and Bray-Curtis diversity",
        artifacts={"alpha": alpha, "beta": beta},
    )


def report_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    manifest = ManifestValidator.validate(config["input"]["sample_sheet"], check_files=False)
    report_path = Path(step.outputs["report_markdown"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    inputs = {
        key: Path(str(value))
        for key, value in step.inputs.items()
        if isinstance(value, (str, Path))
    }
    lines = [
        "# EasyMetagenome ABI Report",
        "",
        f"Input samples: {len(manifest)}",
        "",
        "## Result tables",
        "",
    ]
    for name, path in sorted(inputs.items()):
        lines.append(f"- {name}: `{path}`")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest_path = write_report_manifest(
        step.outputs["report_manifest"],
        workflow="p0_taxonomy",
        sample_count=len(manifest),
        artifacts=inputs,
        report=report_path,
        tables_dir=context.tables_dir,
        table_names=("qc_summary", "host_removal_summary", "taxonomy_abundance"),
    )
    return InternalHandlerResult(
        message="EasyMetagenome report generated",
        artifacts={"report": report_path, "manifest": manifest_path},
    )


def concat_reads_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    """Concatenate paired gzip streams into one valid HUMAnN input stream."""
    del config, context
    destination = Path(step.outputs["merged_reads"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output_handle:
        for key in ("dehost_read1", "dehost_read2"):
            with Path(step.inputs[key]).open("rb") as input_handle:
                shutil.copyfileobj(input_handle, output_handle)
    return InternalHandlerResult(
        message="Concatenated paired host-filtered reads",
        artifacts={"merged_reads": destination},
    )


def _read_humann_table(path: Path, feature_type: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header: list[str] | None = None
        for values in reader:
            if not values:
                continue
            if values[0].startswith("#"):
                if len(values) > 1:
                    header = values
                continue
            if header is None:
                continue
            feature_id = values[0]
            for sample_id, value in zip(header[1:], values[1:]):
                rows.append(
                    {
                        "sample_id": sample_id.rsplit("-RPKs", 1)[0],
                        "feature_type": feature_type,
                        "feature_id": feature_id,
                        "value": value,
                        "stratified": "|" in feature_id,
                        "source_file": str(path),
                    }
                )
    return rows


def functional_report_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    del config, context
    sources = {
        "gene_family": Path(step.inputs["gene_families"]),
        "ko": Path(step.inputs["ko_table"]),
        "pathway": Path(step.inputs["pathway_table"]),
    }
    rows = [
        row
        for feature_type, path in sources.items()
        for row in _read_humann_table(path, feature_type)
    ]
    report_path = Path(step.outputs["report_markdown"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "# EasyMetagenome HUMAnN4 Functional Report\n\n"
        f"Normalized feature observations: {len(rows)}\n\n"
        + "\n".join(f"- {name}: `{path}`" for name, path in sources.items())
        + "\n",
        encoding="utf-8",
    )
    return InternalHandlerResult(
        message=f"Collected {len(rows)} HUMAnN feature observations",
        artifacts={"report": report_path},
    )


def publish_functional_report_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    samples = ManifestValidator.validate(config["input"]["sample_sheet"], check_files=False)
    sources = {
        "gene_family": Path(step.inputs["gene_families"]),
        "ko": Path(step.inputs["ko_table"]),
        "pathway": Path(step.inputs["pathway_table"]),
    }
    feature_observations = sum(
        len(_read_humann_table(path, feature_type)) for feature_type, path in sources.items()
    )
    manifest_path = write_report_manifest(
        step.outputs["report_manifest"],
        workflow="p1_humann4",
        sample_count=len(samples),
        artifacts=sources,
        report=step.inputs["report_markdown"],
        tables_dir=context.tables_dir,
        table_names=("functional_abundance",),
        extra={"feature_observations": feature_observations},
    )
    return InternalHandlerResult(
        message="Published EasyMetagenome functional report manifest",
        artifacts={"manifest": manifest_path},
    )


def handlers() -> dict[str, FunctionInternalHandler]:
    return {
        "easymetagenome.validate_manifest": FunctionInternalHandler(
            "easymetagenome.validate_manifest", validate_manifest_handler, "driver"
        ),
        "easymetagenome.fastp_summary": FunctionInternalHandler(
            "easymetagenome.fastp_summary", fastp_summary_handler
        ),
        "easymetagenome.kneaddata_summary": FunctionInternalHandler(
            "easymetagenome.kneaddata_summary", kneaddata_summary_handler
        ),
        "easymetagenome.bracken_merge": FunctionInternalHandler(
            "easymetagenome.bracken_merge", bracken_merge_handler
        ),
        "easymetagenome.taxonomy_filter": FunctionInternalHandler(
            "easymetagenome.taxonomy_filter", taxonomy_filter_handler
        ),
        "easymetagenome.taxonomy_diversity": FunctionInternalHandler(
            "easymetagenome.taxonomy_diversity", taxonomy_diversity_handler
        ),
        "easymetagenome.report": FunctionInternalHandler("easymetagenome.report", report_handler),
        "easymetagenome.concat_reads": FunctionInternalHandler(
            "easymetagenome.concat_reads", concat_reads_handler
        ),
        "easymetagenome.functional_report": FunctionInternalHandler(
            "easymetagenome.functional_report", functional_report_handler
        ),
        "easymetagenome.publish_functional_report": FunctionInternalHandler(
            "easymetagenome.publish_functional_report", publish_functional_report_handler
        ),
    }
