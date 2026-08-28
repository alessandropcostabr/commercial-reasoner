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
    os.environ.get("LLM_INTEGRATION") != "1" or bool(os.environ.get("CI")),
    reason="integracao real: LLM_INTEGRATION=1 E fora de CI - nunca chamada externa no CI",
)
def test_llm_generate_integracao_real():
    from commercial_reasoner.service.llm import llm_generate

    turn = llm_generate(_req())
    assert isinstance(turn.get("response_text"), str)
    assert turn["response_text"].strip()


# --- structured output: parsing puro (sem rede) --------------------------------
from commercial_reasoner.service.contract import CommitmentCategory, Outcome, Technique
from commercial_reasoner.service.llm import parse_structured


def test_parse_json_completo_seta_as_quatro_etiquetas():
    raw = (
        '{"response_text": "Fica R$ 1.000 a vista. Fechamos hoje?", '
        '"technique": "CIALDINI", "stage": "closing", '
        '"commitment_category": "preco", "outcome": "continue"}'
    )
    out = parse_structured(raw)
    assert out["response_text"] == "Fica R$ 1.000 a vista. Fechamos hoje?"
    assert out["technique"] is Technique.CIALDINI
    assert "stage" not in out  # stage nao e extraido (engine ecoa req.stage)
    assert out["commitment_category"] is CommitmentCategory.PRECO
    assert out["outcome"] is Outcome.CONTINUE


def test_parse_enum_case_insensitive():
    out = parse_structured('{"response_text": "oi", "technique": "voss", "outcome": "CLOSE"}')
    assert out["technique"] is Technique.VOSS
    assert out["outcome"] is Outcome.CLOSE


def test_parse_enum_invalido_e_omitido_cai_no_fallback():
    # technique/outcome tortos NAO entram (reason aplica default depois).
    out = parse_structured('{"response_text": "oi", "technique": "FOO", "outcome": "bar"}')
    assert "technique" not in out
    assert "outcome" not in out


def test_parse_commitment_null_explicito_e_preservado():
    # null do LLM = "sem compromisso" -> chave presente com None (vence o fallback).
    out = parse_structured('{"response_text": "oi", "commitment_category": null}')
    assert "commitment_category" in out
    assert out["commitment_category"] is None


def test_parse_commitment_invalido_e_omitido():
    # categoria torta -> omite -> classificador deterministico preenche.
    out = parse_structured('{"response_text": "oi", "commitment_category": "xyz"}')
    assert "commitment_category" not in out


def test_parse_texto_cru_sem_json_escala():
    # prosa sem JSON = falha do modelo confiavel -> escala (:166, passo 4).
    out = parse_structured("Ola, tudo bem? Como posso ajudar?")
    assert out["response_text"] == "Ola, tudo bem? Como posso ajudar?"
    assert out["outcome"] is Outcome.ESCALATE


def test_parse_json_embutido_em_prosa_e_extraido():
    out = parse_structured('Claro! {"response_text": "aqui", "stage": "discovery"} pronto.')
    assert out["response_text"] == "aqui"
    assert "stage" not in out  # stage nao e extraido


def test_parse_json_valido_sem_response_text_escala():
    # JSON valido mas sem fala -> nao serializa o objeto como texto; escala (achado Codex).
    out = parse_structured('{"technique": "SPIN"}')
    assert out["response_text"] == ""
    assert out["outcome"] is Outcome.ESCALATE
    assert "technique" not in out  # sem fala, as demais etiquetas nao importam


def test_parse_response_text_null_ou_vazio_escala():
    for raw in ('{"response_text": null, "technique": "VOSS"}', '{"response_text": "   "}'):
        out = parse_structured(raw)
        assert out["response_text"] == ""
        assert out["outcome"] is Outcome.ESCALATE


def test_parse_stage_vazio_e_omitido():
    out = parse_structured('{"response_text": "oi", "stage": "   "}')
    assert "stage" not in out


def test_parse_commitment_outro_e_valido():
    out = parse_structured('{"response_text": "x", "commitment_category": "outro"}')
    assert out["commitment_category"] is CommitmentCategory.OUTRO


