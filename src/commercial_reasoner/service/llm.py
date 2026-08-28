"""Gerador de resposta via LLM OpenAI-compatible (default: OpenRouter).

Injetavel em reasoning.reason(generate=llm_generate) - troca so o "cerebro"; a
orquestracao (grounding + gate financeiro + envelope) continua no reasoning.py.

Provider-agnostico: qualquer endpoint OpenAI-compatible. Default aponta pro
OpenRouter - o mesmo provider que o engine ja usa.

Structured output (passo 3): o LLM devolve um objeto JSON com a fala E as
etiquetas (technique/stage/commitment_category/outcome). `parse_structured` (pura,
sem rede) valida com leniencia: etiqueta torta/faltando e OMITIDA -> cai no
fallback que ja existe no reasoning (classificador deterministico / default VOSS
/ continue / gate). JSON quebrado -> usa o texto cru como fala. Nada quebra.

Env:
- LLM_API_KEY   (obrig.) - valor da chave; so vai no header, NUNCA logado.
- LLM_BASE_URL  (default https://openrouter.ai/api/v1)
- LLM_MODEL     (default google/gemma-4-31b-it:free)
- LLM_SOUL_PATH / LLM_PLAYBOOK_PATH (persona + playbook)

Caveat: modelos :free tem limite de rate/cota - teste, nao producao.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from .contract import CommitmentCategory, Outcome, ReasonRequest, Technique
from .reasoning import GeneratedTurn

_DEFAULT_BASE = "https://openrouter.ai/api/v1"
# Modelo de producao (passo 4): pago barato, JSON confiavel, bom pt-BR. Ainda
# sobrescrevivel por LLM_MODEL.
_DEFAULT_MODEL = "qwen/qwen3-30b-a3b-instruct-2507"

# Retry so em falha TRANSITORIA. 4xx de config (401/400) nao repete - e erro de
# deploy, tem que falhar alto.
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_BACKOFF_SECONDS = (0.5, 1.0, 2.0)  # 1 tentativa + 3 retries

# SOUL.md traz uma secao de FATOS de EXEMPLO ficticios; os fatos reais vem do
# grounded_facts (por conta+setor). Remover a secao de exemplo evita o LLM
# confundir/citar numero ficticio como se fosse da conta.
_SOUL_EXAMPLES_MARKER = "## Fatos do curso"

_MISSING = object()  # distingue "etiqueta ausente/invalida" (omitir) de None (null do LLM).


def _read(path: Optional[str]) -> str:
    if not path:
        return ""
    p = Path(path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _persona_sem_exemplos(soul: str) -> str:
    idx = soul.find(_SOUL_EXAMPLES_MARKER)
    return soul[:idx].rstrip() if idx != -1 else soul


def build_system_prompt(req: ReasonRequest) -> str:
    """Persona (SOUL, sem os fatos-exemplo) + playbook + FATOS da conta do payload.

    Testavel sem rede.
    """
    soul = _persona_sem_exemplos(_read(os.environ.get("LLM_SOUL_PATH", "hermes-alma/SOUL.md")))
    playbook = _read(os.environ.get("LLM_PLAYBOOK_PATH", "docs/PLAYBOOK.md"))
    facts = json.dumps(req.grounded_facts.model_dump(), ensure_ascii=False)
    rapport = json.dumps(req.rapport, ensure_ascii=False)
    return (
        f"{soul}\n\n{playbook}\n\n"
        "== FATOS DA CONTA (a UNICA fonte de fato) ==\n"
        "Use EXCLUSIVAMENTE os fatos abaixo. Ignore qualquer numero, preco, data "
        "ou exemplo que apareca no texto de persona/playbook acima - aquilo NAO e "
        "desta conta. Se algo nao estiver aqui, diga que confirma com a equipe; "
        "NUNCA invente numero/preco/data.\n"
        f"{facts}\n\n"
        f"Estagio da conversa: {req.stage}. Rapport: {rapport}.\n"
        "Responda SO com um objeto JSON valido (nada fora dele), com estas chaves:\n"
        '{"response_text": "<a fala final ao cliente: curta, natural, pt-BR, '
        'terminando com uma pergunta fechada que avanca a venda>", '
        '"technique": "<VOSS|CHALLENGER|CIALDINI|SPIN>", '
        '"commitment_category": <"preco"|"prazo"|"forma_pagamento"|"desconto"|"frete"|"outro"|null>, '
        '"outcome": "<continue|close|escalate>"}\n'
        "Use null em commitment_category se a fala NAO assume compromisso comercial. "
        "Faca NO MAXIMO um compromisso comercial por fala; se tocar mais de um, "
        "escolha em commitment_category o de MAIOR prioridade de aprovacao: "
        "desconto > preco > forma_pagamento > frete > prazo."
    )


def build_messages(req: ReasonRequest) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": build_system_prompt(req)}]
    for turn in req.history:
        role = "assistant" if turn.role == "bot" else "user"
        msgs.append({"role": role, "content": turn.text})
    msgs.append({"role": "user", "content": req.message})
    return msgs


def _extract_json(raw: str) -> Optional[dict]:
    """Primeiro objeto {...} do texto, parseado. None se nao houver/quebrar."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


