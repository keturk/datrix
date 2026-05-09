# Delegation Performance Metrics Specification

**Last Updated:** 2026-05-09
**Version:** 1.0

---

## Overview

This specification defines metrics for evaluating skill delegation performance. The delegation architecture aims to deliver:
- **Cost reduction:** 50-90% via strategic model selection (Haiku for mechanical tasks vs. Opus for everything)
- **Latency improvement:** 20%+ via parallel phase execution
- **Quality preservation:** No regression in task success rate or diagnostic accuracy

This document specifies what to measure, where to capture it, and how to report it.

---

## Metric Categories

### 1. Cost Metrics

Track token consumption and costs per skill invocation to validate cost reduction claims.

#### Metrics to Capture

| Metric | Definition | Unit |
|--------|------------|------|
| `phase_input_tokens` | Tokens in prompt sent to agent | integer |
| `phase_output_tokens` | Tokens in agent's response | integer |
| `phase_total_tokens` | `input_tokens + output_tokens` | integer |
| `phase_model` | Model used for phase | `"haiku"` \| `"sonnet"` \| `"opus"` |
| `phase_cost` | `total_tokens × model_rate` | float (USD) |
| `skill_total_cost` | Sum of all `phase_cost` for skill invocation | float (USD) |
| `estimated_monolithic_cost` | Estimated cost if skill ran on Opus for entire workflow | float (USD) |
| `cost_savings_pct` | `(estimated_monolithic - actual) / estimated_monolithic × 100` | float (%) |

#### Model Rates (as of 2026-05-09)

| Model | Input (per MTok) | Output (per MTok) |
|-------|------------------|-------------------|
| Haiku | $0.25 | $1.25 |
| Sonnet | $3.00 | $15.00 |
| Opus | $15.00 | $75.00 |

**Note:** Rates may change. Update this table when Claude API pricing changes.

#### Calculation Formula

**Phase cost:**
```
phase_cost = (input_tokens / 1_000_000 × input_rate) + (output_tokens / 1_000_000 × output_rate)
```

**Estimated monolithic cost:**
```
estimated_monolithic_cost = sum(all phase input/output tokens) / 1_000_000 × opus_rate
```

**Example:**

Phase 1 (Haiku):
- Input: 5,000 tokens, Output: 2,000 tokens
- Cost: (5000/1M × $0.25) + (2000/1M × $1.25) = $0.00125 + $0.0025 = $0.00375

Phase 2 (Opus):
- Input: 12,000 tokens, Output: 3,000 tokens
- Cost: (12000/1M × $15) + (3000/1M × $75) = $0.18 + $0.225 = $0.405

Total: $0.40875
Monolithic (Opus for 22K tokens): (17000/1M × $15) + (5000/1M × $75) = $0.255 + $0.375 = $0.63
Savings: ($0.63 - $0.41) / $0.63 × 100 = 35%

---

### 2. Latency Metrics

Track wall-clock execution time to validate latency reduction claims from parallelization.

#### Metrics to Capture

| Metric | Definition | Unit |
|--------|------------|------|
| `phase_start_time` | Wall-clock time when phase execution started | ISO 8601 timestamp |
| `phase_end_time` | Wall-clock time when phase execution completed | ISO 8601 timestamp |
| `phase_duration_sec` | `end_time - start_time` in seconds | float (seconds) |
| `phase_agent_count` | Number of agents spawned for phase | integer |
| `skill_total_duration_sec` | Sum of all `phase_duration_sec` | float (seconds) |
| `estimated_monolithic_duration_sec` | Estimated duration if all parallel work ran sequentially | float (seconds) |
| `latency_savings_pct` | `(estimated_monolithic - actual) / estimated_monolithic × 100` | float (%) |

#### Calculation Formula

**Phase duration:**
```
phase_duration_sec = (phase_end_time - phase_start_time).total_seconds()
```

**Estimated monolithic duration:**
```
For each parallelizable phase with N agents:
  sequential_duration = phase_duration_sec × agent_count

estimated_monolithic_duration = sum(sequential_durations for parallelizable phases) + sum(actual durations for sequential phases)
```

**Example:**

Phase 1 (sequential): 30s
Phase 2 (3 parallel agents): 45s
Phase 3 (sequential): 60s

Actual total: 30s + 45s + 60s = 135s
Monolithic (phase 2 runs sequentially): 30s + (3 × 45s) + 60s = 225s
Savings: (225 - 135) / 225 × 100 = 40%

**Note:** This is a simplification. Actual monolithic execution may have different latency characteristics due to context size and model behavior.

---

### 3. Quality Metrics

Track task success and intervention rates to validate that delegation does not degrade quality.

#### Metrics to Capture

