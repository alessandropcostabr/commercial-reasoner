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
import math
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class StrictContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Turn(StrictContractModel):
    # Proveniencia obrigatoria: `role='bot'` e contexto conversacional, NUNCA
    # fonte de fato (so `grounded_facts` e o cliente sao autoritativos).
    role: Literal["user", "bot"]
    text: str = Field(min_length=1, max_length=1000)


class PricePointIn(StrictContractModel):
    modality: str = Field(min_length=1, max_length=80)
    value: float
    description: str | None = Field(default=None, max_length=200)

    @field_validator("value", mode="before")
    @classmethod
    def value_is_bounded_real(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("value deve ser numero finito")
        if not 0 <= value <= 10_000_000:
            raise ValueError("value fora do dominio")
        return float(value)


class GroundedFacts(StrictContractModel):
    # Fatos da conta+setor injetados pelo LATE. Tipado na fronteira: payload
    # malformado (ex.: price sem `value`) vira 422 do FastAPI, nao 500 (L52).
    prices: list[PricePointIn] = Field(default_factory=list, max_length=20)
    other_numbers: list[float] = Field(default_factory=list, max_length=20)

    @field_validator("other_numbers", mode="before")
    @classmethod
    def numbers_are_bounded_reals(cls, values):
        if not isinstance(values, list):
            raise ValueError("other_numbers deve ser lista")
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) or not 0 <= value <= 10_000_000 for value in values):
            raise ValueError("other_numbers deve conter numeros finitos no dominio")
        return [float(value) for value in values]


class ReasonRequest(StrictContractModel):
    correlation_token: str = Field(min_length=1, max_length=36)
    message: str = Field(min_length=1, max_length=4096)
    history: list[Turn] = Field(default_factory=list, max_length=20)
    grounded_facts: GroundedFacts = Field(default_factory=GroundedFacts)
    playbook: str | None = None
    rapport: RapportT = None
    stage: str = Field(min_length=1, max_length=100)

    @field_validator("playbook", mode="before")
    @classmethod
    def playbook_is_bounded_utf8(cls, value):
        if not isinstance(value, str):
            raise ValueError("playbook deve ser string")
        try:
            size = len(value.encode("utf-8"))
        except UnicodeEncodeError:
            raise ValueError("playbook deve ser UTF-8 valido") from None
        if size > 2048:
            raise ValueError("playbook excede 2048 bytes")
        return value

    @field_validator("correlation_token")
    @classmethod
    def correlation_token_is_uuid(cls, value):
        try:
            uuid.UUID(value)
        except ValueError:
            raise ValueError("correlation_token deve ser UUID") from None
        return value

    @field_validator("rapport", mode="before")
    @classmethod
    def rapport_is_bounded_json(cls, value):
        if value is None:
            return value
        if isinstance(value, bool):
            raise ValueError("rapport nao aceita booleano")
        if isinstance(value, (int, float)):
            if not math.isfinite(value):
                raise ValueError("rapport deve ser numero finito")
            return value
        if not isinstance(value, dict):
            raise ValueError("rapport deve ser objeto, numero ou null")
        try:
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError):
            raise ValueError("rapport deve ser JSON") from None
        if len(encoded) > 2048 or _json_depth(value) > 3:
            raise ValueError("rapport excede o contrato")
        return value


def _json_depth(value) -> int:
    if not isinstance(value, (dict, list)):
        return 0
    values = value.values() if isinstance(value, dict) else value
    return 1 + max((_json_depth(item) for item in values), default=0)


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
    return _EVENT_PREFIX + str(uuid.uuid5(_EVENT_NS, str(correlation_token)))


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