_RESPONSE_TEXT_RE = re.compile(r'"response_text"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _salvage_response_text(raw: str) -> Optional[str]:
    """Tenta recuperar so o valor de response_text de um JSON quebrado."""
    m = _RESPONSE_TEXT_RE.search(raw)
    if not m:
        return None
    try:
        return json.loads(f'"{m.group(1)}"')  # desescapa via json
    except json.JSONDecodeError:
        return m.group(1)


def _coerce_enum(value: Any, enum_cls: type) -> Any:
    """Enum coagido (tolerante a caixa), None se o LLM mandou null, ou _MISSING
    se invalido/nao-string."""
    if value is None:
        return None
    if isinstance(value, str):
        for candidate in (value, value.strip().upper(), value.strip().lower()):
            try:
                return enum_cls(candidate)
            except ValueError:
                continue
    return _MISSING


def parse_structured(raw: str) -> dict:
    """Extrai os campos do envelope da saida do LLM (pura, sem rede).

    Regras (fail-safe encadeia no reasoning). So JSON limpo com fala usavel segue
    normal; qualquer outra saida escala (:166, passo 4 - modelo confiavel):
    - sem JSON estruturado (prosa, salvada de truncado, vazia, cercada) -> escala
      (outcome=escalate), preservando a fala recuperavel so como contexto.
    - JSON valido mas response_text faltando/null/vazio -> falha fechada
      (response_text="" + outcome=escalate); nunca serializa o objeto como fala.
    - technique/outcome inválidos ou null -> OMITIDOS (reason aplica default).
    - commitment_category: enum valido -> setado; null explicito -> None PRESERVADO
      (vence o classificador deterministico); invalido/ausente -> omitido (fallback).
    - `stage` NAO e extraido de proposito: a engine e stateless e nao e dona da
      FSM de estagios (o LATE e). A engine sempre ecoa o req.stage; o LLM nao
      opina sobre estagio (evita stage invalido - decisao do dono do repo).
    """
    data = _extract_json(raw)
    if data is None:
        # :166 (passo 4): com modelo JSON confiavel, QUALQUER saida sem JSON
        # estruturado limpo (prosa, salvada de truncado, vazia, cercada) e uma
        # FALHA do modelo -> escala (nao da pra estabelecer metadata de seguranca).
        # Preserva a fala recuperavel so como contexto (no escalate o LATE usa o
        # template seguro).
        salvaged = _salvage_response_text(raw)
        if salvaged:
            text = salvaged
        elif raw.strip() and "{" not in raw and "`" not in raw:
            text = raw
        else:
            text = ""
        return {"response_text": text, "outcome": Outcome.ESCALATE}

    out: dict = {}
    rt = data.get("response_text")
    if not (isinstance(rt, str) and rt.strip()):
        # JSON valido mas sem fala usavel (faltando/null/vazio): NAO entregar o
        # objeto serializado como texto ao cliente (achado Codex) - falha fechada,
        # escala. O _extract_json passou, entao o safeguard de JSON-quebrado nao
        # pega este caso; e o mesmo perigo por outro branch.
        return {"response_text": "", "outcome": Outcome.ESCALATE}
    out["response_text"] = rt

    tech = _coerce_enum(data.get("technique"), Technique)
    if tech is not _MISSING and tech is not None:
        out["technique"] = tech

    outcome = _coerce_enum(data.get("outcome"), Outcome)
    if outcome is not _MISSING and outcome is not None:
        out["outcome"] = outcome

    if "commitment_category" in data:
        cat = _coerce_enum(data["commitment_category"], CommitmentCategory)
        if cat is not _MISSING:  # inclui None (null explicito) - preservado de proposito
            out["commitment_category"] = cat

    return out


def llm_generate(req: ReasonRequest) -> GeneratedTurn:
    key = os.environ.get("LLM_API_KEY")
    if not key:  # fail-closed
        raise RuntimeError("LLM_API_KEY ausente")
    base = os.environ.get("LLM_BASE_URL", _DEFAULT_BASE)
    if not base.lower().startswith("https://"):  # nunca mandar o bearer em cleartext (L91)
        raise RuntimeError("LLM_BASE_URL deve ser HTTPS")
    model = os.environ.get("LLM_MODEL", _DEFAULT_MODEL)
    payload = {
        "model": model,
        "messages": build_messages(req),
        "temperature": 0.4,
        "max_tokens": 500,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}

    # Retry so em falha transitoria (429/5xx/timeout/conexao). 4xx de config
    # (401/400) propaga na hora. Esgotou -> escala (falha fechada, nao derruba o
    # /reason com 500).
    for attempt in range(len(_BACKOFF_SECONDS) + 1):
        try:
            resp = httpx.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=90)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            return GeneratedTurn(**parse_structured(text))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _RETRY_STATUS:
                raise  # erro de config/cliente -> falha alto
        except httpx.RequestError:
            pass  # timeout/conexao -> transitorio
        if attempt < len(_BACKOFF_SECONDS):
            time.sleep(_BACKOFF_SECONDS[attempt])

    return GeneratedTurn(response_text="", outcome=Outcome.ESCALATE)
