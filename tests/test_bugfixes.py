"""Regression tests for bugs found and fixed during the project-wide bug sweep.

Each test pins a specific fix so the bug cannot silently reappear.
"""
import os
import tempfile

import pytest

from prompt_builder import _matches_intent, _is_destructive_or_sensitive_tool
from tools.file_ops import edit_file
from tools.codebase_ops import _chunk_text
from tools.system_ops import _parse_session_id, _process_carriage_returns
from error_classifier import classify_api_error, FailoverReason


# --- _chunk_text: must never infinite-loop, regardless of overlap/chunk_size ---

@pytest.mark.parametrize("chunk_size,overlap", [
    (50, 50),    # overlap == chunk_size (previously hung)
    (50, 100),   # overlap > chunk_size (previously hung)
    (0, 10),     # non-positive chunk_size
    (1500, 200), # defaults
])
def test_chunk_text_terminates(chunk_size, overlap):
    chunks = _chunk_text("x" * 300, chunk_size=chunk_size, overlap=overlap)
    assert isinstance(chunks, list)
    assert len(chunks) >= 1
    # whole text must be covered by the concatenated leading edges
    assert "".join(chunks)  # non-empty


def test_chunk_text_empty():
    assert _chunk_text("") == []


# --- _matches_intent: whole-word negations (no false "no" inside "now"/"know") ---

@pytest.mark.parametrize("msg,triggers,expected", [
    ("Now refactor the code", ["refactor"], True),
    ("I know you should deploy this", ["deploy"], True),
    ("do another optimize pass", ["optimize"], True),
    ("monitor and then deploy", ["deploy"], True),
    # genuine negations must still suppress the trigger
    ("please don't refactor this", ["refactor"], False),
    ("do not deploy", ["deploy"], False),
    ("never refactor", ["refactor"], False),
    ("avoid optimize", ["optimize"], False),
])
def test_matches_intent_negation_word_boundaries(msg, triggers, expected):
    assert _matches_intent(msg, triggers) is expected


# --- edit_file: must refuse ambiguous (non-unique) replacements ---

def test_edit_file_rejects_ambiguous_match():
    cwd = os.getcwd()
    d = tempfile.mkdtemp()
    try:
        os.chdir(d)
        with open("f.txt", "w") as fh:
            fh.write("foo\nbar\nfoo\n")
        res = edit_file("f.txt", "foo", "X")
        assert "appears 2 times" in res
        # file must be untouched on an ambiguous edit
        with open("f.txt") as fh:
            assert fh.read() == "foo\nbar\nfoo\n"
    finally:
        os.chdir(cwd)


def test_edit_file_applies_unique_match():
    cwd = os.getcwd()
    d = tempfile.mkdtemp()
    try:
        os.chdir(d)
        with open("g.txt", "w") as fh:
            fh.write("alpha\nbeta\n")
        res = edit_file("g.txt", "beta", "BETA")
        assert "Successfully edited" in res
        with open("g.txt") as fh:
            assert fh.read() == "alpha\nBETA\n"
    finally:
        os.chdir(cwd)


# --- _is_destructive_or_sensitive_tool: fail-safe verb heuristic ---

@pytest.mark.parametrize("tool,expected", [
    ("memory_delete", True),      # was missing from the explicit set
    ("kill_process", True),       # was missing from the explicit set
    ("drop_table", True),         # caught by heuristic
    ("delete_file", True),
    # not destructive, and "skill" must not match the "kill" verb
    ("list_skills", False),
    ("read_skill", False),
    ("web_search", False),
    ("read_file", False),
])
def test_destructive_tool_detection(tool, expected):
    assert _is_destructive_or_sensitive_tool(tool) is expected


# --- classify_api_error: branch coverage for retry/failover decisions ---

@pytest.mark.parametrize("text,reason,retryable", [
    ("context_length_exceeded", FailoverReason.CONTEXT_OVERFLOW, True),
    ("HTTP 429 Too Many Requests", FailoverReason.RATE_LIMIT, True),
    ("503 Service Unavailable", FailoverReason.OVERLOADED, True),
    ("401 unauthorized", FailoverReason.AUTH_FAILURE, False),
    ("connection reset by peer", FailoverReason.NETWORK_ERROR, True),
    ("something totally unrelated", FailoverReason.UNKNOWN, False),
])
def test_classify_api_error(text, reason, retryable):
    c = classify_api_error(Exception(text))
    assert c.reason is reason
    assert c.retryable is retryable


# --- _parse_session_id: must not IndexError on malformed/truncated output ---

@pytest.mark.parametrize("text,expected", [
    ("session_id=abc123 pid=9", "abc123"),
    ("Terminal started. session_id=xyz\nshell=bash", "xyz"),
    ("session_id=", ""),            # marker at end-of-string (previously IndexError)
    ("session_id=\nfoo", ""),       # blank first line after marker (previously IndexError)
    ("session_id=  \n", ""),        # whitespace-only remainder (previously IndexError)
    ("no marker here", ""),
    ("", ""),
])
def test_parse_session_id_robust(text, expected):
    assert _parse_session_id(text) == expected


# --- _process_carriage_returns: keep only the final visible segment per line ---

def test_process_carriage_returns_keeps_last_segment():
    assert _process_carriage_returns("progress 10%\rprogress 100%") == "progress 100%"
    # trailing CR falls back to the previous segment rather than emitting ""
    assert _process_carriage_returns("done\r") == "done"
    # no CR is passed through untouched
    assert _process_carriage_returns("plain line") == "plain line"
