"""
Receipt PDF generation service for Tap&Go.

Generates professional, branded single-page PDF receipts entirely in memory
using ReportLab Platypus.

Key design decisions:
- NotoSans-Regular/Bold TTF fonts bundled in backend/app/assets/fonts/ to correctly
  render the Indian Rupee symbol (₹ / U+20B9), which renders as a black box with
  Helvetica. Noto Sans is a SIL OFL licensed open font.
- Falls back gracefully to Helvetica if fonts cannot be loaded (e.g. stripped builds).
- Zero persistent disk I/O — uses io.BytesIO throughout.
- Uses the official Tap&Go homepage logo (cached and resized).
- Never raises exceptions to the caller; returns None on any failure so that
  financial transactions and emails are never interrupted.
"""

import os
import io
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    KeepTogether,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

# ─── Font Registration ────────────────────────────────────────────────────────
# NotoSans contains the Indian Rupee glyph (₹ / U+20B9).
# Bundled at backend/app/assets/fonts/ for production deployments.
_FONTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../assets/fonts"))
_FONT_REGULAR_PATH = os.path.join(_FONTS_DIR, "NotoSans-Regular.ttf")
_FONT_BOLD_PATH    = os.path.join(_FONTS_DIR, "NotoSans-Bold.ttf")

_noto_registered: bool = False

def _ensure_fonts() -> tuple[str, str]:
    """
    Registers NotoSans-Regular and NotoSans-Bold with ReportLab if the bundled
    font files are present.  Returns (normal_face, bold_face) — either
    ('NotoSans', 'NotoSans-Bold') on success, or ('Helvetica', 'Helvetica-Bold')
    as a safe fallback so the PDF still builds.
    """
    global _noto_registered
    if _noto_registered:
        return ("NotoSans", "NotoSans-Bold")

    try:
        if os.path.isfile(_FONT_REGULAR_PATH) and os.path.getsize(_FONT_REGULAR_PATH) > 50_000:
            pdfmetrics.registerFont(TTFont("NotoSans", _FONT_REGULAR_PATH))
        else:
            raise FileNotFoundError(_FONT_REGULAR_PATH)

        if os.path.isfile(_FONT_BOLD_PATH) and os.path.getsize(_FONT_BOLD_PATH) > 50_000:
            pdfmetrics.registerFont(TTFont("NotoSans-Bold", _FONT_BOLD_PATH))
        else:
            raise FileNotFoundError(_FONT_BOLD_PATH)

        _noto_registered = True
        logger.info("[ReceiptService] NotoSans fonts registered successfully (₹ glyph supported).")
        return ("NotoSans", "NotoSans-Bold")
    except Exception as e:
        logger.warning(f"[ReceiptService] NotoSans font registration failed — falling back to Helvetica: {e}")
        return ("Helvetica", "Helvetica-Bold")


# ─── Logo Cache ───────────────────────────────────────────────────────────────
_cached_logo_path: Optional[str] = None
_cached_logo_bytes: Optional[bytes] = None
_logo_checked: bool = False


def get_logo_path() -> Optional[str]:
    """
    Resolves the exact file path to the official Tap&Go homepage logo.
    Checks the deterministic backend asset directory first, then falls back
    to monorepo paths if running in a shared development workspace.
    """
    global _cached_logo_path, _logo_checked
    if _logo_checked and _cached_logo_path:
        return _cached_logo_path

    candidates = [
        # 1. Authoritative backend asset copy (present in production Docker/Render build)
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../assets/logo.png")),
        # 2. Frontend public directory
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../frontend/public/logio.png")),
        # 3. Frontend src asset directory
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../frontend/src/assets/images/logio.png")),
        # 4. Current working directory relative paths
        os.path.abspath("backend/app/assets/logo.png"),
        os.path.abspath("app/assets/logo.png"),
    ]

    for path in candidates:
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            _cached_logo_path = path
            break

    _logo_checked = True
    return _cached_logo_path


