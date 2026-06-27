"""HTTP client for the Wiro AI API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from genimg.core.providers.wiro_auth import build_wiro_headers
from genimg.core.providers.wiro_schema import ContentMode, ModelRunPlan
from genimg.logging_config import get_logger
from genimg.utils.exceptions import APIError, NetworkError

logger = get_logger(__name__)

WIRO_TASK_DONE_STATUS = "task_postprocess_end"
WIRO_SUCCESS_PEXIT = "0"


@dataclass(frozen=True)
class WiroRunResult:
    """Result of POST /Run."""

    taskid: str
    socketaccesstoken: str


@dataclass(frozen=True)
class WiroTask:
    """One task entry from POST /Task/Detail."""

    taskid: str
    socketaccesstoken: str
    status: str
    pexit: str
    outputs: tuple[dict[str, Any], ...]


class WiroClient:
    """Thin client for Wiro REST endpoints."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        api_secret: str | None = None,
        timeout: int = 60,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._api_secret = (api_secret or "").strip() or None
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return build_wiro_headers(self._api_key, self._api_secret)

    def _check_envelope(self, data: dict[str, Any], *, context: str) -> None:
        if data.get("result") is False:
            errors = data.get("errors")
            msg = ", ".join(str(e) for e in errors) if isinstance(errors, list) else str(errors)
            raise APIError(
                f"Wiro {context} failed: {msg or 'unknown error'}",
                response=str(data),
            )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        context: str = "request",
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            response = requests.request(
                method,
                url,
                headers={**self._headers(), "Content-Type": "application/json"},
                json=json_body,
                timeout=self._timeout,
            )
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Wiro network error during {context}: {e}", original_error=e) from e

        if response.status_code == 401:
            raise APIError(
                "Wiro authentication failed. Check WIRO_API_KEY and WIRO_API_SECRET.",
                status_code=401,
                response=response.text,
            )
        if response.status_code == 403:
            hint = ""
            if not self._api_secret:
                hint = " Signature may be required — set WIRO_API_SECRET."
            raise APIError(
                f"Wiro forbidden (403).{hint}",
                status_code=403,
                response=response.text,
            )
        if response.status_code == 429:
            raise APIError(
                "Wiro rate limit exceeded.",
                status_code=429,
                response=response.text,
            )
        if response.status_code >= 500:
            raise APIError(
                f"Wiro server error: {response.status_code}",
                status_code=response.status_code,
                response=response.text,
            )
        if response.status_code >= 400:
            raise APIError(
                f"Wiro {context} failed with status {response.status_code}: {response.text}",
                status_code=response.status_code,
                response=response.text,
            )

        try:
            data = response.json()
        except ValueError as e:
            raise APIError(
                f"Failed to parse Wiro {context} response as JSON: {e}",
                response=response.text,
            ) from e

        if not isinstance(data, dict):
            raise APIError(
                f"Unexpected Wiro {context} response shape.",
                response=str(data),
            )
        self._check_envelope(data, context=context)
        return data

    def get_model_detail(self, owner: str, project: str) -> dict[str, Any]:
        """POST /Tool/Detail for slugowner/slugproject."""
        return self._request_json(
            "POST",
            "/Tool/Detail",
            json_body={"slugowner": owner, "slugproject": project},
            context="Tool/Detail",
        )

    def run_model(
        self,
        owner: str,
        project: str,
        plan: ModelRunPlan,
    ) -> WiroRunResult:
        """POST /Run/{owner}/{project} with JSON or multipart body."""
        path = f"/Run/{owner}/{project}"
        url = f"{self._base_url}{path}"
        headers = self._headers()

        try:
            if plan.content_mode == ContentMode.JSON:
                response = requests.post(
                    url,
                    headers={**headers, "Content-Type": "application/json"},
                    json=plan.json_fields,
                    timeout=self._timeout,
                )
            else:
                multipart_files = [
                    (field_name, (filename, content, content_type))
                    for field_name, filename, content, content_type in plan.multipart_files
                ]
                response = requests.post(
                    url,
                    headers=headers,
                    data=plan.multipart_text_fields,
                    files=multipart_files,
                    timeout=self._timeout,
                )
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Wiro network error during Run: {e}", original_error=e) from e

        if response.status_code == 401:
            raise APIError(
                "Wiro authentication failed. Check WIRO_API_KEY and WIRO_API_SECRET.",
                status_code=401,
                response=response.text,
            )
        if response.status_code == 403 and not self._api_secret:
            raise APIError(
                "Wiro forbidden (403). Signature may be required — set WIRO_API_SECRET.",
                status_code=403,
                response=response.text,
            )
        if response.status_code >= 400:
            raise APIError(
                f"Wiro Run failed with status {response.status_code}: {response.text}",
                status_code=response.status_code,
                response=response.text,
            )

        try:
            data = response.json()
        except ValueError as e:
            raise APIError(
                f"Failed to parse Wiro Run response as JSON: {e}",
                response=response.text,
            ) from e

        if not isinstance(data, dict):
            raise APIError("Unexpected Wiro Run response shape.", response=str(data))
        self._check_envelope(data, context="Run")

        taskid = str(data.get("taskid") or "")
        token = str(data.get("socketaccesstoken") or "")
        if not token:
            raise APIError(
                "Wiro Run response missing socketaccesstoken.",
                response=str(data),
            )
        return WiroRunResult(taskid=taskid, socketaccesstoken=token)

    def get_task(
        self,
        *,
        tasktoken: str | None = None,
        taskid: str | None = None,
    ) -> WiroTask | None:
        """POST /Task/Detail; return first task or None if empty."""
        body: dict[str, str] = {}
        if tasktoken:
            body["tasktoken"] = tasktoken
        elif taskid:
            body["taskid"] = taskid
        else:
            raise ValueError("tasktoken or taskid required")

        data = self._request_json("POST", "/Task/Detail", json_body=body, context="Task/Detail")
        tasklist = data.get("tasklist")
        if not isinstance(tasklist, list) or not tasklist:
            return None
        raw = tasklist[0]
        if not isinstance(raw, dict):
            return None
        outputs_raw = raw.get("outputs")
        outputs: tuple[dict[str, Any], ...] = ()
        if isinstance(outputs_raw, list):
            outputs = tuple(o for o in outputs_raw if isinstance(o, dict))
        return WiroTask(
            taskid=str(raw.get("id") or taskid or ""),
            socketaccesstoken=str(raw.get("socketaccesstoken") or tasktoken or ""),
            status=str(raw.get("status") or ""),
            pexit=str(raw.get("pexit") or ""),
            outputs=outputs,
        )

    def cancel_task(self, tasktoken: str) -> None:
        """POST /Task/Cancel for queued tasks."""
        self._request_json(
            "POST",
            "/Task/Cancel",
            json_body={"tasktoken": tasktoken},
            context="Task/Cancel",
        )

    def kill_task(self, tasktoken: str) -> None:
        """POST /Task/Kill for running tasks."""
        self._request_json(
            "POST",
            "/Task/Kill",
            json_body={"tasktoken": tasktoken},
            context="Task/Kill",
        )

    def download_url(self, url: str) -> bytes:
        """Download output bytes from a Wiro CDN URL."""
        try:
            response = requests.get(url, timeout=self._timeout)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Failed to download Wiro output: {e}", original_error=e) from e
        if response.status_code != 200:
            raise APIError(
                f"Failed to download Wiro output: HTTP {response.status_code}",
                status_code=response.status_code,
                response=response.text[:500],
            )
        return response.content
