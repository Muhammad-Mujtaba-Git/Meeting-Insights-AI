"""
Meeting Insights AI — single-file Streamlit frontend.

Self-contained: no local imports, drop this one file anywhere and run it.
    pip install streamlit requests
    streamlit run app.py

Backend contract (FastAPI):
    GET  /health                                  -> any 2xx (falls back to /docs, then /)
    POST /process {"source", "chunk_minutes"}     -> {title, summary, action_items,
                                                     key_decisions, questions, transcript}
    POST /ask     {"question"}                    -> {"answer": "..."}
"""

from __future__ import annotations

import html
import json
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================================================================
# Config
# ==========================================================================
APP_TITLE = "Meeting Insights AI"
APP_SUB = (
    "Turn any meeting recording into actionable intelligence — executive summary, "
    "action items, decisions and instant Q&A over the transcript."
)
DEFAULT_API_URL = "http://localhost:8000"   # <- point this at your backend
UPLOAD_DIR = Path("uploads")

# --- Auto-ping behaviour -------------------------------------------------
# The page probes the backend by itself: once as soon as it loads, then on a
# timer so a free-tier host never falls asleep while the tab is open.
AUTO_PING_ON_LOAD = True          # silent probe on first page load
KEEPALIVE_DEFAULT = True          # keep-alive toggle's starting position
KEEPALIVE_INTERVAL = 240          # seconds between keep-alive pings (4 min)
KEEPALIVE_TICK = "3s"             # how often the status widget refreshes itself

HEALTH_TIMEOUT = (5, 25)      # (connect, read) seconds — manual "wake" click
QUICK_TIMEOUT = (3, 8)        # background pings: fail fast, never stall the page
ASK_TIMEOUT = (5, 180)
PROCESS_TIMEOUT = (5, 1800)   # transcription can be slow

ACCENT, ACCENT_2 = "#7c5cff", "#00d4ff"
SUCCESS, WARNING, DANGER, MUTED = "#00d68f", "#ffb800", "#ff5470", "#8b92a7"

st.set_page_config(
    page_title=APP_TITLE, page_icon="🎙️",
    layout="wide", initial_sidebar_state="expanded",
)

