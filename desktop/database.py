"""
OmniStream Pro - SQLite Persistence & History Engine
Provides robust thread-safe queue storage, historical records, settings persistence,
JSON export/import, and automatic backup/restore.
Author: XMON4U (https://github.com/Xmon4u)
"""

import os
import sys
import json
import time
import sqlite3
import shutil
import threading
from typing import Optional, List, Dict, Any

_DB_LOCK = threading.RLock()


def get_data_dir() -> str:
    """Return persistent local AppData directory for OmniStream Pro data and database."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    data_dir = os.path.join(base, "OmniStreamPro")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_db_path() -> str:
    """Return absolute path to omnistream.db."""
    return os.path.join(get_data_dir(), "omnistream.db")


def _get_connection() -> sqlite3.Connection:
    """Create a connection with WAL mode enabled for high concurrent throughput."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    return conn


def init_db():
    """Initialize database tables with automatic migration support."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS queue (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        url TEXT,
                        input_raw TEXT,
                        save_dir TEXT,
                        saved_file TEXT,
                        resolution TEXT DEFAULT '1080p',
                        audio TEXT DEFAULT 'all',
                        sub_format TEXT DEFAULT 'SRT',
                        sub_lang TEXT DEFAULT 'all',
                        include_subtitles INTEGER DEFAULT 1,
                        mode TEXT DEFAULT 'normal',
                        netflix_id TEXT,
                        status TEXT DEFAULT 'Waiting',
                        progress_pct REAL DEFAULT 0.0,
                        progress_text TEXT DEFAULT 'Ready in queue',
                        file_size TEXT DEFAULT '',
                        total_size TEXT DEFAULT '',
                        speed TEXT DEFAULT '',
                        time_left TEXT DEFAULT '',
                        temp_dir TEXT DEFAULT '',
                        error_msg TEXT DEFAULT '',
                        priority INTEGER DEFAULT 0,
                        created_at REAL,
                        completed_at REAL,
                        media_type TEXT DEFAULT '',
                        year TEXT DEFAULT '',
                        is_multi_audio INTEGER DEFAULT 0,
                        audio_languages TEXT DEFAULT '',
                        unique_id TEXT DEFAULT ''
                    );
                """)
                for col_sql in (
                    "ALTER TABLE queue ADD COLUMN is_multi_audio INTEGER DEFAULT 0;",
                    "ALTER TABLE queue ADD COLUMN audio_languages TEXT DEFAULT '';",
                    "ALTER TABLE queue ADD COLUMN unique_id TEXT DEFAULT '';"
                ):
                    try:
                        conn.execute(col_sql)
                    except Exception:
                        pass
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_queue_priority ON queue(priority, created_at);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_queue_unique_id ON queue(unique_id);
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        val TEXT NOT NULL
                    );
                """)
        finally:
            conn.close()


def save_or_update_item(item: dict):
    """Insert or update a queue item into the database safely."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            now = time.time()
            created_at = item.get("created_at") or now
            completed_at = item.get("completed_at")
            if item.get("status") == "Completed" and not completed_at:
                completed_at = now

            with conn:
                conn.execute("""
                    INSERT INTO queue (
                        id, title, url, input_raw, save_dir, saved_file,
                        resolution, audio, sub_format, sub_lang, include_subtitles,
                        mode, netflix_id, status, progress_pct, progress_text,
                        file_size, total_size, speed, time_left, temp_dir,
                        error_msg, priority, created_at, completed_at,
                        media_type, year, is_multi_audio, audio_languages, unique_id
                    ) VALUES (
                        :id, :title, :url, :input_raw, :save_dir, :saved_file,
                        :resolution, :audio, :sub_format, :sub_lang, :include_subtitles,
                        :mode, :netflix_id, :status, :progress_pct, :progress_text,
                        :file_size, :total_size, :speed, :time_left, :temp_dir,
                        :error_msg, :priority, :created_at, :completed_at,
                        :media_type, :year, :is_multi_audio, :audio_languages, :unique_id
                    )
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title,
                        url = excluded.url,
                        input_raw = excluded.input_raw,
                        save_dir = excluded.save_dir,
                        saved_file = excluded.saved_file,
                        resolution = excluded.resolution,
                        audio = excluded.audio,
                        sub_format = excluded.sub_format,
                        sub_lang = excluded.sub_lang,
                        include_subtitles = excluded.include_subtitles,
                        mode = excluded.mode,
                        netflix_id = excluded.netflix_id,
                        status = excluded.status,
                        progress_pct = excluded.progress_pct,
                        progress_text = excluded.progress_text,
                        file_size = excluded.file_size,
                        total_size = excluded.total_size,
                        speed = excluded.speed,
                        time_left = excluded.time_left,
                        temp_dir = excluded.temp_dir,
                        error_msg = excluded.error_msg,
                        priority = excluded.priority,
                        completed_at = excluded.completed_at,
                        media_type = excluded.media_type,
                        year = excluded.year,
                        is_multi_audio = excluded.is_multi_audio,
                        audio_languages = excluded.audio_languages,
                        unique_id = excluded.unique_id;
                """, {
                    "id": item.get("id"),
                    "title": item.get("title", ""),
                    "url": item.get("url") or item.get("input", "") or item.get("source_url", ""),
                    "input_raw": item.get("input", "") or item.get("raw_input", ""),
                    "save_dir": item.get("save_dir", ""),
                    "saved_file": item.get("saved_file", ""),
                    "resolution": item.get("resolution", "1080p"),
                    "audio": item.get("audio", "all") or item.get("audio_choice", "all"),
                    "sub_format": item.get("sub_format", "SRT"),
                    "sub_lang": item.get("sub_lang", "all"),
                    "include_subtitles": 1 if item.get("include_subtitles", True) else 0,
                    "mode": item.get("mode", "normal") or item.get("download_mode", "normal"),
                    "netflix_id": item.get("netflix_id", ""),
                    "status": item.get("status", "Waiting"),
                    "progress_pct": float(item.get("progress_pct", 0.0) or item.get("progress", 0.0)),
                    "progress_text": item.get("progress_text", ""),
                    "file_size": (item.get("metrics") or {}).get("size", "") if isinstance(item.get("metrics"), dict) else item.get("file_size", ""),
                    "total_size": item.get("total_size", ""),
                    "speed": (item.get("metrics") or {}).get("speed", "") if isinstance(item.get("metrics"), dict) else item.get("speed", ""),
                    "time_left": (item.get("metrics") or {}).get("time", "") if isinstance(item.get("metrics"), dict) else item.get("time_left", ""),
                    "temp_dir": item.get("temp_dir", ""),
                    "error_msg": item.get("error_msg", ""),
                    "priority": int(item.get("priority", 0)),
                    "created_at": created_at,
                    "completed_at": completed_at,
                    "media_type": (item.get("media_metadata") or {}).get("media_type", "") if isinstance(item.get("media_metadata"), dict) else item.get("media_type", ""),
                    "year": (item.get("media_metadata") or {}).get("year", "") if isinstance(item.get("media_metadata"), dict) else item.get("year", ""),
                    "is_multi_audio": 1 if (item.get("is_multi_audio") or (isinstance(item.get("audio_languages"), list) and len(item.get("audio_languages")) >= 2)) else 0,
                    "audio_languages": json.dumps(item.get("audio_languages")) if isinstance(item.get("audio_languages"), list) else (str(item.get("audio_languages")) if item.get("audio_languages") else "[]"),
                    "unique_id": item.get("unique_id", "")
                })
        finally:
            conn.close()


