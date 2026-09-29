from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DeliveryLog, utcnow
from app.domain.email import EmailProvider


def enqueue(session: Session, recipient: str, subject: str, body: str, **metadata) -> DeliveryLog:
    log = DeliveryLog(
        channel="email",
        recipient=recipient,
        subject=subject[:240],
        body=body,
        status="pending",
        **metadata,
    )
    session.add(log)
    session.flush()
    return log


def deliver_pending(session: Session, provider: EmailProvider, limit: int = 20) -> int:
    if not provider.configured:
        return 0
    sent = 0
    for _ in range(limit):
        # Lock one message until SMTP accepts it; other workers skip this row.
        log = session.scalars(
            select(DeliveryLog)
            .where(
                DeliveryLog.channel == "email",
                DeliveryLog.status == "pending",
                DeliveryLog.next_attempt_at <= utcnow(),
                DeliveryLog.subject != "",
            )
            .order_by(DeliveryLog.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if log is None:
            session.commit()
            break
        log.attempts += 1
        try:
            provider.send(log.recipient, log.subject, log.body, delivery_id=str(log.id))
        except Exception as error:
            # SMTP responses can contain addresses or credentials; store only the error class.
            log.detail = f"Ошибка отправки ({type(error).__name__})"
            log.status = "failed" if log.attempts >= 6 else "pending"
            log.next_attempt_at = utcnow() + timedelta(seconds=60 * 2 ** (log.attempts - 1))
        else:
            log.status = "sent"
            log.sent_at = utcnow()
            log.detail = "Принято почтовым сервером"
            sent += 1
        session.commit()
    return sent
