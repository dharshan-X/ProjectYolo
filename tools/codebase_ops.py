import os
from pathlib import Path
from typing import List

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from tools.registry import register_tool
from tools.base import YOLO_HOME, audit_log

"""
Local Codebase RAG operations.
Indexes the workspace into a local Qdrant vector database and allows semantic search.
"""

# Path to local RAG qdrant instance (separate from Mem0 episodic memory)
RAG_DB_PATH = YOLO_HOME / "memory" / "codebase_rag"
COLLECTION_NAME = "codebase"

# Avoid indexing binaries, large files, or dependencies
IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".next",
    "dist",
    "build",
}
IGNORED_EXTS = {
    ".pyc",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".mp4",
}
MAX_FILE_SIZE = 500 * 1024  # 500 KB limit for text files


def _get_qdrant_client() -> QdrantClient:
    RAG_DB_PATH.mkdir(parents=True, exist_ok=True)
    
    # Bug fix: Handle local lock contention with a simple retry
    import time
    max_retries = 5
    for i in range(max_retries):
        try:
            client = QdrantClient(path=str(RAG_DB_PATH))
            break
        except Exception as e:
            if "already accessed by another instance" in str(e) and i < max_retries - 1:
                time.sleep(1 + i)
                continue
            raise

    embed_dim = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

    # Check if collection exists
    try:
        client.get_collection(COLLECTION_NAME)
    except Exception:
        # Create it
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=embed_dim, distance=Distance.COSINE),
        )
    return client


def _get_openai_client() -> OpenAI:
    from llm_router import load_llm_config
    llm_cfg = load_llm_config()

    api_key = os.getenv("OPENAI_API_KEY") or llm_cfg.api_key
    base_url = os.getenv("OPENAI_BASE_URL") or (llm_cfg.base_url if llm_cfg.provider in ["openai", "compatible", "openrouter"] else "https://api.openai.com/v1")

    if not api_key:
        raise ValueError("OPENAI_API_KEY or LLM_API_KEY must be set for Codebase RAG embeddings.")
    return OpenAI(api_key=api_key, base_url=base_url)


def _get_embedding(text: str, client: OpenAI) -> List[float]:
    embedding_model = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-3-small")
    response = client.embeddings.create(model=embedding_model, input=text)
    return response.data[0].embedding


def _get_embeddings_batch(texts: List[str], client: OpenAI) -> List[List[float]]:
    if not texts:
        return []
    embedding_model = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-3-small")
    response = client.embeddings.create(model=embedding_model, input=texts)
    # The API returns them in the same order as the inputs
    return [d.embedding for d in sorted(response.data, key=lambda x: x.index)]


def _chunk_text(text: str, chunk_size: int = 1500, overlap: int = 200) -> List[str]:
    """Split text into overlapping chunks based on characters (simple approximation)."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


@register_tool()
def codebase_index() -> str:
    """
    Recursively scans the current workspace, chunks text files, generates OpenAI embeddings,
    and stores them in a local Qdrant vector database.
    """
    try:
        cwd = Path.cwd()
        q_client = _get_qdrant_client()
        o_client = _get_openai_client()

        # We will re-index everything cleanly
        try:
            q_client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
            
        try:
            embed_dim = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
            q_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=embed_dim, distance=Distance.COSINE),
            )
        except Exception:
            pass

        points = []
        point_id = 1

        indexed_files = 0
        total_chunks = 0
        
        # We will accumulate chunks across files to batch embed them
        batch_texts = []
        batch_metadata = []
        
        def _flush_batch():
            nonlocal point_id, total_chunks, points, batch_texts, batch_metadata
            if not batch_texts:
                return
                
            embeddings = _get_embeddings_batch(batch_texts, o_client)
            for i, embedding in enumerate(embeddings):
                points.append(
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=batch_metadata[i]
                    )
                )
                point_id += 1
                total_chunks += 1
                
                # Batch insert into Qdrant every 100 points
                if len(points) >= 100:
                    q_client.upsert(collection_name=COLLECTION_NAME, points=points)
                    points.clear()
                    
            batch_texts.clear()
            batch_metadata.clear()

        for root, dirs, files in os.walk(cwd):
            # Prune ignored directories
            dirs[:] = [
                d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")
            ]

            for file in files:
                path = Path(root) / file
                if path.suffix.lower() in IGNORED_EXTS:
                    continue

                # Skip large files
                try:
                    if path.stat().st_size > MAX_FILE_SIZE:
                        continue
                except OSError:
                    continue

                try:
                    rel_path = path.relative_to(cwd)
                    content = path.read_text(encoding="utf-8", errors="ignore")
                    if not content.strip():
                        continue

                    chunks = _chunk_text(content)

                    for i, chunk in enumerate(chunks):
                        text_to_embed = f"File: {rel_path}\n\n{chunk}"
                        batch_texts.append(text_to_embed)
                        batch_metadata.append({
                            "file": str(rel_path),
                            "chunk_index": i,
                            "content": chunk,
                        })
                        
                        # Max batch size for OpenAI embeddings is generally large, but we'll use 100
                        # to keep latency smooth and memory low.
                        if len(batch_texts) >= 100:
                            _flush_batch()

                    indexed_files += 1
                except Exception:
                    # Skip files that can't be read
                    continue

        # Flush any remaining chunks
        _flush_batch()
        
        # Insert remaining points to Qdrant
        if points:
            q_client.upsert(collection_name=COLLECTION_NAME, points=points)

        result = f"Codebase indexed successfully. Processed {indexed_files} files into {total_chunks} chunks."
        audit_log("codebase_index", {}, "success")
        return result

    except Exception as e:
        audit_log("codebase_index", {}, "error", str(e))
        return f"Error indexing codebase: {e}"


@register_tool()
def codebase_search(query: str, limit: int = 5) -> str:
    """
    Search the codebase using semantic similarity.
    Returns the top K matching code chunks with their file paths.
    """
    try:
        if not query or not query.strip():
            return "Error: Query cannot be empty."

        q_client = _get_qdrant_client()
        o_client = _get_openai_client()

        query_vector = _get_embedding(query, o_client)

        search_result = q_client.search(  # type: ignore
            collection_name=COLLECTION_NAME, query_vector=query_vector, limit=limit
        )

        if not search_result:
            return f"No relevant code found for query: '{query}'"

        output = [f"Semantic search results for: '{query}'\n" + "=" * 40]

        for hit in search_result:
            file_path = hit.payload.get("file", "Unknown file")
            content = hit.payload.get("content", "").strip()
            score = hit.score

            output.append(f"\n📂 File: {file_path} (Score: {score:.3f})")
            output.append("-" * 40)
            output.append(content)
            output.append("-" * 40)

        audit_log("codebase_search", {"query": query}, "success")
        return "\n".join(output)

    except Exception as e:
        audit_log("codebase_search", {"query": query}, "error", str(e))
        return f"Error searching codebase: {e}"
