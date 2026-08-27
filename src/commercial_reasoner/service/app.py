"""Servico HTTP stateless da engine para o LATE (contrato + gate + reasoning).

/reason retorna 202 IMEDIATO (contrato assincrono); reasoning (LLM) + assinatura
+ entrega do webhook rodam em background. O reasoning e sync (chamada HTTP ao
LLM); roda em threadpool p/ NAO bloquear o event loop (L99). LLM real so com flag
COMMERCIAL_REASONER_LLM=llm + chave; default = stub deterministico.

Rodar: `uv run --extra service uvicorn commercial_reasoner.service.app:app`
Env: LATE_WEBHOOK_SECRET (obrig., fail-closed), LATE_WEBHOOK_URL (opcional).
"""
from __future__ import annotations

import asyncio
import os

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, status

from . import reasoning
from .contract import ReasonRequest, make_event_id, serialize, sign

app = FastAPI(title="Commercial Reasoner - contrato LATE + gate + reasoning")


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
            headers={"content-type": "application/json", "x-webhook-signature": sig},
        )


async def _process(req: ReasonRequest, secret: str) -> None:
    # reasoning.reason e sync (chamada HTTP ao LLM) -> threadpool, sem travar o loop.
    envelope = await asyncio.to_thread(reasoning.reason, req, _generator())
    raw = serialize(envelope)
    sig = sign(raw, secret)
    await _deliver(raw, sig)


@app.post("/reason", status_code=status.HTTP_202_ACCEPTED)
async def reason(req: ReasonRequest, background: BackgroundTasks):
    secret = _secret()  # fail-closed cedo, antes de aceitar
    background.add_task(_process, req, secret)
    return {
        "accepted": True,
        "correlation_token": req.correlation_token,
        "event_id": make_event_id(req.correlation_token),
    }


@app.get("/healthz")
async def healthz():
    return {"ok": True}