# ==========================================================================
# Styling
# ==========================================================================
CSS = """
<style>
:root {
    --bg:#0a0e1a; --surface:#131825; --border:#252b3a; --text:#e6e9f0;
    --muted:#8b92a7; --accent:#7c5cff; --accent-2:#00d4ff;
    --success:#00d68f; --warning:#ffb800; --danger:#ff5470;
}
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at 12% 8%,  rgba(124,92,255,.13), transparent 38%),
        radial-gradient(circle at 88% 92%, rgba(0,212,255,.10), transparent 42%),
        var(--bg);
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] {
    background: linear-gradient(180deg,#0e1320 0%,#0a0e1a 100%);
    border-right: 1px solid var(--border);
}
.block-container { padding-top:2.2rem; padding-bottom:3rem; max-width:1280px; }
h1,h2,h3,h4 { letter-spacing:-.02em; font-weight:700; }

.grad {
    background: linear-gradient(90deg,var(--accent) 0%,var(--accent-2) 100%);
    -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent;
}
.hero {
    border:1px solid var(--border); border-radius:18px; padding:30px 34px; margin-bottom:20px;
    background: linear-gradient(135deg,rgba(124,92,255,.10),rgba(0,212,255,.05));
    box-shadow: 0 10px 40px rgba(0,0,0,.35);
}
.hero h1 { font-size:2.5rem; font-weight:800; margin:0 0 6px; line-height:1.15; }
.hero p  { color:var(--muted); font-size:1rem; margin:0; max-width:70ch; }

.card {
    background: rgba(19,24,37,.72); border:1px solid var(--border); border-radius:14px;
    padding:20px 24px; margin-bottom:14px;
    transition: border-color .25s ease, box-shadow .25s ease;
}
.card:hover { border-color: rgba(124,92,255,.5); box-shadow: 0 8px 26px rgba(124,92,255,.14); }
.card-head {
    display:flex; align-items:center; gap:10px; font-size:.82rem; font-weight:700;
    text-transform:uppercase; letter-spacing:.07em; margin-bottom:12px;
}
.card-body { color:#d3d8e6; font-size:.95rem; line-height:1.7; white-space:pre-wrap;
             word-wrap:break-word; margin:0; }
.card-body.empty { color:var(--muted); font-style:italic; }

.kpi {
    background: linear-gradient(135deg,rgba(124,92,255,.09),rgba(0,212,255,.04));
    border:1px solid var(--border); border-radius:14px; padding:18px 14px;
    text-align:center; height:100%; transition: transform .25s ease, border-color .25s ease;
}
.kpi:hover { transform: translateY(-3px); border-color: var(--accent); }
.kpi-value { font-size:1.9rem; font-weight:800; line-height:1.1; }
.kpi-label { color:var(--muted); font-size:.72rem; margin-top:6px;
             text-transform:uppercase; letter-spacing:.09em; }

.pill { display:inline-flex; align-items:center; gap:9px; padding:7px 15px;
        border-radius:999px; font-size:.84rem; font-weight:600; border:1px solid currentColor; }
.dot { width:9px; height:9px; border-radius:50%; background:currentColor; flex:none; }
.dot.live { animation: pulse 1.4s ease-in-out infinite; }
@keyframes pulse { 0%,100%{opacity:.45;transform:scale(.85);} 50%{opacity:1;transform:scale(1.15);} }

.stage { text-align:center; padding:16px 8px; border:1px solid var(--border);
         border-radius:12px; background: rgba(255,255,255,.02);
         transition: transform .25s ease, border-color .25s ease; }
.stage:hover { transform: translateY(-3px); border-color: var(--accent); }
.stage .ico { font-size:1.6rem; line-height:1; }
.stage .name { font-weight:600; margin-top:8px; font-size:.86rem; }

.empty { text-align:center; padding:64px 20px; border:1px dashed var(--border);
         border-radius:16px; background: rgba(19,24,37,.4); }
.empty .ico { font-size:2.8rem; }
.empty .txt { color:var(--muted); font-size:1.05rem; margin-top:14px; }

.stButton > button, .stDownloadButton > button {
    border-radius:10px; font-weight:600; transition: transform .2s ease, box-shadow .2s ease;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(90deg,#7c5cff 0%,#5d3fff 100%); border:none; color:#fff;
}
.stButton > button[kind="primary"]:hover:not(:disabled) {
    transform: translateY(-2px); box-shadow: 0 8px 22px rgba(124,92,255,.42);
}
.stButton > button:disabled { opacity:.45; }

.stTabs [data-baseweb="tab-list"] { gap:6px; padding:6px; border-radius:12px;
    background: rgba(255,255,255,.03); border:1px solid var(--border); }
.stTabs [data-baseweb="tab"] { background:transparent; color:var(--muted);
    border-radius:8px; font-weight:500; padding:8px 18px; }
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg,rgba(124,92,255,.28),rgba(0,212,255,.10));
    color:#fff !important; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display:none; }

[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input { background: rgba(255,255,255,.04); border-radius:10px; }
[data-testid="stChatMessage"] { background: rgba(19,24,37,.62);
    border:1px solid var(--border); border-radius:14px; }
code { color: var(--accent-2); }
hr { border-color: var(--border); }
.foot { text-align:center; color:#5a6075; font-size:.78rem; margin-top:34px; }
</style>
"""
st.html(CSS)


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


# ==========================================================================
# Backend client
# ==========================================================================
class BackendError(RuntimeError):
    """A failure talking to the backend, already phrased for the user."""


