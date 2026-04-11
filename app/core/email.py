import logging
from typing import List

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from pydantic import EmailStr

from app.config import settings

logger = logging.getLogger(__name__)

conf = ConnectionConfig(
    MAIL_USERNAME=settings.smtp_user,
    MAIL_PASSWORD=settings.smtp_password,
    MAIL_FROM=settings.smtp_from,
    MAIL_PORT=settings.smtp_port,
    MAIL_SERVER=settings.smtp_host,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
)

async def send_email(recipients: List[EmailStr], subject: str, body: str):
    """General purpose async email sender."""
    if not settings.smtp_host or not settings.smtp_user:
        logger.warning("SMTP not configured. Email to %s skipped.", recipients)
        logger.info("Email content: \nSubject: %s\nBody: %s", subject, body)
        return

    message = MessageSchema(
        subject=subject,
        recipients=recipients,
        body=body,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    try:
        await fm.send_message(message)
    except Exception as e:
        logger.error("Failed to send email to %s: %s", recipients, str(e))

async def send_welcome_email(email: EmailStr, temporary_password: str):
    subject = "Welcome to BolChat AI"
    body = f"""
    <html>
        <body>
            <h3>Welcome to BolChat AI</h3>
            <p>Your account has been created by the administrator.</p>
            <p><strong>Email:</strong> {email}</p>
            <p><strong>Temporary Password:</strong> {temporary_password}</p>
            <p>Please log in at <a href="{settings.app_url}">{settings.app_url}</a> to change your password.</p>
        </body>
    </html>
    """
    await send_email([email], subject, body)

async def send_lead_email(name: str, email: str, company: str, requirements: str):
    subject = f"🚀 New BolChat Lead: {company}"
    body = f"""
    <html>
        <body>
            <h2>New Landing Page Lead</h2>
            <p><strong>Name:</strong> {name}</p>
            <p><strong>Email:</strong> {email}</p>
            <p><strong>Company:</strong> {company}</p>
            <p><strong>Requirements:</strong><br/>{requirements}</p>
        </body>
    </html>
    """
    await send_email([settings.superadmin_email], subject, body)
