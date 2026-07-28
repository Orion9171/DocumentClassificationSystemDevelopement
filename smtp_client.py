from __future__ import annotations

import logging
import smtplib
import socket
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Dict

from email_config import EmailSettings


logger = logging.getLogger("email.smtp")


class SecureSMTPError(RuntimeError):
    """Base class for user-safe SMTP failures."""


class SMTPTransportSecurityError(SecureSMTPError):
    pass


class SMTPAuthenticationFailure(SecureSMTPError):
    pass


class SMTPConnectionFailure(SecureSMTPError):
    pass


class SMTPRecipientFailure(SecureSMTPError):
    pass


@dataclass(frozen=True)
class SMTPDeliveryResult:
    refused_recipients: Dict[str, tuple]


class SecureSMTPClient:
    """SMTP client that never permits unencrypted authentication or delivery."""

    def __init__(self, settings: EmailSettings, timeout: int = 30):
        self.settings = settings
        self.timeout = timeout

    @staticmethod
    def _tls_context() -> ssl.SSLContext:
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        if hasattr(ssl, "TLSVersion"):
            context.minimum_version = ssl.TLSVersion.TLSv1_2
        return context

    def send(self, message: EmailMessage, password: str) -> SMTPDeliveryResult:
        if not password:
            raise SMTPAuthenticationFailure("SMTP password is required.")

        try:
            if self.settings.security_mode == "ssl":
                refused = self._send_ssl(message, password)
            else:
                refused = self._send_starttls(message, password)
        except smtplib.SMTPAuthenticationError as exc:
            logger.warning("SMTP authentication failed for user=%s host=%s", self.settings.smtp_user, self.settings.smtp_host)
            raise SMTPAuthenticationFailure(
                "SMTP authentication failed. Verify the account, password, and server policy."
            ) from exc
        except ssl.SSLCertVerificationError as exc:
            logger.error("TLS certificate verification failed host=%s", self.settings.smtp_host)
            raise SMTPTransportSecurityError(
                "TLS certificate verification failed. Email sending was blocked."
            ) from exc
        except ssl.SSLError as exc:
            logger.error("TLS negotiation failed host=%s", self.settings.smtp_host)
            raise SMTPTransportSecurityError(
                "A secure TLS connection could not be established."
            ) from exc
        except smtplib.SMTPNotSupportedError as exc:
            logger.error("Required SMTP TLS feature unavailable host=%s", self.settings.smtp_host)
            raise SMTPTransportSecurityError(
                "The SMTP server does not support the required TLS security mode."
            ) from exc
        except (socket.timeout, TimeoutError) as exc:
            logger.warning("SMTP connection timed out host=%s", self.settings.smtp_host)
            raise SMTPConnectionFailure("The SMTP server connection timed out.") from exc
        except socket.gaierror as exc:
            logger.warning("SMTP hostname resolution failed host=%s", self.settings.smtp_host)
            raise SMTPConnectionFailure("The SMTP server address could not be resolved.") from exc
        except (ConnectionError, OSError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected) as exc:
            logger.warning("SMTP connection failed host=%s type=%s", self.settings.smtp_host, type(exc).__name__)
            raise SMTPConnectionFailure("The SMTP server could not be reached securely.") from exc
        except smtplib.SMTPRecipientsRefused as exc:
            logger.warning("SMTP recipients refused count=%d", len(exc.recipients))
            raise SMTPRecipientFailure("The SMTP server rejected all recipients.") from exc
        except smtplib.SMTPException as exc:
            logger.warning("SMTP protocol failure type=%s", type(exc).__name__)
            raise SecureSMTPError("The SMTP server rejected the request.") from exc

        if refused:
            logger.warning("SMTP partially refused recipients count=%d", len(refused))
            raise SMTPRecipientFailure(
                "The SMTP server rejected one or more recipients: "
                + ", ".join(sorted(refused))
            )

        return SMTPDeliveryResult(refused_recipients={})


    def test_authentication(self, password: str) -> None:
        """Validate DNS, TLS, certificate verification, and SMTP login without sending mail."""
        if not password:
            raise SMTPAuthenticationFailure("SMTP password is required.")

        try:
            context = self._tls_context()
            if self.settings.security_mode == "ssl":
                with smtplib.SMTP_SSL(
                    host=self.settings.smtp_host,
                    port=self.settings.smtp_port,
                    timeout=self.timeout,
                    context=context,
                ) as server:
                    server.ehlo()
                    server.login(self.settings.smtp_user, password)
                    server.noop()
            else:
                with smtplib.SMTP(
                    host=self.settings.smtp_host,
                    port=self.settings.smtp_port,
                    timeout=self.timeout,
                ) as server:
                    server.ehlo()
                    if not server.has_extn("STARTTLS"):
                        raise SMTPTransportSecurityError(
                            "The SMTP server did not advertise STARTTLS. Connection testing was blocked."
                        )
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(self.settings.smtp_user, password)
                    server.noop()
        except SMTPTransportSecurityError:
            raise
        except smtplib.SMTPAuthenticationError as exc:
            logger.warning(
                "SMTP authentication test failed for user=%s host=%s",
                self.settings.smtp_user,
                self.settings.smtp_host,
            )
            raise SMTPAuthenticationFailure(
                "SMTP authentication failed. Verify the account, password, app password, and server policy."
            ) from exc
        except ssl.SSLCertVerificationError as exc:
            logger.error("TLS certificate verification failed host=%s", self.settings.smtp_host)
            raise SMTPTransportSecurityError(
                "TLS certificate verification failed. The connection was blocked."
            ) from exc
        except ssl.SSLError as exc:
            logger.error("TLS negotiation failed host=%s", self.settings.smtp_host)
            raise SMTPTransportSecurityError(
                "A secure TLS connection could not be established."
            ) from exc
        except smtplib.SMTPNotSupportedError as exc:
            logger.error("Required SMTP TLS feature unavailable host=%s", self.settings.smtp_host)
            raise SMTPTransportSecurityError(
                "The SMTP server does not support the required TLS security mode."
            ) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise SMTPConnectionFailure("The SMTP server connection timed out.") from exc
        except socket.gaierror as exc:
            raise SMTPConnectionFailure("The SMTP server address could not be resolved.") from exc
        except (ConnectionError, OSError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected) as exc:
            raise SMTPConnectionFailure("The SMTP server could not be reached securely.") from exc
        except smtplib.SMTPException as exc:
            raise SecureSMTPError("The SMTP server rejected the authentication test.") from exc

    def _send_starttls(self, message: EmailMessage, password: str):
        context = self._tls_context()
        with smtplib.SMTP(
            host=self.settings.smtp_host,
            port=self.settings.smtp_port,
            timeout=self.timeout,
        ) as server:
            server.ehlo()
            if not server.has_extn("STARTTLS"):
                raise SMTPTransportSecurityError(
                    "The SMTP server did not advertise STARTTLS. Email sending was blocked."
                )
            server.starttls(context=context)
            server.ehlo()
            server.login(self.settings.smtp_user, password)
            return server.send_message(message)

    def _send_ssl(self, message: EmailMessage, password: str):
        context = self._tls_context()
        with smtplib.SMTP_SSL(
            host=self.settings.smtp_host,
            port=self.settings.smtp_port,
            timeout=self.timeout,
            context=context,
        ) as server:
            server.ehlo()
            server.login(self.settings.smtp_user, password)
            return server.send_message(message)