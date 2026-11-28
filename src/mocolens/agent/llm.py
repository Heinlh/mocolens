"""Constructs the AzureChatOpenAI client (Azure OpenAI, gpt-5.4-mini).

Reads credentials from environment variables (loaded from a .env file at
the repo root if present). Never hardcode a key; there is no fallback
default - a clear error beats a silent wrong-account call. api_key is a
Pydantic SecretStr once passed to AzureChatOpenAI, so it's masked in any
repr/log of the client - never interpolate it into a log message yourself.

gpt-5.4-mini is a reasoning model, which changes two settings from the
gpt-4.1-mini era:
* No temperature. Reasoning models reject anything but the default, so
  consistency (the same tool for the same question) comes from a low
  reasoning_effort instead.
* max_tokens covers the model's hidden reasoning as well as the answer, so
  it is set well above the size of the answer itself. langchain-openai sends
  it to Azure as max_completion_tokens.

AZURE_OPENAI_DEPLOYMENT and AZURE_OPENAI_API_VERSION override the defaults
below, so a deployment can be swapped (or rolled back to the old one)
without a code change.
"""
import os
from urllib.parse import urlsplit

from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI

DEPLOYMENT = "gpt-5.4-mini"
API_VERSION = "2025-04-01-preview"

load_dotenv()  # no-op if there's no .env file - fine for CI/tests


def _env(name: str) -> str | None:
    # .strip() defensively - a stray space around a pasted key/endpoint
    # becomes part of the value otherwise, and Azure's auth error for that
    # gives no hint the key itself was never the problem (hit this exact
    # class of bug with the previous provider).
    return (os.environ.get(name) or "").strip() or None


def get_llm(reasoning_effort: str = "low", max_tokens: int = 4000) -> AzureChatOpenAI:
    """A low-effort reasoning client - this agent does grounded analysis
    over a handful of tool calls, where speed and consistent tool choice
    matter more than long deliberation.
    """
    api_key = _env("AZURE_OPENAI_API_KEY")
    endpoint = _env("AZURE_OPENAI_ENDPOINT")
    missing = [name for name, val in [
        ("AZURE_OPENAI_API_KEY", api_key), ("AZURE_OPENAI_ENDPOINT", endpoint),
    ] if not val]
    if missing:
        raise RuntimeError(
            f"Missing Azure OpenAI credentials: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill them in from your Foundry project's "
            f"Overview page (or an Azure OpenAI resource's 'Keys and Endpoint' page)."
        )
    if "/api/projects/" in endpoint:
        # The Foundry *project* endpoint serves the Foundry SDK and the
        # Responses API, not the Chat Completions API this client calls - every
        # request would fail with a 404 that never mentions the endpoint.
        raise RuntimeError(
            "AZURE_OPENAI_ENDPOINT is a Foundry project endpoint (.../api/projects/...). "
            "Use the project's Azure OpenAI endpoint instead, "
            "https://<resource-name>.openai.azure.com/, from the same Overview page."
        )
    # Foundry displays the endpoint as .../openai/v1 (and a deployment's Target
    # URI as .../openai/deployments/...), but AzureChatOpenAI appends
    # /openai/deployments/<name>/... itself - any path left on the endpoint
    # doubles up and every request 404s. Keep only the resource root.
    parts = urlsplit(endpoint)
    endpoint = f"{parts.scheme}://{parts.netloc}/"

    deployment = _env("AZURE_OPENAI_DEPLOYMENT") or DEPLOYMENT
    # A rollback to gpt-4.1-mini must not send reasoning_effort, which
    # non-reasoning models reject; it gets the old low temperature instead.
    # Keyed on the deployment name, so name deployments after their model.
    if deployment.lower().startswith(("gpt-5", "o1", "o3", "o4")):
        sampling = {"reasoning_effort": reasoning_effort}
    else:
        sampling = {"temperature": 0.1}
    return AzureChatOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=_env("AZURE_OPENAI_API_VERSION") or API_VERSION,
        azure_deployment=deployment,
        model=deployment,
        max_tokens=max_tokens,
        **sampling,
    )
