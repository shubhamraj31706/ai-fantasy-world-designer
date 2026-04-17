import json
import os
import time
import uuid
from typing import Any, Dict, Optional

from werkzeug.security import check_password_hash, generate_password_hash


def _safe_read_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"users": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"users": []}


def _safe_write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


class UserStore:
    """Simple JSON-backed user storage for signup/login demos."""

    def __init__(self, storage_path: str):
        self.storage_path = storage_path

    def _load_data(self) -> Dict[str, Any]:
        return _safe_read_json(self.storage_path)

    def _save_data(self, data: Dict[str, Any]) -> None:
        _safe_write_json(self.storage_path, data)

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        data = self._load_data()
        for user in data.get("users", []):
            if user.get("id") == user_id:
                return user
        return None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        normalized = email.strip().lower()
        data = self._load_data()
        for user in data.get("users", []):
            if user.get("email") == normalized:
                return user
        return None

    def create_user(self, email: str, password: str) -> Dict[str, Any]:
        normalized = email.strip().lower()
        if not normalized or not password:
            raise ValueError("Email and password are required.")
        if self.get_user_by_email(normalized) is not None:
            raise ValueError("A user with that email already exists.")

        now = int(time.time() * 1000)
        user = {
            "id": str(uuid.uuid4()),
            "email": normalized,
            "password_hash": generate_password_hash(password),
            "provider": "password",
            "created_at_ms": now,
        }

        data = self._load_data()
        data.setdefault("users", []).append(user)
        self._save_data(data)
        return user

    def create_social_user(self, provider: str, email: str) -> Dict[str, Any]:
        normalized = email.strip().lower()
        if not normalized:
            raise ValueError("Email is required for social login.")
        existing = self.get_user_by_email(normalized)
        if existing is not None:
            return existing

        now = int(time.time() * 1000)
        user = {
            "id": str(uuid.uuid4()),
            "email": normalized,
            "provider": provider,
            "password_hash": "",
            "created_at_ms": now,
        }

        data = self._load_data()
        data.setdefault("users", []).append(user)
        self._save_data(data)
        return user

    def authenticate(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        user = self.get_user_by_email(email)
        if user is None:
            return None
        if check_password_hash(user.get("password_hash", ""), password):
            return user
        return None
