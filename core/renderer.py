"""Render resume JSON into plain text, Markdown, ATS-friendly DOCX and PDF.

Every format is driven by the same list of layout blocks from build_blocks(), so they always
contain identical content.
"""
import io
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

SECTION_TITLES = {
    "summary": "Professional Summary",
    "skills": "Skills",
    "experience": "Professional Experience",
    "projects": "Projects",
    "education": "Education",
    "certifications": "Certifications",
    "achievements": "Achievements",
}
DEFAULT_ORDER = ["summary", "skills", "experience", "projects", "education",
                 "certifications", "achievements", "additional_sections"]

# One quiet palette for PDF and DOCX: near-black text, a deep navy accent, grey for secondary details.
INK, ACCENT, MUTED, RULE = "#1F2933", "#1F3A5F", "#52606D", "#C3CCD6"


def _s(v) -> str:
    return str(v).strip() if v else ""


def _join(*parts, sep=" | ") -> str:
    return sep.join(p for p in (_s(x) for x in parts) if p)


def _dates(start, end) -> str:
    return _join(start, end, sep=" – ")


def _order(r: dict) -> list[str]:
    order = [s for s in (r.get("section_order") or []) if s in DEFAULT_ORDER]
    return list(dict.fromkeys(order + DEFAULT_ORDER))


def _degree(ed: dict) -> str:
    """'MSc Computer Science' + field 'Computer Science (3rd semester)' -> 'MSc Computer Science (3rd semester)'."""
    degree, field = _s(ed.get("degree")), _s(ed.get("field"))
    if not field:
        return degree
    core = re.sub(r"\s*\([^)]*\)", "", field).strip()
    if degree and core and core.lower() in degree.lower():
        extra = " ".join(re.findall(r"\([^)]*\)", field))
        return f"{degree} {extra}".strip() if extra and extra not in degree else degree
    return _join(degree, field, sep=" in ")


def _grade(g: str) -> str:
    # A bare "8.9/10" or "85%" means nothing without a label.
    return g if re.search(r"[A-Za-z]", g) else f"Grade: {g}"


def build_blocks(r: dict) -> list[tuple]:
    """Flatten resume JSON into (kind, value) layout blocks."""
    b: list[tuple] = [("name", _s(r.get("name")) or "Your Name")]
    if _s(r.get("headline")):
        b.append(("headline", _s(r["headline"])))
    c = r.get("contact") or {}
    contact = [_s(x) for x in [*(c.get(k) for k in ("email", "phone", "location", "linkedin", "github", "portfolio")),
                               *(c.get("other") or [])] if _s(x)]
    if contact:
        b.append(("contact", contact))

    for sec in _order(r):
        if sec == "summary" and _s(r.get("summary")):
            b += [("heading", SECTION_TITLES[sec]), ("para", _s(r["summary"]))]
        elif sec == "skills":
            groups = [g for g in r.get("skills") or [] if g.get("items")]
            if groups:
                b.append(("heading", SECTION_TITLES[sec]))
                for g in groups:
                    cat = _s(g.get("category"))
                    label = "" if cat.lower() in ("skills", "skill") else cat  # avoid "SKILLS / Skills: ..."
                    b.append(("label", (label, ", ".join(_s(i) for i in g["items"] if _s(i)))))
        elif sec == "experience" and r.get("experience"):
            b.append(("heading", SECTION_TITLES[sec]))
            for e in r["experience"]:
                b.append(("entry", (_s(e.get("title")), _join(e.get("company"), e.get("location"), sep=", "),
                                    _dates(e.get("start"), e.get("end")))))
                b += [("bullet", _s(x)) for x in e.get("bullets") or [] if _s(x)]
        elif sec == "projects" and r.get("projects"):
            b.append(("heading", SECTION_TITLES[sec]))
            for p in r["projects"]:
                b.append(("entry", (_s(p.get("name")), _s(p.get("role")), _s(p.get("dates")))))
                tech = ", ".join(_s(t) for t in p.get("tech") or [] if _s(t))
                sub = _join(f"Tech: {tech}" if tech else "", p.get("link"))
                if sub:
                    b.append(("sub", sub))
                b += [("bullet", _s(x)) for x in p.get("bullets") or [] if _s(x)]
        elif sec == "education" and r.get("education"):
            b.append(("heading", SECTION_TITLES[sec]))
            for ed in r["education"]:
                degree = _degree(ed)
                where = _join(ed.get("institution") if degree else "", ed.get("location"), sep=", ")
                if _s(ed.get("grade")):
                    where = _join(where, _grade(_s(ed["grade"])), sep="  ·  ")
                b.append(("entry", (degree or _s(ed.get("institution")), where, _dates(ed.get("start"), ed.get("end")))))
                b += [("bullet", _s(x)) for x in ed.get("details") or [] if _s(x)]
        elif sec == "certifications" and r.get("certifications"):
            b.append(("heading", SECTION_TITLES[sec]))
            for ct in r["certifications"]:
                line = _join(ct.get("name"), ct.get("issuer"), sep=" – ")
                if _s(ct.get("date")):
                    line += f" ({_s(ct['date'])})"
                if line:
                    b.append(("bullet", line))
        elif sec == "achievements" and r.get("achievements"):
            b.append(("heading", SECTION_TITLES[sec]))
            b += [("bullet", _s(x)) for x in r["achievements"] if _s(x)]
        elif sec == "additional_sections":
            for s in r.get("additional_sections") or []:
                items = [_s(x) for x in s.get("items") or [] if _s(x)]
                if not items:
                    continue
                b.append(("heading", _s(s.get("title")) or "Additional Information"))
                if _s(s.get("title")).lower() == "declaration":
                    b += [("para", x) for x in items]
                else:
                    b += [("bullet", x) for x in items]
    return b


