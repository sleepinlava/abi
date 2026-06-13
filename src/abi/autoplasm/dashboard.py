# ruff: noqa: E501
"""Local browser dashboard for AutoPlasm runs."""

from __future__ import annotations

import csv
import json
import mimetypes
import os
import shutil
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Mapping
from urllib.parse import parse_qs, urlparse

from abi.autoplasm.json_utils import load_json_object
from abi.autoplasm.schemas import AutoPlasmError

DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024


class DashboardServer:
    def __init__(self, result_dir: str | Path, *, host: str = "127.0.0.1", port: int = 18790):
        self.result_dir = Path(result_dir).resolve()
        self.host = host
        self.port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        port = self._server.server_port if self._server else self.port
        return f"http://{self.host}:{port}/"

    def start(self, *, open_browser: bool = False) -> str:
        handler = _handler_for(self.result_dir)
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        if open_browser:
            webbrowser.open(self.url)
        return self.url

    def serve_forever(self, *, open_browser: bool = False) -> str:
        handler = _handler_for(self.result_dir)
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        if open_browser:
            webbrowser.open(self.url)
        try:
            self._server.serve_forever()
        finally:
            self._server.server_close()
        return self.url

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        if server:
            server.shutdown()
            server.server_close()
            self._server = None
        if thread:
            thread.join(timeout=2)
            self._thread = None


def _handler_for(result_dir: Path) -> type[BaseHTTPRequestHandler]:
    class AutoPlasmDashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_text(_DASHBOARD_HTML, content_type="text/html; charset=utf-8")
                return
            if parsed.path == "/api/state":
                try:
                    state = dashboard_state(result_dir)
                except AutoPlasmError as exc:
                    self._send_json(
                        {"status": "error", "error": str(exc)},
                        status=500,
                    )
                    return
                self._send_json(state)
                return
            if parsed.path.startswith("/files/"):
                relative = parsed.path.removeprefix("/files/")
                self._send_file(relative)
                return
            if parsed.path == "/api/file":
                query = parse_qs(parsed.query)
                target = query.get("path", [""])[0]
                self._send_file(target)
                return
            self.send_error(404, "Not found")

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_json(self, payload: Mapping[str, Any], *, status: int = 200) -> None:
            self._send_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                content_type="application/json; charset=utf-8",
                status=status,
            )

        def _send_text(self, text: str, *, content_type: str, status: int = 200) -> None:
            data = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_file(self, relative: str) -> None:
            try:
                target = (result_dir / relative).resolve()
                target.relative_to(result_dir)
            except ValueError:
                self.send_error(403, "Path outside result directory")
                return
            if not target.exists() or not target.is_file():
                self.send_error(404, "File not found")
                return
            size = target.stat().st_size
            max_size = _max_file_bytes()
            if size > max_size:
                self.send_error(413, f"File is larger than dashboard limit ({max_size} bytes)")
                return
            content_type = mimetypes.guess_type(str(target))[0] or "text/plain"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with target.open("rb") as handle:
                shutil.copyfileobj(handle, self.wfile)

    return AutoPlasmDashboardHandler


def dashboard_state(result_dir: str | Path) -> Dict[str, Any]:
    root = Path(result_dir).resolve()
    progress_path = root / "provenance" / "progress.json"
    state: Dict[str, Any]
    if progress_path.exists():
        state = load_json_object(progress_path)
    else:
        state = _state_from_plan_and_commands(root)
    state["result_dir"] = str(root)
    state["links"] = _dashboard_links(root)
    return state