def update_status(item_id: str, status: str, saved_file: Optional[str] = None, error_msg: str = "", progress_pct: Optional[float] = None, progress_text: Optional[str] = None):
    """Fast targeted update for item status transitions."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            with conn:
                params = {"id": item_id, "status": status}
                updates = ["status = :status"]
                if saved_file is not None:
                    updates.append("saved_file = :saved_file")
                    params["saved_file"] = saved_file
                if error_msg:
                    updates.append("error_msg = :error_msg")
                    params["error_msg"] = error_msg
                if progress_pct is not None:
                    updates.append("progress_pct = :progress_pct")
                    params["progress_pct"] = float(progress_pct)
                if progress_text is not None:
                    updates.append("progress_text = :progress_text")
                    params["progress_text"] = progress_text
                if status == "Completed":
                    updates.append("completed_at = :completed_at")
                    params["completed_at"] = time.time()

                sql = f"UPDATE queue SET {', '.join(updates)} WHERE id = :id"
                conn.execute(sql, params)
        finally:
            conn.close()


def load_all_queue_items() -> List[dict]:
    """
    Load queue items from SQLite on application start.
    Recovers interrupted downloads: items that were 'Downloading' when app exited
    are marked 'Paused' so they can safely resume.
    """
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.cursor()
            # Recover any orphaned 'Downloading' items to 'Paused'
            cursor.execute("UPDATE queue SET status = 'Paused', progress_text = 'Paused (Interrupted)' WHERE status = 'Downloading'")
            conn.commit()

            cursor.execute("SELECT * FROM queue ORDER BY priority ASC, created_at ASC")
            rows = cursor.fetchall()
            items = []
            for r in rows:
                item = {
                    "id": r["id"],
                    "title": r["title"],
                    "input": r["input_raw"] or r["url"],
                    "url": r["url"],
                    "save_dir": r["save_dir"],
                    "saved_file": r["saved_file"],
                    "resolution": r["resolution"],
                    "audio": r["audio"],
                    "sub_format": r["sub_format"],
                    "sub_lang": r["sub_lang"],
                    "include_subtitles": bool(r["include_subtitles"]),
                    "mode": r["mode"],
                    "netflix_id": r["netflix_id"],
                    "status": r["status"],
                    "progress_pct": float(r["progress_pct"] or 0.0),
                    "progress_text": r["progress_text"] or "",
                    "temp_dir": r["temp_dir"] or "",
                    "error_msg": r["error_msg"] or "",
                    "priority": r["priority"] or 0,
                    "created_at": r["created_at"],
                    "completed_at": r["completed_at"],
                    "progress": float(r["progress_pct"] or 0.0),
                    "final_path": r["saved_file"],
                    "download_mode": r["mode"],
                    "audio_choice": r["audio"],
                    "raw_input": r["input_raw"] or r["url"],
                    "source_url": r["url"],
                    "is_multi_audio": bool(r["is_multi_audio"]) if "is_multi_audio" in r.keys() else False,
                    "audio_languages": (json.loads(r["audio_languages"]) if (r["audio_languages"] and r["audio_languages"].startswith("[")) else []) if "audio_languages" in r.keys() else [],
                    "unique_id": r["unique_id"] if "unique_id" in r.keys() else "",
                    "metrics": {
                        "status": r["status"],
                        "percent": f"{int(r['progress_pct'] or 0)}%",
                        "size": r["file_size"] or "--",
                        "speed": r["speed"] or "0.0 MB/s",
                        "time": r["time_left"] or "--",
                        "left": "--"
                    }
                }
                items.append(item)
            return items
        finally:
            conn.close()


def remove_item(item_id: str):
    """Remove a queue item from the database."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM queue WHERE id = ?", (item_id,))
        finally:
            conn.close()


