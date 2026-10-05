"""LLM clients from central config: Azure /openai/v1 for chat, Azure or
Cloudflare Workers AI (OpenAI-compatible) for embeddings."""

from functools import lru_cache
from urllib.parse import urlsplit

from openai import AsyncOpenAI, OpenAI

from matchpulse.config import get_settings


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


def _cloudflare() -> bool:
    return getattr(get_settings(), "embed_provider", "azure") == "cloudflare"


def _cloudflare_kwargs() -> dict:
    s = get_settings()
    if not s.cf_account_id or not s.cf_ai_api_token.get_secret_value():
        raise RuntimeError("Cloudflare embeddings are not configured")
    return {
        "base_url": f"https://api.cloudflare.com/client/v4/accounts/{s.cf_account_id}/ai/v1",
        "api_key": s.cf_ai_api_token.get_secret_value(),
    }


@lru_cache(maxsize=1)
def _cf_sync_client() -> OpenAI:
    return OpenAI(**_cloudflare_kwargs(), timeout=25, max_retries=1)


@lru_cache(maxsize=1)
def _cf_async_client() -> AsyncOpenAI:
    return AsyncOpenAI(**_cloudflare_kwargs(), timeout=60, max_retries=1)


def embed_sync_client() -> OpenAI:
    return _cf_sync_client() if _cloudflare() else sync_client()


def embed_async_client() -> AsyncOpenAI:
    return _cf_async_client() if _cloudflare() else async_client()


def embedding_kwargs() -> dict:
    """Azure supports reduced `dimensions`; Workers AI models have a fixed size."""
    return {} if _cloudflare() else {"dimensions": get_settings().embed_dim}


@lru_cache(maxsize=256)
def embed_query(query: str) -> tuple[float, ...]:
    """Embed at the commentary table's configured dimension, cache repeated queries."""
    settings = get_settings()
    if not settings.embed_deployment:
        raise RuntimeError("Search embeddings are not configured")
    instruction = getattr(settings, "embed_query_instruction", "")
    text = f"{instruction}{query}" if instruction else query
    response = embed_sync_client().embeddings.create(
        model=settings.embed_deployment, input=text, **embedding_kwargs()
    )
    if len(response.data[0].embedding) != settings.embed_dim:
        raise RuntimeError("Embedding service returned the wrong dimension")
    return tuple(response.data[0].embedding)
