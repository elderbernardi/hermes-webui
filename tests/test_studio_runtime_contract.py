"""Studio proposals must not retain memory or promote failed agent output."""
import contextlib
import sys
import types

import pytest
from api import acervo_studio_agent as studio_agent
from api import profiles


def install_agent(monkeypatch, result=None, error=None):
    calls = {}

    class Agent:
        def __init__(self, **kwargs):
            calls['init'] = kwargs

        def run_conversation(self, **kwargs):
            if error:
                raise error
            return result

        def close(self):
            calls['closed'] = True

    monkeypatch.setitem(sys.modules, 'run_agent', types.SimpleNamespace(AIAgent=Agent))
    monkeypatch.setattr(profiles, 'get_active_profile_name', lambda: 'default')
    monkeypatch.setattr(profiles, 'profile_env_for_background_worker',
                        lambda *a, **k: contextlib.nullcontext())
    monkeypatch.setattr(studio_agent, '_resolve_main_runtime', lambda *a: {
        'model': 'fixture', 'provider': 'fixture', 'api_key': None, 'base_url': None})
    return calls


def test_proposal_turn_does_not_initialize_memory_and_closes(monkeypatch):
    calls = install_agent(monkeypatch, {'completed': True, 'final_response': 'proposal'})
    assert studio_agent._run_agent_text('system', 'input') == 'proposal'
    assert calls['init']['skip_memory'] is True
    assert calls['init']['enabled_toolsets'] == []
    assert calls.get('closed') is True


@pytest.mark.parametrize('response', ['', 'provider failed', '{}',
                                      '{"body_markdown": "  "}',
                                      '{"body_markdown": ["not text"]}'])
def test_promote_invalid_output_never_scaffolds_or_commits(monkeypatch, tmp_path, response):
    from api import acervo_studio
    monkeypatch.setattr(acervo_studio, '_read_envelope', lambda *a: {'caption': 'fixture'})
    monkeypatch.setattr(studio_agent, '_envelope_content', lambda *a: 'raw source, not memory')
    monkeypatch.setattr(studio_agent, '_run_agent_text', lambda *a, **k: response)
    calls = []
    monkeypatch.setattr(studio_agent, '_scaffold_microverso', lambda *a: calls.append('scaffold'))
    monkeypatch.setattr(studio_agent, '_commit_via_acervoctl', lambda *a: calls.append('commit') or {})
    monkeypatch.setattr(studio_agent, '_move_to_promoted', lambda *a: calls.append('move'))
    result = studio_agent.promote(tmp_path, 'fixture', {
        'scope': 'micro', 'slug': 'fixture', 'nature': 'knowledge', 'title': 'Fixture'})
    assert result['ok'] is False
    assert calls == []


@pytest.mark.parametrize('result', [
    None, [], {}, {'completed': False, 'final_response': 'partial'},
    {'completed': True, 'failed': True, 'final_response': 'error'},
    {'completed': True, 'interrupted': True, 'final_response': 'partial'},
    {'completed': True, 'partial': True, 'final_response': 'partial'},
    {'completed': True, 'error': 'provider down', 'final_response': 'error'},
    {'completed': True, 'final_response': ''},
])
def test_unusable_turn_is_rejected_and_closed(monkeypatch, result):
    calls = install_agent(monkeypatch, result)
    with pytest.raises(studio_agent.AgentUnavailable):
        studio_agent._run_agent_text('system', 'input')
    assert calls.get('closed') is True


def test_agent_exception_still_closes(monkeypatch):
    calls = install_agent(monkeypatch, error=RuntimeError('fixture failure'))
    with pytest.raises(studio_agent.AgentUnavailable):
        studio_agent._run_agent_text('system', 'input')
    assert calls.get('closed') is True