def clear_completed_items():
    """Delete all completed items from active queue database."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM queue WHERE status = 'Completed'")
        finally:
            conn.close()


def clear_failed_items():
    """Delete all failed or cancelled items from queue database."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM queue WHERE status IN ('Failed', 'Cancelled')")
        finally:
            conn.close()


def replace_all_queue_items(items: List[dict]):
    """Cleanly replace all items in queue table with a deduplicated list."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM queue")
            for it in items:
                save_or_update_item(it)
        finally:
            conn.close()


def update_priority_order(ordered_item_ids: List[str]):
    """Update priority order for items in queue."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            with conn:
                for idx, iid in enumerate(ordered_item_ids):
                    conn.execute("UPDATE queue SET priority = ? WHERE id = ?", (idx, iid))
        finally:
            conn.close()


def export_queue_to_json(filepath: str) -> bool:
    """Export current queue and history to a JSON file."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM queue ORDER BY priority ASC, created_at ASC")
            rows = [dict(r) for r in cursor.fetchall()]
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump({"version": "2.6.0", "timestamp": time.time(), "items": rows}, f, indent=2)
            return True
        except Exception:
            return False
        finally:
            conn.close()


def import_queue_from_json(filepath: str) -> List[dict]:
    """Import queue items from a JSON backup file and insert into database."""
    with _DB_LOCK:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("items", [])
            for it in items:
                save_or_update_item(it)
            return load_all_queue_items()
        except Exception:
            return []


def create_db_backup(target_dir: Optional[str] = None) -> Optional[str]:
    """Create a timestamped backup copy of omnistream.db."""
    with _DB_LOCK:
        try:
            src = get_db_path()
            if not os.path.exists(src):
                return None
            backup_folder = target_dir or os.path.join(get_data_dir(), "backups")
            os.makedirs(backup_folder, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            dst = os.path.join(backup_folder, f"omnistream_backup_{ts}.db")
            shutil.copy2(src, dst)
            return dst
        except Exception:
            return None


def restore_db_backup(backup_file: str) -> bool:
    """Restore database from a chosen backup file."""
    with _DB_LOCK:
        try:
            if not os.path.exists(backup_file):
                return False
            dst = get_db_path()
            shutil.copy2(backup_file, dst)
            return True
        except Exception:
            return False


# ── Settings Key-Value Store ───────────────────────────────────────────────────

def get_setting(key: str, default: Any = None) -> Any:
    """Retrieve a setting value from SQLite."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT val FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row["val"])
                except Exception:
                    return row["val"]
            return default
        finally:
            conn.close()


