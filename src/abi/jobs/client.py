"""Small stdlib HTTP client for the ABI Job Service."""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from abi.json_utils import loads_json

DEFAULT_JOB_SERVICE_URL = "http://127.0.0.1:18791"


class JobClientError(Exception):
    """Raised when the ABI Job Service returns a non-2xx response."""

    def __init__(self, status_code: int, payload: Mapping[str, Any]) -> None:
        super().__init__(str(payload.get("error") or payload.get("status") or status_code))
        self.status_code = status_code
        self.payload = dict(payload)


def submit_job(
    payload: Mapping[str, Any],
    *,
    base_url: str = DEFAULT_JOB_SERVICE_URL,
) -> Tuple[int, Dict[str, Any]]:
    return request_json("POST", "/jobs", payload, base_url=base_url)


def list_jobs(*, base_url: str = DEFAULT_JOB_SERVICE_URL) -> Tuple[int, Dict[str, Any]]:
    return request_json("GET", "/jobs", base_url=base_url)


def get_job(job_id: str, *, base_url: str = DEFAULT_JOB_SERVICE_URL) -> Tuple[int, Dict[str, Any]]:
    return request_json("GET", f"/jobs/{job_id}", base_url=base_url)


def get_artifacts(
    job_id: str,
    *,
    base_url: str = DEFAULT_JOB_SERVICE_URL,
) -> Tuple[int, Dict[str, Any]]:
    return request_json("GET", f"/jobs/{job_id}/artifacts", base_url=base_url)


def cancel_job(
    job_id: str,
    *,
    base_url: str = DEFAULT_JOB_SERVICE_URL,
) -> Tuple[int, Dict[str, Any]]:
    return request_json("POST", f"/jobs/{job_id}/cancel", {}, base_url=base_url)


def request_json(
    method: str,
    path: str,
    payload: Optional[Mapping[str, Any]] = None,
    *,
    base_url: str = DEFAULT_JOB_SERVICE_URL,
    timeout: float = 30.0,
) -> Tuple[int, Dict[str, Any]]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    url = _join_url(base_url, path)
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, _read_json_response(response.read())
    except HTTPError as exc:
        payload = _read_json_response(exc.read())
        raise JobClientError(exc.code, payload) from exc


def _join_url(base_url: str, path: str) -> str:
    normalized_base = base_url.rstrip("/") + "/"
    normalized_path = path.lstrip("/")
    return urljoin(normalized_base, normalized_path)


def _read_json_response(data: bytes) -> Dict[str, Any]:
    if not data:
        return {}
    decoded = loads_json(data, label="job service response")
    if not isinstance(decoded, dict):
        return {"result": decoded}
    return decoded
