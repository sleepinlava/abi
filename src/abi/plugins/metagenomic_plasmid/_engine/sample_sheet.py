"""Sample sheet parsing and validation."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, List, Mapping, Optional

from abi.plugins.metagenomic_plasmid._engine.config import PROJECT_ROOT
from abi.plugins.metagenomic_plasmid._engine.schemas import VALID_PLATFORMS, SampleContext, SampleInput, SampleSheetError

REQUIRED_COLUMNS = {"sample_id", "platform"}
SUPPORTED_COLUMNS = {
    "sample_id",
    "group",
    "platform",
    "read1",
    "read2",
    "long_reads",
    "assembly",
    "contigs",
    "technology",
    "host_reference",
    "notes",
}


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _path_exists(path_value: Optional[str]) -> bool:
    return not path_value or Path(path_value).exists()


def parse_sample_sheet(path: str | Path, check_files: bool = True) -> SampleContext:
    sample_sheet = _resolve_sample_sheet(path)
    if not sample_sheet.exists():
        raise SampleSheetError(f"Sample sheet does not exist: {sample_sheet}")

    with sample_sheet.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise SampleSheetError(f"Sample sheet is empty: {sample_sheet}")

        columns = set(reader.fieldnames)
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise SampleSheetError(f"Sample sheet missing required columns: {sorted(missing)}")

        unknown = columns - SUPPORTED_COLUMNS
        if unknown:
            raise SampleSheetError(f"Sample sheet contains unsupported columns: {sorted(unknown)}")

        samples = [
            _sample_from_row(row, row_number=index + 2, sample_sheet=sample_sheet)
            for index, row in enumerate(reader)
        ]

    if not samples:
        raise SampleSheetError("Sample sheet contains no sample rows")

    if check_files:
        validate_sample_files(samples)

    return summarize_samples(samples)


def _sample_from_row(row: Mapping[str, str], row_number: int, sample_sheet: Path) -> SampleInput:
    sample_id = _clean(row.get("sample_id"))
    if not sample_id:
        raise SampleSheetError(f"Row {row_number}: sample_id is required")

    platform = _clean(row.get("platform"))
    if platform not in VALID_PLATFORMS:
        raise SampleSheetError(
            f"Row {row_number} sample {sample_id}: platform must be one of "
            f"{sorted(VALID_PLATFORMS)}, got {platform!r}"
        )

    assembly = _clean(row.get("assembly")) or _clean(row.get("contigs"))
    sample = SampleInput(
        sample_id=sample_id,
        group=_clean(row.get("group")),
        platform=platform,
        read1=_clean(row.get("read1")),
        read2=_clean(row.get("read2")),
        long_reads=_clean(row.get("long_reads")),
        assembly=assembly,
        technology=_clean(row.get("technology")),
        host_reference=_clean(row.get("host_reference")),
        notes=_clean(row.get("notes")),
    )
    _resolve_sample_paths(sample, sample_sheet)
    validate_sample_requirements(sample, row_number=row_number)
    return sample


def _resolve_sample_sheet(path: str | Path) -> Path:
    raw_path = Path(path)
    if raw_path.is_absolute():
        return raw_path
    if raw_path.exists():
        return raw_path.resolve()
    project_path = PROJECT_ROOT / raw_path
    if project_path.exists():
        return project_path.resolve()
    return raw_path


def _resolve_sample_paths(sample: SampleInput, sample_sheet: Path) -> None:
    for attr in ("read1", "read2", "long_reads", "assembly", "host_reference"):
        value = getattr(sample, attr)
        if not value:
            continue
        resolved = _resolve_existing_input_path(value, sample_sheet.parent)
        setattr(sample, attr, str(resolved))


def _resolve_existing_input_path(value: str | Path, sheet_dir: Path) -> Path:
    raw_path = Path(value)
    if raw_path.is_absolute():
        return raw_path
    if raw_path.exists():
        return raw_path.resolve()
    for base_dir in (sheet_dir, PROJECT_ROOT):
        candidate = base_dir / raw_path
        if candidate.exists():
            return candidate.resolve()
    return raw_path


def validate_sample_requirements(sample: SampleInput, row_number: int | None = None) -> None:
    prefix = (
        f"Row {row_number} sample {sample.sample_id}"
        if row_number
        else f"Sample {sample.sample_id}"
    )
    if sample.platform == "illumina" and not sample.read1:
        raise SampleSheetError(f"{prefix}: illumina samples require read1")
    if sample.platform in {"ont", "pacbio_hifi"} and not sample.long_reads:
        raise SampleSheetError(f"{prefix}: {sample.platform} samples require long_reads")
    if sample.platform == "hybrid" and not (sample.read1 and sample.long_reads):
        raise SampleSheetError(f"{prefix}: hybrid samples require read1 and long_reads")
    if sample.platform == "assembly" and not sample.assembly:
        raise SampleSheetError(f"{prefix}: assembly samples require assembly FASTA")


def validate_sample_files(samples: Iterable[SampleInput]) -> None:
    missing: List[str] = []
    for sample in samples:
        for attr in ["read1", "read2", "long_reads", "assembly", "host_reference"]:
            value = getattr(sample, attr)
            if not _path_exists(value):
                missing.append(f"{sample.sample_id}:{attr}={value}")
    if missing:
        raise SampleSheetError("Input files do not exist: " + "; ".join(missing))


def summarize_samples(samples: List[SampleInput]) -> SampleContext:
    multi_sample = len(samples) > 1
    groups = {sample.group for sample in samples if sample.group}
    has_groups = len(groups) >= 2
    return SampleContext(
        samples=samples,
        multi_sample=multi_sample,
        has_groups=has_groups,
        enable_sample_analysis=multi_sample,
        enable_differential_abundance=multi_sample and has_groups,
    )


def single_sample_context(
    sample_id: str,
    platform: str,
    read1: Optional[str] = None,
    read2: Optional[str] = None,
    long_reads: Optional[str] = None,
    assembly: Optional[str] = None,
    group: Optional[str] = None,
    technology: Optional[str] = None,
    host_reference: Optional[str] = None,
    check_files: bool = True,
) -> SampleContext:
    sample = SampleInput(
        sample_id=sample_id,
        platform=platform,
        group=group,
        read1=read1,
        read2=read2,
        long_reads=long_reads,
        assembly=assembly,
        technology=technology,
        host_reference=host_reference,
    )
    validate_sample_requirements(sample)
    if check_files:
        validate_sample_files([sample])
    return summarize_samples([sample])
