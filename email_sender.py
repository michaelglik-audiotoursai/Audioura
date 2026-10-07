"""
email_sender.py — LOCAL-604 queue-offer email interface (framework-free).
=========================================================================

Design of record: LEAD ruling D619.

When a free-seat offer is created for a queued device, its claim code is sent to
the email the device gave when it joined the queue. The sender sits behind a
small interface selected by EMAIL_MODE so the provider is a deployment choice,
not a code change:

  EMAIL_MODE=log  (DEFAULT) — write the code to the log and return ok. Nothing
                   leaves the process. This is what every current deployment
                   (LOCAL, test, cloud-until-configured) uses: the app still
                   shows the pending offer in-app exactly as today, so NOTHING
                   depends on real email being wired up.

  EMAIL_MODE=smtp — send via SMTP using SMTP_HOST / SMTP_PORT / SMTP_USER /
                   SMTP_PASS / SMTP_FROM. LEAD and Michael pick the provider
                   later; this task ships the interface, NOT a configured
                   provider. If smtp is selected but the env is incomplete, we
                   fail SOFT (log a warning and return not-sent) — a mis-set
                   provider must never break the queue/offer flow.

Like l2_seats.py and level_codes.py this file exists TWICE (repo root and
user-tracking/) kept byte-identical by a mirror test, because the user-api
container's build context cannot import repo-root modules.

The code never emails anything itself at import; send_offer_email() is called
by the offer path with (email, code). It returns a small dict describing what
happened, and NEVER raises — email delivery is best-effort and must not abort
the DB transaction that created the offer.
"""

import os
import logging

logger = logging.getLogger(__name__)


def _mode():
    return os.getenv('EMAIL_MODE', 'log').strip().lower()


def _render(code, expires_minutes):
    """The one message body, shared by every mode so log and smtp say the same
    thing. Plain text — no PII beyond the recipient's own address."""
    subject = "Your Audioura free-plan code"
    ttl = f"{expires_minutes} minutes" if expires_minutes else "a short time"
    body = (
        "A free Audioura plan just opened up for you.\n\n"
        f"Your code is: {code}\n\n"
        f"Enter it in the app under Your plan -> I have a code. It is valid for "
        f"{ttl} from now. If it expires you keep your place in line and we will "
        "send a fresh code next time a seat frees.\n"
    )
    return subject, body


def send_offer_email(email, code, expires_minutes=None):
    """Send (or log) a queue-offer code to `email`. Returns a dict:
        {'sent': bool, 'mode': str, 'reason': str|None}
    Never raises. A missing email is a no-op (sent=False, reason='no_email') —
    the in-app pending offer still shows the code, so the device is never stuck.
    """
    mode = _mode()
    if not email:
        return {'sent': False, 'mode': mode, 'reason': 'no_email'}

    subject, body = _render(code, expires_minutes)

    if mode == 'smtp':
        host = os.getenv('SMTP_HOST')
        port = os.getenv('SMTP_PORT')
        user = os.getenv('SMTP_USER')
        password = os.getenv('SMTP_PASS')
        sender = os.getenv('SMTP_FROM')
        if not all([host, port, sender]):
            # Fail soft: a half-configured provider must not break the flow.
            logger.warning(
                "[LOCAL-604] EMAIL_MODE=smtp but SMTP_HOST/PORT/FROM are not all "
                "set — offer email not sent (the in-app offer still shows the code).")
            return {'sent': False, 'mode': mode, 'reason': 'smtp_not_configured'}
        try:
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = sender
            msg['To'] = email
            with smtplib.SMTP(host, int(port), timeout=15) as server:
                server.ehlo()
                try:
                    server.starttls()
                    server.ehlo()
                except Exception:
                    pass  # server may not support STARTTLS; continue plain.
                if user and password:
                    server.login(user, password)
                server.sendmail(sender, [email], msg.as_string())
            logger.info(f"[LOCAL-604] offer email sent via SMTP to {_redact(email)}")
            return {'sent': True, 'mode': mode, 'reason': None}
        except Exception as e:  # best-effort: never abort the offer
            logger.warning(f"[LOCAL-604] SMTP send failed ({e}); offer still shows in-app.")
            return {'sent': False, 'mode': mode, 'reason': f'smtp_error:{e}'}

    # Default 'log' mode (and any unknown mode): write the code to the log and
    # the l2_offers row is the record of it. The recipient address is redacted
    # in the log line; the code is written in full because this mode is the
    # local/dev delivery channel.
    logger.info(
        f"[LOCAL-604] EMAIL_MODE=log — offer code for {_redact(email)}: {code} "
        f"(subject: {subject!r})")
    return {'sent': True, 'mode': 'log', 'reason': None}


def _redact(email):
    """Redact an address for logs: keep the first char and the domain."""
    try:
        local, domain = email.split('@', 1)
        head = local[:1] if local else ''
        return f"{head}***@{domain}"
    except Exception:
        return "***"
