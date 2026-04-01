import hashlib
import secrets
from typing import Optional

from sqlalchemy.orm import Session

from storage.models import ApiKey


def generate_api_key() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    key_prefix = raw[:8]
    return raw, key_hash, key_prefix


def find_api_key_by_hash(session: Session, key_hash: str) -> Optional[ApiKey]:
    return (
        session.query(ApiKey)
        .filter(ApiKey.key_hash == key_hash, ApiKey.is_active == "1")
        .first()
    )


def verify_api_key(session: Session, raw_key: str) -> Optional[ApiKey]:
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    return find_api_key_by_hash(session, key_hash)
