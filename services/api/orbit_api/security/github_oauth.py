"""GitHub OAuth exchange and normalized identity projection."""

from dataclasses import dataclass

import httpx
from orbit_api.security.auth_settings import AuthSettings


class GitHubOAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubProfile:
    subject: str
    display_name: str
    email: str | None
    avatar_url: str | None


def exchange_github_code(settings: AuthSettings, code: str) -> GitHubProfile:
    try:
        token_response = httpx.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            json={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            },
            timeout=10,
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise GitHubOAuthError("GitHub did not return an access token")

        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {access_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        profile_response = httpx.get("https://api.github.com/user", headers=headers, timeout=10)
        profile_response.raise_for_status()
        profile = profile_response.json()
        provider_id = profile.get("id")
        login = profile.get("login")
        if not isinstance(provider_id, int) or not isinstance(login, str) or not login:
            raise GitHubOAuthError("GitHub profile is incomplete")

        email = profile.get("email") if isinstance(profile.get("email"), str) else None
        if email is None:
            email_response = httpx.get(
                "https://api.github.com/user/emails", headers=headers, timeout=10
            )
            email_response.raise_for_status()
            candidates = email_response.json()
            if isinstance(candidates, list):
                verified = [
                    item
                    for item in candidates
                    if isinstance(item, dict)
                    and item.get("verified") is True
                    and isinstance(item.get("email"), str)
                ]
                primary = next((item for item in verified if item.get("primary") is True), None)
                selected = primary or (verified[0] if verified else None)
                email = selected["email"] if selected is not None else None

        name = profile.get("name")
        avatar_url = profile.get("avatar_url")
        return GitHubProfile(
            subject=str(provider_id),
            display_name=name.strip() if isinstance(name, str) and name.strip() else login,
            email=email,
            avatar_url=avatar_url if isinstance(avatar_url, str) else None,
        )
    except (httpx.HTTPError, ValueError) as error:
        raise GitHubOAuthError("GitHub OAuth request failed") from error
