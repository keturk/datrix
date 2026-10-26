---
id: 2bb5f6fa1ce3
question: how is an invariant over every registered platform's generated output carried: a set comparison of what each platform's rendered artifacts provision against a kernel plan -- conformance probe, parity case row, or generation-time validator?
model: qwen3-coder:30b-ctx32k
learned: 2026-10-26T03:40:10Z
source: datrix-codegen-kernel/docs/architecture.md 35d80876b97943f80263a5082dcfc38cf0c72165a0bb881d1cc6fc7e1306d3c6
source: datrix/docs/architecture/packs/parity-and-obligation.md 725fc647893f901f3d94789c27391416b439d37bbc49212cd1440d1c6d8f955d
---

A set comparison of each platform's rendered artifacts against a kernel plan is carried via **conformance probes**. Each registered target implements its own probe logic in its package (`conformance_probes.py`, class `LanguageProbes` / `PlatformProbes`) [datrix-codegen-kernel/docs/architecture.md:1671]. These probes are resolved and executed by gates like `parity-cases-gate.ps1` which reads every row on every registered target of its axis [datrix/docs/architecture/packs/parity-and-obligation.md:18]. The probe methods define what is read from each generated artifact, such as response body wire fields, route wire contracts, and event envelopes [datrix-codegen-kernel/docs/architecture.md:1660-1664]. A parity row in `datrix/scripts/gates/parity/cases/<area>.parity.yaml` defines the expectation against which each target's probe result is compared [datrix/docs/architecture/packs/parity-and-obligation.md:18]. The gate fails closed if a missing member or probe method raises `PluginValidationError` [datrix-codegen-kernel/docs/architecture.md:1665].
