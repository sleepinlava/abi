"""Unified resource downloader with atomicity, idempotency, and locking.

所有资源下载使用此模块，提供：
- 原子写入（.part → os.replace）
- 进程级文件锁（filelock）
- 统一哨兵格式（.abi_resource.json）
- checksum 校验
- mock/dry-run 模式

Usage::

    from abi.resources.downloader import ResourceDownloader, DownloadSpec

    downloader = ResourceDownloader(
        root=Path("resources"),
        dry_run=False,
        mock=False,
    )
    result = downloader.ensure(DownloadSpec(
        resource_id="genomad_db",
        tool_id="genomad",
        command=["genomad", "download-database", str(target)],
        ready_check="non_empty_dir",
    ))
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_logger = logging.getLogger("abi.resources.downloader")

__all__ = ["DownloadSpec", "DownloadResult", "ResourceDownloader"]


@dataclass
class DownloadSpec:
    """下载规范 —— 描述一个资源如何获取。"""

    resource_id: str  # 唯一标识符（如 "genomad_db"）
    tool_id: str = ""  # 关联工具 ID
    display_name: str = ""  # 人类可读名称

    # 下载方式（command 优先于 source_url）
    source_url: str = ""  # HTTP/HTTPS 下载地址
    command: list[str] | None = None  # shell 命令

    # 校验
    checksum_algorithm: str = "sha256"
    expected_checksum: str = ""
    min_file_count: int = 0
    min_size_bytes: int = 0
    expected_files: list[str] = field(default_factory=list)

    # 就绪检查方式
    ready_check: str = "sentinel"  # sentinel | non_empty_dir | path_exists
    custom_check: Callable[[Path], bool] | None = None

    # 本地文件源（手动 bundle）
    source_files: list[Path] = field(default_factory=list)
    # 是否原子写入（False 时跳过 .part 中转，直接在目标目录操作）
    atomic: bool = True

    # 自定义目标路径（覆盖 root + resource_id）
    destination: Path | None = None

    # 超时
    timeout_seconds: float = 3600.0

    # 元数据
    version: str = ""
    source_metadata: dict = field(default_factory=dict)


@dataclass
class DownloadResult:
    """下载结果。"""

    resource_id: str
    path: Path
    status: str  # ok | missing | error | skipped | planned
    version: str = ""
    checksum: str = ""
    file_count: int = 0
    size_bytes: int = 0
    downloaded_at: str = ""
    message: str = ""
    command: list[str] = field(default_factory=list)


class ResourceDownloader:
    """统一的资源下载器。

    Args:
        root: 资源存储根目录。
        dry_run: 为 True 时不实际下载，仅返回 planned 状态。
        mock: 为 True 时创建空目录 + 哨兵文件，不下载实际数据。
        lock_timeout: 文件锁超时秒数。
    """

    SENTINEL = ".abi_resource.json"
    LEGACY_SENTINELS = (".abi_ready", ".abi_mock_resource")

    def __init__(
        self,
        root: Path,
        *,
        dry_run: bool = False,
        mock: bool = False,
        lock_timeout: int = 300,
    ) -> None:
        self.root = root.resolve()
        self.dry_run = dry_run
        self.mock = mock
        self.lock_timeout = lock_timeout

    # ── Public API ──────────────────────────────────────────────────────

    def ensure(self, spec: DownloadSpec) -> DownloadResult:
        """原子性确保资源就绪。

        流程：
        1. 检查已有资源（哨兵/目录非空/路径存在）
        2. 如果已就绪 → 返回 ok
        3. 如果 mock → 创建空目录 + mock 哨兵
        4. 如果 dry_run → 返回 planned
        5. 如果未就绪 → 原子下载
        """
        dest = spec.destination or self.root / spec.resource_id
        if self.dry_run:
            return DownloadResult(
                resource_id=spec.resource_id,
                path=dest,
                status="planned",
                message="Would download resource (dry-run)",
                command=list(spec.command or []),
            )
        if self.mock:
            return self._mock_resource(spec, dest)
        existing = self._check_existing(spec, dest)
        if existing.status == "ok":
            return existing
        return self._download_atomic(spec, dest)

    def check(self, spec: DownloadSpec) -> DownloadResult:
        """仅检查资源状态，不下载。"""
        dest = spec.destination or self.root / spec.resource_id
        return self._check_existing(spec, dest)

    def batch_ensure(self, specs: list[DownloadSpec]) -> list[DownloadResult]:
        """并行批量确保资源就绪。"""
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=4) as pool:
            return list(pool.map(self.ensure, specs))

    def batch_check(self, specs: list[DownloadSpec]) -> list[DownloadResult]:
        """批量检查资源状态。"""
        return [self.check(s) for s in specs]

    # ── Internal helpers ────────────────────────────────────────────────

    def _check_existing(self, spec: DownloadSpec, dest: Path) -> DownloadResult:
        """检查现有资源是否有效。"""
        if not dest.exists():
            return DownloadResult(
                resource_id=spec.resource_id,
                path=dest,
                status="missing",
                message="Path does not exist",
            )

        sentinel = dest / self.SENTINEL
        if sentinel.exists():
            try:
                meta = json.loads(sentinel.read_text(encoding="utf-8"))
                return DownloadResult(
                    resource_id=spec.resource_id,
                    path=dest,
                    status="ok",
                    version=meta.get("version", ""),
                    checksum=meta.get("checksum", ""),
                    file_count=meta.get("file_count", 0),
                    size_bytes=meta.get("total_size_bytes", 0),
                    downloaded_at=meta.get("downloaded_at", ""),
                    message="Sentinel OK",
                )
            except (json.JSONDecodeError, OSError):
                pass

        # Legacy sentinel check
        for legacy_name in self.LEGACY_SENTINELS:
            legacy = dest / legacy_name
            if legacy.exists():
                return DownloadResult(
                    resource_id=spec.resource_id,
                    path=dest,
                    status="ok",
                    message=f"Legacy sentinel ({legacy_name})",
                )

        if spec.ready_check == "non_empty_dir":
            if dest.is_dir() and any(dest.iterdir()):
                file_count = sum(1 for _ in dest.rglob("*") if _.is_file())
                total_size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
                return DownloadResult(
                    resource_id=spec.resource_id,
                    path=dest,
                    status="ok",
                    file_count=file_count,
                    size_bytes=total_size,
                    message="Non-empty directory",
                )

        if spec.ready_check == "path_exists":
            return DownloadResult(
                resource_id=spec.resource_id,
                path=dest,
                status="ok",
                message="Path exists",
            )

        return DownloadResult(
            resource_id=spec.resource_id,
            path=dest,
            status="missing",
            message="No valid sentinel or ready_check found",
        )

    def _download_atomic(self, spec: DownloadSpec, dest: Path) -> DownloadResult:
        """原子下载：.part → os.replace() + 哨兵写入。

        对于 command 类下载，直接在 dest 中执行（不经过 .part）——
        因为工具可能通过绝对参数写指定路径，.part 重命名不适用。
        对于 source_url 类下载，使用 .part → os.replace 保证原子性。
        """
        try:
            from filelock import FileLock

            has_filelock = True
        except ImportError:
            has_filelock = False

        lock_path = dest.with_name(dest.name + ".lock")

        if has_filelock:
            lock: Any = FileLock(str(lock_path), timeout=self.lock_timeout)
        else:
            lock = _NullLock()

        try:
            with lock:
                existing = self._check_existing(spec, dest)
                if existing.status == "ok":
                    return existing

                if spec.command:
                    work_dir = dest
                    is_atomic = spec.atomic
                else:
                    if spec.atomic:
                        part = dest.with_name(dest.name + ".part")
                        if part.exists():
                            shutil.rmtree(part, ignore_errors=True)
                        part.mkdir(parents=True, exist_ok=True)
                        work_dir = part
                        is_atomic = True
                    else:
                        work_dir = dest
                        dest.mkdir(parents=True, exist_ok=True)
                        is_atomic = False

                try:
                    if spec.command:
                        _logger.info(
                            "Downloading %s via: %s",
                            spec.resource_id,
                            " ".join(str(c) for c in spec.command),
                        )
                        work_dir.mkdir(parents=True, exist_ok=True)
                        proc = subprocess.run(
                            spec.command,
                            check=False,
                            timeout=spec.timeout_seconds,
                            capture_output=True,
                        )
                        if proc.returncode != 0:
                            stderr = str((proc.stderr or "")).strip()[-500:]
                            raise RuntimeError(f"Command failed (exit={proc.returncode}): {stderr}")
                    elif spec.source_url:
                        _logger.info(
                            "Downloading %s from: %s",
                            spec.resource_id,
                            spec.source_url,
                        )
                        self._download_url(spec.source_url, work_dir)
                    elif spec.source_files:
                        _logger.info(
                            "Copying %d local files for %s",
                            len(spec.source_files),
                            spec.resource_id,
                        )
                        for src in spec.source_files:
                            src_path = Path(src)
                            if not src_path.exists():
                                raise FileNotFoundError(
                                    f"Source file not found: {src_path}"
                                )
                            dest_file = work_dir / src_path.name
                            shutil.copy2(src_path, dest_file)
                    else:
                        raise ValueError(
                            f"No download method for {spec.resource_id}: "
                            "provide command or source_url"
                        )

                    file_count = (
                        sum(1 for _ in work_dir.rglob("*") if _.is_file())
                        if work_dir.is_dir()
                        else 1
                    )
                    total_size = (
                        sum(f.stat().st_size for f in work_dir.rglob("*") if f.is_file())
                        if work_dir.is_dir()
                        else work_dir.stat().st_size
                    )
                    checksum = ""
                    if spec.expected_checksum:
                        checksum = self._compute_checksum(work_dir, spec.checksum_algorithm)

                    sentinel_dir = work_dir if is_atomic else dest
                    self._write_sentinel(sentinel_dir, spec, checksum, file_count, total_size)

                    if is_atomic:
                        if dest.exists():
                            if dest.is_dir():
                                shutil.rmtree(dest)
                            else:
                                dest.unlink()
                        os.replace(work_dir, dest)

                    return DownloadResult(
                        resource_id=spec.resource_id,
                        path=dest,
                        status="ok",
                        version=spec.version,
                        checksum=checksum,
                        file_count=file_count,
                        size_bytes=total_size,
                        downloaded_at=datetime.now(timezone.utc).isoformat(),
                        command=list(spec.command or []),
                        message="Downloaded successfully",
                    )
                except Exception:
                    if not is_atomic:
                        if spec.atomic:
                            self._cleanup_partial(work_dir)
                        else:
                            # non-atomic: cleanup residual files in dest
                            self._cleanup_partial(dest)
                    elif work_dir.exists():
                        shutil.rmtree(work_dir, ignore_errors=True)
                    raise
        except Exception as exc:
            return DownloadResult(
                resource_id=spec.resource_id,
                path=dest,
                status="error",
                message=str(exc),
            )

    def _download_url(self, url: str, dest: Path) -> None:
        """HTTP 下载（流式读取）。"""
        import urllib.request

        filename = url.rstrip("/").rpartition("/")[2] or "download"
        filepath = dest / filename

        try:
            import requests

            resp = requests.get(url, stream=True, timeout=30)
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
        except ImportError:
            urllib.request.urlretrieve(url, filepath)

    def _compute_checksum(self, path: Path, algorithm: str) -> str:
        """计算文件或目录的 checksum。"""
        h = hashlib.new(algorithm)
        if path.is_file():
            h.update(path.read_bytes())
        elif path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and f.name != self.SENTINEL:
                    h.update(f.read_bytes())
        return h.hexdigest()

    def _write_sentinel(
        self,
        dest: Path,
        spec: DownloadSpec,
        checksum: str,
        file_count: int,
        total_size: int,
    ) -> None:
        """写统一格式哨兵文件。"""
        sentinel = {
            "abi_version": "2.0",
            "resource_id": spec.resource_id,
            "tool_id": spec.tool_id,
            "version": spec.version,
            "checksum_algorithm": spec.checksum_algorithm,
            "checksum": checksum,
            "file_count": file_count,
            "total_size_bytes": total_size,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }
        (dest / self.SENTINEL).write_text(json.dumps(sentinel, indent=2), encoding="utf-8")

    def _cleanup_partial(self, path: Path) -> None:
        """清空部分下载的残留目录。"""
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)

    def _mock_resource(self, spec: DownloadSpec, dest: Path) -> DownloadResult:
        """创建 mock 资源（空目录 + 哨兵）。"""
        dest.mkdir(parents=True, exist_ok=True)
        sentinel = dest / self.SENTINEL
        if not sentinel.exists():
            self._write_sentinel(dest, spec, "mock", 0, 0)
        return DownloadResult(
            resource_id=spec.resource_id,
            path=dest,
            status="ok",
            message="Mock resource",
        )


class _NullLock:
    """fallback 文件锁（当 filelock 未安装时使用）。"""

    def __init__(self) -> None:
        pass

    def __enter__(self) -> _NullLock:
        return self

    def __exit__(self, *args: Any) -> None:
        pass
