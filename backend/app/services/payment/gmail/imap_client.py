import imaplib
import email
from email.header import decode_header
import logging
import traceback
from typing import List, Dict, Any

from app.config import settings

logger = logging.getLogger("gmail_imap")


def decode_header_str(header_val: str) -> str:
    """Decodes MIME encoded email header strings properly into UTF-8 text."""
    if not header_val:
        return ""
    try:
        parts = decode_header(header_val)
        res = ""
        for text, enc in parts:
            if isinstance(text, bytes):
                res += text.decode(enc or "utf-8", errors="ignore")
            else:
                res += str(text)
        return res
    except Exception:
        return str(header_val)


class GmailImapClient:
    """
    Connects directly to Gmail IMAP (imap.gmail.com:993) via SSL using the Gmail account
    credentials configured strictly via environment variables (GMAIL_USER / GMAIL_EMAIL and GMAIL_APP_PASSWORD / SMTP_PASSWORD).

    Fetches payment notification emails sent by FamApp / FamPay (e.g. from no-reply@famapp.in
    or emails with subjects like 'You received ₹100.0 in your FamX account')
    to automatically verify payments and credit passenger wallets.
    """

    def __init__(self):
        self.last_login_success = False
        self.last_inbox_success = False
        self.last_error = None

    @property
    def host(self) -> str:
        return settings.GMAIL_IMAP_SERVER or "imap.gmail.com"

    @property
    def port(self) -> int:
        return settings.GMAIL_IMAP_PORT or 993

    @property
    def user(self) -> str:
        return settings.GMAIL_USER

    @property
    def password(self) -> str:
        return settings.GMAIL_APP_PASSWORD

    def fetch_fampay_emails(self) -> List[Dict[str, Any]]:
        """
        Connects to Gmail IMAP via SSL and retrieves payment notification emails.
        Searches ONLY for emails from 'no-reply@famapp.in' or containing FamApp / FamPay / FamX keywords.
        Uses Gmail-compatible IMAP search query without unsupported nested OR expressions.
        """
        logger.info(f"[Gmail IMAP] Connecting to {self.host}:{self.port} for user={self.user}")
        if not self.user or not self.password:
            err = "[Gmail IMAP Error] Missing Gmail credentials (GMAIL_USER/GMAIL_EMAIL and GMAIL_APP_PASSWORD/SMTP_PASSWORD) in environment variables."
            logger.error(err)
            self.last_error = err
            self.last_login_success = False
            self.last_inbox_success = False
            return []

        messages_list = []
        mail = None
        try:
            logger.info(f"[Gmail IMAP] Connecting via SSL to {self.host}:{self.port}...")
            mail = imaplib.IMAP4_SSL(self.host, self.port)

            logger.info(f"[Gmail IMAP] Logging into Gmail as {self.user}...")
            mail.login(self.user, self.password)
            self.last_login_success = True
            logger.info("[Gmail IMAP] Gmail IMAP login succeeded!")

            logger.info("[Gmail IMAP] Selecting INBOX...")
            select_status, select_data = mail.select("INBOX")
            if select_status == "OK":
                self.last_inbox_success = True
                logger.info("[Gmail IMAP] Gmail INBOX selected successfully.")
            else:
                self.last_inbox_success = False
                logger.error(f"[Gmail IMAP] Failed to select Gmail INBOX: {select_status} {select_data}")
                self.last_error = f"Select INBOX failed: {select_status}"
                mail.logout()
                return []

            # Optimized Gmail IMAP Search: Target ONLY no-reply@famapp.in / FamApp / FamPay / FamX emails
            logger.info("[Gmail IMAP] Executing target search for FamApp / FamPay emails...")
            status, data = mail.search(None, 'X-GM-RAW', '"from:no-reply@famapp.in OR FamApp OR FamPay OR FamX"')

            if status != "OK" or not data or not data[0]:
                logger.info("[Gmail IMAP] X-GM-RAW search yielded 0 results. Fallback to standard FROM search...")
                status, data = mail.search(None, 'FROM', '"no-reply@famapp.in"')

            if status != "OK" or not data or not data[0]:
                logger.info("[Gmail IMAP] No matching FamApp / FamPay payment emails found in INBOX.")
                mail.logout()
                return []

            email_ids = data[0].split()
            logger.info(f"[Gmail IMAP] Search returned {len(email_ids)} matching FamApp/FamPay message ID(s).")

            # Inspect only the recent matching IDs (up to last 20 matching messages)
            recent_ids = email_ids[-20:]
            logger.info(f"[Gmail IMAP] Inspecting the last {len(recent_ids)} matching email ID(s)...")

            for msg_id in reversed(recent_ids):
                try:
                    res, msg_data = mail.fetch(msg_id, "(RFC822)")
                    if res != "OK":
                        continue

                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            subject_header = msg.get("Subject", "")
                            subject = decode_header_str(subject_header)
                            from_addr = decode_header_str(msg.get("From", ""))
                            date_str = msg.get("Date", "")

                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    ctype = part.get_content_type()
                                    if ctype in ["text/plain", "text/html"]:
                                        try:
                                            body += part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
                                        except Exception:
                                            pass
                            else:
                                try:
                                    body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore")
                                except Exception:
                                    pass

                            full_content = f"{subject} {from_addr} {body}".lower()
                            if any(k in full_content for k in ["famapp", "fampay", "famx", "fam", "received", "credited", "upi", "inr", "rs.", "utr", "rrn"]):
                                messages_list.append({
                                    "id": f"GMAIL-IMAP-{msg_id.decode('utf-8', errors='ignore')}",
                                    "subject": subject,
                                    "body": {"content": body},
                                    "receivedDateTime": date_str,
                                })
                except Exception as fetch_ex:
                    logger.warning(f"[Gmail IMAP] Error fetching email ID {msg_id}: {fetch_ex}")

            mail.logout()
            logger.info(f"[Gmail IMAP] Successfully retrieved {len(messages_list)} matching payment notification email(s).")
            self.last_error = None
            return messages_list
        except Exception as e:
            self.last_login_success = False
            self.last_inbox_success = False
            self.last_error = str(e)
            logger.error(f"[Gmail IMAP] Exception occurred during email fetch: {e}")
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass
            return []


gmail_imap_client = GmailImapClient()
