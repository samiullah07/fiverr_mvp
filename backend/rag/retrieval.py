"""
Retrieval layer: question → vector search → ranked chunks with metadata.

Binding requirement: every retrieved chunk must carry source_metadata
(filename, section, page, chunk_index) so the LLM prompt can cite sources
and the Phase 3 overlay can display them to the user.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .vectorstore import VectorStore, ChromaConfig


@dataclass
class RetrievalResult:
    """One retrieved chunk with its provenance metadata."""
    text: str
    document_id: str
    source_metadata: Dict[str, Any]
    # Distance score from Chroma (cosine, lower is better)
    distance: float


class Retriever:
    """
    Semantic search over the Chroma collection.

    Usage:
        retriever = Retriever()
        results = retriever.retrieve(question, n_results=5)
        # Each result has text + document_id + source_metadata
    """

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ):
        self.vector_store = vector_store or VectorStore(ChromaConfig())
        try:
            from sentence_transformers import SentenceTransformer
            self.embedder = SentenceTransformer(embedding_model_name)
        except ImportError:
            raise RuntimeError(
                "Embedding dependencies not installed. Install with:\n"
                "  pip install sentence-transformers"
            )

    def retrieve(
        self,
        query: str,
        n_results: int = 5,
    ) -> List[RetrievalResult]:
        """
        Embed the query, run Chroma similarity search, return chunks with
        full source metadata for citation / attribution.
        """
        query_embedding = self.embedder.encode([query])[0].tolist()
        hits = self.vector_store.query_similar(
            query_embedding=query_embedding,
            n_results=n_results,
        )
        results = [
            RetrievalResult(
                text=hit["text"],
                document_id=hit["document_id"] or "",
                source_metadata=hit["source_metadata"],
                distance=hit.get("distance", 1.0),  # Chroma doesn't return distance by default
            )
            for hit in hits
        ]
        return results

    def retrieve_with_embedding(
        self,
        query_embedding: List[float],
        n_results: int = 5,
    ) -> List[RetrievalResult]:
        """Same as retrieve() but accepts a pre-computed query embedding."""
        hits = self.vector_store.query_similar(
            query_embedding=query_embedding,
            n_results=n_results,
        )
        return [
            RetrievalResult(
                text=hit["text"],
                document_id=hit["document_id"] or "",
                source_metadata=hit["source_metadata"],
                distance=hit.get("distance", 1.0),
            )
            for hit in hits
        ]