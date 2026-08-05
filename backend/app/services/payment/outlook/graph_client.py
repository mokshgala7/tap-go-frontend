import json
import logging
import time
import urllib.parse
import urllib.request
from typing import List, Dict, Any, Optional

from app.config import settings

logger = logging.getLogger("outlook_graph")

class OutlookGraphClient:
    def __init__(self):
        self.client_id = settings.OUTLOOK_CLIENT_ID
        self.client_secret = settings.OUTLOOK_CLIENT_SECRET
        self.tenant_id = settings.OUTLOOK_TENANT_ID or "common"
        self.refresh_token = settings.OUTLOOK_REFRESH_TOKEN
        self.email = settings.OUTLOOK_EMAIL
        self._access_token = None
        self._token_expires_at = 0

    def get_access_token(self) -> Optional[str]:
        if not self.client_id or not self.refresh_token:
            logger.warning("[Outlook] Microsoft Graph API credentials not configured in .env.")
            return None

        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        payload = urllib.parse.urlencode({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
            "scope": "https://graph.microsoft.com/Mail.Read offline_access",
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    self._access_token = data.get("access_token")
                    expires_in = data.get("expires_in", 3600)
                    self._token_expires_at = time.time() + expires_in
                    return self._access_token
        except Exception as e:
            logger.error(f"[Outlook] Failed to refresh Graph token: {e}")
            return None

    def fetch_fampay_emails(self) -> List[Dict[str, Any]]:
        """
        Connects to Microsoft Graph API and fetches inbox emails ONLY from 'no-reply@famapp.in'.
        Never touches personal emails or OTP emails.
        """
        token = self.get_access_token()
        if not token:
            logger.info("[Outlook] Graph API token unavailable. Operating in standby mode.")
            return []

        base_url = f"https://graph.microsoft.com/v1.0/users/{self.email}/messages" if self.email else "https://graph.microsoft.com/v1.0/me/messages"
        query = urllib.parse.urlencode({
            "$filter": "from/emailAddress/address eq 'no-reply@famapp.in'",
            "$top": "20",
            "$select": "id,subject,body,receivedDateTime,from",
            "$orderby": "receivedDateTime desc",
        })
        endpoint = f"{base_url}?{query}"

        req = urllib.request.Request(
            endpoint,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    messages = data.get("value", [])
                    logger.info(f"[Outlook] Successfully retrieved {len(messages)} payment emails from no-reply@famapp.in.")
                    return messages
        except Exception as e:
            logger.error(f"[Outlook] Graph API request failed: {e}")
            return []

outlook_client = OutlookGraphClient()
