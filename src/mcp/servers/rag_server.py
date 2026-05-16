"""
RAG (Retrieval-Augmented Generation) MCP Server.
Provides: rag_index, rag_query, rag_status
Wraps chunking + embedding + FAISS vector search from the SmallRAG project.
Optimal config from SmallRAG experiments: chunk_size=512, MMR, top_k=5.
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("rag-server")

INDEX_ROOT = os.environ.get("RAG_SERVER_ROOT", os.getcwd())
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64
DEFAULT_TOP_K = 5
DEFAULT_MODEL = os.environ.get("RAG_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")

# Lazy-loaded singletons
_embedder = None
_vector_store = None
_indexed_files: list[str] = []


@dataclass
class Chunk:
    text: str
    metadata: dict
    chunk_id: int = 0


def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        import numpy as np
        _embedder = SentenceTransformer(DEFAULT_MODEL)
    return _embedder


def _get_or_create_store(dimension: int):
    global _vector_store
    if _vector_store is None:
        import faiss
        import numpy as np
        _vector_store = {
            "index": faiss.IndexFlatIP(dimension),
            "texts": [],
            "metadata": [],
        }
    return _vector_store


def _chunk_text(text: str, chunk_size: int, chunk_overlap: int, source: str) -> list[Chunk]:
    separators = ["\n\n", "\n", ". ", " ", ""]
    pieces = _recursive_split(text, separators, chunk_size, chunk_overlap)
    chunks = []
    for i, piece in enumerate(pieces):
        piece = piece.strip()
        if piece:
            chunks.append(Chunk(
                text=piece,
                metadata={"source": source, "chunk_id": i},
                chunk_id=i,
            ))
    return chunks


def _recursive_split(text: str, seps: list[str], chunk_size: int, overlap: int) -> list[str]:
    if not seps:
        return [text]
    sep = seps[0]
    if sep == "":
        result = []
        for i in range(0, len(text), chunk_size - overlap):
            piece = text[i:i + chunk_size]
            if piece.strip():
                result.append(piece)
        return result

    parts = text.split(sep)
    merged = []
    current = ""
    for part in parts:
        candidate = current + sep + part if current else part
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                merged.append(current)
            if len(part) > chunk_size:
                merged.extend(_recursive_split(part, seps[1:], chunk_size, overlap))
                current = ""
            else:
                current = part
    if current:
        merged.append(current)
    return merged


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="rag_index",
            description="将文件索引到 RAG 知识库 (chunking + embedding + FAISS)",
            inputSchema={
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要索引的文件路径列表 (相对于工作目录)",
                    },
                    "chunk_size": {"type": "integer", "default": 512},
                },
                "required": ["paths"],
            },
        ),
        Tool(
            name="rag_query",
            description="在 RAG 知识库中检索与查询最相关的代码片段",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索查询"},
                    "top_k": {"type": "integer", "default": 5},
                    "method": {
                        "type": "string",
                        "enum": ["topk", "mmr"],
                        "default": "mmr",
                        "description": "检索方法: topk 或 mmr (多样性检索)",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="rag_status",
            description="查看 RAG 知识库状态 (已索引文件数、chunk 数)",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "rag_index":
            return [TextContent(type="text", text=_handle_index(arguments))]
        elif name == "rag_query":
            return [TextContent(type="text", text=_handle_query(arguments))]
        elif name == "rag_status":
            return [TextContent(type="text", text=_handle_status())]
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")]


def _handle_index(args: dict) -> str:
    import numpy as np

    paths = args["paths"]
    chunk_size = args.get("chunk_size", DEFAULT_CHUNK_SIZE)
    root = Path(INDEX_ROOT).resolve()

    all_chunks = []
    for p in paths:
        full_path = root / p
        if not full_path.exists():
            return f"File not found: {p}"
        if not str(full_path.resolve()).startswith(str(root)):
            return f"Access denied: {p} is outside allowed root"

        text = full_path.read_text(encoding="utf-8", errors="replace")
        chunks = _chunk_text(text, chunk_size, DEFAULT_CHUNK_OVERLAP, source=p)
        all_chunks.extend(chunks)

    if not all_chunks:
        return "No content to index"

    embedder = _get_embedder()
    texts = [c.text for c in all_chunks]
    embeddings = embedder.encode(texts, normalize_embeddings=True)
    embeddings = np.array(embeddings, dtype=np.float32)

    store = _get_or_create_store(embeddings.shape[1])
    store["index"].add(embeddings)
    store["texts"].extend(texts)
    store["metadata"].extend([c.metadata for c in all_chunks])

    _indexed_files.extend(paths)

    return f"Indexed {len(all_chunks)} chunks from {len(paths)} files. Total chunks in store: {store['index'].ntotal}"


def _handle_query(args: dict) -> str:
    import numpy as np

    if _vector_store is None:
        return "Knowledge base is empty. Use rag_index first."

    query = args["query"]
    top_k = args.get("top_k", DEFAULT_TOP_K)
    method = args.get("method", "mmr")

    embedder = _get_embedder()
    query_text = query
    if "bge" in DEFAULT_MODEL.lower():
        query_text = "为这个句子生成表示以用于检索相关文章：" + query
    query_emb = embedder.encode([query_text], normalize_embeddings=True)
    query_emb = np.array(query_emb, dtype=np.float32)

    if method == "mmr":
        results = _mmr_search(query_emb[0], top_k)
    else:
        results = _topk_search(query_emb[0], top_k)

    if not results:
        return "No relevant results found."

    output_parts = []
    for i, (text, score, meta) in enumerate(results):
        source = meta.get("source", "unknown")
        output_parts.append(f"[{i+1}] (source: {source}, score: {score:.3f})\n{text}")
    return "\n\n---\n\n".join(output_parts)


def _topk_search(query_emb, top_k: int):
    import numpy as np
    store = _vector_store
    q = query_emb.reshape(1, -1).astype(np.float32)
    scores, indices = store["index"].search(q, min(top_k, store["index"].ntotal))
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        results.append((store["texts"][idx], float(score), store["metadata"][idx]))
    return results


def _mmr_search(query_emb, top_k: int, candidates: int = 20, lambda_mult: float = 0.5):
    import numpy as np
    store = _vector_store
    q = query_emb.reshape(1, -1).astype(np.float32)
    n_candidates = min(candidates, store["index"].ntotal)
    scores, indices = store["index"].search(q, n_candidates)

    candidate_ids = [int(i) for i in indices[0] if i >= 0]
    if not candidate_ids:
        return []

    candidate_embeddings = np.array(
        [store["index"].reconstruct(i) for i in candidate_ids], dtype=np.float32
    )
    candidate_scores = {i: float(s) for i, s in zip(candidate_ids, scores[0]) if i >= 0}

    selected = []
    remaining = list(range(len(candidate_ids)))

    for _ in range(min(top_k, len(candidate_ids))):
        best_score = -float("inf")
        best_idx = -1
        for i in remaining:
            relevance = candidate_scores[candidate_ids[i]]
            if selected:
                selected_embs = candidate_embeddings[selected]
                diversity = max(float(candidate_embeddings[i] @ e) for e in selected_embs)
            else:
                diversity = 0.0
            mmr_score = lambda_mult * relevance - (1 - lambda_mult) * diversity
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = i
        if best_idx < 0:
            break
        selected.append(best_idx)
        remaining.remove(best_idx)

    results = []
    for i in selected:
        idx = candidate_ids[i]
        results.append((store["texts"][idx], candidate_scores[idx], store["metadata"][idx]))
    return results


def _handle_status() -> str:
    if _vector_store is None:
        return json.dumps({"status": "empty", "total_chunks": 0, "indexed_files": []}, ensure_ascii=False)
    return json.dumps({
        "status": "ready",
        "total_chunks": _vector_store["index"].ntotal,
        "indexed_files": list(set(_indexed_files)),
        "embed_model": DEFAULT_MODEL,
    }, ensure_ascii=False)


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
