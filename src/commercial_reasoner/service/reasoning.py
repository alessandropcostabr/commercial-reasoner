"""Orquestracao do /reason: gera resposta -> grounding -> gate -> envelope.

Stateless: os fatos vem no request (grounded_facts). O gerador de resposta e
INJETAVEL (idioma da lib: como LLMExtractFn) - stub deterministico agora, Qwen +
SOUL + PLAYBOOK na Fase 1 seguinte, sem tocar esta orquestracao nem os testes.

Fronteira (design gate D3): a engine DECIDE. Se o gate bloqueia (valor financeiro
que nao confere), sinaliza `outcome=escalate` -> o LATE mostra a resposta-segura
(template da config) e avisa humano; a engine nao envia nada por conta propria.
"""
from __future__ import annotations

from typing import Callable, Optional

from ..memory import canonical_from_mapping, check_response
from .commitment import classify_commitment
from .contract import (
    CommitmentCategory,
    Outcome,
    ReasonRequest,
    ResponseEnvelope,
    Technique,
    build_envelope,
)

# Gerador de resposta: recebe o request, devolve os campos "de conteudo" do
# envelope. So o texto/tecnica/estagio; o gate e o envelope sao deste modulo.
GenerateFn = Callable[[ReasonRequest], "GeneratedTurn"]


class GeneratedTurn(dict):
    """Contrato do gerador: response_text (obrig.) + technique/outcome/rapport/
    stage/commitment_category (opcionais). dict simples p/ ser trivial de mockar."""


def _stub_generate(req: ReasonRequest) -> GeneratedTurn:
    return GeneratedTurn(
        response_text="(stub) resposta de contrato - reasoning real vem na Fase 1",
        technique=Technique.VOSS,
        outcome=Outcome.CONTINUE,
    )


def reason(req: ReasonRequest, generate: GenerateFn = _stub_generate) -> ResponseEnvelope:
    gen = generate(req)
    response_text: str = gen["response_text"]
    technique: Technique = gen.get("technique", Technique.VOSS)
    outcome: Outcome = gen.get("outcome", Outcome.CONTINUE)
    # Categoria do compromisso: o gerador tem prioridade (structured output do LLM,
    # passo futuro); sem ele, classificador deterministico rotula pelo texto.
    commitment: Optional[CommitmentCategory] = gen.get("commitment_category") or classify_commitment(
        response_text
    )

    # Gate financeiro deterministico sobre os fatos da conta (payload) - sem LLM.
    canonical = canonical_from_mapping(req.grounded_facts.model_dump())
    verdict = check_response(response_text, canonical)
    if verdict.decision == "block":
        # Valor financeiro nao confere -> escala; o LATE nao auto-envia.
        outcome = Outcome.ESCALATE

    return build_envelope(
        req,
        response_text=response_text,
        technique=technique,
        outcome=outcome,
        commitment_category=commitment,
        rapport=gen.get("rapport", "__inherit__"),
        stage=gen.get("stage"),
        bant=gen.get("bant"),
    )
