"""Constructs the AzureChatOpenAI client (Azure OpenAI, gpt-4.1-mini).

Reads credentials from environment variables (loaded from a .env file at
the repo root if present). Never hardcode a key; there is no fallback
default - a clear error beats a silent wrong-account call. api_key is a
Pydantic SecretStr once passed to AzureChatOpenAI, so it's masked in any
repr/log of the client - never interpolate it into a log message yourself.
"""
import os

from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI

DEPLOYMENT = "gpt-4.1-mini"
API_VERSION = "2025-01-01-preview"

load_dotenv()  # no-op if there's no .env file - fine for CI/tests


def get_llm(temperature: float = 0.1, max_tokens: int = 1500) -> AzureChatOpenAI:
    """A low-temperature client - this agent does grounded analysis, not
    creative writing, so we want it choosing the same tool for the same
    question most of the time.
    """
    # .strip() defensively - a stray space around a pasted key/endpoint
    # becomes part of the value otherwise, and Azure's auth error for that
    # gives no hint the key itself was never the problem (hit this exact
    # class of bug with the previous provider).
    api_key = (os.environ.get("AZURE_OPENAI_API_KEY") or "").strip() or None
    endpoint = (os.environ.get("AZURE_OPENAI_ENDPOINT") or "").strip() or None
    missing = [name for name, val in [
        ("AZURE_OPENAI_API_KEY", api_key), ("AZURE_OPENAI_ENDPOINT", endpoint),
    ] if not val]
    if missing:
        raise RuntimeError(
            f"Missing Azure OpenAI credentials: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill them in from your Azure OpenAI "
            f"resource's 'Keys and Endpoint' page."
        )

    return AzureChatOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=API_VERSION,
        azure_deployment=DEPLOYMENT,
        temperature=temperature,
        max_tokens=max_tokens,
    )
