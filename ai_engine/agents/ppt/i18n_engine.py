"""
i18nEngine — Multi-language presentation generation.

Handles translation and localization of entire presentations:
- Deck translation to target languages
- Number/currency formatting by locale
- Date format localization
- Right-to-left (RTL) language support preparation
- Cultural adaptation of content

Public API:
    i18nEngine().translate_deck(deck, target_lang) -> DeckSpec
    i18nEngine().localize_number(value, locale) -> str
    i18nEngine().localize_date(date, locale) -> str
    i18nEngine().format_currency(amount, currency, locale) -> str

Supported Languages:
    en, es, fr, de, it, pt, nl, ru, zh, ja, ko, ar, hi
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from ai_engine.agents.ppt.schemas import ChartSpec, DeckSpec, SlideSpec

logger = logging.getLogger(__name__)


@dataclass
class LocaleConfig:
    """Configuration for a locale."""

    code: str
    name: str
    rtl: bool  # Right-to-left
    date_format: str
    time_format: str
    decimal_sep: str
    thousands_sep: str
    currency_symbol: str
    currency_position: str  # "before" or "after"


class I18nEngine:
    """Internationalization and localization engine."""

    # Supported locales
    LOCALES: Dict[str, LocaleConfig] = {
        "en": LocaleConfig("en", "English", False, "%m/%d/%Y", "%I:%M %p", ".", ",", "$", "before"),
        "es": LocaleConfig("es", "Spanish", False, "%d/%m/%Y", "%H:%M", ",", ".", "€", "after"),
        "fr": LocaleConfig("fr", "French", False, "%d/%m/%Y", "%H:%M", ",", " ", "€", "after"),
        "de": LocaleConfig("de", "German", False, "%d.%m.%Y", "%H:%M", ",", ".", "€", "after"),
        "it": LocaleConfig("it", "Italian", False, "%d/%m/%Y", "%H:%M", ",", ".", "€", "after"),
        "pt": LocaleConfig("pt", "Portuguese", False, "%d/%m/%Y", "%H:%M", ",", ".", "€", "after"),
        "nl": LocaleConfig("nl", "Dutch", False, "%d-%m-%Y", "%H:%M", ",", ".", "€", "after"),
        "ru": LocaleConfig("ru", "Russian", False, "%d.%m.%Y", "%H:%M", ",", " ", "₽", "after"),
        "zh": LocaleConfig("zh", "Chinese", False, "%Y/%m/%d", "%H:%M", ".", ",", "¥", "before"),
        "ja": LocaleConfig("ja", "Japanese", False, "%Y/%m/%d", "%H:%M", ".", ",", "¥", "before"),
        "ko": LocaleConfig("ko", "Korean", False, "%Y.%m.%d", "%H:%M", ".", ",", "₩", "before"),
        "ar": LocaleConfig("ar", "Arabic", True, "%d/%m/%Y", "%H:%M", ".", ",", "د.إ", "after"),
        "hi": LocaleConfig("hi", "Hindi", False, "%d/%m/%Y", "%H:%M", ".", ",", "₹", "before"),
    }

    def __init__(self, ai_client: Optional[Any] = None) -> None:
        self.ai_client = ai_client
        self._translation_cache: Dict[Tuple[str, str, str], str] = {}

    def _get_client(self) -> Any:
        """Lazy load AI client."""
        if self.ai_client is not None:
            return self.ai_client
        from ai_engine.client import get_ai_client
        return get_ai_client()

    # ───────────────────────────────────────────────────────────────────────
    #  Deck Translation
    # ───────────────────────────────────────────────────────────────────────

    async def translate_deck(
        self,
        deck: DeckSpec,
        target_lang: str,
        source_lang: str = "auto",
    ) -> DeckSpec:
        """
        Translate entire presentation to target language.

        Args:
            deck: Original deck
            target_lang: Target language code (e.g., 'es', 'fr')
            source_lang: Source language or 'auto' for detection

        Returns:
            Translated DeckSpec
        """
        if target_lang not in self.LOCALES:
            logger.warning("unsupported_target_language: %s", target_lang)
            return deck

        if source_lang != "auto" and source_lang not in self.LOCALES:
            logger.warning("unsupported_source_language: %s", source_lang)
            source_lang = "auto"

        # Translate deck metadata
        translated_title = await self._translate_text(
            deck.title, target_lang, source_lang, context="presentation title"
        )
        translated_subtitle = None
        if deck.subtitle:
            translated_subtitle = await self._translate_text(
                deck.subtitle, target_lang, source_lang, context="presentation subtitle"
            )

        # Translate slides
        translated_slides = []
        for slide in deck.slides:
            translated_slide = await self._translate_slide(
                slide, target_lang, source_lang
            )
            translated_slides.append(translated_slide)

        # Update locale info
        locale = self.LOCALES[target_lang]

        return DeckSpec(
            title=translated_title,
            subtitle=translated_subtitle,
            author=deck.author,
            audience=deck.audience,
            theme=deck.theme,
            accent_color=deck.accent_color,
            slides=translated_slides,
        )

    async def _translate_slide(
        self,
        slide: SlideSpec,
        target_lang: str,
        source_lang: str,
    ) -> SlideSpec:
        """Translate a single slide."""
        updates = {}

        # Translate title
        if slide.title:
            updates["title"] = await self._translate_text(
                slide.title, target_lang, source_lang, context="slide title"
            )

        # Translate subtitle
        if slide.subtitle:
            updates["subtitle"] = await self._translate_text(
                slide.subtitle, target_lang, source_lang
            )

        # Translate bullets
        if slide.bullets:
            translated_bullets = []
            for bullet in slide.bullets:
                translated = await self._translate_text(bullet, target_lang, source_lang)
                translated_bullets.append(translated)
            updates["bullets"] = translated_bullets

        # Translate body
        if slide.body:
            updates["body"] = await self._translate_text(
                slide.body, target_lang, source_lang
            )

        # Translate notes
        if slide.notes:
            updates["notes"] = await self._translate_text(
                slide.notes, target_lang, source_lang, context="speaker notes"
            )

        # Translate caption
        if slide.caption:
            updates["caption"] = await self._translate_text(
                slide.caption, target_lang, source_lang
            )

        return slide.model_copy(update=updates) if updates else slide

    async def _translate_text(
        self,
        text: str,
        target_lang: str,
        source_lang: str = "auto",
        context: str = "",
    ) -> str:
        """Translate a text string."""
        if not text or not text.strip():
            return text

        # Check cache
        cache_key = (text, target_lang, source_lang)
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]

        # Try AI translation
        try:
            translated = await self._ai_translate(text, target_lang, source_lang, context)
            self._translation_cache[cache_key] = translated
            return translated
        except Exception as exc:
            logger.debug("translation_failed: %s", str(exc)[:200])
            return text  # Return original on failure

    async def _ai_translate(
        self,
        text: str,
        target_lang: str,
        source_lang: str,
        context: str = "",
    ) -> str:
        """Use AI for translation."""
        client = self._get_client()

        lang_name = self.LOCALES.get(target_lang, LocaleConfig("en", "English", False, "", "", ".", ",", "$", "before")).name

        prompt = f"""Translate the following text to {lang_name}.

