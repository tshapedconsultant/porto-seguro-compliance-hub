from __future__ import annotations

from typing import Any

from src.governance.dpia_workspace.models import Assessment
from src.governance.dpia_workspace.risk_engine import art36_needed


DISCLAIMER = (
    "Porto Seguro supports assessment and governance. Regulatory responsibilities remain "
    "with the relevant operators and controllers. This report is not AEPD approval, GDPR "
    "certification, EU AI Act certification, or a claim of full compliance."
)


def build_eipa_report(assessment: Assessment) -> dict[str, Any]:
    art36 = art36_needed(assessment.risks)
    return {
        "document_type": "EIPD_REPORT",
        "disclaimer": DISCLAIMER,
        "cover": {
            "assessment_id": assessment.assessment_id,
            "title": assessment.title,
            "version": assessment.version,
            "lifecycle_state": assessment.lifecycle_state,
            "decision_state": assessment.decision_state,
            "owner": assessment.owner,
            "modified_at": assessment.modified_at,
        },
        "executive_summary": {
            "screening_outcome": assessment.screening.get("outcome"),
            "risk_count": len(assessment.risks),
            "incomplete": bool(assessment.missing_information or assessment.contradictions),
            "art36": art36,
        },
        "processing_description": assessment.processing,
        "necessity_screening": assessment.screening,
        "necessity_and_proportionality": assessment.proportionality,
        "risk_register": assessment.risks,
        "controls": assessment.controls,
        "residual_and_art36": art36,
        "reviews": assessment.reviews,
        "evidence_index": assessment.evidence,
        "missing_information": assessment.missing_information,
        "contradictions": assessment.contradictions,
        "legal_uncertainty": assessment.legal_uncertainty,
        "assumptions": assessment.assumptions,
        "limitations": [
            "Frontend role labels are not authentication.",
            "Local JSON persistence is not multi-tenant isolation.",
            "Generating this report does not change approval state.",
        ],
        "legal_sources": [
            "Regulation (EU) 2016/679",
            "LOPDGDD 3/2018",
            "AEPD EIPD guidance (informative)",
            "Regulation (EU) 2024/1689 — applicability is conditional; see regulatory library",
        ],
    }


def render_text_pdf(title: str, lines: list[str]) -> bytes:
    """Minimal PDF 1.4 (Helvetica). For lab export without extra dependencies."""
    escaped = []
    for raw in lines:
        clipped = raw[:110]
        text = clipped.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        escaped.append(text)
    content = ["BT", "/F1 11 Tf", "50 780 Td", f"({title[:90]}) Tj", "/F1 9 Tf", "0 -18 Td"]
    for line in escaped:
        content.append(f"({line}) Tj")
        content.append("0 -12 Td")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects)+1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(out)


def assessment_pdf_bytes(assessment: Assessment) -> bytes:
    report = build_eipa_report(assessment)
    lines = [
        DISCLAIMER,
        f"ID: {assessment.assessment_id}  v{assessment.version}",
        f"Lifecycle: {assessment.lifecycle_state}  Decision: {assessment.decision_state}",
        f"Screening: {assessment.screening.get('outcome', 'n/a')}",
        f"Risks: {len(assessment.risks)}  Missing: {len(assessment.missing_information)}",
        f"Art.36 flag: {report['residual_and_art36']['may_require_prior_consultation']}",
    ]
    for risk in assessment.risks[:12]:
        lines.append(
            f"{risk.get('risk_id')} inherent={risk.get('inherent_score')} residual={risk.get('residual_score')} {risk.get('threat_scenario', '')[:80]}"
        )
    for rev in assessment.reviews[-5:]:
        lines.append(f"Review {rev.get('role')}: {rev.get('decision')} by {rev.get('actor')}")
    return render_text_pdf(f"EIPD {assessment.title}", lines)
