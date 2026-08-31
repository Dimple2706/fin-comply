"""Authoritative regulatory timing context attached to every assessment."""

from datetime import date


SUBSTANTIVE_EFFECTIVE_DATE = date(2027, 5, 13)


def build_regulatory_context(as_of: date | None = None) -> dict:
    assessment_date = as_of or date.today()
    future_readiness = assessment_date < SUBSTANTIVE_EFFECTIVE_DATE
    return {
        "framework": "Digital Personal Data Protection Act, 2023 and DPDP Rules, 2025",
        "assessment_date": assessment_date.isoformat(),
        "substantive_effective_date": SUBSTANTIVE_EFFECTIVE_DATE.isoformat(),
        "assessment_type": (
            "FUTURE_READINESS" if future_readiness else "OPERATIONAL_COMPLIANCE"
        ),
        "basis": (
            "Readiness assessment against notified provisions whose principal "
            "operational commencement is scheduled for 13 May 2027."
            if future_readiness
            else "Operational evidence assessment against provisions in force."
        ),
        "act_source": "https://www.meity.gov.in/static/uploads/2024/02/Digital-Personal-Data-Protection-Act-2023-1.pdf",
        "rules_source": "https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf",
        "disclaimer": (
            "Automated evidence-based decision support only; not legal advice, "
            "regulatory certification, or a determination by the Data Protection Board."
        ),
    }
