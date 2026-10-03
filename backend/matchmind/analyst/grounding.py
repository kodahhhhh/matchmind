"""Numbers and citations must be attributable to this answer's tool outputs."""

import re
from collections.abc import Iterator
from typing import Any

CITATION = re.compile(r"\[\[(ev|seq):([^\]]+)\]\]")
NUMBER = re.compile(r"(?<![\w:])-?\d+(?:\.\d+)?")


def numeric_tokens(value: Any) -> set[str]:
    """Extract numerical evidence, excluding identifiers and embedded model names."""
    tokens = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key not in (
                "id",
                "event_id",
                "sequence_id",
                "match_id",
                "player_id",
                "player_off_id",
                "event_ids",
                "key_event_ids",
            ):
                tokens.update(numeric_tokens(item))
    elif isinstance(value, list):
        for item in value:
            tokens.update(numeric_tokens(item))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        tokens.update(NUMBER.findall(str(value)))
    elif isinstance(value, str) and not value.startswith(("sb:", "ev:", "seq:")):
        tokens.update(NUMBER.findall(value))
    return tokens


def references(value: Any) -> set[str]:
    """Event and sequence identifiers explicitly present in a tool result."""
    result = set()
    if isinstance(value, dict):
        for item in value.values():
            result.update(references(item))
    elif isinstance(value, list):
        for item in value:
            result.update(references(item))
    elif isinstance(value, str) and re.fullmatch(r"sb:\d+:(?:\d+|s\d+)", value):
        result.add(("seq:" if ":s" in value else "ev:") + value)
    return result


def display_evidence(value: Any) -> list[str]:
    """Python computes display precision and percentages for the analyst."""
    values = set()

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key not in (
                    "id",
                    "player_id",
                    "player_off_id",
                    "event_id",
                    "sequence_id",
                    "match_id",
                ):
                    visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            values.add(str(item))
            if isinstance(item, float):
                for precision in (0, 1, 2, 3, 4):
                    values.add(f"{item:.{precision}f}")
                if 0 <= item <= 1:
                    values.add(f"{item * 100:.0f}%")
                    values.add(f"{item * 100:.1f}%")

    visit(value)
    return sorted(values)


def grounding_errors(text: str, results: list[dict]) -> dict:
    """Report any unsupported numbers or citations in the candidate answer."""
    numbers = set().union(*(numeric_tokens(r) for r in results)) if results else set()
    refs = set().union(*(references(r) for r in results)) if results else set()
    plain = CITATION.sub("", text)
    unknown_numbers = [n for n in NUMBER.findall(plain) if n not in numbers]
    unknown_refs = [
        f"{kind}:{ref}"
        for kind, ref in CITATION.findall(text)
        if f"{kind}:{ref}" not in refs
    ]
    return {
        "unsupported_numbers": sorted(set(unknown_numbers)),
        "unsupported_citations": sorted(set(unknown_refs)),
    }


def sentences(buffer: str) -> tuple[list[str], str]:
    """Hold incomplete sentences (and decimal points) until validation is possible."""
    end = 0
    parts = []
    for match in re.finditer(r"(?<!\d)[.!?]\s+|(?<=\d)[.!?](?!\d)\s+|\n", buffer):
        parts.append(buffer[end : match.end()])
        end = match.end()
    return parts, buffer[end:]


def text_deltas(text: str) -> Iterator[str]:
    """Small browser-friendly chunks after a complete sentence passes validation."""
    for i in range(0, len(text), 48):
        yield text[i : i + 48]
