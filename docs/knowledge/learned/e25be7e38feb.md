---
id: e25be7e38feb
question: which examples show extern service with a mock implementation, seed baseline data and login for a demo application
model: qwen3-coder:30b-ctx32k
learned: 2026-11-04T22:49:14Z
source: datrix-codegen-kernel/docs/architecture.md c8604923a8029cd25955df12cff5c83b050000af59d583c04f910514e5f377e5
source: datrix-language/docs/reference/datrix-syntax-reference.md 79ca880531867145db022ca397cab23bd1c27797521bfd0120845fff9d4c8ab6
source: datrix-language/docs/reference/dseed-reference.md 62cbf4ca41bb750ef872374c80d6ea8c73f8704181c4a38cb755ff88d97957d6
source: datrix/docs/architecture/architecture/builtin-traits-enums.md fe741999a8e766653394847a3d0f9b5a9200208180084b706fabdb0300521aef
---

datrix-language/docs/reference/dseed-reference.md:80| `baseline` seeds are for functional starting state (seed org, admin user, subscriptions)
datrix-language/docs/reference/dseed-reference.md:356-408| Complete example shows `reference` and `baseline` categories in seed files
datrix-language/docs/reference/datrix-syntax-reference.md:4917-4935| `login` flag for identity provider handling in applications
datrix/docs/architecture/architecture/builtin-traits-enums.md:41-52| `Seed` builtin objects for reference data, usable in `.dseed` and `.dtrx`
datrix-codegen-kernel/docs/architecture.md:615-619| Seed reference datasets loaded lazily from JSON files
