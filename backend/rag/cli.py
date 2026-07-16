#!/usr/bin/env python3
"""
CLI Test Harness — Meeting Copilot Phase 2 Exit Deliverable

Usage:
    python -m rag.cli <documents_folder> [--provider claude|openai|openrouter] [--model <name>]

This is a minimal REPL for early client testing *before* the Phase 3
Electron overlay exists. It:
  • Loads/reindexes all PDF + .txt files from the folder
  • Accepts a typed question
  • Shows retrieved chunks with source filenames/sections/pages
  • Calls the LLM (Claude, OpenAI, or OpenRouter for dev testing) with a grounded prompt
  • Returns the answer with inline citations
  • Loops until Ctrl-C / 'quit'

Run instructions:
    1. Install deps: pip install -r backend/requirements.txt
    2. Set API key in .env: ANTHROPIC_API_KEY=... or OPENAI_API_KEY=...,
       or OPENROUTER_API_KEY=... (dev/testing only)
    3. python -m rag.cli ./my_meeting_docs
"""
import os
import sys
import signal
from pathlib import Path
from typing import Optional

# Load .env early for API keys
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .ingestion import DocumentIngester, IngestionResult
from .retrieval import Retriever, RetrievalResult
from .vectorstore import VectorStore, ChromaConfig
from .llm import LLMClient, SYSTEM_INSTRUCTIONS, GROUNDING_TEMPLATE


# --------------------------------------------------------------------------- #
# REPL
# --------------------------------------------------------------------------- #
def format_context_chunks(results) -> str:
    """Format retrieved chunks as numbered context for the LLM prompt."""
    lines = []
    for i, r in enumerate(results, 1):
        src = r.source_metadata
        fn = src.get("filename", "?")
        sec = src.get("section") or ""
        pg = src.get("page")
        page_str = f" p.{pg}" if pg else ""
        section_str = f" §{sec}" if sec else ""
        header = f"[{i}] {fn}{section_str}{page_str}"
        lines.append(f"{header}\n{r.text}\n")
    return "\n".join(lines)


def print_retrieved_chunks(results) -> None:
    """Pretty-print retrieved chunks for the user to see what was fetched."""
    print("\n--- Retrieved Chunks ---")
    for i, r in enumerate(results, 1):
        src = r.source_metadata
        fn = src.get("filename", "?")
        sec = src.get("section") or ""
        pg = src.get("page")
        page_str = f" p.{pg}" if pg else ""
        section_str = f" §{sec}" if sec else ""
        print(f"  [{i}] {fn}{section_str}{page_str} (chunk {src.get('chunk_index', '?')})")
        # Show first 120 chars of chunk text
        preview = r.text[:120].replace("\n", " ")
        print(f"      \"{preview}...\"")
    print("------------------------\n")


def run_repl(docs_root: Path, provider: str, model: Optional[str]) -> None:
    print(f"[DOCS] Indexing documents from: {docs_root}")
    if not docs_root.exists():
        print(f"[ERROR] Folder not found: {docs_root}")
        return

    ingester = DocumentIngester(docs_root)
    result: IngestionResult = ingester.ingest_folder()

    if result.status.startswith("error"):
        print(f"[ERROR] Ingestion error: {result.status}")
        return

    print(f"[OK] Indexed {len(result.processed_files)} file(s), "
          f"skipped {len(result.skipped_files)}, "
          f"removed {len(result.removed_files)}. "
          f"Total chunks: {result.total_chunks}")

    retriever = Retriever()
    llm = LLMClient(provider=provider, model=model)

    print("\n[CHAT] Meeting Copilot CLI — type a question (or 'quit' to exit)")
    print("-------------------------------------------------------------")

    def handle_sigint(*_):
        print("\n[BYE] Exiting...")
        sys.exit(0)
    signal.signal(signal.SIGINT, handle_sigint)

    while True:
        try:
            question = input("\n[Q] Question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not question:
            continue
        if question.lower() in {"quit", "exit", "q"}:
            break

        # Retrieve
        results = retriever.retrieve(question, n_results=5)
        if not results:
            print("[WARN] No relevant chunks found in your documents.")
            continue

        print_retrieved_chunks(results)

        # Build grounded prompt
        context = format_context_chunks(results)
        prompt = GROUNDING_TEMPLATE.format(context=context, question=question)

        # Call LLM using LLMClient
        print("Answer: ", end="")
        _ = llm.stream_answer(prompt)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Meeting Copilot RAG CLI — Phase 2 test harness"
    )
    parser.add_argument("docs_folder", help="Path to folder containing PDF/.txt files")
    parser.add_argument(
        "--provider",
        choices=["claude", "openai", "openrouter"],
        default="claude",
        help="LLM provider (default: claude)",
    )
    parser.add_argument(
        "--model",
        help="Model name (default: ANTHROPIC_MODEL env var or claude-haiku-4-5-20251001 for Claude, gpt-4o-mini for OpenAI, OPENROUTER_MODEL env var for OpenRouter)",
    )
    args = parser.parse_args()

    docs_root = Path(args.docs_folder).resolve()
    try:
        run_repl(docs_root, args.provider, args.model)
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
