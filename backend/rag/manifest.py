"""
Manifest store for incremental indexing.

Tracks each indexed file's content hash (sha256) so reindexing can skip
unchanged files and detect changed / removed ones. The manifest lives
next to the Chroma collection so it survives restarts and reinstalls.
"""
import hashlib
import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional


@dataclass
class FileRecord:
    """One tracked file in the manifest."""
    document_id: str          # sha256 of file bytes
    rel_path: str             # path relative to watched root
    mtime_ns: int             # os.stat().st_mtime_ns at index time
    chunk_count: int          # number of chunks emitted (for reporting)


class ManifestStore:
    """
    Simple JSON manifest keyed by relative file path.

    Used by DocumentIngester to decide which files to (re)process and which
    to delete on reindex.
    """

    def __init__(self, store_dir: str | os.PathLike):
        self.manifest_path = Path(store_dir) / "manifest.json"
        self._records: Dict[str, FileRecord] = {}
        self.load()

    def load(self) -> None:
        """Load existing manifest from disk (no-op if missing)."""
        if self.manifest_path.exists():
            try:
                data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                self._records = {
                    k: FileRecord(**v) for k, v in data.get("files", {}).items()
                }
            except (json.JSONDecodeError, TypeError):
                # Corrupt manifest — start fresh rather than crash.
                self._records = {}

    def save(self) -> None:
        """Persist manifest to disk."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"files": {k: asdict(v) for k, v in self._records.items()}}
        self.manifest_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def content_hash(self, file_path: str | os.PathLike) -> str:
        """Return sha256 hex digest of the file's bytes (the document_id)."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(1 << 16), b""):
                h.update(block)
        return h.hexdigest()

    def get(self, rel_path: str) -> Optional[FileRecord]:
        return self._records.get(rel_path)

    def is_unchanged(self, rel_path: str, file_path: str | os.PathLike) -> bool:
        """
        True if the file is already recorded AND its content hash still
        matches (definitive) — we prefer the hash over mtime so an
        in-place rewrite to identical content is a no-op.
        """
        rec = self._records.get(rel_path)
        if rec is None:
            return False
        try:
            return rec.document_id == self.content_hash(file_path)
        except OSError:
            return False

    def record(
        self,
        rel_path: str,
        document_id: str,
        mtime_ns: int,
        chunk_count: int,
    ) -> None:
        self._records[rel_path] = FileRecord(
            document_id=document_id,
            rel_path=rel_path,
            mtime_ns=mtime_ns,
            chunk_count=chunk_count,
        )

    def remove(self, rel_path: str) -> None:
        self._records.pop(rel_path, None)

    def all_records(self) -> Dict[str, FileRecord]:
        return dict(self._records)
