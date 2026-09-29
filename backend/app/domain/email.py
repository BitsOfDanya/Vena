import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Protocol

from app.core.config import Settings


class EmailProvider(Protocol):
    @property
    def configured(self) -> bool: ...

    def send(
        self, recipient: str, subject: str, body: str, *, delivery_id: str | None = None
    ) -> None: ...


class NullEmailProvider:
    @property
    def configured(self) -> bool:
        return False

    def send(
        self, recipient: str, subject: str, body: str, *, delivery_id: str | None = None
    ) -> None:
        raise RuntimeError("Отправка электронной почты не настроена")


class SmtpEmailProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        return self._settings.smtp_configured

    def send(
        self, recipient: str, subject: str, body: str, *, delivery_id: str | None = None
    ) -> None:
        settings = self._settings
        message = EmailMessage()
        message["From"] = settings.smtp_from
        message["To"] = recipient
        message["Subject"] = subject
        if not delivery_id:
            message["Date"] = formatdate(localtime=False)
        message["Message-ID"] = f"<vena-{delivery_id}@5bit.online>" if delivery_id else make_msgid()
        if delivery_id and settings.smtp_host == "smtp.resend.com":
            message["Resend-Idempotency-Key"] = f"vena-delivery/{delivery_id}"
        message.set_content(body)
        context = ssl.create_default_context()
        connection = (
            smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15, context=context)
            if settings.smtp_secure
            else smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
        )
        with connection as client:
            if not settings.smtp_secure and settings.smtp_tls:
                client.starttls(context=context)
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            client.send_message(message)


def build_email_provider(settings: Settings) -> EmailProvider:
    return SmtpEmailProvider(settings) if settings.smtp_configured else NullEmailProvider()


def alert_body(public_url: str, asset_id: str, severity: str, horizon: str, reason: str) -> str:
    level = {"info": "Информация", "attention": "Требует внимания", "critical": "Критический"}
    return "\n".join(
        [
            "VENA",
            "Уведомление о состоянии оборудования",
            "",
            f"Канал: {asset_id}",
            f"Уровень: {level.get(severity, severity)}",
            f"Период: {horizon}",
            f"Причина: {reason}",
            "",
            f"Открыть в VENA: {public_url}/network",
        ]
    )


def assignment_body(
    public_url: str, asset_id: str, task: str, priority: str, due: str, reason: str
) -> str:
    return "\n".join(
        [
            "VENA",
            "Назначена работа",
            "",
            f"Канал: {asset_id}",
            f"Работа: {task}",
            f"Приоритет: {priority}",
            f"Срок: {due}",
            f"Причина: {reason}",
            "",
            f"Открыть в VENA: {public_url}/actions",
        ]
    )


def digest_body(public_url: str, sections: list[tuple[str, list[str]]]) -> str:
    lines = ["VENA", "Утренняя сводка", ""]
    for title, items in sections:
        lines.append(title)
        lines.extend(f"  {item}" for item in items or ["—"])
        lines.append("")
    lines.append(f"Открыть в VENA: {public_url}/pulse")
    return "\n".join(lines)
