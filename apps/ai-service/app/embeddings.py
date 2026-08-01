import httpx

from .config import settings


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts or not settings.embedding_model or not settings.llm_api_key:
        return []
    base_url = (settings.llm_base_url or "").rstrip("/")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{base_url}/embeddings",
            headers={"authorization": f"Bearer {settings.llm_api_key}"},
            json={"model": settings.embedding_model, "input": texts},
        )
        response.raise_for_status()
    vectors = [item["embedding"] for item in sorted(response.json().get("data", []), key=lambda item: item.get("index", 0))]
    if len(vectors) != len(texts) or any(len(vector) != settings.embedding_dimensions for vector in vectors):
        raise RuntimeError("INVALID_EMBEDDING_DIMENSIONS")
    return vectors


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
