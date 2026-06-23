from pathlib import Path

from abi.autoplasm.parsers import parse_standard_outputs, supports_standard_parsing
from abi.autoplasm.standard_tables import (
    append_standard_rows,
    read_standard_table,
    write_consensus_table,
)
from abi.plugins import get_plugin

FIXTURES = Path("tests/fixtures/tool_outputs")


def test_every_registered_plasmid_tool_has_a_standard_parser():
    registry = get_plugin("metagenomic_plasmid").registry()

    assert all(supports_standard_parsing(tool_id) for tool_id in registry.ids())


def test_alignment_assembly_annotation_binning_and_artifact_parsers(tmp_path):
    alignment = tmp_path / "alignment"
    alignment.mkdir()
    (alignment / "S1.sam").write_text(
        "@HD\tVN:1.6\n"
        "r1\t0\tcontig_1\t1\t60\t4M\t*\t0\t0\tACGT\tIIII\n"
        "r2\t4\t*\t0\t0\t*\t*\t0\t0\tTGCA\tIIII\n",
        encoding="utf-8",
    )
    alignment_rows = parse_standard_outputs("bowtie2", alignment, "S1")["alignment_summary"]
    assert alignment_rows[0]["record_count"] == 2
    assert alignment_rows[0]["mapped_records"] == 1
    assert alignment_rows[0]["unmapped_records"] == 1

    assembly = tmp_path / "assembly"
    assembly.mkdir()
    (assembly / "contigs.fasta").write_text(">c1\nACGT\n>c2\nACGTAC\n", encoding="utf-8")
    assembly_rows = parse_standard_outputs("metaspades", assembly, "S1")["assembly_summary"]
    assert next(row for row in assembly_rows if row["metric"] == "contig_count")["value"] == 2

    annotation = tmp_path / "annotation"
    annotation.mkdir()
    (annotation / "genes.gff").write_text(
        "##gff-version 3\nc1\tProdigal\tCDS\t1\t4\t.\t+\t0\tID=gene1;product=enzyme\n",
        encoding="utf-8",
    )
    annotation_rows = parse_standard_outputs("prodigal", annotation, "S1")["annotations"]
    assert annotation_rows[0]["gene"] == "gene1"

    bins = tmp_path / "bins"
    bins.mkdir()
    (bins / "bin.1.fa").write_text(">c1\nACGT\n>c2\nACGTAC\n", encoding="utf-8")
    bin_rows = parse_standard_outputs("metabat2", bins, "S1")
    assert bin_rows["plasmid_bins"][0]["contig_count"] == 2
    assert len(bin_rows["bin_to_contig"]) == 2

    quality = tmp_path / "quality"
    quality.mkdir()
    (quality / "quality_report.tsv").write_text(
        "Name\tCompleteness\tContamination\nBin_1\t95.0\t1.2\n", encoding="utf-8"
    )
    quality_rows = parse_standard_outputs("checkm2", quality, "S1")["mag_quality"]
    assert quality_rows[0]["completeness"] == "95.0"

    visual = tmp_path / "visual"
    visual.mkdir()
    (visual / "network.html").write_text("<html></html>\n", encoding="utf-8")
    visual_rows = parse_standard_outputs("pyvis", visual, "")["visualization_outputs"]
    assert visual_rows[0]["output_type"] == "html"


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
    assert mob["plasmid_typing"][0]["typing_scheme"] == "MOB-typer"

    plasmidfinder = parse_standard_outputs("plasmidfinder", FIXTURES / "plasmidfinder", "S1")
    assert plasmidfinder["plasmid_predictions"][0]["evidence_level"] == "supporting"
    assert plasmidfinder["annotations"][0]["category"] == "replicon"
    assert plasmidfinder["plasmid_typing"][0]["typing_scheme"] == "PlasmidFinder"

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


