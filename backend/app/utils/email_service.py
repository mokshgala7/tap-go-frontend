import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.config import settings
import logging

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """
    Sends an HTML email using the configured SMTP settings.
    Returns True on success, False on failure.
    """
    if not settings.SMTP_HOST or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning(
            f"SMTP settings not fully configured. Simulating email to {to_email}. Subject: {subject}"
        )
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM_EMAIL
        msg["To"] = to_email

        part = MIMEText(html_content, "html", "utf-8")
        msg.attach(part)

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD.strip())
            server.send_message(msg)

        logger.info(f"Email sent successfully to {to_email}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP Authentication failed for {settings.SMTP_USER}: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def send_otp_email(to_email: str, otp: str, account_type: str) -> bool:
    """
    Sends a beautifully designed OTP verification email.
    Mobile-responsive, matching the Tap&Go dark + gold theme.
    """
    role = account_type.capitalize()
    role_badge = "PROFESSIONAL DRIVER" if account_type == "driver" else "PASSENGER"

    # Build OTP digits as a single-row table for perfect alignment on mobile
    otp_cells = ""
    for i, d in enumerate(otp):
        margin = "margin-right:6px;" if i < len(otp) - 1 else ""
        otp_cells += f'''<td align="center" style="padding:0 3px;">
            <div style="width:44px;height:56px;line-height:56px;text-align:center;
            background-color:#1C1C1E;color:#FDD34D;font-size:26px;font-weight:900;
            border-radius:10px;font-family:'Courier New',monospace;
            {margin}">{d}</div>
        </td>'''

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Tap&amp;Go Verification</title>
<!--[if mso]>
<style>table,td {{font-family:Arial,sans-serif !important;}}</style>
<![endif]-->
</head>
<body style="margin:0;padding:0;background-color:#F5F5F5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;-webkit-font-smoothing:antialiased;">

<!-- Wrapper -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#F5F5F5;">
<tr><td align="center" style="padding:24px 12px;">

<!-- Main card -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;background-color:#FFFFFF;border-radius:20px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,0.08);">

<!-- Header: dark with gold accent -->
<tr>
<td style="background-color:#1C1C1E;padding:32px 28px 28px;text-align:center;">
    <!-- Logo text -->
    <div style="font-size:28px;font-weight:900;color:#FFFFFF;letter-spacing:-1px;margin-bottom:4px;">
        Tap<span style="color:#FDD34D;">&amp;</span>Go
    </div>
    <div style="font-size:10px;font-weight:800;color:#FDD34D;letter-spacing:3px;text-transform:uppercase;">
        {role_badge}
    </div>
</td>
</tr>

<!-- Gold accent bar -->
<tr>
<td style="background:linear-gradient(90deg,#FDD34D,#F59E0B);height:4px;font-size:0;line-height:0;">&nbsp;</td>
</tr>

<!-- Body -->
<tr>
<td style="padding:32px 28px 24px;">
    <h2 style="margin:0 0 10px;font-size:22px;font-weight:900;color:#1C1C1E;letter-spacing:-0.3px;">
        Verify Your Email
    </h2>
    <p style="margin:0 0 24px;color:#6B7280;font-size:14px;line-height:1.65;">
        Enter the 6-digit code below to verify your <strong style="color:#1C1C1E;">{role}</strong> account. This code expires in <strong>10 minutes</strong>.
    </p>

    <!-- OTP container -->
    <div style="background-color:#F9FAFB;border:1px solid #E5E7EB;border-radius:16px;padding:24px 12px;text-align:center;margin-bottom:24px;">
        <div style="font-size:10px;font-weight:800;color:#9CA3AF;letter-spacing:3px;text-transform:uppercase;margin-bottom:14px;">
            YOUR VERIFICATION CODE
        </div>
        <!-- OTP digits table for pixel-perfect alignment -->
        <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:0 auto;">
            <tr>
                {otp_cells}
            </tr>
        </table>
        <div style="font-size:11px;color:#9CA3AF;font-weight:600;margin-top:14px;">
            Valid for 10 minutes &bull; Do not share
        </div>
    </div>

    <!-- Security alert -->
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>
        <td style="border-left:3px solid #FDD34D;background-color:#FFFBEB;border-radius:0 10px 10px 0;padding:14px 16px;">
            <div style="font-size:12px;color:#92400E;font-weight:600;line-height:1.6;">
                &#128274; <strong>Security:</strong> Tap&amp;Go will never ask for this code via phone or chat. If you didn't request this, ignore this email.
            </div>
        </td>
    </tr>
    </table>
</td>
</tr>

<!-- Footer -->
<tr>
<td style="background-color:#FAFAFA;border-top:1px solid #F3F4F6;padding:20px 28px;text-align:center;">
    <div style="font-size:16px;font-weight:900;color:#1C1C1E;letter-spacing:-0.3px;margin-bottom:4px;">
        Tap<span style="color:#F59E0B;">&amp;</span>Go
    </div>
    <div style="font-size:11px;color:#9CA3AF;font-weight:500;">
        Smart Transit Payments &bull; Secure &amp; Cashless
    </div>
    <div style="font-size:10px;color:#D1D5DB;margin-top:8px;">
        &copy; 2026 Tap&amp;Go Smart Payments. All rights reserved.
    </div>
</td>
</tr>

</table>
<!-- End main card -->

</td></tr>
</table>
<!-- End wrapper -->

</body>
</html>"""

    subject = f"[Tap&Go] Your verification code is {otp}"
    return send_email(to_email, subject, html_content)


def send_welcome_email(to_email: str, name: str, account_type: str) -> bool:
    """
    Sends a welcome email after successful account creation.
    Mobile-responsive, matching the Tap&Go website theme.
    """
    role_badge = "PROFESSIONAL DRIVER" if account_type == "driver" else "PASSENGER"
    first_name = name.split()[0] if name else "there"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Welcome to Tap&amp;Go</title>
</head>
<body style="margin:0;padding:0;background-color:#F5F5F5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;-webkit-font-smoothing:antialiased;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#F5F5F5;">
<tr><td align="center" style="padding:24px 12px;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;background-color:#FFFFFF;border-radius:20px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,0.08);">

<!-- Header -->
<tr>
<td style="background-color:#1C1C1E;padding:36px 28px;text-align:center;">
    <!-- Checkmark circle -->
    <div style="width:56px;height:56px;border-radius:50%;background-color:#FDD34D;margin:0 auto 16px;line-height:56px;text-align:center;font-size:28px;">
        &#10003;
    </div>
    <div style="font-size:24px;font-weight:900;color:#FFFFFF;letter-spacing:-0.5px;margin-bottom:4px;">
        Welcome, {first_name}!
    </div>
    <div style="font-size:10px;font-weight:800;color:#FDD34D;letter-spacing:3px;text-transform:uppercase;">
        ACCOUNT CREATED
    </div>
</td>
</tr>

<!-- Gold bar -->
<tr>
<td style="background:linear-gradient(90deg,#FDD34D,#F59E0B);height:4px;font-size:0;line-height:0;">&nbsp;</td>
</tr>

<!-- Body -->
<tr>
<td style="padding:32px 28px;">
    <p style="margin:0 0 20px;color:#374151;font-size:14px;line-height:1.7;">
        Your Tap&amp;Go <strong>{role_badge}</strong> account is now active! You can log in and start using the platform immediately.
    </p>

    <!-- Status checklist -->
    <div style="background-color:#F0FDF4;border:1px solid #BBF7D0;border-radius:14px;padding:20px;margin-bottom:24px;">
        <div style="font-size:13px;color:#166534;font-weight:700;line-height:2;">
            &#9989; Email verified<br/>
            &#9989; Identity submitted<br/>
            &#9989; Digital signature captured<br/>
            &#9989; Account activated
        </div>
    </div>

    <p style="margin:0;color:#6B7280;font-size:13px;line-height:1.6;">
        Questions? Reply to this email or contact us at support@tapandgo.app
    </p>
</td>
</tr>

<!-- Footer -->
<tr>
<td style="background-color:#FAFAFA;border-top:1px solid #F3F4F6;padding:20px 28px;text-align:center;">
    <div style="font-size:16px;font-weight:900;color:#1C1C1E;letter-spacing:-0.3px;margin-bottom:4px;">
        Tap<span style="color:#F59E0B;">&amp;</span>Go
    </div>
    <div style="font-size:11px;color:#9CA3AF;font-weight:500;">
        Smart Transit Payments
    </div>
    <div style="font-size:10px;color:#D1D5DB;margin-top:8px;">
        &copy; 2026 Tap&amp;Go Smart Payments. All rights reserved.
    </div>
</td>
</tr>

</table>

</td></tr>
</table>

</body>
</html>"""

    subject = f"Welcome to Tap&Go, {first_name}! 🎉"
    return send_email(to_email, subject, html_content)
