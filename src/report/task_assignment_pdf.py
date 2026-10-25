
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)


def generate_task_assignment_pdf(tenant_id, audit_run_id, tasks):
    """Generate a PDF containing assignments for one tenant audit run."""

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=(595.28, 841.89),
        rightMargin=40,
        leftMargin=40,
        topMargin=45,
        bottomMargin=45,
    )

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="TaskReportTitle",
            parent=styles["Title"],
            fontSize=20,
            leading=25,
            textColor=colors.HexColor("#263C70"),
            alignment=TA_CENTER,
            spaceAfter=18,
        )
    )

    styles.add(
        ParagraphStyle(
            name="TaskReportBody",
            parent=styles["BodyText"],
            fontSize=9,
            leading=14,
            spaceAfter=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="TaskReportHeading",
            parent=styles["Heading2"],
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#263C70"),
            spaceBefore=15,
            spaceAfter=9,
        )
    )

    story = [
        Paragraph("Fin-Comply", styles["TaskReportTitle"]),
        Paragraph(
            "TASK ASSESSMENT & ASSIGNMENT REPORT",
            styles["Heading2"],
        ),
        Paragraph(
            f"<b>Tenant:</b> {escape(str(tenant_id))}",
            styles["TaskReportBody"],
        ),
        Paragraph(
            f"<b>Audit Run:</b> {escape(str(audit_run_id))}",
            styles["TaskReportBody"],
        ),
        Spacer(1, 12),
    ]

    counts = {
        priority: sum(
            task["priority"] == priority for task in tasks
        )
        for priority in ("Critical", "High", "Medium", "Low")
    }

    summary = [
        ["Total Tasks", "Critical", "High", "Medium", "Low"],
        [
            str(len(tasks)),
            str(counts["Critical"]),
            str(counts["High"]),
            str(counts["Medium"]),
            str(counts["Low"]),
        ],
    ]

    table = Table(summary, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263C70")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ]
        )
    )

    story.extend([table, Spacer(1, 20)])

    if not tasks:
        story.append(
            Paragraph(
                "No actionable task assignments were found for this audit run.",
                styles["TaskReportBody"],
            )
        )

    for index, task in enumerate(tasks, start=1):
        steps = task.get("remediation_steps") or []

        content = [
            Paragraph(
                f"{index}. {escape(str(task['task_title']))}",
                styles["TaskReportHeading"],
            ),
            Paragraph(
                f"<b>Rule:</b> {escape(str(task['rule_id']))} "
                f"| <b>Signal:</b> {escape(str(task['signal_id']))}",
                styles["TaskReportBody"],
            ),
            Paragraph(
                f"<b>Priority:</b> {escape(str(task['priority']))}",
                styles["TaskReportBody"],
            ),
            Paragraph(
                f"<b>Responsible Team:</b> "
                f"{escape(str(task['responsible_team']))}",
                styles["TaskReportBody"],
            ),
            Paragraph(
                f"<b>Affected Records:</b> "
                f"{task['affected_records_count']}",
                styles["TaskReportBody"],
            ),
            Paragraph(
                escape(str(task["task_description"])),
                styles["TaskReportBody"],
            ),
            Paragraph(
                "<b>Remediation Steps:</b>",
                styles["TaskReportBody"],
            ),
        ]

        for step_number, step in enumerate(steps, start=1):
            content.append(
                Paragraph(
                    f"{step_number}. {escape(str(step))}",
                    styles["TaskReportBody"],
                )
            )

        story.append(KeepTogether(content))
        story.append(Spacer(1, 12))

    doc.build(story)
    buffer.seek(0)

    return buffer
