"""Montagem do prompt do LLM (sem rede) + integracao skippable.

O teste de integracao real so roda com LLM_INTEGRATION=1 (nunca no CI, mesmo
que uma chave vaze no ambiente) - evita chamada paga/rate-limit no pipeline.
"""
import os

import pytest

from commercial_reasoner.service.contract import ReasonRequest
from commercial_reasoner.service.llm import (
    _persona_sem_exemplos,
    build_messages,
    build_system_prompt,
)

_SOUL = """# Persona
Voce e a consultora. Tom empatico, curto.

## Fatos do curso (EXEMPLO ficticio)
- Preco: R$ 9.999 (NAO usar - e exemplo)
"""
_PLAYBOOK = "# Playbook\nTecnica por calor do lead."


def _req() -> ReasonRequest:
    return ReasonRequest(
        correlation_token="t",
        message="quanto custa?",
        history=[{"role": "user", "text": "oi"}, {"role": "bot", "text": "ola!"}],
        grounded_facts={"prices": [{"modality": "upfront", "value": 1000}]},
        rapport={"heat": "quente"},
        stage="closing",
    )


def test_persona_sem_exemplos_stripa_fatos():
    out = _persona_sem_exemplos(_SOUL)
    assert "consultora" in out
    assert "9.999" not in out  # secao de exemplo removida
    assert "Fatos do curso" not in out


def test_system_prompt_usa_so_grounded_e_ignora_exemplos(monkeypatch, tmp_path):
    soul = tmp_path / "soul.md"
    soul.write_text(_SOUL, encoding="utf-8")
    pb = tmp_path / "pb.md"
    pb.write_text(_PLAYBOOK, encoding="utf-8")
    monkeypatch.setenv("LLM_SOUL_PATH", str(soul))
    monkeypatch.setenv("LLM_PLAYBOOK_PATH", str(pb))

    sp = build_system_prompt(_req())
    assert "9.999" not in sp  # exemplo do SOUL nao entra
    assert "EXCLUSIVAMENTE" in sp  # instrucao de so-grounded
    assert '"value": 1000' in sp or '"value":1000' in sp  # grounded_facts presente
    assert "pergunta fechada" in sp


def test_messages_monta_system_history_user(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_SOUL_PATH", str(tmp_path / "nao_existe.md"))
    monkeypatch.setenv("LLM_PLAYBOOK_PATH", str(tmp_path / "nao_existe2.md"))
    msgs = build_messages(_req())
    assert msgs[0]["role"] == "system"
    assert msgs[1] == {"role": "user", "content": "oi"}
    assert msgs[2] == {"role": "assistant", "content": "ola!"}
    assert msgs[-1] == {"role": "user", "content": "quanto custa?"}


@pytest.mark.skipif(
    os.environ.get("LLM_INTEGRATION") != "1",
    reason="integracao real: setar LLM_INTEGRATION=1 + LLM_API_KEY (nao roda no CI)",
)
def test_llm_generate_integracao_real():
    from commercial_reasoner.service.llm import llm_generate

    turn = llm_generate(_req())
    assert isinstance(turn.get("response_text"), str)
    assert turn["response_text"].strip()
