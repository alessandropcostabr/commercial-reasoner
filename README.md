# Commercial Reasoner

An AI sales reasoning system for lead qualification, verified business information and
goal-directed conversations across messaging channels.

## What it is

Commercial Reasoner is a conversational agent that qualifies leads, negotiates, and drives
conversations toward a close — using established sales frameworks (SPIN, Challenger,
Cialdini, Voss) instead of a single fixed script. It decides *which* technique to apply
and *when*, based on the lead's stage in the conversation and how much rapport has been
established.

## Grounding: numbers are never invented

The design principle is that the reasoner may apply sales technique freely but must never
invent a business fact: it should state a price, availability, or date only when that fact
was provided as verified context (`grounded_facts`) for the conversation.

This principle is carried at two levels of different strength:

- **Prompt-level grounding (all fact types).** The persona/skill layer instructs the model
  not to assert unverified facts of any kind. This is an LLM instruction, not a hard
  guarantee.
- **Deterministic gate (monetary values and percentages only).** On the `/reason` service
  path (the path LATE integrates with, see `API_CONTRACT_LATE.md`), a deterministic,
  LLM-free gate (`src/commercial_reasoner/memory/gate.py` + `numeric_guard.py`) scans every
  reply produced through `/reason` before it goes out and hard-blocks bad numbers. It
  matches only `R$` amounts and `%` tokens; non-numeric claims (dates, availability, free
  text) are not gate-enforced, and replies not routed through `/reason` (e.g. a gateway
  wired straight to Telegram) are not covered.

What the numeric scan does:

- Every well-formed `R$` amount and `%` in the reply is matched with regex against the
  `grounded_facts` sent for that conversation; an amount that isn't in the table is blocked.
- Installment plans get an **arithmetic check**, not just a lookup: **when the family
  total is present** in the grounded facts, `(total - down payment) / installment value`
  is derived and compared against the number of installments the reply claims. For legacy
  facts that carry only the installment value and no total, the amount is still matched but
  the count is not arithmetically enforced.
- **Wrong or invented numbers fail closed.** An amount not present in the grounded facts is
  blocked; an amount that exists but is asserted for the wrong modality (e.g. "à vista R$
  1.200" when cash is R$ 1.000) is blocked. A correct amount stated without a specific
  modality is allowed (it's a valid figure). The gate reasons over payment modalities, not
  product identity.
- On a block, the engine does not suppress the text itself: it flips the response `outcome`
  to `escalate` and still returns the original `response_text` in the callback. Keeping it
  away from the customer depends on the integrator (e.g. LATE) honoring `escalate` and
  holding the reply for human review instead of auto-sending.

Scope of the numeric gate: it operates on parsed `R$`/`%` tokens and resolves one payment
modality per sentence, so it is a deterministic backstop for well-formed monetary claims,
not a formal proof. Unusual numeric formats (e.g. signed values) or a single sentence mixing
several modality hints can fall outside its checks; prompt-level grounding remains the first
line for those cases.

## How it works

- **Gateway:** [Hermes](https://github.com/NousResearch/hermes-agent) handles the
  conversational surface (message routing, session lifecycle).
- **Reasoning:** an LLM (via [OpenRouter](https://openrouter.ai)) drives the conversation,
  conditioned by a persona/playbook prompt layer rather than fine-tuned weights.
- **Memory:** conversation history and per-contact context need a primary store, and that
  choice hasn't been made yet. Two candidates run side by side today,
  [claude-mem](https://github.com/thedotmack/claude-mem) (`docker/`) and, experimentally,
  [Honcho](https://github.com/plastic-labs/honcho) (`docker-honcho-distribuido/`), each
  its own full Postgres+cache stack. This is a **pending decision, not a dual-backend
  feature**: one has to be picked as primary before this scales further, to avoid running
  two databases for the same job.

## Status

This repository holds the current persona/skill prompt layer (`hermes-alma/`) and two
deployment stacks (`docker/`, `docker-honcho-distribuido/`) reflecting the memory decision
above. Facts referenced in the example prompts (school name, pricing, address) are
fictional placeholders illustrating the grounding pattern, not real business data.

## License

MIT — see [LICENSE](./LICENSE).