def get_optimized_logo_bytes() -> Optional[bytes]:
    """
    Returns an optimized thumbnail of the official Tap&Go logo cached in memory.
    Resizes the high-res 1024x1024 homepage logo to a crisp 192x192 retina asset,
    reducing PDF receipt attachment sizes from ~2.4MB down to ~25KB while
    preserving pixel-perfect clarity.
    """
    global _cached_logo_bytes
    if _cached_logo_bytes:
        return _cached_logo_bytes

    logo_path = get_logo_path()
    if not logo_path:
        return None

    try:
        from PIL import Image as PILImage
        with PILImage.open(logo_path) as img:
            thumb = img.copy()
            thumb.thumbnail((192, 192), getattr(PILImage, "Resampling", PILImage).LANCZOS)
            buf = io.BytesIO()
            thumb.save(buf, format="PNG", optimize=True)
            _cached_logo_bytes = buf.getvalue()
            return _cached_logo_bytes
    except Exception as e:
        logger.warning(f"[ReceiptService] Could not generate optimized logo thumbnail: {e}")
        try:
            with open(logo_path, "rb") as f:
                _cached_logo_bytes = f.read()
                return _cached_logo_bytes
        except Exception:
            return None


# ─── Utilities ────────────────────────────────────────────────────────────────

def format_datetime(dt_val: Any) -> str:
    """
    Formats a transaction timestamp into a clean, human-readable string.
    Converts UTC to Indian Standard Time (IST, UTC+5:30) with clear timezone labeling.
    """
    if not dt_val:
        dt = datetime.utcnow()
    elif isinstance(dt_val, str):
        try:
            clean_str = dt_val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
        except Exception:
            return str(dt_val)
    elif isinstance(dt_val, datetime):
        dt = dt_val
    else:
        dt = datetime.utcnow()

    # Convert UTC to IST (+5:30)
    ist_dt = dt + timedelta(hours=5, minutes=30)
    return ist_dt.strftime("%d %B %Y, %I:%M %p IST")


def format_inr(amount: Any) -> str:
    """Formats numeric amounts to Indian Rupees string e.g. ₹120.00"""
    try:
        val = float(amount)
        return f"\u20b9{val:,.2f}"
    except (ValueError, TypeError):
        return f"\u20b9{amount}"


# ─── Style Builder ────────────────────────────────────────────────────────────

def _build_styles() -> Dict[str, ParagraphStyle]:
    """Builds a consistent typography and styling palette for Tap&Go receipts."""
    base = getSampleStyleSheet()
    normal_face, bold_face = _ensure_fonts()

    return {
        "BrandTitle": ParagraphStyle(
            "BrandTitle",
            parent=base["Normal"],
            fontName=bold_face,
            fontSize=19,
            leading=23,
            textColor=colors.HexColor("#1C1C1E"),
        ),
        "BrandTagline": ParagraphStyle(
            "BrandTagline",
            parent=base["Normal"],
            fontName=normal_face,
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#6B7280"),
            spaceAfter=0,
        ),
        "ReceiptType": ParagraphStyle(
            "ReceiptType",
            parent=base["Normal"],
            fontName=bold_face,
            fontSize=12,
            leading=16,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#1C1C1E"),
        ),
        "ReceiptRef": ParagraphStyle(
            "ReceiptRef",
            parent=base["Normal"],
            fontName="Courier-Bold",
            fontSize=8.5,
            leading=12,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#4B5563"),
        ),
        "StatusBadge": ParagraphStyle(
            "StatusBadge",
            parent=base["Normal"],
            fontName=bold_face,
            fontSize=8,
            leading=11,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#059669"),
        ),
        "SectionHeading": ParagraphStyle(
            "SectionHeading",
            parent=base["Normal"],
            fontName=bold_face,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#1C1C1E"),
        ),
        "CellLabel": ParagraphStyle(
            "CellLabel",
            parent=base["Normal"],
            fontName=normal_face,
            fontSize=8.5,
            leading=13,
            textColor=colors.HexColor("#6B7280"),
        ),
        "CellValue": ParagraphStyle(
            "CellValue",
            parent=base["Normal"],
            fontName=bold_face,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#111827"),
        ),
        "CellValueRight": ParagraphStyle(
            "CellValueRight",
            parent=base["Normal"],
            fontName=bold_face,
            fontSize=9,
            leading=13,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#111827"),
        ),
        "TotalLabel": ParagraphStyle(
            "TotalLabel",
            parent=base["Normal"],
            fontName=bold_face,
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#1C1C1E"),
        ),
        "TotalAmount": ParagraphStyle(
            "TotalAmount",
            parent=base["Normal"],
            fontName=bold_face,
            fontSize=16,
            leading=20,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#059669"),
        ),
        "ThankYouText": ParagraphStyle(
            "ThankYouText",
            parent=base["Normal"],
            fontName=bold_face,
            fontSize=10,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#1C1C1E"),
        ),
        "SubFooter": ParagraphStyle(
            "SubFooter",
            parent=base["Normal"],
            fontName=normal_face,
            fontSize=8,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#6B7280"),
        ),
        "AcademicNotice": ParagraphStyle(
            "AcademicNotice",
            parent=base["Normal"],
            fontName=normal_face,
            fontSize=6.5,
            leading=10,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#9CA3AF"),
        ),
    }