@dataclass
class MeetingResult:
    """Normalised /process response — tolerant of missing or differently named fields."""

    title: str = "Untitled meeting"
    summary: str = ""
    action_items: str = ""
    key_decisions: str = ""
    questions: str = ""
    transcript: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "MeetingResult":
        if not isinstance(payload, dict):
            raise BackendError("Backend returned an unexpected response shape.")

        def text(*keys: str) -> str:
            for key in keys:
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
                if isinstance(value, list) and value:
                    return "\n".join(f"• {str(v).strip()}" for v in value if str(v).strip())
            return ""

        raw_title = clean_text(text("title", "meeting_title", "name"))
        # Keep the header to one line: some models return a paragraph as "title".
        first_line = next((ln.strip() for ln in raw_title.splitlines() if ln.strip()), "")
        if len(first_line) > 120:
            first_line = first_line[:117].rstrip() + "…"

        return cls(
            title=first_line or "Untitled meeting",
            summary=text("summary", "executive_summary"),
            action_items=text("action_items", "actions", "tasks"),
            key_decisions=text("key_decisions", "decisions"),
            questions=text("questions", "open_questions"),
            transcript=text("transcript", "text"),
            raw=payload,
        )


def _session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2, backoff_factor=0.6, status_forcelist=(502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}), raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def normalise_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url


def _request(method: str, base_url: str, path: str, *, timeout, **kwargs) -> Any:
    base = normalise_url(base_url)
    if not base:
        raise BackendError("No API base URL configured.")
    try:
        with _session() as session:
            response = session.request(method, base + path, timeout=timeout, **kwargs)
    except requests.exceptions.ConnectTimeout:
        raise BackendError("Connection timed out — the backend may be asleep.") from None
    except requests.exceptions.ReadTimeout:
        raise BackendError("The backend accepted the request but took too long to answer.") from None
    except requests.exceptions.SSLError:
        raise BackendError("TLS handshake failed — check the https:// URL.") from None
    except requests.exceptions.ConnectionError:
        raise BackendError(f"Cannot reach {base} — is the backend running?") from None
    except requests.exceptions.RequestException as exc:
        raise BackendError(f"Request failed: {exc}") from None

    if response.status_code >= 400:
        detail = response.text.strip()
        try:
            body = response.json()
            detail = str(body.get("detail", body))
        except ValueError:
            pass
        raise BackendError(f"HTTP {response.status_code}: {detail[:300] or response.reason}")

    try:
        return response.json()
    except ValueError:
        raise BackendError("Backend did not return valid JSON.") from None


def api_health(base_url: str, timeout=HEALTH_TIMEOUT) -> tuple[bool, str]:
    """Probe the backend. Returns (is_online, message). Never raises."""
    base = normalise_url(base_url)
    if not base:
        return False, "No API base URL configured."
    for path in ("/health", "/docs", "/"):
        try:
            with _session() as session:
                response = session.get(base + path, timeout=timeout)
            if response.status_code < 500:
                return True, f"Responded {response.status_code} on {path}"
        except requests.exceptions.Timeout:
            return False, "Timed out — cold start can take 30–60s, retrying shortly."
        except requests.exceptions.RequestException:
            continue
    return False, f"No response from {base}"


def api_process(base_url: str, source: str, chunk_minutes: int = 10) -> MeetingResult:
    payload = _request(
        "POST", base_url, "/process",
        json={"source": source, "chunk_minutes": chunk_minutes},
        timeout=PROCESS_TIMEOUT,
    )
    return MeetingResult.from_payload(payload)


