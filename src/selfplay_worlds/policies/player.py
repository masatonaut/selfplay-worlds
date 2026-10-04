"""A policy backed by a language model.

The Player knows nothing about any particular game. Game-specific text (rules,
how to describe an observation) is looked up by ``game_name``, and the model only
ever sees this seat's observation, the public conversation, and its own notes.

Reply format asked of the model:

    <thinking>private reasoning</thinking>
    <answer>{"option": 3}</answer>          for a decision
    <answer>what I say to the table</answer> for talk

Thinking belongs to the Player alone:

* ``thoughts`` keeps every model call (prompt, reply, thinking, answer, usage),
  keyed by a per-player counter. It is never trimmed and never shown to the model.
* ``thoughtpad`` is a short running text of past thinking. It is the only memory
  that reaches later prompts. When it grows past ``thoughtpad_max_words``, the
  model is asked to rewrite it, keeping only what matters for the rest of the game.

Parsing happens in two stages: the Player turns model text into an answer dict,
then the game's ``Action.from_answer`` turns the dict into an action.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from selfplay_worlds.core.persist import save_json
from selfplay_worlds.inference.base import GenerationConfig, InferenceBackend
from selfplay_worlds.inference.usage import UsageLimitExceeded, UsageLimits, UsageTracker
from selfplay_worlds.policies.base import Policy

SYSTEM_TEMPLATE = """{rules}

