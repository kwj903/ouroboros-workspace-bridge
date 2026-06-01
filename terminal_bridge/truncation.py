from __future__ import annotations


def truncate_text(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False

    omitted_chars = len(text) - limit
    marker = f"\n\n... [truncated {omitted_chars} chars] ...\n\n"
    body_limit = max(0, limit - len(marker))
    head_limit = body_limit // 2
    tail_limit = body_limit - head_limit
    tail = text[-tail_limit:] if tail_limit else ""

    return text[:head_limit] + marker[:limit] + tail, True