def api_ask(base_url: str, question: str) -> str:
    payload = _request(
        "POST", base_url, "/ask", json={"question": question}, timeout=ASK_TIMEOUT
    )
    if isinstance(payload, dict):
        for key in ("answer", "result", "response", "output"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    raise BackendError("Backend returned an empty answer.")


# ==========================================================================
# Non-blocking health probe
# ==========================================================================
# The probe runs on a worker thread and publishes into a module-level cache.
# The script NEVER waits on the network during a page render, so first paint is
# instant even when the backend is dead, remote or cold-starting.
_PROBE_LOCK = threading.Lock()
_PROBE_CACHE: dict[str, dict] = {}   # url -> {status, detail, ts, running}


def _probe_worker(url: str) -> None:
    online, detail = api_health(url, QUICK_TIMEOUT)
    with _PROBE_LOCK:
        _PROBE_CACHE[url] = {
            "status": "online" if online else "offline",
            "detail": detail,
            "ts": time.monotonic(),
            "running": False,
        }


def start_probe(url: str) -> None:
    """Kick off a background probe unless one is already in flight."""
    if not url:
        return
    with _PROBE_LOCK:
        entry = _PROBE_CACHE.get(url)
        if entry and entry.get("running"):
            return
        _PROBE_CACHE[url] = {
            "status": entry["status"] if entry else "unknown",
            "detail": entry["detail"] if entry else "Checking…",
            "ts": entry["ts"] if entry else 0.0,
            "running": True,
        }
    # Daemon thread: never touches Streamlit APIs, only the cache above.
    threading.Thread(target=_probe_worker, args=(url,), daemon=True).start()


def read_probe(url: str) -> dict:
    with _PROBE_LOCK:
        entry = _PROBE_CACHE.get(url)
        return dict(entry) if entry else {
            "status": "unknown", "detail": "Checking…", "ts": 0.0, "running": False,
        }


# ==========================================================================
# State
# ==========================================================================
DEFAULT_STATE: dict = {
    "api_url": DEFAULT_API_URL,
    "result": None,
    "chat": [],
    "backend_state": "unknown",       # unknown | online | offline
    "backend_detail": "Not checked yet.",
    "checked_at": None,
    "source_path": "",
    "keepalive": KEEPALIVE_DEFAULT,
    "last_ping": 0.0,                 # time.monotonic() of the last probe
    "pinged_url": "",                 # URL that was last probed
}
for _key, _value in DEFAULT_STATE.items():
    st.session_state.setdefault(_key, _value)


def reset_session() -> None:
    st.session_state.result = None
    st.session_state.chat = []
    st.session_state.source_path = ""


def check_backend(quick: bool = False) -> bool:
    """Blocking probe — only for the explicit 'wake backend' button."""
    online, detail = api_health(
        st.session_state.api_url, QUICK_TIMEOUT if quick else HEALTH_TIMEOUT
    )
    st.session_state.backend_state = "online" if online else "offline"
    st.session_state.backend_detail = detail
    st.session_state.checked_at = datetime.now().strftime("%H:%M:%S")
    st.session_state.last_ping = time.monotonic()
    st.session_state.pinged_url = normalise_url(st.session_state.api_url)
    with _PROBE_LOCK:   # keep the shared cache in sync with the manual result
        _PROBE_CACHE[st.session_state.pinged_url] = {
            "status": st.session_state.backend_state, "detail": detail,
            "ts": time.monotonic(), "running": False,
        }
    return online


def auto_ping() -> None:
    """Publish the latest probe result and schedule the next one. Never blocks.

    Called on every render of the status fragment: it reads whatever the worker
    thread has finished, then decides if a fresh probe is due.
    """
    if not AUTO_PING_ON_LOAD:
        return

    url = normalise_url(st.session_state.api_url)
    entry = read_probe(url)

    # Publish the worker's finding into session state for rendering.
    st.session_state.backend_state = entry["status"]
    st.session_state.backend_detail = entry["detail"]
    if entry["ts"]:
        st.session_state.last_ping = entry["ts"]
        st.session_state.checked_at = datetime.now().strftime("%H:%M:%S") \
            if url != st.session_state.pinged_url else st.session_state.checked_at
        st.session_state.pinged_url = url

    if entry["running"]:
        return   # a probe is already in flight

    never = entry["ts"] == 0.0
    elapsed = time.monotonic() - entry["ts"]
    interval = KEEPALIVE_INTERVAL if entry["status"] == "online" else 30
    due = st.session_state.keepalive and elapsed >= interval
    if never or due:
        start_probe(url)


# ==========================================================================
# Text helpers
# ==========================================================================
_TAGS = r"think|thinking|thought|thoughts|reasoning|reflection|scratchpad|analysis"
# Closed block: <think> … </think>
_THINK_BLOCK = re.compile(rf"<\s*({_TAGS})\s*>.*?<\s*/\s*\1\s*>", re.DOTALL | re.IGNORECASE)
# Orphan close: everything before </think> is scratchpad, the answer follows it.
_THINK_ORPHAN_CLOSE = re.compile(rf"^.*?<\s*/\s*(?:{_TAGS})\s*>", re.DOTALL | re.IGNORECASE)
# Any leftover bare tag.
_THINK_TAG = re.compile(rf"<\s*/?\s*(?:{_TAGS})\s*>", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*(?:[-*•\u2022]|\d+[.)])\s+")


def clean_text(text: str | None) -> str:
    """Strip reasoning-model scratchpads and outer code fences, keep real content.

    Handles the messy variants seen in the wild:
      * HTML-escaped tags (``&lt;think&gt;``) — unescaped first, so they still match
      * alternate tag names (thinking / reasoning / analysis / scratchpad …)
      * an orphan ``</think>`` with no opener — keep only what follows it
      * an orphan ``<think>`` with no closer — drop the tag, keep the text
      * stray ``**`` bold wrappers around the whole blob
    """
    if not text:
        return ""

    # Escaped tags arrive as &lt;think&gt; and would never match a regex on "<".
    cleaned = html.unescape(str(text))
    cleaned = _THINK_BLOCK.sub("", cleaned)

    # An unmatched closing tag means the scratchpad ran up to it: keep the tail,
    # but only if that tail actually has content (else we'd delete the answer).
    if re.search(rf"<\s*/\s*(?:{_TAGS})\s*>", cleaned, re.IGNORECASE):
        tail = _THINK_ORPHAN_CLOSE.sub("", cleaned, count=1)
        if tail.strip():
            cleaned = tail

    cleaned = _THINK_TAG.sub("", cleaned)
    cleaned = re.sub(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$", "", cleaned.strip())
    cleaned = re.sub(r"^\*\*(.*)\*\*$", r"\1", cleaned.strip(), flags=re.DOTALL)
    return cleaned.strip()


def count_items(text: str | None) -> int:
    lines = [ln.strip() for ln in clean_text(text).splitlines() if ln.strip()]
    bulleted = [ln for ln in lines if _BULLET_RE.match(ln)]
    return len(bulleted) if bulleted else len(lines)


def word_count(text: str | None) -> int:
    return len(clean_text(text).split())


# ==========================================================================
# HTML components (every interpolated value is escaped)
# ==========================================================================
def hero(title: str, subtitle: str) -> None:
    st.html(f"<div class='hero'><h1 class='grad'>{esc(title)}</h1><p>{esc(subtitle)}</p></div>")


def kpi(label: str, value: object, color: str) -> None:
    st.html(
        f"<div class='kpi'><div class='kpi-value' style=\"background:linear-gradient(90deg,"
        f"{esc(color)},{ACCENT});-webkit-background-clip:text;background-clip:text;"
        f"-webkit-text-fill-color:transparent;\">{esc(value)}</div>"
        f"<div class='kpi-label'>{esc(label)}</div></div>"
    )


def insight_card(icon: str, label: str, body: str, color: str) -> None:
    text = (body or "").strip()
    css_class = "card-body" if text else "card-body empty"
    text = text or "Nothing extracted for this section."
    st.html(
        f"<div class='card'><div class='card-head' style='color:{esc(color)};'>"
        f"<span style='font-size:1.15rem;'>{esc(icon)}</span>{esc(label)}</div>"
        f"<div class='{css_class}'>{esc(text)}</div></div>"
    )


def status_pill(color: str, title: str, detail: str, live: bool = False) -> None:
    dot = "dot live" if live else "dot"
    st.html(
        f"<div style='display:flex;align-items:center;gap:12px;flex-wrap:wrap;'>"
        f"<span class='pill' style='color:{esc(color)};'><span class='{dot}'></span>"
        f"{esc(title)}</span>"
        f"<span style='color:var(--muted);font-size:.86rem;'>{esc(detail)}</span></div>"
    )


def stage_strip(stages: list[tuple[str, str, str]]) -> None:
    cells = "".join(
        f"<div class='stage'><div class='ico'>{esc(i)}</div>"
        f"<div class='name' style='color:{esc(c)};'>{esc(n)}</div></div>"
        for i, n, c in stages
    )
    st.html(
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));"
        f"gap:12px;'>{cells}</div>"
    )