| Metric | Definition | Unit |
|--------|------------|------|
| `phase_status` | Outcome of phase execution | `"success"` \| `"failed"` |
| `phase_success_rate` | `successful_phases / total_phases × 100` | float (%) |
| `skill_status` | Outcome of entire skill invocation | `"completed"` \| `"failed"` \| `"blocked"` |
| `skill_success_rate` | `successful_skills / total_skills × 100` | float (%) |
| `user_intervention_count` | Number of times user input was required (confidence gates, ambiguity resolution) | integer |
| `user_intervention_rate` | `interventions / total_skills × 100` | float (%) |

#### Quality Targets

- **Phase success rate:** >= 95%
- **Skill success rate:** >= 90%
- **User intervention rate:** <= 10%

**Comparison to monolithic baseline:** Track the same metrics for monolithic skill execution (if available) to ensure delegation does not regress quality.

---

## Instrumentation Points

### Where to Capture Metrics

Metrics are captured by the **phase orchestrator** at specific points in the execution workflow:

| Point | Metrics Captured |
|-------|------------------|
| **Before spawning agents** | `phase_start_time`, `phase_model`, `phase_agent_count` |
| **After agents complete** | `phase_end_time`, `phase_duration_sec`, `phase_input_tokens`, `phase_output_tokens`, `phase_total_tokens`, `phase_cost`, `phase_status` |
| **After all phases complete** | `skill_total_cost`, `skill_total_duration_sec`, `skill_status`, `estimated_monolithic_cost`, `estimated_monolithic_duration_sec`, `cost_savings_pct`, `latency_savings_pct` |
| **On user intervention** | `user_intervention_count` |

### How to Access Token Counts

Claude Code provides token usage information in API responses. The orchestrator should extract:
- `input_tokens` — from the request metadata
- `output_tokens` — from the response metadata

