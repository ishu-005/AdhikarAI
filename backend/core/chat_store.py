"""Conversation persistence: in-memory mirror backed by the Supabase `chats` table."""
from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from threading import Lock

from backend.core.chat_intelligence import make_chat_title
from backend.core.clients import get_supabase_client
from backend.core.logging import get_logger

logger = get_logger("chat_store")

_threads: dict[str, list[dict]] = {}
_metadata: dict[str, dict] = {}
_lock = Lock()
_DEFAULT_OWNER = "default"


def _owner_key(owner_id: str | None) -> str:
    owner = (owner_id or _DEFAULT_OWNER).strip() or _DEFAULT_OWNER
    return sha256(owner.encode("utf-8")).hexdigest()[:16]


def _owner_key_from_conversation_id(conversation_id: str) -> str:
    prefix = conversation_id.split("_", 1)[0]
    if len(prefix) == 16 and all(ch in "0123456789abcdef" for ch in prefix):
        return prefix
    return _owner_key(_DEFAULT_OWNER)


def _matches_owner(conversation_id: str, owner_id: str | None) -> bool:
    if owner_id is None:
        return True
    expected = _owner_key(owner_id)
    actual = _metadata.get(conversation_id, {}).get("owner_key") or _owner_key_from_conversation_id(conversation_id)
    return actual == expected


def load_all_from_supabase() -> int:
    client = get_supabase_client()
    if client is None:
        return 0
    try:
        resp = client.table("chats").select("id, messages").execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load chats from Supabase: %s", exc)
        return 0
    with _lock:
        for row in resp.data or []:
            convo_id = row["id"]
            messages = deepcopy(row.get("messages", []) or [])
            _threads[convo_id] = messages
            _metadata.setdefault(
                convo_id,
                {
                    "id": convo_id,
                    "owner_key": _owner_key_from_conversation_id(convo_id),
                    "title": _title_from_messages(messages),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                    "domain": _last_meta_value(messages, "domain", "general"),
                    "language": _last_meta_value(messages, "language", "en"),
                },
            )
        try:
            meta_resp = client.table("chat_metadata").select("id, name, created_at, updated_at").execute()
            for row in meta_resp.data or []:
                existing = _metadata.setdefault(
                    row["id"],
                    {"id": row["id"], "owner_key": _owner_key_from_conversation_id(row["id"])},
                )
                if row.get("name"):
                    existing["title"] = row["name"]
                existing["created_at"] = row.get("created_at") or existing.get("created_at")
                existing["updated_at"] = row.get("updated_at") or existing.get("updated_at")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load chat metadata from Supabase: %s", exc)
    return len(resp.data or [])


def _persist(conversation_id: str, messages: list[dict]) -> None:
    client = get_supabase_client()
    if client is None:
        return
    try:
        client.table("chats").upsert({"id": conversation_id, "messages": messages}).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to persist chat %s: %s", conversation_id, exc)


def _persist_metadata(conversation_id: str) -> None:
    client = get_supabase_client()
    if client is None:
        return
    meta = _metadata.get(conversation_id, {})
    try:
        client.table("chat_metadata").upsert({"id": conversation_id, "name": meta.get("title", "New Chat")}).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to persist chat metadata %s: %s", conversation_id, exc)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _last_meta_value(messages: list[dict], key: str, default: str) -> str:
    for item in reversed(messages):
        value = (item.get("meta") or {}).get(key)
        if value:
            return str(value)
    return default


def _title_from_messages(messages: list[dict]) -> str:
    for item in messages:
        if item.get("role") == "user" and item.get("content"):
            return make_chat_title(str(item["content"]))
    return "New Chat"


