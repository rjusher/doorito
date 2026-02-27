"""Unit tests for webhook delivery service."""

import hashlib
import hmac
from unittest.mock import MagicMock

import httpx
import pytest

from common.models import WebhookEndpoint
from common.services.webhook import compute_signature, deliver_to_endpoint


class TestComputeSignature:
    """Tests for compute_signature() function."""

    def test_known_hmac(self):
        payload = b'{"key": "value"}'
        secret = "test-secret"
        expected = hmac.new(
            secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        assert compute_signature(payload, secret) == expected

    def test_different_secret_different_signature(self):
        payload = b'{"key": "value"}'
        sig1 = compute_signature(payload, "secret-1")
        sig2 = compute_signature(payload, "secret-2")
        assert sig1 != sig2

    def test_different_payload_different_signature(self):
        secret = "test-secret"
        sig1 = compute_signature(b'{"a": 1}', secret)
        sig2 = compute_signature(b'{"b": 2}', secret)
        assert sig1 != sig2


@pytest.mark.django_db
class TestDeliverToEndpoint:
    """Tests for deliver_to_endpoint() function."""

    def _make_event(self, make_outbox_event):
        return make_outbox_event(
            event_type="file.stored",
            payload={"file_id": "123", "filename": "test.pdf"},
        )

    def _make_endpoint(self):
        return WebhookEndpoint.objects.create(
            url="https://example.com/webhook",
            secret="test-secret",
        )

    def test_successful_delivery(self, make_outbox_event):
        event = self._make_event(make_outbox_event)
        endpoint = self._make_endpoint()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        client = MagicMock(spec=httpx.Client)
        client.post.return_value = mock_response

        result = deliver_to_endpoint(client, endpoint, event)

        assert result["ok"] is True
        assert result["status_code"] == 200
        assert result["error"] == ""

    def test_http_error_response(self, make_outbox_event):
        event = self._make_event(make_outbox_event)
        endpoint = self._make_endpoint()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        exc = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_response
        )
        mock_response.raise_for_status.side_effect = exc

        client = MagicMock(spec=httpx.Client)
        client.post.return_value = mock_response

        result = deliver_to_endpoint(client, endpoint, event)

        assert result["ok"] is False
        assert result["status_code"] == 500
        assert "HTTP 500" in result["error"]

    def test_network_error(self, make_outbox_event):
        event = self._make_event(make_outbox_event)
        endpoint = self._make_endpoint()

        client = MagicMock(spec=httpx.Client)
        client.post.side_effect = httpx.ConnectError("Connection refused")

        result = deliver_to_endpoint(client, endpoint, event)

        assert result["ok"] is False
        assert result["status_code"] is None
        assert "ConnectError" in result["error"]

    def test_correct_headers_sent(self, make_outbox_event):
        event = self._make_event(make_outbox_event)
        endpoint = self._make_endpoint()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        client = MagicMock(spec=httpx.Client)
        client.post.return_value = mock_response

        deliver_to_endpoint(client, endpoint, event)

        call_args = client.post.call_args
        headers = call_args.kwargs["headers"]

        assert "X-Webhook-Signature" in headers
        assert headers["X-Webhook-Event"] == "file.stored"
        assert headers["X-Webhook-Delivery"] == str(event.pk)
        assert headers["Content-Type"] == "application/json"

    def test_signature_matches_payload(self, make_outbox_event):
        event = self._make_event(make_outbox_event)
        endpoint = self._make_endpoint()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        client = MagicMock(spec=httpx.Client)
        client.post.return_value = mock_response

        deliver_to_endpoint(client, endpoint, event)

        call_args = client.post.call_args
        sent_payload = call_args.kwargs["content"]
        sent_signature = call_args.kwargs["headers"]["X-Webhook-Signature"]

        expected_signature = compute_signature(sent_payload, endpoint.secret)
        assert sent_signature == expected_signature
