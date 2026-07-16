"""
Meeting Copilot RAG Pipeline
- Document ingestion with incremental Chroma indexing
- Document_id (content hash) + source_metadata on every chunk
- Delete-before-reinsert for document updates
- Source attribution for LLM prompt and overlay display
"""

from .ingestion import DocumentIngester, IngestionResult
from .vectorstore import VectorStore
from .retrieval import Retriever, RetrievalResult
from .manifest import ManifestStore

__all__ = [
    "DocumentIngester",
    "IngestionResult",
    "VectorStore",
    "Retriever",
    "RetrievalResult",
    "ManifestStore",
]