def create_conversation(owner_id: str | None = None) -> str:
    owner_key = _owner_key(owner_id)
    convo_id = f"{owner_key}_{uuid.uuid4().hex}" if owner_id else uuid.uuid4().hex
    now = _now()
    with _lock:
        _threads[convo_id] = []
        _metadata[convo_id] = {
            "id": convo_id,
            "owner_key": owner_key,
            "title": "New Chat",
            "created_at": now,
            "updated_at": now,
            "domain": "general",
            "language": "en",
        }
    _persist(convo_id, [])
    _persist_metadata(convo_id)
    return convo_id


def conversation_belongs_to(conversation_id: str, owner_id: str | None) -> bool:
    with _lock:
        if conversation_id not in _threads and conversation_id not in _metadata:
            return False
        return _matches_owner(conversation_id, owner_id)


def append_message(
    conversation_id: str,
    role: str,
    content: str,
    meta: dict | None = None,
    owner_id: str | None = None,
) -> None:
    if owner_id is not None and not conversation_belongs_to(conversation_id, owner_id):
        logger.warning("Blocked cross-owner append to chat %s", conversation_id)
        return
    msg_meta = meta or {}
    created_at = _now()
    message = {
        "role": role,
        "content": content,
        "created_at": created_at,
        "meta": msg_meta,
    }
    with _lock:
        _threads.setdefault(conversation_id, []).append(message)
        current = _metadata.setdefault(
            conversation_id,
            {
                "id": conversation_id,
                "owner_key": _owner_key(owner_id),
                "title": "New Chat",
                "created_at": created_at,
                "domain": "general",
                "language": "en",
            },
        )
        current["updated_at"] = created_at
        if msg_meta.get("domain"):
            current["domain"] = msg_meta["domain"]
        if msg_meta.get("language"):
            current["language"] = msg_meta["language"]
        if role == "user" and current.get("title") in {"", "New Chat", None}:
            current["title"] = make_chat_title(content)
        messages = deepcopy(_threads[conversation_id])
    _persist(conversation_id, messages)
    _persist_metadata(conversation_id)


def get_conversation(conversation_id: str, owner_id: str | None = None) -> list[dict]:
    with _lock:
        if not _matches_owner(conversation_id, owner_id):
            return []
        return deepcopy(_threads.get(conversation_id, []))


def delete_conversation(conversation_id: str, owner_id: str | None = None) -> None:
    with _lock:
        if not _matches_owner(conversation_id, owner_id):
            return
        _threads.pop(conversation_id, None)
        _metadata.pop(conversation_id, None)
    client = get_supabase_client()
    if client is not None:
        try:
            client.table("chats").delete().eq("id", conversation_id).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to delete chat %s: %s", conversation_id, exc)


def rename_conversation(conversation_id: str, name: str, owner_id: str | None = None) -> None:
    with _lock:
        if not _matches_owner(conversation_id, owner_id):
            return
        meta = _metadata.setdefault(conversation_id, {"id": conversation_id, "created_at": _now()})
        meta["title"] = name
        meta["updated_at"] = _now()
    client = get_supabase_client()
    if client is not None:
        try:
            client.table("chat_metadata").upsert({"id": conversation_id, "name": name}).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to rename chat %s: %s", conversation_id, exc)


def list_conversations(limit: int = 50, owner_id: str | None = None) -> list[dict]:
    with _lock:
        summaries = []
        for convo_id, messages in _threads.items():
            if not _matches_owner(convo_id, owner_id):
                continue
            meta = _metadata.get(convo_id, {})
            summaries.append(
                {
                    "id": convo_id,
                    "title": meta.get("title") or _title_from_messages(messages),
                    "updated_at": meta.get("updated_at") or _last_meta_value(messages, "created_at", ""),
                    "created_at": meta.get("created_at") or "",
                    "message_count": len(messages),
                    "domain": meta.get("domain") or _last_meta_value(messages, "domain", "general"),
                    "language": meta.get("language") or _last_meta_value(messages, "language", "en"),
                }
            )
    return sorted(summaries, key=lambda row: row.get("updated_at") or "", reverse=True)[:limit]
