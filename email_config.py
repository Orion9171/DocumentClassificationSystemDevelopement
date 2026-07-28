from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from typing import Any, Dict

import utils as utl


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

ALLOWED_SECURITY_MODES = {
    "starttls",
    "ssl",
}

PERSISTED_EMAIL_KEYS = {
    "enabled",
    "smtp_host",
    "smtp_port",
    "smtp_user",
    "sender_email",
    "security_mode",
    "confidence_threshold",
    "max_attachment_mb",
    "subject_prefix",
    "remember_settings",
    "remember_password",
    "same_as_sender",
}

SENSITIVE_KEYS = {
    "smtp_pass",
    "smtp_password",
    "password",
    "token",
    "access_token",
}

LEGACY_TOP_LEVEL_KEYS = {
    "smtp_host",
    "smtp_port",
    "smtp_user",
    "smtp_pass",
    "smtp_password",
    "sender_email",
    "use_starttls",
    "security_mode",
}


class EmailConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmailSettings:
    enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_user: str
    sender_email: str
    security_mode: str
    confidence_threshold: float
    max_attachment_mb: float
    subject_prefix: str

    @property
    def max_attachment_bytes(self) -> int:
        return int(self.max_attachment_mb * 1024 * 1024)

    @classmethod
    def from_config(
        cls,
        config: Dict[str, Any],
        require_connection_settings: bool = True,
    ) -> "EmailSettings":
        section = dict(config.get("email_config") or {})

        # Compatibility with older top-level SMTP fields.
        for key in (
            "smtp_host",
            "smtp_port",
            "smtp_user",
            "sender_email",
        ):
            if key not in section and key in config:
                section[key] = config[key]

        # Secure default. Plain SMTP is never inferred.
        if "security_mode" not in section:
            section["security_mode"] = "starttls"

        try:
            settings = cls(
                enabled=bool(
                    section.get("enabled", True)
                ),
                smtp_host=str(
                    section.get("smtp_host", "") or ""
                ).strip(),
                smtp_port=int(
                    section.get("smtp_port", 587)
                ),
                smtp_user=str(
                    section.get("smtp_user", "") or ""
                ).strip(),
                sender_email=str(
                    section.get("sender_email", "") or ""
                ).strip(),
                security_mode=str(
                    section.get(
                        "security_mode",
                        "starttls",
                    )
                    or "starttls"
                ).strip().lower(),
                confidence_threshold=float(
                    section.get(
                        "confidence_threshold",
                        0.8,
                    )
                ),
                max_attachment_mb=float(
                    section.get(
                        "max_attachment_mb",
                        15,
                    )
                ),
                subject_prefix=str(
                    section.get(
                        "subject_prefix",
                        "[AI 公文分發]",
                    )
                    or ""
                ).strip(),
            )
        except (TypeError, ValueError) as exc:
            raise EmailConfigurationError(
                f"Invalid email configuration value: {exc}"
            ) from exc

        settings.validate(
            require_connection_settings=
            require_connection_settings
        )

        return settings

    def validate(
        self,
        require_connection_settings: bool = True,
    ) -> None:
        if not self.enabled:
            raise EmailConfigurationError(
                "Email function is disabled in config.json."
            )

        if not 1 <= self.smtp_port <= 65535:
            raise EmailConfigurationError(
                "smtp_port must be between 1 and 65535."
            )

        if self.security_mode not in ALLOWED_SECURITY_MODES:
            raise EmailConfigurationError(
                "security_mode must be either "
                "'starttls' or 'ssl'."
            )

        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise EmailConfigurationError(
                "confidence_threshold must be between 0 and 1."
            )

        if self.max_attachment_mb <= 0:
            raise EmailConfigurationError(
                "max_attachment_mb must be greater than 0."
            )

        # Opening the settings window is allowed before SMTP
        # account information has been configured.
        if not require_connection_settings:
            return

        missing = []

        if not self.smtp_host:
            missing.append("smtp_host")

        if not self.smtp_user:
            missing.append("smtp_user")

        if not self.sender_email:
            missing.append("sender_email")

        if missing:
            raise EmailConfigurationError(
                "Missing email configuration: "
                + ", ".join(missing)
            )

        # SMTP usernames are not necessarily email addresses.
        # Enterprise servers may use username or DOMAIN\\username.
        if not EMAIL_PATTERN.fullmatch(self.sender_email):
            raise EmailConfigurationError(
                f"Invalid sender_email: {self.sender_email}"
            )


def load_config(
    config_path: str,
) -> Dict[str, Any]:
    return utl.load_config(config_path)


