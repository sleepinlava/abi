from pathlib import Path

from abi.autoplasm.parsers import parse_standard_outputs, supports_standard_parsing
from abi.autoplasm.standard_tables import (
    append_standard_rows,
    read_standard_table,
    write_consensus_table,
)

FIXTURES = Path("tests/fixtures/tool_outputs")


def test_core_parsers_emit_standard_rows(tmp_path):
    assert supports_standard_parsing("genomad")

    genomad = parse_standard_outputs("genomad", FIXTURES / "genomad", "S1")
    assert genomad["plasmid_predictions"][0]["contig_id"] == "contig_1"
    assert genomad["plasmid_predictions"][0]["confidence"] == "high"
    assert genomad["plasmid_predictions"][0]["evidence_level"] == "primary"

    mob = parse_standard_outputs("mob_suite", FIXTURES / "mob_suite", "S1")
    assert mob["plasmid_predictions"][0]["tool"] == "mob_suite"
    assert mob["plasmid_predictions"][0]["evidence_level"] == "supporting"
    assert mob["host_predictions"][0]["host_taxon"] == "Enterobacteriaceae"

    plasmidfinder = parse_standard_outputs("plasmidfinder", FIXTURES / "plasmidfinder", "S1")
    assert plasmidfinder["plasmid_predictions"][0]["evidence_level"] == "supporting"
    assert plasmidfinder["annotations"][0]["category"] == "replicon"

    abricate = parse_standard_outputs("abricate", FIXTURES / "abricate", "S1")
    assert abricate["annotations"][0]["category"] == "ARG"

    amrfinder = parse_standard_outputs("amrfinderplus", FIXTURES / "amrfinderplus", "S1")
    assert amrfinder["annotations"][0]["gene"] == "tetA"

    bakta = parse_standard_outputs("bakta", FIXTURES / "bakta", "S1")
    assert bakta["annotations"][0]["product"] == "replication initiation protein"

    host = parse_standard_outputs("plasmidhostfinder", FIXTURES / "plasmidhostfinder", "S1")
    assert host["host_predictions"][0]["host_taxon"] == "Escherichia coli"

    metaphlan = parse_standard_outputs("metaphlan", FIXTURES / "metaphlan", "S1")
    assert metaphlan["host_predictions"][0]["host_taxon"] == "Escherichia coli"
    assert metaphlan["host_predictions"][0]["contig_id"] == ""
    assert metaphlan["host_predictions"][0]["method"] == "taxonomy_abundance"

    coverm = parse_standard_outputs("coverm", FIXTURES / "coverm", "S1")
    assert coverm["abundance"][0]["coverage"] == "42.5"

    fastp = parse_standard_outputs("fastp", FIXTURES / "fastp", "S1")
    assert fastp["qc_summary"][0]["tool"] == "fastp"
    assert any(row["metric"] == "after_filtering.total_reads" for row in fastp["qc_summary"])

    fastqc = parse_standard_outputs("fastqc", FIXTURES / "fastqc", "S1")
    assert any(row["metric"] == "Total Sequences" for row in fastqc["qc_summary"])

    multiqc = parse_standard_outputs("multiqc", FIXTURES / "multiqc", "S1")
    assert multiqc["qc_summary"][0]["tool"] == "multiqc"

    nanoplot = parse_standard_outputs("nanoplot", FIXTURES / "nanoplot", "S1")
    assert any(row["metric"] == "number_of_reads" for row in nanoplot["qc_summary"])

    filtlong = parse_standard_outputs("filtlong", FIXTURES / "filtlong", "S1")
    assert any(row["metric"] == "Output reads" for row in filtlong["qc_summary"])

    hifiadapterfilt = parse_standard_outputs(
        "hifiadapterfilt",
        FIXTURES / "hifiadapterfilt",
        "HIFI1",
    )
    assert any(row["metric"] == "Adapter reads removed" for row in hifiadapterfilt["qc_summary"])

    megahit = parse_standard_outputs("megahit", FIXTURES / "megahit", "S1")
    assert any(row["metric"] == "n50" for row in megahit["assembly_summary"])

    metaflye = parse_standard_outputs("metaflye", FIXTURES / "metaflye", "S1")
    assert any(row["metric"] == "n50" for row in metaflye["assembly_summary"])

    hifiasm = parse_standard_outputs("hifiasm_meta", FIXTURES / "hifiasm_meta", "HIFI1")
    assert any(row["metric"] == "n50" for row in hifiasm["assembly_summary"])

    opera_ms = parse_standard_outputs("opera_ms", FIXTURES / "opera_ms", "HYB1")
    assert any(row["metric"] == "n50" for row in opera_ms["assembly_summary"])


