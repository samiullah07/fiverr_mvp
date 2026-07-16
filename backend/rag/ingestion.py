"""
Document ingestion: parse → chunk → embed → store.

Binding requirements implemented:
  • Incremental: tracks content-hash per file (document_id) via ManifestStore
  • No duplicate accumulation: reindexing a document deletes all previous
    chunks with that document_id before inserting new ones (via VectorStore)
  • Source metadata attached to every chunk: filename, section (if any),
    page (if any), chunk_index – flows to LLM prompt and Phase 3 overlay
  • Local-only: embeddings model + Chroma both run on client machine

Design notes for v1:
  • Fixed-size chunking with overlap (semantic chunking is a nice-to-have)
  • Uses the local sentence-transformers model from
    sentence-transformers/all-MiniLM-L6-v2 (384-dim, widely used)
  • Document types supported: PDF (via pypdf) and plain text.
"""
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Lazy imports keep start-up fast for non-RAG features
try:
    import pypdf  # for PDF files
    PDF_SUPPORTED = True
except ImportError:
    PDF_SUPPORTED = False

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDER_AVAILABLE = True
except ImportError:
    EMBEDDER_AVAILABLE = False

from .manifest import FileRecord, ManifestStore
from .vectorstore import VectorStore, ChromaConfig, DocMetadata


@dataclass
class Chunk:
    """One chunk of text together with its provenance."""
    text: str
    chunk_index: int                 # sequential index within this document
    page: Optional[int] = None       # if source is PDF
    section: Optional[str] = None    # future-proof for .docx headings, etc.
    document_id: str = ""            # sha256 of the document's bytes (set at ingest)
    source_text: str = ""            # for reference / diagnostics


@dataclass
class IngestionResult:
    """Outcome of ingesting one document root."""
    processed_files: List[str]     # relative paths of new/changed files
    skipped_files  : List[str]     # unchanged files
    removed_files  : List[str]     # files no longer present on disk
    total_chunks   : int
    status: str = "success"        # or "error" with message in `error`


