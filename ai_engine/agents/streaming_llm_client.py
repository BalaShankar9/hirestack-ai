"""
StreamingAIClient — Token-Level Streaming with Agentic Events
===============================================================
Wraps any AI client (OpenAI, Anthropic, etc.) to emit world-class
streaming events while generating content.

Features:
  • Word-by-word streaming (not just chunks)
  • Paragraph boundary detection
  • Live citation extraction
  • Quality signal emission
  • Accumulated text tracking per agent

Version: 2.0.0
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple

from .streaming_protocol import (
    AgentContext,
    EventMetadata,
    EventType,
    StageContext,
    StageTimer,
    StreamPriority,
)
from .agentic_event_emitter import AgenticEventEmitter


class StreamingAIClient:
    """
    Wrapper around base AI client optimized for world-class token streaming.

    Buffers tokens into words/phrases for readability while maintaining
    sub-100ms latency to the frontend.
    """

    def __init__(
        self,
        base_client: Any,
        emitter: AgenticEventEmitter,
    ) -> None:
        self.base = base_client
        self.emitter = emitter

        # Buffer management
        self._word_buffer: Dict[str, str] = {}  # agent_id → buffer
        self._accumulated: Dict[str, str] = {}  # agent_id → full text
        self._last_analysis: Dict[str, float] = {}  # agent_id → timestamp
        self._paragraph_count: Dict[str, int] = {}

        # Token counting (if tiktoken available)
        self._encoder = None
        try:
            import tiktoken
            self._encoder = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            pass

    # ── Public Streaming Interface ────────────────────────────────

    async def complete_streaming(
        self,
        *,
        prompt: str,
        agent_id: str,
        agent_name: str = "drafter",
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        model: Optional[str] = None,
        on_token: Optional[Callable[[str], None]] = None,
        section_name: Optional[str] = None,
    ) -> str:
        """
        Stream a completion with full event emission.

        Returns the full accumulated text when complete.
        """
        # Initialize buffers
        self._word_buffer[agent_id] = ""
        self._accumulated[agent_id] = ""
        self._paragraph_count[agent_id] = 0

        # Emit generation start
        prompt_tokens = self._count_tokens(prompt)
        await self.emitter.emit(
            event_type=EventType.GENERATION_STARTED,
            payload={
                "prompt_tokens": prompt_tokens,
                "max_tokens_requested": max_tokens,
                "temperature": temperature,
                "model": model or "default",
                "section_name": section_name,
            },
            agent=AgentContext(id=agent_id, name=agent_name, type=agent_name),
            stage=StageContext(name="content_generation", iteration=1, depth=0),
            priority=StreamPriority.HIGH,
        )

        # Emit start token
        await self.emitter.emit_token_stream(
            agent_id=agent_id,
            token="",
            is_start=True,
        )

        async_timer = StageTimer()
        tokens_out = 0
        last_emit = time.monotonic()

        async with async_timer:
            async for chunk in self._stream_completion(
                prompt=prompt,
                system=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model,
            ):
                token = chunk.content if hasattr(chunk, "content") else str(chunk)
                tokens_out += 1

                # Process token
                await self._process_token(
                    agent_id=agent_id,
                    token=token,
                    on_token=on_token,
                    section_name=section_name,
                )

                # Periodic analysis every 100ms
                if time.monotonic() - last_emit > 0.1:
                    await self._analyze_partial_content(agent_id)
                    last_emit = time.monotonic()

        # Flush remaining buffer
        remaining = self._word_buffer.get(agent_id, "")
        if remaining:
            await self.emitter.emit_token_stream(
                agent_id=agent_id,
                token=remaining,
            )
            if on_token:
                on_token(remaining)

        # Emit end token
        full_text = self._accumulated.get(agent_id, "")
        await self.emitter.emit_token_stream(
            agent_id=agent_id,
            token="",
            is_end=True,
        )

        # Detect and emit paragraph completions
        await self._detect_paragraphs(agent_id, full_text, section_name)

        # Extract and emit citations
        citations = await self._extract_citations(full_text)
        for citation in citations:
            await self.emitter.emit_citation(
                agent_id=agent_id,
                citation=citation,
                section_name=section_name,
            )

        # Emit generation completed
        await self.emitter.emit(
            event_type=EventType.GENERATION_COMPLETED,
            payload={
                "total_tokens": tokens_out,
                "total_characters": len(full_text),
                "paragraphs": self._paragraph_count.get(agent_id, 0),
                "citations_found": len(citations),
                "section_name": section_name,
                "duration_ms": async_timer.elapsed_ms,
            },
            agent=AgentContext(id=agent_id, name=agent_name, type=agent_name),
            stage=StageContext(name="content_generation", iteration=1, depth=0),
            priority=StreamPriority.HIGH,
            metadata=EventMetadata(
                latency_ms=async_timer.elapsed_ms,
                tokens_in=prompt_tokens,
                tokens_out=tokens_out,
                cost_usd=self._estimate_cost(prompt_tokens, tokens_out, model),
            ),
        )

        # Cleanup
        self._word_buffer.pop(agent_id, None)
        self._accumulated.pop(agent_id, None)
        self._paragraph_count.pop(agent_id, None)

        return full_text

    async def stream_thinking(
        self,
        *,
        prompt: str,
        agent_id: str,
        reasoning_type: str = "planning",
        chunk_size: int = 5,
    ) -> str:
        """
        Stream agent's reasoning/thought process separately from content.
        """
        await self.emitter.emit(
            event_type=EventType.REASONING_STARTED,
            payload={
                "reasoning_type": reasoning_type,
                "prompt_summary": prompt[:200] + "..." if len(prompt) > 200 else prompt,
            },
            agent=AgentContext(id=agent_id, name="researcher", type="researcher"),
            stage=StageContext(name="reasoning", iteration=1, depth=0),
            priority=StreamPriority.NORMAL,
        )

        full_thought = ""
        confidence = 0.0

        async for chunk in self._stream_completion(
            prompt=prompt,
            temperature=0.3,  # Lower temp for reasoning
            max_tokens=1000,
        ):
            token = chunk.content if hasattr(chunk, "content") else str(chunk)
            full_thought += token

            # Emit in word chunks for readability
            words = full_thought.split()
            if len(words) >= chunk_size:
                chunk_text = " ".join(words[-chunk_size:])
                confidence = self._estimate_confidence(full_thought)
                await self.emitter.emit_thought_stream(
                    agent_id=agent_id,
                    thought_chunk=chunk_text + " ",
                    reasoning_type=reasoning_type,
                    confidence=confidence,
                )
                await asyncio.sleep(0.05)  # Natural reading pace

        await self.emitter.emit(
            event_type=EventType.REASONING_COMPLETED,
            payload={
                "reasoning_type": reasoning_type,
                "final_confidence": round(confidence, 3),
                "thought_length": len(full_thought),
            },
            agent=AgentContext(id=agent_id, name="researcher", type="researcher"),
            stage=StageContext(name="reasoning", iteration=1, depth=0),
            priority=StreamPriority.NORMAL,
        )

        return full_thought

    # ── Private Helpers ───────────────────────────────────────────

    async def _stream_completion(
        self,
        *,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        model: Optional[str] = None,
    ) -> AsyncIterator[Any]:
        """Adapter to base client's streaming interface."""
        # Try common streaming interfaces
        if hasattr(self.base, "stream_complete"):
            async for chunk in self.base.stream_complete(
                prompt=prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model,
            ):
                yield chunk
        elif hasattr(self.base, "complete_stream"):
            async for chunk in self.base.complete_stream(
                prompt=prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yield chunk
        elif hasattr(self.base, "async_stream"):
            async for chunk in self.base.async_stream(prompt):
                yield chunk
        else:
            # Fallback: non-streaming, yield entire response
            response = await self.base.complete(prompt) if asyncio.iscoroutinefunction(self.base.complete) else self.base.complete(prompt)
            class _Chunk:
                content = response if isinstance(response, str) else str(response)
            yield _Chunk()

    async def _process_token(
        self,
        *,
        agent_id: str,
        token: str,
        on_token: Optional[Callable[[str], None]],
        section_name: Optional[str],
    ) -> None:
        """Buffer tokens and emit words/phrases."""
        self._accumulated[agent_id] = self._accumulated.get(agent_id, "") + token

        # Detect word boundaries
        buf = self._word_buffer.get(agent_id, "") + token
        self._word_buffer[agent_id] = buf

        word_boundary = token in " \n.!?;:," or len(buf) > 15

        if word_boundary:
            await self.emitter.emit_token_stream(
                agent_id=agent_id,
                token=buf,
            )
            if on_token:
                on_token(buf)
            self._word_buffer[agent_id] = ""

    async def _detect_paragraphs(
        self,
        agent_id: str,
        text: str,
        section_name: Optional[str],
    ) -> None:
        """Detect paragraph boundaries and emit completion events."""
        paragraphs = text.split('\n\n')
        prev_count = self._paragraph_count.get(agent_id, 0)

        for i, para in enumerate(paragraphs[:-1]):  # All but last (incomplete)
            if i >= prev_count and para.strip():
                await self.emitter.emit(
                    event_type=EventType.PARAGRAPH_COMPLETED,
                    payload={
                        "paragraph_index": i,
                        "paragraph_preview": para[:200] + "..." if len(para) > 200 else para,
                        "word_count": len(para.split()),
                        "section_name": section_name,
                    },
                    agent=AgentContext(id=agent_id, name="drafter", type="drafter"),
                    stage=StageContext(name="content_generation", iteration=1, depth=0),
                    priority=StreamPriority.NORMAL,
                )
                self._paragraph_count[agent_id] = i + 1

    async def _analyze_partial_content(self, agent_id: str) -> None:
        """Analyze partial content and emit quality signals."""
        text = self._accumulated.get(agent_id, "")
        if len(text) < 50:
            return

        last_200 = text[-200:]

        signals = {
            "has_metrics": bool(re.search(r'\d+%|\d+\s*(years?|months?)', last_200)),
            "has_action_verbs": any(v in text.lower() for v in ["led", "developed", "increased", "created", "designed", "implemented"]),
            "has_quantification": bool(re.search(r'\d+\s*(\+|%)', last_200)),
            "section_progress": self._detect_section_progress(text),
            "accumulated_length": len(text),
        }

        await self.emitter.emit(
            event_type=EventType.GENERATION_QUALITY_SIGNAL,
            payload=signals,
            agent=AgentContext(id=agent_id, name="drafter", type="drafter"),
            stage=StageContext(name="content_generation", iteration=1, depth=0),
            priority=StreamPriority.LOW,
        )

    async def _extract_citations(self, text: str) -> List[Dict[str, Any]]:
        """Extract citation patterns from text."""
        citations = []

        # URL citations
        url_pattern = r'https?://[^\s\)\"\'\>\]]+'
        for match in re.finditer(url_pattern, text):
            citations.append({
                "type": "url",
                "text": match.group(0)[:100],
                "position": match.start(),
            })

        # Reference citations [1], [2], etc.
        ref_pattern = r'\[\d+\]'
        for match in re.finditer(ref_pattern, text):
            citations.append({
                "type": "reference",
                "text": match.group(0),
                "position": match.start(),
            })

        # Named citations (e.g., "According to Gartner...")
        org_pattern = r'(?:According to|Per|As reported by)\s+([A-Z][\w\s]+)'
        for match in re.finditer(org_pattern, text):
            citations.append({
                "type": "attribution",
                "text": match.group(1),
                "position": match.start(),
            })

        return citations

    # ── Utility Methods ──────────────────────────────────────────

    def _count_tokens(self, text: str) -> int:
        """Estimate token count."""
        if self._encoder:
            return len(self._encoder.encode(text))
        return len(text) // 4  # Rough estimate

    def _estimate_cost(
        self,
        tokens_in: int,
        tokens_out: int,
        model: Optional[str] = None,
    ) -> float:
        """Rough cost estimation."""
        model = model or "gpt-4o"
        rates = {
            "gpt-4o": (5.0 / 1_000_000, 15.0 / 1_000_000),  # input, output per token
            "gpt-4o-mini": (0.15 / 1_000_000, 0.6 / 1_000_000),
            "gpt-4": (30.0 / 1_000_000, 60.0 / 1_000_000),
        }
        input_rate, output_rate = rates.get(model, rates["gpt-4o"])
        return (tokens_in * input_rate) + (tokens_out * output_rate)

    def _estimate_confidence(self, thought: str) -> float:
        """Estimate confidence from reasoning text heuristics."""
        confidence = 0.5

        # Increase for certainty words
        if any(w in thought.lower() for w in ["confident", "certain", "clearly", "definitely"]):
            confidence += 0.2

        # Decrease for uncertainty
        if any(w in thought.lower() for w in ["uncertain", "unclear", "might", "possibly", "unsure"]):
            confidence -= 0.15

        # Increase for numerical specificity
        if re.search(r'\d+', thought):
            confidence += 0.1

        # Increase for evidence references
        if re.search(r'according to|source|reference', thought, re.I):
            confidence += 0.1

        return max(0.0, min(1.0, confidence))

    def _detect_section_progress(self, text: str) -> str:
        """Detect which resume section we're in."""
        lower = text.lower()
        sections = [
            ("summary", ["summary", "professional summary", "about me"]),
            ("experience", ["experience", "work experience", "employment"]),
            ("skills", ["skills", "technical skills", "competencies"]),
            ("education", ["education", "academic", "degree"]),
            ("projects", ["projects", "project highlights"]),
        ]

        for section, keywords in reversed(sections):
            for kw in keywords:
                if kw in lower[-500:]:  # Look at last 500 chars
                    return section
        return "unknown"
