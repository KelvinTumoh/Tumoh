"""Efficient flat offset <-> LSP line/character position conversion."""

from ide_core.lsp.protocol import Position


def offset_to_position(text: str, offset: int) -> Position:
    """Convert a flat 0-indexed offset into an LSP ``Position``.

    The position is computed by counting the newlines that appear strictly
    before ``offset`` and measuring the distance from the most recent one.
    """
    if offset < 0 or offset > len(text):
        raise IndexError(f"Offset {offset} out of range [0, {len(text)}]")

    line = text.count("\n", 0, offset)
    last_newline = text.rfind("\n", 0, offset)
    character = offset if last_newline == -1 else offset - last_newline - 1
    return Position(line=line, character=character)


def position_to_offset(text: str, position: Position) -> int:
    """Convert an LSP ``Position`` into a flat 0-indexed offset."""
    if position.line < 0 or position.character < 0:
        raise ValueError("Position line and character must be non-negative")

    line_start = -1
    for _ in range(position.line):
        line_start = text.find("\n", line_start + 1)
        if line_start == -1:
            raise IndexError(f"Line {position.line} out of range")

    line_end = text.find("\n", line_start + 1)
    if line_end == -1:
        line_end = len(text)

    max_character = line_end - (line_start + 1)
    if position.character > max_character:
        raise IndexError(
            f"Character {position.character} out of range for line {position.line} "
            f"(max {max_character})"
        )

    return line_start + 1 + position.character
