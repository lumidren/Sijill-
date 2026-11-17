"""PDF readiness report and gap list (ReportLab), in English or Arabic.

ReportLab has no OpenType shaping, so Arabic is shaped with arabic_reshaper (presentation
forms) and reordered with python-bidi. Lines are wrapped on the logical text first and each
line is reordered on its own, so multi-line paragraphs read in the right order.
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Flowable, KeepTogether, PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle

from ..config import get_settings
from .data import ReportData
from .strings import MONTHS_AR, S

FONT_DIR = Path(__file__).parent / "fonts"
FONT, FONT_BOLD = "PDPLSans", "PDPLSans-Bold"
BRAND = colors.HexColor("#0f625c")
BRAND_DARK = colors.HexColor("#0f3d3a")
INK = colors.HexColor("#10201f")
MUTED = colors.HexColor("#5b6b6a")
LINE = colors.HexColor("#e2e8f0")
STATUS_COLOR = {
    "compliant": colors.HexColor("#15803d"), "partial": colors.HexColor("#b45309"),
    "non_compliant": colors.HexColor("#b91c1c"), "not_applicable": colors.HexColor("#64748b"),
    "not_assessed": colors.HexColor("#64748b"),
}
PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
_registered = False


def _fonts() -> None:
    global _registered
    if not _registered:
        pdfmetrics.registerFont(TTFont(FONT, str(FONT_DIR / "PDPLSans-Regular.ttf")))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_DIR / "PDPLSans-Bold.ttf")))
        _registered = True


AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


class Lang:
    def __init__(self, code: str):
        self.code = code
        self.rtl = code == "ar"
        self.s = S[code]
        self.tz = ZoneInfo(get_settings().timezone_display)

    def t(self, key: str, **kw) -> str:
        return self.s[key].format(**kw)

    def num(self, v, digits: int = 0) -> str:
        text = f"{v:,.{digits}f}"
        return text.translate(AR_DIGITS) if self.rtl else text

    def date(self, dt: datetime, with_time: bool = True) -> str:
        local = dt.astimezone(self.tz)
        if self.rtl:
            text = f"{local.day} {MONTHS_AR[local.month - 1]} {local.year}"
            if with_time:
                text += f"، {local:%H:%M}"
            return text.translate(AR_DIGITS)
        return local.strftime("%d %b %Y, %H:%M" if with_time else "%d %b %Y")

    def pick(self, text) -> str:
        return text.ar if (self.rtl and getattr(text, "ar", "")) else text.en


def visual(text: str) -> str:
    """Logical Arabic/mixed text -> visual order with joined letter forms."""
    return get_display(arabic_reshaper.reshape(text), base_dir="R")


class Para(Flowable):
    """Wrapped paragraph that renders LTR or RTL text correctly with a TrueType font."""

    def __init__(self, text: str, size: float = 9.5, bold: bool = False, color=INK, rtl: bool = False,
                 leading: float | None = None, space_after: float = 0, align: str | None = None):
        super().__init__()
        self.text = " ".join(str(text).split())
        self.size = size
        self.font = FONT_BOLD if bold else FONT
        self.color = color
        self.rtl = rtl
        self.leading = leading or size * 1.45
        self.space_after = space_after
        self.align = align or ("right" if rtl else "left")
        self.lines: list[str] = []

    def _width(self, s: str) -> float:
        return pdfmetrics.stringWidth(arabic_reshaper.reshape(s) if self.rtl else s, self.font, self.size)

    def wrap(self, avail_w, avail_h):
        self.avail_w = avail_w
        words, lines, cur = self.text.split(" "), [], ""
        for w in words:
            cand = f"{cur} {w}" if cur else w
            if cur and self._width(cand) > avail_w:
                lines.append(cur)
                cur = w
            else:
                cur = cand
        if cur:
            lines.append(cur)
        self.lines = [visual(l) if self.rtl else l for l in lines] or [""]
        self.height = len(self.lines) * self.leading + self.space_after
        return avail_w, self.height

    def draw(self):
        c = self.canv
        c.setFont(self.font, self.size)
        c.setFillColor(self.color)
        y = self.height - self.space_after - self.size
        for line in self.lines:
            if self.align == "right":
                c.drawRightString(self.avail_w, y, line)
            elif self.align == "center":
                c.drawCentredString(self.avail_w / 2, y, line)
            else:
                c.drawString(0, y, line)
            y -= self.leading


def _numbered_canvas(lang: Lang, org: str):
    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self._decorate(total)
                super().showPage()
            super().save()

        def _text(self, x, y, text, size=7.5, font=FONT, color=MUTED, anchor="left"):
            self.setFont(font, size)
            self.setFillColor(color)
            t = visual(text) if lang.rtl else text
            if anchor == "right":
                self.drawRightString(x, y, t)
            elif anchor == "center":
                self.drawCentredString(x, y, t)
            else:
                self.drawString(x, y, t)

        def _decorate(self, total):
            self.setStrokeColor(LINE)
            self.setLineWidth(0.6)
            self.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)
            disclaimer = lang.t("disclaimer")
            # footer: disclaimer (shortened to one line) + page number
            first_sentence = disclaimer.split(". ")[-1] if not lang.rtl else disclaimer.split(". ")[-1]
            page = lang.t("page", n=lang.num(self._pageNumber), total=lang.num(total))
            if lang.rtl:
                self._text(PAGE_W - MARGIN, 9 * mm, first_sentence, anchor="right")
                self._text(MARGIN, 9 * mm, page, anchor="left")
                self._text(PAGE_W - MARGIN, PAGE_H - 11 * mm, f"{lang.t('brand')} · {org}", anchor="right")
            else:
                self._text(MARGIN, 9 * mm, first_sentence)
                self._text(PAGE_W - MARGIN, 9 * mm, page, anchor="right")
                self._text(MARGIN, PAGE_H - 11 * mm, f"{lang.t('brand')} · {org}")

    return NumberedCanvas


def _table(rows: list[list], widths: list[float], lang: Lang, header: bool = True, zebra: bool = True,
           extra: list | None = None) -> Table:
    if lang.rtl:  # columns run right-to-left
        rows = [list(reversed(r)) for r in rows]
        widths = list(reversed(widths))
    data = []
    for i, r in enumerate(rows):
        cells = []
        for cell in r:
            if isinstance(cell, Flowable):
                cells.append(cell)
            else:
                cells.append(Para(str(cell), size=8.3 if i else 7.8, bold=header and i == 0, rtl=lang.rtl,
                                  color=MUTED if header and i == 0 else INK))
        data.append(cells)
    tbl = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
    ]
    if header:
        style += [("LINEBELOW", (0, 0), (-1, 0), 0.8, BRAND), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f4"))]
    if zebra:
        for i in range(1 if header else 0, len(data)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fafcfc")))
    tbl.setStyle(TableStyle(style + (extra or [])))
    return tbl


def _h(text: str, lang: Lang, size: float = 13, space_before: float = 10) -> list:
    return [Spacer(1, space_before), Para(text, size=size, bold=True, rtl=lang.rtl, color=BRAND_DARK, space_after=5)]


def _trend(d: ReportData, lang: Lang, width: float, height: float = 120) -> Drawing:
    dr = Drawing(width, height)
    pts = d.trend
    pad_l, pad_b, pad_t = 26, 18, 8
    w, h = width - pad_l - 6, height - pad_b - pad_t
    for v in (0, 25, 50, 75, 100):
        y = pad_b + h * v / 100
        dr.add(Line(pad_l, y, pad_l + w, y, strokeColor=LINE, strokeWidth=0.5))
        dr.add(String(pad_l - 4, y - 2.5, lang.num(v), fontName=FONT, fontSize=6.5, fillColor=MUTED, textAnchor="end"))
    if len(pts) < 2:
        return dr
    t0, t1 = pts[0][0].timestamp(), pts[-1][0].timestamp()
    span = max(t1 - t0, 1)

    def xy(p):
        x = (p[0].timestamp() - t0) / span
        if lang.rtl:
            x = 1 - x
        return pad_l + w * x, pad_b + h * p[1]

    coords = [c for p in pts for c in xy(p)]
    dr.add(PolyLine(coords, strokeColor=BRAND, strokeWidth=1.6))
    prev = None
    for p in pts:
        x, y = xy(p)
        dip = prev is not None and p[1] < prev - 0.0005
        dr.add(Circle(x, y, 2.6 if dip else 1.5, fillColor=colors.HexColor("#dc2626") if dip else BRAND, strokeColor=colors.white, strokeWidth=0.5))
        prev = p[1]
    for p, anchor in ((pts[0], "start"), (pts[-1], "end")):
        x, _ = xy(p)
        a = anchor if not lang.rtl else ("end" if anchor == "start" else "start")
        label = lang.date(p[0], with_time=False)
        dr.add(String(x, 4, visual(label) if lang.rtl else label, fontName=FONT, fontSize=6.5, fillColor=MUTED, textAnchor=a))
    return dr


def _why(r, lang: Lang) -> str:
    fails = sum(1 for c in r.checks if c.status == "FAIL")
    graded = sum(1 for c in r.checks if c.status)
    if r.reason == "capped_by_failing_checks":
        return lang.t("why_capped", n=lang.num(fails))
    if r.reason == "na_overridden_by_failing_checks":
        return lang.t("why_na_override", n=lang.num(fails))
    if r.reason == "derived_from_checks":
        return lang.t("why_failing", n=lang.num(fails), m=lang.num(graded))
    if r.reason == "from_answer":
        return lang.t("why_answer")
    return lang.t("why_none")


def _header_block(d: ReportData, lang: Lang, title: str, width: float) -> list:
    org = d.org.get("name_ar") if lang.rtl and d.org.get("name_ar") else d.org.get("name", "")
    out = [
        Para(lang.t("brand"), size=9, bold=True, color=BRAND, rtl=lang.rtl),
        Para(title, size=20, bold=True, color=BRAND_DARK, rtl=lang.rtl, space_after=2),
        Para(org, size=13, rtl=lang.rtl),
        Para(lang.t("generated", when=lang.date(d.generated_at)), size=8.5, color=MUTED, rtl=lang.rtl, space_after=8),
    ]
    box = Table([[Para(lang.t("disclaimer"), size=8.3, rtl=lang.rtl)],
                 [Para(lang.t("unverified", count=lang.num(d.unverified), total=lang.num(len(d.catalog.requirements))), size=8.3, rtl=lang.rtl, color=MUTED)]],
                colWidths=[width])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff7ed")),
                             ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#fdba74")),
                             ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                             ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    out.append(box)
    return out


def _status_cell(status: str, lang: Lang) -> Para:
    return Para(lang.t(status), size=8.3, bold=True, color=STATUS_COLOR[status], rtl=lang.rtl)


def _gap_table(d: ReportData, lang: Lang, width: float) -> list:
    gaps = d.gaps
    if not gaps:
        return [Para(lang.t("gaps_none"), rtl=lang.rtl)]
    rows = [[lang.t("req"), lang.t("area"), lang.t("status"), lang.t("basis"), lang.t("why")]]
    for r in gaps:
        req = d.req(r.id)
        area = d.catalog.area(r.area_id)
        rows.append([
            Para(f"{req.label}  {lang.pick(req.title)}", size=8.3, rtl=lang.rtl),
            Para(lang.pick(area.title), size=7.8, color=MUTED, rtl=lang.rtl),
            _status_cell(r.status, lang),
            lang.t(f"basis_{r.basis}"),
            _why(r, lang),
        ])
    w = width
    return [Para(lang.t("gaps_intro", count=lang.num(len(gaps))), rtl=lang.rtl, color=MUTED, space_after=4),
            _table(rows, [w * 0.30, w * 0.20, w * 0.13, w * 0.12, w * 0.25], lang)]


def _summary(d: ReportData, lang: Lang, width: float) -> list:
    c = d.score.counts()
    score = d.score.overall
    big = Para(lang.num(round((score or 0) * 100)) if score is not None else "—", size=40, bold=True, color=BRAND,
               rtl=lang.rtl, align="center", leading=46)
    left = [big, Para(lang.t("out_of"), size=9, color=MUTED, rtl=lang.rtl, align="center", space_after=4)]
    cov_rows = [
        [lang.t("automated"), lang.num(c["by_basis"].get("automated", 0))],
        [lang.t("attested"), lang.num(c["by_basis"].get("attested", 0))],
        [lang.t("not_assessed"), lang.num(c["by_basis"].get("not_assessed", 0))],
    ]
    st_rows = [[lang.t(k), lang.num(c["by_status"].get(k, 0))] for k in ("compliant", "partial", "non_compliant", "not_applicable", "not_assessed")]
    right_w = width * 0.62
    right = [
        Para(lang.t("coverage"), size=10, bold=True, rtl=lang.rtl, space_after=2),
        _table(cov_rows, [right_w * 0.75, right_w * 0.25], lang, header=False, zebra=False),
        Para(lang.t("technical_coverage", automated=lang.num(c["technical_automated"]), technical=lang.num(c["technical_total"])), size=8.3, color=MUTED, rtl=lang.rtl, space_after=6),
        Para(lang.t("status_counts"), size=10, bold=True, rtl=lang.rtl, space_after=2),
        _table(st_rows, [right_w * 0.75, right_w * 0.25], lang, header=False, zebra=False),
        Para(f"{lang.t('stale', days=lang.num(d.stale_days))}: {lang.num(c['stale'])} · {lang.t('capped')}: {lang.num(c['capped'])}", size=8.3, color=MUTED, rtl=lang.rtl),
    ]
    cols = [left, right] if not lang.rtl else [right, left]
    widths = [width * 0.34, width * 0.66] if not lang.rtl else [width * 0.66, width * 0.34]
    grid = Table([cols], colWidths=widths)
    grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    return [*_h(lang.t("score"), lang), grid, Para(lang.t("score_caption"), size=8.3, color=MUTED, rtl=lang.rtl, space_after=4)]


def _areas(d: ReportData, lang: Lang, width: float) -> list:
    rows = [[lang.t("area"), lang.t("score_col"), lang.t("met"), lang.t("part"), lang.t("notmet"), lang.t("unassessed"), lang.t("na_col")]]
    for a in d.score.areas:
        area = d.catalog.area(a.id)
        rows.append([
            f"{area.label}  {lang.pick(area.title)}",
            lang.num(round(a.score * 100)) if a.score is not None else "—",
            lang.num(a.by_status.get("compliant", 0)), lang.num(a.by_status.get("partial", 0)),
            lang.num(a.by_status.get("non_compliant", 0)), lang.num(a.by_status.get("not_assessed", 0)),
            lang.num(a.by_status.get("not_applicable", 0)),
        ])
    w = width
    return [*_h(lang.t("areas"), lang), _table(rows, [w * 0.40, w * 0.10, w * 0.10, w * 0.10, w * 0.10, w * 0.10, w * 0.10], lang)]


def _regressions(d: ReportData, lang: Lang) -> list:
    out = _h(lang.t("regressions"), lang)
    if not d.regressions:
        return out + [Para(lang.t("regressions_none"), rtl=lang.rtl, color=MUTED)]
    for r in d.regressions:
        reqs = ", ".join(x.upper().replace("-", ".") for x in r["requirements"])
        resource = r["resource"].split(":")[-1].split("/")[-1]
        out.append(Para("• " + lang.t("regression_line", check=r["title"] or r["check_id"], resource=resource,
                                       target=r["target"], reqs=reqs), size=8.5, rtl=lang.rtl, color=colors.HexColor("#991b1b")))
    return out


def _sources(d: ReportData, lang: Lang) -> list:
    out = _h(lang.t("sources"), lang)
    if not d.runs:
        return out + [Para(lang.t("sources_none"), rtl=lang.rtl, color=MUTED)]
    for run in d.runs:
        out.append(Para("• " + lang.t("source_line", target=run.target, provider=run.provider, when=lang.date(run.started_at),
                                       passed=lang.num(run.passed), failed=lang.num(run.failed), sha=run.file_sha256[:16] + "…"),
                        size=8, rtl=lang.rtl, color=MUTED))
    return out


def _remediation(d: ReportData, lang: Lang, width: float) -> list:
    out = _h(lang.t("remediation"), lang)
    if not d.tasks:
        return out + [Para(lang.t("remediation_none"), rtl=lang.rtl, color=MUTED)]
    rows = [[lang.t("task"), lang.t("req"), lang.t("owner"), lang.t("due"), lang.t("status")]]
    for t in d.tasks[:25]:
        due = t["due_on"] or "—"
        if t["overdue"]:
            due = f"{due} ({lang.t('overdue_short')})"
        rows.append([t["title"], t["requirement_label"] or "—", t["owner"] or "—",
                     due.translate(AR_DIGITS) if lang.rtl else due, lang.t(f"task_{t['status']}")])
    w = width
    return out + [_table(rows, [w * 0.40, w * 0.10, w * 0.18, w * 0.17, w * 0.15], lang)]


def _risk_register(d: ReportData, lang: Lang, width: float) -> list:
    out = _h(lang.t("risks"), lang)
    if not d.risks:
        return out + [Para(lang.t("risks_none"), rtl=lang.rtl, color=MUTED)]
    rows = [[lang.t("risk"), lang.t("inherent"), lang.t("residual"), lang.t("treatment"), lang.t("status")]]
    for r in d.risks[:15]:
        inh = f"{lang.num(r['score'])} · {lang.t('level_' + r['level'])}"
        res = f"{lang.num(r['residual_score'])} · {lang.t('level_' + r['residual_level'])}" if r["residual_score"] else "—"
        status = lang.t("risk_" + r["status"])
        if r["status"] == "accepted" and r["acceptance_expires_on"]:
            exp = r["acceptance_expires_on"]
            status += f" → {exp.translate(AR_DIGITS) if lang.rtl else exp}"
        rows.append([r["title"], inh, res, lang.t("treat_" + r["treatment"]), status])
    w = width
    return out + [_table(rows, [w * 0.40, w * 0.14, w * 0.14, w * 0.14, w * 0.18], lang)]


def _doc(buf, d: ReportData, lang: Lang, title: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=17 * mm,
                             bottomMargin=19 * mm, title=title, author="PDPL-Ready", subject=d.org.get("name", ""),
                             creator="PDPL-Ready", lang=lang.code)


def readiness_pdf(d: ReportData, lang_code: str = "en") -> bytes:
    _fonts()
    lang = Lang(lang_code)
    width = PAGE_W - 2 * MARGIN
    story = _header_block(d, lang, lang.t("readiness_title"), width)
    story += _summary(d, lang, width)
    story += [*_h(lang.t("trend"), lang), _trend(d, lang, width)]
    story += _regressions(d, lang)
    story += [PageBreak()] + _areas(d, lang, width)
    story += [*_h(lang.t("gaps"), lang)] + _gap_table(d, lang, width)
    story += _remediation(d, lang, width) + _risk_register(d, lang, width)
    story += [KeepTogether(_h(lang.t("method"), lang) + [Para(lang.t("method_text"), size=8.5, rtl=lang.rtl, color=MUTED)])]
    story += _sources(d, lang)
    buf = io.BytesIO()
    org = d.org.get("name_ar") if lang.rtl and d.org.get("name_ar") else d.org.get("name", "")
    _doc(buf, d, lang, lang.t("readiness_title")).build(story, canvasmaker=_numbered_canvas(lang, org))
    return buf.getvalue()


def gaps_pdf(d: ReportData, lang_code: str = "en") -> bytes:
    _fonts()
    lang = Lang(lang_code)
    width = PAGE_W - 2 * MARGIN
    story = _header_block(d, lang, lang.t("gaps_title"), width) + [Spacer(1, 8)] + _gap_table(d, lang, width)
    buf = io.BytesIO()
    org = d.org.get("name_ar") if lang.rtl and d.org.get("name_ar") else d.org.get("name", "")
    _doc(buf, d, lang, lang.t("gaps_title")).build(story, canvasmaker=_numbered_canvas(lang, org))
    return buf.getvalue()
