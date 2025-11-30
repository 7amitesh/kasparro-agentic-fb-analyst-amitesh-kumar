"""
Robust OpenAI integration adapter.

- Loads OPENAI_API_KEY from .env using python-dotenv.
- Supports old openai.ChatCompletion (v0.28) and provides
  graceful message if newer SDK is installed.
- Exposes call_llm(prompt, max_tokens, temperature, model)
  which returns text or None on failure.
- Implements simple retries and exponential backoff.
"""
import os
import time
import json
from typing import Optional
from dotenv import load_dotenv

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Try import compatible OpenAI SDK (v0.28) first; if not available, try v2 style
try:
    import openai  # type: ignore
    _OPENAI_SDK = "legacy"  # uses openai.ChatCompletion.create
    # For legacy package, set api_key on module
    if OPENAI_KEY:
        openai.api_key = OPENAI_KEY
except Exception:
    # newer SDK may be installed or missing; still import to check
    try:
        import openai as openai_new  # type: ignore
        openai = openai_new
        _OPENAI_SDK = "new"
        if OPENAI_KEY:
            # new SDK expects api_key in client; keep compatibility
            # We'll attempt to call new-style API if legacy not usable
            pass
    except Exception:
        openai = None
        _OPENAI_SDK = None

# Small helper for retry/backoff
def _backoff_sleep(attempt: int):
    time.sleep(min(2 ** attempt, 8))

def call_llm(prompt: str,
             max_tokens: int = 400,
             temperature: float = 0.3,
             model: Optional[str] = None,
             retries: int = 2,
             timeout_seconds: int = 20) -> Optional[str]:
    """Call LLM and return the response text. Returns None on failure."""
    if model is None:
        model = DEFAULT_MODEL

    if openai is None:
        return None

    last_err = None
    for attempt in range(max(1, retries + 1)):
        try:
            # Legacy (v0.28) usage
            if _OPENAI_SDK == "legacy":
                resp = openai.ChatCompletion.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    request_timeout=timeout_seconds
                )
                content = resp["choices"][0]["message"]["content"]
                return content

            # Newer SDK (adapter) - attempt a generic POST via openai if available
            elif _OPENAI_SDK == "new":
                # Try to support new OpenAI client shape if present
                # Many installs will still expose ChatCompletion with similar shape
                try:
                    resp = openai.ChatCompletion.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    content = resp["choices"][0]["message"]["content"]
                    return content
                except Exception as e:
                    # fallback: attempt text completion or other endpoints
                    last_err = e
                    raise

            else:
                return None

        except Exception as e:
            last_err = e
            if attempt < retries:
                _backoff_sleep(attempt)
                continue
            else:
                # give up
                return None
    return None

def parse_json_from_text(text: str):
    """Attempt to extract and parse JSON from model text."""
    if not text:
        return None
    text = text.strip()
    # If the model returns pure JSON, parse directly
    try:
        return json.loads(text)
    except Exception:
        # Try to find first { or [ and load
        start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
        if start >= 0:
            try:
                return json.loads(text[start:])
            except Exception:
                return None
    return None
