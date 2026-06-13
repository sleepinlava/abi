"""Optional MCP stdio server for ABI agent tools."""

from __future__ import annotations

from typing import Any, Optional

from abi.agent import ABIAgentInterface

FastMCP: Any
try:
    from mcp.server.fastmcp import FastMCP as _ImportedFastMCP
except ImportError:  # pragma: no cover - exercised when optional dependency is absent
    FastMCP = None
else:
    FastMCP = _ImportedFastMCP


def create_server() -> object:
    """Create the ABI MCP server.

    The MCP SDK is optional so the main Python 3.9 ABI environment remains
    dependency-light. Install the MCP extra or use a separate MCP environment
    before launching this server.
    """
    if FastMCP is None:
        raise RuntimeError(
            "The optional MCP SDK is not installed. Install ABI with the MCP extra "
            "in a compatible environment before running `python -m abi.mcp.server`."
        )

    mcp = FastMCP("abi")
    agent = ABIAgentInterface()

    @mcp.tool()
    def abi_list_types() -> str:
        """List installed ABI analysis plugin types."""
        return agent.list_types()

    @mcp.tool()
    def abi_plan(
        analysis_type: str,
        config_path: Optional[str] = None,
        sample_sheet: Optional[str] = None,
        profile: str = "dry_run",
        mode: Optional[str] = None,
        threads: Optional[int] = None,
        outdir: Optional[str] = None,
        log_dir: Optional[str] = None,
        check_files: bool = True,
    ) -> str:
        """Build and persist an ABI execution plan without running external tools."""
        return agent.plan(
            analysis_type=analysis_type,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            check_files=check_files,
        )

    @mcp.tool()
    def abi_dry_run(
        analysis_type: str,
        config_path: Optional[str] = None,
        sample_sheet: Optional[str] = None,
        profile: str = "dry_run",
        mode: Optional[str] = None,
        threads: Optional[int] = None,
        outdir: Optional[str] = None,
        log_dir: Optional[str] = None,
        progress: Optional[bool] = None,
        check_files: bool = True,
    ) -> str:
        """Render commands and provenance artifacts without executing real tools."""
        return agent.dry_run(
            analysis_type=analysis_type,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            progress=progress,
            check_files=check_files,
        )

    @mcp.tool()
    def abi_inspect(result_dir: str) -> str:
        """Inspect an ABI result directory and summarize run health."""
        return agent.inspect(result_dir=result_dir)

    @mcp.tool()
    def abi_report(result_dir: str, analysis_type: Optional[str] = None) -> str:
        """Regenerate report files from existing ABI results."""
        return agent.report(result_dir=result_dir, analysis_type=analysis_type)

    @mcp.tool()
    def abi_export_nextflow(
        analysis_type: str,
        output: str,
        config_path: Optional[str] = None,
        sample_sheet: Optional[str] = None,
        profile: str = "dry_run",
        mode: Optional[str] = None,
        threads: Optional[int] = None,
        outdir: Optional[str] = None,
        log_dir: Optional[str] = None,
        smoke: bool = False,
        mamba_root: Optional[str] = None,
        check_files: bool = True,
    ) -> str:
        """Export an ABI execution plan as a Nextflow DSL2 workflow without running it."""
        return agent.export_nextflow(
            analysis_type=analysis_type,
            output=output,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            smoke=smoke,
            mamba_root=mamba_root,
            check_files=check_files,
        )

    @mcp.tool()
    def abi_export_agent_context(analysis_type: str) -> str:
        """Export compact machine-readable context for ABI agent callers."""
        return agent.export_agent_context(analysis_type=analysis_type)

    @mcp.tool()
    def abi_doctor_agent(analysis_type: str) -> str:
        """Return a short operating guide for ABI agent callers."""
        return agent.doctor_agent(analysis_type=analysis_type)

    @mcp.tool()
    def abi_validate_result(
        result_dir: str,
        allow_empty_tables: bool = True,
    ) -> str:
        """Validate an ABI result directory without modifying it."""
        return agent.abi_validate_result(
            result_dir=result_dir,
            allow_empty_tables=allow_empty_tables,
        )

    @mcp.tool()
    def abi_run(
        analysis_type: str,
        engine: str = "local",
        config_path: Optional[str] = None,
        sample_sheet: Optional[str] = None,
        profile: str = "dry_run",
        mode: Optional[str] = None,
        threads: Optional[int] = None,
        outdir: Optional[str] = None,
        log_dir: Optional[str] = None,
        workflow: Optional[str] = None,
        work_dir: Optional[str] = None,
        nxf_home: Optional[str] = None,
        nextflow_bin: Optional[str] = None,
        nextflow_profile: Optional[str] = None,
        executor: Optional[str] = None,
        resume: bool = False,
        mamba_root: Optional[str] = None,
        smoke: bool = False,
        check_files: bool = True,
        confirm_execution: bool = False,
    ) -> str:
        """Execute an ABI analysis after explicit user confirmation."""
        return agent.run(
            analysis_type=analysis_type,
            engine=engine,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            workflow=workflow,
            work_dir=work_dir,
            nxf_home=nxf_home,
            nextflow_bin=nextflow_bin,
            nextflow_profile=nextflow_profile,
            executor=executor,
            resume=resume,
            mamba_root=mamba_root,
            smoke=smoke,
            check_files=check_files,
            confirm_execution=confirm_execution,
        )

    return mcp


def main() -> None:
    server = create_server()
    server.run(transport="stdio")  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
