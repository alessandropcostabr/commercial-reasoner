"""Fase 1 - loader + gate ligados no /reason: dinheiro errado -> escala."""
from commercial_reasoner.service.contract import CommitmentCategory, Outcome, ReasonRequest, Technique
from commercial_reasoner.service.reasoning import GeneratedTurn, reason


def _req(with_facts: bool = True) -> ReasonRequest:
    gf = (
        {"prices": [{"modality": "upfront", "value": 1000}], "other_numbers": [10]}
        if with_facts
        else {}
    )
    return ReasonRequest(
        correlation_token="tok",
        message="quanto custa?",
        history=[],
        grounded_facts=gf,
        rapport={"heat": "quente"},
        stage="closing",
    )


def _gen(text: str, **extra):
    def g(_req):
        return GeneratedTurn(
            response_text=text,
            technique=Technique.CIALDINI,
            outcome=Outcome.CONTINUE,
            **extra,
        )

    return g


def test_gate_bloqueia_dinheiro_inventado_escala():
    env = reason(_req(), generate=_gen("Consigo fazer por R$ 1.500."))
    assert env.outcome is Outcome.ESCALATE  # 1500 nao confere -> escala


def test_gate_permite_dinheiro_correto_mantem_outcome():
    env = reason(_req(), generate=_gen("À vista fica R$ 1.000."))
    assert env.outcome is Outcome.CONTINUE  # 1000 confere upfront


def test_resposta_sem_dinheiro_continua():
    env = reason(_req(), generate=_gen("Quer que eu já reserve sua vaga?"))
    assert env.outcome is Outcome.CONTINUE


def test_grounded_facts_vazio_com_dinheiro_escala():
    # sem fatos da conta, qualquer valor financeiro nao confere -> escala.
    env = reason(_req(with_facts=False), generate=_gen("Fica R$ 1.000."))
    assert env.outcome is Outcome.ESCALATE


def test_stub_default_gera_envelope_valido_e_continua():
    env = reason(_req())  # gerador stub (sem dinheiro)
    assert env.correlation_token == "tok"
    assert env.event_id.startswith("commercial-reasoner:")
    assert env.outcome is Outcome.CONTINUE


def test_commitment_category_deterministica_quando_gerador_omite():
    # gerador nao informa commitment_category -> classificador rotula pelo texto.
    env = reason(_req(), generate=_gen("À vista fica R$ 1.000."))
    assert env.commitment_category is CommitmentCategory.PRECO


def test_commitment_category_do_gerador_tem_prioridade():
    # gerador informa (structured output futuro) -> vence o deterministico.
    env = reason(
        _req(),
        generate=_gen("À vista fica R$ 1.000.", commitment_category=CommitmentCategory.DESCONTO),
    )
    assert env.commitment_category is CommitmentCategory.DESCONTO


def test_commitment_category_none_explicita_do_gerador_vence_heuristico():
    # gerador decide "sem compromisso" (None explicito) -> heuristico NAO sobrepoe,
    # mesmo com "desconto" no texto (achado Codex: presenca da chave, nao truthiness).
    env = reason(
        _req(),
        generate=_gen("Nao oferecemos desconto neste curso.", commitment_category=None),
    )
    assert env.commitment_category is None
