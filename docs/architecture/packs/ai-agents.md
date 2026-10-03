# Pack: AI Agents — Model-Driven Tool Loops as a Declared Block

**Read when:** you touch the `agents` service block, `tool`/`agent` declarations, model providers, `approval`, `replay` fixtures, or agent observability signals.
**Not for:** the engineering agents that work on this repo (see `.claude/`).
**Core map:** [architecture-cheat-sheet.md](../architecture-cheat-sheet.md)

[Decision 46](../architecture-overview.md#decision-46-ai-agents--model-driven-tool-loops-as-a-declared-service-block-approved--implementation-in-progress) — Approved; Phases 1–2 implemented, Phase 3 not started.

An `agents <alias> { model h; tool T(…) -> R : description('…') { ensure …; … } agent A(…) -> R { model(h); tools(…); steps(N); attachments(p); prompt { … } } }` service block: the author declares, the generator emits a bounded observe → decide → act → update loop. Provider, model id, sampling, timeout, key handle and budget live under the block alias in the service ConfigDSL (`provider` = API family, `flavor` = `container`/`external`/`managed`/`direct`).

- The model chooses only among declared tools (closed at generation); model-supplied arguments are untrusted input, parsed and checked by the tool's leading `ensure` clauses; tools run with the caller's identity; a model result is data, parsed against the declared type before use.
- Provider realization is a required per-provider platform declaration (absence is a construction error; no provider name in shared layers). Keys are logical secret handles; off-loopback transport is verified TLS unless `allowPlaintextHttp = true` with `auth = "none"`; no certificate-verification switch exists.
- `test` never reaches a live model (`replay` provider only, fixtures selected by `: replay('…')`). Every limit and budget field is realized before the call that would exceed it. Logs carry identity and counts, never content.
- Every language and platform is obligated (`MODEL` builtin group + `agents` domain) or carries a counted gap; the pre-generation realization stage rejects an `agents` block on a non-realizing language before any file is written.
- Phase 2 added the fail-closed `approval` marker (suspended run behind an injected request row — the compare-and-set contract — four role-gated endpoints, deciding principal never the requester, continuation declared on the agent), managed model placement on AWS/Azure, model calls as a resilient-client dependency kind, and agent signals on the five observability categories. Cost budgets stay rejected; live-turn fixture capture is out of scope.
