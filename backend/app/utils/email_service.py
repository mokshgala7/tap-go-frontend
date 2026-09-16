import re
import logging
import threading
from datetime import datetime
from typing import Optional

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import boto3
from botocore.exceptions import ClientError, BotoCoreError

from app.config import settings
from app.database import SessionLocal
from app.models import EmailLog

logger = logging.getLogger(__name__)

_last_email_error = threading.local()


def get_last_email_error() -> Optional[str]:
    """Retrieves the last diagnostic error message from the most recent email dispatch."""
    return getattr(_last_email_error, "value", None)


def _set_last_email_error(err: Optional[str]) -> None:
    _last_email_error.value = err


def _sanitize_error_message(err: Optional[str]) -> str:
    """Removes any sensitive tokens or AWS secrets from error logs and diagnostic messages."""
    if not err:
        return ""
    sanitized = str(err)
    if settings.AWS_SECRET_ACCESS_KEY:
        sanitized = sanitized.replace(settings.AWS_SECRET_ACCESS_KEY, "[REDACTED_SECRET]")
    if settings.AWS_ACCESS_KEY_ID:
        sanitized = sanitized.replace(settings.AWS_ACCESS_KEY_ID, "[REDACTED_KEY_ID]")
    if settings.SMTP_PASSWORD:
        sanitized = sanitized.replace(settings.SMTP_PASSWORD, "[REDACTED_PASSWORD]")
    return sanitized


def log_email_delivery(
    email_type: str,
    recipient: str,
    reference: Optional[str] = None,
    status: str = "SENT",
    error_message: Optional[str] = None,
) -> None:
    """Safely log email delivery attempt to database without failing the caller or storing secrets."""
    try:
        clean_error = _sanitize_error_message(error_message) if error_message else None
        with SessionLocal() as db:
            log_entry = EmailLog(
                email_type=email_type,
                recipient=recipient,
                reference=reference,
                status=status,
                error_message=clean_error[:500] if clean_error else None,
            )
            db.add(log_entry)
            db.commit()
    except Exception as e:
        logger.warning(f"[EmailLog] Could not record email log: {e}")


def _get_ses_client():
    """Initializes and returns an Amazon SES client using HTTPS."""
    client_kwargs = {
        "region_name": settings.AWS_REGION or "ap-south-1"
    }
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        client_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        client_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    return boto3.client("ses", **client_kwargs)


def _strip_html(html: str) -> str:
    """Generates clean plain text alternative from HTML for email clients."""
    clean = re.sub(r'<style.*?</style>', '', html, flags=re.DOTALL)
    clean = re.sub(r'<[^<]+?>', '', clean)
    return re.sub(r'\n\s*\n', '\n\n', clean).strip()


def _send_ses_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """
    Sends an HTML email with clean plain-text alternative using Amazon SES via HTTPS (boto3).
    Sole production email-sending mechanism for Tap & Go.
    Configures From, Reply-To, and plain-text body for high deliverability.
    Never raises uncaught exceptions.
    Returns (success: bool, error_message: Optional[str]).
    """
    if not settings.AWS_ACCESS_KEY_ID:
        return False, "AWS_ACCESS_KEY_ID is missing in configuration"
    if not settings.AWS_SECRET_ACCESS_KEY:
        return False, "AWS_SECRET_ACCESS_KEY is missing in configuration"

    sender = settings.SES_FROM_EMAIL or "Tap & Go <support@thetapandgo.in>"
    reply_to = ["Tap & Go Support <support@thetapandgo.in>"]
    plain_text = text_content.strip() if text_content else _strip_html(html_content)

    try:
        client = _get_ses_client()
        response = client.send_email(
            Source=sender,
            Destination={
                "ToAddresses": [to_email],
            },
            ReplyToAddresses=reply_to,
            Message={
                "Subject": {
                    "Data": subject,
                    "Charset": "UTF-8",
                },
                "Body": {
                    "Html": {
                        "Data": html_content,
                        "Charset": "UTF-8",
                    },
                    "Text": {
                        "Data": plain_text,
                        "Charset": "UTF-8",
                    },
                },
            },
        )
        message_id = response.get("MessageId", "unknown")
        logger.info(f"[Email] Successfully delivered email to {to_email} via Amazon SES (MessageId: {message_id})")
        return True, None
    except ClientError as ce:
        err_code = ce.response.get("Error", {}).get("Code", "SESClientError")
        err_msg = ce.response.get("Error", {}).get("Message", str(ce))
        safe_err = _sanitize_error_message(f"SES [{err_code}]: {err_msg}")
        logger.warning(f"[Email] Amazon SES client error sending to {to_email}: {safe_err}")
        return False, safe_err
    except BotoCoreError as be:
        safe_err = _sanitize_error_message(f"SES BotoCoreError: {str(be)}")
        logger.warning(f"[Email] Amazon SES core error sending to {to_email}: {safe_err}")
        return False, safe_err
    except Exception as ex:
        safe_err = _sanitize_error_message(f"SES Unexpected error: {type(ex).__name__} ({str(ex)})")
        logger.error(f"[Email] Exception during Amazon SES delivery to {to_email}: {safe_err}")
        return False, safe_err



