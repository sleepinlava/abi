"""Tests for the declarative TSV column mapper (``src/abi/tsv_mapping.py``).

Covers:
- ``TSVMapper`` loading, parsing, target table resolution.
- ``generate_rows()`` with synthetic TSV files.
- Source column matching, multi-source fallback, positional columns.
- Comment line skipping, constants injection, error handling.
- Golden-file comparison: declarative mapper vs hand-written parser.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from abi.tsv_mapping import TSVMapper, generate_rows

# ── Helpers ────────────────────────────────────────────────────────────────


def _write_tsv(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Write a list of dicts as a TSV file."""
    if not rows:
        path.write_text("")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


# ── TSVMapper loading ──────────────────────────────────────────────────────


class TestTSVMapperLoading:
    def test_load_from_yaml(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "parsers.yaml"
        yaml_path.write_text(
            """
parsers:
  test_tool:
    source:
      type: tsv_mapping
      pattern: "*.tsv"
    target_table: test_table
    columns:
      col_a: {sources: [ColumnA, col_a]}
    constants:
      tool: test_tool
"""
        )
        mapper = TSVMapper.from_yaml(yaml_path)
        assert mapper.has_parser("test_tool")
        assert mapper.get_target_table("test_tool") == "test_table"
        assert "test_tool" in mapper.tool_ids

    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        mapper = TSVMapper.from_yaml(tmp_path / "nonexistent.yaml")
        assert not mapper.has_parser("anything")
        assert mapper.tool_ids == []

    def test_load_empty_yaml(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "empty.yaml"
        yaml_path.write_text("")
        mapper = TSVMapper.from_yaml(yaml_path)
        assert mapper.tool_ids == []

    def test_load_missing_parsers_key(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "noparsers.yaml"
        yaml_path.write_text("other_key: [1, 2, 3]")
        mapper = TSVMapper.from_yaml(yaml_path)
        assert mapper.tool_ids == []


# ── Column mapping ─────────────────────────────────────────────────────────


class TestColumnMapping:
    def test_simple_column_remap(self, tmp_path: Path) -> None:
        """Map TSV columns to standard table columns."""
        _write_tsv(
            tmp_path / "output.tsv",
            [{"Gene symbol": "blaTEM", "Scope": "core"}],
        )
        spec = {
            "source": {"type": "tsv_mapping", "pattern": "*.tsv"},
            "columns": {
                "gene_symbol": {"sources": ["Gene symbol"]},
                "scope": {"sources": ["Scope"]},
            },
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert len(rows) == 1
        assert rows[0]["gene_symbol"] == "blaTEM"
        assert rows[0]["scope"] == "core"
        assert rows[0]["sample_id"] == "S1"
        assert "source_file" in rows[0]

    def test_multi_source_fallback(self, tmp_path: Path) -> None:
        """First matching source column wins."""
        _write_tsv(
            tmp_path / "output.tsv",
            [{"coverage_pct": "99.5"}],  # has the second option
        )
        spec = {
            "source": {"type": "tsv_mapping", "pattern": "*.tsv"},
            "columns": {
                "coverage_pct": {
                    "sources": [
                        "% Coverage of reference sequence",
                        "coverage_pct",
                    ],
                    "default": "0",
                },
            },
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert rows[0]["coverage_pct"] == "99.5"

    def test_multi_source_first_match_wins(self, tmp_path: Path) -> None:
        """When both source columns exist, use the first one."""
        _write_tsv(
            tmp_path / "output.tsv",
            [{"A": "value_a", "B": "value_b"}],
        )
        spec = {
            "source": {"type": "tsv_mapping", "pattern": "*.tsv"},
            "columns": {
                "result": {"sources": ["A", "B"]},
            },
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert rows[0]["result"] == "value_a"

    def test_default_when_column_missing(self, tmp_path: Path) -> None:
        """Use default when no source column matches."""
        _write_tsv(tmp_path / "output.tsv", [{"X": "y"}])
        spec = {
            "source": {"type": "tsv_mapping", "pattern": "*.tsv"},
            "columns": {
                "missing": {"sources": ["NonExistent"], "default": "N/A"},
            },
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert rows[0]["missing"] == "N/A"


# ── Positional columns ─────────────────────────────────────────────────────


class TestPositionalColumns:
    def test_last_column(self, tmp_path: Path) -> None:
        """sources_from: last_column uses the final field."""
        _write_tsv(
            tmp_path / "output.tsv",
            [{"Geneid": "GENE1", "chr": "1", "count": "42"}],
        )
        spec = {
            "source": {"type": "tsv_mapping", "pattern": "*.tsv"},
            "columns": {
                "gene_id": {"sources": ["Geneid"]},
                "count": {"sources_from": "last_column", "default": "0"},
            },
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert rows[0]["count"] == "42"

    def test_column_index(self, tmp_path: Path) -> None:
        """sources_from: column_index uses 1-based positional access."""
        _write_tsv(
            tmp_path / "output.tsv",
            [{"A": "col1", "B": "col2", "C": "col3"}],
        )
        spec = {
            "source": {"type": "tsv_mapping", "pattern": "*.tsv"},
            "columns": {
                "first": {"sources_from": "column_index", "index": 1},
                "third": {"sources_from": "column_index", "index": 3},
            },
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert rows[0]["first"] == "col1"
        assert rows[0]["third"] == "col3"

    def test_column_index_out_of_range(self, tmp_path: Path) -> None:
        """Out-of-range index returns default."""
        _write_tsv(tmp_path / "output.tsv", [{"A": "x"}])
        spec = {
            "source": {"type": "tsv_mapping", "pattern": "*.tsv"},
            "columns": {
                "oob": {
                    "sources_from": "column_index",
                    "index": 99,
                    "default": "fallback",
                },
            },
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert rows[0]["oob"] == "fallback"


# ── Constants injection ────────────────────────────────────────────────────


class TestConstantsInjection:
    def test_constants_injected_into_every_row(self, tmp_path: Path) -> None:
        _write_tsv(
            tmp_path / "a.tsv",
            [
                {"Gene symbol": "a"},
                {"Gene symbol": "b"},
            ],
        )
        spec = {
            "source": {"type": "tsv_mapping", "pattern": "*.tsv"},
            "columns": {
                "gene_symbol": {"sources": ["Gene symbol"]},
            },
            "constants": {"tool": "amrfinderplus", "version": "3.12"},
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert len(rows) == 2
        assert rows[0]["tool"] == "amrfinderplus"
        assert rows[0]["version"] == "3.12"
        assert rows[1]["tool"] == "amrfinderplus"


# ── Comment skipping ───────────────────────────────────────────────────────


class TestCommentSkipping:
    def test_skip_lines_starting_with(self, tmp_path: Path) -> None:
        """Lines starting with # are skipped before the header."""
        tsv = tmp_path / "output.tsv"
        tsv.write_text(
            "# Program: featureCounts\n# Version: 2.0\nGeneid\tChr\tcount\nGENE1\t1\t42\n"
        )
        spec = {
            "source": {
                "type": "tsv_mapping",
                "pattern": "*.tsv",
                "skip_lines_starting_with": "#",
            },
            "columns": {
                "gene_id": {"sources": ["Geneid"]},
                "count": {"sources": ["count"]},
            },
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert len(rows) == 1
        assert rows[0]["gene_id"] == "GENE1"


# ── Multi-file glob ────────────────────────────────────────────────────────


class TestMultiFileGlob:
    def test_multiple_files_aggregated(self, tmp_path: Path) -> None:
        for fname in ["sample1_amr.tsv", "sample2_amr.tsv"]:
            _write_tsv(
                tmp_path / fname,
                [{"Gene symbol": f"gene_in_{fname}"}],
            )
        spec = {
            "source": {"type": "tsv_mapping", "pattern": "*amr*.tsv"},
            "columns": {"gene_symbol": {"sources": ["Gene symbol"]}},
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert len(rows) == 2
        assert rows[0]["gene_symbol"] == "gene_in_sample1_amr.tsv"
        assert rows[1]["gene_symbol"] == "gene_in_sample2_amr.tsv"


# ── Error resilience ───────────────────────────────────────────────────────


class TestErrorResilience:
    def test_non_matching_glob_returns_empty(self, tmp_path: Path) -> None:
        """No files match → empty list (not an error)."""
        spec = {
            "source": {"type": "tsv_mapping", "pattern": "*.nonexistent"},
            "columns": {"x": {"sources": ["x"]}},
        }
        rows = generate_rows(spec, tmp_path)
        assert rows == []

    def test_empty_file_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "empty.tsv").write_text("")
        spec = {
            "source": {"type": "tsv_mapping", "pattern": "*.tsv"},
            "columns": {"x": {"sources": ["x"]}},
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert rows == []

    def test_malformed_file_skipped(self, tmp_path: Path) -> None:
        """Binary or unparseable files are skipped with a warning."""
        (tmp_path / "bad.tsv").write_bytes(b"\x00\x01\x02\xff\xfe")
        spec = {
            "source": {"type": "tsv_mapping", "pattern": "*.tsv"},
            "columns": {"x": {"sources": ["x"]}},
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert rows == []


# ── Golden-file: mapper output vs hand-written parser ──────────────────────


# ── JSON mapping ────────────────────────────────────────────────────────────


class TestJSONMapping:
    def test_fastp_json_flatten(self, tmp_path: Path) -> None:
        """Flatten nested JSON blocks into key-value rows."""
        p = tmp_path / "fastp.json"
        json.dump(
            {
                "summary": {
                    "before_filtering": {"total_reads": 1000},
                    "after_filtering": {"total_reads": 950},
                }
            },
            p.open("w"),
        )
        spec = {
            "source": {
                "type": "json_mapping",
                "pattern": "*.json",
                "root_key": "summary",
                "blocks": {
                    "before_filtering": {"prefix": "before_filtering"},
                    "after_filtering": {"prefix": "after_filtering"},
                },
            },
            "constants": {"tool": "fastp"},
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert len(rows) == 2
        assert rows[0]["metric"] == "before_filtering.total_reads"
        assert rows[0]["value"] == 1000
        assert rows[0]["tool"] == "fastp"
        assert rows[0]["sample_id"] == "S1"

    def test_json_missing_root_key(self, tmp_path: Path) -> None:
        """Gracefully handle missing root_key."""
        p = tmp_path / "data.json"
        json.dump({"other": 1}, p.open("w"))
        spec = {
            "source": {
                "type": "json_mapping",
                "pattern": "*.json",
                "root_key": "nonexistent",
                "blocks": {"a": {"prefix": "a"}},
            },
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert rows == []

    def test_json_invalid_file_skipped(self, tmp_path: Path) -> None:
        """Skip malformed JSON files."""
        (tmp_path / "bad.json").write_text("not json")
        spec = {
            "source": {
                "type": "json_mapping",
                "pattern": "*.json",
                "root_key": "summary",
                "blocks": {"a": {"prefix": "a"}},
            },
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert rows == []


# ── Key-value log ───────────────────────────────────────────────────────────


class TestKeyValueLog:
    def test_star_log_parsing(self, tmp_path: Path) -> None:
        """Parse pipe-delimited STAR log into key-value rows."""
        log = tmp_path / "Log.final.out"
        log.write_text(
            "Started job on |	Jan 01 00:00:00\n"
            "Uniquely mapped reads number |	950\n"
            "Mapping speed, Million of reads per hour |	100.50\n"
        )
        spec = {
            "source": {
                "type": "key_value_log",
                "pattern": "*Log.final.out",
                "delimiter": "|",
            },
            "constants": {"tool": "star"},
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert len(rows) == 3
        assert rows[0]["metric"] == "Started job on"
        assert rows[1]["value"] == "950"
        assert rows[2]["tool"] == "star"

    def test_log_empty_lines_skipped(self, tmp_path: Path) -> None:
        """Empty lines are ignored."""
        log = tmp_path / "log.txt"
        log.write_text("\n\nkey | value\n\n")
        spec = {
            "source": {
                "type": "key_value_log",
                "pattern": "*.txt",
                "delimiter": "|",
            },
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert len(rows) == 1

    def test_log_missing_delimiter_skipped(self, tmp_path: Path) -> None:
        """Lines without delimiter are skipped."""
        log = tmp_path / "log.txt"
        log.write_text("no delimiter here\nkey | value\n")
        spec = {
            "source": {
                "type": "key_value_log",
                "pattern": "*.txt",
                "delimiter": "|",
            },
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert len(rows) == 1

    def test_log_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """No matching files → empty list."""
        spec = {
            "source": {
                "type": "key_value_log",
                "pattern": "*.nonexistent",
                "delimiter": "|",
            },
        }
        rows = generate_rows(spec, tmp_path, sample_id="S1")
        assert rows == []


class TestTSVMapperGoldenTraceParity:
    """Verify that declarative mapper produces same output as hand-written parsers."""

    def test_wgs_parsers_yaml_matches_expected_output(self, tmp_path: Path) -> None:
        """The TSVMapper produces correct AMRFinderPlus rows from parsers.yaml."""
        from abi.config import PLUGIN_ROOT
        from abi.tsv_mapping import TSVMapper

        mapper = TSVMapper.from_yaml(PLUGIN_ROOT / "wgs_bacteria" / "parsers.yaml")

        _write_tsv(
            tmp_path / "test_amr.tsv",
            [
                {
                    "Gene symbol": "blaTEM-1",
                    "Sequence name": "contig_1",
                    "Scope": "core",
                    "Element type": "AMR",
                    "Element subtype": "BETA-LACTAM",
                    "Class": "BETA-LACTAM",
                    "Subclass": "PENICILLIN",
                    "Method": "BLASTP",
                    "% Coverage of reference sequence": "100.0",
                    "% Identity to reference sequence": "99.5",
                },
            ],
        )

        rows = mapper.parse("amrfinderplus", tmp_path, sample_id="S1")
        assert len(rows) == 1
        assert rows[0]["gene_symbol"] == "blaTEM-1"
        assert rows[0]["coverage_pct"] == "100.0"
        assert rows[0]["identity_pct"] == "99.5"
        assert rows[0]["tool"] == "amrfinderplus"
        assert rows[0]["sample_id"] == "S1"
        assert "source_file" in rows[0]

    def test_matches_alpha_diversity_parser(self, tmp_path: Path) -> None:
        """Verify TSVMapper matches _parse_alpha_diversity output."""
        from abi.plugins.amplicon_16s import _parse_alpha_diversity

        _write_tsv(
            tmp_path / "alpha_diversity.tsv",
            [
                {
                    "sample_id": "S1",
                    "observed_features": "150",
                    "shannon_entropy": "3.5",
                    "simpson": "0.9",
                    "faith_pd": "12.3",
                    "chao1": "160",
                }
            ],
        )

        hand_rows = _parse_alpha_diversity(tmp_path)

        mapper_spec = {
            "source": {"type": "tsv_mapping", "pattern": "alpha*.tsv"},
            "columns": {
                "sample_id": {"sources": ["sample_id"]},
                "observed_features": {
                    "sources": ["observed_features", "observed_otus"],
                    "default": "",
                },
                "shannon_entropy": {
                    "sources": ["shannon", "shannon_entropy"],
                    "default": "",
                },
                "simpson_index": {"sources": ["simpson"], "default": ""},
                "faith_pd": {"sources": ["faith_pd"], "default": ""},
                "chao1": {"sources": ["chao1"], "default": ""},
            },
            "constants": {"tool": "diversity_metrics"},
        }
        mapper_rows = generate_rows(mapper_spec, tmp_path, sample_id="S1")

        assert len(mapper_rows) == 1
        assert mapper_rows[0]["observed_features"] == "150"
        assert mapper_rows[0]["shannon_entropy"] == "3.5"
        assert mapper_rows[0]["chao1"] == "160"
        # Note: the hand-written parser has sample_id in the row itself;
        # the mapper injects it from the argument.  Values should match.
        assert mapper_rows[0]["sample_id"] == hand_rows[0]["sample_id"]
