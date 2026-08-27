"""Gerador de resposta via LLM OpenAI-compatible (default: OpenRouter + Nemotron free).

Injetavel em reasoning.reason(generate=llm_generate) - troca so o "cerebro"; a
orquestracao (grounding + gate financeiro + envelope) continua no reasoning.py.

Provider-agnostico: qualquer endpoint OpenAI-compatible. Default aponta pro
OpenRouter (que expoe Nemotron/NVIDIA free) - o mesmo provider que o engine ja usa.

Env:
- LLM_API_KEY   (obrig.) - valor da chave; so vai no header, NUNCA logado.
- LLM_BASE_URL  (default https://openrouter.ai/api/v1)
- LLM_MODEL     (default nvidia/nemotron-3-super-120b-a12b:free)
- LLM_SOUL_PATH / LLM_PLAYBOOK_PATH (persona + playbook)

Caveat: modelos :free tem limite de rate/cota - teste, nao producao.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import httpx

from .contract import ReasonRequest, Technique
from .reasoning import GeneratedTurn

_DEFAULT_BASE = "https://openrouter.ai/api/v1"
_DEFAULT_MODEL = "google/gemma-4-31b-it:free"

# SOUL.md traz uma secao de FATOS de EXEMPLO ficticios; os fatos reais vem do
# grounded_facts (por conta+setor). Remover a secao de exemplo evita o LLM
# confundir/citar numero ficticio como se fosse da conta.
_SOUL_EXAMPLES_MARKER = "## Fatos do curso"


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
        "Responda SO com a fala final ao cliente (sem raciocinio, sem meta-texto): "
        "curta, natural, pt-BR, terminando com uma pergunta fechada que avanca a venda."
    )


def build_messages(req: ReasonRequest) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": build_system_prompt(req)}]
    for turn in req.history:
        role = "assistant" if turn.role == "bot" else "user"
        msgs.append({"role": role, "content": turn.text})
    msgs.append({"role": "user", "content": req.message})
    return msgs


def llm_generate(req: ReasonRequest) -> GeneratedTurn:
    key = os.environ.get("LLM_API_KEY")
    if not key:  # fail-closed
        raise RuntimeError("LLM_API_KEY ausente")
    base = os.environ.get("LLM_BASE_URL", _DEFAULT_BASE)
    if not base.lower().startswith("https://"):  # nunca mandar o bearer em cleartext (L91)
        raise RuntimeError("LLM_BASE_URL deve ser HTTPS")
    model = os.environ.get("LLM_MODEL", _DEFAULT_MODEL)

    resp = httpx.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        json={
            "model": model,
            "messages": build_messages(req),
            "temperature": 0.4,
            "max_tokens": 400,
        },
        timeout=90,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"].strip()
    # Tecnica/estagio/commitment estruturados = passo seguinte (structured output);
    # aqui so o texto. O gate financeiro (reasoning.py) roda sobre ele.
    return GeneratedTurn(response_text=text, technique=Technique.VOSS)
