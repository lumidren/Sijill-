"""Demo processing register for the fictional Nour Family Clinic (started, not finished)."""
from __future__ import annotations

from datetime import datetime, timedelta

from .models import ProcessingActivity

ACTIVITIES = [
    dict(name="Patient medical records", purpose="Providing medical care and keeping a continuous clinical history.",
         lawful_basis="To be confirmed with legal adviser", data_subjects=["Patients", "Parents or guardians of child patients"],
         data_categories=["Identity and contact details", "National ID number", "Medical history", "Diagnoses and prescriptions"],
         sensitive_categories=["Health data"], source="Patients at registration and consultations",
         recipients=["Partner laboratory", "Referred specialists"], cross_border=True,
         transfer_countries=["Germany (AWS eu-central-1 hosting)"], transfer_safeguards="",
         retention="To be defined", security_measures="Encrypted database, role-based access in the EHR system, audit logging.",
         systems=["EHR (nour-ehr-db)", "Paper archive"], owner="Dr. Mona Hassan"),
    dict(name="Appointment booking and SMS reminders", purpose="Booking visits and reminding patients of appointments.",
         lawful_basis="To be confirmed with legal adviser", data_subjects=["Patients"],
         data_categories=["Name", "Mobile number", "Appointment time"], source="Patients by phone and booking form",
         recipients=["SMS gateway provider"], retention="12 months after the appointment",
         security_measures="Access limited to reception staff.", systems=["Booking app", "nour-appointment-reminders"],
         owner="Reception supervisor"),
    dict(name="Billing and insurance claims", purpose="Invoicing patients and submitting claims to insurers.",
         lawful_basis="To be confirmed with legal adviser", data_subjects=["Patients"],
         data_categories=["Identity details", "Insurance policy number", "Services provided"],
         sensitive_categories=["Health data (procedure codes)"], source="Patients and the EHR",
         recipients=["Health insurance companies"], retention="As required for tax records (to be confirmed)",
         security_measures="", systems=["Billing module"], owner="Finance officer"),
    dict(name="Staff HR records", purpose="Employment administration and payroll.",
         lawful_basis="To be confirmed with legal adviser", data_subjects=["Employees", "Job applicants"],
         data_categories=["Identity and contact details", "Salary", "Qualifications"], source="Employees",
         recipients=["Payroll bank"], retention="", security_measures="Locked cabinet; HR folder restricted.",
         systems=["HR spreadsheet"], owner="Clinic manager"),
    dict(name="CCTV in the waiting area", purpose="Safety of patients and staff.",
         lawful_basis="To be confirmed with legal adviser", data_subjects=["Patients", "Visitors", "Staff"],
         data_categories=["Video images"], source="Cameras in the waiting area and entrance",
         recipients=[], retention="30 days, then overwritten", security_measures="Recorder in locked IT room.",
         systems=["CCTV recorder"], owner="Omar Adel (IT)"),
]


def seed_register(db, users, now: datetime) -> str:
    dpo = users["dpo"]
    for i, fields in enumerate(ACTIVITIES):
        when = now - timedelta(days=21 - i)
        db.add(ProcessingActivity(role="controller", created_at=when, updated_at=when, updated_by_id=dpo.id, **fields))
    db.flush()
    return f"{len(ACTIVITIES)} register entries"
