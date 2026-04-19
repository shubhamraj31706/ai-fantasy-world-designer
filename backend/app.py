import json
import os

import base64
import urllib.parse
from typing import Any, Dict, List

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_session import Session
from google import genai
from google.genai import types

from auth import auth_bp, init_oauth
from user_store import UserStore
from world_store import WorldStore


load_dotenv()


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=os.path.join(os.path.dirname(__file__), "..", "frontend"),
        static_url_path="",
    )

    # ── Config MUST come before Session(app) and init_oauth ──────────────────
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_only_change_me")

    # Filesystem sessions — survive Flask reloader restarts.
    # The OAuth state (stored when user clicks Login) must still be there
    # when Google redirects back seconds later. In-memory (cachelib/SimpleCache)
    # gets wiped when Flask's debug reloader restarts the process mid-flow.
    # Filesystem writes to disk instantly, so the state survives any restart.
    _sess_dir = os.path.join(os.path.dirname(__file__), ".flask_session")
    os.makedirs(_sess_dir, exist_ok=True)
    app.config["SESSION_TYPE"] = "filesystem"
    app.config["SESSION_FILE_DIR"] = _sess_dir
    app.config["SESSION_FILE_THRESHOLD"] = 500
    app.config["SESSION_PERMANENT"] = True
    app.config["PERMANENT_SESSION_LIFETIME"] = 3600
    # Lax: browser must send the cookie on the Google/GitHub redirect-back
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SECURE"] = False   # False = http://localhost is fine
    Session(app)

    # ── OAuth + auth blueprint (registered after config is ready) ─────────────
    init_oauth(app)
    app.register_blueprint(auth_bp)  # mounts /auth/* routes from auth.py

    # ── Storage ───────────────────────────────────────────────────────────────
    storage_path = os.path.join(os.path.dirname(__file__), "storage", "worlds.json")
    store = WorldStore(storage_path=storage_path)

    user_storage_path = os.path.join(
        os.path.dirname(__file__), "storage", "users.json"
    )
    users = UserStore(storage_path=user_storage_path)

    # ── AI config ─────────────────────────────────────────────────────────────
    gemini_model = (
        os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    )
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()

    MODEL_TEMPERATURE = 0.7
    MODEL_TOP_P = 0.9

    DOMAIN_SYSTEM_PROMPT = (
        "You are a fantasy world-building expert. Only generate fictional, creative, "
        "and immersive content. Stay strictly within the fantasy domain (world-building, "
        "lore, creatures, magic, kingdoms, myths). If the user asks for non-fantasy topics "
        "(real politics, medical advice, coding, etc), refuse briefly and redirect back to "
        "fantasy storytelling.\n\n"
        "CRITICAL RULES FOR LANGUAGE AND TONE:\n"
        "1. Use very simple, everyday language. Avoid complex, heavy, or difficult dictionary words (e.g., do not use words like 'ethereal', 'cataclysmic', 'abyssal'). Write in a clear, basic way so that anyone can easily understand.\n"
        "2. MULTILINGUAL SUPPORT: You must reply in the EXACT SAME LANGUAGE the user uses in their prompt. If the user writes in Hindi, Hinglish, Bengali, Tamil, or any other language, you must generate the entire world lore in that exact language while keeping the vocabulary basic."
    )

    WORLD_SCHEMA_INSTRUCTIONS = """
Return a SINGLE valid JSON object ONLY (no markdown) with this exact shape:
{
  "world_name": "string",
  "geography": ["bullet string", "..."],
  "history": ["bullet string", "..."],
  "creatures": [{"name":"string","description":"string"}],
  "magic_system": ["bullet string", "..."],
  "plot_hooks": ["bullet string", "..."],
  "tone_tags": ["dark","mystical", "..."]
}
Constraints:
- Keep it fantasy-only.
- Make each bullet concise, using VERY SIMPLE and basic words.
- Provide 4-7 items per list.
- Provide 3-6 creatures.
- IMPORTANT: The text values inside the JSON must be generated in the SAME LANGUAGE as the user's prompt.
"""

    WORLD_JSON_SCHEMA: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "world_name": {"type": "string"},
            "geography": {"type": "array", "items": {"type": "string"}},
            "history": {"type": "array", "items": {"type": "string"}},
            "creatures": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["name", "description"],
                },
            },
            "magic_system": {"type": "array", "items": {"type": "string"}},
            "plot_hooks": {"type": "array", "items": {"type": "string"}},
            "tone_tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "world_name",
            "geography",
            "history",
            "creatures",
            "magic_system",
            "plot_hooks",
            "tone_tags",
        ],
        "additionalProperties": True,
    }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_gemini_client() -> genai.Client:
        nonlocal gemini_api_key
        if not gemini_api_key:
            gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Create a .env file (see .env.example) and restart."
            )
        return genai.Client(api_key=gemini_api_key)

    def _session_chat() -> List[Dict[str, str]]:
        chat = session.get("chat_history")
        return chat if isinstance(chat, list) else []

    def _set_session_chat(chat: List[Dict[str, str]]) -> None:
        session["chat_history"] = chat[-20:]

    def _current_world() -> Dict[str, Any] | None:
        w = session.get("world")
        return w if isinstance(w, dict) else None

    def _set_current_world(world: Dict[str, Any]) -> None:
        session["world"] = world

    def _current_user() -> Dict[str, Any] | None:
        """
        Unified user lookup.
        - OAuth login  → stored in session["user"] (dict with name/email/picture/provider)
        - Password login → stored in session["user_id"] (looked up from UserStore)
        Returns a normalised dict or None.
        """
        # Check OAuth session first
        oauth_user = session.get("user")
        if isinstance(oauth_user, dict) and oauth_user.get("logged_in"):
            return oauth_user

        # Check password session
        user_id = session.get("user_id")
        if isinstance(user_id, str):
            db_user = users.get_user_by_id(user_id)
            if db_user:
                return {
                    "id": db_user["id"],
                    "email": db_user["email"],
                    "name": db_user.get("name") or db_user["email"],
                    "picture": None,
                    "provider": db_user.get("provider", "password"),
                    "logged_in": True,
                }
        return None

    def _log_in_user(user: Dict[str, Any]) -> None:
        """Store password-login user in session (same normalised format as OAuth)."""
        session["user_id"] = user.get("id")
        # Also write to session["user"] so the frontend's /auth/user check works
        session["user"] = {
            "id": user.get("id"),
            "email": user.get("email"),
            "name": user.get("name") or user.get("email"),
            "picture": None,
            "provider": user.get("provider", "password"),
            "logged_in": True,
        }

    def _log_out_user() -> None:
        session.pop("user_id", None)
        session.pop("user", None)

    # ── Auth API endpoints (password-based) ───────────────────────────────────
    # NOTE: /auth/* routes are handled by auth_bp (real OAuth).
    #       These /api/auth/* routes are for email+password auth only.

    @app.get("/api/auth/me")
    def auth_me() -> Any:
        user = _current_user()
        if user:
            return jsonify({
                "logged_in": True,
                "user": {
                    "id": user.get("id"),
                    "email": user.get("email"),
                    "name": user.get("name"),
                    "picture": user.get("picture"),
                    "provider": user.get("provider"),
                },
            })
        return jsonify({"logged_in": False, "user": None})

    @app.post("/api/auth/signup")
    def auth_signup() -> Any:
        body = request.get_json(silent=True) or {}
        email = str(body.get("email") or "").strip()
        password = str(body.get("password") or "")
        if not email or not password:
            return jsonify({"error": "Missing email or password."}), 400
        if "@" not in email or len(password) < 6:
            return jsonify(
                {"error": "Enter a valid email and a password with at least 6 characters."}
            ), 400
        try:
            user = users.create_user(email=email, password=password)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 409
        _log_in_user(user)
        return jsonify({"user": {"id": user["id"], "email": user["email"]}})

    @app.post("/api/auth/login")
    def auth_login() -> Any:
        body = request.get_json(silent=True) or {}
        email = str(body.get("email") or "").strip()
        password = str(body.get("password") or "")
        if not email or not password:
            return jsonify({"error": "Missing email or password."}), 400
        user = users.authenticate(email=email, password=password)
        if not user:
            return jsonify({"error": "Invalid email or password."}), 401
        _log_in_user(user)
        return jsonify({"user": {"id": user["id"], "email": user["email"]}})

    @app.post("/api/auth/logout")
    def auth_logout() -> Any:
        _log_out_user()
        return jsonify({"ok": True})

    # ── Health ────────────────────────────────────────────────────────────────

    @app.get("/health")
    def health() -> Any:
        return jsonify({"ok": True})

    # ── Frontend ──────────────────────────────────────────────────────────────

    @app.get("/")
    def index() -> Any:
        return send_from_directory(app.static_folder, "index.html")

    # ── World generation ──────────────────────────────────────────────────────

    @app.post("/api/generate-world")
    def generate_world() -> Any:
        body = request.get_json(silent=True) or {}
        idea = str(body.get("idea") or "").strip()
        if not idea:
            return jsonify({"error": "Missing 'idea'"}), 400

        try:
            client = _get_gemini_client()
            prompt = (
                f"{DOMAIN_SYSTEM_PROMPT}\n\n"
                "Task: Generate a complete fantasy world blueprint.\n"
                f"{WORLD_SCHEMA_INSTRUCTIONS}\n\n"
                f"World idea: {idea}"
            )
            resp = client.models.generate_content(
                model=gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=MODEL_TEMPERATURE,
                    top_p=MODEL_TOP_P,
                    response_mime_type="application/json",
                    response_json_schema=WORLD_JSON_SCHEMA,
                ),
            )
            content = (resp.text or "").strip() or "{}"
            world = json.loads(content)
        except Exception as e:
            # THIS PRINTS THE EXACT REASON IT FAILED IN YOUR TERMINAL
            print(f"\n❌ WORLD GENERATION ERROR: {str(e)}\n")
            return jsonify({"error": "AI generation failed", "details": str(e)}), 500

        _set_current_world(world)
        _set_session_chat(
            [
                {
                    "role": "system",
                    "content": DOMAIN_SYSTEM_PROMPT
                    + "\nYou are now chatting inside a specific fantasy world context. Be consistent.",
                },
                {
                    "role": "system",
                    "content": "WORLD_CONTEXT:\n" + _world_to_context(world),
                },
                {
                    "role": "assistant",
                    "content": "World created. Ask me anything about it (lore, characters, factions, quests).",
                },
            ]
        )
        return jsonify({"world": world})

    # ── Chat ──────────────────────────────────────────────────────────────────

    def _world_to_context(world: Dict[str, Any]) -> str:
        parts: List[str] = []
        parts.append(f"World Name: {world.get('world_name', '')}")
        for k in ["geography", "history", "magic_system", "plot_hooks", "tone_tags"]:
            v = world.get(k)
            if isinstance(v, list):
                parts.append(f"{k}: " + "; ".join(str(x) for x in v[:8]))
        creatures = world.get("creatures")
        if isinstance(creatures, list):
            compact = []
            for c in creatures[:8]:
                if isinstance(c, dict):
                    compact.append(f"{c.get('name', '')}: {c.get('description', '')}")
            parts.append("creatures: " + " | ".join(compact))
        return "\n".join([p for p in parts if p.strip()])

    @app.post("/api/chat")
    def chat() -> Any:
        body = request.get_json(silent=True) or {}
        message = str(body.get("message") or "").strip()
        if not message:
            return jsonify({"error": "Missing 'message'"}), 400

        world = _current_world()
        if not world:
            return jsonify({"error": "No world in session. Generate a world first."}), 400

        chat_history = _session_chat()
        if not chat_history:
            chat_history = [
                {"role": "system", "content": DOMAIN_SYSTEM_PROMPT},
                {"role": "system", "content": "WORLD_CONTEXT:\n" + _world_to_context(world)},
            ]

        chat_history.append({"role": "user", "content": message})

        try:
            client = _get_gemini_client()
            transcript_lines: List[str] = []
            for m in chat_history[-20:]:
                role = str(m.get("role") or "").lower()
                content = str(m.get("content") or "").strip()
                if not content:
                    continue
                if role == "system":
                    transcript_lines.append(f"[SYSTEM]\n{content}\n")
                elif role == "user":
                    transcript_lines.append(f"[USER]\n{content}\n")
                else:
                    transcript_lines.append(f"[ASSISTANT]\n{content}\n")

            prompt = (
                "You are the assistant in a fantasy-only lore chat.\n"
                "Rules:\n"
                "- Stay strictly in fantasy world-building.\n"
                "- Use the WORLD_CONTEXT and prior chat turns for consistency.\n"
                "- If asked for non-fantasy topics, refuse briefly and redirect.\n"
                "- Speak in VERY SIMPLE, easy-to-understand language. No complex vocabulary.\n"
                "- ALWAYS reply in the exact same language the user is speaking in right now.\n\n"
                + "\n".join(transcript_lines)
                + "\n[ASSISTANT]\n"
            )

            resp = client.models.generate_content(
                model=gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=MODEL_TEMPERATURE,
                    top_p=MODEL_TOP_P,
                ),
            )
            assistant_text = (resp.text or "").strip()
        except Exception as e:
            return jsonify({"error": "Chat failed", "details": str(e)}), 500

        chat_history.append({"role": "assistant", "content": assistant_text})
        _set_session_chat(chat_history)
        return jsonify({"reply": assistant_text})

    @app.post("/api/generate-image")
    def generate_image() -> Any:
        body = request.get_json(silent=True) or {}
        name = str(body.get("name") or "").strip()
        description = str(body.get("description") or "").strip()

        if not name or not description:
            return jsonify({"error": "Missing name or description"}), 400

        try:
            # We create a prompt just like before
            prompt = f"Fantasy concept art of a creature named {name}. Description: {description}. Style: digital painting, high fantasy, detailed."
            
            # URL-encode the prompt so it's safe for a web link
            encoded_prompt = urllib.parse.quote(prompt)
            
            # Pollinations.ai generates images just by visiting a URL!
            # We add an arbitrary seed so it generates a new image each time
            import random
            seed = random.randint(1, 100000)
            image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&seed={seed}&nologo=true"
            
            # Instead of downloading base64 bytes, we just send the URL directly to your frontend
            return jsonify({"image_url": image_url})

        except Exception as e:
            print(f"\n❌ IMAGE GENERATION ERROR: {str(e)}\n") 
            return jsonify({"error": "Image generation failed", "details": str(e)}), 500


    # ── World persistence ─────────────────────────────────────────────────────

    @app.get("/api/worlds")
    def list_worlds() -> Any:
        return jsonify({"worlds": store.list_worlds()})

    @app.post("/api/worlds/save")
    def save_world() -> Any:
        world = _current_world()
        if not world:
            return jsonify({"error": "No world in session to save."}), 400
        body = request.get_json(silent=True) or {}
        title = str(body.get("title") or "").strip()
        existing_id = body.get("id")
        existing_id = str(existing_id).strip() if existing_id else None
        record = store.upsert_world(title=title, world=world, existing_id=existing_id)
        session["saved_world_id"] = record["id"]
        return jsonify({"saved": record})

    @app.post("/api/worlds/load")
    def load_world() -> Any:
        body = request.get_json(silent=True) or {}
        world_id = str(body.get("id") or "").strip()
        if not world_id:
            return jsonify({"error": "Missing 'id'"}), 400
        record = store.get_world(world_id)
        if not record:
            return jsonify({"error": "World not found"}), 404
        world = record.get("world") or {}
        _set_current_world(world)
        _set_session_chat(
            [
                {
                    "role": "system",
                    "content": DOMAIN_SYSTEM_PROMPT
                    + "\nYou are now chatting inside a specific fantasy world context. Be consistent.",
                },
                {
                    "role": "system",
                    "content": "WORLD_CONTEXT:\n" + _world_to_context(world),
                },
                {
                    "role": "assistant",
                    "content": f"Loaded world '{world.get('world_name', '')}'. Ask me anything about it.",
                },
            ]
        )
        session["saved_world_id"] = record["id"]
        return jsonify(
            {"world": world, "meta": {"id": record["id"], "title": record.get("title")}}
        )

    @app.get("/api/worlds/download/<world_id>.txt")
    def download_world_txt(world_id: str) -> Any:
        record = store.get_world(world_id)
        if not record:
            return jsonify({"error": "World not found"}), 404
        world = record.get("world") or {}
        title = record.get("title") or (world.get("world_name") or "World")
        text = _world_to_pretty_text(title=title, world=world)
        
        # FIX: HTTP headers strictly require ASCII characters. If 'title' contains 
        # non-English characters (like Hindi), the server crashes.
        # Since our JavaScript frontend (a.download) dictates the final filename 
        # anyway, we pass a safe, static ASCII string here.
        return Response(
            text,
            mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="loreforge_export.txt"'},
        )

    def _world_to_pretty_text(title: str, world: Dict[str, Any]) -> str:
        def section(h: str, items: Any) -> str:
            if isinstance(items, list):
                lines = "\n".join([f"- {str(x)}" for x in items])
                return f"{h}\n{lines}\n"
            return f"{h}\n- {str(items)}\n"

        out = [f"{title}\n" + "=" * len(title) + "\n"]
        out.append(f"World Name: {world.get('world_name', '')}\n")
        out.append(section("Geography", world.get("geography", [])))
        out.append(section("History", world.get("history", [])))
        creatures = world.get("creatures", [])
        if isinstance(creatures, list):
            out.append("Creatures\n---------\n")
            for c in creatures:
                if isinstance(c, dict):
                    out.append(f"- {c.get('name', '')}: {c.get('description', '')}\n")
            out.append("\n")
        out.append(section("Magic System", world.get("magic_system", [])))
        out.append(section("Plot Hooks", world.get("plot_hooks", [])))
        return "".join(out).strip() + "\n"
    
    @app.post("/api/worlds/delete")
    def delete_world() -> Any:
        body = request.get_json(silent=True) or {}
        world_id = str(body.get("id") or "").strip()
        
        if not world_id:
            return jsonify({"error": "Missing 'id'"}), 400
            
        success = store.delete_world(world_id)
        if not success:
            return jsonify({"error": "World not found or already deleted."}), 404
            
        # If the user deleted the world they currently have loaded, unbind it
        if session.get("saved_world_id") == world_id:
            session.pop("saved_world_id", None)
            
        return jsonify({"ok": True})

    # ── SPA fallback ──────────────────────────────────────────────────────────

    @app.errorhandler(404)
    def not_found(e: Exception) -> Any:
        path = request.path.lstrip("/")
        if path.startswith("api/") or path == "health":
            return jsonify({"error": "Not found"}), 404
        return send_from_directory(app.static_folder, "index.html")

    return app


app = create_app()

if __name__ == "__main__":
    # use_reloader=False stops Flask from forking a child process on startup.
    # That fork was wiping the OAuth state stored in the session between
    # "redirect to Google" and "Google redirects back" → MismatchingStateError.
    # Debug error pages still work; auto-reload on file-save is disabled
    # (just restart manually with Ctrl+C → python backend\app.py).
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)