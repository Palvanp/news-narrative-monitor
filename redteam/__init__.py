"""Prompt-injection red teaming for Nazar's article pipeline.

Generates local test pages with a harmless instruction hidden in them, checks which
hiding methods survive text extraction, runs the brief generator on them with and
without the defences in pipeline/safety/defences.py, and reports the results.

    uv run python -m redteam.run_redteam

Everything runs against locally generated pages; nothing is fetched from or sent to
a third-party site other than the LLM provider the app already uses.
"""