def _sha256_file(path: str | os.PathLike) -> str:
    """Return hex digest (document_id) for a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Split text into fixed-size character chunks with overlap.

    Returns list of strings (chunks). This is simpler than token-based
    chunking and good enough for v1.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("chunk_size must be strictly greater than overlap")
    # Stride between chunk starts. min 1 guarantees forward progress even if
    # (hypothetically) overlap == chunk_size, so the loop can never spin forever.
    step = max(1, chunk_size - overlap)
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += step
    return chunks


class DocumentIngester:
    """
    Walks a folder, (re)indexes PDF and .txt files, storing chunks in Chroma
    with document_id + source_metadata.
    """

    def __init__(
        self,
        watch_root: str | os.PathLike,
        vector_store: Optional[VectorStore] = None,
        manifest_store: Optional[ManifestStore] = None,
        embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        chunk_size: int = 500,
        overlap: int = 50,
    ):
        if not EMBEDDER_AVAILABLE:
            raise RuntimeError(
                "Embedding dependencies not installed. Install with:\n"
                "  pip install sentence-transformers"
            )
        self.watch_root = Path(watch_root).resolve()
        self.vector_store = vector_store or VectorStore(ChromaConfig())
        self.manifest = manifest_store or ManifestStore(
            self.vector_store.config.persist_directory
        )
        self.embedder = SentenceTransformer(embedding_model_name)
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._supported_exts = {".txt", ".md", ".pdf"}

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def ingest_folder(self) -> IngestionResult:
        """
        Scan `watch_root`, (re)index new/changed PDF/txt files, and delete
        entries for files that no longer exist.

        Returns an IngestionResult with lists and total chunk count.
        """
        try:
            processed: List[str] = []
            skipped: List[str] = []
            removed: List[str] = []
            total_chunks = 0

            # 1) Walk disk and build a mapping of relative path → absolute path
            current_files: Dict[str, Path] = {}
            for root, _dirs, files in os.walk(self.watch_root):
                for name in files:
                    ext = os.path.splitext(name)[1].lower()
                    if ext in self._supported_exts:
                        abs_path = Path(root) / name
                        rel_path = abs_path.relative_to(self.watch_root)
                        current_files[str(rel_path)] = abs_path

            # 2) Determine which files changed, which are new, and which vanished
            manifest_records = self.manifest.all_records()
            manifest_rel_paths = set(manifest_records.keys())
            current_rel_paths = set(current_files.keys())

            # Vanished files: in manifest but not on disk → delete their chunks
            for rel_path in sorted(manifest_rel_paths - current_rel_paths):
                rec = manifest_records[rel_path]
                self.vector_store._delete_by_document_id(rec.document_id)
                self.manifest.remove(rel_path)
                removed.append(rel_path)

            # Changed or new files: content-hash differs or not in manifest
            for rel_path in sorted(current_rel_paths):
                abs_path = current_files[rel_path]
                if not self.manifest.is_unchanged(rel_path, abs_path):
                    doc_id = _sha256_file(abs_path)
                    # Record will be updated after successful embedding
                    processed.extend(self._process_file(
                        rel_path=rel_path,
                        abs_path=abs_path,
                        document_id=doc_id,
                        mtime_ns=abs_path.stat().st_mtime_ns,
                    ))
                else:
                    skipped.append(rel_path)

            # Flush manifest and compute total chunk count
            self.manifest.save()
            # Recalculate chunk count from manifest for accurate reporting
            total_chunks = sum(r.chunk_count for r in self.manifest.all_records().values())

            return IngestionResult(
                processed_files=processed,
                skipped_files=skipped,
                removed_files=removed,
                total_chunks=total_chunks,
                status="success",
            )
        except Exception as exc:  # pragma: no cover - defensive
            import traceback
            traceback.print_exc()
            return IngestionResult(
                processed_files=[],
                skipped_files=[],
                removed_files=[],
                total_chunks=0,
                status=f"error: {exc}",
            )

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #
    def _process_file(
        self,
        *,
        rel_path: str,
        abs_path: Path,
        document_id: str,
        mtime_ns: int,
    ) -> List[str]:
        """
        Extract text → chunk → embed → upsert to Chroma.

        Returns list of relative paths processed (just the one input file).
        Updates the manifest with the new chunk count.
        """
        # Extract raw text according to file type
        text = self._extract_text(abs_path)
        if not text.strip():
            # Empty file → nothing to index, still record zero chunks
            self.manifest.record(rel_path, document_id, mtime_ns, chunk_count=0)
            return [rel_path]

        # Chunk the text
        raw_chunks = _chunk_text(text, self.chunk_size, self.overlap)
        if not raw_chunks:
            self.manifest.record(rel_path, document_id, mtime_ns, chunk_count=0)
            return [rel_path]

        # Embed all chunks at once (efficient for batch)
        embeddings = self.embedder.encode(raw_chunks, show_progress_bar=False)
        # Ensure we have a plain list of lists for Chroma
        embedding_vectors: List[List[float]] = embeddings.tolist()

        # Build per-chunk metadata
        source_metadata_list: List[Dict[str, Any]] = []
        for idx, chunk_text in enumerate(raw_chunks):
            # For v1 we treat every file as one section; page is unknown for txt/md
            meta: Dict[str, Any] = {
                "filename": Path(rel_path).name,
                "section": None,  # PDF section extraction is a v2 nice-to-have
                "page": None,
                "chunk_index": idx,
                "source_text": chunk_text,
            }
            source_metadata_list.append(meta)

        # Upsert to Chroma with delete-before-insert (binding requirement)
        self.vector_store.upsert_document_chunks(
            document_id=document_id,
            embedding_vectors=embedding_vectors,
            source_metadata_list=source_metadata_list,
            source_texts=raw_chunks,
        )

        # Update manifest with the number of chunks we just stored
        self.manifest.record(rel_path, document_id, mtime_ns, chunk_count=len(raw_chunks))
        return [rel_path]

    # --------------------------------------------------------------------- #
    # Text extraction helpers
    # --------------------------------------------------------------------- #
    def _extract_text(self, path: Path) -> str:
        """Dispatch based on file extension."""
        ext = path.suffix.lower()
        if ext == ".pdf":
            return self._extract_pdf_text(path)
        if ext in {".txt", ".md"}:
            return self._extract_plain_text(path)
        return ""

    def _extract_plain_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Fall back to latin-1 so we at least get something
            return path.read_text(encoding="latin-1")

    def _extract_pdf_text(self, path: Path) -> str:
        if not PDF_SUPPORTED:
            raise RuntimeError("PDF support requires: pip install pypdf")
        text_parts = []
        with open(path, "rb") as f:
            reader = pypdf.PdfReader(f)
            for page_num, page in enumerate(reader.pages, start=1):
                try:
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        text_parts.append(f"[Page {page_num}]\n{page_text}")
                except Exception:  # pragma: no cover – defensive
                    continue
        return "\n\n".join(text_parts)
