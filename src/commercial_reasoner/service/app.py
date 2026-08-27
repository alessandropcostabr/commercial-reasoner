"""Servico HTTP stateless da engine para o LATE (STUB de contrato - Fase 0).

STUB: o reasoning e canned (resposta fixa); TODO o resto do contrato e real
(schema, event_id prefixado, timestamp, echo do token, assinatura HMAC). Prova
o CONTRATO ponta a ponta antes de plugar o reasoning real (Fase 1+).

Rodar: `uv run --extra service uvicorn commercial_reasoner.service.app:app`
Env: LATE_WEBHOOK_SECRET (obrigatorio, fail-closed), LATE_WEBHOOK_URL (opcional
enquanto o receiver do LATE nao existe).
"""
from __future__ import annotations

import os

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, status

from .contract import (
    Outcome,
    ReasonRequest,
    ResponseEnvelope,
    Technique,
    build_envelope,
    serialize,
    sign,
)

app = FastAPI(title="Commercial Reasoner - contrato LATE (stub)")


def _secret() -> str:
    s = os.environ.get("LATE_WEBHOOK_SECRET")
    if not s:  # fail-closed: sem segredo, nao assina nada
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LATE_WEBHOOK_SECRET ausente",
        )
    return s


def _reason_stub(req: ReasonRequest) -> ResponseEnvelope:
    """Reasoning CANNED. Trocar por Qwen(SOUL+PLAYBOOK)+lib memory na Fase 1."""
    return build_envelope(
        req,
        response_text="(stub) resposta de contrato - reasoning real vem na Fase 1",
        technique=Technique.VOSS,
        outcome=Outcome.CONTINUE,
        commitment_category=None,
    )


async def _deliver(raw: bytes, sig: str) -> None:
    url = os.environ.get("LATE_WEBHOOK_URL")
    if not url:  # LATE receiver ainda nao existe (Fase 0) - no-op logado
        return
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            url,
            content=raw,
            headers={
                "content-type": "application/json",
                "x-webhook-signature": sig,
            },
        )


@app.post("/reason", status_code=status.HTTP_202_ACCEPTED)
async def reason(req: ReasonRequest, background: BackgroundTasks):
    secret = _secret()
    envelope = _reason_stub(req)
    raw = serialize(envelope)
    sig = sign(raw, secret)
    # Webhook assincrono (o LATE trata como at-least-once do seu lado).
    background.add_task(_deliver, raw, sig)
    return {
        "accepted": True,
        "correlation_token": req.correlation_token,
        "event_id": envelope.event_id,
    }


@app.get("/healthz")
async def healthz():
    return {"ok": True}