Each time it is your turn to decide, you will see the situation and a numbered list of options.
Think privately inside <thinking>...</thinking>, then give your reply inside <answer>...</answer>.
For a decision, the answer is one JSON object: {{"option": <number of your chosen option>}}.
When you are asked to talk, the answer is what you say to the table; leave it empty to stay silent.
Your thinking is private. It is added to your notes, which you will see in later prompts.
What you say is public and never binding."""

DECISION_INSTRUCTION = 'Choose one option. Reply with <thinking>...</thinking> then <answer>{"option": <number>}</answer>.'
TALK_INSTRUCTION = (
    "It is your moment to talk before you decide. "
    "Reply with <thinking>...</thinking> then <answer>what you say to the table</answer>, "
    "or an empty <answer></answer> to stay silent."
)
SUMMARY_INSTRUCTION = (
    "Rewrite your notes so they stay useful for the rest of this game. Keep only what matters "
    "from here on: what you believe about each player's cards and intentions, your plan, and "
    "facts you would otherwise forget. Drop anything that no longer matters. Use at most {words} words. "
    "Reply with <answer>your new notes</answer>."
)
THOUGHTPAD_MAX_WORDS = 400
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
        thoughtpad_max_words: int = THOUGHTPAD_MAX_WORDS,
    ) -> None:
        super().__init__(game_name=game_name)
        self.generation_config = generation_config or GenerationConfig()
        self.usage = UsageTracker(limits=usage_limits)
        self.thoughtpad_max_words = thoughtpad_max_words
        self.thoughtpad = ""
        """Running notes from past thinking. The only memory shown in later prompts."""
        self.thoughts: dict[int, dict[str, Any]] = {}
        """Every model call, in order: prompt, reply, thinking, answer, usage. Never trimmed."""
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
            "thoughtpad_max_words": self.thoughtpad_max_words,
        }

    def save(self, *, path: str | Path) -> Path:
        """Pickle the Player (without its model) and write its thoughts as readable JSON beside it."""
        path = super().save(path=path)
        save_json(
            path=path.with_suffix(".thoughts.json"),
            value={"thoughtpad": self.thoughtpad, "thoughts": {str(k): v for k, v in self.thoughts.items()}},
        )
        return path

    # ----------------------------------------------------------------- deciding

    def get_action(self, *, observation, conversation):
        prompt = self.get_prompt(
            rendered_observation=self.render_observation(observation=observation),
            observation=observation,
            conversation=conversation,
        )
        text, usage = self._generate(prompt=prompt)
        blocks = self.parse_response(text=text)
        answer = self.parse_answer(answer=blocks["answer"], observation=observation)
        self._remember(kind="action", observation=observation, prompt=prompt, reply=text, usage=usage,
                       thinking=blocks["thinking"], answer=answer)
        return answer

    def get_message(self, *, observation, conversation):
        prompt = self.get_prompt(
            rendered_observation=self.render_observation(observation=observation),
            observation=observation,
            conversation=conversation,
            talk=True,
        )
        text, usage = self._generate(prompt=prompt)
        blocks = self.parse_response(text=text)
        message = (blocks["answer"] or "").strip().strip('"').strip()
        message = None if message.lower() in _SILENCE else message
        self._remember(kind="talk", observation=observation, prompt=prompt, reply=text, usage=usage,
                       thinking=blocks["thinking"], answer=message)
        return message

    # ------------------------------------------------------------------ prompts

    def get_prompt(
        self,
        *,
        rendered_observation: str,
        observation: dict[str, Any],
        conversation: list[dict[str, Any]],
        talk: bool = False,
    ) -> list[dict[str, str]]:
        parts = [rendered_observation]
        if self.thoughtpad:
            parts.append(f"Your private notes so far:\n{self.thoughtpad}")
        talk_lines = [f"- {e['player_id']} says: {e['content']}" for e in conversation[-CONVERSATION_WINDOW:]]
        if talk_lines:
            parts.append(f"Table talk so far (last {len(talk_lines)}):\n" + "\n".join(talk_lines))
        parts.append(TALK_INSTRUCTION if talk else DECISION_INSTRUCTION)
        feedback = observation.get("feedback")
        if feedback and not talk:
            parts.append(f"Your previous answer was rejected: {feedback}. Answer again.")
        return [{"role": "system", "content": self._system_prompt()}, {"role": "user", "content": "\n\n".join(parts)}]

    def _system_prompt(self) -> str:
        from selfplay_worlds.games import RULES  # imported late: games import policies

        return SYSTEM_TEMPLATE.format(rules=RULES.get(self.game_name, f"You are playing {self.game_name}."))

    def _generate(self, *, prompt: list[dict[str, str]]) -> tuple[str, dict[str, Any]]:
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
        usage = {
            "model": generation.model,
            "input_tokens": generation.input_tokens,
            "output_tokens": generation.output_tokens,
            "latency_s": generation.latency_s,
            "cost_usd": generation.cost_usd,
        }
        self.usage.record(usage)
        return generation.text, usage

    # ---------------------------------------------------------------- thoughts

    def _remember(
        self,
        *,
        kind: str,
        observation: dict[str, Any],
        prompt: list[dict[str, str]],
        reply: str,
        usage: dict[str, Any],
        thinking: str | None,
        answer: Any,
    ) -> None:
        """Store the call in ``thoughts``; append any thinking to the thoughtpad, summarizing if too long."""
        step, phase = observation.get("step"), observation.get("phase")
        self.thoughts[len(self.thoughts)] = {
            "kind": kind,
            "step": step,
            "phase": phase,
            "feedback": observation.get("feedback"),
            "prompt": prompt[-1]["content"],
            "reply": reply,
            "thinking": thinking,
            "answer": answer,
            **usage,
        }
        if not thinking:
            return
        entry = f"[step {step}, {phase}] {thinking}"
        self.thoughtpad = f"{self.thoughtpad}\n{entry}" if self.thoughtpad else entry
        if _word_count(self.thoughtpad) > self.thoughtpad_max_words:
            self._summarize(observation=observation)

    def _summarize(self, *, observation: dict[str, Any]) -> None:
        """Ask the model to rewrite the thoughtpad. The full history stays in ``thoughts``."""
        before = self.thoughtpad
        target = max(1, self.thoughtpad_max_words // 2)
        prompt = [
            {"role": "system", "content": self._system_prompt()},
            {
                "role": "user",
                "content": "\n\n".join([
                    self.render_observation(observation=observation),
                    f"Your private notes so far:\n{before}",
                    SUMMARY_INSTRUCTION.format(words=target),
                ]),
            },
        ]
        try:
            text, usage = self._generate(prompt=prompt)
        except UsageLimitExceeded:
            # Out of budget: keep the newest notes instead, so this decision still goes through.
            text, usage, summary = "", {}, _newest_words(before, target)
        else:
            summary = (self.parse_response(text=text)["answer"] or "").strip() or _newest_words(before, target)
        self.thoughtpad = _newest_words(summary, self.thoughtpad_max_words)  # a hard cap, whatever the model did
        self.thoughts[len(self.thoughts)] = {
            "kind": "summary",
            "step": observation.get("step"),
            "phase": observation.get("phase"),
            "feedback": None,
            "prompt": prompt[-1]["content"],
            "reply": text,
            "thinking": None,
            "answer": None,
            "thoughtpad_before": before,
            "thoughtpad_after": self.thoughtpad,
            **usage,
        }

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


def _word_count(text: str) -> int:
    return len(text.split())


def _newest_words(text: str, limit: int) -> str:
    """The text itself if it fits, otherwise "..." and its newest words, ``limit`` words in all."""
    words = text.split()
    if len(words) <= limit:
        return text
    return " ".join(["...", *words[len(words) - limit + 1 :]])


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
