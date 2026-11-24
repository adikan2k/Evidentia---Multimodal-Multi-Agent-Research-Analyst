"""OpenAI calls with the same contract as `llm.LLM.structured` (D-038).

A validated pydantic answer back, the worst case reserved against the cost cap before the call,
the real cost recorded after it, and every call traced in Langfuse through its OpenAI wrapper.
"""

from typing import Any, TypeVar

from pydantic import BaseModel

from evidentia.config import ConfigError, Settings
from evidentia.cost import Charge, Ledger, estimate_tokens, openai_usd
from evidentia.llm import ModelStopped

T = TypeVar("T", bound=BaseModel)


def is_openai_model(model: str) -> bool:
    return model.startswith("gpt-")


def make_client(settings: Settings) -> Any:
    if settings.openai_api_key is None:
        raise ConfigError("Missing or invalid settings: OPENAI_API_KEY")
    # Importing from langfuse.openai gives a client whose every call is traced (rule 11).
    from langfuse.openai import AsyncOpenAI

    return AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(), timeout=180, max_retries=2
    )


class OpenAILLM:
    def __init__(self, settings: Settings, ledger: Ledger, client: Any = None) -> None:
        self.settings = settings
        self.ledger = ledger
        self.client = client or make_client(settings)

    async def structured(
        self,
        *,
        node: str,
        model: str,
        effort: str,
        max_tokens: int,
        system: str,
        user: str,
        schema: type[T],
        config: Any = None,  # accepted for the same signature as LLM; tracing is by the wrapper
    ) -> T:
        worst_case = openai_usd(model, estimate_tokens(system + user), max_tokens)
        with self.ledger.reserve(node, worst_case):
            response = await self.client.responses.parse(
                model=model,
                instructions=system,
                input=user,
                text_format=schema,
                max_output_tokens=max_tokens,
                reasoning={"effort": effort},
                store=False,
            )
            self._charge(node, model, response.usage)
        if response.status == "incomplete":
            raise ModelStopped(f"{node}: the model stopped early ({response.incomplete_details})")
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:  # a refusal, or a reply that did not match the shape
            raise ModelStopped(f"{node}: the reply did not match the expected shape")
        return parsed

    def _charge(self, node: str, model: str, usage: Any) -> None:
        if usage is None:
            return
        details = getattr(usage, "input_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) or 0
        usd = openai_usd(model, usage.input_tokens, usage.output_tokens, cached)
        self.ledger.add(
            Charge(
                node=node,
                item=model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                usd=usd,
            )
        )
