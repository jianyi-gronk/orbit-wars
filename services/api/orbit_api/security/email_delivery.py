"""Verification-email delivery with a deliberately small provider boundary."""

from typing import Literal

import httpx
from orbit_api.security.auth_settings import AuthSettings


class EmailDeliveryError(RuntimeError):
    pass


def send_verification_email(
    settings: AuthSettings,
    *,
    email: str,
    code: str,
    purpose: Literal["register", "password_reset"],
    locale: Literal["zh", "en"],
) -> None:
    if settings.debug_codes:
        return

    if locale == "zh":
        subject = "Orbit Wars 验证码"
        action = "完成注册" if purpose == "register" else "重置密码"
        text = f"你的 Orbit Wars 验证码是 {code}，用于{action}。验证码 10 分钟内有效。"
    else:
        subject = "Your Orbit Wars verification code"
        action = "finish registration" if purpose == "register" else "reset your password"
        text = f"Your Orbit Wars code is {code}. Use it to {action}. It expires in 10 minutes."

    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": [email],
                "subject": subject,
                "text": text,
            },
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise EmailDeliveryError("verification email could not be sent") from error
