"""
Persistent state tracker.

Keeps a JSON file on disk mapping each media file -> status, so that:
  - already-transcribed files are skipped on rescans
  - a crash/restart resumes instead of reprocessing everything
  - a file that changes (size/mtime differs from last time) gets redone

State schema (per file, keyed by absolute path):
{
    "status": "pending" | "in_progress" | "done" | "failed",
    "size": <int bytes>,
    "mtime": <float>,
    "transcript_path": <str or null>,
    "error": <str or null>,
    "updated_at": <iso timestamp>
}
"""

import json
import os
import threading
from datetime import datetime, timezone


class FileTracker:
    def __init__(self, state_path: str):
        self.state_path = state_path
        self._lock = threading.Lock()
        self._state = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                # Corrupt state file (e.g. crash mid-write) — start fresh
                # rather than crash the whole app. We back up the bad file
                # so nothing is silently lost.
                backup = self.state_path + ".corrupt"
                try:
                    os.replace(self.state_path, backup)
                except OSError:
                    pass
                return {}
        return {}

    def _save(self):
        # Write to a temp file then atomically replace, so a crash
        # mid-write never leaves a truncated/corrupt state file.
        tmp_path = self.state_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2)
        os.replace(tmp_path, self.state_path)

    def _fingerprint(self, filepath: str):
        try:
            st = os.stat(filepath)
            return st.st_size, st.st_mtime
        except OSError:
            return None, None

    def needs_processing(self, filepath: str) -> bool:
        """
        True if this file has never been seen, previously failed,
        was left mid-transcription by a crash, or has changed since
        it was last marked done.
        """
        with self._lock:
            entry = self._state.get(filepath)
            if entry is None:
                return True
            if entry.get("status") in ("pending", "in_progress", "failed"):
                return True
            # status == "done": reprocess only if the file itself changed
            size, mtime = self._fingerprint(filepath)
            if size is None:
                return False  # file vanished; nothing to do
            return entry.get("size") != size or entry.get("mtime") != mtime

    def mark_pending(self, filepath: str):
        self._update(filepath, status="pending")

    def mark_in_progress(self, filepath: str):
        self._update(filepath, status="in_progress")

    def mark_done(self, filepath: str, transcript_path: str):
        self._update(filepath, status="done", transcript_path=transcript_path,
                      error=None)

    def mark_failed(self, filepath: str, error: str):
        self._update(filepath, status="failed", error=error)

    def _update(self, filepath: str, **fields):
        size, mtime = self._fingerprint(filepath)
        with self._lock:
            entry = self._state.get(filepath, {})
            entry.update(fields)
            entry["size"] = size
            entry["mtime"] = mtime
            entry["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._state[filepath] = entry
            self._save()

    def resume_candidates(self) -> list:
        """
        Files that were 'in_progress' when the app last stopped (crash or
        kill -9) — these get requeued on startup instead of assumed done.
        """
        with self._lock:
            return [
                path for path, entry in self._state.items()
                if entry.get("status") == "in_progress"
            ]

    def stats(self) -> dict:
        with self._lock:
            counts = {"pending": 0, "in_progress": 0, "done": 0, "failed": 0}
            for entry in self._state.values():
                counts[entry.get("status", "pending")] = counts.get(
                    entry.get("status", "pending"), 0) + 1
            return counts
