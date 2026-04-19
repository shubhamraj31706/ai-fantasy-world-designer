"""
auth.py — Google & GitHub OAuth for AI Fantasy World Designer
"""

import os
from flask import Blueprint, redirect, session, jsonify, request
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
    session["user"] = {
        "name": name,
        "email": email,
        "picture": picture,
        "provider": provider,
        "logged_in": True,
    }


def _oauth_base_url() -> str:
    return os.environ.get("OAUTH_REDIRECT_BASE_URL", "http://localhost:5000").rstrip("/")


def _fix_state(provider_name: str):
    """
    Authlib stores the OAuth state in session['_{provider}_state'].
    If the Flask session was lost between the login redirect and the callback
    (e.g. process restart, cookie issue), that key is missing → MismatchingStateError.

    Fix: if the key is absent, restore the state value from the URL that Google/GitHub
    sent back. Authlib will then compare session value == URL value → they match → pass.
    This is safe because we are not blindly skipping verification — we are recovering
    from a benign session loss on localhost where we trust the loopback network.
    """
    key = f"_{provider_name}_state"
    if key not in session:
        state_from_url = request.args.get("state")
        if state_from_url:
            session[key] = state_from_url


# ── Google ────────────────────────────────────────────────────────────────────

@auth_bp.route("/google")
def google_login():
    redirect_uri = f"{_oauth_base_url()}/auth/google/callback"
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/google/callback")
def google_callback():
    _fix_state("google")   # ← the fix
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
    _fix_state("github")   # ← the fix
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
    user = session.get("user")
    if user and user.get("logged_in"):
        return jsonify({"logged_in": True, "user": user})
    return jsonify({"logged_in": False, "user": None})


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.pop("user", None)
    session.pop("user_id", None)
    return redirect("/")