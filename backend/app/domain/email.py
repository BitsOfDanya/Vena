import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings


class EmailProvider(Protocol):
    @property
    def configured(self) -> bool: ...

    def send(self, recipient: str, subject: str, body: str) -> None: ...


class NullEmailProvider:
    @property
    def configured(self) -> bool:
        return False

    def send(self, recipient: str, subject: str, body: str) -> None:
        raise RuntimeError("Отправка электронной почты не настроена")


class SmtpEmailProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        return self._settings.smtp_configured

    def send(self, recipient: str, subject: str, body: str) -> None:
        settings = self._settings
        message = EmailMessage()
        message["From"] = settings.smtp_from
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
            if settings.smtp_tls:
                client.starttls()
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)


def build_email_provider(settings: Settings) -> EmailProvider:
    return SmtpEmailProvider(settings) if settings.smtp_configured else NullEmailProvider()


def alert_body(public_url: str, asset_id: str, severity: str, horizon: str, reason: str) -> str:
    return "\n".join(
        [
            "VENA",
            "Критический риск на объекте",
            "",
            f"Канал: {asset_id}",
            f"Уровень: {severity}",
            f"Горизонт прогноза: {horizon}",
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