# ─── Shared Header ────────────────────────────────────────────────────────────

def _create_header_table(
    styles: Dict[str, ParagraphStyle],
    receipt_title: str,
    reference: str,
    status: str = "Successful",
    accent_color: str = "#F59E0B",
) -> list:
    """
    Creates the receipt header section: logo + brand left, receipt type + ref right.
    Returns a list of flowables (not a single table) so spacing is easier to manage.
    """
    logo_bytes = get_optimized_logo_bytes()
    logo_element = None

    if logo_bytes:
        try:
            # Display logo at 52x52 pt — retina quality from 192×192 thumbnail
            logo_element = Image(io.BytesIO(logo_bytes), width=52, height=52)
        except Exception as e:
            logger.warning(f"[ReceiptService] Could not embed logo image: {e}")

    brand_html = 'Tap<font color="#F59E0B"><b>&amp;</b></font>Go'
    if logo_element:
        left_flowables = [
            Table(
                [[logo_element, [
                    Paragraph(brand_html, styles["BrandTitle"]),
                    Spacer(1, 2),
                    Paragraph("Smart Cashless Transit Payments", styles["BrandTagline"]),
                ]]],
                colWidths=[60, 200],
                style=[
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ],
            )
        ]
    else:
        left_flowables = [
            Paragraph(brand_html, styles["BrandTitle"]),
            Spacer(1, 2),
            Paragraph("Smart Cashless Transit Payments", styles["BrandTagline"]),
        ]

    right_flowables = [
        Paragraph(receipt_title.upper(), styles["ReceiptType"]),
        Spacer(1, 4),
        Paragraph(f"Ref: {reference}", styles["ReceiptRef"]),
        Spacer(1, 5),
        Paragraph(f"\u2714 {status.upper()}", styles["StatusBadge"]),
    ]

    header_table = Table(
        [[left_flowables, right_flowables]],
        colWidths=[280, 252],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ],
    )
    return [
        header_table,
        Spacer(1, 10),
        HRFlowable(width="100%", thickness=3, color=colors.HexColor(accent_color), spaceBefore=0, spaceAfter=0),
    ]


# ─── Shared Details Table ─────────────────────────────────────────────────────

def _create_details_table(
    styles: Dict[str, ParagraphStyle],
    rows: list,
) -> Table:
    """
    Creates a clean two-column key-value details table.
    rows: list of (label_str, value_str) tuples.
    """
    table_data = [
        [Paragraph(label, styles["CellLabel"]), Paragraph(value, styles["CellValue"])]
        for label, value in rows
    ]

    return Table(
        table_data,
        colWidths=[165, 367],
        style=[
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F9FAFB")),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#E5E7EB")),
            ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#E5E7EB")),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
        ],
    )


# ─── Amount Highlight Box ─────────────────────────────────────────────────────

def _create_amount_box(
    styles: Dict[str, ParagraphStyle],
    label: str,
    amount_str: str,
    bg_color: str = "#F0FDF4",
    border_color: str = "#10B981",
) -> Table:
    """Creates a prominent highlighted box for the main transaction amount."""
    data = [[
        Paragraph(label, styles["TotalLabel"]),
        Paragraph(amount_str, styles["TotalAmount"]),
    ]]
    return Table(
        data,
        colWidths=[266, 266],
        style=[
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg_color)),
            ("BOX", (0, 0), (-1, -1), 1.5, colors.HexColor(border_color)),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("LEFTPADDING", (0, 0), (-1, -1), 16),
            ("RIGHTPADDING", (0, 0), (-1, -1), 16),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ],
    )


