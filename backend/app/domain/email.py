import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import escape
from typing import Protocol
from urllib.parse import urlencode

from app.core.config import Settings

FONT = "Arial,Helvetica,sans-serif"
PAPER = "#ece9e1"
CARD = "#f6f4ee"
INK = "#1c2220"
MUTED = "#555c58"
LINE = "#dcd7ca"
ACCENT = "#22695f"
BRASS = "#a86f1c"
TONES = {"critical": "#b0433a", "attention": "#b3741a", "info": ACCENT}
LEVELS = {"critical": "Критично", "attention": "Внимание", "info": "Информация"}


class EmailProvider(Protocol):
    @property
    def configured(self) -> bool: ...

    def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        *,
        html: str | None = None,
        delivery_id: str | None = None,
    ) -> None: ...


class NullEmailProvider:
    @property
    def configured(self) -> bool:
        return False

    def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        *,
        html: str | None = None,
        delivery_id: str | None = None,
    ) -> None:
        raise RuntimeError("Отправка электронной почты не настроена")


class SmtpEmailProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        return self._settings.smtp_configured

    def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        *,
        html: str | None = None,
        delivery_id: str | None = None,
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
        if html:
            message.add_alternative(html, subtype="html")
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


def vena_link(public_url: str, path: str, **query: str) -> str:
    url = public_url.rstrip("/") + path
    return f"{url}?{urlencode(query)}" if query else url


@dataclass(frozen=True)
class Letter:
    kicker: str
    title: str
    link: str
    tone: str = "info"
    summary: str = ""
    facts: list[tuple[str, str]] = field(default_factory=list)
    notes: list[tuple[str, str]] = field(default_factory=list)
    sections: list[tuple[str, list[str]]] = field(default_factory=list)

    def text(self) -> str:
        lines = [f"VENA · {self.kicker}", "", self.title]
        if self.summary:
            lines.append(self.summary)
        if self.facts:
            lines.append("")
            lines.extend(f"{label}: {value}" for label, value in self.facts)
        for label, value in self.notes:
            lines.extend(["", f"{label}: {value}"])
        for title, items in self.sections:
            lines.extend(["", title])
            lines.extend(f"  {item}" for item in items or ["—"])
        lines.extend(["", f"Открыть в VENA: {self.link}"])
        return "\n".join(lines)

    def html(self) -> str:
        tone = TONES.get(self.tone, ACCENT)
        link = escape(self.link)
        rows = [
            f'<tr><td style="padding:22px 32px 18px;border-bottom:3px solid {ACCENT};">'
            f'<span style="font:700 20px/1 {FONT};letter-spacing:5px;color:{ACCENT};">VENA</span>'
            f'<span style="padding-left:14px;font:600 11px/1 {FONT};letter-spacing:1px;'
            f'text-transform:uppercase;color:{BRASS};">{escape(self.kicker)}</span></td></tr>',
            f'<tr><td style="padding:26px 32px 4px;border-left:4px solid {tone};">'
            f'<h1 style="margin:0;font:700 21px/1.35 {FONT};color:{INK};">{escape(self.title)}</h1>'
            + (
                f'<p style="margin:10px 0 0;font:15px/1.55 {FONT};color:{MUTED};">'
                f"{escape(self.summary)}</p>"
                if self.summary
                else ""
            )
            + "</td></tr>",
        ]
        if self.facts:
            cells = "".join(
                f'<tr><td style="width:38%;padding:9px 12px 9px 0;border-bottom:1px solid {LINE};'
                f'vertical-align:top;font:13px/1.45 {FONT};color:{MUTED};">{escape(label)}</td>'
                f'<td style="padding:9px 0;border-bottom:1px solid {LINE};vertical-align:top;'
                f'font:600 14px/1.45 {FONT};color:{tone if label == "Уровень" else INK};">'
                f"{escape(value)}</td></tr>"
                for label, value in self.facts
            )
            rows.append(
                f'<tr><td style="padding:18px 32px 0;"><table role="presentation" width="100%" '
                f'cellpadding="0" cellspacing="0" border="0" style="border-top:1px solid {LINE};">'
                f"{cells}</table></td></tr>"
            )
        rows.extend(
            f'<tr><td style="padding:18px 32px 0;"><div style="border-left:3px solid {BRASS};'
            f'padding:2px 0 2px 14px;"><div style="font:700 11px/1.4 {FONT};letter-spacing:1px;'
            f'text-transform:uppercase;color:{BRASS};">{escape(label)}</div>'
            f'<div style="margin-top:4px;font:15px/1.55 {FONT};color:{INK};">{escape(value)}'
            f"</div></div></td></tr>"
            for label, value in self.notes
        )
        for title, items in self.sections:
            entries = "".join(
                f'<tr><td style="padding:7px 0;border-bottom:1px solid {PAPER};'
                f'font:14px/1.45 {FONT};color:{INK};">{escape(item)}</td></tr>'
                for item in items or ["—"]
            )
            rows.append(
                f'<tr><td style="padding:20px 32px 0;"><div style="padding-bottom:6px;'
                f'border-bottom:1px solid {LINE};font:700 14px/1.4 {FONT};color:{ACCENT};">'
                f'{escape(title)}<span style="font-weight:400;color:{MUTED};"> · {len(items)}'
                f'</span></div><table role="presentation" width="100%" cellpadding="0" '
                f'cellspacing="0" border="0">{entries}</table></td></tr>'
            )
        rows.append(
            f'<tr><td style="padding:28px 32px 30px;"><table role="presentation" cellpadding="0" '
            f'cellspacing="0" border="0"><tr><td bgcolor="{ACCENT}" style="border-radius:4px;'
            f'background:{ACCENT};"><a href="{link}" target="_blank" style="display:inline-block;'
            f"padding:13px 24px;font:700 15px/1 {FONT};color:#ffffff;text-decoration:none;"
            f'border-radius:4px;">Открыть в VENA</a></td></tr></table></td></tr>'
        )
        rows.append(
            f'<tr><td style="padding:18px 32px 24px;border-top:1px solid {LINE};'
            f'font:12px/1.55 {FONT};color:{MUTED};">Письмо сформировано VENA автоматически. '
            f"Получателей и правила настраивает администратор в разделе «Настройки → "
            f'Уведомления».<br><a href="{link}" style="color:{ACCENT};word-break:break-all;">'
            f"{link}</a></td></tr>"
        )
        preheader = escape(self.summary or self.title)
        return (
            '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="color-scheme" content="light only">'
            f"<title>{escape(self.title)}</title></head>"
            f'<body style="margin:0;padding:0;background:{PAPER};">'
            f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{PAPER};">'
            f"{preheader}</div>"
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'bgcolor="{PAPER}" style="background:{PAPER};"><tr><td align="center" '
            f'style="padding:24px 12px;"><table role="presentation" width="100%" cellpadding="0" '
            f'cellspacing="0" border="0" bgcolor="{CARD}" style="max-width:600px;background:{CARD};'
            f'border:1px solid {LINE};">{"".join(rows)}</table></td></tr></table></body></html>'
        )