def empty_state(icon: str, text: str) -> None:
    st.html(f"<div class='empty'><div class='ico'>{esc(icon)}</div>"
            f"<div class='txt'>{esc(text)}</div></div>")


# ==========================================================================
# Sidebar
# ==========================================================================
@st.fragment(run_every=KEEPALIVE_TICK)
def backend_status_panel() -> None:
    """Live status block: reads the background probe, never waits on the network."""
    auto_ping()

    state = st.session_state.backend_state
    colors = {"online": SUCCESS, "offline": DANGER, "unknown": MUTED}
    labels = {"online": "Online", "offline": "Unreachable", "unknown": "Checking…"}
    status_pill(
        colors[state], labels[state],
        f"checked {st.session_state.checked_at}" if st.session_state.checked_at else "",
        live=state in ("online", "unknown"),
    )
    st.caption(st.session_state.backend_detail)

    if state == "offline" and st.session_state.keepalive:
        st.caption("⏳ Auto-retrying every 30s — you can still process meanwhile.")

    if st.button("🔄 Check / wake backend now", use_container_width=True):
        with st.spinner("Pinging backend…"):
            check_backend()          # manual click gets the patient timeout
        st.rerun()

    st.toggle(
        "Auto keep-alive", key="keepalive",
        help=f"Ping the backend every {KEEPALIVE_INTERVAL // 60} min so free-tier "
             "hosts don't fall asleep while you work.",
    )


