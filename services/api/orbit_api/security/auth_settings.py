"""Environment-backed first-party authentication configuration."""

from dataclasses import dataclass
from os import environ


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AuthSettings:
    enabled: bool
    secret: str
    public_base_url: str
    cookie_secure: bool
    debug_codes: bool
    password_enabled: bool = False
    resend_api_key: str = ""
    email_from: str = "Orbit Wars <noreply@example.invalid>"
    github_enabled: bool = False
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = ""
    google_enabled: bool = False

    @classmethod
    def from_environment(cls) -> "AuthSettings":
        app_env = environ.get("APP_ENV", "development").strip().lower()
        production = app_env in {"production", "prod"}
        enabled = _enabled(environ.get("ORBIT_AUTH_ENABLED"))
        password_enabled = enabled and _enabled(environ.get("ORBIT_PASSWORD_AUTH_ENABLED"))
        public_base_url = environ.get("ORBIT_PUBLIC_BASE_URL", "http://localhost:3000").rstrip("/")
        secret = environ.get("ORBIT_AUTH_SECRET", "")
        debug_codes = _enabled(environ.get("ORBIT_AUTH_DEBUG_CODES")) and not production
        cookie_secure = public_base_url.startswith("https://")

        if enabled and len(secret.encode("utf-8")) < 32:
            raise RuntimeError("ORBIT_AUTH_SECRET must contain at least 32 bytes")
        if enabled and production and not cookie_secure:
            raise RuntimeError("first-party authentication requires an HTTPS public URL")
        if password_enabled and not debug_codes and not environ.get("RESEND_API_KEY"):
            raise RuntimeError("RESEND_API_KEY is required when debug codes are disabled")

        github_client_id = environ.get("GITHUB_OAUTH_CLIENT_ID", "")
        github_client_secret = environ.get("GITHUB_OAUTH_CLIENT_SECRET", "")
        github_enabled = enabled and bool(github_client_id and github_client_secret)

        return cls(
            enabled=enabled,
            secret=secret,
            public_base_url=public_base_url,
            cookie_secure=cookie_secure,
            debug_codes=debug_codes,
            password_enabled=password_enabled,
            resend_api_key=environ.get("RESEND_API_KEY", ""),
            email_from=environ.get("ORBIT_AUTH_EMAIL_FROM", "Orbit Wars <noreply@example.invalid>"),
            github_enabled=github_enabled,
            github_client_id=github_client_id,
            github_client_secret=github_client_secret,
            github_redirect_uri=environ.get(
                "GITHUB_OAUTH_REDIRECT_URI",
                f"{public_base_url}/orbit-api/api/auth/github/callback",
            ),
            google_enabled=bool(environ.get("GOOGLE_OAUTH_CLIENT_ID")),
        )


def get_auth_settings() -> AuthSettings:
    return AuthSettings.from_environment()
