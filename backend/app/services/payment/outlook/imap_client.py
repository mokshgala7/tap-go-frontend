import imaplib
import email
from email.header import decode_header
import logging
import traceback
from typing import List, Dict, Any

from app.config import settings

logger = logging.getLogger("gmail_imap")


class GmailImapClient:
    """
    Connects to Gmail IMAP (imap.gmail.com:993) via SSL and fetches FamPay/FamApp
    payment notification emails (including emails forwarded from Outlook to Gmail).
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
        return settings.GMAIL_USER or "mokshgala070@gmail.com"

    @property
    def password(self) -> str:
        return settings.GMAIL_APP_PASSWORD or settings.SMTP_PASSWORD or ""

    def fetch_fampay_emails(self) -> List[Dict[str, Any]]:
        """
        Connects to Gmail IMAP via SSL and retrieves payment notification emails.
        Searches for emails from 'no-reply@famapp.in' or forwarded FamPay emails in Gmail.
        """
        logger.info(f"[Gmail IMAP] Connecting to {self.host}:{self.port} for user={self.user}")
        if not self.user or not self.password:
            logger.info("[Gmail IMAP] Gmail credentials not configured in environment variables.")
            return []

        messages_list = []
        mail = None
        try:
            logger.info(f"[Gmail IMAP] Connecting via SSL to {self.host}:{self.port}...")
            mail = imaplib.IMAP4_SSL(self.host, self.port)

            logger.info(f"[Gmail IMAP] Logging in as {self.user}...")
            mail.login(self.user, self.password)
            self.last_login_success = True
            logger.info("[Gmail IMAP] Login succeeded.")

            logger.info("[Gmail IMAP] Selecting INBOX...")
            select_status, select_data = mail.select("INBOX")
            if select_status == "OK":
                self.last_inbox_success = True
                logger.info("[Gmail IMAP] INBOX selected successfully.")
            else:
                self.last_inbox_success = False
                logger.error(f"[Gmail IMAP] Failed to select INBOX: {select_status} {select_data}")
                self.last_error = f"Select INBOX failed: {select_status}"
                mail.logout()
                return []

            # Search for emails from no-reply@famapp.in OR emails mentioning FamApp/FamPay (forwarded from Outlook)
            logger.info("[Gmail IMAP] Searching for FamPay / FamApp payment emails in Gmail INBOX...")
            status, data = mail.search(None, '(OR (FROM "no-reply@famapp.in") (OR (SUBJECT "FamApp") (OR (SUBJECT "FamPay") (BODY "FamApp"))))')

            if status != "OK" or not data or not data[0]:
                logger.info("[Gmail IMAP] Fallback search for all recent messages...")
                status, data = mail.search(None, "ALL")

            if status != "OK" or not data or not data[0]:
                logger.info("[Gmail IMAP] No matching payment emails found in Gmail INBOX.")
                mail.logout()
                return []

            email_ids = data[0].split()
            logger.info(f"[Gmail IMAP] Found {len(email_ids)} matching messages in Gmail INBOX.")

            recent_ids = email_ids[-20:]
            logger.info(f"[Gmail IMAP] Processing the last {len(recent_ids)} recent emails...")

            for msg_id in reversed(recent_ids):
                try:
                    res, msg_data = mail.fetch(msg_id, "(RFC822)")
                    if res != "OK":
                        continue

                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            subject_header = msg.get("Subject", "")
                            subject = ""
                            if subject_header:
                                dh = decode_header(subject_header)
                                subject = "".join(
                                    str(t[0], t[1] or "utf-8") if isinstance(t[0], bytes) else str(t[0])
                                    for t in dh
                                )

                            date_str = msg.get("Date", "")
                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    ctype = part.get_content_type()
                                    if ctype in ["text/plain", "text/html"]:
                                        try:
                                            body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
                                            break
                                        except Exception:
                                            pass
                            else:
                                try:
                                    body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore")
                                except Exception:
                                    pass

                            # Include if it contains FamApp / FamPay / UPI payment info
                            if any(k in f"{subject} {body}".lower() for k in ["famapp", "fampay", "received", "credited", "upi", "inr", "rs."]):
                                messages_list.append({
                                    "id": f"GMAIL-IMAP-{msg_id.decode('utf-8', errors='ignore')}",
                                    "subject": subject,
                                    "body": {"content": body},
                                    "receivedDateTime": date_str,
                                })
                except Exception as fetch_ex:
                    logger.warning(f"[Gmail IMAP] Error fetching email ID {msg_id}: {fetch_ex}")

            mail.logout()
            logger.info(f"[Gmail IMAP] Successfully parsed {len(messages_list)} payment notification emails from Gmail.")
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


outlook_imap_client = GmailImapClient()