# ---------------------------------------------------------------- text / markdown

def resume_to_text(r: dict) -> str:
    out = []
    for kind, v in build_blocks(r):
        if kind == "name":
            out.append(v.upper())
        elif kind == "contact":
            out.append(" | ".join(v))
        elif kind == "heading":
            out += ["", v.upper()]
        elif kind == "entry":
            out.append(_join(*v))
        elif kind == "bullet":
            out.append(f"• {v}")
        elif kind == "label":
            out.append(f"{v[0]}: {v[1]}" if v[0] else v[1])
        else:
            out.append(v)
    return "\n".join(out).strip()


def _md(t: str) -> str:
    return t.replace("\\", "\\\\").replace("$", "\\$").replace("*", "\\*").replace("_", "\\_")


def resume_to_markdown(r: dict) -> str:
    out = []
    for kind, v in build_blocks(r):
        if kind == "name":
            out.append(f"## {_md(v)}")
        elif kind == "headline":
            out.append(f"**{_md(v)}**")
        elif kind == "contact":
            out.append(_md("  ·  ".join(v)))
        elif kind == "heading":
            out.append(f"\n#### {_md(v.upper())}\n---")
        elif kind == "entry":
            a, b, c = v
            out.append(f"\n**{_md(a)}**" + (f" — {_md(b)}" if b else "") + (f"  ·  *{_md(c)}*" if c else ""))
        elif kind == "sub":
            out.append(f"*{_md(v)}*")
        elif kind == "bullet":
            out.append(f"- {_md(v)}")
        elif kind == "label":
            out.append((f"**{_md(v[0])}:** " if v[0] else "") + _md(v[1]) + "  ")
        else:
            out.append(_md(v))
    return _md_join(out)


def _md_join(lines: list[str]) -> str:
    # Keep bullet lists tight; separate everything else by blank lines.
    res = []
    for line in lines:
        if res and line.startswith("- ") and res[-1].startswith("- "):
            res[-1] += "\n" + line
        else:
            res.append(line)
    return "\n\n".join(res)


# ---------------------------------------------------------------- DOCX

