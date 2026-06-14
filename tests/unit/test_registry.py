from abi.autoplasm.skills.registry import ToolRegistry


def test_registry_builds_fastp_command():
    registry = ToolRegistry.from_path()
    skill = registry.create("fastp", mock_tools=True)
    command = skill.build_command(
        {
            "sample_id": "S1",
            "read1": "examples/fixtures/tiny_R1.fastq",
            "read2": "examples/fixtures/tiny_R2.fastq",
            "output_dir": "results/test/qc",
            "threads": 2,
        }
    )
    assert command[0] == "fastp"
    assert "--thread" in command


def test_registry_builds_genomad_command_with_restart_and_threads():
    registry = ToolRegistry.from_path()
    skill = registry.create("genomad", mock_tools=True)
    command = skill.build_command(
        {
            "assembly": "assembly.fasta",
            "output_dir": "results/genomad",
            "database": "resources/autoplasm/genomad",
            "threads": 2,
        }
    )

    assert command[:2] == ["genomad", "end-to-end"]
    assert "--restart" in command
    assert "--threads" in command
    assert "2" in command


def test_registry_builds_bowtie2_command_with_temporary_index():
    registry = ToolRegistry.from_path()
    skill = registry.create("bowtie2", mock_tools=True)
    command = skill.build_command(
        {
            "sample_id": "S1",
            "plasmid_contigs": "results/S1/plasmid_contigs.fasta",
            "read1": "results/S1/S1_R1.clean.fastq.gz",
            "read2": "results/S1/S1_R2.clean.fastq.gz",
            "output_dir": "results/S1/abundance",
            "threads": 2,
        }
    )

    assert command[:2] == ["sh", "-c"]
    assert 'bowtie2-build "$1"' in command[2]
    assert command[4:] == [
        "results/S1/plasmid_contigs.fasta",
        "results/S1/abundance",
        "S1",
        "",
        "results/S1/S1_R1.clean.fastq.gz",
        "results/S1/S1_R2.clean.fastq.gz",
        "2",
        "results/S1/abundance/S1.sam",
    ]


def test_registry_builds_minimap2_command_with_long_read_inputs():
    registry = ToolRegistry.from_path()
    skill = registry.create("minimap2", mock_tools=True)
    command = skill.build_command(
        {
            "sample_id": "ONT1",
            "plasmid_contigs": "results/ONT1/plasmid_contigs.fasta",
            "long_reads": "results/ONT1/ONT1.filtlong.fastq",
            "output_dir": "results/ONT1/abundance",
            "threads": 2,
        }
    )

    assert command[0] == "minimap2"
    assert "-ax" in command
    assert "map-ont" in command
    assert "results/ONT1/ONT1.filtlong.fastq" in command
    assert "results/ONT1/abundance/ONT1.sam" in command


def test_registry_builds_minimap2_command_with_hifi_preset():
    registry = ToolRegistry.from_path()
    skill = registry.create("minimap2", mock_tools=True)
    command = skill.build_command(
        {
            "sample_id": "HIFI1",
            "plasmid_contigs": "results/HIFI1/plasmid_contigs.fasta",
            "long_reads": "results/HIFI1/HIFI1.hifiadapterfilt.fastq.gz",
            "output_dir": "results/HIFI1/abundance",
            "threads": 2,
            "minimap2_preset": "map-hifi",
        }
    )

    assert command[0] == "minimap2"
    assert "map-hifi" in command
    assert "results/HIFI1/HIFI1.hifiadapterfilt.fastq.gz" in command
    assert "results/HIFI1/abundance/HIFI1.sam" in command


def test_registry_builds_hifiasm_meta_command_with_fasta_normalization():
    registry = ToolRegistry.from_path()
    skill = registry.create("hifiasm_meta", mock_tools=True)
    command = skill.build_command(
        {
            "sample_id": "HIFI1",
            "long_reads": "results/HIFI1/HIFI1.hifiadapterfilt.fastq.gz",
            "output_dir": "results/HIFI1/assembly",
            "threads": 2,
        }
    )

    assert command[:2] == ["sh", "-c"]
    assert 'hifiasm -t "$2"' in command[2]
    assert "scripts/hifiasm_gfa_to_fasta.sh" in command[2]
    assert command[4:8] == [
        "results/HIFI1/assembly",
        "2",
        "HIFI1",
        "results/HIFI1/HIFI1.hifiadapterfilt.fastq.gz",
    ]


def test_registry_builds_opera_ms_command_with_fasta_normalization():
    registry = ToolRegistry.from_path()
    skill = registry.create("opera_ms", mock_tools=True)
    command = skill.build_command(
        {
            "sample_id": "HYB1",
            "read1": "results/HYB1/HYB1_R1.clean.fastq.gz",
            "read2": "results/HYB1/HYB1_R2.clean.fastq.gz",
            "long_reads": "results/HYB1/HYB1.filtlong.fastq",
            "output_dir": "results/HYB1/assembly",
            "threads": 2,
        }
    )

    assert command[:2] == ["sh", "-c"]
    assert "OPERA-MS.pl" in command[2]
    assert "scripts/normalize_opera_ms_output.sh" in command[2]
    assert "contigs.fasta" in command[2]


