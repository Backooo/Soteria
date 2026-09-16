"""Tests never call the hosted model: the rule policy decides, deterministically."""

import pytest


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    monkeypatch.setenv("SOTERIA_LLM", "0")
