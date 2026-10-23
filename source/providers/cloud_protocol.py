"""Cloud protocol conversion helpers; no inference engine or model loader."""
from __future__ import annotations
import json
from typing import Any
from .base import FunctionCall

def _normalise(url: str) -> str:
    """Whatever the user pasted, turned into a base URL that works.

    Three things get fixed, all of them things people actually type:
      * `localhost` -> `127.0.0.1`, for the Windows resolver reason above.
      * A missing scheme, because "192.168.1.40:11434" is what a person writes.
      * A missing or duplicated `/v1`, because half the setup guides include it
        and half do not, and `.../v1/v1/chat/completions` is a 404 that reads
        like the server is down.
    """
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    scheme, _, rest = url.partition("://")
    host, slash, path = rest.partition("/")
    if host.split(":")[0].lower() == "localhost":
        port = host.partition(":")[2]
        host = "127.0.0.1" + (f":{port}" if port else "")
    url = f"{scheme}://{host}{slash}{path}".rstrip("/")
    # Only append /v1 when there is no path at all. An endpoint served under a
    # prefix (a reverse proxy, OpenRouter's /api/v1) must be left alone.
    if not path:
        url += "/v1"
    return url

def _is_loopback(url: str) -> bool:
    host = url.partition("://")[2].partition("/")[0].partition(":")[0].lower()
    return host in ("127.0.0.1", "::1", "localhost") or host.startswith("127.")

def parts_to_openai(parts: list) -> Any:
    """Gemini `parts` -> an OpenAI message `content`.

    The app builds image payloads as `{"inline_data": {"mime_type", "data"}}`,
    with the data already base64 — see `_flush_pending_vision` in main.py and
    `_to_live_parts` in core/gemini.py. OpenAI wants the same bytes as a data
    URI, so this is a reshape rather than a re-encode.

    Text-only content is returned as a bare string, not a one-element list.
    Several local servers accept only the string form for plain text, and every
    server accepts it, so it is the safer of the two shapes.
    """
    out: list[dict] = []
    texts: list[str] = []
    for p in parts or []:
        if isinstance(p, str):
            texts.append(p)
            out.append({"type": "text", "text": p})
            continue
        if not isinstance(p, dict):
            # An SDK Part object.
            blob = getattr(p, "inline_data", None)
            if blob is not None:
                data = getattr(blob, "data", None)
                mime = getattr(blob, "mime_type", None) or "image/png"
                if isinstance(data, bytes):
                    import base64
                    data = base64.b64encode(data).decode("ascii")
                out.append({"type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{data}"}})
                continue
            txt = getattr(p, "text", None)
            if txt:
                texts.append(txt)
                out.append({"type": "text", "text": txt})
            continue
        if "text" in p:
            texts.append(p["text"])
            out.append({"type": "text", "text": p["text"]})
        elif "inline_data" in p:
            blob = p["inline_data"]
            data = blob.get("data")
            mime = blob.get("mime_type") or "image/png"
            if isinstance(data, bytes):
                import base64
                data = base64.b64encode(data).decode("ascii")
            out.append({"type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{data}"}})

    if len(out) == len(texts):
        return "\n".join(texts)
    return out

class _ToolCallBuffer:
    """Reassembles tool calls that arrive in fragments.

    A streamed tool call does not come as one object. The name arrives in one
    delta, the arguments in a dozen more, each tagged with an `index`, and a
    burst can carry two calls interleaved. Concatenating without honouring the
    index produces one call with two names welded together — which then fails to
    match any tool and looks like the model hallucinated.
    """

    def __init__(self) -> None:
        self._slots: dict[int, dict] = {}

    def feed(self, deltas: list) -> None:
        for d in deltas or []:
            idx = d.get("index", 0)
            slot = self._slots.setdefault(idx, {"id": "", "name": "", "args": ""})
            if d.get("id"):
                slot["id"] = d["id"]
            fn = d.get("function") or {}
            if fn.get("name"):
                slot["name"] += fn["name"]
            if fn.get("arguments"):
                slot["args"] += fn["arguments"]

    def drain(self) -> list[FunctionCall]:
        calls = []
        for idx in sorted(self._slots):
            slot = self._slots[idx]
            if not slot["name"]:
                continue
            raw = slot["args"].strip() or "{}"
            try:
                args = json.loads(raw)
            except Exception:
                # A model that emits invalid JSON is common enough that dropping
                # the call is the wrong answer: the tool name is usually right
                # and the arguments usually salvageable. Try the largest object
                # in the string before giving up on the call entirely.
                args = {}
                if "{" in raw and "}" in raw:
                    try:
                        args = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
                    except Exception:
                        args = {}
            if not isinstance(args, dict):
                args = {"value": args}
            calls.append(FunctionCall(id=slot["id"] or f"call_{idx}",
                                      name=slot["name"], args=args))
        self._slots.clear()
        return calls

def _terse(text: str, limit: int = 160) -> str:
    """A server's error body, reduced to something a person can read.

    Local servers return HTML error pages and hosted ones return nested JSON;
    both are hundreds of characters of nothing when they reach a log line.
    """
    text = " ".join((text or "").split())
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            err = obj.get("error", obj)
            if isinstance(err, dict):
                text = str(err.get("message") or err)
            else:
                text = str(err)
    except Exception:
        pass
    return text[:limit] + ("..." if len(text) > limit else "")