def render_sidebar() -> None:
    with st.sidebar:
        st.html(
            "<div style='text-align:center;padding:14px 0 22px;'>"
            "<div class='grad' style='font-size:1.7rem;font-weight:800;'>🎙️ Meeting Insights</div>"
            "<div style='color:#8b92a7;font-size:.8rem;margin-top:6px;'>"
            "AI-powered meeting intelligence</div></div>"
        )

        st.subheader("⚙️ Connection", divider="gray")
        # Bind by key only. Passing value= for an existing session_state key raises.
        st.text_input(
            "API base URL", key="api_url", placeholder=DEFAULT_API_URL,
            help="Root URL of your FastAPI backend, e.g. https://my-api.onrender.com",
        )

        backend_status_panel()

        st.subheader("📊 Session", divider="gray")
        result: MeetingResult | None = st.session_state.result
        if result:
            st.metric("Meeting", result.title[:28] + ("…" if len(result.title) > 28 else ""))
            st.metric("Questions asked",
                      sum(1 for m in st.session_state.chat if m["role"] == "user"))
        else:
            st.caption("No meeting processed yet.")

        if st.button("🗑️ Clear session", use_container_width=True):
            reset_session()
            st.rerun()

        st.subheader("💡 How it works", divider="gray")
        st.markdown(
            "1. Provide a YouTube URL, a path, or upload a file\n"
            "2. Audio is chunked and transcribed with Whisper\n"
            "3. An LLM extracts summary, actions and decisions\n"
            "4. Ask follow-ups answered by RAG over the transcript"
        )
        st.html("<div style='text-align:center;color:#5a6075;font-size:.72rem;margin-top:18px;'>"
                "v2.0 • FastAPI · LangChain · Groq</div>")


