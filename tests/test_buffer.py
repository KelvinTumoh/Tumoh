"""Unit tests for the piece-table TextBuffer."""

import pytest

from ide_core.buffer import TextBuffer


def test_empty_buffer():
    buffer = TextBuffer()
    assert buffer.get_text() == ""
    assert len(buffer) == 0


def test_initial_text():
    buffer = TextBuffer("hello")
    assert buffer.get_text() == "hello"
    assert len(buffer) == 5


def test_insert_at_beginning():
    buffer = TextBuffer("world")
    buffer.insert(0, "hello ")
    assert buffer.get_text() == "hello world"


def test_insert_at_middle():
    buffer = TextBuffer("heo")
    buffer.insert(2, "ll")
    assert buffer.get_text() == "hello"


def test_insert_at_end():
    buffer = TextBuffer("hello")
    buffer.insert(5, " world")
    assert buffer.get_text() == "hello world"


def test_insert_into_empty_buffer():
    buffer = TextBuffer()
    buffer.insert(0, "hello")
    assert buffer.get_text() == "hello"
    assert len(buffer) == 5


def test_insert_empty_string_is_noop():
    buffer = TextBuffer("hello")
    buffer.insert(2, "")
    assert buffer.get_text() == "hello"
    assert len(buffer) == 5


def test_delete_single_piece():
    buffer = TextBuffer("hello world")
    buffer.delete(5, 6)
    assert buffer.get_text() == "helloworld"
    assert len(buffer) == 10


def test_delete_from_start():
    buffer = TextBuffer("hello")
    buffer.delete(0, 2)
    assert buffer.get_text() == "llo"


def test_delete_to_end():
    buffer = TextBuffer("hello")
    buffer.delete(3, 5)
    assert buffer.get_text() == "hel"


def test_delete_across_original_and_add_piece_boundaries():
    buffer = TextBuffer("abc")
    buffer.insert(3, "def")
    assert buffer.get_text() == "abcdef"
    buffer.delete(2, 4)
    assert buffer.get_text() == "abef"


def test_delete_across_multiple_add_pieces():
    buffer = TextBuffer("0123")
    buffer.insert(4, "45")
    buffer.insert(6, "67")
    assert buffer.get_text() == "01234567"
    buffer.delete(2, 6)
    assert buffer.get_text() == "0167"


def test_delete_entire_buffer():
    buffer = TextBuffer("hello")
    buffer.delete(0, 5)
    assert buffer.get_text() == ""
    assert len(buffer) == 0


def test_zero_length_delete_is_noop():
    buffer = TextBuffer("hello")
    buffer.delete(2, 2)
    assert buffer.get_text() == "hello"


def test_repeated_insert_delete_cycles():
    buffer = TextBuffer("a")
    buffer.insert(1, "b")
    buffer.insert(2, "c")
    buffer.delete(1, 2)
    buffer.insert(1, "x")
    assert buffer.get_text() == "axc"


def test_insert_out_of_bounds_raises():
    buffer = TextBuffer("hi")
    with pytest.raises(IndexError):
        buffer.insert(3, "!")


def test_insert_negative_index_raises():
    buffer = TextBuffer("hi")
    with pytest.raises(IndexError):
        buffer.insert(-1, "!")


def test_delete_out_of_bounds_raises():
    buffer = TextBuffer("hi")
    with pytest.raises(IndexError):
        buffer.delete(0, 3)


def test_delete_negative_index_raises():
    buffer = TextBuffer("hi")
    with pytest.raises(IndexError):
        buffer.delete(-1, 1)


def test_delete_with_end_before_start_raises():
    buffer = TextBuffer("hi")
    with pytest.raises(ValueError):
        buffer.delete(2, 1)


def test_get_text_after_many_edits():
    buffer = TextBuffer("The quick ")
    buffer.insert(10, "brown fox")
    buffer.insert(19, " jumps")
    buffer.delete(0, 4)
    buffer.delete(12, 16)
    assert buffer.get_text() == "quick brown jumps"