**Note:** If token counts are not directly available, they can be estimated using a tokenizer (e.g., `tiktoken` for OpenAI models, or Claude's tokenizer). However, direct API metadata is preferred for accuracy.

---

## Output Format

### Metrics File: `metrics.jsonl`

All metrics are written to `.agent_output/{session_id}/metrics.jsonl` in JSON Lines format (one JSON object per line).

**Why JSON Lines?**
- Append-only (no need to parse entire file to add a new metric)
- Streaming-friendly (can tail the file to see real-time metrics)
- Easy to aggregate with standard tools (e.g., `jq`, pandas)

### Metric Event Schema

Each line in `metrics.jsonl` is a JSON object representing one metric event:

```json
{
  "timestamp": "2026-05-09T14:32:15.123Z",
  "event_type": "phase_start" | "phase_complete" | "skill_complete" | "user_intervention",
  "skill_name": "execute-tasks",
  "phase_name": "baseline",
  "phase_index": 1,
  "data": {
    // Event-specific fields
  }
}
```

### Event Types

#### `phase_start`

```json
{
  "timestamp": "2026-05-09T14:32:15.123Z",
  "event_type": "phase_start",
  "skill_name": "execute-tasks",
  "phase_name": "baseline",
  "phase_index": 1,
  "data": {
    "model": "haiku",
    "parallelizable": true,
    "agent_count": 3
  }
}
```

#### `phase_complete`

```json
{
  "timestamp": "2026-05-09T14:32:27.456Z",
  "event_type": "phase_complete",
  "skill_name": "execute-tasks",
  "phase_name": "baseline",
  "phase_index": 1,
  "data": {
    "status": "success",
    "duration_sec": 12.333,
    "input_tokens": 15000,
    "output_tokens": 4200,
    "total_tokens": 19200,
    "cost_usd": 0.00905,
    "agent_count": 3
  }
}
```

#### `skill_complete`

```json
{
  "timestamp": "2026-05-09T14:35:42.789Z",
  "event_type": "skill_complete",
  "skill_name": "execute-tasks",
  "data": {
    "status": "completed",
    "total_phases": 5,
    "successful_phases": 5,
    "failed_phases": 0,
    "total_duration_sec": 207.666,
    "total_cost_usd": 0.42,
    "estimated_monolithic_cost_usd": 2.80,
    "cost_savings_pct": 85.0,
    "estimated_monolithic_duration_sec": 225.0,
    "latency_savings_pct": 7.7,
    "user_interventions": 0
  }
}
```

#### `user_intervention`

```json
{
  "timestamp": "2026-05-09T14:33:42.123Z",
  "event_type": "user_intervention",
  "skill_name": "troubleshoot-and-fix",
  "phase_name": "root_cause_analysis",
  "data": {
    "reason": "confidence_gate",
    "confidence_level": "MEDIUM",
    "message": "Root cause identified with MEDIUM confidence. Review before proceeding?"
  }
}
```

---

## Reporting Format

### In-Skill Checkpoint Reports

Each phase checkpoint should include cost and latency info:

```
CHECKPOINT — Phase 2: Baseline Test Capture
Status: COMPLETED
Model: haiku
Agents: 3 (parallel)
Duration: 12s
Cost: $0.009
Results: 3/3 successful
  - task-40-01: 12/12 tests passing
  - task-40-02: 8/8 tests passing
  - task-40-03: 15/15 tests passing
```

### Final Skill Report

Include aggregated metrics in final report:

```
EXECUTION COMPLETE — /execute-tasks

Overall Status: COMPLETED

Phases executed: 5/5
1. pre_check (haiku, 1 agent, 8s, $0.002)
2. baseline (haiku, 3 agents, 12s, $0.009)
3. implement (sonnet, 1 agent, 145s, $0.35)
4. verify (haiku, 3 agents, 18s, $0.012)
5. quality_gate (opus, 1 agent, 25s, $0.047)

Performance Metrics:
Cost: $0.42 (estimated $2.80 monolithic, 85% savings)
Latency: 208s (estimated 225s monolithic, 8% savings)
Quality: 5/5 phases successful, 0 user interventions
```

### Aggregate Reporting (Future)

For analyzing trends across multiple skill invocations:

```bash
# Extract all skill_complete events
cat .agent_output/*/metrics.jsonl | jq 'select(.event_type == "skill_complete")'

# Aggregate cost savings
cat .agent_output/*/metrics.jsonl | jq -s 'map(select(.event_type == "skill_complete")) | map(.data.cost_savings_pct) | add / length'

# Count user interventions
cat .agent_output/*/metrics.jsonl | jq -s 'map(select(.event_type == "user_intervention")) | length'
```

**Future work:** Build a dashboard or reporting tool that aggregates `metrics.jsonl` files across sessions to visualize ROI trends.

---

## Example Calculation Walkthrough

### Scenario

Skill: `/execute-tasks` with 3 tasks

Delegation strategy: 5 phases (pre_check, baseline, implement, verify, quality_gate)

### Phase-by-Phase Metrics

| Phase | Model | Agents | Duration | Input Tokens | Output Tokens | Cost |
|-------|-------|--------|----------|--------------|---------------|------|
| pre_check | haiku | 1 | 8s | 6,000 | 1,500 | $0.0034 |
| baseline | haiku | 3 | 12s | 18,000 | 4,200 | $0.0098 |
| implement | sonnet | 1 | 145s | 25,000 | 8,000 | $0.195 |
| verify | haiku | 3 | 18s | 21,000 | 5,400 | $0.0120 |
| quality_gate | opus | 1 | 25s | 15,000 | 2,500 | $0.4125 |
| **TOTAL** | — | — | **208s** | **85,000** | **21,600** | **$0.6327** |

### Cost Calculation

**Actual cost (delegated):**
```
$0.0034 + $0.0098 + $0.195 + $0.0120 + $0.4125 = $0.6327
```

**Estimated monolithic cost (Opus for everything):**
```
Input: 85,000 tokens × $15/MTok = $1.275
Output: 21,600 tokens × $75/MTok = $1.620
Total: $2.895
```

**Savings:**
```
($2.895 - $0.633) / $2.895 × 100 = 78.1%
```

### Latency Calculation

**Actual latency (delegated):**
```
208s (sum of all phase durations)
```

**Estimated monolithic latency:**
```
Pre_check (1 agent): 8s
Baseline (3 agents → sequential): 3 × 12s = 36s
Implement (1 agent): 145s
Verify (3 agents → sequential): 3 × 18s = 54s
Quality_gate (1 agent): 25s

Total: 8 + 36 + 145 + 54 + 25 = 268s
```

**Savings:**
```
(268 - 208) / 268 × 100 = 22.4%
```

### Quality Metrics

- Phases successful: 5/5 (100%)
- Skill status: COMPLETED
- User interventions: 0

### Final Report

```
EXECUTION COMPLETE — /execute-tasks

Overall Status: COMPLETED

Performance Metrics:
Cost: $0.63 (estimated $2.90 monolithic, 78% savings)
Latency: 208s (estimated 268s monolithic, 22% savings)
Quality: 5/5 phases successful, 0 user interventions
```

---

## Quality Assurance

### Validation

Before using delegation metrics in production:

1. **Validate token counts:** Compare API-reported token counts to manual tokenizer estimates. Ensure accuracy within 5%.
2. **Validate cost calculations:** Cross-check phase costs against Claude API billing.
3. **Validate latency measurements:** Use `time` command or similar to verify wall-clock duration matches logged metrics.

### Calibration

Periodically recalibrate estimated monolithic costs/latencies by:
1. Running a skill in monolithic mode (without delegation)
2. Comparing actual monolithic metrics to estimates
3. Adjusting estimation formulas if discrepancies exceed 10%

---

## Related Documentation

- [Skill Delegation Metadata Schema](skill-delegation-schema.md) — Frontmatter and phase marker definitions
- [Phase Orchestrator Specification](phase-orchestrator-spec.md) — Execution workflow (where metrics are captured)
- [Skill Authoring Guide: Delegation](skill-authoring-guide-delegation.md) — Best practices for delegated skills

---

**Questions or feedback?** See `.claude/README.md` § Skill Delegation Architecture.
