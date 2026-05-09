"""Prompt-injection pre-classifier (P1-12 / m12-pr10).

Complements ``ai_engine.agents.prompt_defense.wrap_user_input`` with a
weighted multi-signal classifier. ``wrap_user_input`` provides
*structural separation* (delimited untrusted block + a small regex
strip). This module adds *defence in depth*:

* A heuristic classifier scores any untrusted text for injection
  likelihood across several orthogonal signals (override phrases,
  role impersonation, encoded payloads, instruction density,
  delimiter breakouts, length anomalies).
* The classifier returns a verdict — ``allow``, ``redact``, or
  ``block`` — together with a normalised score, the matching
  signals, and a redacted variant of the text.
* ``classify_and_wrap`` is the one-call helper for prompt
  builders: it fuses classifier + structural wrap and emits a
  telemetry event when severity rises above ``allow``.

Design constraints:

* Pure-Python, no LLM call. The classifier runs on every prompt
  build path so cost has to be ~0.
* Fail-open. A bug in the classifier must never block a legitimate
  request — on any unexpected error we log and pass the original
  text through ``wrap_user_input``.
* Deterministic. Same input → same verdict. No clocks, no random.
* Configurable thresholds via env vars so security can tune without
  a redeploy:
  - ``PROMPT_INJECTION_REDACT_THRESHOLD`` (default 0.35)
  - ``PROMPT_INJECTION_BLOCK_THRESHOLD``  (default 0.75)
  - ``PROMPT_INJECTION_ENFORCE_BLOCK``    (default "0" — observe-only)
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from ai_engine.agents.prompt_defense import wrap_user_input

logger = logging.getLogger("hirestack.prompt_injection")


# ── Signals ────────────────────────────────────────────────────────────
# Each signal is a (name, regex, weight). Weights are calibrated so the
# composite score lands in [0, 1] for realistic adversarial payloads.

_SIGNAL_PATTERNS: tuple[tuple[str, re.Pattern[str], float], ...] = (
    # Direct override attempts.
    ("override_ignore",
     re.compile(r"(?i)\bignore (?:all |any )?(?:previous|prior|above) instructions?\b"),
     0.35),
    ("override_disregard",
     re.compile(r"(?i)\bdisregard (?:the )?(?:above|prior|previous|system)\b"),
     0.30),
    ("override_forget",
     re.compile(r"(?i)\bforget (?:everything|all|your) (?:above|prior|previous|instructions?)\b"),
     0.30),
    ("override_new_instructions",
     re.compile(r"(?i)\bnew instructions?\s*[:\-]"),
     0.25),
    # Role impersonation / jailbreak personas.
    ("role_impersonation",
     re.compile(r"(?i)\b(?:you are now|act as|pretend to be|roleplay as) (?:a |an )?"
                r"(?:dan|developer mode|jailbroken|admin|root|system)\b"),
     0.40),
    ("system_prefix",
     re.compile(r"(?i)(?:^|\n)\s*(?:system|assistant)\s*:\s*\S"),
     0.20),
    # ChatML / OpenAI delimiter injection.
    ("chatml_token",
     re.compile(r"<\|im_(?:start|end)\|>|<\|endoftext\|>"),
     0.45),
    # Tag breakout attempts targeting our wrapper.
    ("tag_breakout",
     re.compile(r"</user_input\s*>", re.IGNORECASE),
     0.45),
    # Encoded payloads — base64 or hex blobs long enough to hide an
    # instruction. Heuristic only; legitimate base64 attachments are
    # rare in resume/JD text.
    ("encoded_blob",
     re.compile(r"(?:[A-Za-z0-9+/]{40,}={0,2}|[0-9a-f]{60,})"),
     0.20),
    # "Output your system prompt" / data exfiltration probes.
    ("exfil_probe",
     re.compile(r"(?i)\b(?:reveal|print|output|repeat|show me|display|leak) "
                r"(?:your |the )?(?:system )?(?:prompt|instructions?|rules?)\b"),
     0.40),
    # Tool / function abuse.
    ("tool_abuse",
     re.compile(r"(?i)\b(?:execute|run|eval) (?:the following|this) "
                r"(?:code|command|shell|python|bash)\b"),
     0.35),
    # URL / link injection (lower weight; common in legitimate inputs).
    ("suspicious_url",
     re.compile(r"(?i)\b(?:click|visit|go to|browse to)\s+https?://"),
     0.10),
)

# Cap individual signal contribution so no single match alone yields
# block; blocking requires either two strong signals or one strong + a
# couple of weak.
_PER_SIGNAL_CAP = 0.45

_REDACT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    pat for name, pat, _ in _SIGNAL_PATTERNS
    if name in {
        "override_ignore", "override_disregard", "override_forget",
        "override_new_instructions", "role_impersonation",
        "chatml_token", "exfil_probe", "tool_abuse",
    }
)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def redact_threshold() -> float:
    return _env_float("PROMPT_INJECTION_REDACT_THRESHOLD", 0.35)


def block_threshold() -> float:
    return _env_float("PROMPT_INJECTION_BLOCK_THRESHOLD", 0.75)


def enforcement_enabled() -> bool:
    """When false (default), `block` verdicts are downgraded to `redact`.

    Lets us roll the classifier out in observe-mode first.
    """
    return _env_bool("PROMPT_INJECTION_ENFORCE_BLOCK", False)


# ── Verdict types ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class InjectionSignal:
    name: str
    weight: float
    matches: int


@dataclass(frozen=True)
class InjectionVerdict:
    severity: str  # "allow" | "redact" | "block"
    score: float
    signals: tuple[InjectionSignal, ...] = field(default_factory=tuple)
    redacted_text: str = ""
    original_length: int = 0
    enforced: bool = False

    @property
    def is_blocked(self) -> bool:
        return self.severity == "block"

    @property
    def is_clean(self) -> bool:
        return self.severity == "allow"


class PromptInjectionBlocked(RuntimeError):
    """Raised by ``classify_and_wrap`` when severity == 'block' and
    enforcement is enabled."""

    def __init__(self, verdict: InjectionVerdict):
        self.verdict = verdict
        super().__init__(
            f"prompt_injection_blocked score={verdict.score:.2f} "
            f"signals={[s.name for s in verdict.signals]}"
        )


# ── Classifier ────────────────────────────────────────────────────────


def _redact(text: str) -> str:
    cleaned = text
    for pat in _REDACT_PATTERNS:
        cleaned = pat.sub("[REDACTED]", cleaned)
    return cleaned


def classify(value: Any) -> InjectionVerdict:
    """Score ``value`` for prompt-injection likelihood.

    Always returns a verdict; never raises on bad input.
    """
    text = "" if value is None else str(value)
    original_length = len(text)
    if not text:
        return InjectionVerdict(severity="allow", score=0.0, original_length=0,
                                redacted_text="")

    signals: list[InjectionSignal] = []
    score = 0.0
    try:
        for name, pat, weight in _SIGNAL_PATTERNS:
            matches = len(pat.findall(text))
            if matches:
                contribution = min(weight * matches, _PER_SIGNAL_CAP)
                signals.append(InjectionSignal(name=name, weight=weight,
                                               matches=matches))
                score += contribution
        # Length-density adjustment: many signals in a short input is
        # more suspicious than the same in a long resume.
        if signals and original_length < 500:
            score *= 1.15
        score = min(score, 1.0)
    except Exception:  # pragma: no cover - defensive fail-open
        logger.exception("prompt_injection_classifier_error")
        return InjectionVerdict(severity="allow", score=0.0,
                                original_length=original_length,
                                redacted_text=text)

    redact_t = redact_threshold()
    block_t = block_threshold()
    enforced = enforcement_enabled()

    if score >= block_t:
        severity = "block" if enforced else "redact"
    elif score >= redact_t:
        severity = "redact"
    else:
        severity = "allow"

    redacted = _redact(text) if severity != "allow" else text

    return InjectionVerdict(
        severity=severity,
        score=round(score, 4),
        signals=tuple(signals),
        redacted_text=redacted,
        original_length=original_length,
        enforced=enforced,
    )


# ── Telemetry hook ─────────────────────────────────────────────────────
# Optional callback that receives a verdict + label whenever severity is
# above "allow". Wired by the runtime to forward to the agent event
# emitter / metrics. Setter is process-global because the prompt build
# path is hot and we don't want a context-var lookup per call.

_TelemetryHook = Optional[Any]
_TELEMETRY_HOOK: _TelemetryHook = None


def set_telemetry_hook(hook: _TelemetryHook) -> None:
    """Install (or clear with ``None``) a synchronous telemetry hook.

    Hook signature: ``hook(label: str, verdict: InjectionVerdict) -> None``.
    Exceptions inside the hook are swallowed.
    """
    global _TELEMETRY_HOOK
    _TELEMETRY_HOOK = hook


def _emit(label: str, verdict: InjectionVerdict) -> None:
    hook = _TELEMETRY_HOOK
    if hook is None or verdict.is_clean:
        return
    try:
        hook(label, verdict)
    except Exception:  # pragma: no cover - hook is best effort
        logger.exception("prompt_injection_hook_error")


# ── One-call wrapper ──────────────────────────────────────────────────


def classify_and_wrap(value: Any, *, label: str = "user_input") -> str:
    """Classify ``value`` then return a structurally-wrapped block.

    * ``allow``  -> wrap original text via ``wrap_user_input``.
    * ``redact`` -> wrap the redacted text.
    * ``block``  -> raise :class:`PromptInjectionBlocked` when
      enforcement is on; otherwise behaves like ``redact``.

    Telemetry is emitted for every non-allow verdict via the hook
    installed with :func:`set_telemetry_hook`.
    """
    verdict = classify(value)
    _emit(label, verdict)
    if verdict.is_blocked:
        raise PromptInjectionBlocked(verdict)
    text_to_wrap = verdict.redacted_text if verdict.severity == "redact" else (
        "" if value is None else str(value)
    )
    return wrap_user_input(text_to_wrap, label=label)


__all__ = [
    "InjectionSignal",
    "InjectionVerdict",
    "PromptInjectionBlocked",
    "block_threshold",
    "classify",
    "classify_and_wrap",
    "enforcement_enabled",
    "redact_threshold",
    "set_telemetry_hook",
]
