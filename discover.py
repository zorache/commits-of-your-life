#!/usr/bin/env python3
"""
Discovery Pipeline — probe your notes vault, retrieve resonant entries via RAG,
synthesize life events, and feed them into create_life_repo().
"""

import os
import sys
import json
import re
import hashlib
from pathlib import Path
from datetime import datetime

import yaml
import anthropic
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Embedding function for ChromaDB using nomic-embed-text-v1.5
# ---------------------------------------------------------------------------

SKIP_DIRS = {".obsidian", ".trash", "templates", ".git", ".DS_Store"}
ALLOWED_EXTENSIONS = {".md", ".txt"}

CLAUDE_MODEL = "claude-sonnet-4-6"


class NomicEmbeddingFunction:
    """ChromaDB-compatible embedding function wrapping nomic-embed-text-v1.5.

    Handles the required search_document: / search_query: prefixes.
    Uses MPS (Apple Silicon) with CPU fallback.
    """

    def __init__(self):
        import torch
        from sentence_transformers import SentenceTransformer

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        self._model = SentenceTransformer(
            "nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True, device=device
        )
        self._mode = "document"  # "document" or "query"

    def name(self) -> str:
        return "nomic-embed-text-v1.5"

    def set_mode(self, mode: str):
        assert mode in ("document", "query")
        self._mode = mode

    def __call__(self, input: list[str]) -> list[list[float]]:
        prefix = "search_document: " if self._mode == "document" else "search_query: "
        texts = [prefix + t for t in input]
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    # ChromaDB v1.5+ interface
    def embed_documents(self, input: list[str]) -> list[list[float]]:
        self._mode = "document"
        return self(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:
        self._mode = "query"
        return self(input)


# ---------------------------------------------------------------------------
# VaultIngester — walk a folder of notes, chunk, store in ChromaDB
# ---------------------------------------------------------------------------


class VaultIngester:
    def __init__(self, collection):
        self._collection = collection

    def ingest(self, vault_path: str) -> int:
        vault = Path(vault_path).expanduser().resolve()
        if not vault.is_dir():
            raise FileNotFoundError(f"Not a directory: {vault}")

        chunks_added = 0
        batch_ids, batch_docs, batch_metas = [], [], []

        for fpath in sorted(vault.rglob("*")):
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            if any(skip in fpath.parts for skip in SKIP_DIRS):
                continue

            text = fpath.read_text(errors="replace")
            if not text.strip():
                continue

            frontmatter, body = self._split_frontmatter(text)
            meta_base = self._extract_metadata(fpath, frontmatter, vault)
            chunks = self._chunk_text(body)

            for i, chunk in enumerate(chunks):
                doc_id = self._chunk_id(fpath, vault, i)
                meta = {**meta_base, "chunk_index": i}
                batch_ids.append(doc_id)
                batch_docs.append(chunk)
                batch_metas.append(meta)

                if len(batch_ids) >= 100:
                    self._collection.upsert(
                        ids=batch_ids, documents=batch_docs, metadatas=batch_metas
                    )
                    chunks_added += len(batch_ids)
                    batch_ids, batch_docs, batch_metas = [], [], []

        # flush remaining
        if batch_ids:
            self._collection.upsert(
                ids=batch_ids, documents=batch_docs, metadatas=batch_metas
            )
            chunks_added += len(batch_ids)

        return chunks_added

    # -- helpers --

    @staticmethod
    def _split_frontmatter(text: str):
        """Return (frontmatter_dict, body_str)."""
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                try:
                    fm = yaml.safe_load(parts[1])
                    if isinstance(fm, dict):
                        return fm, parts[2]
                except yaml.YAMLError:
                    pass
        return {}, text

    @staticmethod
    def _extract_metadata(fpath: Path, frontmatter: dict, vault_root: Path) -> dict:
        rel = str(fpath.relative_to(vault_root))
        meta = {"file_path": rel, "file_name": fpath.stem}

        # date: frontmatter > filename pattern > mtime
        date_str = None
        if "date" in frontmatter:
            date_str = str(frontmatter["date"])[:10]
        else:
            # try YYYY-MM-DD at start of filename
            m = re.match(r"(\d{4}-\d{2}-\d{2})", fpath.stem)
            if m:
                date_str = m.group(1)
            else:
                date_str = datetime.fromtimestamp(fpath.stat().st_mtime).strftime(
                    "%Y-%m-%d"
                )
        meta["date"] = date_str

        # tags from frontmatter
        tags = frontmatter.get("tags", [])
        if isinstance(tags, list):
            meta["tags"] = ", ".join(str(t) for t in tags)
        elif isinstance(tags, str):
            meta["tags"] = tags
        else:
            meta["tags"] = ""

        return meta

    @staticmethod
    def _chunk_text(text: str) -> list[str]:
        """Split on paragraph boundaries. Short notes stay whole."""
        text = text.strip()
        if not text:
            return []

        word_count = len(text.split())
        if word_count < 100:
            return [text]

        paragraphs = re.split(r"\n\s*\n", text)
        chunks = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(para) <= 500:
                chunks.append(para)
            else:
                # split long paragraphs on sentence boundaries
                sentences = re.split(r"(?<=[.!?])\s+", para)
                buf = ""
                for sent in sentences:
                    if len(buf) + len(sent) > 500 and buf:
                        chunks.append(buf.strip())
                        buf = ""
                    buf += sent + " "
                if buf.strip():
                    chunks.append(buf.strip())

        return chunks if chunks else [text]

    @staticmethod
    def _chunk_id(fpath: Path, vault_root: Path, chunk_index: int) -> str:
        rel = str(fpath.relative_to(vault_root))
        raw = f"{rel}::chunk_{chunk_index}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# VaultProber — probe query → ChromaDB retrieval → Claude synthesis
# ---------------------------------------------------------------------------


class VaultProber:
    def __init__(self, collection, embed_fn, anthropic_client):
        self._collection = collection
        self._embed_fn = embed_fn
        self._client = anthropic_client

    def probe(self, query: str, n_results: int = 15) -> dict:
        """Return {"echoes": [...], "events": [...]}"""
        self._embed_fn.set_mode("query")
        results = self._collection.query(query_texts=[query], n_results=n_results)
        self._embed_fn.set_mode("document")  # reset

        echoes = []
        for i in range(len(results["ids"][0])):
            echoes.append(
                {
                    "text": results["documents"][0][i],
                    "file": results["metadatas"][0][i].get("file_name", ""),
                    "date": results["metadatas"][0][i].get("date", ""),
                    "distance": results["distances"][0][i] if results.get("distances") else None,
                }
            )

        events = self._synthesize(query, echoes)
        return {"echoes": echoes, "events": events}

    def _synthesize(self, query: str, echoes: list[dict]) -> list[dict]:
        echo_text = "\n---\n".join(
            f"[{e['file']} | {e['date']}]\n{e['text']}" for e in echoes
        )

        prompt = f"""You are helping someone rediscover their life story by reading fragments from their personal notes.

The person entered this probe: "{query}"

Here are the most resonant fragments retrieved from their vault:

{echo_text}

Based on these fragments, synthesize concrete life events that emerge from the material.
Each event should be a real moment or transition you can identify from the notes — not invented.

Return ONLY a JSON array of events in this format:
[
  {{
    "commit_message": "Start learning piano",
    "date": "YYYY-MM-DD",
    "description": "A 1-2 sentence description of what happened",
    "keyword": "piano"
  }}
]

Guidelines:
- Extract dates from the fragments when available; estimate if needed
- commit_message should be imperative mood, like a git commit (plain human language, not developer jargon)
- keyword: 2-3 evocative words capturing the emotional essence (e.g. "first love", "father lost", "Brooklyn art")
- Focus on events that respond to the probe theme
- Typically 3-8 events per probe
- Be faithful to what the notes actually say"""

        try:
            response = self._client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            # strip markdown fences
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)
            return json.loads(text.strip())
        except Exception as e:
            print(f"Synthesis error: {e}")
            return []