# ==========================================================================
# Tab 1 — Process
# ==========================================================================
def run_processing(source: str, chunk_minutes: int) -> None:
    with st.status("Processing meeting…", expanded=True) as status:
        # If the probe never succeeded, try a patient wake-up first — but treat
        # a failed probe as a warning, not a blocker, and attempt /process anyway.
        if st.session_state.backend_state != "online":
            st.write("Backend not confirmed yet — sending a wake-up call…")
            if check_backend():
                st.write("✅ Backend responded.")
            else:
                st.write(f"⚠️ No reply to the health probe ({st.session_state.backend_detail}). "
                         "Trying /process regardless…")

        st.write("Sending job to the backend — transcription can take several minutes.")
        try:
            result = api_process(st.session_state.api_url, source, chunk_minutes)
        except BackendError as exc:
            status.update(label="Processing failed", state="error")
            st.error(str(exc))
            st.caption(
                f"Tried: `POST {normalise_url(st.session_state.api_url)}/process`. "
                "Check the URL in the sidebar, that the backend is running, and that "
                "it exposes a /process route."
            )
            return
        st.session_state.result = result
        st.session_state.chat = []
        # A successful call proves the backend is up, whatever /health said.
        st.session_state.backend_state = "online"
        st.session_state.backend_detail = "Confirmed by a successful /process call."
        status.update(label=f"Done — {result.title}", state="complete", expanded=False)
    st.success("Meeting processed. Open the **Insights** tab.", icon="✅")


def render_process_tab() -> None:
    st.subheader("🎥 Input source")
    st.caption("Paste a YouTube URL or a server-side file path, or upload a recording below.")

    # Uploader lives OUTSIDE the form so the file is saved the moment it's picked.
    uploaded = st.file_uploader(
        "Upload audio/video (optional)",
        type=["mp3", "wav", "m4a", "mp4", "mkv", "aac", "flac", "ogg", "webm"],
    )
    if uploaded is not None:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        # Basename only, so a crafted filename cannot escape the folder.
        save_path = UPLOAD_DIR / Path(uploaded.name).name
        save_path.write_bytes(uploaded.getbuffer())
        st.session_state.source_path = str(save_path.resolve())
        st.success(f"Saved `{save_path}` ({uploaded.size / 1_048_576:.1f} MB)")

    # A FORM is the fix for "the button won't click": a plain text_input does not
    # rerun the script until you press Enter or blur it, so a button gated on its
    # value stays stale/disabled while you type. A form submits the current text
    # together with the click, in one go — and the button is never disabled.
    with st.form("process_form", clear_on_submit=False, border=False):
        left, right = st.columns([3, 1], vertical_alignment="bottom")
        typed_source = left.text_input(
            "Source",
            placeholder="https://youtube.com/watch?v=…  or  /data/meeting.mp3",
            label_visibility="collapsed",
        )
        chunk_minutes = right.number_input("Chunk (min)", 2, 30, 10, 1)
        submitted = st.form_submit_button(
            "⚡ Process meeting", type="primary", use_container_width=False
        )

    if st.session_state.source_path:
        st.caption(f"Uploaded file ready: `{st.session_state.source_path}`")

    if submitted:
        source = typed_source.strip() or st.session_state.source_path
        if not source:
            st.warning("Please paste a URL/path or upload a file first.", icon="⚠️")
        else:
            run_processing(source, int(chunk_minutes))

    st.subheader("🔧 Pipeline", divider="gray")
    stage_strip([
        ("🎵", "Audio", ACCENT_2), ("📝", "Transcribe", ACCENT), ("🧠", "Summarize", DANGER),
        ("📌", "Extract", WARNING), ("🗄️", "Vectorize", SUCCESS),
    ])


