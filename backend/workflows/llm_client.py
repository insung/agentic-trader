"""LLM invocation helpers for workflow nodes."""
from tenacity import retry, stop_after_attempt, wait_exponential


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def invoke_llm_with_retry(structured_llm, messages):
    """Invoke an LLM with exponential backoff retry logic."""
    return structured_llm.invoke(messages)
