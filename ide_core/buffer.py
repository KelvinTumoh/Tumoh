"""Piece-table based text buffer engine for the IDE."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class _Source(str, Enum):
    """Identifies the immutable source buffer a piece refers to."""

    ORIGINAL = "original"
    ADD = "add"


@dataclass(frozen=True)
class _Piece:
    """A contiguous span of text inside one of the source buffers."""

    source: _Source
    start: int
    length: int


class TextBuffer:
    """A text buffer backed by an immutable piece table.

    The buffer is composed of an ordered list of pieces, each of which
    references a span in one of two immutable source buffers:

    * ``original``: the initial text supplied at construction.
    * ``add``: all text ever inserted; only appended to.

    This design makes edits non-destructive and naturally supports
    operations such as undo, redo, or snapshotting.

    Attributes:
        _original: The initial text string; never modified.
        _add: List of characters accumulated from every insertion.
        _pieces: Ordered list of pieces describing the current text.
        _length: Total number of logical characters.
    """

    def __init__(self, text: str = "") -> None:
        self._original: str = text
        self._add: list[str] = []
        self._pieces: list[_Piece] = (
            [_Piece(_Source.ORIGINAL, 0, len(text))] if text else []
        )
        self._length: int = len(text)

    def __len__(self) -> int:
        """Return the number of characters in the buffer."""
        return self._length

    def __repr__(self) -> str:
        return f"TextBuffer({self.get_text()!r})"

    def get_text(self) -> str:
        """Return the buffer's full content as a single string."""
        return "".join(self._render_piece(piece) for piece in self._pieces)

    def insert(self, index: int, text: str) -> None:
        """Insert ``text`` at logical ``index``."""
        if not text:
            return

        if index < 0 or index > self._length:
            raise IndexError(
                f"Insert index {index} out of range [0, {self._length}]"
            )

        piece_index, local_offset = self._locate(index)
        left, right = self._split_at(piece_index, local_offset)

        add_start = len(self._add)
        self._add.extend(text)
        new_piece = _Piece(_Source.ADD, add_start, len(text))

        self._pieces = left + [new_piece] + right
        self._length += len(text)

    def delete(self, start: int, end: int) -> None:
        """Delete characters from ``start`` up to (but not including) ``end``."""
        if end < start:
            raise ValueError(f"End {end} is less than start {start}")

        if start < 0 or end > self._length:
            raise IndexError(
                f"Delete range [{start}, {end}) out of bounds"
            )

        if start == end:
            return

        start_index, start_offset = self._locate(start)
        end_index, end_offset = self._locate(end)

        left = self._prefix(start_index, start_offset)
        right = self._suffix(end_index, end_offset)

        self._pieces = left + right
        self._length -= end - start

    def _locate(self, index: int) -> tuple[int, int]:
        """Map a logical position to the containing piece and local offset.

        If ``index`` equals the buffer length, the returned piece index is
        ``len(self._pieces)`` and the offset is zero, representing a cursor
        after the last character.
        """
        remaining = index
        for i, piece in enumerate(self._pieces):
            if remaining < piece.length:
                return i, remaining
            remaining -= piece.length
        return len(self._pieces), 0

    def _split_at(
        self, piece_index: int, local_offset: int
    ) -> tuple[list[_Piece], list[_Piece]]:
        """Return the left and right piece lists around an insertion point.

        The cursor is at ``piece_index`` / ``local_offset`` using insertion-
        point semantics: a zero offset sits at the start of the piece, and
        the end of the buffer is represented by
        ``piece_index == len(self._pieces)``.
        """
        if piece_index == len(self._pieces):
            return list(self._pieces), []

        piece = self._pieces[piece_index]

        if local_offset == 0:
            left: list[_Piece] = self._pieces[:piece_index]
            right: list[_Piece] = list(self._pieces[piece_index:])
        elif local_offset == piece.length:
            left = self._pieces[: piece_index + 1]
            right = list(self._pieces[piece_index + 1 :])
        else:
            left = list(self._pieces[:piece_index]) + [
                _Piece(piece.source, piece.start, local_offset)
            ]
            right = [
                _Piece(
                    piece.source,
                    piece.start + local_offset,
                    piece.length - local_offset,
                )
            ] + list(self._pieces[piece_index + 1 :])

        return left, right

    def _prefix(self, piece_index: int, local_offset: int) -> list[_Piece]:
        """Return the pieces kept to the left of a delete start cursor."""
        if local_offset == 0:
            return list(self._pieces[:piece_index])

        piece = self._pieces[piece_index]
        return list(self._pieces[:piece_index]) + [
            _Piece(piece.source, piece.start, local_offset)
        ]

    def _suffix(self, piece_index: int, local_offset: int) -> list[_Piece]:
        """Return the pieces kept to the right of a delete end cursor."""
        if local_offset == 0:
            return list(self._pieces[piece_index:])

        piece = self._pieces[piece_index]
        return [
            _Piece(
                piece.source,
                piece.start + local_offset,
                piece.length - local_offset,
            )
        ] + list(self._pieces[piece_index + 1 :])

    def _render_piece(self, piece: _Piece) -> str:
        """Return the string content represented by a single piece."""
        if piece.source == _Source.ORIGINAL:
            return self._original[piece.start : piece.start + piece.length]
        return "".join(self._add[piece.start : piece.start + piece.length])
