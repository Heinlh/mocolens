"""Constructs the chat model client (Azure OpenAI in Microsoft Foundry, gpt-5.4-mini).

Reads credentials from environment variables (loaded from a .env file at
the repo root if present). Never hardcode a key; there is no fallback
default - a clear error beats a silent wrong-account call. api_key is a
Pydantic SecretStr once passed to the client, so it's masked in any
repr/log of it - never interpolate it into a log message yourself.

Calls go to Azure's OpenAI v1 API (https://<resource>.openai.azure.com/openai/v1/)
through the standard OpenAI client, which is how Foundry presents its
endpoint. The v1 API takes no api-version, and the deployment name goes in
`model`. The older AzureChatOpenAI client appended its own
/openai/deployments/... path to whatever endpoint it was given, so pasting
the endpoint exactly as Foundry shows it produced .../openai/v1/openai/
deployments/... and a bare "404 Resource not found". _v1_base_url() below
accepts any form of the endpoint a person is likely to paste.

gpt-5.4-mini is a reasoning model, which changes two settings from the
gpt-4.1-mini era:
* No temperature. Reasoning models reject anything but the default, so
  consistency (the same tool for the same question) comes from a low
  reasoning_effort instead.
* max_tokens covers the model's hidden reasoning as well as the answer, so
  it is set well above the size of the answer itself. langchain-openai sends
  it as max_completion_tokens.

AZURE_OPENAI_DEPLOYMENT overrides the default deployment name, so a
deployment can be swapped (or rolled back to the old one) without a code
change.
"""
import os
from urllib.parse import urlsplit

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

DEPLOYMENT = "gpt-5.4-mini"

# One Azure AI resource answers on several hostnames; only these carry the
# OpenAI v1 API under the same resource name.
_AZURE_HOST_SUFFIXES = (".openai.azure.com", ".services.ai.azure.com", ".cognitiveservices.azure.com")

load_dotenv()  # no-op if there's no .env file - fine for CI/tests


def _env(name: str) -> str | None:
    # .strip() defensively - a stray space around a pasted key/endpoint
    # becomes part of the value otherwise, and Azure's auth error for that
    # gives no hint the key itself was never the problem (hit this exact
    # class of bug with the previous provider).
    return (os.environ.get(name) or "").strip() or None


def _v1_base_url(endpoint: str) -> str:
    """The resource's OpenAI v1 base URL, from any endpoint form Foundry or
    the Azure Portal shows: the bare resource URL, the same with /openai/v1/
    already on it, the cognitiveservices.azure.com form, or the Foundry
    project endpoint (https://<resource>.services.ai.azure.com/api/projects/<p>).
    Any path is dropped and replaced, so it cannot be doubled.
    """
    parts = urlsplit(endpoint if "://" in endpoint else f"https://{endpoint}")
    host = parts.netloc.lower()
    for suffix in _AZURE_HOST_SUFFIXES:
        if host.endswith(suffix):
            host = host[: -len(suffix)] + ".openai.azure.com"
            break
    return f"{parts.scheme or 'https'}://{host}/openai/v1/"


def get_llm(reasoning_effort: str = "low", max_tokens: int = 4000) -> ChatOpenAI:
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

    deployment = _env("AZURE_OPENAI_DEPLOYMENT") or DEPLOYMENT
    # A rollback to gpt-4.1-mini must not send reasoning_effort, which
    # non-reasoning models reject; it gets the old low temperature instead.
    # Keyed on the deployment name, so name deployments after their model.
    if deployment.lower().startswith(("gpt-5", "o1", "o3", "o4")):
        sampling = {"reasoning_effort": reasoning_effort}
    else:
        sampling = {"temperature": 0.1}
    return ChatOpenAI(
        base_url=_v1_base_url(endpoint),
        api_key=api_key,
        model=deployment,
        max_tokens=max_tokens,
        # Chat Completions, as before: the agent's tool calling, forced final
        # tool, and streaming were all built and tested against it.
        use_responses_api=False,
        **sampling,
    )
