from moonlighter.core.llm.caller import LLMCaller


def test_llm_caller_type_is_exported():
    """LLMCaller is importable from moonlighter.core.llm.caller."""
    assert LLMCaller is not None