def _atomic_write_json(
    config_path: str,
    config: Dict[str, Any],
) -> None:
    directory = os.path.dirname(
        os.path.abspath(config_path)
    )

    os.makedirs(
        directory,
        exist_ok=True,
    )

    fd, temp_path = tempfile.mkstemp(
        prefix="config_",
        suffix=".json.tmp",
        dir=directory,
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                config,
                file,
                ensure_ascii=False,
                indent=4,
            )

            file.flush()
            os.fsync(file.fileno())

        os.replace(
            temp_path,
            config_path,
        )

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def sanitize_config(
    config: Dict[str, Any],
) -> Dict[str, Any]:
    section = dict(
        config.get("email_config") or {}
    )

    for key in (
        "smtp_host",
        "smtp_port",
        "smtp_user",
        "sender_email",
    ):
        if key not in section and key in config:
            section[key] = config[key]

    # Never migrate a disabled STARTTLS flag into plaintext SMTP.
    if "security_mode" not in section:
        section["security_mode"] = "starttls"

    defaults = {
        "enabled": True,
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "sender_email": "",
        "security_mode": "starttls",
        "confidence_threshold": 0.8,
        "max_attachment_mb": 15,
        "subject_prefix": "[AI 公文分發]",
        "remember_settings": False,
        "remember_password": False,
        "same_as_sender": True,
    }

    clean_section = {
        key: section.get(key, default)
        for key, default in defaults.items()
    }

    # Remove legacy and sensitive fields from the JSON root.
    for key in list(config):
        if (
            key in LEGACY_TOP_LEVEL_KEYS
            or key.lower() in SENSITIVE_KEYS
        ):
            config.pop(key, None)

    # Defensive cleanup inside email_config.
    for key in list(clean_section):
        if (
            key.lower() in SENSITIVE_KEYS
            or key == "use_starttls"
        ):
            clean_section.pop(key, None)

    config["email_config"] = clean_section
    return config


def get_email_preferences(config_path: str) -> Dict[str, Any]:
    config = sanitize_config(load_config(config_path))
    section = config["email_config"]
    return {
        "remember_settings": bool(section.get("remember_settings", False)),
        "remember_password": bool(section.get("remember_password", False)),
        "same_as_sender": bool(section.get("same_as_sender", True)),
    }


def save_email_preferences(
    config_path: str,
    values: Dict[str, Any],
    *,
    remember_settings: bool,
    remember_password: bool,
    same_as_sender: bool,
) -> EmailSettings:
    forbidden = set(values) & SENSITIVE_KEYS
    if forbidden:
        raise EmailConfigurationError(
            "Sensitive credentials must not be stored in config.json: "
            + ", ".join(sorted(forbidden))
        )

    runtime_section = {
        "enabled": True,
        "smtp_host": values.get("smtp_host", ""),
        "smtp_port": values.get("smtp_port", 587),
        "smtp_user": values.get("smtp_user", ""),
        "sender_email": values.get("sender_email", ""),
    }

    current = sanitize_config(load_config(config_path))
    current_section = current["email_config"]
    for key in (
        "security_mode",
        "confidence_threshold",
        "max_attachment_mb",
        "subject_prefix",
    ):
        runtime_section[key] = current_section[key]

    runtime_settings = EmailSettings.from_config(
        {"email_config": runtime_section},
        require_connection_settings=True,
    )

    current_section["remember_settings"] = bool(remember_settings)
    current_section["remember_password"] = bool(
        remember_settings and remember_password
    )
    current_section["same_as_sender"] = bool(same_as_sender)

    if remember_settings:
        current_section.update({
            "smtp_host": runtime_settings.smtp_host,
            "smtp_port": runtime_settings.smtp_port,
            "smtp_user": runtime_settings.smtp_user,
            "sender_email": runtime_settings.sender_email,
        })
    else:
        current_section.update({
            "smtp_host": "",
            "smtp_port": 587,
            "smtp_user": "",
            "sender_email": "",
        })

    _atomic_write_json(config_path, current)
    return runtime_settings


def save_non_secret_email_settings(
    config_path: str,
    values: Dict[str, Any],
) -> EmailSettings:
    forbidden = set(values) & SENSITIVE_KEYS

    if forbidden:
        raise EmailConfigurationError(
            "Sensitive credentials must not be stored "
            "in config.json: "
            + ", ".join(sorted(forbidden))
        )

    unknown = set(values) - PERSISTED_EMAIL_KEYS

    if unknown:
        raise EmailConfigurationError(
            "Unsupported email configuration fields: "
            + ", ".join(sorted(unknown))
        )

    config = sanitize_config(
        load_config(config_path)
    )

    section = config["email_config"]
    section.update(values)

    # Saving requires complete non-secret SMTP settings.
    settings = EmailSettings.from_config(
        config,
        require_connection_settings=True,
    )

    _atomic_write_json(
        config_path,
        config,
    )

    return settings


def migrate_and_sanitize_config(
    config_path: str,
) -> EmailSettings:
    config = sanitize_config(
        load_config(config_path)
    )

    # Opening the Email Management window is allowed even
    # when SMTP connection information has not been entered yet.
    settings = EmailSettings.from_config(
        config,
        require_connection_settings=False,
    )

    _atomic_write_json(
        config_path,
        config,
    )

    return settings