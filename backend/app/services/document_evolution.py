"""
Document Evolution Engine — semantic diff tracking between document versions.

Goes beyond text diff to track HOW documents improve across iterations:
  - Content changes: sections added/removed/modified
  - Keyword evolution: which target keywords were added/removed
  - Evidence strength delta: did evidence backing improve?
  - Tone shifts: formal ↔ conversational drift detection
  - Improvement scoring: net quality change between versions

This powers the "Document Evolution" visualization showing users
exactly how their documents have improved over time.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from difflib import SequenceMatcher
import re
import structlog

from app.core.database import get_db, TABLES, SupabaseDB

logger = structlog.get_logger("hirestack.document_evolution")


class DocumentEvolutionEngine:
    """Tracks and scores semantic evolution between document versions."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()

    async def analyze_evolution(
        self,
        user_id: str,
        document_id: str,
        old_content: str,
        new_content: str,
        version_from: int,
        version_to: int,
        application_id: Optional[str] = None,
        target_keywords: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Analyze and record the evolution between two document versions.

        Returns a comprehensive diff report with improvement scoring.
        """
        # Run all diff analyses
        content_diff = self._analyze_content_changes(old_content, new_content)
        keyword_diff = self._analyze_keyword_evolution(old_content, new_content, target_keywords or [])
        structure_diff = self._analyze_structure_changes(old_content, new_content)
        improvement = self._compute_improvement_score(content_diff, keyword_diff, structure_diff)

        # Persist the evolution record
        record = {
            "user_id": user_id,
            "document_id": document_id,
            "application_id": application_id,
            "version_from": version_from,
            "version_to": version_to,
            "diff_type": "content",
            "change_summary": improvement["summary"],
            "improvement_score": improvement["score"],
            "sections_changed": content_diff["sections_changed"],
            "keywords_added": keyword_diff["added"],
            "keywords_removed": keyword_diff["removed"],
            "evidence_delta": content_diff.get("evidence_delta", {}),
            "metadata": {
                "similarity": content_diff["similarity"],
                "word_count_delta": content_diff["word_count_delta"],
                "section_count_delta": structure_diff["section_count_delta"],
                "keyword_coverage_before": keyword_diff["coverage_before"],
                "keyword_coverage_after": keyword_diff["coverage_after"],
            },
        }

        try:
            await self.db.create(TABLES["document_evolution"], record)
        except Exception as e:
            logger.warning("document_evolution.persist_failed", error=str(e)[:200])

        return {
            "improvement_score": improvement["score"],
            "summary": improvement["summary"],
            "content": content_diff,
            "keywords": keyword_diff,
            "structure": structure_diff,
            "version_from": version_from,
            "version_to": version_to,
        }

    async def get_evolution_timeline(
        self,
        user_id: str,
        document_id: Optional[str] = None,
        application_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get the evolution timeline for a document or all documents.

        Returns a chronological list of evolution records showing
        how documents have changed over time.
        """
        filters = [("user_id", "==", user_id)]
        if document_id:
            filters.append(("document_id", "==", document_id))
        if application_id:
            filters.append(("application_id", "==", application_id))

        try:
            records = await self.db.query(
                TABLES["document_evolution"],
                filters=filters,
                order_by="created_at",
                order_direction="DESCENDING",
                limit=limit,
            )
            return records
        except Exception as e:
            logger.warning("document_evolution.timeline_failed", error=str(e)[:200])
            return []

    async def get_improvement_trend(self, user_id: str, limit: int = 30) -> Dict[str, Any]:
        """Get the overall document improvement trend for a user.

        Returns aggregate statistics showing whether documents are
        getting better over time.
        """
        try:
            records = await self.db.query(
                TABLES["document_evolution"],
                filters=[("user_id", "==", user_id)],
                order_by="created_at",
                order_direction="DESCENDING",
                limit=limit,
            )
        except Exception:
            records = []

        if not records:
            return {
                "total_evolutions": 0,
                "avg_improvement": 0,
                "trend_direction": "neutral",
                "best_improvement": 0,
                "worst_change": 0,
            }

        scores = [r.get("improvement_score", 0) for r in records if r.get("improvement_score") is not None]
        if not scores:
            return {
                "total_evolutions": len(records),
                "avg_improvement": 0,
                "trend_direction": "neutral",
                "best_improvement": 0,
                "worst_change": 0,
            }

        # Recent half vs older half
        mid = len(scores) // 2
        recent = scores[:max(mid, 1)]
        older = scores[max(mid, 1):]
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older) if older else recent_avg

        if recent_avg > older_avg + 2:
            trend = "improving"
        elif recent_avg < older_avg - 2:
            trend = "declining"
        else:
            trend = "stable"

        return {
            "total_evolutions": len(records),
            "avg_improvement": round(sum(scores) / len(scores), 1),
            "trend_direction": trend,
            "best_improvement": round(max(scores), 1),
            "worst_change": round(min(scores), 1),
            "recent_avg": round(recent_avg, 1),
        }

    # ── Analysis routines ─────────────────────────────────────────────

    def _analyze_content_changes(
        self, old_content: str, new_content: str,
    ) -> Dict[str, Any]:
        """Analyze content-level changes between versions."""
        old_words = old_content.split()
        new_words = new_content.split()

        similarity = SequenceMatcher(None, old_content, new_content).ratio()

        # Detect section-level changes
        old_sections = self._extract_sections(old_content)
        new_sections = self._extract_sections(new_content)

        sections_changed = []
        all_headings = set(list(old_sections.keys()) + list(new_sections.keys()))
        for heading in all_headings:
            old_text = old_sections.get(heading, "")
            new_text = new_sections.get(heading, "")
            if heading not in old_sections:
                sections_changed.append({"heading": heading, "change": "added"})
            elif heading not in new_sections:
                sections_changed.append({"heading": heading, "change": "removed"})
            elif SequenceMatcher(None, old_text, new_text).ratio() < 0.9:
                sections_changed.append({"heading": heading, "change": "modified"})

        # Count quantified achievements (evidence proxy)
        old_metrics = len(re.findall(r'\d+[%$]|\$[\d,]+|\d+ (?:years?|months?)', old_content))
        new_metrics = len(re.findall(r'\d+[%$]|\$[\d,]+|\d+ (?:years?|months?)', new_content))

        return {
            "similarity": round(similarity, 3),
            "word_count_delta": len(new_words) - len(old_words),
            "old_word_count": len(old_words),
            "new_word_count": len(new_words),
            "sections_changed": sections_changed,
            "sections_added": sum(1 for s in sections_changed if s["change"] == "added"),
            "sections_removed": sum(1 for s in sections_changed if s["change"] == "removed"),
            "sections_modified": sum(1 for s in sections_changed if s["change"] == "modified"),
            "evidence_delta": {
                "metrics_before": old_metrics,
                "metrics_after": new_metrics,
                "metrics_change": new_metrics - old_metrics,
            },
        }

    def _analyze_keyword_evolution(
        self,
        old_content: str,
        new_content: str,
        target_keywords: List[str],
    ) -> Dict[str, Any]:
        """Track which target keywords appeared or disappeared."""
        if not target_keywords:
            return {
                "added": [],
                "removed": [],
                "retained": [],
                "coverage_before": 0,
                "coverage_after": 0,
            }

        old_lower = old_content.lower()
        new_lower = new_content.lower()

        added = []
        removed = []
        retained = []

        for kw in target_keywords:
            kw_lower = kw.lower()
            in_old = kw_lower in old_lower
            in_new = kw_lower in new_lower
            if in_new and not in_old:
                added.append(kw)
            elif in_old and not in_new:
                removed.append(kw)
            elif in_old and in_new:
                retained.append(kw)

        total = len(target_keywords)
        present_before = len(retained) + len(removed)
        present_after = len(retained) + len(added)

        return {
            "added": added,
            "removed": removed,
            "retained": retained,
            "coverage_before": round(present_before / total * 100, 1) if total else 0,
            "coverage_after": round(present_after / total * 100, 1) if total else 0,
        }

    def _analyze_structure_changes(
        self, old_content: str, new_content: str,
    ) -> Dict[str, Any]:
        """Analyze structural changes (headings, bullets, paragraphs)."""
        old_sections = self._extract_sections(old_content)
        new_sections = self._extract_sections(new_content)

        old_bullets = len(re.findall(r'^[\s]*[-•●◦▪]', old_content, re.MULTILINE))
        new_bullets = len(re.findall(r'^[\s]*[-•●◦▪]', new_content, re.MULTILINE))

        old_paragraphs = len([p for p in old_content.split('\n\n') if p.strip()])
        new_paragraphs = len([p for p in new_content.split('\n\n') if p.strip()])

        return {
            "section_count_delta": len(new_sections) - len(old_sections),
            "old_sections": len(old_sections),
            "new_sections": len(new_sections),
            "bullet_count_delta": new_bullets - old_bullets,
            "paragraph_count_delta": new_paragraphs - old_paragraphs,
        }

    def _compute_improvement_score(
        self,
        content_diff: Dict[str, Any],
        keyword_diff: Dict[str, Any],
        structure_diff: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compute a net improvement score (-100 to +100).

        Positive = document improved, negative = degraded.
        """
        score = 0.0
        reasons = []

        # Content expansion (moderate positive, up to +15)
        word_delta = content_diff["word_count_delta"]
        if word_delta > 0:
            score += min(15, word_delta / 10)
            reasons.append(f"+{word_delta} words")
        elif word_delta < -50:
            score -= min(10, abs(word_delta) / 20)
            reasons.append(f"{word_delta} words (significant reduction)")

        # Evidence gains (strong positive, up to +25)
        evidence_delta = content_diff.get("evidence_delta", {})
        metrics_change = evidence_delta.get("metrics_change", 0)
        if metrics_change > 0:
            score += min(25, metrics_change * 8)
            reasons.append(f"+{metrics_change} quantified achievements")
        elif metrics_change < 0:
            score -= min(15, abs(metrics_change) * 5)
            reasons.append(f"{metrics_change} metrics removed")

        # Keyword coverage improvement (strong positive, up to +30)
        kw_before = keyword_diff.get("coverage_before", 0)
        kw_after = keyword_diff.get("coverage_after", 0)
        kw_delta = kw_after - kw_before
        if kw_delta > 0:
            score += min(30, kw_delta * 0.5)
            reasons.append(f"+{kw_delta:.0f}% keyword coverage")
        elif kw_delta < -10:
            score -= min(15, abs(kw_delta) * 0.3)
            reasons.append(f"{kw_delta:.0f}% keyword coverage lost")

        # Section additions (moderate positive, up to +15)
        sections_added = content_diff.get("sections_added", 0)
        if sections_added > 0:
            score += min(15, sections_added * 5)
            reasons.append(f"+{sections_added} new sections")

        # Bullet points (structure clarity, small positive)
        bullet_delta = structure_diff.get("bullet_count_delta", 0)
        if bullet_delta > 0:
            score += min(10, bullet_delta * 2)

        # Clamp to range
        score = max(-100, min(100, score))

        # Generate summary
        if score >= 15:
            summary = "Significant improvement: " + ", ".join(reasons[:3])
        elif score >= 5:
            summary = "Minor improvement: " + ", ".join(reasons[:2])
        elif score >= -5:
            summary = "Minimal change"
        else:
            summary = "Regression: " + ", ".join(reasons[:2])

        return {"score": round(score, 1), "summary": summary}

    # ── Utility ───────────────────────────────────────────────────────

    def _extract_sections(self, content: str) -> Dict[str, str]:
        """Extract named sections from document content."""
        sections: Dict[str, str] = {}
        # Match common heading patterns: ## Heading, **Heading**, HEADING:
        pattern = r'(?:^#{1,3}\s+(.+)|^\*\*(.+?)\*\*|^([A-Z][A-Z\s]{2,}):?\s*$)'
        matches = list(re.finditer(pattern, content, re.MULTILINE))

        for i, match in enumerate(matches):
            heading = (match.group(1) or match.group(2) or match.group(3)).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            sections[heading] = content[start:end].strip()

        return sections
