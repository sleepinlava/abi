#!/usr/bin/env python3
"""Emit per-environment YAML files from the unified environments.yaml.

Reads ``environments.yaml`` and writes each environment definition to
``envs/{name}.yml`` with the ``name:`` field inserted so that
``mamba env create -f envs/{name}.yml`` and
``mamba env update -f envs/{name}.yml`` work correctly.

Usage::

    python scripts/emit_env_yamls.py                        # default paths
    python scripts/emit_env_yamls.py --output /tmp/envs     # custom output dir
    python scripts/emit_env_yamls.py --envs autoplasm-qc,autoplasm-assembly  # subset
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ENV_KEYS = frozenset({"channels", "channel_priority", "dependencies"})


def emit_env_yamls(
    env_file: Path,
    output_dir: Path,
    *,
    env_names: list[str] | None = None,
) -> list[Path]:
    """Generate per-environment YAML files from a unified environments file.

    Args:
        env_file: Path to ``environments.yaml``.
        output_dir: Directory to write ``{name}.yml`` files into.
        env_names: Optional subset of environment names to emit.  When
            ``None``, all environments are emitted.

    Returns:
        List of output file paths written.
    """
    data = yaml.safe_load(env_file.read_text(encoding="utf-8"))
    environments = data.get("environments", {})
    if not environments:
        print("Warning: no environments found in", env_file, file=sys.stderr)
        return []

    name_filter = set(env_names) if env_names else None
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for env_name, env_def in environments.items():
        if name_filter and env_name not in name_filter:
            continue

        out: dict = {"name": env_name}
        for key in sorted(env_def):
            if key in ENV_KEYS:
                out[key] = env_def[key]

        out_path = output_dir / f"{env_name}.yml"
        # Use block style for readability / diff friendliness.
        yaml.safe_dump(
            out,
            out_path.open("w", encoding="utf-8"),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        written.append(out_path)

    return written


def main(argv: list[str] | None = None) -> None:
    project_root = Path(__file__).resolve().parents[1]
    default_env_file = project_root / "environments.yaml"
    default_output_dir = project_root / "envs"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default=str(default_env_file),
        help="Path to environments.yaml (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default=str(default_output_dir),
        help="Directory for per-env YAML files (default: %(default)s)",
    )
    parser.add_argument(
        "--envs",
        default=None,
        help="Comma-separated environment names to emit (default: all)",
    )
    args = parser.parse_args(argv)

    env_names = [n.strip() for n in args.envs.split(",") if n.strip()] if args.envs else None

    written = emit_env_yamls(
        Path(args.input),
        Path(args.output),
        env_names=env_names,
    )
    for p in written:
        print(p)


if __name__ == "__main__":
    main()
