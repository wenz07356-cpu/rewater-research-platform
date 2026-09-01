from types import SimpleNamespace

import app.agents.research_agent as research_agent


def _build_search_subagent(monkeypatch, *, enabled: bool):
    monkeypatch.setattr(
        research_agent,
        "get_settings",
        lambda: SimpleNamespace(enable_knowledge_service=enabled),
    )
    monkeypatch.setattr(research_agent, "_load_prompt", lambda _path: "search prompt")
    return research_agent._build_search_subagent(model_name="test:model")


def _tool_names(subagent):
    return [tool.__name__ for tool in subagent["tools"]]


def test_enabled_self_kb_replaces_ragflow_at_existing_position(monkeypatch):
    subagent = _build_search_subagent(monkeypatch, enabled=True)

    assert _tool_names(subagent) == [
        "external_search",
        "read_web_page",
        "knowledge_base_search",
    ]
    assert "ragflow_search" not in _tool_names(subagent)


def test_disabled_self_kb_keeps_existing_public_tool_order(monkeypatch):
    subagent = _build_search_subagent(monkeypatch, enabled=False)

    assert _tool_names(subagent) == ["external_search", "read_web_page"]


def test_search_subagent_description_is_provider_neutral(monkeypatch):
    subagent = _build_search_subagent(monkeypatch, enabled=True)
    description = subagent["description"]

    assert "内部知识库" in description
    assert "公开互联网检索" in description
    assert "网页读取" in description
    assert "RAGFlow" not in description
    assert "兼容" not in description
    assert "补充" not in description
    assert "并存" not in description
    assert subagent["system_prompt"] == "search prompt"
    assert subagent["model"] == "test:model"


def test_research_agent_no_longer_imports_or_registers_ragflow(monkeypatch):
    subagent = _build_search_subagent(monkeypatch, enabled=True)

    assert hasattr(research_agent, "knowledge_base_search")
    assert not hasattr(research_agent, "ragflow_search")
    assert research_agent.knowledge_base_search in subagent["tools"]
    assert all(tool.__module__ != "app.tools.ragflow_search" for tool in subagent["tools"])