def to_docx(r: dict, photo: bytes | None = None, a4: bool = True) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Mm, Pt, RGBColor

    doc = Document()
    sec = doc.sections[0]
    if a4:
        sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.left_margin = sec.right_margin = Inches(0.65)
    sec.top_margin = sec.bottom_margin = Inches(0.55)
    width = sec.page_width - sec.left_margin - sec.right_margin

    # Calibri: installed wherever Word is, so the file looks the same on the recruiter's machine.
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor.from_string(INK[1:])
    normal.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Calibri")
    normal.paragraph_format.space_after = Pt(1)
    normal.paragraph_format.space_before = Pt(0)
    accent, muted = RGBColor.from_string(ACCENT[1:]), RGBColor.from_string(MUTED[1:])

    def bottom_border(p):
        bdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        for k, val in (("w:val", "single"), ("w:sz", "4"), ("w:space", "2"), ("w:color", RULE[1:])):
            bottom.set(qn(k), val)
        bdr.append(bottom)
        p._p.get_or_add_pPr().append(bdr)

    def tracking(run, twentieths: int):
        sp = OxmlElement("w:spacing")
        sp.set(qn("w:val"), str(twentieths))
        run._r.get_or_add_rPr().append(sp)

    if photo:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(io.BytesIO(photo), width=Inches(1.1))

    for kind, v in build_blocks(r):
        if kind == "name":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(v)
            run.bold, run.font.size, run.font.color.rgb = True, Pt(20), RGBColor.from_string(INK[1:])
            tracking(run, 10)
        elif kind == "headline":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(v)
            run.font.size, run.font.color.rgb = Pt(11), accent
        elif kind == "contact":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run("  ·  ".join(v))
            run.font.size, run.font.color.rgb = Pt(9.5), muted
        elif kind == "heading":
            p = doc.add_paragraph()
            p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(9), Pt(3)
            p.paragraph_format.keep_with_next = True
            run = p.add_run(v.upper())
            run.bold, run.font.size, run.font.color.rgb = True, Pt(10.5), accent
            tracking(run, 20)
            bottom_border(p)
        elif kind == "entry":
            a, b, c = v
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.keep_with_next = True
            p.paragraph_format.tab_stops.add_tab_stop(width, WD_TAB_ALIGNMENT.RIGHT)
            p.add_run(a).bold = True
            if b:
                p.add_run(f"  |  {b}")
            if c:
                run = p.add_run(f"\t{c}")
                run.font.size, run.font.color.rgb = Pt(9.5), muted
        elif kind == "sub":
            p = doc.add_paragraph()
            p.paragraph_format.keep_with_next = True
            run = p.add_run(v)
            run.italic, run.font.size, run.font.color.rgb = True, Pt(9.5), muted
        elif kind == "bullet":
            p = doc.add_paragraph(v, style="List Bullet")
            p.paragraph_format.space_after = Pt(1.5)
        elif kind == "label":
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(1.5)
            if v[0]:
                p.add_run(f"{v[0]}: ").bold = True
            p.add_run(v[1])
        else:
            doc.add_paragraph(v)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def cover_letter_to_docx(text: str, a4: bool = True) -> bytes:
    from docx import Document
    from docx.shared import Inches, Mm, Pt

    doc = Document()
    sec = doc.sections[0]
    if a4:
        sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Inches(1)
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    for para in text.split("\n\n"):
        doc.add_paragraph(para.strip())
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- PDF

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
# Lato ships with the app, so the PDF looks identical locally and on Streamlit Cloud.
_FONT_CANDIDATES = [
    tuple(str(FONT_DIR / f"Lato-{s}.ttf") for s in ("Regular", "Bold", "Italic", "BoldItalic")),
    ("C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf", "C:/Windows/Fonts/calibrii.ttf",
     "C:/Windows/Fonts/calibriz.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"),
]
_fonts: tuple[str, str, str] | None = None


def _pdf_fonts() -> tuple[str, str, str]:
    """Register a Unicode TTF family (for ₹, accents etc.); Helvetica if none is available."""
    global _fonts
    if _fonts:
        return _fonts
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    _fonts = ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique")
    for reg, bold, ital, boldital in _FONT_CANDIDATES:
        if not all(os.path.exists(f) for f in (reg, bold, ital, boldital)):
            continue
        try:
            for name, path in (("RR", reg), ("RR-Bold", bold), ("RR-Italic", ital), ("RR-BoldItalic", boldital)):
                pdfmetrics.registerFont(TTFont(name, path))
            addMapping("RR", 0, 0, "RR")
            addMapping("RR", 1, 0, "RR-Bold")
            addMapping("RR", 0, 1, "RR-Italic")
            addMapping("RR", 1, 1, "RR-BoldItalic")
            _fonts = ("RR", "RR-Bold", "RR-Italic")
            break
        except Exception:
            continue
    return _fonts


def _link(item: str) -> str:
    """Contact item as escaped markup, made clickable when it's an email or a URL."""
    text = escape(item).replace(" ", "&nbsp;")  # break lines only between items, never inside one
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.\w+", item):
        return f'<a href="mailto:{escape(item)}">{text}</a>'
    if re.fullmatch(r"(https?://)?[\w-]+(\.[\w-]+)+(/\S*)?", item):
        href = item if item.startswith("http") else f"https://{item}"
        return f'<a href="{escape(href)}">{text}</a>'
    return text


