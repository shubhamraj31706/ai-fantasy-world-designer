import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional


def _now_ms() -> int:
    return int(time.time() * 1000)


def _safe_read_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"worlds": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # If file is corrupted, do not crash the app; start fresh.
        return {"worlds": []}


def _safe_write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


class WorldStore:
    """
    Tiny JSON-file persistence for demo/academic evaluation.

    For production at scale, replace with a database (Postgres, etc).
    """

    def __init__(self, storage_path: str):
        self.storage_path = storage_path

    def list_worlds(self) -> List[Dict[str, Any]]:
        data = _safe_read_json(self.storage_path)
        worlds = data.get("worlds", [])
        # newest first
        worlds.sort(key=lambda w: w.get("updated_at_ms", 0), reverse=True)
        return worlds

    def get_world(self, world_id: str) -> Optional[Dict[str, Any]]:
        for w in self.list_worlds():
            if w.get("id") == world_id:
                return w
        return None

    def upsert_world(self, title: str, world: Dict[str, Any], existing_id: Optional[str] = None) -> Dict[str, Any]:
        data = _safe_read_json(self.storage_path)
        worlds: List[Dict[str, Any]] = data.get("worlds", [])

        world_id = existing_id or str(uuid.uuid4())
        now = _now_ms()

        record = {
            "id": world_id,
            "title": title.strip() or (world.get("world_name") or "Untitled World"),
            "world": world,
            "updated_at_ms": now,
            "created_at_ms": now,
        }

        replaced = False
        for i, w in enumerate(worlds):
            if w.get("id") == world_id:
                record["created_at_ms"] = w.get("created_at_ms", now)
                worlds[i] = record
                replaced = True
                break

        if not replaced:
            worlds.append(record)

        data["worlds"] = worlds
        _safe_write_json(self.storage_path, data)
        return record

    def delete_world(self, world_id: str) -> bool:
        data = _safe_read_json(self.storage_path)
        worlds: List[Dict[str, Any]] = data.get("worlds", [])
        initial_count = len(worlds)
        
        # Filter out the world with the matching ID
        data["worlds"] = [w for w in worlds if w.get("id") != world_id]
        
        # If the list shrank, it means we successfully deleted it
        if len(data["worlds"]) < initial_count:
            _safe_write_json(self.storage_path, data)
            return True
            
        return False