# ─── Footer ───────────────────────────────────────────────────────────────────

def _create_footer_flowables(styles: Dict[str, ParagraphStyle]) -> list:
    """Creates standard receipt footer with thank you message and academic disclosure."""
    return [
        Spacer(1, 16),
        HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#E5E7EB"), spaceBefore=0, spaceAfter=0),
        Spacer(1, 10),
        Paragraph("Thank you for using Tap&Go.", styles["ThankYouText"]),
        Spacer(1, 4),
        Paragraph(
            "Fast \u2022 Secure \u2022 Cashless Transit \u2022 Support: tapandgosupport@gmail.com",
            styles["SubFooter"],
        ),
        Spacer(1, 10),
        HRFlowable(width="100%", thickness=0.25, color=colors.HexColor("#F3F4F6"), spaceBefore=0, spaceAfter=0),
        Spacer(1, 6),
        Paragraph(
            "Tap&Go is a student academic project developed by Moksh Gala, Arham Fofriya, and Vansh Gala "
            "at SVKM\u2019s Shri Bhagubhai Mafatlal Polytechnic.",
            styles["AcademicNotice"],
        ),
    ]


# ─── Ride Payment Receipt ─────────────────────────────────────────────────────

def generate_transaction_receipt(txn_data: Dict[str, Any]) -> Optional[bytes]:
    """
    Generates a professional PDF receipt for a successful passenger-to-driver ride payment.

    Expected txn_data fields:
        reference: str (e.g. 'TXN9E4B2A10C')
        fare: float
        passenger_name: str
        passenger_email: Optional[str]
        driver_name: str
        vehicle_type: Optional[str]
        vehicle_registration: Optional[str]
        payment_method: Optional[str] ('Tap & Go Wallet (QR)' / 'NFC')
        balance_after: Optional[float]
        status: Optional[str] ('Successful' / 'completed')
        created_at: Optional[datetime or str]

    Returns:
        bytes: Generated PDF binary data, or None if generation failed.
    """
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=44,
            rightMargin=44,
            topMargin=40,
            bottomMargin=40,
        )

        styles = _build_styles()
        story = []

        ref              = txn_data.get("reference", "TXN-UNKNOWN")
        status           = txn_data.get("status", "Successful")
        fare             = txn_data.get("fare", 0.0)
        passenger_name   = txn_data.get("passenger_name") or "Passenger"
        driver_name      = txn_data.get("driver_name") or "Driver"
        vehicle_type     = txn_data.get("vehicle_type") or "Auto / Taxi"
        vehicle_reg      = txn_data.get("vehicle_registration") or "Registered Vehicle"
        payment_method   = txn_data.get("payment_method") or "Tap & Go Wallet"
        passenger_email  = txn_data.get("passenger_email") or ""
        created_at_str   = format_datetime(txn_data.get("created_at"))
        balance_after    = txn_data.get("balance_after")

        # 1. Header (logo + brand + reference + status)
        story.extend(_create_header_table(styles, "Ride Payment Receipt", ref, status, accent_color="#F59E0B"))
        story.append(Spacer(1, 16))

        # 2. Transaction Details Table
        detail_rows = [
            ("Transaction Reference", ref),
            ("Date & Time (IST)",      created_at_str),
            ("Payment Status",         "COMPLETED"),
            ("Passenger",              passenger_name),
        ]
        if passenger_email:
            detail_rows.append(("Passenger Email", passenger_email))

        detail_rows.extend([
            ("Driver",          driver_name),
            ("Vehicle Type",    vehicle_type),
            ("Vehicle Number",  vehicle_reg),
            ("Payment Mode",    payment_method),
        ])
        if balance_after is not None:
            detail_rows.append(("Wallet Balance After", format_inr(balance_after)))

        story.append(_create_details_table(styles, detail_rows))
        story.append(Spacer(1, 18))

        # 3. Total Fare Highlight
        story.append(_create_amount_box(
            styles,
            label="Total Ride Fare Paid",
            amount_str=format_inr(fare),
            bg_color="#F0FDF4",
            border_color="#10B981",
        ))

        # 4. Footer & Academic Disclosure
        story.extend(_create_footer_flowables(styles))

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        logger.info(f"[ReceiptService] Ride payment receipt PDF ({len(pdf_bytes)} bytes) generated for {ref}")
        return pdf_bytes
    except Exception as e:
        logger.error(f"[ReceiptService] Exception generating transaction receipt: {e}", exc_info=True)
        return None


