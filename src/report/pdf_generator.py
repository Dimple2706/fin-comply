import json
import io
from datetime import datetime, timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.units import inch, cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

# â”€â”€ Color Palette â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
BRAND_DARK   = colors.HexColor('#0B0F19')
BRAND_BLUE   = colors.HexColor('#3B82F6')
BRAND_INDIGO = colors.HexColor('#6366F1')
HEADER_BG    = colors.HexColor('#1E293B')
ROW_ALT      = colors.HexColor('#F8FAFC')
ROW_WHITE    = colors.white
BORDER_COLOR = colors.HexColor('#CBD5E1')
SEV_COLORS = {
    'CRITICAL': colors.HexColor('#EF4444'),
    'HIGH':     colors.HexColor('#F97316'),
    'MEDIUM':   colors.HexColor('#EAB308'),
    'LOW':      colors.HexColor('#22C55E'),
}
URGENCY_COLORS = {
    'IMMEDIATE': colors.HexColor('#EF4444'),
    'HIGH':      colors.HexColor('#F97316'),
    'MEDIUM':    colors.HexColor('#EAB308'),
    'LOW':       colors.HexColor('#22C55E'),
}
TIER_COLORS = {
    'CRITICAL': colors.HexColor('#EF4444'),
    'HIGH':     colors.HexColor('#F97316'),
    'MEDIUM':   colors.HexColor('#EAB308'),
    'LOW':      colors.HexColor('#22C55E'),
    'COMPLIANT':colors.HexColor('#22C55E'),
}


