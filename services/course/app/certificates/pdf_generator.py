"""Certificate PDF generator using ReportLab.

Pure utility — no DB or FastAPI imports.
Generates a single-page landscape A4 PDF with Docfliq branding.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas


@dataclass(frozen=True)
class CertificatePDFData:
    """All data needed to render a certificate PDF."""

    recipient_name: str
    course_title: str
    instructor_name: str
    issued_date: datetime
    total_hours: float | None
    score: int | None
    verification_code: str
    verification_url: str
    module_title: str | None = None
    template: str | None = None


def _generate_qr_image(url: str) -> io.BytesIO:
    """Generate QR code PNG bytes for the verification URL."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def generate_certificate_pdf(data: CertificatePDFData) -> bytes:
    """Generate a branded certificate PDF and return raw bytes."""
    buf = io.BytesIO()
    page_w, page_h = landscape(A4)
    c = canvas.Canvas(buf, pagesize=landscape(A4))

    # --- Background border ---
    margin = 1.5 * cm
    c.setStrokeColor(colors.HexColor("#1a56db"))
    c.setLineWidth(3)
    c.rect(margin, margin, page_w - 2 * margin, page_h - 2 * margin)

    # Inner decorative border
    inner = 2 * cm
    c.setStrokeColor(colors.HexColor("#93bbfb"))
    c.setLineWidth(1)
    c.rect(inner, inner, page_w - 2 * inner, page_h - 2 * inner)

    center_x = page_w / 2

    # --- Header: Docfliq branding ---
    c.setFillColor(colors.HexColor("#1a56db"))
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(center_x, page_h - 3.5 * cm, "DOCFLIQ")

    c.setFillColor(colors.HexColor("#6b7280"))
    c.setFont("Helvetica", 11)
    c.drawCentredString(center_x, page_h - 4.3 * cm, "Professional Learning Platform")

    # --- Decorative line ---
    c.setStrokeColor(colors.HexColor("#1a56db"))
    c.setLineWidth(1.5)
    c.line(center_x - 6 * cm, page_h - 4.8 * cm, center_x + 6 * cm, page_h - 4.8 * cm)

    # --- Title ---
    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica-Bold", 22)
    cert_heading = "Module Certificate" if data.module_title else "Certificate of Completion"
    c.drawCentredString(center_x, page_h - 6 * cm, cert_heading)

    # --- Subtitle ---
    c.setFillColor(colors.HexColor("#6b7280"))
    c.setFont("Helvetica", 12)
    c.drawCentredString(center_x, page_h - 6.8 * cm, "This certifies that")

    # --- Recipient name ---
    c.setFillColor(colors.HexColor("#1a56db"))
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(center_x, page_h - 8 * cm, data.recipient_name)

    # --- Underline for name ---
    name_width = c.stringWidth(data.recipient_name, "Helvetica-Bold", 26)
    c.setStrokeColor(colors.HexColor("#93bbfb"))
    c.setLineWidth(0.5)
    c.line(
        center_x - name_width / 2 - 1 * cm, page_h - 8.3 * cm,
        center_x + name_width / 2 + 1 * cm, page_h - 8.3 * cm,
    )

    # --- "has successfully completed" ---
    c.setFillColor(colors.HexColor("#6b7280"))
    c.setFont("Helvetica", 12)
    completion_text = (
        f"has successfully completed the module"
        if data.module_title
        else "has successfully completed the course"
    )
    c.drawCentredString(center_x, page_h - 9.2 * cm, completion_text)

    # --- Course/Module title ---
    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica-Bold", 18)
    title = data.course_title
    if len(title) > 60:
        title = title[:57] + "..."
    c.drawCentredString(center_x, page_h - 10.2 * cm, title)

    # --- Module title (below course title) ---
    if data.module_title:
        c.setFillColor(colors.HexColor("#4b5563"))
        c.setFont("Helvetica-Bold", 14)
        mod_title = data.module_title
        if len(mod_title) > 60:
            mod_title = mod_title[:57] + "..."
        c.drawCentredString(center_x, page_h - 10.9 * cm, f"Module: {mod_title}")

    # --- Details line (instructor, hours, score) ---
    details_parts = []
    if data.instructor_name:
        details_parts.append(f"Instructor: {data.instructor_name}")
    if data.total_hours is not None:
        details_parts.append(f"Duration: {data.total_hours:.1f} hours")
    if data.score is not None:
        details_parts.append(f"Score: {data.score}%")

    if details_parts:
        c.setFillColor(colors.HexColor("#4b5563"))
        c.setFont("Helvetica", 10)
        details_text = "  |  ".join(details_parts)
        c.drawCentredString(center_x, page_h - 11 * cm, details_text)

    # --- Date ---
    date_str = data.issued_date.strftime("%B %d, %Y")
    c.setFillColor(colors.HexColor("#374151"))
    c.setFont("Helvetica", 11)
    c.drawCentredString(center_x, page_h - 12 * cm, f"Issued on {date_str}")

    # --- QR Code (bottom-right) ---
    qr_buf = _generate_qr_image(data.verification_url)
    from reportlab.lib.utils import ImageReader
    qr_img = ImageReader(qr_buf)
    qr_size = 2.8 * cm
    c.drawImage(
        qr_img,
        page_w - 3.5 * cm - qr_size,
        2.5 * cm,
        width=qr_size,
        height=qr_size,
    )

    # --- Verification code (bottom-center) ---
    c.setFillColor(colors.HexColor("#9ca3af"))
    c.setFont("Helvetica", 8)
    c.drawCentredString(center_x, 2.8 * cm, f"Verification Code: {data.verification_code}")
    c.setFont("Helvetica", 7)
    c.drawCentredString(center_x, 2.2 * cm, f"Verify at: {data.verification_url}")

    # --- Signature line (bottom-left) ---
    sig_x = 5 * cm
    c.setStrokeColor(colors.HexColor("#d1d5db"))
    c.setLineWidth(0.5)
    c.line(sig_x - 2.5 * cm, 3.5 * cm, sig_x + 2.5 * cm, 3.5 * cm)
    c.setFillColor(colors.HexColor("#6b7280"))
    c.setFont("Helvetica", 9)
    c.drawCentredString(sig_x, 2.8 * cm, "Docfliq Platform")

    c.showPage()
    c.save()
    return buf.getvalue()