def set_setting(key: str, value: Any):
    """Save a setting value to SQLite."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            encoded = json.dumps(value)
            with conn:
                conn.execute(
                    "INSERT INTO settings (key, val) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET val = excluded.val",
                    (key, encoded)
                )
        finally:
            conn.close()


def get_all_settings() -> Dict[str, Any]:
    """Load all settings as a dictionary."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT key, val FROM settings")
            except sqlite3.OperationalError:
                init_db()
                cursor.execute("SELECT key, val FROM settings")
            result = {}
            for r in cursor.fetchall():
                try:
                    result[r["key"]] = json.loads(r["val"])
                except Exception:
                    result[r["key"]] = r["val"]
            return result
        except Exception:
            return {}
        finally:
            conn.close()


def update_title(item_id: str, new_title: str):
    """Update title for a queue item."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            with conn:
                conn.execute(
                    "UPDATE queue SET title = ? WHERE id = ?",
                    (new_title, item_id)
                )
        finally:
            conn.close()


def update_progress(item_id: str, progress: float, progress_text: str = ""):
    """Fast targeted update for progress."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            with conn:
                conn.execute(
                    "UPDATE queue SET progress_pct = ?, progress_text = ? WHERE id = ?",
                    (progress, progress_text, item_id)
                )
        finally:
            conn.close()


class Database:
    """Convenience wrapper providing class-level and instance-level access to database routines."""
    init_db = staticmethod(init_db)
    save_or_update_item = staticmethod(save_or_update_item)
    update_status = staticmethod(update_status)
    update_title = staticmethod(update_title)
    update_progress = staticmethod(update_progress)
    load_all_queue_items = staticmethod(load_all_queue_items)
    remove_item = staticmethod(remove_item)
    clear_completed_items = staticmethod(clear_completed_items)
    clear_failed_items = staticmethod(clear_failed_items)
    update_priority_order = staticmethod(update_priority_order)
    export_queue_to_json = staticmethod(export_queue_to_json)
    import_queue_from_json = staticmethod(import_queue_from_json)
    create_db_backup = staticmethod(create_db_backup)
    restore_db_backup = staticmethod(restore_db_backup)
    get_setting = staticmethod(get_setting)
    set_setting = staticmethod(set_setting)
    get_all_settings = staticmethod(get_all_settings)


_db_instance = None


def get_db() -> Database:
    """Return the singleton Database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance

