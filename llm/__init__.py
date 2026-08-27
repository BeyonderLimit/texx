"""Texx LLM layer.

The LLM is a *bounded* intelligence module, not the center of Texx. It is used
only for natural conversation, writing, explanation, ambiguous-command
disambiguation, and memory extraction. Texx works fully without it; every
entry point degrades gracefully when no model is configured or `llama-cpp-python`
is unavailable.
"""
