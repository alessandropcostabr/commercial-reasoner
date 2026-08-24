# Commercial Reasoner

An AI sales reasoning system for lead qualification, verified business information and
goal-directed conversations across messaging channels.

## What it is

Commercial Reasoner is a conversational agent that qualifies leads, negotiates, and drives
conversations toward a close — using established sales frameworks (SPIN, Challenger,
Cialdini, Voss) instead of a single fixed script. It decides *which* technique to apply
and *when*, based on the lead's stage in the conversation and how much rapport has been
established.

The core design principle is **factual grounding**: the reasoner never states a specific
business fact (price, availability, dates) unless that fact was explicitly provided as
verified context for that conversation. Persuasion technique and factual knowledge are
kept as separate concerns — the model is free to apply sales technique creatively, but
never free to invent a number.

## How it works

- **Gateway:** [Hermes](https://github.com/NousResearch/hermes-agent) handles the
  conversational surface (message routing, session lifecycle).
- **Reasoning:** an LLM (via [OpenRouter](https://openrouter.ai)) drives the conversation,
  conditioned by a persona/playbook prompt layer rather than fine-tuned weights.
- **Memory:** conversation history and per-contact context are persisted via
  [claude-mem](https://github.com/thedotmack/claude-mem) and, experimentally,
  [Honcho](https://github.com/plastic-labs/honcho).

## Status

This repository holds the current persona/skill prompt layer (`hermes-alma/`) and the
deployment stack (`docker/`). Facts referenced in the example prompts (school name,
pricing, address) are fictional placeholders illustrating the grounding pattern, not real
business data.

## License

MIT — see [LICENSE](./LICENSE).
