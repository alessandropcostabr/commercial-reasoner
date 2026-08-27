"""Servico HTTP stateless da engine para o LATE (contrato Fase 0 + gate Fase 1).

O reasoning ainda e canned (stub em reasoning._stub_generate); o gate financeiro
deterministico JA roda sobre os grounded_facts do request (barra dinheiro errado
antes de qualquer LLM). Todo o resto do contrato e real (schema, event_id,
timestamp assinado, echo do token, HMAC sobre bytes crus, fail-closed).

Rodar: `uv run --extra service uvicorn commercial_reasoner.service.app:app`
Env: LATE_WEBHOOK_SECRET (obrigatorio, fail-closed), LATE_WEBHOOK_URL (opcional
enquanto o receiver do LATE nao existe).
"""
from __future__ import annotations

import os

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, status

from . import reasoning
from .contract import ReasonRequest, serialize, sign

app = FastAPI(title="Commercial Reasoner - contrato LATE (stub) + gate")


def _generator():
    """Escolhe o cerebro: LLM real so com flag explicita + chave; senao stub.

    Default = stub deterministico -> CI/testes nunca chamam LLM nem precisam de chave.
    """
    if os.environ.get("COMMERCIAL_REASONER_LLM") == "llm" and os.environ.get("LLM_API_KEY"):
        from .llm import llm_generate

        return llm_generate
    return reasoning._stub_generate


def _secret() -> str:
    s = os.environ.get("LATE_WEBHOOK_SECRET")
    if not s:  # fail-closed: sem segredo, nao assina nada
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LATE_WEBHOOK_SECRET ausente",
        )
    return s


async def _deliver(raw: bytes, sig: str) -> None:
    url = os.environ.get("LATE_WEBHOOK_URL")
    if not url:  # LATE receiver ainda nao existe (Fase 0) - no-op
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
    envelope = reasoning.reason(req, generate=_generator())  # gera + grounding + gate
    raw = serialize(envelope)
    sig = sign(raw, secret)
    background.add_task(_deliver, raw, sig)  # webhook assincrono (at-least-once)
    return {
        "accepted": True,
        "correlation_token": req.correlation_token,
        "event_id": envelope.event_id,
        "outcome": envelope.outcome.value,
    }


@app.get("/healthz")
async def healthz():
    return {"ok": True}
