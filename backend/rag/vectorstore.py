"""
Chroma client wrapper for storing chunk vectors with metadata.

Schema per-chunk:
  - embedding: List[float]
  - document_id: str          # sha256 of the document bytes at embed time
  - source_metadata: dict     # must contain at least:
        filename: str,
        section: str | None,
        page: int | None,
        chunk_index: int
  - text: str                 # original chunk text (for debugging/logging)
  - collection_name: "meeting_copilot_chunks" (constant)

Two responsibilities:
  1. Connect to / create a Chroma collection with a stable local path
  2. Provide upsert and semantic-search APIs, deleting by document_id before
     reinsertion (binding requirement from CLIENT_BRIEF.md §6.5).
"""
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from chromadb import PersistentClient
from chromadb.api.models import Collection


@dataclass
class ChromaConfig:
    """Configuration for the Chroma client."""
    # Use os.environ for Windows LOCALAPPDATA expansion (Path.expanduser() only handles ~)
    _persist_dir_cache: str = None

    def __post_init__(self):
        if self._persist_dir_cache is None:
            local_app = os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))
            self._persist_dir_cache = str(Path(local_app) / "MeetingCopilot" / "chroma")

    @property
    def persist_directory(self) -> str:
        return self._persist_dir_cache

    @persist_directory.setter
    def persist_directory(self, value: str):
        self._persist_dir_cache = value

    collection_name: str = "meeting_copilot_chunks"
    embedding_dimension: int = 384


@dataclass
class DocMetadata:
    """Metadata attached to every Chroma document chunk."""
    document_id: str
    source_metadata: Dict[str, Any]
    text: str
    collection_name: str

    def to_chroma(self) -> Dict[str, Any]:
        """Return dict suitable for Chroma document insertion."""
        d = asdict(self)
        d["collection_name"] = self.collection_name
        return d

    @classmethod
    def from_chroma(cls, doc_id: str, meta: Dict[str, Any]) -> "DocMetadata":
        # Back-compat if called with new-style dict (embedding, metadata, id)
        if "metadata" in meta:
            # New Chroma format: embedding is separate, actual metadata lives
            # under the "metadata" key. Reconstruct the fields we care about.
            md = meta.get("metadata", {})
            return cls(
                document_id=meta.get("document_id", md.get("document_id", "")),
                source_metadata={
                    "filename": md.get("source_filename"),
                    "section": md.get("source_section"),
                    "page": md.get("source_page"),
                    "chunk_index": md.get("source_chunk_index"),
                },
                text=md.get("source_text", ""),
                collection_name=md.get("collection_name", cls.__name__),
            )
        return cls(
            document_id=meta.get("document_id", ""),
            source_metadata={
                "filename": meta.get("source_filename"),
                "section": meta.get("source_section"),
                "page": meta.get("source_page"),
                "chunk_index": meta.get("source_chunk_index"),
            },
            text=meta.get("source_text", ""),
            collection_name=meta.get("collection_name", "meeting_copilot_chunks"),
        )


class VectorStore:
    """
    Manages a single Chroma collection for all meeting-copilot chunks.

    Binding requirement: reindexing a document must delete all existing chunks
    with that document_id before inserting new ones. This is implemented in
    `upsert_document_chunks` so callers (the ingestion pipeline) know they
    must manage document identities via `document_id` metadata.
    """

    def __init__(self, config: Optional[ChromaConfig] = None):
        self.config = config or ChromaConfig()
        # PersistentClient writes to disk at `path` — this is the local-only
        # guarantee; nothing leaves the machine.
        self._client = PersistentClient(path=self.config.persist_directory)
        self._collection: Collection = self._client.get_or_create_collection(
            name=self.config.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def _delete_by_document_id(self, document_id: str) -> int:
        """
        Delete all documents that have this document_id.

        This is a binding requirement from CLIENT_BRIEF.md §6.5. Returns the
        number of documents removed.
        """
        existing = self._collection.get(
            where={"document_id": document_id},
            include=[],
        )
        ids_to_delete = existing.get("ids", [])
        if ids_to_delete:
            self._collection.delete(ids=ids_to_delete)
        return len(ids_to_delete)

    def upsert_document_chunks(
        self,
        document_id: str,
        embedding_vectors: List[List[float]],
        source_metadata_list: List[Dict[str, Any]],
        source_texts: List[str],
    ) -> None:
        """
        Bulk insert/update chunks for a document, with delete-before-insert.

        Follows the binding requirement: if any chunks already exist for this
        document_id, delete them first to avoid accumulation on document
        replacement.
        """
        # 1) Delete old chunks for this document
        self._delete_by_document_id(document_id)

        # 2) Build new rows
        documents = []
        metadatas = []
        ids = []
        for i, (vec, src_meta, text) in enumerate(
            zip(embedding_vectors, source_metadata_list, source_texts)
        ):
            doc_id = f"{document_id}_{i:06d}"
            doc_meta = DocMetadata(
                document_id=document_id,
                source_metadata={
                    "filename": src_meta.get("filename"),
                    "section": src_meta.get("section"),
                    "page": src_meta.get("page"),
                    "chunk_index": src_meta.get("chunk_index", i),
                    "source_text": text,
                },
                text=text,
                collection_name=self.config.collection_name,
            )
            documents.append(text)
            metadatas.append({
                "document_id": document_id,
                "source_filename": src_meta.get("filename"),
                "source_section": src_meta.get("section"),
                "source_page": src_meta.get("page"),
                "source_chunk_index": src_meta.get("chunk_index", i),
                "source_text": text,
                "collection_name": self.config.collection_name,
            })
            ids.append(doc_id)

        self._collection.upsert(
            embeddings=embedding_vectors,
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )

    def query_similar(
        self,
        query_embedding: List[float],
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search returning each hit's text plus source metadata.

        Binding requirement: source metadata (filename, section, page, etc.) must
        be returned so the LLM prompt can cite sources and Phase 3 overlay can
        surface them to the user.
        """
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["metadatas", "documents"],
        )

        hits: List[Dict[str, Any]] = []
        if results.get("ids") and len(results["ids"][0]) > 0:
            for i in range(len(results["ids"][0])):
                doc_id = results["ids"][0][i]
                text = results["documents"][0][i] if results["documents"] else ""
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                hits.append({
                    "id": doc_id,
                    "text": text,
                    "document_id": meta.get("document_id"),
                    "source_metadata": {
                        "filename": meta.get("source_filename"),
                        "section": meta.get("source_section"),
                        "page": meta.get("source_page"),
                        "chunk_index": meta.get("source_chunk_index"),
                        "source_text": meta.get("source_text", text),
                    },
                })
        return hits

    def count(self) -> int:
        """Return total number of chunks in the collection."""
        return self._collection.count()

    def count_by_document_id(self) -> Dict[str, int]:
        """Return {document_id: chunk_count} across the whole collection."""
        data = self._collection.get(include=["metadatas"])
        counts: Dict[str, int] = {}
        for meta in data.get("metadatas", []) or []:
            did = meta.get("document_id", "<unknown>")
            counts[did] = counts.get(did, 0) + 1
        return counts

    def clear(self) -> None:
        """Clear all chunks from the collection (useful for testing)."""
        self._collection.delete(where={})