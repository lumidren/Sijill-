"""Governance modules: remediation tasks, risk register, data subject requests, vendors, DPIAs, policies.

Pure helpers here; HTTP lives in routers/governance.py. Anything that reads like a legal rule (the
request response period, the DPIA screening rule of thumb) is configuration or labelled as practice,
and is listed in docs/LEGAL-REVIEW.md.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalog import get_catalog
from .config import get_settings
from .db import utcnow
from .models import DataRequest, Dpia, Policy, Risk, Task, Vendor

# ------------------------------------------------------------------ dates


def day(d) -> datetime | None:
    """A calendar date stored at midday UTC, so it is the same day in Cairo (see DECISIONS #20)."""
    if d is None:
        return None
    return datetime.combine(d, time(12, 0), tzinfo=timezone.utc)


def days_until(target: datetime | None, now: datetime) -> int | None:
    return None if target is None else (target.date() - now.date()).days


def iso_date(dt: datetime | None) -> str | None:
    return dt.date().isoformat() if dt else None


# ------------------------------------------------------------------ tasks

TASK_OPEN = ("todo", "in_progress", "blocked")


def task_out(t: Task, now: datetime) -> dict:
    req = get_catalog().requirement(t.requirement_id) if t.requirement_id else None
    d = days_until(t.due_on, now)
    return {
        "id": t.id, "title": t.title, "description": t.description, "requirement_id": t.requirement_id,
        "requirement_label": req.label if req else None, "source": t.source, "source_id": t.source_id,
        "owner": t.owner, "priority": t.priority, "status": t.status, "due_on": iso_date(t.due_on),
        "days_left": d, "overdue": bool(d is not None and d < 0 and t.status in TASK_OPEN),
        "completed_at": t.completed_at.isoformat() if t.completed_at else None, "notes": t.notes,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


# ------------------------------------------------------------------ risks
# 5x5 matrix bands (a common convention, not a legal rule): 1-4 low, 5-9 medium, 10-16 high, 20-25 critical.

def risk_level(score: int) -> str:
    if score >= 20:
        return "critical"
    if score >= 10:
        return "high"
    if score >= 5:
        return "medium"
    return "low"


def risk_out(r: Risk, now: datetime) -> dict:
    inherent = r.likelihood * r.impact
    residual = (r.residual_likelihood * r.residual_impact
                if r.residual_likelihood and r.residual_impact else None)
    expired = bool(r.status == "accepted" and r.acceptance_expires_on and r.acceptance_expires_on < now)
    return {
        "id": r.id, "title": r.title, "description": r.description, "category": r.category,
        "likelihood": r.likelihood, "impact": r.impact, "score": inherent, "level": risk_level(inherent),
        "residual_likelihood": r.residual_likelihood, "residual_impact": r.residual_impact,
        "residual_score": residual, "residual_level": risk_level(residual) if residual else None,
        "treatment": r.treatment, "status": r.status, "owner": r.owner, "requirement_ids": r.requirement_ids or [],
        "controls": r.controls, "review_due": iso_date(r.review_due),
        "accepted_at": r.accepted_at.isoformat() if r.accepted_at else None,
        "acceptance_expires_on": iso_date(r.acceptance_expires_on), "acceptance_expired": expired,
        "acceptance_note": r.acceptance_note, "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def heat_map(risks: list[Risk], residual: bool = False) -> list[list[int]]:
    """5x5 counts, indexed [impact-1][likelihood-1], open/treating/accepted risks only."""
    grid = [[0] * 5 for _ in range(5)]
    for r in risks:
        if r.status == "closed":
            continue
        li, im = (r.residual_likelihood, r.residual_impact) if residual and r.residual_likelihood and r.residual_impact \
            else (r.likelihood, r.impact)
        grid[im - 1][li - 1] += 1
    return grid


# ------------------------------------------------------------------ data subject requests

REQUEST_OPEN = ("received", "in_progress")


def request_due(r: DataRequest) -> datetime:
    return r.received_at + timedelta(days=get_settings().dsr_response_days)


def request_out(r: DataRequest, now: datetime) -> dict:
    due = request_due(r)
    open_ = r.status in REQUEST_OPEN
    d = days_until(due, now)
    if not open_:
        state = "late" if r.completed_at and r.completed_at > due else "done"
    elif d < 0:
        state = "overdue"
    elif d <= 7:
        state = "due_soon"
    else:
        state = "on_track"
    return {
        "id": r.id, "ref": f"DSR-{r.id:04d}", "request_type": r.request_type, "requester": r.requester,
        "channel": r.channel, "received_at": r.received_at.isoformat(), "identity_verified": r.identity_verified,
        "status": r.status, "details": r.details, "outcome": r.outcome, "owner": r.owner,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "due_at": due.isoformat(), "days_left": d if open_ else None, "state": state,
        "response_days": get_settings().dsr_response_days, "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


# ------------------------------------------------------------------ vendors

def vendor_issues(v: Vendor, now: datetime) -> list[str]:
    out = []
    if v.status != "active":
        return out
    if v.role in ("processor", "sub_processor") and not v.dpa_signed:
        out.append("no_dpa")
    if v.due_diligence_on is None:
        out.append("no_due_diligence")
    if v.next_review_on and v.next_review_on < now:
        out.append("review_overdue")
    if any(c.strip().lower() not in ("egypt", "مصر") for c in (v.countries or []) if c.strip()):
        out.append("cross_border")
    return out


def vendor_out(v: Vendor, now: datetime) -> dict:
    return {
        "id": v.id, "name": v.name, "service": v.service, "role": v.role, "data_categories": v.data_categories or [],
        "countries": v.countries or [], "dpa_signed": v.dpa_signed, "dpa_signed_on": iso_date(v.dpa_signed_on),
        "due_diligence_on": iso_date(v.due_diligence_on), "next_review_on": iso_date(v.next_review_on),
        "days_to_review": days_until(v.next_review_on, now), "risk_level": v.risk_level,
        "security_notes": v.security_notes, "status": v.status, "owner": v.owner,
        "issues": vendor_issues(v, now), "updated_at": v.updated_at.isoformat() if v.updated_at else None,
    }


# ------------------------------------------------------------------ DPIAs
# Screening criteria and the "two or more criteria" rule of thumb come from general data-protection
# practice, not from verified Egyptian law; the UI says "likely needed".

DPIA_CRITERIA = ["sensitive_data", "large_scale", "systematic_monitoring", "new_technology", "vulnerable_people",
                 "cross_border", "automated_decisions", "data_matching"]


def dpia_screening(screening: dict) -> dict:
    yes = [k for k in DPIA_CRITERIA if screening.get(k) is True]
    answered = sum(1 for k in DPIA_CRITERIA if screening.get(k) is not None)
    return {"criteria_met": yes, "count": len(yes), "likely_needed": len(yes) >= 2,
            "complete": answered == len(DPIA_CRITERIA)}


def dpia_out(d: Dpia, now: datetime, activity_names: dict[int, str]) -> dict:
    return {
        "id": d.id, "ref": f"DPIA-{d.id:03d}", "title": d.title, "activity_id": d.activity_id,
        "activity_name": activity_names.get(d.activity_id) if d.activity_id else None,
        "screening": d.screening or {}, "screening_result": dpia_screening(d.screening or {}),
        "description": d.description, "necessity": d.necessity, "risks": d.risks, "measures": d.measures,
        "residual_risk": d.residual_risk, "dpo_opinion": d.dpo_opinion, "status": d.status, "owner": d.owner,
        "approved_at": d.approved_at.isoformat() if d.approved_at else None, "review_due": iso_date(d.review_due),
        "days_to_review": days_until(d.review_due, now), "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }


# ------------------------------------------------------------------ policies

def policy_out(p: Policy, now: datetime) -> dict:
    d = days_until(p.review_due, now)
    return {
        "id": p.id, "title": p.title, "version": p.version, "status": p.status, "owner": p.owner,
        "summary": p.summary, "requirement_ids": p.requirement_ids or [], "evidence_file_id": p.evidence_file_id,
        "approved_on": iso_date(p.approved_on), "review_due": iso_date(p.review_due), "days_to_review": d,
        "review_overdue": bool(d is not None and d < 0 and p.status == "approved"),
        "history": p.history or [], "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# ------------------------------------------------------------------ dashboard summary

def summary(db: Session, now: datetime | None = None) -> dict:
    now = now or utcnow()
    tasks = list(db.execute(select(Task)).scalars())
    risks = list(db.execute(select(Risk)).scalars())
    reqs = list(db.execute(select(DataRequest)).scalars())
    vendors = list(db.execute(select(Vendor)).scalars())
    policies = list(db.execute(select(Policy)).scalars())
    dpias = list(db.execute(select(Dpia)).scalars())
    open_tasks = [task_out(t, now) for t in tasks if t.status in TASK_OPEN]
    open_reqs = [request_out(r, now) for r in reqs if r.status in REQUEST_OPEN]
    levels: dict[str, int] = {}
    for r in risks:
        if r.status != "closed":
            lv = risk_level(r.likelihood * r.impact)
            levels[lv] = levels.get(lv, 0) + 1
    return {
        "tasks": {"open": len(open_tasks), "overdue": sum(1 for t in open_tasks if t["overdue"]),
                  "due_soon": sorted([t for t in open_tasks if t["days_left"] is not None],
                                     key=lambda t: t["days_left"])[:5]},
        "risks": {"open": sum(levels.values()), "by_level": levels, "heat_map": heat_map(risks),
                  "acceptance_expired": sum(1 for r in risks if risk_out(r, now)["acceptance_expired"]),
                  "top": sorted((risk_out(r, now) for r in risks if r.status != "closed"),
                                key=lambda x: -x["score"])[:3]},
        "requests": {"open": len(open_reqs), "overdue": sum(1 for r in open_reqs if r["state"] == "overdue"),
                     "due_soon": sum(1 for r in open_reqs if r["state"] == "due_soon")},
        "vendors": {"active": sum(1 for v in vendors if v.status == "active"),
                    "without_dpa": sum(1 for v in vendors if "no_dpa" in vendor_issues(v, now))},
        "policies": {"approved": sum(1 for p in policies if p.status == "approved"),
                     "review_overdue": sum(1 for p in policies if policy_out(p, now)["review_overdue"])},
        "dpias": {"total": len(dpias), "approved": sum(1 for d in dpias if d.status == "approved"),
                  "pending": sum(1 for d in dpias if d.status in ("draft", "in_review"))},
    }