# ==========================================================================
# Tab 2 — Insights
# ==========================================================================
def render_insights_tab() -> None:
    result: MeetingResult | None = st.session_state.result
    if not result:
        empty_state("📋", "No insights yet — process a meeting first.")
        return

    st.html(
        "<div class='card' style='display:flex;justify-content:space-between;align-items:center;"
        "gap:16px;flex-wrap:wrap;'><div>"
        "<div style='color:var(--muted);font-size:.74rem;letter-spacing:.08em;"
        "text-transform:uppercase;'>Meeting title</div>"
        f"<div style='font-size:1.5rem;font-weight:700;margin-top:4px;'>🎙️ {esc(result.title)}</div>"
        "</div><span class='pill' style='color:#00d68f;'><span class='dot'></span>Processed</span></div>"
    )

    metrics = [
        ("Action items", count_items(result.action_items), WARNING),
        ("Key decisions", count_items(result.key_decisions), SUCCESS),
        ("Open questions", count_items(result.questions), DANGER),
        ("Summary words", word_count(result.summary), ACCENT_2),
    ]
    for column, (label, value, color) in zip(st.columns(4), metrics):
        with column:
            kpi(label, value, color)

    st.subheader("📊 Breakdown", divider="gray")
    for icon, label, body, color in [
        ("📄", "Executive summary", result.summary, ACCENT_2),
        ("⚡", "Action items", result.action_items, WARNING),
        ("✅", "Key decisions", result.key_decisions, SUCCESS),
        ("❓", "Open questions", result.questions, DANGER),
    ]:
        insight_card(icon, label, clean_text(body), color)

    if result.transcript:
        with st.expander("📜 Full transcript"):
            st.text(clean_text(result.transcript))

    st.subheader("📥 Export", divider="gray")
    downloads = [
        ("Summary", clean_text(result.summary), "summary.txt", "text/plain"),
        ("Action items", clean_text(result.action_items), "action_items.txt", "text/plain"),
        ("Decisions", clean_text(result.key_decisions), "decisions.txt", "text/plain"),
        ("Full JSON", json.dumps(result.raw or {}, indent=2, ensure_ascii=False),
         "meeting_insights.json", "application/json"),
    ]
    for column, (label, data, filename, mime) in zip(st.columns(4), downloads):
        column.download_button(
            label, data=data or "(empty)", file_name=filename, mime=mime,
            use_container_width=True, disabled=not data,
        )


# ==========================================================================
# Tab 3 — Q&A
# ==========================================================================
SUGGESTIONS = [
    "What was the main topic of this meeting?",
    "List all action items with their owners.",
    "Which decisions were finalised?",
]


def render_qa_tab() -> None:
    if not st.session_state.result:
        empty_state("💬", "Process a meeting first to enable Q&A.")
        return

    st.subheader("💬 Ask anything about the meeting")
    st.caption("Answers come from semantic search over the meeting transcript.")

    for column, question in zip(st.columns(len(SUGGESTIONS)), SUGGESTIONS):
        if column.button(question, use_container_width=True, key=f"sugg::{question}"):
            st.session_state.chat.append({"role": "user", "content": question})
            st.rerun()

    # Everything below is drawn into ONE container that is created BEFORE the
    # chat_input widget. That ordering is what keeps the input pinned under the
    # conversation — previously a new turn was drawn after the widget, so the
    # input box ended up sandwiched between messages.
    history = st.container()

    with history:
        for message in st.session_state.chat:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # A trailing user turn means the answer hasn't been fetched yet. Fetch it
    # inside the same container so the reply lands directly under the question.
    awaiting = bool(st.session_state.chat) and st.session_state.chat[-1]["role"] == "user"
    if awaiting:
        with history, st.chat_message("assistant"):
            with st.spinner("Searching the transcript…"):
                try:
                    answer = clean_text(api_ask(
                        st.session_state.api_url, st.session_state.chat[-1]["content"]
                    ))
                    answer = answer or "_The backend returned an empty answer._"
                except BackendError as exc:
                    answer = f"⚠️ {exc}"
            st.markdown(answer)
        st.session_state.chat.append({"role": "assistant", "content": answer})

    if question := st.chat_input("Ask a question about the meeting…"):
        st.session_state.chat.append({"role": "user", "content": question})
        st.rerun()

    if st.session_state.chat and st.button("🗑️ Clear chat"):
        st.session_state.chat = []
        st.rerun()


# ==========================================================================
# Layout
# ==========================================================================
def main() -> None:
    render_sidebar()
    hero(APP_TITLE, APP_SUB)

    process_tab, insights_tab, qa_tab = st.tabs(
        ["🚀 Process meeting", "📋 Insights", "💬 Ask questions"]
    )
    with process_tab:
        render_process_tab()
    with insights_tab:
        render_insights_tab()
    with qa_tab:
        render_qa_tab()

    st.html("<div class='foot'>Built with FastAPI · LangChain · Groq Whisper · Streamlit</div>")
    st.session_state.first_paint_done = True


main()
