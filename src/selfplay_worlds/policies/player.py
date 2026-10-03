"""A policy backed by a language model.

The Player knows nothing about any particular game. Game-specific text (rules,
how to describe an observation) is looked up by ``game_name``, and the model only
ever sees this seat's observation and the conversation it may see.

Reply format asked of the model:

    <thinking>private reasoning</thinking>
    <answer>{"option": 3}</answer>          for a decision
    <answer>what I say to the table</answer> for talk

Parsing happens in two stages: the Player turns model text into an answer dict,
then the game's ``Action.from_answer`` turns the dict into an action.
"""

from __future__ import annotations

import json
import re
from typing import Any

from selfplay_worlds.inference.base import GenerationConfig, InferenceBackend
from selfplay_worlds.inference.usage import UsageLimits, UsageTracker
from selfplay_worlds.policies.base import Policy

SYSTEM_TEMPLATE = """{rules}

Each time it is your turn to decide, you will see the situation and a numbered list of options.
Think privately inside <thinking>...</thinking>, then give your reply inside <answer>...</answer>.
For a decision, the answer is one JSON object: {{"option": <number of your chosen option>}}.
When you are asked to talk, the answer is what you say to the table; leave it empty to stay silent.
Your thinking is private. What you say is public and never binding."""

DECISION_INSTRUCTION = 'Choose one option. Reply with <thinking>...</thinking> then <answer>{"option": <number>}</answer>.'
TALK_INSTRUCTION = (
    "It is your moment to talk before you decide. "
    "Reply with <thinking>...</thinking> then <answer>what you say to the table</answer>, "
    "or an empty <answer></answer> to stay silent."
)
CONVERSATION_WINDOW = 40

_THINKING = re.compile(r"<thinking>(.*?)</thinking>", re.S | re.I)
_ANSWER = re.compile(r"<answer>(.*?)</answer>", re.S | re.I)
_BARE_NUMBER = re.compile(r"\s*(\d+)\s*\.?\s*")
_SILENCE = {"", "null", "none", "(silence)", "(silent)", "..."}


class Player(Policy):
    def __init__(
        self,
        *,
        game_name: str,
        model: InferenceBackend | None,
        generation_config: GenerationConfig | None = None,
        usage_limits: UsageLimits | None = None,
    ) -> None:
        super().__init__(game_name=game_name)
        self.generation_config = generation_config or GenerationConfig()
        self.usage = UsageTracker(limits=usage_limits)
        self.transcript: list[dict[str, Any]] = []
        """Every prompt and reply this Player produced. Survives save and load."""
        self.model: InferenceBackend | None = None
        self.model_name: str | None = None
        self.backend_name: str | None = None
        if model is not None:
            self.set_model(model=model)

    def set_model(self, *, model: InferenceBackend) -> None:
        """Attach a model. Needed after ``load``, which never restores one."""
        self.model = model
        self.model_name = model.model
        self.backend_name = model.name

    def __getstate__(self) -> dict[str, Any]:
        state = self.__dict__.copy()
        state["model"] = None  # live clients are never pickled; call set_model after load
        return state

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "model": self.model_name,
            "backend": self.backend_name,
            "generation": self.generation_config.to_dict(),
        }

    # ----------------------------------------------------------------- deciding

    def get_action(self, *, observation, conversation):
        rendered = self.render_observation(observation=observation)
        prompt = self.get_prompt(rendered_observation=rendered, observation=observation, conversation=conversation)
        blocks = self.parse_response(text=self._generate(kind="action", prompt=prompt))
        self.last_thinking = blocks["thinking"]
        return self.parse_answer(answer=blocks["answer"], observation=observation)

    def get_message(self, *, observation, conversation):
        rendered = self.render_observation(observation=observation)
        prompt = self.get_prompt(
            rendered_observation=rendered, observation=observation, conversation=conversation, talk=True
        )
        blocks = self.parse_response(text=self._generate(kind="message", prompt=prompt))
        self.last_thinking = blocks["thinking"]
        message = (blocks["answer"] or "").strip().strip('"').strip()
        return None if message.lower() in _SILENCE else message

    # ------------------------------------------------------------------ prompts

    def get_prompt(
        self,
        *,
        rendered_observation: str,
        observation: dict[str, Any],
        conversation: list[dict[str, Any]],
        talk: bool = False,
    ) -> list[dict[str, str]]:
        from selfplay_worlds.games import RULES  # imported late: games import policies

        system = SYSTEM_TEMPLATE.format(rules=RULES.get(self.game_name, f"You are playing {self.game_name}."))
        parts = [rendered_observation]
        talk_lines = [_conversation_line(entry) for entry in conversation[-CONVERSATION_WINDOW:]]
        if talk_lines:
            parts.append(f"Table talk so far (last {len(talk_lines)}):\n" + "\n".join(talk_lines))
        parts.append(TALK_INSTRUCTION if talk else DECISION_INSTRUCTION)
        feedback = observation.get("feedback")
        if feedback and not talk:
            parts.append(f"Your previous answer was rejected: {feedback}. Answer again.")
        return [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(parts)}]

    def _generate(self, *, kind: str, prompt: list[dict[str, str]]) -> str:
        if self.model is None:
            raise RuntimeError("this Player has no model; call set_model(model=...) after load")
        self.usage.check_before_call()
        config = self.generation_config
        generation = self.model.generate(
            messages=prompt,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
            top_k=config.top_k,
        )
        metadata = {
            "model": generation.model,
            "input_tokens": generation.input_tokens,
            "output_tokens": generation.output_tokens,
            "latency_s": generation.latency_s,
            "cost_usd": generation.cost_usd,
        }
        self.usage.record(metadata)
        self.transcript.append({"kind": kind, "prompt": prompt[-1]["content"], "reply": generation.text, **metadata})
        return generation.text

    # ------------------------------------------------------------------ parsing

    def parse_response(self, *, text: str) -> dict[str, str | None]:
        """Split a reply into ``{"thinking": ..., "answer": ...}``. Missing tags are tolerated."""
        thinking_match = _THINKING.search(text)
        thinking = thinking_match.group(1).strip() if thinking_match else None
        answer_match = _ANSWER.search(text)
        if answer_match:
            answer = answer_match.group(1).strip()
        else:
            answer = _THINKING.sub("", text).strip()
        return {"thinking": thinking or None, "answer": answer or None}

    def parse_answer(self, *, answer: str | None, observation: dict[str, Any]) -> dict[str, Any]:
        """Read an answer dict. A JSON object, or a bare option number. Unreadable text gives ``{}``,
        which the game's ``from_answer`` rejects with a reason."""
        if answer is None:
            return {}
        data = _first_json_object(answer)
        if data is not None:
            choice = data.get("option")
            if isinstance(choice, str) and choice.strip().isdigit():
                data = {**data, "option": int(choice)}
            return data
        bare = _BARE_NUMBER.fullmatch(answer)
        if bare:
            return {"option": int(bare.group(1))}
        return {}


def _conversation_line(entry: dict[str, Any]) -> str:
    if entry["kind"] == "thinking":
        return f"- (your private thinking) {entry['content']}"
    return f"- {entry['player_id']} says: {entry['content']}"


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
