"""
src/reporting/reasoner.py
-------------------------
Session notes from CONFIRMED events only.

Two modes:
  template  deterministic text built from the confirmed events (default; always available)
  llm       an optional local model (llama-cpp + a GGUF file such as Phi-3 mini) that
            rewrites the same facts in prose; loaded lazily, never required

Both outputs go through guard.sanitize(), and the fixed disclaimer is appended
after sanitising. generate() is a pure function of (session, audience), so the
UI can run it in a background thread.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Optional

from src.config import resolve, settings
from src.core.events import EVENT_LABELS, Event
from src.core.session import Session
from src.reporting import guard
from src.utils.logger import logger

AUDIENCES = ("professional", "family")
LLM = Callable[[str], str]


def mmss(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _facts(session: Session) -> dict:
    """Everything a report may mention – derived from confirmed events only."""
    events: list[Event] = session.confirmed()
    by_id = {e.id: e for e in session.events}
    lines = []
    for e in events:
        linked = [by_id[i].label.lower() for i in e.linked if i in by_id and by_id[i].status == "confirmed"]
        lines.append({
            "start": mmss(e.start), "end": mmss(e.end), "label": e.label,
            "duration_s": round(e.duration, 1), "with": linked, "note": bool(e.note),
        })
    return {"summary": session.summary(), "events": lines}


class ReportGenerator:
    def __init__(self, llm_path: Optional[Path] = None, llm: Optional[LLM] = None):
        self.llm_path = Path(llm_path) if llm_path is not None else resolve(settings.report.llm_path)
        self._llm = llm
        self._tried_load = llm is not None

    # ------------------------------------------------------------------ llm loading
    def _get_llm(self) -> Optional[LLM]:
        if self._tried_load:
            return self._llm
        self._tried_load = True
        if not self.llm_path.exists():
            logger.info("No local language model found – using template reports.")
            return None
        try:
            from llama_cpp import Llama  # optional dependency
        except ImportError:
            logger.info("llama-cpp-python not installed – using template reports.")
            return None
        try:
            model = Llama(model_path=str(self.llm_path), n_ctx=2048,
                          n_threads=settings.report.llm_threads, verbose=False)
        except Exception as exc:  # noqa: BLE001 – any load failure falls back to the template
            logger.warning(f"Language model failed to load ({exc}) – using template reports.")
            return None

        def run(prompt: str) -> str:
            out = model(prompt, max_tokens=settings.report.llm_max_tokens, temperature=0.0,
                        stop=["<|end|>"], echo=False)
            return out["choices"][0]["text"].strip()

        self._llm = run
        return run

    # ------------------------------------------------------------------ public
    @property
    def available_mode(self) -> str:
        return "llm" if self._get_llm() else "template"

    def generate(self, session: Session, audience: str = "professional") -> dict:
        if audience not in AUDIENCES:
            raise ValueError(f"audience must be one of {AUDIENCES}")
        facts = _facts(session)
        llm = self._get_llm()
        mode = "template"
        body = self._template(facts, audience)
        if llm is not None and facts["events"]:
            try:
                body = llm(self._prompt(facts, audience)).strip() or body
                mode = "llm"
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Report generation with the language model failed ({exc}); using template.")
        removed = guard.check(body)
        body = guard.sanitize(body)
        text = f"{body.rstrip()}\n\n{settings.app.disclaimer}"
        return {"text": text, "mode": mode, "guard_removed": removed}

    # ------------------------------------------------------------------ builders
    @staticmethod
    def _template(facts: dict, audience: str) -> str:
        s, events = facts["summary"], facts["events"]
        plain = audience == "family"
        lines = [f"Session length: {mmss(s['duration_s'])} (mm:ss)."]
        if not events:
            lines.append("No observations were confirmed by the reviewer for this session.")
        else:
            lines.append(f"Confirmed observations: {s['confirmed_events']} "
                         f"(of {s['suggested_events']} suggested by the software).")
            lines.append("")
            for kind, count in s["counts_by_kind"].items():
                secs = s["seconds_by_kind"].get(kind, 0)
                label = EVENT_LABELS[kind]
                lines.append(f"- {label}: {count} time{'s' if count != 1 else ''}, about {round(secs)} s in total.")
            lines.append("")
            lines.append("When they happened:" if plain else "Timeline of confirmed observations:")
            for e in events:
                extra = f" (at the same time: {', '.join(e['with'])})" if e["with"] else ""
                lines.append(f"- {e['start']}–{e['end']} {e['label']}{extra}")
            lines.append(f"First observation at {events[0]['start']}, last at {events[-1]['start']}.")
        if s.get("mean_heart_rate"):
            hr = f"Average estimated heart rate from the camera: {s['mean_heart_rate']} beats per minute"
            if s.get("baseline_heart_rate"):
                hr += f" (personal baseline {round(s['baseline_heart_rate'])})"
            lines.append(hr + ". Camera-based heart rate is an estimate and can be affected by light and movement.")
        notes = sum(1 for e in events if e["note"])
        if notes:
            lines.append(f"The reviewer added notes to {notes} observation{'s' if notes != 1 else ''}.")
        return "\n".join(lines)

    @staticmethod
    def _prompt(facts: dict, audience: str) -> str:
        style = ("plain, warm language for a family member; short sentences; no jargon"
                 if audience == "family" else "concise, neutral language for a professional")
        rules = (
            "You write session observation notes. Use ONLY the facts below.\n"
            "Describe what was observed, when and how often. Do not interpret, diagnose, name or suggest any "
            "condition, and do not give treatment advice. If heart-rate rises happened at the same time as an "
            "observation, mention only the timing. Do not add a disclaimer.\n"
            f"Style: {style}."
        )
        s = facts["summary"]
        fact_lines = [f"Session length: {mmss(s['duration_s'])}",
                      f"Confirmed observations: {s['confirmed_events']}"]
        for e in facts["events"]:
            extra = f"; same time as: {', '.join(e['with'])}" if e["with"] else ""
            fact_lines.append(f"{e['start']}-{e['end']}: {e['label']} ({e['duration_s']} s{extra})")
        if s.get("mean_heart_rate"):
            fact_lines.append(f"Mean estimated heart rate: {s['mean_heart_rate']} bpm")
        return f"<|user|>\n{rules}\n\nFACTS:\n" + "\n".join(fact_lines) + "\n<|end|>\n<|assistant|>"
