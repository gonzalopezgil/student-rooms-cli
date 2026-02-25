"""
tests/test_notifiers.py — Tests for the pluggable notification system.
"""
import json
import unittest
from unittest.mock import patch, MagicMock

from student_rooms.models.config import (
    NotificationConfig,
    StdoutNotifierConfig,
    WebhookNotifierConfig,
    TelegramNotifierConfig,
    OpenClawNotifierConfig,
)
from student_rooms.notifiers.base import BaseNotifier, StdoutNotifier, create_notifier
from student_rooms.notifiers.webhook import WebhookNotifier
from student_rooms.notifiers.telegram import TelegramNotifier
from student_rooms.notifiers.openclaw import OpenClawNotifier


class TestStdoutNotifier(unittest.TestCase):
    """Test the default stdout notifier."""

    def test_name(self):
        n = StdoutNotifier()
        self.assertEqual(n.name, "stdout")

    def test_send_returns_true(self):
        n = StdoutNotifier()
        self.assertTrue(n.send("Hello, test!"))

    def test_validate_returns_none(self):
        n = StdoutNotifier()
        self.assertIsNone(n.validate())


class TestWebhookNotifier(unittest.TestCase):
    """Test the webhook notifier."""

    def test_validate_missing_url(self):
        cfg = WebhookNotifierConfig(enabled=True, url=None)
        n = WebhookNotifier(cfg)
        self.assertIsNotNone(n.validate())

    def test_validate_ok(self):
        cfg = WebhookNotifierConfig(enabled=True, url="https://example.com/webhook")
        n = WebhookNotifier(cfg)
        self.assertIsNone(n.validate())

    @patch("student_rooms.notifiers.webhook.requests.request")
    def test_send_success(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_request.return_value = mock_resp

        cfg = WebhookNotifierConfig(enabled=True, url="https://example.com/webhook")
        n = WebhookNotifier(cfg)
        result = n.send("Test message")

        self.assertTrue(result)
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args
        self.assertEqual(call_kwargs[0][0], "POST")
        self.assertEqual(call_kwargs[0][1], "https://example.com/webhook")

    @patch("student_rooms.notifiers.webhook.requests.request")
    def test_send_failure(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_request.return_value = mock_resp

        cfg = WebhookNotifierConfig(enabled=True, url="https://example.com/webhook")
        n = WebhookNotifier(cfg)
        result = n.send("Test message")

        self.assertFalse(result)

    @patch("student_rooms.notifiers.webhook.requests.request")
    def test_send_with_custom_body_template(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_request.return_value = mock_resp

        cfg = WebhookNotifierConfig(
            enabled=True,
            url="https://example.com/webhook",
            body_template='{"msg": "{message}"}',
        )
        n = WebhookNotifier(cfg)
        n.send("Hello world")

        call_kwargs = mock_request.call_args
        # Should have parsed JSON from template
        self.assertIn("json", call_kwargs[1])

    @patch("student_rooms.notifiers.webhook.requests.request")
    def test_send_with_custom_headers(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_request.return_value = mock_resp

        cfg = WebhookNotifierConfig(
            enabled=True,
            url="https://example.com/webhook",
            headers={"Authorization": "Bearer test123"},
        )
        n = WebhookNotifier(cfg)
        n.send("Test")

        call_kwargs = mock_request.call_args
        headers = call_kwargs[1].get("headers", {})
        self.assertEqual(headers.get("Authorization"), "Bearer test123")

    def test_send_without_url_returns_false(self):
        cfg = WebhookNotifierConfig(enabled=True, url=None)
        n = WebhookNotifier(cfg)
        result = n.send("Test")
        self.assertFalse(result)


class TestTelegramNotifier(unittest.TestCase):
    """Test the Telegram Bot API notifier."""

    def test_validate_missing_bot_token(self):
        cfg = TelegramNotifierConfig(enabled=True, bot_token=None, chat_id="12345")
        n = TelegramNotifier(cfg)
        self.assertIsNotNone(n.validate())

    def test_validate_missing_chat_id(self):
        cfg = TelegramNotifierConfig(enabled=True, bot_token="abc:xyz", chat_id=None)
        n = TelegramNotifier(cfg)
        self.assertIsNotNone(n.validate())

    def test_validate_ok(self):
        cfg = TelegramNotifierConfig(enabled=True, bot_token="abc:xyz", chat_id="12345")
        n = TelegramNotifier(cfg)
        self.assertIsNone(n.validate())

    @patch("student_rooms.notifiers.telegram.requests.post")
    def test_send_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {}}
        mock_post.return_value = mock_resp

        cfg = TelegramNotifierConfig(enabled=True, bot_token="123:ABC", chat_id="999")
        n = TelegramNotifier(cfg)
        result = n.send("Test notification")

        self.assertTrue(result)
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertIn("/bot123:ABC/sendMessage", call_args[0][0])
        payload = call_args[1]["json"]
        self.assertEqual(payload["chat_id"], "999")
        self.assertEqual(payload["text"], "Test notification")

    @patch("student_rooms.notifiers.telegram.requests.post")
    def test_send_with_parse_mode(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp

        cfg = TelegramNotifierConfig(enabled=True, bot_token="123:ABC", chat_id="999", parse_mode="HTML")
        n = TelegramNotifier(cfg)
        n.send("Test")

        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["parse_mode"], "HTML")

    @patch("student_rooms.notifiers.telegram.requests.post")
    def test_send_api_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": False, "description": "Bad Request"}
        mock_post.return_value = mock_resp

        cfg = TelegramNotifierConfig(enabled=True, bot_token="123:ABC", chat_id="999")
        n = TelegramNotifier(cfg)
        result = n.send("Test")

        self.assertFalse(result)

    def test_send_without_config_returns_false(self):
        cfg = TelegramNotifierConfig(enabled=True, bot_token=None, chat_id=None)
        n = TelegramNotifier(cfg)
        result = n.send("Test")
        self.assertFalse(result)


class TestOpenClawNotifier(unittest.TestCase):
    """Test the OpenClaw notifier."""

    def test_validate_missing_target(self):
        cfg = OpenClawNotifierConfig(enabled=True, target=None)
        n = OpenClawNotifier(cfg)
        self.assertIsNotNone(n.validate())

    def test_validate_ok(self):
        cfg = OpenClawNotifierConfig(enabled=True, target="12345")
        n = OpenClawNotifier(cfg)
        self.assertIsNone(n.validate())

    def test_validate_bad_mode(self):
        cfg = OpenClawNotifierConfig(enabled=True, target="12345", mode="invalid")
        n = OpenClawNotifier(cfg)
        self.assertIsNotNone(n.validate())


class TestCreateNotifier(unittest.TestCase):
    """Test the notifier factory."""

    def test_creates_stdout_by_default(self):
        cfg = NotificationConfig(type="stdout")
        n = create_notifier(cfg)
        self.assertIsInstance(n, StdoutNotifier)

    def test_creates_webhook(self):
        cfg = NotificationConfig(
            type="webhook",
            webhook=WebhookNotifierConfig(enabled=True, url="https://example.com"),
        )
        n = create_notifier(cfg)
        self.assertIsInstance(n, WebhookNotifier)

    def test_creates_telegram(self):
        cfg = NotificationConfig(
            type="telegram",
            telegram=TelegramNotifierConfig(enabled=True, bot_token="x", chat_id="1"),
        )
        n = create_notifier(cfg)
        self.assertIsInstance(n, TelegramNotifier)

    def test_creates_openclaw(self):
        cfg = NotificationConfig(
            type="openclaw",
            openclaw=OpenClawNotifierConfig(enabled=True, target="12345"),
        )
        n = create_notifier(cfg)
        self.assertIsInstance(n, OpenClawNotifier)

    def test_unknown_type_falls_back_to_stdout(self):
        cfg = NotificationConfig(type="unknown_type")
        n = create_notifier(cfg)
        self.assertIsInstance(n, StdoutNotifier)


if __name__ == "__main__":
    unittest.main()