# Sizes for one layout pass; to_pdf shrinks them step by step until the resume fits the page limit.
_SCALES = (1.0, 0.965, 0.93, 0.9)
# (text scale, whitespace) steps tried in order by to_pdf when fitting; text never goes below 9pt
_FIT_STEPS = [(sc, 1.0) for sc in _SCALES] + [(_SCALES[-1], 0.6)]
_BULLET_INDENT = 12


def _margins(scale: float) -> tuple[float, float]:
    """(side, top/bottom) page margins in points; they narrow slightly as the layout is compacted."""
    from reportlab.lib.units import inch

    return (0.62 - 0.12 * (1 - scale) / 0.1) * inch, (0.5 - 0.06 * (1 - scale) / 0.1) * inch


def bullet_lines(text: str, a4: bool = True, scale: float = _SCALES[-1]) -> tuple[int, int]:
    """(lines, words on the last line) for a bullet in the most compact PDF layout.

    Cutting that many words from a wrapped bullet saves a whole line, which is what actually shortens the page.
    """
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.pdfbase.pdfmetrics import stringWidth

    font, size = _pdf_fonts()[0], 10 * scale
    width = (A4 if a4 else letter)[0] - 2 * _margins(scale)[0] - 12 - _BULLET_INDENT  # 12: page frame padding
    lines, used, last = 1, 0.0, 0
    space = stringWidth(" ", font, size)
    for word in text.split():
        w = stringWidth(word, font, size)
        if used and used + space + w > width:
            lines, used, last = lines + 1, w, 1
        else:
            used, last = used + (space if used else 0) + w, last + 1
    return lines, last


