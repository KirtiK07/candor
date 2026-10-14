from pathlib import Path

from core.config import setting

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "redrafter.db"


def make_store():
    """Supabase when STORAGE=supabase is configured, otherwise a local SQLite file."""
    if str(setting("STORAGE", "sqlite")).lower() == "supabase":
        from storage.supabase_store import SupabaseStore

        return SupabaseStore(setting("SUPABASE_URL"), setting("SUPABASE_KEY"))
    from storage.sqlite_store import SQLiteStore

    return SQLiteStore(setting("SQLITE_PATH") or DEFAULT_DB)
