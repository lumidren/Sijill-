"""Breach readiness: notification clocks and notice templates.

The deadlines are configuration (PDPL_BREACH_REGULATOR_HOURS, PDPL_BREACH_INDIVIDUALS_HOURS),
counted from the moment the organisation became aware of the breach. The defaults reflect the
project brief and are unverified (see docs/LEGAL-REVIEW.md). Times are stored in UTC and shown in
Africa/Cairo.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import utcnow
from .models import AppSetting, Incident

WARNING_HOURS = 24
URGENT_HOURS = 12


def cairo() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone_display)


def parse_when(value: str) -> datetime:
    """ISO 8601 with an offset is taken as given; without one it is read as Cairo local time."""
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=cairo())
    return dt.astimezone(timezone.utc)


def deadlines(i: Incident) -> tuple[datetime, datetime]:
    s = get_settings()
    return (i.discovered_at + timedelta(hours=s.breach_regulator_hours),
            i.discovered_at + timedelta(hours=s.breach_individuals_hours))


def clock(due: datetime, done_at: datetime | None, now: datetime) -> dict:
    if done_at is not None:
        return {"due": due.isoformat(), "done_at": done_at.isoformat(),
                "state": "met" if done_at <= due else "met_late", "seconds_left": None}
    left = (due - now).total_seconds()
    if left < 0:
        state = "overdue"
    elif left <= URGENT_HOURS * 3600:
        state = "urgent"
    elif left <= WARNING_HOURS * 3600:
        state = "warning"
    else:
        state = "running"
    return {"due": due.isoformat(), "done_at": None, "state": state, "seconds_left": int(left)}


def clocks(i: Incident, now: datetime | None = None) -> dict:
    now = now or utcnow()
    reg_due, ind_due = deadlines(i)
    if i.individuals_notice_needed is False:
        individuals = {"due": ind_due.isoformat(), "done_at": None, "state": "not_needed", "seconds_left": None}
    else:
        individuals = clock(ind_due, i.individuals_notified_at, now)
    return {"regulator": clock(reg_due, i.regulator_notified_at, now), "individuals": individuals,
            "regulator_hours": get_settings().breach_regulator_hours,
            "individuals_hours": get_settings().breach_individuals_hours}


def active_clocks(db: Session, now: datetime | None = None) -> list[dict]:
    """Open incidents with at least one notification still to do (for the dashboard)."""
    now = now or utcnow()
    out = []
    for i in db.execute(select(Incident).where(Incident.status != "closed").order_by(Incident.discovered_at)).scalars():
        c = clocks(i, now)
        if c["regulator"]["done_at"] and c["individuals"]["state"] in ("met", "met_late", "not_needed"):
            continue
        out.append({"id": i.id, "title": i.title, "status": i.status,
                    "regulator_due": c["regulator"]["due"], "regulator_state": c["regulator"]["state"],
                    "regulator_done": c["regulator"]["done_at"] is not None,
                    "individuals_due": c["individuals"]["due"] if c["individuals"]["state"] != "not_needed" else None,
                    "individuals_state": c["individuals"]["state"]})
    return out


# ----------------------------------------------------------------------------- notice templates

def _org(db: Session) -> dict:
    row = db.execute(select(AppSetting).where(AppSetting.key == "organization")).scalar_one_or_none()
    return row.value if row else {}


def _fmt(dt: datetime | None, lang: str) -> str | None:
    if dt is None:
        return None
    local = dt.astimezone(cairo())
    if lang == "ar":
        from .reports.strings import MONTHS_AR
        return f"{local.day} {MONTHS_AR[local.month - 1]} {local.year}، الساعة {local:%H:%M} (بتوقيت القاهرة)"
    return local.strftime("%d %B %Y, %H:%M (Cairo time)")


GAP = {"en": "[to be completed: {what}]", "ar": "[يُستكمل: {what}]"}
LABELS = {
    "en": {"description": "what happened", "data": "personal data involved", "count": "number of people affected",
           "consequences": "likely consequences", "measures": "measures taken or proposed", "contact": "contact details",
           "occurred": "when it happened, if known", "systems": "systems involved", "steps": "steps people can take to protect themselves",
           "dpo": "DPO name"},
    "ar": {"description": "ما الذي حدث", "data": "البيانات الشخصية المعنية", "count": "عدد الأشخاص المتأثرين",
           "consequences": "العواقب المحتملة", "measures": "الإجراءات المتخذة أو المقترحة", "contact": "بيانات التواصل",
           "occurred": "وقت الحدوث إن كان معروفًا", "systems": "الأنظمة المعنية", "steps": "الخطوات التي يمكن للأشخاص اتخاذها لحماية أنفسهم",
           "dpo": "اسم مسؤول حماية البيانات"},
}
TEMPLATE_NOTE = {
    "en": "Template drafted by PDPL-Ready without the regulator's official form. Check the fields and channel the regulator requires before sending. Not legal advice.",
    "ar": "نموذج أعدّته PDPL-Ready دون الاطلاع على النموذج الرسمي للجهة الرقابية. تحققوا من الحقول ووسيلة الإرسال المطلوبة قبل الإرسال. ليس استشارة قانونية.",
}


def notice(db: Session, i: Incident, target: str, lang: str) -> dict:
    org = _org(db)
    L = LABELS[lang]

    def v(value, key):
        if value in (None, "", []):
            return GAP[lang].format(what=L[key])
        if isinstance(value, list):
            return "، ".join(value) if lang == "ar" else ", ".join(value)
        return str(value)

    org_name = (org.get("name_ar") if lang == "ar" and org.get("name_ar") else org.get("name")) or "[organisation]"
    ref = f"INC-{i.id:04d}"
    count = None if i.affected_count is None else (f"{i.affected_count:,}" if lang == "en" else f"{i.affected_count}")
    if target == "regulator" and lang == "en":
        subject = f"Personal data breach notification: {org_name} ({ref})"
        lines = [
            "To: the data protection regulator",
            "",
            f"1. Organisation: {org_name}",
            f"2. Data Protection Officer: {v(org.get('dpo'), 'dpo')}; contact: {v(i.contact, 'contact')}",
            f"3. Our reference: {ref}",
            f"4. When we became aware of the breach: {_fmt(i.discovered_at, 'en')}",
            f"5. When the breach happened: {v(_fmt(i.occurred_at, 'en'), 'occurred')}",
            f"6. What happened: {v(i.description, 'description')}",
            f"7. Personal data involved: {v(i.data_categories, 'data')}",
            f"8. Number of people affected (estimate): {v(count, 'count')}",
            f"9. Systems involved: {v(i.systems, 'systems')}",
            f"10. Likely consequences for the people affected: {v(i.likely_consequences, 'consequences')}",
            f"11. Measures taken or proposed: {v(i.measures_taken, 'measures')}",
            f"12. Contact for follow-up: {v(i.contact, 'contact')}",
        ]
    elif target == "regulator":
        subject = f"إخطار باختراق بيانات شخصية: {org_name} ({ref})"
        lines = [
            "إلى: الجهة الرقابية المختصة بحماية البيانات الشخصية",
            "",
            f"١. المؤسسة: {org_name}",
            f"٢. مسؤول حماية البيانات: {v(org.get('dpo'), 'dpo')}؛ للتواصل: {v(i.contact, 'contact')}",
            f"٣. الرقم المرجعي لدينا: {ref}",
            f"٤. وقت علمنا بالاختراق: {_fmt(i.discovered_at, 'ar')}",
            f"٥. وقت حدوث الاختراق: {v(_fmt(i.occurred_at, 'ar'), 'occurred')}",
            f"٦. ما الذي حدث: {v(i.description, 'description')}",
            f"٧. البيانات الشخصية المعنية: {v(i.data_categories, 'data')}",
            f"٨. عدد الأشخاص المتأثرين (تقديري): {v(count, 'count')}",
            f"٩. الأنظمة المعنية: {v(i.systems, 'systems')}",
            f"١٠. العواقب المحتملة على الأشخاص المتأثرين: {v(i.likely_consequences, 'consequences')}",
            f"١١. الإجراءات المتخذة أو المقترحة: {v(i.measures_taken, 'measures')}",
            f"١٢. جهة التواصل للمتابعة: {v(i.contact, 'contact')}",
        ]
    elif lang == "en":
        subject = f"Important: an incident involving your personal data ({org_name})"
        lines = [
            "Dear [name],",
            "",
            f"We are writing to tell you about an incident at {org_name} that involved some of your personal data.",
            "",
            f"What happened: {v(i.description, 'description')}",
            f"When we found out: {_fmt(i.discovered_at, 'en')}",
            f"What information was involved: {v(i.data_categories, 'data')}",
            f"What we are doing: {v(i.measures_taken, 'measures')}",
            f"What you can do: {GAP['en'].format(what=L['steps'])}",
            "",
            f"If you have questions, contact us: {v(i.contact, 'contact')}",
            "",
            "We are sorry for any concern this causes.",
            org_name,
        ]
    else:
        subject = f"هام: حادث يتعلق ببياناتك الشخصية ({org_name})"
        lines = [
            "عزيزي/عزيزتي [الاسم]،",
            "",
            f"نكتب إليك لإبلاغك بحادث وقع لدى {org_name} وتعلق ببعض بياناتك الشخصية.",
            "",
            f"ما الذي حدث: {v(i.description, 'description')}",
            f"متى علمنا بذلك: {_fmt(i.discovered_at, 'ar')}",
            f"ما البيانات المعنية: {v(i.data_categories, 'data')}",
            f"ما الذي نقوم به: {v(i.measures_taken, 'measures')}",
            f"ما الذي يمكنك فعله: {GAP['ar'].format(what=L['steps'])}",
            "",
            f"للاستفسار، تواصل معنا: {v(i.contact, 'contact')}",
            "",
            "نعتذر عن أي قلق قد يسببه ذلك.",
            org_name,
        ]
    body = "\n".join(lines)
    missing = body.count(GAP[lang].split("{")[0])
    return {"subject": subject, "body": body, "note": TEMPLATE_NOTE[lang], "missing_fields": missing, "lang": lang,
            "target": target}


def notice_pdf(n: dict) -> bytes:
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Spacer

    from .reports import pdf as rp

    rp._fonts()
    L = rp.Lang(n["lang"])
    story = [rp.Para(n["subject"], size=14, bold=True, rtl=L.rtl, color=rp.BRAND_DARK, space_after=8)]
    for line in n["body"].split("\n"):
        story.append(rp.Para(line, size=10, rtl=L.rtl) if line.strip() else Spacer(1, 6))
    story += [Spacer(1, 12), rp.Para(n["note"], size=8, rtl=L.rtl, color=rp.MUTED)]
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm,
                      bottomMargin=20 * mm, title=n["subject"], author="PDPL-Ready").build(story)
    return buf.getvalue()
