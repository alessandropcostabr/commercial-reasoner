"""Smoke do endpoint /reason (camada HTTP stateless, stub Fase 0)."""
import base64
import hashlib
import hmac
import json
import uuid

from fastapi.testclient import TestClient

from commercial_reasoner.service.app import app


def _client(monkeypatch, secret="s3cr3t"):
    monkeypatch.setenv("LATE_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("LATE_ENGINE_INGRESS_SECRET", "ingress-secret")
    monkeypatch.delenv("LATE_WEBHOOK_URL", raising=False)  # sem receiver LATE ainda
    return TestClient(app), secret


def _payload(token=None):
    return {
        "correlation_token": token or str(uuid.uuid4()),
        "message": "tem desconto a vista?",
        "history": [{"role": "user", "text": "tem desconto a vista?"}],
        "grounded_facts": {"prices": [{"modality": "a vista", "value": 1200}]},
        "rapport": {"heat": "quente"},
        "stage": "closing",
    }


def _post(client, payload):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = base64.b64encode(hmac.new(b"ingress-secret", raw, hashlib.sha256).digest()).decode()
    return client.post("/reason", content=raw, headers={"Webhook-Signature": signature})


def test_reason_aceita_e_devolve_202_com_event_id(monkeypatch):
    client, _ = _client(monkeypatch)
    r = _post(client, _payload())
    assert r.status_code == 202
    body = r.json()
    assert body["accepted"] is True
    assert body["correlation_token"]
    assert body["event_id"].startswith("commercial-reasoner:")


def test_reason_falha_fechado_sem_segredo(monkeypatch):
    monkeypatch.delenv("LATE_WEBHOOK_SECRET", raising=False)
    client = TestClient(app, raise_server_exceptions=False)
    r = _post(client, _payload())
    assert r.status_code == 503  # fail-closed: sem segredo, nao assina


def test_reason_falha_fechado_sem_segredo_de_ingresso(monkeypatch):
    client, _ = _client(monkeypatch)
    monkeypatch.delenv("LATE_ENGINE_INGRESS_SECRET")
    r = _post(client, _payload())
    assert r.status_code == 503


def test_reason_rejeita_payload_malformado(monkeypatch):
    client, _ = _client(monkeypatch)
    r = _post(client, {"message": "faltou o token e o stage"})
    assert r.status_code == 422  # validacao estrita do schema


def test_webhook_entregue_com_assinatura_valida(monkeypatch):
    """Com LATE_WEBHOOK_URL setado, o webhook sai assinado sobre o rawBody."""
    captured = {}

    class _FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, content=None, headers=None):
            captured["url"] = url
            captured["raw"] = content
            captured["sig"] = headers["x-webhook-signature"]

    import commercial_reasoner.service.app as appmod

    monkeypatch.setenv("LATE_WEBHOOK_SECRET", "s3cr3t")
    monkeypatch.setenv("LATE_ENGINE_INGRESS_SECRET", "ingress-secret")
    monkeypatch.setenv("LATE_WEBHOOK_URL", "https://late.local/webhook")
    monkeypatch.setattr(appmod.httpx, "AsyncClient", _FakeAsyncClient)

    client = TestClient(app)
    r = _post(client, _payload())
    assert r.status_code == 202
    # background task rodou e entregou
    assert captured["url"] == "https://late.local/webhook"
    expected = base64.b64encode(
        hmac.new(b"s3cr3t", captured["raw"], hashlib.sha256).digest()
    ).decode()
    assert captured["sig"] == expected  # HMAC sobre os bytes crus enviados (L58)


def test_reason_rejeita_assinatura_invalida_sem_task(monkeypatch):
    client, _ = _client(monkeypatch)
    r = client.post("/reason", json=_payload(), headers={"Webhook-Signature": "invalida"})
    assert r.status_code == 401


def test_reason_rejeita_corpo_acima_do_limite_antes_da_assinatura(monkeypatch):
    client, _ = _client(monkeypatch)
    r = client.post("/reason", content=b"x" * (16 * 1024 + 1))
    assert r.status_code == 413


def test_reason_aceita_chave_anterior_na_janela_de_rotacao(monkeypatch):
    client, _ = _client(monkeypatch)
    monkeypatch.setenv("LATE_ENGINE_INGRESS_SECRETS", "nova, anterior")
    raw = json.dumps(_payload(), separators=(",", ":")).encode()
    signature = base64.b64encode(hmac.new(b"anterior", raw, hashlib.sha256).digest()).decode()
    assert client.post("/reason", content=raw, headers={"Webhook-Signature": signature}).status_code == 202


def test_reason_rejeita_schema_estrito_sem_task(monkeypatch):
    client, _ = _client(monkeypatch)
    payload = _payload()
    payload["grounded_facts"]["prices"][0]["injected"] = True
    assert _post(client, payload).status_code == 422


def test_reason_rejeita_token_e_rapport_fora_do_contrato(monkeypatch):
    client, _ = _client(monkeypatch)
    payload = _payload(token="nao-e-uuid")
    assert _post(client, payload).status_code == 422
    payload = _payload()
    payload["rapport"] = {"a": {"b": {"c": {"d": 1}}}}
    assert _post(client, payload).status_code == 422