def test_registered_new_tool_parsers_emit_standard_rows():
    plasme = parse_standard_outputs("plasme", FIXTURES / "plasme", "S1")
    assert plasme["plasmid_predictions"][0]["tool"] == "plasme"

    plasx = parse_standard_outputs("plasx", FIXTURES / "plasx", "S1")
    assert plasx["plasmid_predictions"][0]["contig_id"] == "contig_2"

    copla = parse_standard_outputs("copla", FIXTURES / "copla", "S1")
    assert copla["plasmid_typing"][0]["typing_scheme"] == "COPLA"

    gplas2 = parse_standard_outputs("gplas2", FIXTURES / "gplas2", "S1")
    assert gplas2["plasmid_bins"][0]["bin_id"] == "bin_1"
    assert gplas2["bin_to_contig"][0]["contig_id"] == "contig_1"

    plasmaag = parse_standard_outputs("plasmaag", FIXTURES / "plasmaag", "S1")
    assert plasmaag["bin_to_contig"][0]["tool"] == "plasmaag"

    kraken2 = parse_standard_outputs("kraken2", FIXTURES / "kraken2", "S1")
    assert kraken2["host_predictions"][0]["host_taxon"] == "Escherichia coli"

    blast = parse_standard_outputs("blast", FIXTURES / "blast", "S1")
    assert blast["comparative_hits"][0]["subject_id"] == "ref_plasmid_A"

    mmseqs2 = parse_standard_outputs("mmseqs2", FIXTURES / "mmseqs2", "S1")
    assert mmseqs2["comparative_hits"][0]["tool"] == "mmseqs2"

    mummer = parse_standard_outputs("mummer", FIXTURES / "mummer", "S1")
    assert mummer["comparative_hits"][0]["identity"] == "94.0"

    clinker = parse_standard_outputs("clinker", FIXTURES / "clinker", "S1")
    assert clinker["visualization_outputs"][0]["tool"] == "clinker"

    fastspar = parse_standard_outputs("fastspar", FIXTURES / "fastspar", "")
    assert fastspar["network_edges"][0]["method"] == "fastspar"
    assert fastspar["network_nodes"][0]["node_id"] == "contig_1"


def test_bakta_parser_reads_gff_features(tmp_path):
    output_dir = tmp_path / "bakta"
    output_dir.mkdir()
    (output_dir / "S1.gff3").write_text(
        "\n".join(
            [
                "##gff-version 3",
                (
                    "contig_gff\tBakta\tCDS\t10\t90\t.\t+\t0\t"
                    "ID=cds-1;gene=repB;product=replication%20protein;Dbxref=RFAM:RF00001"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rows = parse_standard_outputs("bakta", output_dir, "S1")["annotations"]

    assert rows[0]["contig_id"] == "contig_gff"
    assert rows[0]["gene"] == "repB"
    assert rows[0]["product"] == "replication protein"
    assert rows[0]["evidence"] == "RFAM:RF00001"


def test_standard_table_consensus_uses_configured_strategy(tmp_path):
    tables = tmp_path / "tables"
    append_standard_rows(
        tables,
        parse_standard_outputs("genomad", FIXTURES / "genomad", "S1"),
    )
    append_standard_rows(
        tables,
        parse_standard_outputs("mob_suite", FIXTURES / "mob_suite", "S1"),
    )
    write_consensus_table(
        tables,
        strategy="intersection",
        detection_tools=["genomad", "mob_suite"],
    )

    consensus = read_standard_table(tables, "plasmid_consensus")
    by_contig = {row["contig_id"]: row for row in consensus}
    assert by_contig["contig_1"]["final_plasmid_call"] == "True"
    assert by_contig["contig_1"]["support_tools"] == "genomad,mob_suite"
    assert by_contig["contig_2"]["final_plasmid_call"] == "False"
