"""HTTP client for POST /api/bulk/photo — see docs/bulkscan-contract.md.

Retry/halt behaviour mirrors the contract's reference loop:
  - 401 / 403 / 409  -> config or job-state bug, halt immediately.
  - 400 / 5xx / network error -> transient or content bug, retry the
    SAME job+pass+seq (safe: the server overwrites that slot) with
    backoff 1s, 2s, 4s, 8s, 16s, then halt.
  - 200 with an ordinal that doesn't match what we sent -> pairing is
    drifting, halt immediately (never silently continue). Checked
    against `ordinal`, not `seq`: for pass 2, `seq` in the response is
    DELIBERATELY the paired pass-1 row (N+1-ordinal), by design — that's
    the whole point of the reverse-order pairing, not a sign of drift.
    `ordinal` is the field that actually echoes what was sent.
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)

HALT_STATUS = {401, 403, 409}
MAX_ATTEMPTS = 5


class UploadHalt(RuntimeError):
    """Stop the rig — not safe or useful to retry."""


class SequenceMismatch(UploadHalt):
    """The server assigned an ordinal, within this pass, other than the
    seq we sent — not to be confused with the response's `seq` field,
    which is deliberately something else on pass 2 (see uploader module
    docstring)."""


class PhotoUploader:
    def __init__(self, base_url: str, device_key: str, timeout: float = 30.0):
        self._url = f"{base_url}/api/bulk/photo"
        self._headers = {"x-bulk-key": device_key}
        self._timeout = timeout

    def upload(self, job: str, pass_num: int, seq: int, photo_path: str) -> dict:
        last_error = None
        for attempt in range(MAX_ATTEMPTS):
            if attempt:
                time.sleep(2**attempt)  # 2s, 4s, 8s, 16s between retries

            try:
                with open(photo_path, "rb") as fh:
                    resp = requests.post(
                        self._url,
                        headers=self._headers,
                        data={"job": job, "pass": str(pass_num), "seq": str(seq)},
                        files={"photo": fh},
                        timeout=self._timeout,
                    )
            except requests.RequestException as exc:
                last_error = exc
                logger.warning(
                    "seq=%s attempt=%s network error: %s", seq, attempt + 1, exc
                )
                continue

            if resp.status_code == 200:
                body = resp.json()
                if body.get("ordinal") != seq:
                    raise SequenceMismatch(
                        f"sent seq={seq} but server assigned ordinal="
                        f"{body.get('ordinal')} within this pass"
                        " — pairing is drifting, stop and tell the operator"
                    )
                return body

            if resp.status_code in HALT_STATUS:
                raise UploadHalt(f"HALT: {resp.status_code} {resp.text}")

            last_error = RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
            logger.warning(
                "seq=%s attempt=%s server error: %s", seq, attempt + 1, last_error
            )

        raise UploadHalt(
            f"card seq={seq} would not upload after {MAX_ATTEMPTS} attempts — "
            f"fix and rerun this pass ({last_error})"
        )
