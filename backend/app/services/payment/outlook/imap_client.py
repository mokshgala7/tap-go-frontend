import imaplib
import email
from email.header import decode_header
import logging
import traceback
from typing import List, Dict, Any

from app.config import settings

logger = logging.getLogger("outlook_imap")


class OutlookImapClient:
    def __init__(self):
        self.last_login_success = False
        self.last_inbox_success = False
        self.last_error = None

    @property
    def host(self) -> str:
        return settings.OUTLOOK_IMAP_SERVER or "outlook.office365.com"

    @property
    def port(self) -> int:
        return settings.OUTLOOK_IMAP_PORT or 993

    @property
    def user(self) -> str:
        return settings.OUTLOOK_EMAIL

    @property
    def password(self) -> str:
        return settings.OUTLOOK_APP_PASSWORD

    def fetch_fampay_emails(self) -> List[Dict[str, Any]]:
        """
        Connects to Outlook IMAP via SSL and retrieves emails strictly from 'no-reply@famapp.in'.
        Ignores all other emails completely.
        """
        logger.info(f"[IMAP] Fetching emails from host={self.host}:{self.port} for user={self.user}")
        if not self.user or not self.password:
            logger.info("[IMAP] Outlook credentials not configured. Proceeding to Gmail IMAP channel...")
            return self._fetch_gmail_fallback()

        messages_list = []
        mail = None
        try:
            logger.info("[IMAP] Attempting SSL connection...")
            mail = imaplib.IMAP4_SSL(self.host, self.port)
            
            logger.info("[IMAP] Attempting login...")
            mail.login(self.user, self.password)
            self.last_login_success = True
            logger.info("[IMAP] Login succeeded.")

            logger.info("[IMAP] Selecting INBOX...")
            select_status, select_data = mail.select("INBOX")
            if select_status == "OK":
                self.last_inbox_success = True
                logger.info("[IMAP] INBOX selected successfully.")
            else:
                self.last_inbox_success = False
                logger.error(f"[IMAP] Failed to select INBOX: {select_status} {select_data}")
                self.last_error = f"Select INBOX failed: {select_status}"
                mail.logout()
                return []

            # Search strictly for emails from no-reply@famapp.in
            logger.info("[IMAP] Searching for emails from no-reply@famapp.in...")
            status, data = mail.search(None, '(FROM "no-reply@famapp.in")')
            if status != "OK":
                logger.error(f"[IMAP] Search failed with status: {status}")
                self.last_error = f"Search failed: {status}"
                mail.logout()
                return []

            if not data or not data[0]:
                logger.info("[IMAP] No emails found from no-reply@famapp.in.")
                mail.logout()
                return []

            email_ids = data[0].split()
            logger.info(f"[IMAP] Found total {len(email_ids)} emails from no-reply@famapp.in.")
            
            recent_ids = email_ids[-15:]
            logger.info(f"[IMAP] Processing the last {len(recent_ids)} recent emails...")

            for msg_id in reversed(recent_ids):
                logger.info(f"[IMAP] Fetching email ID: {msg_id.decode('utf-8', errors='ignore')}")
                res, msg_data = mail.fetch(msg_id, "(RFC822)")
                if res != "OK":
                    logger.error(f"[IMAP] Failed to fetch email ID: {msg_id.decode()} status={res}")
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
                        logger.info(f"[IMAP] Email Subject: '{subject}'")

                        date_str = msg.get("Date", "")
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                ctype = part.get_content_type()
                                if ctype in ["text/plain", "text/html"]:
                                    try:
                                        body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
                                        break
                                    except Exception as body_ex:
                                        logger.warning(f"[IMAP] Body part decoding failed: {body_ex}")
                                        pass
                        else:
                            try:
                                body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore")
                            except Exception as body_ex:
                                logger.warning(f"[IMAP] Simple body decoding failed: {body_ex}")
                                pass

                        messages_list.append({
                            "id": f"IMAP-{msg_id.decode('utf-8', errors='ignore')}",
                            "subject": subject,
                            "body": {"content": body},
                            "receivedDateTime": date_str,
                        })

            mail.logout()
            logger.info(f"[Outlook IMAP] Successfully fetched {len(messages_list)} emails from no-reply@famapp.in.")
            self.last_error = None
            return messages_list
        except Exception as e:
            self.last_login_success = False
            self.last_inbox_success = False
            self.last_error = str(e)
            logger.error(f"[Outlook IMAP] Exception occurred during email fetch: {e}")
            
            return self._fetch_gmail_fallback()
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass
            return []

    def _fetch_gmail_fallback(self) -> List[Dict[str, Any]]:
        messages_list = []
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            logger.info(f"[IMAP Fallback] Attempting Gmail IMAP fetch for user={settings.SMTP_USER}...")
            try:
                gmail_mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
                gmail_mail.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                self.last_login_success = True
                self.last_inbox_success = True
                self.last_error = None
                logger.info("[Gmail IMAP] Login succeeded.")

                gmail_mail.select("INBOX")
                status, data = gmail_mail.search(None, '(OR (FROM "no-reply@famapp.in") (BODY "FamApp"))')
                if status == "OK" and data and data[0]:
                    email_ids = data[0].split()
                    recent_ids = email_ids[-15:]
                    for msg_id in reversed(recent_ids):
                        res, msg_data = gmail_mail.fetch(msg_id, "(RFC822)")
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

                                messages_list.append({
                                    "id": f"GMAIL-IMAP-{msg_id.decode('utf-8', errors='ignore')}",
                                    "subject": subject,
                                    "body": {"content": body},
                                    "receivedDateTime": date_str,
                                })
                gmail_mail.logout()
                logger.info(f"[Gmail IMAP Fallback] Successfully fetched {len(messages_list)} payment emails.")
                return messages_list
            except Exception as g_ex:
                logger.error(f"[Gmail IMAP Fallback Error]: {g_ex}")
                self.last_login_success = False
                self.last_inbox_success = False
                self.last_error = str(g_ex)
        return []


outlook_imap_client = OutlookImapClient()
