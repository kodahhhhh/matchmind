"""Azure clients from central config; resource-level /openai/v1 endpoint."""

from functools import lru_cache
from urllib.parse import urlsplit

from openai import AsyncOpenAI, OpenAI

from matchmind.config import get_settings


def base_url() -> str:
    """Foundry project paths must not be propagated to embeddings/responses."""
    endpoint = urlsplit(get_settings().azure_openai_endpoint)
    if not endpoint.scheme or not endpoint.netloc:
        raise RuntimeError("Analyst service is not configured")
    return f"{endpoint.scheme}://{endpoint.netloc}/openai/v1/"


@lru_cache(maxsize=1)
def sync_client() -> OpenAI:
    return OpenAI(
        base_url=base_url(),
        api_key=get_settings().azure_openai_api_key.get_secret_value(),
        timeout=25,
        max_retries=1,
    )


@lru_cache(maxsize=1)
def async_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=base_url(),
        api_key=get_settings().azure_openai_api_key.get_secret_value(),
        timeout=45,
        max_retries=1,
    )


@lru_cache(maxsize=256)
def embed_query(query: str) -> tuple[float, ...]:
    """Embed at the commentary table's configured dimension, cache repeated queries."""
    settings = get_settings()
    if not settings.embed_deployment:
        raise RuntimeError("Search embeddings are not configured")
    response = sync_client().embeddings.create(
        model=settings.embed_deployment, input=query, dimensions=settings.embed_dim
    )
    return tuple(response.data[0].embedding)
