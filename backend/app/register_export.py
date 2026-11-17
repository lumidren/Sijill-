"""Records-of-processing exports in a controller layout and a processor layout.

The column sets are modelled on the regulator's controller and processor templates as
described in the project brief; they have not been checked against the official templates
(see docs/LEGAL-REVIEW.md).
"""
from __future__ import annotations

import csv
import io

from .models import ProcessingActivity

# (key, English header, Arabic header)
CONTROLLER_COLUMNS = [
    ("ref", "Ref", "المرجع"),
    ("name", "Processing activity", "نشاط المعالجة"),
    ("purpose", "Purpose(s)", "الأغراض"),
    ("lawful_basis", "Lawful basis", "الأساس المشروع"),
    ("data_subjects", "Categories of data subjects", "فئات أصحاب البيانات"),
    ("data_categories", "Categories of personal data", "فئات البيانات الشخصية"),
    ("sensitive_categories", "Sensitive data", "البيانات الحساسة"),
    ("source", "Source of the data", "مصدر البيانات"),
    ("recipients", "Recipients", "الجهات المتلقية"),
    ("cross_border", "Cross-border transfer (countries)", "النقل عبر الحدود (الدول)"),
    ("transfer_safeguards", "Transfer safeguards", "ضمانات النقل"),
    ("retention", "Retention period", "مدة الاحتفاظ"),
    ("security_measures", "Security measures", "إجراءات الأمان"),
    ("systems", "Systems", "الأنظمة"),
    ("owner", "Owner", "المسؤول"),
    ("updated_at", "Last updated", "آخر تحديث"),
]

PROCESSOR_COLUMNS = [
    ("ref", "Ref", "المرجع"),
    ("client_name", "Controller (client)", "المتحكم (العميل)"),
    ("name", "Processing carried out", "المعالجة المنفذة"),
    ("purpose", "Purpose as instructed", "الغرض وفق التعليمات"),
    ("data_categories", "Categories of personal data", "فئات البيانات الشخصية"),
    ("data_subjects", "Categories of data subjects", "فئات أصحاب البيانات"),
    ("recipients", "Sub-processors and recipients", "المعالجون من الباطن والجهات المتلقية"),
    ("cross_border", "Cross-border transfer (countries)", "النقل عبر الحدود (الدول)"),
    ("transfer_safeguards", "Transfer safeguards", "ضمانات النقل"),
    ("security_measures", "Security measures", "إجراءات الأمان"),
    ("retention", "Retention, return or deletion", "الاحتفاظ أو الإرجاع أو الحذف"),
    ("updated_at", "Last updated", "آخر تحديث"),
]

NOTE_EN = ("Layout modelled on the regulator's controller/processor register templates as described in the project "
           "brief; not verified against the official templates. Not legal advice.")
NOTE_AR = "تخطيط مستوحى من نماذج سجلات المتحكم والمعالج كما وُصفت في وثيقة المشروع؛ لم تتم مطابقته مع النماذج الرسمية. ليس استشارة قانونية."


def columns(role: str):
    return CONTROLLER_COLUMNS if role == "controller" else PROCESSOR_COLUMNS


def value(a: ProcessingActivity, key: str, lang: str = "en") -> str:
    if key == "ref":
        return f"{'C' if a.role == 'controller' else 'P'}-{a.id:03d}"
    if key == "cross_border":
        if not a.cross_border:
            return "لا" if lang == "ar" else "No"
        countries = ", ".join(a.transfer_countries or [])
        yes = "نعم" if lang == "ar" else "Yes"
        return f"{yes} ({countries})" if countries else yes
    if key == "updated_at":
        return a.updated_at.date().isoformat()
    v = getattr(a, key)
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return "" if v is None else str(v)


def _cell(s: str) -> str:
    return "'" + s if s.startswith(("=", "+", "-", "@", "\t", "\r")) else s


def to_csv(activities: list[ProcessingActivity], role: str) -> bytes:
    cols = columns(role)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"{en} / {ar}" for _, en, ar in cols])
    for a in activities:
        w.writerow([_cell(value(a, k)) for k, _, _ in cols])
    w.writerow([])
    w.writerow([NOTE_EN])
    w.writerow([NOTE_AR])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def to_pdf(activities: list[ProcessingActivity], role: str, lang: str, org: dict) -> bytes:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Spacer

    from .reports import pdf as rp

    rp._fonts()
    L = rp.Lang(lang)
    page = landscape(A4)
    margin = 12 * mm
    width = page[0] - 2 * margin
    cols = columns(role)
    title_en = "Records of processing: controller register" if role == "controller" else "Records of processing: processor register"
    title_ar = "سجل أنشطة المعالجة: سجل المتحكم" if role == "controller" else "سجل أنشطة المعالجة: سجل المعالج"
    org_name = org.get("name_ar") if L.rtl and org.get("name_ar") else org.get("name", "")
    story = [
        rp.Para(title_ar if L.rtl else title_en, size=16, bold=True, rtl=L.rtl, color=rp.BRAND_DARK),
        rp.Para(org_name, size=11, rtl=L.rtl),
        rp.Para(NOTE_AR if L.rtl else NOTE_EN, size=8, rtl=L.rtl, color=rp.MUTED, space_after=6),
        Spacer(1, 4),
    ]
    header = [ar if L.rtl else en for _, en, ar in cols]
    rows = [header] + [[value(a, k, lang) for k, _, _ in cols] for a in activities]
    if len(rows) == 1:
        rows.append(["—"] + [""] * (len(cols) - 1))
    widths = [width / len(cols)] * len(cols)
    story.append(rp._table(rows, widths, L))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=margin, rightMargin=margin, topMargin=15 * mm,
                            bottomMargin=17 * mm, title=title_ar if L.rtl else title_en, author="PDPL-Ready")
    doc.build(story, canvasmaker=rp._numbered_canvas(L, org_name))
    return buf.getvalue()