def _state_from_plan_and_commands(root: Path) -> Dict[str, Any]:
    plan_path = root / "execution_plan.json"
    summary_path = root / "provenance" / "run_summary.json"
    plan = _read_json(plan_path)
    summary = _read_json(summary_path)
    command_rows = _read_tsv(root / "provenance" / "commands.tsv")
    rows_by_step = {row.get("step_id", ""): row for row in command_rows}
    plan_steps = plan.get("steps", []) if isinstance(plan.get("steps", []), list) else []
    steps = []
    for step in plan_steps:
        row = rows_by_step.get(str(step.get("step_id", "")), {})
        steps.append(
            {
                "step_id": step.get("step_id", ""),
                "sample_id": step.get("sample_id") or "",
                "step_name": step.get("step_name", ""),
                "tool_id": step.get("tool_id", ""),
                "category": step.get("category", ""),
                "status": row.get("status", "pending"),
                "reason": row.get("reason", ""),
                "return_code": row.get("return_code", ""),
                "parsed_status": row.get("parsed_status", ""),
                "standard_tables": row.get("standard_tables", ""),
                "started_at": "",
                "finished_at": "",
            }
        )
    samples = {
        str(sample.get("sample_id", "")): {
            "sample_id": sample.get("sample_id", ""),
            "platform": sample.get("platform", ""),
            "status": "pending",
            "current_step_id": "",
            "completed_step_count": 0,
            "failed_step_count": 0,
        }
        for sample in plan.get("samples", [])
        if sample.get("sample_id")
    }
    for step in steps:
        sample_id = str(step.get("sample_id", ""))
        if sample_id not in samples:
            continue
        if step.get("status") in {"success", "dry_run", "skipped", "failed"}:
            samples[sample_id]["completed_step_count"] += 1
        if step.get("status") == "failed":
            samples[sample_id]["failed_step_count"] += 1
            samples[sample_id]["status"] = "failed"
    for sample in samples.values():
        if sample["status"] != "failed" and sample["completed_step_count"]:
            sample["status"] = "completed"
    failed_count = sum(1 for step in steps if step.get("status") == "failed")
    completed_count = sum(
        1 for step in steps if step.get("status") in {"success", "dry_run", "skipped", "failed"}
    )
    return {
        "project_name": plan.get("project_name", root.name),
        "status": summary.get("status", "unknown"),
        "dry_run": summary.get("dry_run", False),
        "parallel": summary.get("parallel", False),
        "workers": summary.get("workers", 1),
        "started_at": "",
        "finished_at": "",
        "total_step_count": len(steps),
        "completed_step_count": completed_count,
        "failed_step_count": failed_count,
        "running_step_count": 0,
        "current_steps": [],
        "samples": samples,
        "steps": steps,
        "last_event": {},
    }


def _dashboard_links(root: Path) -> Dict[str, str]:
    candidates = {
        "execution_plan": "execution_plan.json",
        "commands": "provenance/commands.tsv",
        "progress": "provenance/progress.json",
        "summary": "provenance/run_summary.json",
        "report": "report/report.html",
    }
    return {name: f"/files/{path}" for name, path in candidates.items() if (root / path).exists()}


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return load_json_object(path)


def _max_file_bytes() -> int:
    raw = os.environ.get("AUTOPLASM_DASHBOARD_MAX_FILE_BYTES")
    if not raw:
        return DEFAULT_MAX_FILE_BYTES
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_FILE_BYTES
    return value if value > 0 else DEFAULT_MAX_FILE_BYTES


def _read_tsv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


_DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AutoPlasm Dashboard</title>
<style>
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --panel: #ffffff;
  --ink: #20242c;
  --muted: #667085;
  --line: #d9dee8;
  --ok: #167c45;
  --warn: #a15c00;
  --bad: #b42318;
  --run: #175cd3;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
