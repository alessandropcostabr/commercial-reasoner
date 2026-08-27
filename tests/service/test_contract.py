"""Testes do contrato LATE (Fase 0): schema, event_id, echo do token, HMAC.

Provam o LADO ENGINE do contrato sem precisar do receiver do LATE (que ainda
nao existe). Quando o CR-1 for codado, os dois lados batem contra este contrato.
"""
import base64
import hashlib
import hmac
import json

from commercial_reasoner.service.contract import (
    CommitmentCategory,
    Outcome,
    ReasonRequest,
    Technique,
    build_envelope,
    make_event_id,
    serialize,
    sign,
)


def _req(token: str = "tok-abc") -> ReasonRequest:
    return ReasonRequest(
        correlation_token=token,
        message="quanto custa o curso?",
        history=[{"role": "user", "text": "quanto custa o curso?"}],
        grounded_facts={"preco": 1200},
        rapport={"heat": "morno"},
        stage="qualifying",
    )


def test_event_id_prefixado_global_e_deterministico_por_token():
    a = make_event_id("tok-1")
    b = make_event_id("tok-1")
    c = make_event_id("tok-2")
    assert a.startswith("commercial-reasoner:")  # prefixo global (ledger do LATE)
    assert a == b  # idempotente por token: retry do LATE nao duplica (L41)
    assert a != c


def test_envelope_ecoa_token_e_herda_stage_do_request():
    env = build_envelope(
        _req("tok-xyz"),
        response_text="oi",
        technique=Technique.VOSS,
        outcome=Outcome.CONTINUE,
    )
    assert env.correlation_token == "tok-xyz"  # echo obrigatorio
    assert env.event_id.startswith("commercial-reasoner:")
    assert env.timestamp.endswith("Z")
    assert env.stage == "qualifying"  # herdado do request se nao sobrescrito


def test_commitment_category_null_por_default_e_dominio_valido():
    req = _req()
    env0 = build_envelope(
        req, response_text="x", technique=Technique.SPIN, outcome=Outcome.CONTINUE
    )
    assert env0.commitment_category is None  # null = sem compromisso
    env1 = build_envelope(
        req,
        response_text="x",
        technique=Technique.SPIN,
        outcome=Outcome.CONTINUE,
        commitment_category=CommitmentCategory.PRECO,
    )
    assert env1.commitment_category is CommitmentCategory.PRECO


def test_hmac_e_sobre_os_bytes_crus_enviados_L58():
    env = build_envelope(
        _req(), response_text="ola", technique=Technique.VOSS, outcome=Outcome.CONTINUE
    )
    raw = serialize(env)
    secret = "s3cr3t-partilhado"
    sig = sign(raw, secret)
    # O LATE DEVE verificar sobre o rawBody recebido, nao re-stringify.
    expected = base64.b64encode(
        hmac.new(secret.encode(), raw, hashlib.sha256).digest()
    ).decode()
    assert sig == expected
    # Os bytes assinados sao JSON valido e round-trip identico ao token.
    assert json.loads(raw)["correlation_token"] == "tok-abc"


def test_schema_completo_serializa_valores_json_nativos():
    env = build_envelope(
        _req(),
        response_text="ola",
        technique=Technique.CIALDINI,
        outcome=Outcome.CLOSE,
        commitment_category=CommitmentCategory.FRETE,
        bant={"budget": 7},
    )
    d = json.loads(serialize(env))
    for k in (
        "event_id",
        "timestamp",
        "correlation_token",
        "response_text",
        "technique",
        "rapport",
        "stage",
        "commitment_category",
        "outcome",
    ):
        assert k in d, k
    assert d["technique"] == "CIALDINI"  # Enum -> str
    assert d["commitment_category"] == "frete"
    assert d["outcome"] == "close"


def test_serialize_null_quando_sem_compromisso():
    env = build_envelope(
        _req(), response_text="x", technique=Technique.SPIN, outcome=Outcome.CONTINUE
    )
    d = json.loads(serialize(env))
    assert d["commitment_category"] is None  # JSON null, nao a string "null"
