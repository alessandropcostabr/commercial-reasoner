"""Smoke do endpoint /reason (camada HTTP stateless, stub Fase 0)."""
import base64
import hashlib
import hmac

from fastapi.testclient import TestClient

from commercial_reasoner.service.app import app


def _client(monkeypatch, secret="s3cr3t"):
    monkeypatch.setenv("LATE_WEBHOOK_SECRET", secret)
    monkeypatch.delenv("LATE_WEBHOOK_URL", raising=False)  # sem receiver LATE ainda
    return TestClient(app), secret


def _payload(token="tok-http"):
    return {
        "correlation_token": token,
        "message": "tem desconto a vista?",
        "history": [{"role": "user", "text": "tem desconto a vista?"}],
        "grounded_facts": {"preco": 1200},
        "rapport": {"heat": "quente"},
        "stage": "closing",
    }


def test_reason_aceita_e_devolve_202_com_event_id(monkeypatch):
    client, _ = _client(monkeypatch)
    r = client.post("/reason", json=_payload("tok-1"))
    assert r.status_code == 202
    body = r.json()
    assert body["accepted"] is True
    assert body["correlation_token"] == "tok-1"
    assert body["event_id"].startswith("commercial-reasoner:")


def test_reason_falha_fechado_sem_segredo(monkeypatch):
    monkeypatch.delenv("LATE_WEBHOOK_SECRET", raising=False)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/reason", json=_payload())
    assert r.status_code == 503  # fail-closed: sem segredo, nao assina


def test_reason_rejeita_payload_malformado(monkeypatch):
    client, _ = _client(monkeypatch)
    r = client.post("/reason", json={"message": "faltou o token e o stage"})
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
    monkeypatch.setenv("LATE_WEBHOOK_URL", "https://late.local/webhook")
    monkeypatch.setattr(appmod.httpx, "AsyncClient", _FakeAsyncClient)

    client = TestClient(app)
    r = client.post("/reason", json=_payload("tok-wh"))
    assert r.status_code == 202
    # background task rodou e entregou
    assert captured["url"] == "https://late.local/webhook"
    expected = base64.b64encode(
        hmac.new(b"s3cr3t", captured["raw"], hashlib.sha256).digest()
    ).decode()
    assert captured["sig"] == expected  # HMAC sobre os bytes crus enviados (L58)
