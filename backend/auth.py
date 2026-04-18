"""
auth.py — Real Google & GitHub OAuth for AI Fantasy World Designer
Registered as a Blueprint in app.py via init_oauth() + app.register_blueprint(auth_bp).
"""

import os
from flask import Blueprint, redirect, session, jsonify
from authlib.integrations.flask_client import OAuth

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
oauth = OAuth()


def init_oauth(app):
    """Call once in app.py AFTER secret_key and Session(app) are configured."""
    oauth.init_app(app)

    oauth.register(
        name="google",
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile",
            "prompt": "select_account",
        },
    )

    oauth.register(
        name="github",
        client_id=os.environ.get("GITHUB_CLIENT_ID"),
        client_secret=os.environ.get("GITHUB_CLIENT_SECRET"),
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user user:email"},
    )


def _save_user_to_session(name, email, picture, provider):
    """Unified session format shared by OAuth and password login."""
    session["user"] = {
        "name": name,
        "email": email,
        "picture": picture,
        "provider": provider,
        "logged_in": True,
    }


def _oauth_base_url() -> str:
    return os.environ.get("OAUTH_REDIRECT_BASE_URL", "http://localhost:5000").rstrip("/")


# ── Google ────────────────────────────────────────────────────────────────────

@auth_bp.route("/google")
def google_login():
    redirect_uri = f"{_oauth_base_url()}/auth/google/callback"
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/google/callback")
def google_callback():
    token = oauth.google.authorize_access_token()
    user_info = token.get("userinfo") or oauth.google.userinfo()
    _save_user_to_session(
        name=user_info.get("name") or user_info.get("email", "Adventurer"),
        email=user_info.get("email"),
        picture=user_info.get("picture"),
        provider="google",
    )
    return redirect("/")


# ── GitHub ────────────────────────────────────────────────────────────────────

@auth_bp.route("/github")
def github_login():
    redirect_uri = f"{_oauth_base_url()}/auth/github/callback"
    return oauth.github.authorize_redirect(redirect_uri)


@auth_bp.route("/github/callback")
def github_callback():
    token = oauth.github.authorize_access_token()
    resp = oauth.github.get("user", token=token)
    user_info = resp.json()

    email = user_info.get("email")
    if not email:
        emails_resp = oauth.github.get("user/emails", token=token)
        emails = emails_resp.json()
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


# ── User state & logout ───────────────────────────────────────────────────────

@auth_bp.route("/user")
def current_user():
    """
    Frontend calls this on every page load to check login state.
    Works for both OAuth users (session["user"]) and password users
    (session["user"] is also set by _log_in_user in app.py).
    """
    user = session.get("user")
    if user and user.get("logged_in"):
        return jsonify({"logged_in": True, "user": user})
    return jsonify({"logged_in": False, "user": None})


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """Clears all session auth keys and redirects home."""
    session.pop("user", None)
    session.pop("user_id", None)
    return redirect("/")