# ---------------------------------------------------------------------------
# Lazy singleton — shared across CLI and web routes
# ---------------------------------------------------------------------------

_embed_fn = None
_collection = None
_prober = None


def _get_embed_fn():
    global _embed_fn
    if _embed_fn is None:
        print("Loading embedding model (first time may download ~270MB)...")
        _embed_fn = NomicEmbeddingFunction()
        print("Embedding model ready.")
    return _embed_fn


def _get_collection():
    global _collection
    if _collection is None:
        import chromadb

        db_path = os.getenv("CHROMA_DB_PATH", "./chroma_db")
        chroma_client = chromadb.PersistentClient(path=db_path)
        _collection = chroma_client.get_or_create_collection(
            name="vault", embedding_function=_get_embed_fn()
        )
    return _collection


def get_prober() -> VaultProber:
    """Get or create a VaultProber singleton. Used by app.py routes."""
    global _prober
    if _prober is None:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        _prober = VaultProber(_get_collection(), _get_embed_fn(), client)
    return _prober


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cli():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python discover.py ingest /path/to/vault")
        print('  python discover.py probe "what did I believe about love?"')
        print("  python discover.py status")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "ingest":
        if len(sys.argv) < 3:
            print("Usage: python discover.py ingest /path/to/vault")
            sys.exit(1)
        vault_path = sys.argv[2]
        collection = _get_collection()
        ingester = VaultIngester(collection)
        count = ingester.ingest(vault_path)
        total = collection.count()
        print(f"Ingested {count} chunks. Collection total: {total}")

    elif cmd == "probe":
        if len(sys.argv) < 3:
            print('Usage: python discover.py probe "your query"')
            sys.exit(1)
        query = sys.argv[2]
        prober = get_prober()
        result = prober.probe(query)

        print(f"\n=== Echoes ({len(result['echoes'])}) ===")
        for e in result["echoes"]:
            print(f"\n[{e['file']} | {e['date']}]")
            print(e["text"][:200])

        print(f"\n=== Synthesized Events ({len(result['events'])}) ===")
        for ev in result["events"]:
            print(f"  {ev['date']}  {ev['commit_message']}")
            print(f"           {ev['description']}")

    elif cmd == "status":
        collection = _get_collection()
        print(f"Collection 'vault': {collection.count()} chunks")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