def _build_pdf(r: dict, photo: bytes | None, a4: bool, scale: float, gap: float = 1.0) -> tuple[bytes, int]:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Flowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    reg, bold, ital = _pdf_fonts()
    ink, accent, muted, rule = (colors.HexColor(c) for c in (INK, ACCENT, MUTED, RULE))
    f = scale
    g = scale * gap  # vertical whitespace; the last fitting step tightens it without shrinking text further
    body, lead = 10 * f, (13.2 - 1.4 * (1 - gap)) * f
    base = ParagraphStyle("base", fontName=reg, fontSize=body, leading=lead, textColor=ink)
    st = {
        "name": ParagraphStyle("name", base, fontName=bold, fontSize=21 * f, leading=25 * f, alignment=TA_CENTER),
        "headline": ParagraphStyle("headline", base, fontSize=10.8 * f, leading=14 * f, alignment=TA_CENTER,
                                   textColor=accent, spaceBefore=1 * g),
        "contact": ParagraphStyle("contact", base, fontSize=8.9 * f, leading=12 * f, alignment=TA_CENTER,
                                  textColor=muted, spaceBefore=2 * g, spaceAfter=2 * g),
        "right": ParagraphStyle("right", base, fontSize=9.2 * f, alignment=TA_RIGHT, textColor=muted),
        "sub": ParagraphStyle("sub", base, fontName=ital, fontSize=9 * f, leading=12 * f, textColor=muted,
                              spaceAfter=1 * g),
        "bullet": ParagraphStyle("bullet", base, leftIndent=_BULLET_INDENT, bulletIndent=2.5, spaceAfter=1.6 * g,
                                 bulletFontName=reg, bulletFontSize=body * 0.85, bulletColor=accent),
        "label": ParagraphStyle("label", base, spaceAfter=1.6 * g),
        "para": ParagraphStyle("para", base, spaceAfter=1 * g),
    }

    class Heading(Flowable):
        """Letter-spaced small-caps style section title with a hairline rule underneath."""

        def __init__(self, text: str, width: float):
            super().__init__()
            self.text, self.width = text.upper(), width
            self.size = 10.2 * f
            self.height = self.size + 6 * f
            self.spaceBefore, self.spaceAfter = 9 * g, 3.5 * g
            self.keepWithNext = 1

        def wrap(self, aw, ah):
            return self.width, self.height

        def draw(self):
            c = self.canv
            t = c.beginText(0, 5 * f)
            t.setFont(bold, self.size)
            t.setCharSpace(1.1 * f)
            t.setFillColor(accent)
            t.textOut(self.text)
            c.drawText(t)
            c.setStrokeColor(rule)
            c.setLineWidth(0.6)
            c.line(0, 0, self.width, 0)

    buf = io.BytesIO()
    side, top = _margins(f)
    doc = SimpleDocTemplate(buf, pagesize=A4 if a4 else letter, leftMargin=side, rightMargin=side,
                            topMargin=top, bottomMargin=top,
                            title=_s(r.get("name")) or "Resume", author=_s(r.get("name")))
    width = doc.width
    story = []
    if photo:
        iw, ih = ImageReader(io.BytesIO(photo)).getSize()
        w = 1.0 * inch
        story += [Image(io.BytesIO(photo), width=w, height=w * ih / iw), Spacer(1, 4)]

    blocks = build_blocks(r)
    skip = False
    for n, (kind, v) in enumerate(blocks):
        if skip:
            skip = False
            continue
        # An entry title stays with its own details, but never chains into the next entry or section.
        follows = [k for k, _ in blocks[n + 1:n + 3]]
        attach = int(bool(follows) and follows[0] in ("bullet", "sub"))
        if kind in ("name", "headline"):
            story.append(Paragraph(escape(v), st[kind]))
        elif kind == "contact":
            story.append(Paragraph("&nbsp;&nbsp;·&nbsp;&nbsp; ".join(_link(x) for x in v), st["contact"]))
        elif kind == "heading":
            story.append(Heading(v, width))
        elif kind == "entry" and not v[1] and not v[2] and n + 1 < len(blocks) and blocks[n + 1][0] == "sub":
            # Undated project: put its tech line next to the name instead of on a line of its own.
            p = Paragraph(f"<b>{escape(v[0])}</b>&nbsp;&nbsp;<font color='{MUTED}'>|</font>&nbsp;&nbsp;"
                          f"<font name='{ital}' color='{MUTED}' size='{9.2 * f:.2f}'>"
                          f"{escape(blocks[n + 1][1].removeprefix('Tech: '))}</font>",
                          ParagraphStyle("proj", base, spaceBefore=4 * g, spaceAfter=1 * g,
                                         keepWithNext=int(follows[1:2] == ["bullet"])))
            story.append(p)
            skip = True
        elif kind == "entry":
            a, b, c = v
            left = Paragraph(f"<b>{escape(a)}</b>" + (f"&nbsp;&nbsp;|&nbsp;&nbsp;{escape(b)}" if b else ""), base)
            t = Table([[left, Paragraph(escape(c), st["right"])]], colWidths=[width * 0.74, width * 0.26],
                      hAlign="LEFT")
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 4 * g),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 1 * g)]))
            t.keepWithNext = attach
            story.append(t)
        elif kind == "sub":
            p = Paragraph(escape(v), st["sub"])
            p.keepWithNext = int(follows[:1] == ["bullet"])
            story.append(p)
        elif kind == "bullet":
            story.append(Paragraph(escape(v), st["bullet"], bulletText="•"))
        elif kind == "label":
            story.append(Paragraph((f"<b>{escape(v[0])}:</b> " if v[0] else "") + escape(v[1]), st["label"]))
        else:
            story.append(Paragraph(escape(v), st["para"]))

    doc.build(story)
    return buf.getvalue(), getattr(doc, "page", 1)


def pdf_pages(r: dict, a4: bool, fit_pages: int) -> int:
    """Pages the resume needs at its most compact allowed size."""
    return to_pdf(r, None, a4, fit_pages)[1]


def to_pdf(r: dict, photo: bytes | None = None, a4: bool = True, fit_pages: int | None = None) -> tuple[bytes, int]:
    """Return (pdf_bytes, page_count). With fit_pages, type and spacing shrink a little (never below 9pt body
    text) until the resume fits; if it still doesn't, the most compact version is returned."""
    result = None
    for scale, gap in _FIT_STEPS if fit_pages else _FIT_STEPS[:1]:
        result = _build_pdf(r, photo, a4, scale, gap)
        if result[1] <= (fit_pages or result[1]):
            break
    return result


def cover_letter_to_pdf(text: str, a4: bool = True) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    reg, _, _ = _pdf_fonts()
    style = ParagraphStyle("cl", fontName=reg, fontSize=11, leading=15.5, spaceAfter=10,
                           textColor=colors.HexColor(INK))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4 if a4 else letter, leftMargin=inch, rightMargin=inch,
                            topMargin=inch, bottomMargin=inch, title="Cover Letter")
    doc.build([Paragraph(escape(p.strip()).replace("\n", "<br/>"), style) for p in text.split("\n\n") if p.strip()])
    return buf.getvalue()
