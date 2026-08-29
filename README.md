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

The reasoner never states a specific business fact (price, availability, dates) unless
that fact was explicitly provided as verified context (`grounded_facts`) for that
conversation. Persuasion technique and factual knowledge are kept as separate concerns:
the model is free to apply sales technique creatively, but never free to invent a number.

This is enforced by a **deterministic, LLM-free gate**
(`src/commercial_reasoner/memory/gate.py` + `numeric_guard.py`) that scans every generated
reply before it goes out:

- Every `R$` amount and `%` in the reply is matched with regex and checked against the
  `grounded_facts` sent for that conversation. An amount that isn't in the table is
  blocked, no exceptions.
- Installment plans get an **arithmetic check**, not just a lookup: `(total - down
  payment) / installment value` is derived from the grounded facts and compared against
  the number of installments the reply actually claims.
- **Fail-closed on ambiguity.** Two payment plans, two down payments, or two product
  families in the same sentence can't be safely linked to the right numbers, so the gate
  blocks rather than risk matching the wrong ones.
- A blocked reply never reaches the customer: it flips the response `outcome` to
  `escalate` so the integrator (e.g. LATE) can hold it for human review instead of
  auto-sending.

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