def _build_styles():
    """Create the style dictionary for the PDF."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        'ReportTitle', parent=styles['Heading1'],
        fontSize=24, alignment=TA_CENTER, spaceAfter=6,
        textColor=BRAND_DARK, fontName='Helvetica-Bold',
    ))
    styles.add(ParagraphStyle(
        'ReportSubtitle', parent=styles['Normal'],
        fontSize=11, alignment=TA_CENTER, spaceAfter=4,
        textColor=colors.HexColor('#64748B'),
    ))
    styles.add(ParagraphStyle(
        'SectionTitle', parent=styles['Heading2'],
        fontSize=14, spaceBefore=18, spaceAfter=8,
        textColor=BRAND_DARK, fontName='Helvetica-Bold',
        borderWidth=0, borderPadding=0,
    ))
    styles.add(ParagraphStyle(
        'SubSection', parent=styles['Heading3'],
        fontSize=11, spaceBefore=10, spaceAfter=4,
        textColor=colors.HexColor('#334155'), fontName='Helvetica-Bold',
    ))
    styles.add(ParagraphStyle(
        'CustomBodyText', parent=styles['Normal'],
        fontSize=9.5, leading=14, alignment=TA_JUSTIFY,
        textColor=colors.HexColor('#334155'),
    ))
    styles.add(ParagraphStyle(
        'SmallMono', parent=styles['Normal'],
        fontSize=8, fontName='Courier', leading=11,
        textColor=colors.HexColor('#475569'),
    ))
    styles.add(ParagraphStyle(
        'CellText', parent=styles['Normal'],
        fontSize=8.5, leading=11,
        textColor=colors.HexColor('#1E293B'),
    ))
    styles.add(ParagraphStyle(
        'CellBold', parent=styles['Normal'],
        fontSize=8.5, leading=11, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#1E293B'),
    ))
    styles.add(ParagraphStyle(
        'FooterText', parent=styles['Normal'],
        fontSize=7, alignment=TA_CENTER,
        textColor=colors.HexColor('#94A3B8'),
    ))
    return styles


def _header_row_style():
    """Common table style for header rows."""
    return [
        ('BACKGROUND',   (0, 0), (-1, 0), HEADER_BG),
        ('TEXTCOLOR',    (0, 0), (-1, 0), colors.white),
        ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, 0), 8.5),
        ('BOTTOMPADDING',(0, 0), (-1, 0), 8),
        ('TOPPADDING',   (0, 0), (-1, 0), 8),
        ('ALIGN',        (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME',     (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',     (0, 1), (-1, -1), 8),
        ('TOPPADDING',   (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING',(0, 1), (-1, -1), 5),
        ('GRID',         (0, 0), (-1, -1), 0.5, BORDER_COLOR),
    ]


def _alternating_rows(row_count):
    """Return style commands for alternating row colors."""
    cmds = []
    for i in range(1, row_count):
        bg = ROW_ALT if i % 2 == 0 else ROW_WHITE
        cmds.append(('BACKGROUND', (0, i), (-1, i), bg))
    return cmds


def generate_pdf_report(tenant_id: str, db_conn, audit_run_id: str) -> io.BytesIO:
    """
    Generates a comprehensive, professional DPDP compliance audit PDF report.
    """
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT result_json, created_at 
            FROM evaluation_results 
            WHERE tenant_id = %s AND audit_run_id = %s
            """,
            (tenant_id, audit_run_id)
        )
        row = cur.fetchone()

    if not row:
        raise ValueError(f"No compliance data found for tenant {tenant_id}")

    if isinstance(row, dict):
        result_json = row.get("result_json")
        eval_date = row.get("created_at")
    else:
        result_json = row[0]
        eval_date = row[1]

    if isinstance(eval_date, str):
        try:
            eval_date = datetime.fromisoformat(eval_date.replace("Z", "+00:00"))
        except Exception:
            eval_date = datetime.now(timezone.utc)

    data = result_json if isinstance(result_json, dict) else json.loads(result_json)

    styles = _build_styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=36, leftMargin=36,
        topMargin=36, bottomMargin=36,
    )

    elements = []
    page_width = A4[0] - 72  # usable width

    # ══════════════════════════════════════════════════════════
    # PAGE 1: TITLE + EXECUTIVE SUMMARY + SCORE CARD + ML LAYER
    # ══════════════════════════════════════════════════════════
    elements.append(Spacer(1, 1.2 * inch))

    # Decorative top line
    elements.append(HRFlowable(
        width="100%", thickness=3, color=BRAND_BLUE,
        spaceAfter=20, spaceBefore=0,
    ))

    elements.append(Paragraph("DPDP Compliance Audit Report", styles['ReportTitle']))
    elements.append(Spacer(1, 0.1 * inch))

    tenant_name = data.get('tenant_name', tenant_id)
    elements.append(Paragraph(f"Organisation: {tenant_name}", styles['ReportSubtitle']))
    elements.append(Paragraph(f"Tenant ID: {tenant_id}", styles['ReportSubtitle']))
    elements.append(Paragraph(
        f"Report Generated: {eval_date.strftime('%d %B %Y, %H:%M UTC') if eval_date else 'N/A'}",
        styles['ReportSubtitle']
    ))
    elements.append(Paragraph(
        "Digital Personal Data Protection Act, 2023 — Automated Compliance Assessment",
        styles['ReportSubtitle']
    ))

    regulatory_context = data.get("regulatory_context") or {}
    if regulatory_context:
        assessment_label = regulatory_context.get("assessment_type", "EVIDENCE_ASSESSMENT").replace("_", " ")
        elements.append(Paragraph(
            f"<b>Assessment basis:</b> {assessment_label} | "
            f"<b>Assessment date:</b> {regulatory_context.get('assessment_date', 'N/A')} | "
            f"<b>Substantive effective date:</b> {regulatory_context.get('substantive_effective_date', 'N/A')}",
            styles['ReportSubtitle']
        ))
        elements.append(Paragraph(
            regulatory_context.get("disclaimer", ""),
            styles['ReportSubtitle']
        ))

    # Audit Run Metadata if present
    run_meta = data.get("run_metadata")
    if run_meta:
        meta_sha = run_meta.get("model_sha256", "N/A")
        meta_sha_short = meta_sha[:16] + "..." if len(meta_sha) > 16 else meta_sha
        elements.append(Paragraph(
            f"<b>Engine Build:</b> v{run_meta.get('engine_version', '1.0.0')} | <b>Schema:</b> {run_meta.get('schema_version', '2026.1')} | <b>Model SHA:</b> {meta_sha_short}",
            styles['ReportSubtitle']
        ))

    elements.append(HRFlowable(
        width="100%", thickness=1, color=BORDER_COLOR,
        spaceAfter=20, spaceBefore=20,
    ))

    # ── Executive Summary ──
    elements.append(Paragraph("1. Executive Summary", styles['SectionTitle']))
    exec_sum = data.get("executive_summary", "No executive summary available.")
    elements.append(Paragraph(exec_sum, styles['CustomBodyText']))
    elements.append(Spacer(1, 0.15 * inch))

    # ── Score Card ──
    elements.append(Paragraph("2. Compliance Score Card", styles['SectionTitle']))

    score = data.get("risk_score", 0)
    tier = data.get("risk_tier", "UNKNOWN")
    tier_color = TIER_COLORS.get(tier, colors.grey)

    score_data = [
        ["Metric", "Value"],
        ["Audit Run ID", str(data.get("audit_run_id", "N/A"))],
        ["Audit Run Status", str(data.get("run_status", "completed")).upper()],
        ["ISO 31000 Risk Score", f"{score} / 100"],
        ["Deterministic Risk Tier", tier],
        ["Compliance Score Percentage", f"{data.get('compliance_score', {}).get('score_percentage', 0.0):.1f}%"],
        ["Satisfied Obligations (PASS)", str(data.get('compliance_score', {}).get('satisfied_obligations', 0))],
        ["Violated Obligations (VIOLATION)", str(data.get('compliance_score', {}).get('violated_obligations', 0))],
        ["Failed Obligations (FAILED)", str(data.get('compliance_score', {}).get('failed_obligations', 0))],
        ["Not Assessable Obligations", str(data.get('compliance_score', {}).get('not_assessable_obligations', 0))],
        ["Unique Rules Violated", str(data.get("unique_rules_violated", 0))],
        ["Total Violation Occurrences", str(data.get("total_violation_occurrences", 0))],
        ["Maximum Financial Exposure", f"₹ {data.get('total_penalty_exposure_crore', 0)} Crore"],
    ]

    # Include ML validation tier if available
    ml = data.get("ml_layer")
    if ml and ml.get("ml_available"):
        ml_tier = ml.get("predicted_tier", "UNKNOWN")
        ml_conf = ml.get("probabilities", {}).get(ml_tier, 0)
        conf_str = f"{ml_conf:.1f}%" if ml_conf > 1 else f"{ml_conf * 100:.1f}%"
        score_data.append(["ML Predicted Risk Tier (XGBoost)", f"{ml_tier} (Confidence: {conf_str})"])

    t = Table(score_data, colWidths=[page_width * 0.55, page_width * 0.45])
    style_cmds = _header_row_style() + _alternating_rows(len(score_data))
    style_cmds.append(('TEXTCOLOR', (1, 4), (1, 4), tier_color))
    style_cmds.append(('FONTNAME', (1, 4), (1, 4), 'Helvetica-Bold'))
    t.setStyle(TableStyle(style_cmds))
    elements.append(t)
    elements.append(Spacer(1, 0.1 * inch))
    
    disclaimer_text = f"<b>Disclaimer:</b> {data.get('disclaimer', 'Maximum statutory exposure estimate — not an actual or certain fine.')}"
    elements.append(Paragraph(disclaimer_text, styles['CustomBodyText']))

    elements.append(PageBreak())

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # PAGE 2: AGENT BREAKDOWN + RISK CONTRIBUTIONS
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    # â”€â”€ Agent Breakdown â”€â”€
    elements.append(Paragraph("3. Agent Analysis Breakdown", styles['SectionTitle']))
    agent_breakdown = data.get("agent_breakdown", {})

    if agent_breakdown:
        agent_data = [["Agent", "Violations", "Warnings", "Total Findings"]]
        total_v = 0
        total_w = 0
        for agent_key, info in agent_breakdown.items():
            v_count = info.get("violations", 0) if isinstance(info, dict) else 0
            w_count = info.get("warnings", 0) if isinstance(info, dict) else 0
            total_v += v_count
            total_w += w_count
            name = agent_key.replace('_', ' ').title()
            agent_data.append([name, str(v_count), str(w_count), str(v_count + w_count)])

        agent_data.append(["TOTAL", str(total_v), str(total_w), str(total_v + total_w)])

        at = Table(agent_data, colWidths=[page_width * 0.40, page_width * 0.20, page_width * 0.20, page_width * 0.20])
        style_cmds = _header_row_style() + _alternating_rows(len(agent_data))
        # Bold the total row
        last_row = len(agent_data) - 1
        style_cmds.append(('FONTNAME', (0, last_row), (-1, last_row), 'Helvetica-Bold'))
        style_cmds.append(('BACKGROUND', (0, last_row), (-1, last_row), colors.HexColor('#E2E8F0')))
        at.setStyle(TableStyle(style_cmds))
        elements.append(at)
    else:
        elements.append(Paragraph("No agent breakdown data available.", styles['CustomBodyText']))

    elements.append(Spacer(1, 0.2 * inch))

    # â”€â”€ Risk Contributions â”€â”€
    elements.append(Paragraph("4. Rule-Level Risk Contributions", styles['SectionTitle']))
    elements.append(Paragraph(
        "Each rule's contribution to the overall risk score, computed using the ISO 31000 "
        "Likelihood Ã— Impact framework with DPDP Act Section 33 recurrence escalation.",
        styles['CustomBodyText']
    ))
    elements.append(Spacer(1, 0.1 * inch))

    contributions = data.get("risk_contributions", {})
    violations_list = data.get("violations", [])

    if contributions:
        sorted_contribs = sorted(contributions.items(), key=lambda x: x[1], reverse=True)
        contrib_data = [["Rule ID", "Rule Name", "Severity", "Contribution", "% of Score"]]
        total_contrib = sum(contributions.values())

        for rule_id, contrib_val in sorted_contribs:
            # Find the violation to get name and severity
            viol = next((v for v in violations_list if v.get("rule_id") == rule_id), {})
            rule_name = viol.get("rule_name", rule_id)
            severity = viol.get("severity", "â€”")
            pct = (contrib_val / total_contrib * 100) if total_contrib > 0 else 0
            contrib_data.append([
                rule_id,
                Paragraph(rule_name, styles['CellText']),
                severity,
                f"{contrib_val:.4f}",
                f"{pct:.1f}%",
            ])

        ct = Table(contrib_data, colWidths=[
            page_width * 0.14, page_width * 0.36, page_width * 0.14,
            page_width * 0.18, page_width * 0.18
        ])
        style_cmds = _header_row_style() + _alternating_rows(len(contrib_data))
        ct.setStyle(TableStyle(style_cmds))
        elements.append(ct)
    else:
        elements.append(Paragraph("No risk contribution data available.", styles['CustomBodyText']))

    elements.append(PageBreak())

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # PAGE 3: REMEDIATION PRIORITY
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    elements.append(Paragraph("5. Remediation Priority", styles['SectionTitle']))
    elements.append(Paragraph(
        "Actions ordered by urgency (DPDP Act severity mapping) and risk contribution. "
        "Immediate items should be addressed within 72 hours.",
        styles['CustomBodyText']
    ))
    elements.append(Spacer(1, 0.1 * inch))

    remediation = data.get("remediation_priority", [])

    if remediation:
        rem_data = [["#", "Rule ID", "Rule Name", "Action", "Urgency", "Exposure"]]
        for item in remediation:
            rem_data.append([
                str(item.get("priority", "")),
                item.get("rule_id", ""),
                Paragraph(item.get("rule_name", ""), styles['CellText']),
                Paragraph(item.get("action", "No action specified"), styles['CellText']),
                item.get("urgency", ""),
                f"â‚¹{item.get('penalty_exposure_crore', 0)} Cr",
            ])

        rt = Table(rem_data, colWidths=[
            page_width * 0.05, page_width * 0.10, page_width * 0.18,
            page_width * 0.40, page_width * 0.12, page_width * 0.15
        ])
        style_cmds = _header_row_style() + _alternating_rows(len(rem_data))
        rt.setStyle(TableStyle(style_cmds))
        elements.append(rt)
    else:
        elements.append(Paragraph("No remediation actions required. Full compliance.", styles['CustomBodyText']))

    elements.append(PageBreak())

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # PAGES 4+: DETAILED VIOLATION ANALYSIS (EXPLAINABILITY)
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    elements.append(Paragraph("6. Detailed Violation Analysis", styles['SectionTitle']))
    elements.append(Paragraph(
        "Each violated rule is explained with SHAP-equivalent signal attribution (Ï† values), "
        "DPDP Act legal context, root cause classification, and remediation steps.",
        styles['CustomBodyText']
    ))
    elements.append(Spacer(1, 0.15 * inch))

    if violations_list:
        for idx, viol in enumerate(violations_list):
            rule_id = viol.get("rule_id", "UNKNOWN")
            rule_name = viol.get("rule_name", "Unknown Rule")
            severity = viol.get("severity", "LOW")
            occ = viol.get("occurrence_count", 0)
            penalty = viol.get("penalty_exposure_crore", 0)
            root_cause = viol.get("root_cause", "â€”")
            contrib = viol.get("contribution_to_score", 0)

            exp = viol.get("explanation", {}) or {}

            # â”€â”€ Violation Header â”€â”€
            sev_color = SEV_COLORS.get(severity, colors.grey)
            header_text = f'6.{idx+1} &nbsp; <font color="#{sev_color.hexval()[2:]}">[{severity}]</font> &nbsp; {rule_id} â€” {rule_name}'
            elements.append(Paragraph(header_text, styles['SubSection']))

            # â”€â”€ Quick facts table â”€â”€
            facts = [
                ["Occurrences", str(occ)],
                ["Penalty Exposure", f"â‚¹{penalty} Crore"],
                ["Risk Contribution", f"{contrib:.4f}"],
                ["Root Cause", root_cause.replace('_', ' ').title()],
                ["Top Signal", exp.get("top_contributing_signal", "â€”")],
            ]
            ft = Table(facts, colWidths=[page_width * 0.30, page_width * 0.70])
            ft.setStyle(TableStyle([
                ('FONTNAME',     (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE',     (0, 0), (-1, -1), 8),
                ('TOPPADDING',   (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING',(0, 0), (-1, -1), 3),
                ('TEXTCOLOR',    (0, 0), (-1, -1), colors.HexColor('#334155')),
                ('LINEBELOW',    (0, -1), (-1, -1), 0.5, BORDER_COLOR),
            ]))
            elements.append(ft)
            elements.append(Spacer(1, 0.1 * inch))

            # â”€â”€ What Happened â”€â”€
            why_detected = exp.get("why_detected", "")
            if why_detected:
                elements.append(Paragraph("<b>What Happened:</b>", styles['CellBold']))
                elements.append(Paragraph(why_detected, styles['CustomBodyText']))
                elements.append(Spacer(1, 0.05 * inch))

            # â”€â”€ DPDP Act Violation â”€â”€
            risk_reason = exp.get("risk_reason", "")
            if risk_reason:
                elements.append(Paragraph("<b>DPDP Act Violation:</b>", styles['CellBold']))
                elements.append(Paragraph(f"<i>{risk_reason}</i>", styles['CustomBodyText']))
                elements.append(Spacer(1, 0.05 * inch))

            # ── Signal Attribution Table (Deterministic Rule Weights) ──
            signals = exp.get("signals_analysis", [])
            if signals:
                elements.append(Paragraph("<b>Signal Attribution (Deterministic Weight):</b>", styles['CellBold']))
                sig_data = [["Signal", "Description", "Weight", "Fired", "Contribution", "Reason"]]
                for s in signals:
                    fired_str = "✓" if s.get("fired") else "—"
                    contrib_val = s.get("signal_contribution", s.get("phi", 0))
                    sig_data.append([
                        s.get("signal", ""),
                        Paragraph(s.get("description", "—"), styles['CellText']),
                        f"{s.get('weight', 0):.2f}",
                        fired_str,
                        f"{contrib_val:.2f}",
                        Paragraph(s.get("reason", "—") if s.get("fired") else "—", styles['CellText']),
                    ])

                # Total row
                total_sig = exp.get("total_signal_weight", exp.get("total_shap", sum(s.get("signal_contribution", s.get("phi", 0)) for s in signals)))
                sig_data.append(["", "", "", "", f"{total_sig:.2f}", Paragraph("<b>Total Signal Weight</b>", styles['CellBold'])])

                st = Table(sig_data, colWidths=[
                    page_width * 0.08, page_width * 0.25, page_width * 0.08,
                    page_width * 0.07, page_width * 0.08, page_width * 0.44
                ])
                style_cmds = _header_row_style() + _alternating_rows(len(sig_data))
                last = len(sig_data) - 1
                style_cmds.append(('BACKGROUND', (0, last), (-1, last), colors.HexColor('#EFF6FF')))
                style_cmds.append(('FONTNAME', (4, last), (4, last), 'Helvetica-Bold'))
                st.setStyle(TableStyle(style_cmds))
                elements.append(st)
                elements.append(Spacer(1, 0.05 * inch))

            # â”€â”€ Remediation Steps â”€â”€
            mitigation = exp.get("mitigation", [])
            if mitigation and isinstance(mitigation, list):
                elements.append(Paragraph("<b>Remediation Steps:</b>", styles['CellBold']))
                for i, step in enumerate(mitigation):
                    elements.append(Paragraph(f"{i+1}. {step}", styles['CustomBodyText']))
                elements.append(Spacer(1, 0.05 * inch))

            # Separator between violations
            elements.append(HRFlowable(
                width="100%", thickness=0.5, color=BORDER_COLOR,
                spaceAfter=12, spaceBefore=8,
            ))
    else:
        elements.append(Paragraph("No violations detected. Full DPDP compliance achieved.", styles['CustomBodyText']))

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # FOOTER / DISCLAIMER
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    elements.append(Spacer(1, 0.3 * inch))
    elements.append(HRFlowable(width="100%", thickness=1, color=BRAND_BLUE, spaceAfter=10))
    elements.append(Paragraph(
        "This report was generated by <b>Fin-Comply</b> â€” AI-Powered DPDP Regulatory Intelligence System. "
        "Risk scoring follows the ISO 31000 Likelihood Ã— Impact framework with DPDP Act Section 33 recurrence escalation. "
        "Signal attribution uses analytical SHAP (Lundberg & Lee, 2017) for linear additive scoring models.",
        styles['FooterText']
    ))
    elements.append(Paragraph(
        f"Report ID: RPT-{tenant_id}-{eval_date.strftime('%Y%m%d%H%M') if eval_date else 'NA'} "
        f"| Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        styles['FooterText']
    ))

    # Build
    doc.build(elements)
    buffer.seek(0)
    return buffer