def test_parse_json_quebrado_nao_entrega_cru_e_escala():
    # JSON truncado (comeca com '{', sem response_text salvavel): nunca vai cru ao
    # cliente -> response_text vazio + escala (achado Codex).
    out = parse_structured('{"technique": "VOSS", "outc')
    assert out["response_text"] == ""
    assert out["outcome"] is Outcome.ESCALATE


def test_parse_json_quebrado_salva_a_fala_mas_escala():
    # recupera a fala como contexto, mas sem metadata confiavel -> escala (:166).
    out = parse_structured('{"response_text": "Fica R$ 1.000. Fechamos?", "techni')
    assert out["response_text"] == "Fica R$ 1.000. Fechamos?"
    assert out["outcome"] is Outcome.ESCALATE


def test_parse_prosa_pura_escala():
    # sem JSON estruturado -> escala, preservando a fala so como contexto (:166).
    out = parse_structured("Claro! Posso te ajudar com isso. Quando comeca?")
    assert out["response_text"].startswith("Claro!")
    assert out["outcome"] is Outcome.ESCALATE


def test_parse_saida_vazia_escala():
    for raw in ("", "   ", "\n\t "):
        out = parse_structured(raw)
        assert out["response_text"] == ""
        assert out["outcome"] is Outcome.ESCALATE


def test_parse_cerca_de_codigo_malformada_escala():
    # ```json + JSON truncado: nao comeca com '{' mas NAO e prosa - nao vai cru.
    out = parse_structured("```json\n{\"response_text\": \"oi\", \"techni")
    assert out["response_text"] == "" or out["response_text"] == "oi"
    # se nao salvou a fala, tem que escalar; se salvou, a fala e limpa (sem cerca).
    if out["response_text"] == "":
        assert out["outcome"] is Outcome.ESCALATE
    assert "```" not in out["response_text"]


def test_parse_cerca_sem_json_valido_nao_vai_crua():
    out = parse_structured("```\nalguma coisa\n```")
    assert "```" not in out["response_text"]


# --- retry/resiliencia (httpx mockado, sem rede) -------------------------------
import commercial_reasoner.service.llm as _L


def _resp(status, content='{"response_text": "oi", "outcome": "continue"}'):
    req = _L.httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return _L.httpx.Response(status, json={"choices": [{"message": {"content": content}}]}, request=req)


def test_llm_generate_retry_em_429_depois_sucesso(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setattr(_L.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fake_post(url, **kw):
        calls["n"] += 1
        return _resp(429) if calls["n"] < 3 else _resp(200)

    monkeypatch.setattr(_L.httpx, "post", fake_post)
    turn = _L.llm_generate(_req())
    assert turn["response_text"] == "oi"
    assert calls["n"] == 3  # 2 falhas + 1 sucesso


def test_llm_generate_429_persistente_escala(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setattr(_L.time, "sleep", lambda *_: None)
    monkeypatch.setattr(_L.httpx, "post", lambda url, **kw: _resp(429))
    turn = _L.llm_generate(_req())
    assert turn["response_text"] == ""
    assert turn["outcome"] is Outcome.ESCALATE


def test_llm_generate_4xx_escala_sem_repetir(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setattr(_L.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fake_post(url, **kw):
        calls["n"] += 1
        return _resp(401)

    monkeypatch.setattr(_L.httpx, "post", fake_post)
    # em background, um raise trava a run do LATE -> 4xx escala em vez de levantar.
    turn = _L.llm_generate(_req())
    assert turn["outcome"] is Outcome.ESCALATE
    assert calls["n"] == 1  # 4xx nao repete


def test_llm_generate_5xx_fora_do_allowlist_antigo_faz_retry(monkeypatch):
    # 520 (Cloudflare) estava fora do {429,500,502,503,504} antigo (achado Codex).
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setattr(_L.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fake_post(url, **kw):
        calls["n"] += 1
        return _resp(520) if calls["n"] < 2 else _resp(200)

    monkeypatch.setattr(_L.httpx, "post", fake_post)
    turn = _L.llm_generate(_req())
    assert turn["response_text"] == "oi"
    assert calls["n"] == 2  # 520 e transitorio -> repetiu