def test_registry_skill_docs_exist():
    from pathlib import Path

    # skill_path values in tool_registry.yaml are relative (skills/<tool>/SKILL.md).
    # Skills now live inside the ABI package at src/abi/skills/.
    skills_root = _resolve_skills_root()
    registry = ToolRegistry.from_path()
    missing = []
    for tool in registry.list_tools():
        skill_path = tool.get("skill_path")
        if skill_path:
            # Resolve: strip the leading "skills/" prefix and look inside package
            tool_name = Path(skill_path).parent.name
            candidate = skills_root / tool_name / "SKILL.md"
            if not candidate.exists():
                missing.append(f"{skill_path} (expected at {candidate})")
    assert missing == []


def _resolve_skills_root():
    """Resolve the bundled skills directory inside the ABI package."""
    from pathlib import Path as _Path

    try:
        from importlib.resources import files as _resources_files

        _path = _resources_files("abi") / "skills"
        if _path.is_dir():
            return _Path(str(_path))
    except Exception:
        pass
    import abi

    return _Path(abi.__file__).parent / "skills"


def test_integronfinder_uses_dedicated_biopython_compat_env():
    registry = ToolRegistry.from_path()
    metadata = registry.get("integronfinder")

    assert metadata["env_name"] == "autoplasm-integronfinder"
    assert "biopython=1.77" in metadata["limitations"]


def test_generic_skill_uses_repository_mamba_root(tmp_path, monkeypatch):
    env_bin = tmp_path / ".mamba" / "envs" / "mock-env" / "bin"
    env_bin.mkdir(parents=True)
    executable = env_bin / "mock_tool"
    executable.write_text("#!/usr/bin/env sh\nprintf 'mock ok\\n'\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(tmp_path / ".mamba"))

    skill = ToolRegistry(
        [
            {
                "id": "mock_tool",
                "env_name": "mock-env",
                "executable": "mock_tool",
                "command_template": "mock_tool",
            }
        ]
    ).create("mock_tool")

    assert skill.check_installation()
    result = skill.run({}, dry_run=False)
    assert result.status == "success"
    assert result.stdout == "mock ok\n"


def test_generic_skill_handles_stdout_redirection(tmp_path, monkeypatch):
    env_bin = tmp_path / ".mamba" / "envs" / "mock-env" / "bin"
    env_bin.mkdir(parents=True)
    executable = env_bin / "mock_tool"
    executable.write_text("#!/usr/bin/env sh\nprintf 'redirect ok\\n'\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(tmp_path / ".mamba"))

    output = tmp_path / "out" / "result.txt"
    skill = ToolRegistry(
        [
            {
                "id": "mock_tool",
                "env_name": "mock-env",
                "executable": "mock_tool",
                "command_template": "mock_tool > {output}",
            }
        ]
    ).create("mock_tool")

    result = skill.run({"output": str(output)}, dry_run=False)
    assert result.status == "success"
    assert output.read_text(encoding="utf-8") == "redirect ok\n"


def test_generic_skill_times_out_hung_process(tmp_path, monkeypatch):
    env_bin = tmp_path / ".mamba" / "envs" / "mock-env" / "bin"
    env_bin.mkdir(parents=True)
    executable = env_bin / "mock_tool"
    executable.write_text("#!/usr/bin/env sh\nsleep 2\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(tmp_path / ".mamba"))

    skill = ToolRegistry(
        [
            {
                "id": "mock_tool",
                "env_name": "mock-env",
                "executable": "mock_tool",
                "command_template": "mock_tool",
                "timeout_seconds": 0.01,
            }
        ]
    ).create("mock_tool")

    result = skill.run({}, dry_run=False)

    assert result.status == "timeout"
    assert result.return_code == -1
    assert "timed out" in result.stderr


def test_check_tools_reports_resource_status(tmp_path, monkeypatch):
    env_bin = tmp_path / ".mamba" / "envs" / "mock-env" / "bin"
    env_bin.mkdir(parents=True)
    executable = env_bin / "mock_tool"
    executable.write_text("#!/usr/bin/env sh\nprintf 'mock ok\\n'\n", encoding="utf-8")
    executable.chmod(0o755)
    database = tmp_path / "db"
    database.mkdir()
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(tmp_path / ".mamba"))

    registry = ToolRegistry(
        [
            {
                "id": "mock_tool",
                "env_name": "mock-env",
                "executable": "mock_tool",
                "command_template": "mock_tool {database}",
            }
        ]
    )

    rows = registry.check_tools(config={"resources": {"mock_tool": {"database": str(database)}}})
    assert rows[0]["status"] == "ok"
    assert rows[0]["resource_status"] == "ok"
