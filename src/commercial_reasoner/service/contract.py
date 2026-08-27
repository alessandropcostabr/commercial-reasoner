"""Contrato de API LATE <-> engine (lado engine) - forma do envelope + assinatura.

Fonte de verdade da FORMA e da ASSINATURA do que a engine devolve ao webhook do
LATE. Ver `API_CONTRACT_LATE.md` na raiz. Este modulo NAO gera a resposta de
venda (isso e o reasoning, Fase 1+); ele so monta, serializa e assina o envelope.

Stateless de proposito: o LATE e dono do estado (rapport/estagio na run, fatos na
config, canais). A engine recebe o contexto no request e devolve raciocinio - o
que casa com multi-canal + multiplas chamadas concorrentes.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional, Union

from pydantic import BaseModel

# Namespace fixo para uuid5 -> event_id deterministico por correlation_token.
# Deterministico = idempotente: um retry do LATE (mesmo token) produz o MESMO
# event_id, entao o ledger global do LATE deduplica em vez de duplicar (L41).
_EVENT_NS = uuid.UUID("b4d0c0de-0000-4000-8000-000000000001")

_EVENT_PREFIX = "commercial-reasoner:"


class Technique(str, Enum):
    VOSS = "VOSS"
    CHALLENGER = "CHALLENGER"
    CIALDINI = "CIALDINI"
    SPIN = "SPIN"


class CommitmentCategory(str, Enum):
    # `null` (None) = sem compromisso; qualquer valor abaixo = compromisso a
    # ser TRAVADO pelo LATE (a engine so CLASSIFICA; o gate e do LATE).
    PRECO = "preco"
    PRAZO = "prazo"
    FORMA_PAGAMENTO = "forma_pagamento"
    DESCONTO = "desconto"
    FRETE = "frete"
    OUTRO = "outro"


class Outcome(str, Enum):
    CONTINUE = "continue"
    CLOSE = "close"
    ESCALATE = "escalate"


RapportT = Union[dict, float, int, None]


class Turn(BaseModel):
    # Proveniencia obrigatoria: `role='bot'` e contexto conversacional, NUNCA
    # fonte de fato (so `grounded_facts` e o cliente sao autoritativos).
    role: Literal["user", "bot"]
    text: str


class PricePointIn(BaseModel):
    modality: str
    value: float
    description: str = ""


class GroundedFacts(BaseModel):
    # Fatos da conta+setor injetados pelo LATE. Tipado na fronteira: payload
    # malformado (ex.: price sem `value`) vira 422 do FastAPI, nao 500 (L52).
    prices: list[PricePointIn] = []
    other_numbers: list[float] = []


class ReasonRequest(BaseModel):
    correlation_token: str
    message: str
    history: list[Turn] = []
    grounded_facts: GroundedFacts = GroundedFacts()
    rapport: RapportT = None
    stage: str


class ResponseEnvelope(BaseModel):
    event_id: str
    timestamp: str
    correlation_token: str
    response_text: str
    technique: Technique
    rapport: RapportT
    stage: str
    bant: Optional[dict] = None
    commitment_category: Optional[CommitmentCategory] = None
    outcome: Outcome


def make_event_id(correlation_token: str) -> str:
    """event_id prefixado global e deterministico por token (L41)."""
    return _EVENT_PREFIX + str(uuid.uuid5(_EVENT_NS, correlation_token))


def build_envelope(
    req: ReasonRequest,
    *,
    response_text: str,
    technique: Technique,
    outcome: Outcome,
    commitment_category: Optional[CommitmentCategory] = None,
    rapport: RapportT = "__inherit__",
    stage: Optional[str] = None,
    bant: Optional[dict] = None,
    now: Optional[datetime] = None,
) -> ResponseEnvelope:
    ts = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return ResponseEnvelope(
        event_id=make_event_id(req.correlation_token),
        timestamp=ts,
        correlation_token=req.correlation_token,
        response_text=response_text,
        technique=technique,
        rapport=req.rapport if rapport == "__inherit__" else rapport,
        stage=stage or req.stage,
        bant=bant,
        commitment_category=commitment_category,
        outcome=outcome,
    )


def serialize(envelope: ResponseEnvelope) -> bytes:
    """Bytes CANONICOS do envelope: os MESMOS que sao assinados E enviados.

    A regra de canonicalizacao (L58) e: a engine assina os bytes crus que envia;
    o LATE verifica o HMAC sobre o rawBody recebido, NUNCA sobre um
    JSON.stringify(parsed) - senao whitespace/ordem de chaves quebram o 401.
    `mode='json'` resolve Enum->str e None->null.
    """
    return json.dumps(
        envelope.model_dump(mode="json"),
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sign(raw: bytes, secret: str) -> str:
    """base64(HMAC-SHA256(rawBody, secret)) para o header x-webhook-signature."""
    return base64.b64encode(
        hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    ).decode("ascii")