def test_mmseqs2_parser_reads_cross_sample_cluster_membership(tmp_path):
    output_dir = tmp_path / "mmseqs2"
    output_dir.mkdir()
    (output_dir / "plasmid_catalog_cluster.tsv").write_text(
        "S1|rep_1\tS1|rep_1\nS1|rep_1\tS2|member_2\n",
        encoding="utf-8",
    )

    rows = parse_standard_outputs("mmseqs2", output_dir, "")["plasmid_catalog"]

    assert rows[0]["representative_id"] == "S1|rep_1"
    assert rows[1]["member_id"] == "S2|member_2"
    assert rows[1]["sample_id"] == "S2"


def test_deseq2_plasmid_parser_reads_effects_and_fdr(tmp_path):
    output_dir = tmp_path / "deseq2"
    output_dir.mkdir()
    (output_dir / "differential_plasmids.tsv").write_text(
        "plasmid_id\tgroup_a\tgroup_b\tlog2_fold_change\tp_value\tq_value\tmethod\twarnings\n"
        "p1\tcase\tcontrol\t2.5\t0.001\t0.01\tDESeq2\t\n",
        encoding="utf-8",
    )

    rows = parse_standard_outputs("deseq2_plasmid", output_dir, "")["differential_plasmids"]

    assert rows[0]["plasmid_id"] == "p1"
    assert rows[0]["q_value"] == "0.01"


def test_mobile_element_parsers_populate_normalized_annotations(tmp_path):
    isescan_dir = tmp_path / "isescan"
    integron_dir = tmp_path / "integron"
    isescan_dir.mkdir()
    integron_dir.mkdir()
    (isescan_dir / "hits.gff").write_text(
        "##gff-version 3\ncontig_1\tISEScan\tinsertion_sequence\t10\t100\t.\t+\t.\t"
        "ID=IS1;family=IS3\n",
        encoding="utf-8",
    )
    (integron_dir / "hits.gff").write_text(
        "##gff-version 3\ncontig_2\tIntegronFinder\tintegron\t20\t200\t.\t-\t.\t"
        "ID=integron_1;complete=true\n",
        encoding="utf-8",
    )

    is_rows = parse_standard_outputs("isescan", isescan_dir, "S1")["annotations"]
    integron_rows = parse_standard_outputs("integronfinder", integron_dir, "S1")["annotations"]

    assert is_rows[0]["category"] == "IS"
    assert integron_rows[0]["category"] == "integron"


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


def test_platon_parser_contributes_supporting_predictions(tmp_path):
    output_dir = tmp_path / "platon"
    output_dir.mkdir()
    (output_dir / "S1.plasmid.tsv").write_text(
        "ID\tRDS\tLength\ncontig_1\t0.91\t12000\n",
        encoding="utf-8",
    )

    rows = parse_standard_outputs("platon", output_dir, "S1")["plasmid_predictions"]

    assert rows[0]["contig_id"] == "contig_1"
    assert rows[0]["tool"] == "platon"
    assert rows[0]["evidence_level"] == "supporting"


def test_single_tool_consensus_keeps_primary_detector_authoritative(tmp_path):
    tables = tmp_path / "tables"
    append_standard_rows(
        tables,
        {
            "plasmid_predictions": [
                {"sample_id": "S1", "contig_id": "primary", "tool": "genomad"},
                {"sample_id": "S1", "contig_id": "supported", "tool": "genomad"},
                {"sample_id": "S1", "contig_id": "supported", "tool": "platon"},
                {"sample_id": "S1", "contig_id": "optional_only", "tool": "platon"},
            ]
        },
    )

    write_consensus_table(
        tables,
        strategy="single_tool",
        detection_tools=["genomad", "platon"],
    )

    rows = {row["contig_id"]: row for row in read_standard_table(tables, "plasmid_consensus")}
    assert rows["primary"]["final_plasmid_call"] == "True"
    assert rows["supported"]["support_tools"] == "genomad,platon"
    assert rows["optional_only"]["final_plasmid_call"] == "False"
