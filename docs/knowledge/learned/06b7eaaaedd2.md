---
id: 06b7eaaaedd2
question: How does a DAL generator domain emit a variable number of files from one builder, a builder returning many path and content pairs?
model: nemotron-3-super:120b
learned: 2026-10-27T08:41:54Z
source: datrix-codegen-kernel/docs/architecture.md 128cb250a947526a685d5e0f32092ca152c372bc56630b384d024acffb0150b8
source: datrix/docs/architecture/packs/codegen-engine.md 23bbd7d6715c67669cd18df641332b70ea7dfd30894de541027ab0a470c48925
---

A domain builder returns a list of GeneratedFile objects, each with a path and content, enabling emission of a variable number of files from one builder.  
datrix-codegen-kernel/docs/architecture.md:1459  
Domain builders receive the current scope and return a list of GeneratedFile objects.  
datrix-codegen-kernel/docs/architecture.md:1459  
They provide an escape hatch for complex generation logic that doesn't fit the declarative file model.  
datrix-codegen-kernel/docs/architecture.md:1459  
Example: builder graphql.build_all_graphql_files;  
datrix-codegen-kernel/docs/architecture.md:1463  
The builder function is a dotted Python path returning GeneratedFile list.  
datrix-codegen-kernel/docs/architecture.md:1350-1353  
Context builders are called once per domain or iteration scope and return frozen dataclass instances.  
datrix-codegen-kernel/docs/architecture.md:1353  
The builder carries the preconditions and builds the shared typed context where the domain has one.  
datrix/docs/architecture/packs/codegen-engine.md:31  
No per-domain micro-generator, hooks class or orchestrator exists in a backend package.  
datrix/docs/architecture/packs/codegen-engine.md:31
