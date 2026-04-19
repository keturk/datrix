"""Email helper functions for generated Python code.

Provider-specific implementations for AWS SES, Azure Communication Services, and SMTP.
Email send functions are designed to fail gracefully — they log a warning and return
False when the email provider is not configured, rather than crashing the caller.
This allows lifecycle hooks that send emails to not abort database operations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

_logger = logging.getLogger(__name__)


def _get_sender(opts: dict[str, object]) -> str:
    """Return sender address from opts or env. Raise if missing."""
    sender = opts.get("from") or os.environ.get("SMTP_FROM") or os.environ.get("AZURE_EMAIL_SENDER")
    if not sender:
        raise ValueError(
            "Email sender (from) is required. Set opts['from'] or env SMTP_FROM or AZURE_EMAIL_SENDER."
        )
    return sender


def _send_email_ses_sync(
    to: str,
    subject: str,
    body: str,
    options: Optional[dict] = None,
) -> None:
    import boto3

    client = boto3.client("ses")
    opts = options or {}
    kwargs: dict[str, object] = {
        "Source": _get_sender(opts),
        "Destination": {"ToAddresses": [to]},
        "Message": {
            "Subject": {"Data": subject},
            "Body": {"Text": {"Data": body}},
        },
    }
    if "cc" in opts:
        kwargs["Destination"]["CcAddresses"] = opts["cc"]
    client.send_email(**kwargs)


async def _email_send_ses(payload: dict[str, object]) -> bool:
    """Send email via AWS SES. Accepts a dict with to, subject, body/template, and optional fields."""
    try:
        to = payload["to"]
        subject = payload.get("subject", "")
        body = payload.get("body", "")
        options = {k: v for k, v in payload.items() if k not in ("to", "subject", "body")}
        await asyncio.to_thread(_send_email_ses_sync, to, subject, body, options or None)
        return True
    except Exception as exc:
        _logger.warning("email_send_failed provider=ses to=%s error=%s", payload.get("to"), exc)
        return False


def _send_template_ses_sync(
    to: str,
    template: str,
    data: dict,
    options: Optional[dict] = None,
) -> None:
    import boto3

    client = boto3.client("ses")
    opts = options or {}
    client.send_templated_email(
        Source=_get_sender(opts),
        Destination={"ToAddresses": [to]},
        Template=template,
        TemplateData=json.dumps(data),
    )


async def _email_send_template_ses(payload: dict[str, object]) -> bool:
    """Send templated email via AWS SES. Accepts a dict with to, template, data, and optional fields."""
    try:
        to = payload["to"]
        template = payload.get("template", "")
        data = payload.get("data", {})
        options = {k: v for k, v in payload.items() if k not in ("to", "template", "data")}
        await asyncio.to_thread(_send_template_ses_sync, to, template, data, options or None)
        return True
    except Exception as exc:
        _logger.warning(
            "email_send_template_failed provider=ses to=%s error=%s", payload.get("to"), exc
        )
        return False


async def _email_send_bulk_ses(recipients: list[str], subject: str, body: str) -> list[bool]:
    results = []
    for r in recipients:
        results.append(await _email_send_ses({"to": r, "subject": subject, "body": body}))
    return results


# ── Azure Communication Services ──


def _send_email_azure_sync(
    to: str,
    subject: str,
    body: str,
    options: Optional[dict] = None,
) -> None:
    from azure.communication.email import EmailClient

    client = EmailClient.from_connection_string(os.environ["AZURE_COMM_CONNECTION_STRING"])
    opts = options or {}
    sender = _get_sender(opts)
    message = {
        "senderAddress": sender,
        "recipients": {"to": [{"address": to}]},
        "content": {"subject": subject, "plainText": body},
    }
    poller = client.begin_send(message)
    poller.result()


async def _email_send_azure(payload: dict[str, object]) -> bool:
    """Send email via Azure Communication Services. Accepts a dict with to, subject, body, and optional fields."""
    try:
        to = payload["to"]
        subject = payload.get("subject", "")
        body = payload.get("body", "")
        options = {k: v for k, v in payload.items() if k not in ("to", "subject", "body")}
        await asyncio.to_thread(_send_email_azure_sync, to, subject, body, options or None)
        return True
    except Exception as exc:
        _logger.warning("email_send_failed provider=azure to=%s error=%s", payload.get("to"), exc)
        return False


async def _email_send_template_azure(payload: dict[str, object]) -> bool:
    """Send templated email via Azure. Accepts a dict with to, template, data, and optional fields."""
    try:
        to = payload["to"]
        template = payload.get("template", "")
        data = payload.get("data", {})
        body = f"Template: {template}, Data: {data}"
        options = {k: v for k, v in payload.items() if k not in ("to", "template", "data")}
        await asyncio.to_thread(_send_email_azure_sync, to, template, body, options or None)
        return True
    except Exception as exc:
        _logger.warning(
            "email_send_template_failed provider=azure to=%s error=%s", payload.get("to"), exc
        )
        return False


async def _email_send_bulk_azure(recipients: list[str], subject: str, body: str) -> list[bool]:
    results = []
    for r in recipients:
        results.append(await _email_send_azure({"to": r, "subject": subject, "body": body}))
    return results


# ── SMTP ──


async def _email_send_smtp(payload: dict[str, object]) -> bool:
    """Send email via SMTP. Accepts a dict with to, subject, body, and optional fields."""
    try:
        from email.message import EmailMessage

        import aiosmtplib

        to = payload["to"]
        subject = payload.get("subject", "")
        body = payload.get("body", "")
        options = {k: v for k, v in payload.items() if k not in ("to", "subject", "body")}

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = _get_sender(options)
        msg["To"] = to
        msg.set_content(body)
        await aiosmtplib.send(
            msg,
            hostname=os.environ["SMTP_HOST"],
            port=int(os.environ["SMTP_PORT"]),
        )
        return True
    except Exception as exc:
        _logger.warning("email_send_failed provider=smtp to=%s error=%s", payload.get("to"), exc)
        return False


async def _email_send_template_smtp(payload: dict[str, object]) -> bool:
    """Send templated email via SMTP. Accepts a dict with to, template, data, and optional fields."""
    try:
        template = payload.get("template", "")
        data = payload.get("data", {})
        body = f"Template: {template}, Data: {data}"
        return await _email_send_smtp({"to": payload["to"], "subject": template, "body": body})
    except Exception as exc:
        _logger.warning(
            "email_send_template_failed provider=smtp to=%s error=%s", payload.get("to"), exc
        )
        return False


async def _email_send_bulk_smtp(recipients: list[str], subject: str, body: str) -> list[bool]:
    results = []
    for r in recipients:
        results.append(await _email_send_smtp({"to": r, "subject": subject, "body": body}))
    return results
