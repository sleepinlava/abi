from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def test_release_lock_helper_is_atomic_immutable_and_idempotent(tmp_path: Path) -> None:
    project = tmp_path / "abi"
    autoplasm = project / "resources" / "autoplasm"
    star_index = project / "resources" / "star_index"
    autoplasm.mkdir(parents=True)
    star_index.mkdir(parents=True)
    (project / "resources" / "NC_000913.3.gtf").write_text("test\n", encoding="utf-8")
    (autoplasm / "ready.txt").write_text("ready\n", encoding="utf-8")

    subprocess.run(["git", "init", "-q", str(project)], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "ABI Test"], check=True)
    subprocess.run(
        ["git", "-C", str(project), "config", "user.email", "abi@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(project), "add", "."], check=True)
    subprocess.run(["git", "-C", str(project), "commit", "-q", "-m", "test fixture"], check=True)

    fake_abi = tmp_path / "fake-abi"
    fake_abi.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == "--version" ]]; then
  echo "9.9.9"
  exit 0
fi
output_dir=""
prefix=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir) output_dir=$2; shift 2 ;;
    --prefix) prefix=$2; shift 2 ;;
    *) shift ;;
  esac
done
sleep 0.2
mkdir -p "${output_dir}"
for kind in conda tools resources runtime; do
  printf 'kind: abi-%s-lock\\n' "${kind}" > "${output_dir}/${prefix}.${kind}.lock.yaml"
done
""",
        encoding="utf-8",
    )
    fake_abi.chmod(0o755)

    lock_root = tmp_path / "runtime-locks"
    env = {
        **os.environ,
        "ABI_PROJECT_ROOT": str(project),
        "ABI_MAMBA_ROOT": str(tmp_path / "mamba"),
        "ABI_RUNTIME_RESOURCE_ROOT": str(tmp_path / "canonical-resources"),
        "ABI_LOCK_ROOT": str(lock_root),
        "ABI_AUTOPLASM_SOURCE": str(autoplasm),
        "ABI_RNA_SOURCE": str(project / "resources"),
        "ABI_BIN": str(fake_abi),
    }
    helper = Path(__file__).parents[2] / "scripts" / "cloud" / "prepare_release_lock.sh"

    processes = [
        subprocess.Popen(
            ["bash", str(helper)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    results = [process.communicate(timeout=30) + (process.returncode,) for process in processes]
    assert [result[2] for result in results] == [0, 0], results

    release_dirs = [path for path in lock_root.iterdir() if path.is_dir()]
    assert len(release_dirs) == 1
    release_dir = release_dirs[0]
    assert not release_dir.name.endswith(".publish-lock")
    assert not release_dir.name.endswith(".staging")
    assert not (release_dir.stat().st_mode & stat.S_IWUSR)
    manifest = next(release_dir.glob("*.sha256"))
    subprocess.run(
        ["sha256sum", "--check", manifest.name], cwd=release_dir, check=True, capture_output=True
    )

    repeated = subprocess.run(
        ["bash", str(helper)], env=env, check=False, capture_output=True, text=True
    )
    assert repeated.returncode == 0, repeated.stderr
    assert "already verified" in repeated.stdout

    conflict_root = tmp_path / "conflicting-resources"
    (conflict_root / "autoplasm").mkdir(parents=True)
    conflict_env = {**env, "ABI_RUNTIME_RESOURCE_ROOT": str(conflict_root)}
    conflict = subprocess.run(
        ["bash", str(helper)], env=conflict_env, check=False, capture_output=True, text=True
    )
    assert conflict.returncode == 1
    assert "Refusing to replace existing resource path" in conflict.stderr

    locked_file = next(release_dir.glob("*.runtime.lock.yaml"))
    locked_file.chmod(0o644)
    locked_file.write_text("corrupted\n", encoding="utf-8")
    corrupt = subprocess.run(
        ["bash", str(helper)], env=env, check=False, capture_output=True, text=True
    )
    assert corrupt.returncode == 1
    assert "FAILED" in corrupt.stdout

    timeout_root = tmp_path / "timeout-locks"
    timeout_root.mkdir()
    (timeout_root / f"{release_dir.name}.publish-lock").mkdir()
    timeout_env = {
        **env,
        "ABI_LOCK_ROOT": str(timeout_root),
        "ABI_PUBLISH_WAIT_SECONDS": "1",
    }
    timed_out = subprocess.run(
        ["bash", str(helper)], env=timeout_env, check=False, capture_output=True, text=True
    )
    assert timed_out.returncode == 1
    assert "Timed out waiting for release publication lock" in timed_out.stderr
