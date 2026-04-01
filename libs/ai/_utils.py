"""Internal text processing utilities for AI provider integrations."""

import re
from typing import List


def strip_reasoning_markup(text: str) -> str:
    """Remove <think>...</think> thinking block markers from model output."""
    return re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL).strip()


def normalize_text_for_length_check(text: str) -> str:
    """Normalize text for content-length comparison."""
    return re.sub(r'\s+', '', text).strip()


def preserves_enough_content(
    original_text: str,
    enhanced_text: str,
    min_ratio: float = 0.7,
) -> bool:
    """Check whether enhanced text significantly compressed the original content."""
    original_normalized = normalize_text_for_length_check(original_text)
    enhanced_normalized = normalize_text_for_length_check(enhanced_text)
    if not original_normalized:
        return True
    return len(enhanced_normalized) >= len(original_normalized) * min_ratio


def split_text_for_model(text: str, max_chars: int = 1800) -> List[str]:
    """Split long text into chunks suitable for model API calls."""
    words = text.split()
    if not words:
        return []

    chunks = []
    current_words = []
    current_length = 0

    for word in words:
        if len(word) > max_chars:
            if current_words:
                chunks.append(' '.join(current_words))
                current_words = []
                current_length = 0
            for i in range(0, len(word), max_chars):
                chunks.append(word[i:i + max_chars])
            continue

        extra_length = len(word) + (1 if current_words else 0)
        if current_words and current_length + extra_length > max_chars:
            chunks.append(' '.join(current_words))
            current_words = [word]
            current_length = len(word)
        else:
            current_words.append(word)
            current_length += extra_length

    if current_words:
        chunks.append(' '.join(current_words))

    return chunks
