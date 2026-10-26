"""Build an owner-bound storage adapter for one authenticated request."""

from ai.storage.session_repository import SQLiteSessionStore, SupabaseSessionStore
from backend.app.config import (
    get_database_path,
    get_storage_backend,
    get_supabase_publishable_key,
    get_supabase_url,
)


def get_request_session_store(user) -> SQLiteSessionStore | SupabaseSessionStore:
    """Create a fresh store bound only to the verified request identity."""
    user_id = str(user)
    if not user_id:
        raise ValueError("A verified user identity is required.")
    if get_storage_backend() == "sqlite":
        return SQLiteSessionStore(owner_id=user_id, db_path=get_database_path())
    project_url = get_supabase_url()
    publishable_key = get_supabase_publishable_key()
    access_token = getattr(user, "access_token", None)
    if not project_url or not publishable_key or not access_token:
        raise ValueError("Supabase session storage is not configured for this request.")
    return SupabaseSessionStore(
        project_url=project_url,
        publishable_key=publishable_key,
        owner_id=user_id,
        access_token=access_token,
    )