Text: "{text}"

Context: {context or "general business content"}

Requirements:
- Maintain professional business tone
- Keep formatting (bullet points, punctuation)
- Ensure accuracy for business terminology
- Output ONLY the translation, nothing else"""

        response = await client.complete(
            prompt=prompt,
            system="You are a professional translator specializing in business presentations.",
            max_tokens=len(text.split()) * 2 + 50,
            temperature=0.3,
        )

        return response.strip().strip('"')

    # ───────────────────────────────────────────────────────────────────────
    #  Number/Date Localization
    # ───────────────────────────────────────────────────────────────────────

    def localize_number(self, value: float, locale_code: str) -> str:
        """
        Format number according to locale conventions.

        Args:
            value: Numeric value
            locale_code: Locale code (e.g., 'de', 'en')

        Returns:
            Localized number string
        """
        locale = self.LOCALES.get(locale_code, self.LOCALES["en"])

        # Format with thousands separator
        if value == int(value):
            formatted = f"{int(value):,}"
        else:
            formatted = f"{value:,.2f}"

        # Apply locale separators
        if locale.decimal_sep != ".":
            formatted = formatted.replace(".", locale.decimal_sep)
        if locale.thousands_sep != ",":
            formatted = formatted.replace(",", locale.thousands_sep)

        return formatted

    def format_currency(
        self,
        amount: float,
        currency: str = "USD",
        locale_code: str = "en",
    ) -> str:
        """
        Format currency according to locale.

        Args:
            amount: Monetary amount
            currency: Currency code (USD, EUR, GBP, etc.)
            locale_code: Locale code

        Returns:
            Formatted currency string
        """
        locale = self.LOCALES.get(locale_code, self.LOCALES["en"])

        # Format number
        formatted = self.localize_number(amount, locale_code)

        # Get currency symbol
        symbol = self._get_currency_symbol(currency, locale_code)

        # Position symbol
        if locale.currency_position == "before":
            return f"{symbol}{formatted}"
        else:
            return f"{formatted} {symbol}"

    def localize_date(self, dt: date, locale_code: str) -> str:
        """
        Format date according to locale.

        Args:
            dt: Date object
            locale_code: Locale code

        Returns:
            Formatted date string
        """
        locale = self.LOCALES.get(locale_code, self.LOCALES["en"])
        return dt.strftime(locale.date_format)

    def localize_datetime(self, dt: datetime, locale_code: str) -> str:
        """
        Format datetime according to locale.

        Args:
            dt: Datetime object
            locale_code: Locale code

        Returns:
            Formatted datetime string
        """
        locale = self.LOCALES.get(locale_code, self.LOCALES["en"])
        date_part = dt.strftime(locale.date_format)
        time_part = dt.strftime(locale.time_format)
        return f"{date_part} {time_part}"

    def _get_currency_symbol(self, currency: str, locale_code: str) -> str:
        """Get currency symbol for code."""
        symbols = {
            "USD": "$",
            "EUR": "€",
            "GBP": "£",
            "JPY": "¥",
            "CNY": "¥",
            "KRW": "₩",
            "INR": "₹",
            "RUB": "₽",
            "BRL": "R$",
            "CAD": "C$",
            "AUD": "A$",
            "CHF": "CHF",
            "SEK": "kr",
            "NOK": "kr",
            "DKK": "kr",
            "PLN": "zł",
            "MXN": "$",
        }
        return symbols.get(currency.upper(), currency)

    def is_rtl(self, locale_code: str) -> bool:
        """Check if language is right-to-left."""
        locale = self.LOCALES.get(locale_code)
        return locale.rtl if locale else False

    def get_supported_locales(self) -> List[str]:
        """Get list of supported locale codes."""
        return list(self.LOCALES.keys())


# Convenience functions

async def translate_presentation(deck: DeckSpec, target_lang: str) -> DeckSpec:
    """One-shot deck translation."""
    engine = I18nEngine()
    return await engine.translate_deck(deck, target_lang)


def format_localized_number(value: float, locale: str = "en") -> str:
    """One-shot number localization."""
    engine = I18nEngine()
    return engine.localize_number(value, locale)

