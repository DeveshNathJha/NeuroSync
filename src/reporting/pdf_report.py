"""
src/reporting/pdf_report.py
---------------------------
Neutral PDF of a session's observation notes: subject pseudonym, date,
duration, consent details (roles, not names), the table of CONFIRMED events,
the report text, and the disclaimer in every page footer.

Uses fpdf2 core fonts (latin-1); other characters are replaced safely.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from src.config import settings
from src.core.session import Session
from src.reporting.reasoner import mmss

_REPLACE = {"–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...", "•": "-", "²": "2"}


def _latin1(text: str) -> str:
    for a, b in _REPLACE.items():
        text = text.replace(a, b)
    return text.encode("latin-1", errors="replace").decode("latin-1")


class _NotesPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 9, _latin1("NeuroSync – Session Observation Notes"), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(120, 120, 120)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)

    def footer(self):
        self.set_y(-18)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(110, 110, 110)
        self.multi_cell(0, 3.2, _latin1(settings.app.disclaimer + f"  Page {self.page_no()}/{{nb}}"))
        self.set_text_color(0, 0, 0)


def render_pdf(session: Session, report: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = _NotesPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.add_page()

    c = session.consent
    started = datetime.fromtimestamp(session.started_at).strftime("%Y-%m-%d %H:%M") if session.started_at else "-"
    meta = [
        ("Subject (pseudonym)", c.subject_id if c else "-"),
        ("Date", started),
        ("Duration", mmss(session.elapsed())),
        ("Mode", "live session" if session.mode == "live" else "recorded video"),
        ("Consent given by", c.given_by if c else "-"),
        ("Recorded by", c.recorded_by if c else "-"),
        ("Purpose", c.purpose if c else "-"),
    ]
    pdf.set_font("Helvetica", "", 10)
    for k, v in meta:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(45, 6, _latin1(k))
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, _latin1(str(v)), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Confirmed observations", new_x="LMARGIN", new_y="NEXT")
    events = session.confirmed()
    if not events:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, "None confirmed.", new_x="LMARGIN", new_y="NEXT")
    else:
        widths = (28, 72, 22, 68)
        pdf.set_font("Helvetica", "B", 9)
        for w, h in zip(widths, ("Time", "Observation", "Detector conf.", "Reviewer note")):
            pdf.cell(w, 6, h, border=1)
        pdf.ln()
        pdf.set_font("Helvetica", "", 9)
        for e in events:
            row = (f"{mmss(e.start)}-{mmss(e.end)}", e.label, f"{e.confidence:.2f}", (e.note or "")[:60])
            for w, val in zip(widths, row):
                pdf.cell(w, 6, _latin1(val), border=1)
            pdf.ln()
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Notes", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, _latin1(report.get("text", "")))
    pdf.output(str(path))
    return path
