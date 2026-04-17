"""
auth.py — Google & GitHub OAuth for AI Fantasy World Designer
Drop this file into backend/ and register the blueprint in app.py.
"""

import os
from flask import Blueprint, redirect, url_for, session, jsonify, request
from authlib.integrations.flask_client import OAuth

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# ── OAuth instance (attached to app in init_oauth) ─────────────────────────
oauth = OAuth()


def init_oauth(app):
    """Call this once in app.py after creating the Flask app."""
    oauth.init_app(app)

    # ── Google ──────────────────────────────────────────────────────────────
    oauth.register(
        name="google",
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        # OpenID-Connect discovery doc – handles all endpoint URLs automatically
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile",
            "prompt": "select_account",  # always show account chooser
        },
    )

    # ── GitHub ──────────────────────────────────────────────────────────────
    oauth.register(
        name="github",
        client_id=os.environ.get("GITHUB_CLIENT_ID"),
        client_secret=os.environ.get("GITHUB_CLIENT_SECRET"),
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user user:email"},
    )


# ── Helpers ─────────────────────────────────────────────────────────────────


def _save_user_to_session(
    name: str, email: str | None, picture: str | None, provider: str
):
    session["user"] = {
        "name": name,
        "email": email,
        "picture": picture,
        "provider": provider,
        "logged_in": True,
    }


def _oauth_base_url() -> str:
    return os.environ.get("OAUTH_REDIRECT_BASE_URL", "http://localhost:5000").rstrip(
        "/"
    )


# ── Google routes ────────────────────────────────────────────────────────────


@auth_bp.route("/google")
def google_login():
    redirect_uri = f"{_oauth_base_url()}/auth/google/callback"
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/google/callback")
def google_callback():
    token = oauth.google.authorize_access_token()
    user_info = token.get("userinfo")  # included automatically via OIDC
    if not user_info:
        # Fallback: fetch from userinfo endpoint
        user_info = oauth.google.userinfo()

    _save_user_to_session(
        name=user_info.get("name") or user_info.get("email", "Adventurer"),
        email=user_info.get("email"),
        picture=user_info.get("picture"),
        provider="google",
    )
    return redirect("/")


# ── GitHub routes ─────────────────────────────────────────────────────────────


@auth_bp.route("/github")
def github_login():
    redirect_uri = f"{_oauth_base_url()}/auth/github/callback"
    return oauth.github.authorize_redirect(redirect_uri)


@auth_bp.route("/github/callback")
def github_callback():
    token = oauth.github.authorize_access_token()

    # Basic profile
    resp = oauth.github.get("user", token=token)
    user_info = resp.json()

    # GitHub doesn't always expose email in the profile; fetch it separately
    email = user_info.get("email")
    if not email:
        emails_resp = oauth.github.get("user/emails", token=token)
        emails = emails_resp.json()
        # Pick the primary verified address
        email = next(
            (e["email"] for e in emails if e.get("primary") and e.get("verified")),
            None,
        )

    _save_user_to_session(
        name=user_info.get("name") or user_info.get("login", "Adventurer"),
        email=email,
        picture=user_info.get("avatar_url"),
        provider="github",
    )
    return redirect("/")


# ── Session / logout ──────────────────────────────────────────────────────────


@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    return redirect("/")


@auth_bp.route("/user")
def current_user():
    """
    Frontend polls this to check login state.
    Returns: { logged_in: bool, user?: { name, email, picture, provider } }
    """
    user = session.get("user")
    if user:
        return jsonify({"logged_in": True, "user": user})
    return jsonify({"logged_in": False})
