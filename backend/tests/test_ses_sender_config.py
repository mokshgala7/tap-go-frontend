"""Sender, Reply-To and region configuration for Amazon SES.

No network and no AWS: boto3's client is replaced by a recorder. These tests prove how the code
reads its configuration (they say nothing about what production's environment contains).
"""
from unittest.mock import MagicMock, patch

import pytest

import app.utils.email_service as email_service
from app.config import DEFAULT_SES_FROM, settings

ENV_KEYS = ("SES_FROM_EMAIL", "AWS_SES_FROM_EMAIL", "SES_REPLY_TO_EMAIL", "AWS_REGION")


@pytest.fixture
def clean_env(monkeypatch):
    """Start every test with none of the sender/region variables set."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


class TestSenderResolution:
    def test_default_is_the_verified_domain_never_a_personal_mailbox(self, clean_env):
        assert DEFAULT_SES_FROM == "Tap & Go <noreply@thetapandgo.in>"
        assert settings.SES_FROM_EMAIL == "Tap & Go <noreply@thetapandgo.in>"
        assert settings.SES_SENDER_EMAIL == "noreply@thetapandgo.in"
        assert "gmail" not in settings.SES_FROM_EMAIL.lower()

    def test_intended_production_value_is_used_unchanged(self, clean_env):
        clean_env.setenv("SES_FROM_EMAIL", "Tap & Go <noreply@thetapandgo.in>")
        assert settings.SES_FROM_EMAIL == "Tap & Go <noreply@thetapandgo.in>"
        assert settings.SES_SENDER_EMAIL == "noreply@thetapandgo.in"

    def test_a_bare_address_is_wrapped_with_the_display_name(self, clean_env):
        clean_env.setenv("SES_FROM_EMAIL", "noreply@thetapandgo.in")
        assert settings.SES_FROM_EMAIL == "Tap & Go <noreply@thetapandgo.in>"
        assert settings.SES_SENDER_EMAIL == "noreply@thetapandgo.in"

    def test_whitespace_around_the_value_is_ignored(self, clean_env):
        clean_env.setenv("SES_FROM_EMAIL", "  Tap & Go <noreply@thetapandgo.in>  ")
        assert settings.SES_FROM_EMAIL == "Tap & Go <noreply@thetapandgo.in>"

    def test_the_old_alias_works_and_the_primary_variable_wins(self, clean_env):
        clean_env.setenv("AWS_SES_FROM_EMAIL", "alias@thetapandgo.in")
        assert settings.SES_SENDER_EMAIL == "alias@thetapandgo.in"
        clean_env.setenv("SES_FROM_EMAIL", "primary@thetapandgo.in")
        assert settings.SES_SENDER_EMAIL == "primary@thetapandgo.in"

    def test_an_empty_value_falls_back_to_the_default(self, clean_env):
        clean_env.setenv("SES_FROM_EMAIL", "   ")
        assert settings.SES_SENDER_EMAIL == "noreply@thetapandgo.in"


class TestReplyToAndRegion:
    def test_reply_to_is_optional(self, clean_env):
        assert settings.SES_REPLY_TO_EMAIL is None
        clean_env.setenv("SES_REPLY_TO_EMAIL", " tapandgosupport@gmail.com ")
        assert settings.SES_REPLY_TO_EMAIL == "tapandgosupport@gmail.com"

    def test_region_defaults_to_mumbai_and_is_read_from_aws_region_only(self, clean_env):
        assert settings.AWS_REGION == "ap-south-1"
        clean_env.setenv("SES_REGION", "us-east-1")          # there is no such variable: ignored
        assert settings.AWS_REGION == "ap-south-1"
        clean_env.setenv("AWS_REGION", "ap-south-1")
        assert settings.AWS_REGION == "ap-south-1"


class TestWhatIsSentToSes:
    @pytest.fixture
    def ses(self, clean_env):
        """Fake boto3 SES client plus fake (non-functional) credentials."""
        clean_env.setenv("AWS_ACCESS_KEY_ID", "AKIATESTFAKEFAKEFAKE")
        clean_env.setenv("AWS_SECRET_ACCESS_KEY", "test-fake-secret-not-real")
        client = MagicMock()
        client.send_email.return_value = {"MessageId": "test-message-id"}
        client.send_raw_email.return_value = {"MessageId": "test-raw-id"}
        with patch.object(email_service, "_get_ses_client", return_value=client):
            yield client

    def test_source_is_the_domain_sender_and_reply_to_is_the_support_inbox(self, ses, clean_env):
        clean_env.setenv("SES_FROM_EMAIL", "Tap & Go <noreply@thetapandgo.in>")
        clean_env.setenv("SES_REPLY_TO_EMAIL", "tapandgosupport@gmail.com")
        ok, err = email_service._send_ses_email("someone@example.com", "Subject", "<p>Hi</p>")
        assert ok is True and err is None
        kwargs = ses.send_email.call_args.kwargs
        assert kwargs["Source"] == "Tap & Go <noreply@thetapandgo.in>"
        assert kwargs["ReplyToAddresses"] == ["tapandgosupport@gmail.com"]
        assert kwargs["Destination"] == {"ToAddresses": ["someone@example.com"]}

    def test_with_nothing_configured_the_mail_still_leaves_from_the_domain(self, ses):
        ok, _ = email_service._send_ses_email("someone@example.com", "Subject", "<p>Hi</p>")
        assert ok is True
        kwargs = ses.send_email.call_args.kwargs
        assert kwargs["Source"] == "Tap & Go <noreply@thetapandgo.in>"
        assert "ReplyToAddresses" not in kwargs               # none is invented

    def test_the_attachment_path_uses_the_same_sender_and_reply_to(self, ses, clean_env):
        clean_env.setenv("SES_FROM_EMAIL", "Tap & Go <noreply@thetapandgo.in>")
        clean_env.setenv("SES_REPLY_TO_EMAIL", "tapandgosupport@gmail.com")
        ok, _ = email_service._send_ses_email(
            "someone@example.com", "Receipt", "<p>Hi</p>",
            attachments=[{"filename": "receipt.pdf", "content": b"%PDF-1.4", "mime_type": "application/pdf"}],
        )
        assert ok is True
        raw = ses.send_raw_email.call_args.kwargs
        assert raw["Source"] == "Tap & Go <noreply@thetapandgo.in>"
        mime = raw["RawMessage"]["Data"].decode("utf-8", "ignore")
        assert "From: Tap & Go <noreply@thetapandgo.in>" in mime
        assert "Reply-To: tapandgosupport@gmail.com" in mime

    def test_the_client_is_created_for_the_configured_region(self, clean_env):
        clean_env.setenv("AWS_ACCESS_KEY_ID", "AKIATESTFAKEFAKEFAKE")
        clean_env.setenv("AWS_SECRET_ACCESS_KEY", "test-fake-secret-not-real")
        clean_env.setenv("AWS_REGION", "ap-south-1")
        with patch.object(email_service.boto3, "client") as factory:
            email_service._get_ses_client()
        args, kwargs = factory.call_args
        assert args == ("ses",) and kwargs["region_name"] == "ap-south-1"


class TestClientTimeouts:
    def test_the_client_fails_fast_instead_of_hanging(self, clean_env):
        clean_env.setenv("AWS_ACCESS_KEY_ID", "AKIATESTFAKEFAKEFAKE")
        clean_env.setenv("AWS_SECRET_ACCESS_KEY", "test-fake-secret-not-real")
        with patch.object(email_service.boto3, "client") as factory:
            email_service._get_ses_client()
        cfg = factory.call_args.kwargs["config"]
        assert cfg.connect_timeout == 5 and cfg.read_timeout == 10
        assert cfg.retries["max_attempts"] == 2

    def test_a_provider_outage_is_reported_as_failure_without_leaking_credentials(self, clean_env):
        from botocore.exceptions import EndpointConnectionError
        clean_env.setenv("AWS_ACCESS_KEY_ID", "AKIATESTFAKEFAKEFAKE")
        clean_env.setenv("AWS_SECRET_ACCESS_KEY", "test-fake-secret-not-real")
        client = MagicMock()
        client.send_email.side_effect = EndpointConnectionError(endpoint_url="https://email.ap-south-1.amazonaws.com")
        with patch.object(email_service, "_get_ses_client", return_value=client):
            ok, err = email_service._send_ses_email("someone@example.com", "Subject", "<p>Hi</p>")
        assert ok is False and err
        assert "test-fake-secret-not-real" not in err and "AKIATESTFAKEFAKEFAKE" not in err
