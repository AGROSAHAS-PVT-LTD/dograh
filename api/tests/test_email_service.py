import pytest

from api.services import email as email_service


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.started_tls = False
        self.logged_in = None
        self.message = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def ehlo(self):
        return None

    def starttls(self, context=None):
        self.started_tls = True
        self.context = context

    def login(self, username, password):
        self.logged_in = (username, password)

    def send_message(self, message):
        self.message = message


@pytest.mark.asyncio
async def test_email_is_disabled_without_smtp(monkeypatch):
    monkeypatch.setattr(email_service, "EMAIL_DELIVERY_ENABLED", False)
    monkeypatch.setattr(email_service, "SMTP_HOST", None)
    sent = await email_service.send_email(
        to_email="person@example.com",
        subject="Hello",
        text_body="Body",
    )
    assert sent is False


@pytest.mark.asyncio
async def test_email_uses_starttls_and_login(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(email_service, "EMAIL_DELIVERY_ENABLED", True)
    monkeypatch.setattr(email_service, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_service, "SMTP_PORT", 587)
    monkeypatch.setattr(email_service, "SMTP_USE_SSL", False)
    monkeypatch.setattr(email_service, "SMTP_USE_TLS", True)
    monkeypatch.setattr(email_service, "SMTP_USERNAME", "user")
    monkeypatch.setattr(email_service, "SMTP_PASSWORD", "pass")
    monkeypatch.setattr(email_service, "SMTP_FROM_EMAIL", "no-reply@example.com")
    monkeypatch.setattr(email_service, "SMTP_FROM_NAME", "Dograh")
    monkeypatch.setattr(email_service, "SMTP_REPLY_TO", None)
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)

    sent = await email_service.send_email(
        to_email="person@example.com",
        subject="Hello",
        text_body="Plain body",
        html_body="<p>HTML body</p>",
    )

    assert sent is True
    smtp = FakeSMTP.instances[0]
    assert smtp.host == "smtp.example.com"
    assert smtp.started_tls is True
    assert smtp.logged_in == ("user", "pass")
    assert smtp.message["To"] == "person@example.com"
    assert smtp.message["Subject"] == "Hello"
    assert (
        "Plain body" in smtp.message.get_body(preferencelist=("plain",)).get_content()
    )


@pytest.mark.asyncio
async def test_password_reset_email_contains_link(monkeypatch):
    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(email_service, "send_email", fake_send)
    sent = await email_service.send_password_reset_email(
        to_email="person@example.com",
        reset_url="https://app.example.com/auth/reset?token=abc",
        expires_minutes=60,
    )

    assert sent is True
    assert captured["subject"] == "Reset your Dograh password"
    assert "https://app.example.com/auth/reset?token=abc" in captured["text_body"]
    assert "60 minutes" in captured["html_body"]


@pytest.mark.asyncio
async def test_invitation_email_contains_link_and_escapes_html(monkeypatch):
    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(email_service, "send_email", fake_send)
    sent = await email_service.send_invitation_email(
        to_email="person@example.com",
        invite_url="https://app.example.com/invite?token=abc",
        role="admin",
        inviter_email="owner@example.com",
        expires_at="2026-11-05 12:00 UTC",
    )

    assert sent is True
    assert captured["to_email"] == "person@example.com"
    assert "https://app.example.com/invite?token=abc" in captured["text_body"]
    assert "<strong>Admin</strong>" in captured["html_body"]
