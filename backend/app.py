import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    request,
    redirect,
    url_for,
    send_from_directory,
    session,
)
from flask_session import Session
from google import genai
from google.genai import types
from auth import auth_bp, init_oauth
from user_store import UserStore
from world_store import WorldStore


# ============================================================
# AI Fantasy World Designer (Flask Backend)
# ============================================================
# DATA FLOW (for viva):
# 1) User types prompt in Frontend (browser)
# 2) Frontend JS sends HTTP request to Flask backend: /api/generate-world or /api/chat
# 3) Backend calls Gemini API with a domain-restricted system prompt
# 4) Gemini returns generated content
# 5) Backend returns JSON response to Frontend
# 6) Frontend renders world cards + chat messages
# ============================================================


load_dotenv()


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=os.path.join(os.path.dirname(__file__), "..", "frontend"),
        static_url_path="",
    )
    init_oauth(app)
    app.register_blueprint(auth_bp)

    # Secret key is required for sessions (memory). In production keep it secret.
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_only_change_me")

    # Server-side session so chat history can be stored safely (cookie has size limits).
    app.config["SESSION_TYPE"] = "filesystem"
    app.config["SESSION_FILE_DIR"] = os.path.join(
        os.path.dirname(__file__), ".flask_session"
    )
    app.config["SESSION_PERMANENT"] = False
    Session(app)

    storage_path = os.path.join(os.path.dirname(__file__), "storage", "worlds.json")
    store = WorldStore(storage_path=storage_path)

    user_storage_path = os.path.join(os.path.dirname(__file__), "storage", "users.json")
    users = UserStore(storage_path=user_storage_path)

    gemini_model = (
        os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    )
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()

    # Model configuration (for viva):
    # - temperature=0.7 gives balanced creativity (not too random, not too rigid).
    # - top_p=0.9 keeps diversity while avoiding very low-probability noise.
    MODEL_TEMPERATURE = 0.7
    MODEL_TOP_P = 0.9

    DOMAIN_SYSTEM_PROMPT = (
        "You are a fantasy world-building expert. Only generate fictional, creative, and immersive content. "
        "Stay strictly within the fantasy domain (world-building, lore, creatures, magic, kingdoms, myths). "
        "If the user asks for non-fantasy topics (real politics, medical advice, coding, etc), refuse briefly "
        "and redirect back to fantasy storytelling."
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
- Make each bullet concise but vivid.
- Provide 4-7 items per list.
- Provide 3-6 creatures.
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

    def _get_gemini_client() -> genai.Client:
        """
        Create the client lazily so the server can start without a key.
        This helps demos: the UI loads even if GEMINI_API_KEY isn't set yet.
        """
        nonlocal gemini_api_key
        if not gemini_api_key:
            # Re-read in case the process environment was updated.
            gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Create a .env file (see .env.example) and restart the server."
            )
        return genai.Client(api_key=gemini_api_key)

    def _session_chat() -> List[Dict[str, str]]:
        chat = session.get("chat_history")
        if not isinstance(chat, list):
            chat = []
        return chat

    def _set_session_chat(chat: List[Dict[str, str]]) -> None:
        # Keep last N messages for memory.
        session["chat_history"] = chat[-20:]

    def _current_world() -> Dict[str, Any] | None:
        w = session.get("world")
        if isinstance(w, dict):
            return w
        return None

    def _set_current_world(world: Dict[str, Any]) -> None:
        session["world"] = world

    def _current_user() -> Dict[str, Any] | None:
        user_id = session.get("user_id")
        if not isinstance(user_id, str):
            return None
        return users.get_user_by_id(user_id)

    def _log_in_user(user: Dict[str, Any]) -> None:
        session["user_id"] = user.get("id")

    def _log_out_user() -> None:
        session.pop("user_id", None)

    @app.get("/api/auth/me")
    def auth_me() -> Any:
        user = _current_user()
        return jsonify(
            {"user": {"id": user["id"], "email": user["email"]} if user else None}
        )

    @app.post("/api/auth/signup")
    def auth_signup() -> Any:
        body = request.get_json(silent=True) or {}
        email = str(body.get("email") or "").strip()
        password = str(body.get("password") or "")
        if not email or not password:
            return jsonify({"error": "Missing email or password."}), 400
        if "@" not in email or len(password) < 6:
            return jsonify(
                {
                    "error": "Enter a valid email and a password with at least 6 characters."
                }
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

    @app.get("/auth/user")
    def auth_user() -> Any:
        user = _current_user()
        return jsonify(
            {
                "logged_in": bool(user),
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "name": user.get("name") or user["email"],
                    "picture": user.get("picture"),
                }
                if user
                else None,
            }
        )

    @app.get("/auth/logout")
    def web_logout() -> Any:
        _log_out_user()
        return redirect(url_for("index"))

    @app.route("/auth/<provider>", methods=["GET", "POST"])
    def auth_provider(provider: str) -> Any:
        supported = {"google", "github"}
        provider_key = provider.lower()
        if provider_key not in supported:
            return "Unsupported provider", 404

        if request.method == "POST":
            email = str(request.form.get("email") or "").strip()
            if not email:
                return "Email is required.", 400

            user = users.create_social_user(provider=provider_key, email=email)
            _log_in_user(user)
            return redirect(url_for("index"))

        label = "Google" if provider_key == "google" else "GitHub"
        return f"""
            <!doctype html>
            <html lang="en">
            <head>
              <meta charset="utf-8">
              <title>Continue with {label}</title>
              <style>
                body {{font-family: system-ui, sans-serif; background:#0d0b14; color:#f5f3ff; display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0;}}
                .page {{width:min(520px,94vw); background:rgba(15,12,25,.96); border:1px solid rgba(168,85,247,.24); border-radius:20px; padding:28px; box-shadow:0 20px 60px rgba(0,0,0,.45);}}
                input, button {{width:100%; padding:14px 16px; margin-top:12px; border-radius:12px; border:1px solid rgba(255,255,255,.12); background:rgba(255,255,255,.06); color:#f7f1ff;}}
                button {{background:#8b5cf6; border:none; color:#fff; cursor:pointer; font-weight:700;}}
                a {{color:#a78bfa; text-decoration:none; display:inline-block; margin-top:18px;}}
              </style>
            </head>
            <body>
              <div class="page">
                <h1>Continue with {label}</h1>
                <p>Enter your email to continue with {label} authentication.</p>
                <form method="post">
                  <label for="email">Email</label>
                  <input id="email" name="email" type="email" required placeholder="you@example.com" />
                  <button type="submit">Continue</button>
                </form>
                <a href="/">Back to site</a>
              </div>
            </body>
            </html>
        """

    @app.post("/api/auth/oauth/<provider>")
    def auth_oauth(provider: str) -> Any:
        supported = {"google", "github"}
        if provider.lower() not in supported:
            return jsonify({"error": "Social login provider is not supported."}), 400

        body = request.get_json(silent=True) or {}
        email = str(body.get("email") or "").strip()
        if not email:
            return jsonify({"error": "Email is required for social login."}), 400

        try:
            user = users.create_social_user(provider=provider.lower(), email=email)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        _log_in_user(user)
        return jsonify({"user": {"id": user["id"], "email": user["email"]}})

    @app.get("/health")
    def health() -> Any:
        """Simple health check for demos/deployments."""
        return jsonify({"ok": True})

    @app.get("/")
    def index() -> Any:
        """Serve the frontend entrypoint."""
        # Serve the frontend SPA entrypoint
        return send_from_directory(app.static_folder, "index.html")

    @app.post("/api/generate-world")
    def generate_world() -> Any:
        """
        Generate a new fantasy world (structured JSON).
        Frontend calls this first with the user's world idea.
        """
        body = request.get_json(silent=True) or {}
        idea = str(body.get("idea") or "").strip()
        if not idea:
            return jsonify({"error": "Missing 'idea'"}), 400

        try:
            import json

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
            return jsonify({"error": "AI generation failed", "details": str(e)}), 500

        # Initialize chat memory for this world.
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

    def _world_to_context(world: Dict[str, Any]) -> str:
        # Compact world context for the model, used as a system message.
        # (Keeps the chatbot consistent and domain-specific.)
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
        """
        Lore chatbot endpoint.
        Uses session memory: (system prompt + world context + last N turns).
        """
        body = request.get_json(silent=True) or {}
        message = str(body.get("message") or "").strip()
        if not message:
            return jsonify({"error": "Missing 'message'"}), 400

        world = _current_world()
        if not world:
            return jsonify(
                {"error": "No world in session. Generate a world first."}
            ), 400

        chat_history = _session_chat()
        if not chat_history:
            chat_history = [
                {"role": "system", "content": DOMAIN_SYSTEM_PROMPT},
                {
                    "role": "system",
                    "content": "WORLD_CONTEXT:\n" + _world_to_context(world),
                },
            ]

        chat_history.append({"role": "user", "content": message})

        try:
            client = _get_gemini_client()

            transcript_lines: List[str] = []
            # Keep the order and roles explicit so the model stays consistent.
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
                "- If asked for non-fantasy topics, refuse briefly and redirect.\n\n"
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

    @app.get("/api/worlds")
    def list_worlds() -> Any:
        """List saved worlds from JSON storage."""
        return jsonify({"worlds": store.list_worlds()})

    @app.post("/api/worlds/save")
    def save_world() -> Any:
        """Persist the current session world into JSON storage."""
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
        """Load a saved world into the current session (restores chat context)."""
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
        """Download a saved world as a plain text file."""
        record = store.get_world(world_id)
        if not record:
            return jsonify({"error": "World not found"}), 404

        world = record.get("world") or {}
        title = record.get("title") or (world.get("world_name") or "World")
        text = world_to_pretty_text(title=title, world=world)

        from flask import Response

        filename = f"{title}".replace(" ", "_").replace("/", "_")
        return Response(
            text,
            mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}.txt"'},
        )

    def world_to_pretty_text(title: str, world: Dict[str, Any]) -> str:
        def section(h: str, items: Any) -> str:
            if isinstance(items, list):
                lines = "\n".join([f"- {str(x)}" for x in items])
                return f"{h}\n{lines}\n"
            return f"{h}\n- {str(items)}\n"

        out = []
        out.append(f"{title}\n" + "=" * len(title) + "\n")
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

    # SPA fallback for any unknown route (keeps refresh working)
    @app.errorhandler(404)
    def not_found(e: Exception) -> Any:
        path = request.path.lstrip("/")
        if path.startswith("api/") or path == "health":
            return jsonify({"error": "Not found"}), 404
        return send_from_directory(app.static_folder, "index.html")

    return app


app = create_app()


if __name__ == "__main__":
    # Dev server
    app.run(host="0.0.0.0", port=5000, debug=True)
