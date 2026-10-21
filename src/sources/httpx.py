"""GET with retries. Raw files go to bronze with a new copy only when the content changes (sha256),
every fetch is logged, and if the API is down we fall back to the last copy."""

from pathlib import Path
import httpx
import time
from src.config import settings
from loguru import logger
import hashlib
import json
from datetime import datetime, timedelta, UTC

events: list[dict] = []
client: httpx.Client | None = None

def client_func() -> httpx.Client:
    global client
    if not client:
        client = httpx.Client(timeout=httpx.Timeout(timeout=120, connect=15),
                               follow_redirects=True, headers={"User-Agent": "euro-area-hicp/1.0 (research pipeline)"},
                               transport=httpx.HTTPTransport(retries=2))
    return client

# strategy for delay: if it return Retry-After -> follow rule otherwise use exponential back-off
def delay(attempt:int, response: httpx.Response | None = None) -> float:
    after = response.headers.get("Retry-After", "") if response is not None else ""
    return float(after) if after.isdigit() else settings.backoff_seconds * 2**attempt

def get(url: str, params: dict | None = None, timeout: float = 120.0) -> httpx.Response:
    """GET with retries on transport errors and on 429 errors or 500 and above. Raises httpx.HTTPError"""
    for attempt in range(settings.max_attempts - 1):
        try:
            r = client_func().get(url, params=params, timeout=timeout)
        except httpx.TransportError as exc:
            wait, why = delay(attempt), type(exc).__name__
        else:
            if r.status_code not in settings.retry_status:
                r.raise_for_status()
                return r
            wait, why = delay(attempt, r), f"HTTP {r.status_code}"
        logger.info(f"{url}: {why}, retry in {wait:.0f}s")
        time.sleep(wait)

    # last try, whatever happens now is final
    r = client_func().get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r

# take the latest existing file if there are any errors
def latest(source: str, name: str, ext: str = "csv") -> Path | None:
    files = stored(settings.bronze / source / name, ext)
    return files[-1] if files else None

def stored(folder: Path, ext: str) -> list[Path]:
    return [p for p in sorted(folder.glob(f"*.{ext}")) if not p.name.endswith(".meta.json")]

def fetched_today(source, name):
    """The stored file if the last fetch of source/name was today (UTC), else None."""
    folder = settings.bronze / source / name
    if not (folder / LOG).exists():
        return None
    lines = (folder / LOG).read_text().strip().splitlines()
    if not lines:
        return None
    last = json.loads(lines[-1])
    path = folder / last["stored_as"]
    today = datetime.now(UTC).date().isoformat()
    return path if last["fetched_at"][:10] == today and path.exists() else None

# check if there any duplicated version before write to disk
def sha(path: Path) -> str:
    meta = path.with_suffix(path.suffix + ".meta.json")
    if meta.exists():
        return json.loads(meta.read_text())["sha256"]
    return hashlib.sha256(path.read_bytes()).hexdigest()

LOG = "fetch_log.jsonl"
def _last_logged(folder: Path) -> dict | None:
    log_path = folder / LOG
    if not log_path.exists():
        return None
    lines = log_path.read_text().strip().splitlines()
    return json.loads(lines[-1]) if lines else None

def fetch(url: str, params, *, source: str, name: str, ext: str = "csv",
          refresh: bool = False, timeout: float = 120.0) -> bytes:
    folder = settings.bronze / source / name
    now = datetime.now(UTC)
    last = _last_logged(folder)
    if (not refresh and last and last["fetched_at"][:10] == now.date().isoformat()
            and (folder / last["stored_as"]).exists()):
        logger.debug(f"already fetched today: {source}/{name}")
        return (folder / last["stored_as"]).read_bytes()

    try:
        r = get(url, params, timeout)
    except httpx.HTTPError as exc:
        old = latest(source, name, ext)
        if old is None:
            raise
        logger.warning(f"{source}/{name}: live fetch failed ({exc}), using {old.name}")
        events.append({"source": source, "name": name, "fallback": old.name, "error": str(exc)})
        return old.read_bytes()

    content = r.content
    digest = hashlib.sha256(content).hexdigest()
    previous = latest(source, name, ext)
    folder.mkdir(parents=True, exist_ok=True)
    if previous is not None and sha(previous) == digest:
        stored_as, new = previous.name, False
    else:
        # names sort in time order, microseconds keep two changes in one second apart
        stamp = now
        while (folder / f"{stamp:%Y-%m-%dT%H%M%S%fZ}.{ext}").exists():
            stamp += timedelta(microseconds=1)
        stored_as, new = f"{stamp:%Y-%m-%dT%H%M%S%fZ}.{ext}", True
        path = folder / stored_as
        path.write_bytes(content)
        meta = {"url": str(r.url), "fetched_at": now.isoformat(timespec="seconds"),
                "sha256": digest, "bytes": len(content)}
        path.with_suffix(f".{ext}.meta.json").write_text(json.dumps(meta, indent=2))
    with (folder / LOG).open("a") as fh:
        fh.write(json.dumps({"fetched_at": now.isoformat(timespec="seconds"), "url": str(r.url),
                             "sha256": digest, "bytes": len(content), "stored_as": stored_as,
                             "new": new}) + "\n")
    return content