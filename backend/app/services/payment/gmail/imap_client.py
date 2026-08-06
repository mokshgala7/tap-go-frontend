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
    Connects directly to Gmail IMAP (imap.gmail.com:993) via SSL using credentials
    configured strictly via environment variables (GMAIL_USER / GMAIL_EMAIL and GMAIL_APP_PASSWORD / SMTP_PASSWORD).

    Fetches payment notification emails sent by FamApp (no-reply@famapp.in), including
    auto-forwarded emails received via Outlook/Hotmail.
    """

    def __init__(self):
        self.last_login_success = False
        self.last_inbox_success = False
        self.last_error = None
        self.total_emails_found = 0
        self.last_fetched_count = 0

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
        Retrieves recent emails to inspect both direct and Outlook-forwarded FamApp payment emails.
        """
        logger.info(f"[Gmail IMAP] Account used: '{self.user}'")
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

            logger.info(f"[Gmail IMAP] Logging into Gmail as '{self.user}'...")
            try:
                mail.login(self.user, self.password)
                self.last_login_success = True
                logger.info(f"[Gmail IMAP] Login status: SUCCESS for user='{self.user}'")
            except Exception as login_err:
                self.last_login_success = False
                self.last_error = f"Login failed: {str(login_err)}"
                logger.error(f"[Gmail IMAP] Login status: FAILURE for user='{self.user}': {login_err}")
                raise login_err

            logger.info("[Gmail IMAP] Selecting INBOX...")
            select_status, select_data = mail.select("INBOX")
            if select_status == "OK":
                self.last_inbox_success = True
                logger.info(f"[Gmail IMAP] Mailbox selected: INBOX (status={select_status})")
            else:
                self.last_inbox_success = False
                logger.error(f"[Gmail IMAP] Failed to select Gmail INBOX: status={select_status}, data={select_data}")
                self.last_error = f"Select INBOX failed: {select_status}"
                mail.logout()
                return []

            # Retrieve recent message IDs to inspect both direct and Outlook-forwarded FamApp emails
            logger.info("[Gmail IMAP] Searching INBOX for messages (Search command: ALL)...")
            status, data = mail.search(None, "ALL")
            logger.info(f"[Gmail IMAP] Search status: {status}")

            if status != "OK" or not data or not data[0]:
                self.total_emails_found = 0
                self.last_fetched_count = 0
                logger.info("[Gmail IMAP] Total emails in INBOX: 0")
                mail.logout()
                return []

            email_ids = data[0].split()
            self.total_emails_found = len(email_ids)
            logger.info(f"[Gmail IMAP] Total emails in INBOX: {self.total_emails_found}")

            # Inspect matching IDs (up to last 30 recent messages)
            recent_ids = email_ids[-30:]
            self.last_fetched_count = len(recent_ids)
            logger.info(f"[Gmail IMAP] Number of emails fetched/inspected: {self.last_fetched_count}")

            for msg_id in reversed(recent_ids):
                uid_str = msg_id.decode('utf-8', errors='ignore')
                try:
                    res, msg_data = mail.fetch(msg_id, "(RFC822)")
                    if res != "OK":
                        logger.warning(f"[Gmail IMAP] Fetch status for UID {uid_str}: {res}")
                        continue

                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            subject_header = msg.get("Subject", "")
                            subject = decode_header_str(subject_header)
                            from_addr = decode_header_str(msg.get("From", ""))
                            date_str = msg.get("Date", "")

                            logger.info(
                                f"[Gmail IMAP Email] IMAP UID: {uid_str} | "
                                f"From: '{from_addr}' | "
                                f"Subject: '{subject}' | "
                                f"Date: '{date_str}'"
                            )

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

                            messages_list.append({
                                "id": f"GMAIL-IMAP-{uid_str}",
                                "imap_uid": uid_str,
                                "from": from_addr,
                                "subject": subject,
                                "body": {"content": body},
                                "receivedDateTime": date_str,
                            })
                except Exception as fetch_ex:
                    logger.warning(f"[Gmail IMAP] Error fetching email UID {uid_str}: {fetch_ex}")

            mail.logout()
            logger.info(f"[Gmail IMAP] Successfully fetched {len(messages_list)} email(s) for verification inspection.")
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