def _send_smtp_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """
    Local development fallback SMTP dispatcher.
    Only invoked if AWS SES credentials are not present in the local environment.
    """
    if not settings.SMTP_HOST or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        return False, "Local development SMTP settings incomplete"

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM_EMAIL
        msg["To"] = to_email
        msg["Reply-To"] = "Tap & Go Support <support@thetapandgo.in>"

        plain_text = text_content.strip() if text_content else _strip_html(html_content)
        msg.attach(MIMEText(plain_text, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        clean_pw = settings.SMTP_PASSWORD.strip()
        ports_to_try = [(settings.SMTP_PORT, settings.SMTP_PORT == 465)]
        if settings.SMTP_PORT != 465:
            ports_to_try.append((465, True))

        last_err = None
        for port, is_ssl in ports_to_try:
            try:
                if is_ssl:
                    server = smtplib.SMTP_SSL(settings.SMTP_HOST, port, timeout=10)
                else:
                    server = smtplib.SMTP(settings.SMTP_HOST, port, timeout=10)
                    server.ehlo()
                    server.starttls()
                    server.ehlo()

                with server:
                    server.login(settings.SMTP_USER, clean_pw)
                    server.send_message(msg)
                    logger.info(f"[Email] Local dev fallback email delivered to {to_email} via SMTP:{port}")
                    return True, None
            except Exception as ex:
                last_err = _sanitize_error_message(f"{type(ex).__name__} on port {port}: {ex}")
                logger.warning(f"[Email] Local SMTP attempt on port {port} failed: {last_err}")

        return False, last_err or "Local SMTP delivery failed"
    except Exception as ex:
        safe_err = _sanitize_error_message(f"SMTP prep error: {ex}")
        return False, safe_err


def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    email_type: str = "general",
    reference: Optional[str] = None,
    text_content: Optional[str] = None,
) -> bool:
    """
    Central email delivery dispatcher.
    Uses Amazon SES HTTPS API (boto3) as the primary production delivery mechanism.
    Falls back to local SMTP only if AWS SES credentials are absent in development.
    Records delivery status in email_logs.
    """
    _set_last_email_error(None)
    success = False
    err_msg = None

    # Check environment: In production, Amazon SES is the sole authorized provider.
    if settings.IS_PRODUCTION:
        if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
            err_msg = "Production AWS SES configuration error: AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY is missing. Silent SMTP fallback is disabled in production."
            logger.error(f"[Email] {err_msg}")
            success = False
        else:
            try:
                success, err_msg = _send_ses_email(to_email, subject, html_content, text_content=text_content)
            except Exception as e:
                logger.error(f"[Email] Exception during production Amazon SES delivery to {to_email}: {e}")
                err_msg = _sanitize_error_message(f"{type(e).__name__}: {str(e)}")
                success = False
    else:
        # Local development path:
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            try:
                success, err_msg = _send_ses_email(to_email, subject, html_content, text_content=text_content)
            except Exception as e:
                logger.error(f"[Email] Exception during Amazon SES delivery to {to_email}: {e}")
                err_msg = _sanitize_error_message(f"{type(e).__name__}: {str(e)}")
                success = False
        elif settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD:
            # Local development fallback only
            logger.info(f"[Email] [Local Dev] AWS credentials not detected. Falling back to local dev SMTP for {to_email}")
            try:
                success, err_msg = _send_smtp_email(to_email, subject, html_content, text_content=text_content)
            except Exception as e:
                logger.error(f"[Email] Exception during local development SMTP delivery to {to_email}: {e}")
                err_msg = _sanitize_error_message(f"{type(e).__name__}: {str(e)}")
                success = False
        else:
            err_msg = "No email credentials configured (AWS SES or local dev SMTP)"
            logger.warning(f"[Email] Cannot send email to {to_email}: {err_msg}")
            success = False

    if not success:
        _set_last_email_error(err_msg)

    try:
        log_email_delivery(
            email_type=email_type,
            recipient=to_email,
            reference=reference,
            status="SENT" if success else "FAILED",
            error_message=None if success else (err_msg or "Email delivery failed"),
        )
    except Exception as log_err:
        logger.error(f"[Email] Failed to record delivery log: {log_err}")

    return success



# ─────────────────────────────────────────────────────────────────────────────
# EMAIL TEMPLATE RENDERER (Clean, branded, responsive dark + gold theme)
# ─────────────────────────────────────────────────────────────────────────────

def _render_email_shell(
    badge: str,
    badge_bg: str,
    badge_color: str,
    title: str,
    body_html: str,
    accent_bar_gradient: str = "linear-gradient(90deg,#FDD34D,#F59E0B)",
) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>{title}</title>
<!--[if mso]>
<style>table,td {{font-family:Arial,sans-serif !important;}}</style>
<![endif]-->
</head>
<body style="margin:0;padding:0;background-color:#F4F4F6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;-webkit-font-smoothing:antialiased;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#F4F4F6;">
<tr><td align="center" style="padding:28px 12px;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:500px;width:100%;background-color:#FFFFFF;border-radius:20px;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,0.08);">

<!-- Header -->
<tr>
<td style="background-color:#1C1C1E;padding:30px 24px 24px;text-align:center;">
    <div style="font-size:30px;font-weight:900;color:#FFFFFF;letter-spacing:-0.5px;margin-bottom:6px;">
        Tap<span style="color:#FDD34D;">&amp;</span>Go
    </div>
    <div style="display:inline-block;padding:4px 14px;border-radius:20px;background-color:{badge_bg};font-size:11px;font-weight:800;color:{badge_color};letter-spacing:2px;text-transform:uppercase;">
        {badge}
    </div>
</td>
</tr>

<!-- Accent bar -->
<tr>
<td style="background:{accent_bar_gradient};height:4px;font-size:0;line-height:0;">&nbsp;</td>
</tr>

<!-- Body -->
<tr>
<td style="padding:32px 28px 24px;">
    {body_html}
</td>
</tr>

<!-- Footer -->
<tr>
<td style="background-color:#FAFAFB;border-top:1px solid #ECECF0;padding:22px 28px;text-align:center;">
    <div style="font-size:15px;font-weight:900;color:#1C1C1E;margin-bottom:4px;">
        Tap<span style="color:#F59E0B;">&amp;</span>Go
    </div>
    <div style="font-size:12px;color:#6B7280;font-weight:500;line-height:1.5;">
        Smart Cashless Transit Payments &bull; Fast &bull; Secure
    </div>
    <div style="font-size:11px;color:#9CA3AF;margin-top:8px;">
        Need help? Contact <a href="mailto:tapandgosupport@gmail.com" style="color:#D97706;text-decoration:none;font-weight:600;">tapandgosupport@gmail.com</a>
    </div>
    <div style="font-size:10px;color:#D1D5DB;margin-top:10px;">
        &copy; 2026 Tap&amp;Go Smart Payments. All rights reserved.
    </div>
</td>
</tr>

</table>

</td></tr>
</table>

</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# 1. REGISTRATION OTP EMAIL
# ─────────────────────────────────────────────────────────────────────────────

def send_registration_otp(to_email: str, otp: str, account_type: str = "passenger") -> bool:
    """
    Sends distinct registration verification OTP email.
    Subject: 'Tap & Go - Verify Your Email'
    Expires in 5 minutes.
    """
    role = "Driver" if account_type == "driver" else "Passenger"

    otp_cells = "".join([
        f'''<td align="center" style="padding:0 3px;">
            <div style="width:44px;height:54px;line-height:54px;text-align:center;
            background-color:#1C1C1E;color:#FDD34D;font-size:26px;font-weight:900;
            border-radius:10px;font-family:'Courier New',monospace;">{d}</div>
        </td>'''
        for d in otp
    ])

    body = f"""
    <h2 style="margin:0 0 10px;font-size:22px;font-weight:900;color:#1C1C1E;letter-spacing:-0.3px;">
        Verify Your Email
    </h2>
    <p style="margin:0 0 22px;color:#4B5563;font-size:14px;line-height:1.6;">
        Thank you for registering with Tap &amp; Go as a <strong>{role}</strong>. Please enter the 6-digit verification code below to verify your email address.
    </p>

    <!-- OTP Card -->
    <div style="background-color:#F9FAFB;border:1px solid #E5E7EB;border-radius:14px;padding:22px 14px;text-align:center;margin-bottom:22px;">
        <div style="font-size:11px;font-weight:800;color:#6B7280;letter-spacing:2.5px;text-transform:uppercase;margin-bottom:12px;">
            YOUR VERIFICATION CODE
        </div>
        <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:0 auto;">
            <tr>{otp_cells}</tr>
        </table>
        <div style="font-size:12px;color:#DC2626;font-weight:700;margin-top:14px;">
            ⏰ This code expires in 5 minutes
        </div>
    </div>

    <!-- Security Info -->
    <div style="border-left:4px solid #FDD34D;background-color:#FFFBEB;border-radius:0 10px 10px 0;padding:12px 16px;margin-bottom:14px;">
        <div style="font-size:12px;color:#92400E;font-weight:600;line-height:1.6;">
            🔒 <strong>Security Notice:</strong> Never share this code with anyone. Tap &amp; Go staff will never ask for your verification code.
        </div>
    </div>
    <p style="margin:0;color:#9CA3AF;font-size:12px;line-height:1.5;">
        If you did not request this verification code, you can safely ignore this email.
    </p>
    """

    html = _render_email_shell(
        badge="ACCOUNT REGISTRATION",
        badge_bg="#2E2E32",
        badge_color="#FDD34D",
        title="Verify Your Email",
        body_html=body,
    )
    plain_text = (
        f"Tap & Go Account Verification\n\n"
        f"Hello,\n\n"
        f"Thank you for registering with Tap & Go as a {role}.\n"
        f"Your 6-digit verification code is: {otp}\n\n"
        f"This code expires in 5 minutes.\n\n"
        f"Security Notice: Never share this code with anyone. Tap & Go staff will never ask for your verification code.\n"
        f"If you did not request this verification code, you can safely ignore this email.\n\n"
        f"Tap & Go Smart Cashless Transit Payments\n"
        f"Support: support@thetapandgo.in"
    )
    return send_email(
        to_email=to_email,
        subject="Tap & Go - Verify Your Email",
        html_content=html,
        email_type="registration_otp",
        text_content=plain_text,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. FORGOT PASSWORD OTP EMAIL
# ─────────────────────────────────────────────────────────────────────────────

def send_password_reset_otp(to_email: str, otp: str) -> bool:
    """
    Sends distinct password reset OTP email.
    Subject: 'Tap & Go - Password Reset OTP'
    Expires in 5 minutes.
    """
    otp_cells = "".join([
        f'''<td align="center" style="padding:0 3px;">
            <div style="width:44px;height:54px;line-height:54px;text-align:center;
            background-color:#1C1C1E;color:#F59E0B;font-size:26px;font-weight:900;
            border-radius:10px;font-family:'Courier New',monospace;">{d}</div>
        </td>'''
        for d in otp
    ])

    body = f"""
    <h2 style="margin:0 0 10px;font-size:22px;font-weight:900;color:#1C1C1E;letter-spacing:-0.3px;">
        Reset Your Password
    </h2>
    <p style="margin:0 0 22px;color:#4B5563;font-size:14px;line-height:1.6;">
        We received a request to reset your Tap &amp; Go password. Use the 6-digit verification code below to securely reset your credentials.
    </p>

    <!-- OTP Card -->
    <div style="background-color:#FFFBEB;border:1px solid #FDE68A;border-radius:14px;padding:22px 14px;text-align:center;margin-bottom:22px;">
        <div style="font-size:11px;font-weight:800;color:#B45309;letter-spacing:2.5px;text-transform:uppercase;margin-bottom:12px;">
            PASSWORD RESET CODE
        </div>
        <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:0 auto;">
            <tr>{otp_cells}</tr>
        </table>
        <div style="font-size:12px;color:#DC2626;font-weight:700;margin-top:14px;">
            ⏰ This code expires in 5 minutes
        </div>
    </div>

    <!-- Security Warning -->
    <div style="border-left:4px solid #EF4444;background-color:#FEF2F2;border-radius:0 10px 10px 0;padding:12px 16px;margin-bottom:14px;">
        <div style="font-size:12px;color:#991B1B;font-weight:600;line-height:1.6;">
            ⚠️ <strong>Didn't request this?</strong> If you did not request a password reset, please ignore this email. Your password will not change unless this verification code is entered.
        </div>
    </div>
    <p style="margin:0;color:#9CA3AF;font-size:12px;line-height:1.5;">
        For your security, never share this code with anyone.
    </p>
    """

    html = _render_email_shell(
        badge="SECURITY &bull; PASSWORD RESET",
        badge_bg="#382D1E",
        badge_color="#F59E0B",
        title="Password Reset OTP",
        body_html=body,
        accent_bar_gradient="linear-gradient(90deg,#F59E0B,#DC2626)",
    )
    plain_text = (
        f"Tap & Go Password Reset\n\n"
        f"Hello,\n\n"
        f"We received a request to reset your Tap & Go password.\n"
        f"Your 6-digit verification code is: {otp}\n\n"
        f"This code expires in 5 minutes.\n\n"
        f"Security Warning: If you did not request a password reset, please ignore this email. Never share this code with anyone.\n\n"
        f"Tap & Go Smart Cashless Transit Payments\n"
        f"Support: support@thetapandgo.in"
    )
    return send_email(
        to_email=to_email,
        subject="Tap & Go - Password Reset OTP",
        html_content=html,
        email_type="forgot_password_otp",
        text_content=plain_text,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2b. WITHDRAWAL CONFIRMATION OTP EMAIL
# ─────────────────────────────────────────────────────────────────────────────

def send_withdrawal_otp(to_email: str, otp: str, amount: Optional[float] = None) -> bool:
    """
    Sends distinct withdrawal authorization OTP email.
    Subject: 'Tap & Go - Authorize Withdrawal'
    Expires in 5 minutes.
    """
    otp_cells = "".join([
        f'''<td align="center" style="padding:0 3px;">
            <div style="width:44px;height:54px;line-height:54px;text-align:center;
            background-color:#1C1C1E;color:#6366F1;font-size:26px;font-weight:900;
            border-radius:10px;font-family:'Courier New',monospace;">{d}</div>
        </td>'''
        for d in otp
    ])

    amount_str = f" of <strong>₹{amount:.2f}</strong>" if amount and amount > 0 else ""

    body = f"""
    <h2 style="margin:0 0 10px;font-size:22px;font-weight:900;color:#1C1C1E;letter-spacing:-0.3px;">
        Authorize Withdrawal
    </h2>
    <p style="margin:0 0 22px;color:#4B5563;font-size:14px;line-height:1.6;">
        We received a request to withdraw funds{amount_str} from your Tap &amp; Go wallet to your designated payout account. Use the 6-digit authorization code below to confirm this transaction.
    </p>

    <!-- OTP Card -->
    <div style="background-color:#EEF2FF;border:1px solid #C7D2FE;border-radius:14px;padding:22px 14px;text-align:center;margin-bottom:22px;">
        <div style="font-size:11px;font-weight:800;color:#4338CA;letter-spacing:2.5px;text-transform:uppercase;margin-bottom:12px;">
            WITHDRAWAL AUTHORIZATION CODE
        </div>
        <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:0 auto;">
            <tr>{otp_cells}</tr>
        </table>
        <div style="font-size:12px;color:#DC2626;font-weight:700;margin-top:14px;">
            ⏰ This code expires in 5 minutes
        </div>
    </div>

    <!-- Security Warning -->
    <div style="border-left:4px solid #EF4444;background-color:#FEF2F2;border-radius:0 10px 10px 0;padding:12px 16px;margin-bottom:14px;">
        <div style="font-size:12px;color:#991B1B;font-weight:600;line-height:1.6;">
            ⚠️ <strong>Didn't request this payout?</strong> If you did not initiate this withdrawal, please secure your account immediately and contact Tap &amp; Go Support. Never share this code with anyone.
        </div>
    </div>
    <p style="margin:0;color:#9CA3AF;font-size:12px;line-height:1.5;">
        Tap &amp; Go staff will never ask for your authorization code.
    </p>
    """

    html = _render_email_shell(
        badge="SECURITY &bull; WITHDRAWAL AUTHORIZATION",
        badge_bg="#1E1B4B",
        badge_color="#A5B4FC",
        title="Authorize Withdrawal",
        body_html=body,
        accent_bar_gradient="linear-gradient(90deg,#6366F1,#4F46E5)",
    )
    amount_text = f" of ₹{amount:.2f}" if amount and amount > 0 else ""
    plain_text = (
        f"Tap & Go Withdrawal Authorization\n\n"
        f"Hello,\n\n"
        f"We received a request to withdraw funds{amount_text} from your Tap & Go wallet.\n"
        f"Your 6-digit authorization code is: {otp}\n\n"
        f"This code expires in 5 minutes.\n\n"
        f"Security Warning: If you did not initiate this withdrawal, please secure your account immediately.\n"
        f"Tap & Go staff will never ask for your authorization code.\n\n"
        f"Tap & Go Smart Cashless Transit Payments\n"
        f"Support: support@thetapandgo.in"
    )
    return send_email(
        to_email=to_email,
        subject="Tap & Go - Authorize Withdrawal",
        html_content=html,
        email_type="withdrawal_otp",
        text_content=plain_text,
    )



# ─────────────────────────────────────────────────────────────────────────────
# 3. WALLET TOP-UP EMAIL (Add Money: Initiated / Successful / Failed)
# ─────────────────────────────────────────────────────────────────────────────

def send_wallet_topup_email(
    to_email: str,
    user_name: str,
    amount: float,
    reference: str,
    status: str = "Successful",
    provider: str = "Razorpay",
) -> bool:
    first_name = user_name.split()[0] if user_name else "User"
    is_success = status.lower() in ("successful", "completed", "success")
    is_pending = status.lower() in ("pending", "initiated")

    badge = "ADD MONEY INITIATED" if is_pending else ("PAYMENT SUCCESSFUL" if is_success else "PAYMENT FAILED")
    badge_bg = "#1E293B" if is_pending else ("#064E3B" if is_success else "#7F1D1D")
    badge_color = "#38BDF8" if is_pending else ("#34D399" if is_success else "#F87171")
    headline = "Top-Up Initiated" if is_pending else ("Payment Successful" if is_success else "Payment Failed")
    accent_bar = "linear-gradient(90deg,#10B981,#059669)" if is_success else ("linear-gradient(90deg,#EF4444,#DC2626)" if not is_pending else "linear-gradient(90deg,#38BDF8,#0284C7)")

    formatted_amount = f"₹{amount:.2f}"
    now_str = datetime.utcnow().strftime("%d %B %Y, %I:%M %p UTC")

    body = f"""
    <h2 style="margin:0 0 8px;font-size:22px;font-weight:900;color:#1C1C1E;letter-spacing:-0.3px;">
        {headline}
    </h2>
    <p style="margin:0 0 20px;color:#4B5563;font-size:14px;line-height:1.6;">
        Hi {first_name}, {'your Tap & Go wallet has been credited.' if is_success else ('your wallet top-up request has been initiated.' if is_pending else 'your top-up attempt could not be completed.')}
    </p>

    <!-- Receipt Details Table -->
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#F9FAFB;border:1px solid #E5E7EB;border-radius:14px;margin-bottom:20px;">
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Amount</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:16px;font-weight:900;">{formatted_amount}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Transaction Reference</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:12px;font-family:monospace;font-weight:700;">{reference}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Payment Gateway</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:13px;font-weight:600;">{provider}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Date &amp; Time</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:12px;font-weight:600;">{now_str}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;color:#6B7280;font-size:13px;font-weight:600;">Status</td>
            <td align="right" style="padding:14px 18px;color:{badge_color};font-size:13px;font-weight:800;text-transform:uppercase;">{status}</td>
        </tr>
    </table>
    """

    html = _render_email_shell(
        badge=badge,
        badge_bg=badge_bg,
        badge_color=badge_color,
        title=f"Wallet Top-up {status}",
        body_html=body,
        accent_bar_gradient=accent_bar,
    )
    return send_email(
        to_email=to_email,
        subject=f"Tap & Go - Wallet Top-up {status}",
        html_content=html,
        email_type="wallet_topup",
        reference=reference,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. WITHDRAWAL EMAIL (Initiated / Successful / Failed)
# ─────────────────────────────────────────────────────────────────────────────

def send_withdrawal_email(
    to_email: str,
    user_name: str,
    amount: float,
    reference: str,
    destination: str,
    status: str = "Initiated",
) -> bool:
    first_name = user_name.split()[0] if user_name else "User"
    is_success = status.lower() in ("successful", "completed", "paid")
    is_failed = status.lower() in ("failed", "rejected", "cancelled")

    badge = "WITHDRAWAL COMPLETED" if is_success else ("WITHDRAWAL FAILED" if is_failed else "WITHDRAWAL INITIATED")
    badge_bg = "#064E3B" if is_success else ("#7F1D1D" if is_failed else "#2E2E32")
    badge_color = "#34D399" if is_success else ("#F87171" if is_failed else "#FDD34D")
    accent_bar = "linear-gradient(90deg,#10B981,#059669)" if is_success else ("linear-gradient(90deg,#EF4444,#DC2626)" if is_failed else "linear-gradient(90deg,#FDD34D,#F59E0B)")

    formatted_amount = f"₹{amount:.2f}"
    now_str = datetime.utcnow().strftime("%d %B %Y, %I:%M %p UTC")

    body = f"""
    <h2 style="margin:0 0 8px;font-size:22px;font-weight:900;color:#1C1C1E;letter-spacing:-0.3px;">
        Withdrawal {status.title()}
    </h2>
    <p style="margin:0 0 20px;color:#4B5563;font-size:14px;line-height:1.6;">
        Hi {first_name}, {'your withdrawal payout has been completed.' if is_success else ('your withdrawal request has been received and is being processed.' if not is_failed else 'your withdrawal request could not be completed.')}
    </p>

    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#F9FAFB;border:1px solid #E5E7EB;border-radius:14px;margin-bottom:20px;">
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Payout Amount</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:16px;font-weight:900;">{formatted_amount}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Destination</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:13px;font-weight:700;">{destination}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Reference ID</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:12px;font-family:monospace;font-weight:700;">{reference}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Date &amp; Time</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:12px;font-weight:600;">{now_str}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;color:#6B7280;font-size:13px;font-weight:600;">Status</td>
            <td align="right" style="padding:14px 18px;color:{badge_color};font-size:13px;font-weight:800;text-transform:uppercase;">{status}</td>
        </tr>
    </table>
    """

    html = _render_email_shell(
        badge=badge,
        badge_bg=badge_bg,
        badge_color=badge_color,
        title=f"Withdrawal {status}",
        body_html=body,
        accent_bar_gradient=accent_bar,
    )
    return send_email(
        to_email=to_email,
        subject=f"Tap & Go - Withdrawal Request {status}",
        html_content=html,
        email_type="wallet_withdrawal",
        reference=reference,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. RIDE PAYMENT EMAILS (Passenger payment & Driver payment received)
# ─────────────────────────────────────────────────────────────────────────────

def send_ride_passenger_email(
    to_email: str,
    passenger_name: str,
    fare: float,
    driver_name: str,
    reference: str,
    status: str = "Successful",
) -> bool:
    first_name = passenger_name.split()[0] if passenger_name else "Passenger"
    is_success = status.lower() in ("successful", "completed", "success")
    formatted_fare = f"₹{fare:.2f}"
    now_str = datetime.utcnow().strftime("%d %B %Y, %I:%M %p UTC")

    body = f"""
    <h2 style="margin:0 0 8px;font-size:22px;font-weight:900;color:#1C1C1E;letter-spacing:-0.3px;">
        {'Ride Payment Successful' if is_success else 'Ride Payment Failed'}
    </h2>
    <p style="margin:0 0 20px;color:#4B5563;font-size:14px;line-height:1.6;">
        Hi {first_name}, {'your ride payment has been transferred to your driver.' if is_success else 'your ride payment could not be completed.'}
    </p>

    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#F9FAFB;border:1px solid #E5E7EB;border-radius:14px;margin-bottom:20px;">
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Ride Fare</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:16px;font-weight:900;">{formatted_fare}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Paid To</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:13px;font-weight:700;">{driver_name}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Payment Method</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:13px;font-weight:600;">Tap &amp; Go Wallet (Internal)</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Transaction ID</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:12px;font-family:monospace;font-weight:700;">{reference}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;color:#6B7280;font-size:13px;font-weight:600;">Date &amp; Time</td>
            <td align="right" style="padding:14px 18px;color:#1C1C1E;font-size:12px;font-weight:600;">{now_str}</td>
        </tr>
    </table>
    """

    html = _render_email_shell(
        badge="RIDE PAYMENT" if is_success else "PAYMENT FAILED",
        badge_bg="#064E3B" if is_success else "#7F1D1D",
        badge_color="#34D399" if is_success else "#F87171",
        title="Ride Payment",
        body_html=body,
        accent_bar_gradient="linear-gradient(90deg,#10B981,#059669)" if is_success else "linear-gradient(90deg,#EF4444,#DC2626)",
    )
    return send_email(
        to_email=to_email,
        subject=f"Tap & Go - Ride Payment {status}",
        html_content=html,
        email_type="ride_passenger_payment",
        reference=reference,
    )


def send_ride_driver_email(
    to_email: str,
    driver_name: str,
    fare: float,
    passenger_name: str,
    reference: str,
) -> bool:
    first_name = driver_name.split()[0] if driver_name else "Driver"
    formatted_fare = f"₹{fare:.2f}"
    now_str = datetime.utcnow().strftime("%d %B %Y, %I:%M %p UTC")

    body = f"""
    <h2 style="margin:0 0 8px;font-size:22px;font-weight:900;color:#1C1C1E;letter-spacing:-0.3px;">
        Payment Received
    </h2>
    <p style="margin:0 0 20px;color:#4B5563;font-size:14px;line-height:1.6;">
        Hi {first_name}, you received a ride fare payment credited directly to your Tap &amp; Go driver wallet.
    </p>

    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#F9FAFB;border:1px solid #E5E7EB;border-radius:14px;margin-bottom:20px;">
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Amount Credited</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#10B981;font-size:16px;font-weight:900;">+{formatted_fare}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Passenger</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:13px;font-weight:700;">{passenger_name}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Transaction ID</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:12px;font-family:monospace;font-weight:700;">{reference}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;color:#6B7280;font-size:13px;font-weight:600;">Date &amp; Time</td>
            <td align="right" style="padding:14px 18px;color:#1C1C1E;font-size:12px;font-weight:600;">{now_str}</td>
        </tr>
    </table>
    """

    html = _render_email_shell(
        badge="DRIVER PAYMENT RECEIVED",
        badge_bg="#064E3B",
        badge_color="#34D399",
        title="Payment Received",
        body_html=body,
        accent_bar_gradient="linear-gradient(90deg,#10B981,#059669)",
    )
    return send_email(
        to_email=to_email,
        subject=f"Tap & Go - Payment Received ({formatted_fare})",
        html_content=html,
        email_type="ride_driver_payment",
        reference=reference,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. NFC CARD ORDER EMAILS (Order Placed & Status Updates)
# ─────────────────────────────────────────────────────────────────────────────

def send_nfc_card_order_email(
    to_email: str,
    user_name: str,
    order_reference: str,
    total_amount: float,
    delivery_address: str,
    status: str = "Order Placed",
) -> bool:
    first_name = user_name.split()[0] if user_name else "Customer"
    formatted_amount = f"₹{total_amount:.2f}"
    now_str = datetime.utcnow().strftime("%d %B %Y, %I:%M %p UTC")

    body = f"""
    <h2 style="margin:0 0 8px;font-size:22px;font-weight:900;color:#1C1C1E;letter-spacing:-0.3px;">
        NFC Card Order Placed
    </h2>
    <p style="margin:0 0 20px;color:#4B5563;font-size:14px;line-height:1.6;">
        Hi {first_name}, your Tap &amp; Go contactless NFC Smart Card order has been placed successfully!
    </p>

    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#F9FAFB;border:1px solid #E5E7EB;border-radius:14px;margin-bottom:20px;">
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Order Reference</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:12px;font-family:monospace;font-weight:700;">{order_reference}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Total Amount</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:16px;font-weight:900;">{formatted_amount}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;font-weight:600;">Delivery Address</td>
            <td align="right" style="padding:14px 18px;border-bottom:1px solid #E5E7EB;color:#1C1C1E;font-size:12px;font-weight:600;max-width:200px;">{delivery_address}</td>
        </tr>
        <tr>
            <td style="padding:14px 18px;color:#6B7280;font-size:13px;font-weight:600;">Order Status</td>
            <td align="right" style="padding:14px 18px;color:#F59E0B;font-size:13px;font-weight:800;text-transform:uppercase;">{status}</td>
        </tr>
    </table>
    """

    html = _render_email_shell(
        badge="NFC CARD ORDER",
        badge_bg="#2E2E32",
        badge_color="#FDD34D",
        title="NFC Card Order Placed",
        body_html=body,
    )
    return send_email(
        to_email=to_email,
        subject=f"Tap & Go - NFC Card Order Placed ({order_reference})",
        html_content=html,
        email_type="nfc_card_order",
        reference=order_reference,
    )


def send_nfc_status_update_email(
    to_email: str,
    user_name: str,
    order_reference: str,
    order_status: str,
) -> bool:
    first_name = user_name.split()[0] if user_name else "Customer"
    status_clean = order_status.replace("_", " ").title()

    body = f"""
    <h2 style="margin:0 0 8px;font-size:22px;font-weight:900;color:#1C1C1E;letter-spacing:-0.3px;">
        Order Status Update
    </h2>
    <p style="margin:0 0 20px;color:#4B5563;font-size:14px;line-height:1.6;">
        Hi {first_name}, the status of your Tap &amp; Go NFC Smart Card order has been updated:
    </p>

    <div style="background-color:#F9FAFB;border:1px solid #E5E7EB;border-radius:14px;padding:20px;text-align:center;margin-bottom:20px;">
        <div style="font-size:11px;font-weight:700;color:#6B7280;letter-spacing:1px;text-transform:uppercase;margin-bottom:6px;">
            ORDER REFERENCE: {order_reference}
        </div>
        <div style="font-size:22px;font-weight:900;color:#1C1C1E;margin-bottom:4px;">
            {status_clean}
        </div>
        <div style="font-size:12px;color:#9CA3AF;">
            Updated on {datetime.utcnow().strftime("%d %B %Y, %I:%M %p UTC")}
        </div>
    </div>
    """

    html = _render_email_shell(
        badge=f"NFC ORDER &bull; {status_clean.upper()}",
        badge_bg="#2E2E32",
        badge_color="#FDD34D",
        title="NFC Card Order Update",
        body_html=body,
    )
    return send_email(
        to_email=to_email,
        subject=f"Tap & Go - NFC Card Order {status_clean}",
        html_content=html,
        email_type="nfc_status_update",
        reference=order_reference,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. ACCOUNT SECURITY & WELCOME EMAILS
# ─────────────────────────────────────────────────────────────────────────────

def send_welcome_email(to_email: str, name: str, account_type: str) -> bool:
    role_badge = "PROFESSIONAL DRIVER" if account_type == "driver" else "PASSENGER"
    first_name = name.split()[0] if name else "there"

    body = f"""
    <div style="width:56px;height:56px;border-radius:50%;background-color:#FDD34D;margin:0 auto 16px;line-height:56px;text-align:center;font-size:28px;">
        &#10003;
    </div>
    <h2 style="margin:0 0 10px;font-size:22px;font-weight:900;color:#1C1C1E;text-align:center;">
        Welcome to Tap &amp; Go, {first_name}!
    </h2>
    <p style="margin:0 0 20px;color:#4B5563;font-size:14px;line-height:1.6;text-align:center;">
        Your Tap &amp; Go <strong>{role_badge}</strong> account is now active and ready for fast cashless transit.
    </p>

    <div style="background-color:#F0FDF4;border:1px solid #BBF7D0;border-radius:14px;padding:18px 20px;margin-bottom:20px;">
        <div style="font-size:13px;color:#166534;font-weight:700;line-height:2;">
            &#9989; Email verified<br/>
            &#9989; Digital wallet created<br/>
            &#9989; Account activated
        </div>
    </div>
    """

    html = _render_email_shell(
        badge="ACCOUNT CREATED",
        badge_bg="#064E3B",
        badge_color="#34D399",
        title="Welcome to Tap & Go",
        body_html=body,
    )
    return send_email(
        to_email=to_email,
        subject=f"Welcome to Tap & Go, {first_name}! 🎉",
        html_content=html,
        email_type="welcome",
    )


def send_security_alert_email(
    to_email: str,
    user_name: str,
    title: str,
    details: str,
) -> bool:
    first_name = user_name.split()[0] if user_name else "User"
    now_str = datetime.utcnow().strftime("%d %B %Y, %I:%M %p UTC")

    body = f"""
    <h2 style="margin:0 0 10px;font-size:22px;font-weight:900;color:#1C1C1E;letter-spacing:-0.3px;">
        {title}
    </h2>
    <p style="margin:0 0 16px;color:#4B5563;font-size:14px;line-height:1.6;">
        Hi {first_name}, this is a security confirmation for your Tap &amp; Go account.
    </p>

    <div style="background-color:#F9FAFB;border:1px solid #E5E7EB;border-radius:14px;padding:18px;margin-bottom:18px;">
        <div style="font-size:13px;color:#1C1C1E;font-weight:700;margin-bottom:4px;">
            {title}
        </div>
        <div style="font-size:13px;color:#4B5563;line-height:1.6;">
            {details}
        </div>
        <div style="font-size:11px;color:#9CA3AF;margin-top:10px;">
            Recorded on: {now_str}
        </div>
    </div>

    <div style="border-left:4px solid #EF4444;background-color:#FEF2F2;border-radius:0 10px 10px 0;padding:12px 16px;">
        <div style="font-size:12px;color:#991B1B;font-weight:600;line-height:1.6;">
            🔒 If you did not make this change, please contact Tap &amp; Go security immediately at <a href="mailto:tapandgosupport@gmail.com" style="color:#B91C1C;font-weight:700;">tapandgosupport@gmail.com</a>.
        </div>
    </div>
    """

    html = _render_email_shell(
        badge="SECURITY ALERT",
        badge_bg="#7F1D1D",
        badge_color="#F87171",
        title="Security Alert",
        body_html=body,
        accent_bar_gradient="linear-gradient(90deg,#EF4444,#DC2626)",
    )
    return send_email(
        to_email=to_email,
        subject=f"Tap & Go Security Alert: {title}",
        html_content=html,
        email_type="security_alert",
    )


# Backward-compatibility alias
def send_otp_email(to_email: str, otp: str, account_type: str = "passenger") -> bool:
    return send_registration_otp(to_email, otp, account_type)


# ─────────────────────────────────────────────────────────────────────────────
# NEW EMAIL FUNCTIONS — Support Tickets, NFC, Withdrawal lifecycle
# ─────────────────────────────────────────────────────────────────────────────

def send_topup_otp(to_email: str, otp: str, amount: float) -> bool:
    """Send wallet top-up OTP email before Razorpay checkout."""
    body = f"""
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="padding:0 0 20px;">
        <p style="margin:0;font-size:15px;color:#C8D6E5;line-height:1.7;">
          You requested to add <strong style="color:#FDD34D;">₹{amount:.2f}</strong> to your Tap&amp;Go wallet.
          Use the code below to authorise the transaction. This code is valid for <strong>5 minutes</strong> and is single-use only.
        </p>
      </td></tr>
      <tr><td style="padding:0 0 28px;">
        <div style="background:rgba(253,211,77,0.10);border:2px solid rgba(253,211,77,0.30);border-radius:16px;padding:28px 20px;text-align:center;">
          <span style="font-size:40px;font-weight:900;letter-spacing:18px;color:#FDD34D;font-family:monospace;">{otp}</span>
          <p style="margin:14px 0 0;font-size:13px;color:#8A9BAD;">Top-up OTP · ₹{amount:.2f} · Valid 5 mins</p>
        </div>
      </td></tr>
      <tr><td style="padding:0 0 16px;">
        <p style="margin:0;font-size:13px;color:#8A9BAD;line-height:1.6;">
          If you did not request this top-up, please ignore this email. Do not share this OTP with anyone.
        </p>
      </td></tr>
    </table>
    """
    html = _render_email_shell(
        badge="Wallet Top-up OTP",
        badge_bg="rgba(253,211,77,0.14)",
        badge_color="#FDD34D",
        title="Wallet Top-up Verification Code",
        body_html=body,
    )
    plain_text = (
        f"Tap & Go Wallet Top-up Verification\n\n"
        f"Hello,\n\n"
        f"You requested to add ₹{amount:.2f} to your Tap & Go wallet.\n"
        f"Your 6-digit verification code is: {otp}\n\n"
        f"This code is valid for 5 minutes and is single-use only.\n\n"
        f"Security Warning: If you did not request this top-up, please ignore this email. Never share this code with anyone.\n\n"
        f"Tap & Go Smart Cashless Transit Payments\n"
        f"Support: support@thetapandgo.in"
    )
    return send_email(
        to_email=to_email,
        subject="Tap & Go — Wallet Top-up OTP",
        html_content=html,
        email_type="topup_otp",
        text_content=plain_text,
    )


def send_support_ticket_created(to_email: str, user_name: str, ticket_id: int, subject: str) -> bool:
    """Confirmation email when user creates a support ticket."""
    body = f"""
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="padding:0 0 20px;">
        <p style="margin:0;font-size:15px;color:#C8D6E5;line-height:1.7;">
          Hi <strong style="color:#F1F5F9;">{user_name}</strong>,<br/><br/>
          We've received your support ticket and our team will get back to you shortly.
        </p>
      </td></tr>
      <tr><td style="padding:0 0 24px;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(255,255,255,0.04);border-radius:12px;overflow:hidden;">
          <tr><td style="padding:14px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">
            <span style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8A9BAD;">Ticket ID</span><br/>
            <span style="font-size:15px;font-weight:700;color:#F1F5F9;">#{ticket_id}</span>
          </td></tr>
          <tr><td style="padding:14px 18px;">
            <span style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8A9BAD;">Subject</span><br/>
            <span style="font-size:15px;font-weight:600;color:#F1F5F9;">{subject}</span>
          </td></tr>
        </table>
      </td></tr>
    </table>
    """
    html = _render_email_shell(
        badge="Support Ticket Created",
        badge_bg="rgba(99,102,241,0.14)",
        badge_color="#A5B4FC",
        title="Your Support Ticket Has Been Received",
        body_html=body,
    )
    return send_email(
        to_email=to_email,
        subject=f"Tap & Go — Support Ticket #{ticket_id} Received",
        html_content=html,
        email_type="support_ticket_created",
        reference=str(ticket_id),
    )


def send_support_ticket_reply(to_email: str, user_name: str, ticket_id: int, subject: str, reply: str) -> bool:
    """Notification email when admin replies to a support ticket."""
    body = f"""
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="padding:0 0 20px;">
        <p style="margin:0;font-size:15px;color:#C8D6E5;line-height:1.7;">
          Hi <strong style="color:#F1F5F9;">{user_name}</strong>,<br/><br/>
          Our support team has replied to your ticket <strong>#{ticket_id}</strong>.
        </p>
      </td></tr>
      <tr><td style="padding:0 0 24px;">
        <div style="background:rgba(255,255,255,0.04);border-left:4px solid #A5B4FC;border-radius:0 12px 12px 0;padding:16px 18px;">
          <p style="margin:0 0 8px;font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8A9BAD;">Admin Reply</p>
          <p style="margin:0;font-size:14px;color:#E2E8F0;line-height:1.7;">{reply}</p>
        </div>
      </td></tr>
      <tr><td style="padding:0 0 16px;">
        <p style="margin:0;font-size:13px;color:#8A9BAD;">Subject: {subject}</p>
      </td></tr>
    </table>
    """
    html = _render_email_shell(
        badge="Support Reply",
        badge_bg="rgba(99,102,241,0.14)",
        badge_color="#A5B4FC",
        title="Your Support Ticket Has Been Updated",
        body_html=body,
    )
    return send_email(
        to_email=to_email,
        subject=f"Tap & Go — Reply to Support Ticket #{ticket_id}",
        html_content=html,
        email_type="support_ticket_reply",
        reference=str(ticket_id),
    )


def send_withdrawal_approved_email(to_email: str, user_name: str, amount: float, reference: str) -> bool:
    """Withdrawal request approved email."""
    body = f"""
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="padding:0 0 20px;">
        <p style="margin:0;font-size:15px;color:#C8D6E5;line-height:1.7;">
          Hi <strong style="color:#F1F5F9;">{user_name}</strong>,<br/><br/>
          Your withdrawal request of <strong style="color:#FDD34D;">₹{amount:.2f}</strong> has been <strong style="color:#4ADE80;">approved</strong> and is now being processed for payout.
        </p>
      </td></tr>
      <tr><td style="padding:0 0 24px;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(255,255,255,0.04);border-radius:12px;overflow:hidden;">
          <tr><td style="padding:14px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">
            <span style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8A9BAD;">Reference</span><br/>
            <span style="font-size:14px;font-weight:700;color:#F1F5F9;font-family:monospace;">{reference}</span>
          </td></tr>
          <tr><td style="padding:14px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">
            <span style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8A9BAD;">Amount</span><br/>
            <span style="font-size:20px;font-weight:900;color:#FDD34D;">₹{amount:.2f}</span>
          </td></tr>
          <tr><td style="padding:14px 18px;">
            <span style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8A9BAD;">Status</span><br/>
            <span style="font-size:14px;font-weight:700;color:#4ADE80;">✓ Approved</span>
          </td></tr>
        </table>
      </td></tr>
    </table>
    """
    html = _render_email_shell(
        badge="Withdrawal Approved",
        badge_bg="rgba(74,222,128,0.12)",
        badge_color="#4ADE80",
        title="Withdrawal Request Approved",
        body_html=body,
        accent_bar_gradient="linear-gradient(90deg,#4ADE80,#22C55E)",
    )
    return send_email(
        to_email=to_email,
        subject=f"Tap & Go — Withdrawal Approved ({reference})",
        html_content=html,
        email_type="withdrawal_approved",
        reference=reference,
    )


def send_withdrawal_paid_email(to_email: str, user_name: str, amount: float, reference: str) -> bool:
    """Withdrawal paid/disbursed email."""
    body = f"""
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="padding:0 0 20px;">
        <p style="margin:0;font-size:15px;color:#C8D6E5;line-height:1.7;">
          Hi <strong style="color:#F1F5F9;">{user_name}</strong>,<br/><br/>
          Your withdrawal of <strong style="color:#FDD34D;">₹{amount:.2f}</strong> has been <strong style="color:#4ADE80;">paid out</strong> to your registered bank/UPI destination.
        </p>
      </td></tr>
      <tr><td style="padding:0 0 24px;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(255,255,255,0.04);border-radius:12px;overflow:hidden;">
          <tr><td style="padding:14px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">
            <span style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8A9BAD;">Reference</span><br/>
            <span style="font-size:14px;font-weight:700;color:#F1F5F9;font-family:monospace;">{reference}</span>
          </td></tr>
          <tr><td style="padding:14px 18px;">
            <span style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8A9BAD;">Status</span><br/>
            <span style="font-size:14px;font-weight:700;color:#4ADE80;">✓ Paid Out</span>
          </td></tr>
        </table>
      </td></tr>
      <tr><td><p style="margin:0;font-size:13px;color:#8A9BAD;line-height:1.6;">Please allow 1–3 business days for the funds to reflect in your account.</p></td></tr>
    </table>
    """
    html = _render_email_shell(
        badge="Withdrawal Paid",
        badge_bg="rgba(74,222,128,0.12)",
        badge_color="#4ADE80",
        title="Your Withdrawal Has Been Paid",
        body_html=body,
        accent_bar_gradient="linear-gradient(90deg,#4ADE80,#22C55E)",
    )
    return send_email(
        to_email=to_email,
        subject=f"Tap & Go — Withdrawal Paid ({reference})",
        html_content=html,
        email_type="withdrawal_paid",
        reference=reference,
    )


def send_withdrawal_rejected_email(
    to_email: str, user_name: str, amount: float, reference: str, admin_note: Optional[str] = None
) -> bool:
    """Withdrawal rejection email — informs user balance has been restored."""
    note_block = (
        f'<tr><td style="padding:14px 18px;"><span style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8A9BAD;">Reason</span><br/>'
        f'<span style="font-size:14px;color:#E2E8F0;">{admin_note}</span></td></tr>'
        if admin_note else ""
    )
    body = f"""
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="padding:0 0 20px;">
        <p style="margin:0;font-size:15px;color:#C8D6E5;line-height:1.7;">
          Hi <strong style="color:#F1F5F9;">{user_name}</strong>,<br/><br/>
          Unfortunately, your withdrawal request of <strong style="color:#FDD34D;">₹{amount:.2f}</strong> has been <strong style="color:#F87171;">rejected</strong>.
          The full amount has been <strong style="color:#4ADE80;">restored to your wallet</strong>.
        </p>
      </td></tr>
      <tr><td style="padding:0 0 24px;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(255,255,255,0.04);border-radius:12px;overflow:hidden;">
          <tr><td style="padding:14px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">
            <span style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8A9BAD;">Reference</span><br/>
            <span style="font-size:14px;font-weight:700;color:#F1F5F9;font-family:monospace;">{reference}</span>
          </td></tr>
          <tr><td style="padding:14px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">
            <span style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8A9BAD;">Status</span><br/>
            <span style="font-size:14px;font-weight:700;color:#F87171;">✗ Rejected</span>
          </td></tr>
          {note_block}
        </table>
      </td></tr>
      <tr><td><p style="margin:0;font-size:13px;color:#8A9BAD;line-height:1.6;">Your wallet balance has been restored. If you have questions, please contact support.</p></td></tr>
    </table>
    """
    html = _render_email_shell(
        badge="Withdrawal Rejected",
        badge_bg="rgba(248,113,113,0.12)",
        badge_color="#F87171",
        title="Withdrawal Request Rejected",
        body_html=body,
        accent_bar_gradient="linear-gradient(90deg,#F87171,#EF4444)",
    )
    return send_email(
        to_email=to_email,
        subject=f"Tap & Go — Withdrawal Rejected ({reference})",
        html_content=html,
        email_type="withdrawal_rejected",
        reference=reference,
    )