# ─── Wallet Top-Up Receipt ────────────────────────────────────────────────────

def generate_wallet_topup_receipt(topup_data: Dict[str, Any]) -> Optional[bytes]:
    """
    Generates a professional PDF acknowledgement for a successful wallet add-money (top-up) transaction.

    Expected topup_data fields:
        reference: str (e.g. 'RZP1A2B3C4D')
        amount: float
        user_name: str
        user_email: Optional[str]
        account_type: Optional[str] ('passenger' / 'driver')
        provider: Optional[str] ('Razorpay')
        payment_method: Optional[str] ('UPI', 'Card', 'Net Banking', 'Wallet')
        razorpay_payment_id: Optional[str] ('pay_...')
        razorpay_order_id: Optional[str] ('order_...')
        balance_after: Optional[float]
        status: Optional[str] ('Successful')
        created_at: Optional[datetime or str]

    Returns:
        bytes: Generated PDF binary data, or None if generation failed.
    """
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=44,
            rightMargin=44,
            topMargin=40,
            bottomMargin=40,
        )

        styles = _build_styles()
        story = []

        ref            = topup_data.get("reference", "RZP-UNKNOWN")
        status         = topup_data.get("status", "Successful")
        amount         = topup_data.get("amount", 0.0)
        user_name      = topup_data.get("user_name") or "User"
        user_email     = topup_data.get("user_email") or ""
        account_type   = (topup_data.get("account_type") or "Passenger").title()
        provider       = topup_data.get("provider") or "Razorpay"
        payment_method = topup_data.get("payment_method") or ""
        rzp_payment_id = topup_data.get("razorpay_payment_id")
        rzp_order_id   = topup_data.get("razorpay_order_id")
        balance_after  = topup_data.get("balance_after")
        created_at_str = format_datetime(topup_data.get("created_at"))

        # 1. Header (logo + brand + reference + status)
        story.extend(_create_header_table(styles, "Wallet Top-Up Receipt", ref, status, accent_color="#10B981"))
        story.append(Spacer(1, 16))

        # 2. Top-Up Details Table
        detail_rows = [
            ("Transaction Reference", ref),
            ("Date & Time (IST)",     created_at_str),
            ("Top-Up Status",         "COMPLETED"),
            ("Account Holder",        user_name),
        ]
        if user_email:
            detail_rows.append(("Registered Email", user_email))

        detail_rows.append(("Account Type", account_type))

        if payment_method:
            detail_rows.append(("Payment Method", payment_method))

        detail_rows.append(("Payment Gateway", provider))

        if rzp_payment_id:
            detail_rows.append(("Gateway Payment ID", str(rzp_payment_id)))
        if rzp_order_id:
            detail_rows.append(("Gateway Order ID",   str(rzp_order_id)))
        if balance_after is not None:
            detail_rows.append(("New Wallet Balance", format_inr(balance_after)))

        story.append(_create_details_table(styles, detail_rows))
        story.append(Spacer(1, 18))

        # 3. Amount Credited Highlight
        story.append(_create_amount_box(
            styles,
            label="Total Amount Credited to Wallet",
            amount_str=format_inr(amount),
            bg_color="#F0FDF4",
            border_color="#10B981",
        ))

        # 4. Footer & Academic Disclosure
        story.extend(_create_footer_flowables(styles))

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        logger.info(f"[ReceiptService] Wallet top-up receipt PDF ({len(pdf_bytes)} bytes) generated for {ref}")
        return pdf_bytes
    except Exception as e:
        logger.error(f"[ReceiptService] Exception generating wallet topup receipt: {e}", exc_info=True)
        return None
