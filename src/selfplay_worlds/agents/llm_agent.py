"""An agent backed by a language model.

The agent knows nothing about any particular game. The game-specific text
(rules, how to describe an observation) comes from the GameSpec, and the model
only ever sees the acting player's observation.

Reply format asked of the model:

    {"message": "something to say, or null", "action": 3}

``action`` is the number of a legal action. Copying the action object itself is
also accepted; the environment decides whether it is legal.
"""

from __future__ import annotations

import json

from selfplay_worlds.agents.base import Agent
from selfplay_worlds.core.env import GameSpec
from selfplay_worlds.core.interaction import Interaction, MessagePolicy
from selfplay_worlds.core.types import Action, AgentOutput
from selfplay_worlds.inference.base import GenerationConfig, InferenceBackend

SYSTEM_TEMPLATE = """{rules}

Each time it is your decision, you will see the situation and a numbered list of legal actions.
Reply with one JSON object and nothing else:
{{"message": "<what you say to the table, or null>", "action": <number of your chosen action>}}
Your message is public."""

MESSAGE_RULES = {
    MessagePolicy.REQUIRED: "A message is required for this decision.",
    MessagePolicy.OPTIONAL: "A message is optional.",
    MessagePolicy.NONE: 'No message is allowed for this decision; use "message": null.',
}

AGENT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": ["string", "null"]},
        "action": {"type": "integer", "minimum": 1},
    },
    "required": ["message", "action"],
    "additionalProperties": False,
}


class LLMAgent(Agent):
    def __init__(
        self,
        *,
        backend: InferenceBackend,
        spec: GameSpec,
        max_tokens: int = 300,
        temperature: float = 0.7,
        generation_config: GenerationConfig | None = None,
        structured_output: bool = False,
    ) -> None:
        super().__init__()
        if spec.render_observation is None:
            raise ValueError(f"game {spec.name!r} has no render_observation for LLM agents")
        self._backend = backend
        self._spec = spec
        self._generation_config = generation_config or GenerationConfig(
            max_tokens=max_tokens,
            temperature=temperature,
            json_schema=AGENT_OUTPUT_SCHEMA if structured_output else None,
        )
        if structured_output and self._generation_config.json_schema is None:
            self._generation_config = GenerationConfig(
                max_tokens=self._generation_config.max_tokens,
                temperature=self._generation_config.temperature,
                top_p=self._generation_config.top_p,
                top_k=self._generation_config.top_k,
                json_schema=AGENT_OUTPUT_SCHEMA,
                reasoning=self._generation_config.reasoning,
            )
        self._system = SYSTEM_TEMPLATE.format(rules=spec.rules_text)
        self._last_problem: str | None = None

    def act(
        self, *, observation: dict, interaction: Interaction, legal_actions: list[Action], feedback: str | None = None
    ) -> AgentOutput:
        prompt = self._spec.render_observation(
            observation=observation, interaction=interaction, legal_actions=legal_actions
        )
        prompt += "\n\n" + MESSAGE_RULES[interaction.message_policy]
        if feedback is not None:
            why = f" ({self._last_problem})" if self._last_problem else ""
            prompt += f"\nYour previous reply was rejected: {feedback}{why}. Reply again with one JSON object."
        generation = self._backend.generate(
            messages=[{"role": "system", "content": self._system}, {"role": "user", "content": prompt}],
            max_tokens=self._generation_config.max_tokens,
            temperature=self._generation_config.temperature,
            top_p=self._generation_config.top_p,
            top_k=self._generation_config.top_k,
            json_schema=self._generation_config.json_schema,
        )
        message, action, problem = parse_reply(generation.text, legal_actions)
        self._last_problem = problem
        return AgentOutput(
            action=action,
            message=message,
            raw_model_output=None if self._generation_config.reasoning else generation.text,
            metadata={
                "model": generation.model,
                "input_tokens": generation.input_tokens,
                "output_tokens": generation.output_tokens,
                "latency_s": generation.latency_s,
                "cost_usd": generation.cost_usd,
                "parse_error": problem,
                "reasoning_redacted": self._generation_config.reasoning,
            },
        )

    def describe(self) -> dict:
        return {
            "type": "LLMAgent",
            "model": self._backend.model,
            "backend": self._backend.name,
            "generation": self._generation_config.to_dict(),
        }

    def state_dict(self) -> dict:
        data = super().state_dict()
        data["implementation"] = {"last_parse_problem": self._last_problem}
        return data

    def load_state_dict(self, data: dict) -> None:
        super().load_state_dict(data)
        self._last_problem = data.get("implementation", {}).get("last_parse_problem")


def parse_reply(text: str, legal_actions: list[Action]) -> tuple[str | None, Action | None, str | None]:
    """Read ``(message, action, problem)`` from a model reply. Never guesses an action."""
    data = _first_json_object(text)
    if data is None:
        return None, None, "no JSON object found in the reply"
    message = data.get("message")
    message = message.strip() if isinstance(message, str) and message.strip() else None
    choice = data.get("action")
    if isinstance(choice, str) and choice.strip().isdigit():
        choice = int(choice)
    if isinstance(choice, int) and not isinstance(choice, bool):
        if 1 <= choice <= len(legal_actions):
            return message, legal_actions[choice - 1], None
        return message, None, f"action number {choice} is not between 1 and {len(legal_actions)}"
    if choice is None:
        return message, None, None
    return message, None, f"could not read the action {choice!r}"


def _first_json_object(text: str) -> dict | None:
    """The first JSON object in the text, ignoring code fences or prose around it."""
    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None