header {
  padding: 20px 28px 14px;
  border-bottom: 1px solid var(--line);
  background: #fff;
}
h1 { margin: 0; font-size: 24px; line-height: 1.2; letter-spacing: 0; }
.subhead { margin-top: 6px; color: var(--muted); font-size: 14px; }
main { padding: 20px 28px 32px; max-width: 1280px; margin: 0 auto; }
.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}
.metric, .section {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.metric { padding: 14px 16px; }
.metric .label { color: var(--muted); font-size: 12px; text-transform: uppercase; }
.metric .value { margin-top: 6px; font-size: 24px; font-weight: 650; }
.section { margin-top: 14px; overflow: hidden; }
.section h2 {
  margin: 0;
  padding: 13px 16px;
  border-bottom: 1px solid var(--line);
  font-size: 15px;
}
.progress-wrap { padding: 16px; }
.progressbar {
  height: 14px;
  background: #eceff4;
  border-radius: 999px;
  overflow: hidden;
}
.progressbar > div {
  height: 100%;
  width: 0;
  background: var(--run);
  transition: width 180ms ease;
}
.links { display: flex; flex-wrap: wrap; gap: 8px; padding: 0 16px 16px; }
.links a {
  color: var(--run);
  text-decoration: none;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 6px 8px;
  background: #fff;
  font-size: 13px;
}
.lanes { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; padding: 14px 16px 16px; }
.lane { border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fcfcfd; min-height: 96px; }
.lane-title { display: flex; justify-content: space-between; gap: 8px; font-weight: 650; }
.lane-detail { margin-top: 8px; color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
.status { font-size: 12px; padding: 2px 7px; border-radius: 999px; border: 1px solid var(--line); white-space: nowrap; }
.status.success, .status.completed, .status.dry_run { color: var(--ok); background: #ecfdf3; border-color: #abefc6; }
.status.running { color: var(--run); background: #eff8ff; border-color: #b2ddff; }
.status.failed { color: var(--bad); background: #fef3f2; border-color: #fecdca; }
.status.pending { color: var(--muted); background: #f8fafc; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 9px 10px; border-top: 1px solid var(--line); vertical-align: top; }
thead th { border-top: 0; color: var(--muted); font-weight: 650; background: #fcfcfd; }
td code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; overflow-wrap: anywhere; }
.reason { max-width: 420px; overflow-wrap: anywhere; color: var(--muted); }
@media (max-width: 720px) {
  header, main { padding-left: 14px; padding-right: 14px; }
  table { font-size: 12px; }
  th:nth-child(3), td:nth-child(3) { display: none; }
}
</style>
</head>
<body>
<header>
  <h1 id="project">AutoPlasm Dashboard</h1>
  <div class="subhead" id="subtitle">Connecting...</div>
</header>
<main>
  <section class="metrics">
    <div class="metric"><div class="label">Status</div><div class="value" id="status">unknown</div></div>
    <div class="metric"><div class="label">Progress</div><div class="value" id="count">0 / 0</div></div>
    <div class="metric"><div class="label">Running</div><div class="value" id="running">0</div></div>
    <div class="metric"><div class="label">Failed</div><div class="value" id="failed">0</div></div>
  </section>
  <section class="section">
    <h2>Run Progress</h2>
    <div class="progress-wrap"><div class="progressbar"><div id="bar"></div></div></div>
    <div class="links" id="links"></div>
  </section>
  <section class="section">
    <h2>Samples</h2>
    <div class="lanes" id="lanes"></div>
  </section>
  <section class="section">
    <h2>Steps</h2>
    <table>
      <thead><tr><th>Step</th><th>Status</th><th>Sample</th><th>Tool</th><th>Reason</th><th>Logs</th></tr></thead>
      <tbody id="steps"></tbody>
    </table>
  </section>
</main>
<script>
async function refresh() {
  const response = await fetch('/api/state', {cache: 'no-store'});
  const state = await response.json();
  render(state);
}
function statusBadge(status) {
  const value = status || 'pending';
  return `<span class="status ${escapeHtml(value)}">${escapeHtml(value)}</span>`;
}
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}
function render(state) {
  const total = Number(state.total_step_count || 0);
  const completed = Number(state.completed_step_count || 0);
  const percent = total ? Math.round((completed / total) * 100) : 0;
  document.getElementById('project').textContent = state.project_name || 'AutoPlasm Dashboard';
  document.getElementById('subtitle').textContent = `${state.result_dir || ''} | dry-run: ${Boolean(state.dry_run)} | parallel: ${Boolean(state.parallel)} | workers: ${state.workers || 1}`;
  document.getElementById('status').textContent = state.status || 'unknown';
  document.getElementById('count').textContent = `${completed} / ${total}`;
  document.getElementById('running').textContent = state.running_step_count || 0;
  document.getElementById('failed').textContent = state.failed_step_count || 0;
  document.getElementById('bar').style.width = `${percent}%`;
  const links = state.links || {};
  document.getElementById('links').innerHTML = Object.entries(links)
    .map(([name, href]) => `<a href="${escapeHtml(href)}" target="_blank" rel="noreferrer">${escapeHtml(name)}</a>`)
    .join('');
  const samples = Object.values(state.samples || {});
  document.getElementById('lanes').innerHTML = samples.map(sample => `
    <div class="lane">
      <div class="lane-title"><span>${escapeHtml(sample.sample_id)}</span>${statusBadge(sample.status)}</div>
      <div class="lane-detail">Platform: ${escapeHtml(sample.platform || '')}</div>
      <div class="lane-detail">Current: ${escapeHtml(sample.current_step_id || 'idle')}</div>
      <div class="lane-detail">Completed: ${sample.completed_step_count || 0}, failed: ${sample.failed_step_count || 0}</div>
    </div>`).join('');
  document.getElementById('steps').innerHTML = (state.steps || []).map(step => {
    const stdout = step.step_id ? `/files/provenance/step_logs/${step.step_id}.stdout.log` : '';
    const stderr = step.step_id ? `/files/provenance/step_logs/${step.step_id}.stderr.log` : '';
    const links = step.status && step.status !== 'pending'
      ? `<a href="${stdout}" target="_blank" rel="noreferrer">stdout</a> <a href="${stderr}" target="_blank" rel="noreferrer">stderr</a>`
      : '';
    return `<tr>
      <td><code>${escapeHtml(step.step_id)}</code><div>${escapeHtml(step.category || '')}</div></td>
      <td>${statusBadge(step.status)}</td>
      <td>${escapeHtml(step.sample_id || '')}</td>
      <td>${escapeHtml(step.tool_id || '')}</td>
      <td class="reason">${escapeHtml(step.reason || '')}</td>
      <td>${links}</td>
    </tr>`;
  }).join('');
}
refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""
