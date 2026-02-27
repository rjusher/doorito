"""Webhook delivery service for outbox events."""

import hashlib
import hmac
import json
import logging

import httpx

logger = logging.getLogger(__name__)

WEBHOOK_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def compute_signature(payload_bytes, secret):
    """Compute HMAC-SHA256 signature for webhook payload.

    Args:
        payload_bytes: The raw bytes of the JSON payload.
        secret: The shared secret string.

    Returns:
        Hex-encoded HMAC-SHA256 signature string.
    """
    return hmac.new(
        secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()


def deliver_to_endpoint(client, endpoint, event):
    """Deliver an outbox event to a single webhook endpoint.

    Posts the event payload as JSON with HMAC signature and
    metadata headers.

    Args:
        client: An httpx.Client instance (for connection pooling).
        endpoint: A WebhookEndpoint instance.
        event: An OutboxEvent instance.

    Returns:
        dict: {"ok": bool, "status_code": int|None, "error": str}
    """
    payload_bytes = json.dumps(event.payload, default=str).encode("utf-8")
    signature = compute_signature(payload_bytes, endpoint.secret)

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
        "X-Webhook-Event": event.event_type,
        "X-Webhook-Delivery": str(event.pk),
    }

    try:
        response = client.post(
            str(endpoint.url), content=payload_bytes, headers=headers
        )
        response.raise_for_status()
        logger.info(
            "Webhook delivered: event=%s endpoint=%s status=%d",
            event.pk,
            endpoint.url,
            response.status_code,
        )
        return {"ok": True, "status_code": response.status_code, "error": ""}
    except httpx.HTTPStatusError as exc:
        error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        logger.warning(
            "Webhook HTTP error: event=%s endpoint=%s error=%s",
            event.pk,
            endpoint.url,
            error,
        )
        return {"ok": False, "status_code": exc.response.status_code, "error": error}
    except httpx.RequestError as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "Webhook request error: event=%s endpoint=%s error=%s",
            event.pk,
            endpoint.url,
            error,
        )
        return {"ok": False, "status_code": None, "error": error}
