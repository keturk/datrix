---
description: Runs a premortem on any plan, launch, product, hire, strategy, or decision. Assumes it already failed 6 months later and works backward to find every reason why. Produces a revised plan with blind spots exposed.
model: claude-sonnet-4-6
delegation-strategy:
  phases:
    - name: "context_gathering"
      model: "sonnet"
      parallelizable: false
      description: "Gather minimum context: what, who, success criteria"
    - name: "raw_premortem"
      model: "sonnet"
      parallelizable: false
      description: "Generate exhaustive list of genuine failure reasons"
    - name: "deep_analysis"
      model: "sonnet"
      parallelizable: true
      max_parallel: 9
      description: "Analyze each failure reason in depth with failure story, assumption, and warning signs"
    - name: "synthesis"
      model: "sonnet"
      parallelizable: false
      description: "Synthesize findings into actionable report with revised plan"
    - name: "report_generation"
      model: "haiku"
      parallelizable: false
      description: "Generate visual HTML report and markdown transcript"
---

# Premortem

Runs a premortem on plans, launches, products, hires, strategies, or decisions. Uses "prospective hindsight" to identify failure modes before they happen by assuming the plan already failed and working backward to explain why.

## The Psychology

A premortem is the opposite of a postmortem. Instead of figuring out what went wrong after something fails, you imagine it already failed and figure out why before you start.

The method comes from psychologist Gary Klein (published in Harvard Business Review). Daniel Kahneman called it his single most valuable technique for decision-making. Google, Goldman Sachs, and Procter & Gamble use it before big decisions.

**Key insight:** When you ask "what could go wrong?" people give cautious, hedged answers. When you say "this already failed, tell me why," the brain shifts into narrative mode and generates far more specific, creative, honest reasons. Wharton and Cornell researchers called this "prospective hindsight" and found it significantly increases ability to identify causes of future outcomes.

**Why this matters for AI-assisted decisions:** Claude tends toward polite, optimistic answers. If you ask "is this a good plan?" it will find reasons to say yes. The premortem breaks this pattern by forcing the frame to "this is dead, explain how it died." Claude stops searching for reasons your plan will work and starts explaining how it fell apart.

---

## When to Use

**MANDATORY TRIGGERS** (always run premortem):
- User says: "premortem this", "premortem my", "run a premortem"
- User says: "what could kill this", "stress test this plan", "what am I missing here", "find the blind spots"

**STRONG TRIGGERS** (recommend premortem):
- "what could go wrong", "am I missing something", "poke holes in this", "where will this break", "devil's advocate"

**DO NOT trigger on:**
- Simple feedback requests (editing, creative feedback)
- Factual questions with one correct answer
- LLM Council requests (different mechanism - Council gives multiple perspectives on a decision right now; premortem sends Claude to the future where the decision already failed)

**Good targets:**
- A product or feature you're about to build
- A launch plan with money or reputation on the line
- A pricing or business model change
- A hire you're about to make
- A strategy or positioning pivot
- A partnership or deal you're evaluating
- Any commitment where the cost of being wrong is high

**Bad targets:**
- Vague ideas with no concrete plan yet (help them plan first, then premortem)
- Questions with one correct answer (just answer them)
- Creative feedback requests on a draft (that's editing, not a premortem)
- Decisions already made and irreversible (premortem only useful when you can still change course)

---

## How to Invoke

```
/premortem

PLAN: I'm about to launch a $297 live workshop on how to use Claude Code for marketing teams. 50 seats. Targeting marketing directors at 10-50 person companies.
```

Or simply:
```
/premortem

[paste plan details or reference files]
```

The skill will gather additional context if needed before running the premortem.

---

## Context Gathering (Minimum Necessary)

A premortem is only as good as the context it runs on. Vague information produces vague failure scenarios that don't help anyone. Before running the premortem, you need to hit a minimum context threshold.

### Step 1: Search for Existing Context

Before asking the user anything, search for context that's already available:

**A. The current conversation.** The user may have been discussing a plan, launch, product, or decision earlier in this session. Read the conversation and extract what's relevant.

**B. The workspace.** Quickly scan for files that might contain relevant context:
- `CLAUDE.md` or `claude.md` (business context, preferences, constraints)
- Any `memory/` folder (audience profiles, business details, past decisions)
- Files the user explicitly referenced or attached
- Any project files, briefs, or plans related to what's being premortemed

Use `Glob` and quick `Read` calls. Don't spend more than 30 seconds on this. You're looking for the key files that will anchor the failure scenarios in reality.

### Step 2: Assess Context Sufficiency

After scanning, check if you have enough to run a useful premortem. You need three things:

1. **What is it?** — A clear understanding of what's being premortemed (a product, a launch, a hire, a pricing change, a strategy). You should be able to describe it to the user in one sentence.

2. **Who is it for / who does it affect?** — The audience, the customer, the team, the stakeholders. Failure scenarios depend heavily on who's involved.

3. **What does success look like?** — What outcome is the user hoping for? Failure is defined by inverting success. If you don't know what success means, you can't define what failure means.

### Step 3: Fill Gaps Conversationally

**If you have all three** → proceed to the premortem immediately. Don't ask unnecessary questions.

**If you're missing one or more** → ask first for the most important missing piece. One question at a time. Reassess after each answer whether you now have enough. Keep asking until you hit the threshold, but never ask more than necessary.

Examples of focused context questions:
- "What exactly are you about to launch/build/decide?" (if you don't know what it is)
- "Who is this for?" (if you know the plan but not the audience)
- "What would a win look like for this?" (if you know the plan and audience but not success criteria)

**Goal:** Hit the minimum as quickly as possible without making the user feel like they're filling out a form. Conversational, not interrogative. If you can infer an answer from context, do so instead of asking.

---

## Phase 1: Establish the Frame

After gathering enough context, establish the premortem frame explicitly. Something like:

> "Alright, I have enough context. Let's run the premortem. The premise is: it's 6 months later. [The plan/launch/decision] has failed. It's done. We're looking back trying to understand what went wrong."

**This framing matters.** It shifts the mode from "evaluate this plan" (which triggers polite answers) to "explain why this died" (which triggers honest, specific failure identification).

---

## Phase 2: Generate Failure Reasons (Raw Premortem)

Run the raw premortem as a single, complete analysis. No prefabricated categories, no lenses, no constraints. Just the basic Klein method:

> "This plan has failed 6 months out. Generate every genuine reason why it might have died. Be exhaustive. Be specific. Ground each reason in actual plan details. Don't pad with weak reasons and don't stop early if there's more."

The output should be a complete list of failure reasons, each expressed in 1-2 sentences. Be honest and exhaustive. Some plans may have 4 genuine failure modes. Others may have 9. The number should be whatever is real for this specific plan.

**Each failure reason should be:**
- Specific to this plan (not generic advice that applies to anything)
- Grounded in actual details the user provided
- A genuine threat (not a minor inconvenience or extremely unlikely edge case)

**Examples of good failure reasons:**
- "Marketing directors at companies this size need approval to spend $297 on professional development, adding friction you haven't accounted for"
- "The audience who actually buys might be solopreneurs, not team directors, creating a mismatch between content and attendees"
- "Building a workshop for marketing teams requires demo environments with realistic marketing data and multi-user setups, which takes 5 weeks of prep, not the 2 you've budgeted"

**Examples of bad failure reasons (too generic):**
- "The market might not be ready"
- "Competitors could launch something similar"
- "Technical challenges could arise"

---

## Phase 3: Deep Analysis Agents (One Per Failure Reason, All in Parallel)

Take each failure reason from Phase 2 and launch a sub-agent per reason, **all in parallel**. Each agent takes its assigned failure reason and analyzes it in depth independently.

**Sub-agent prompt template:**

```
You are a researcher in a premortem analysis. You've been assigned a specific failure reason to analyze in depth.

The plan:
---
[full context: what it is, who it's for, what success looks like, plus relevant context from workspace]
---

PREMORTEM FRAME: It's 6 months later. This plan has failed.

YOUR ASSIGNED FAILURE REASON: [the specific failure reason from Phase 2]

Your job is to dig into this failure. Write the story of how it actually unfolded. Be specific. Use details from the plan. Make it feel real, like a case study of something that actually happened.

Your output should include:

1. THE FAILURE STORY: A 2-3 paragraph narrative of how this specific failure unfolded. Use details from the plan. Name specific moments where things went wrong and why.

2. THE UNDERLYING ASSUMPTION: The one thing the user was taking for granted that made this failure possible. Express it in one sentence.

3. EARLY WARNING SIGNS: 1-2 concrete, observable signals the user could watch for that would indicate this failure mode is starting to unfold. These should be things you can actually see or measure, not vague feelings.

Keep the total response under 300 words. Be direct. Don't hedge it. Don't soften it.
```

**CRITICAL:** Always launch all agents in parallel. Sequential launching wastes time and allows earlier responses to bias later ones.

---

## Phase 4: Synthesis

After all agents complete, read each deep analysis and produce the synthesis:

### PREMORTEM REPORT

**1. Most Likely Failure** — What failure scenario is most likely given what you know about the plan? Why? This is the one the user should focus on first.

**2. Most Dangerous Failure** — What failure scenario would cause the most damage if it happened, even if it's less likely? This is the one worth insuring against.

**3. Hidden Assumption** — Across all the failure analyses, what's the single most important assumption the user is making that they probably haven't questioned? This is where the real value of the premortem often lives: the thing that's so obvious to the user they forgot it was an assumption.

**4. Revised Plan** — Based on the failure scenarios, what specific changes would make the plan more resilient? Be concrete. Don't say "consider your pricing." Say "test pricing at $X with 20 people before committing publicly." Each revision should map directly to a specific failure scenario.

**5. Pre-Launch Checklist** — 3-5 specific things the user should verify, test, or implement before executing. Each should prevent or detect one of the identified failure modes.

---

## Phase 5: Generate Reports

Generate two files:

### A. Visual HTML Report

**Filename:** `premortem-report-[timestamp].html`

A single self-contained HTML file with inline CSS. Design principles:
- Dark background (#0a0e1a or similar), clean typography, easy to scan
- **Synthesis section first** (most likely failure, most dangerous failure, hidden assumption, revised plan, checklist) — displayed prominently at the top since it's what most people will read first
- **Failure analysis cards** below — one visual card per failure reason showing:
  - Failure reason as header
  - Failure story
  - Underlying assumption
  - Early warning signs
  - Use distinct accent colors for each card to make them visually scannable
- **Visual severity/likelihood indicator** for each failure mode
- **Agent execution summary** — show the number of agents that ran and their findings as a grid or card layout
- **Footer** with timestamp and what was premortemed

**After generating, open the HTML file.**

### B. Markdown Transcript

**Filename:** `premortem-transcript-[timestamp].md`

Save the complete premortem transcript including:
- The context that was gathered (what, who, success criteria)
- The raw premortem failure reasons
- All agent deep analyses
- The complete synthesis

### C. Chat Summary

Provide a concise summary in the chat: the most likely failure, the hidden assumption, and the single most important plan revision. **Three sentences max.** The report has all the details.

---

## Output Format

Each premortem session produces:

```
premortem-report-[timestamp].html    # visual report for scanning
premortem-transcript-[timestamp].md  # complete transcript for reference
```

The user sees the HTML report first. The transcript is available if they want to dig into the reasoning behind each failure scenario.

---

## Example: Product Launch Premortem

**User:** "premortem this: I'm about to launch a $297 live workshop on how to use Claude Cowork for marketing teams. 50 seats. Targeting marketing directors at 10-50 person companies."

**Raw premortem identifies 6 failure reasons:**
1. Marketing directors at companies this size need approval to spend $297 on professional development, adding friction you haven't accounted for
2. "Claude Cowork for marketing" is a tool-first pitch in a market where most directors are still deciding whether AI is relevant to them
3. The audience who actually buys might be solopreneurs, not team directors, creating a mismatch between content and attendees
4. Building a workshop for marketing teams requires demo environments with realistic marketing data and multi-user setups, which takes 5 weeks of prep, not the 2 you've budgeted
5. If 60% of attendees are solopreneurs, your reviews and case studies won't resonate with the marketing director audience you need for future cohorts
6. At $297 with 50 seats, max revenue is $14,850, which may not justify prep time vs. other revenue opportunities

**6 agents dig into each reason independently, producing failure stories, underlying assumptions, and early warning signs.**

**Synthesis:**
- **Most likely failure:** Audience mismatch — you're targeting people who need approval to spend $297, adding friction you haven't accounted for
- **Most dangerous failure:** Attracting solopreneurs instead of team directors means your case studies and testimonials won't resonate with the actual target buyer for future cohorts, compounding the problem over time
- **Hidden assumption:** You assume "marketing directors at 10-50 person companies" is a reachable audience, but these people don't self-identify that way and aren't in the same places
- **Revised plan:** Run a $47 pilot session for 20 people first. Use that to identify whether your actual buyers are team directors or solopreneurs, and build the full workshop for whoever actually shows up

---

## Important Notes

- **Always establish the frame explicitly.** "This has already failed" is the psychological mechanism that makes this work. Without it, the analysis reverts to polite risk assessment instead of honest failure identification.

- **Always launch all failure agents in parallel.** Sequential launching wastes time and allows earlier responses to bias later ones.

- **Be exhaustive but don't pad.** Find every genuine failure reason. Don't stop at 3 if there are 7. But don't force 7 if there are only 3. The number should be whatever is real for this specific plan.

- **The synthesis is the product.** Most users will read the synthesis and skim the individual failure cards. Make the synthesis specific and actionable.

- **Don't soften.** The point of a premortem is to tell the user things they don't want to hear before reality does. If a plan has serious problems, say it directly.

- **The revised plan should be concrete.** Don't say "consider testing your pricing." Say "run a $47 pilot with 20 people before committing to the full $297 workshop." Each revision should be something the user can actually do this week.

- **Respect the minimum context threshold.** Running a premortem with insufficient context produces generic failures that waste the user's time. Better to ask one more question than produce a bad premortem.

- **This is not LLM Council.** Council gives multiple perspectives on a decision right now. Premortem sends Claude to the future where the decision already failed and works backward to explain why. Different psychological mechanism, different output. If the user seems to want multiple perspectives rather than failure analysis, suggest council instead.

---

## Anti-Patterns

- **NO skipping the frame.** Always establish "this already failed" explicitly before generating failure reasons.
- **NO sequential agent execution.** Launch all failure analysis agents in parallel.
- **NO generic failure reasons.** Every reason must be specific to this plan with actual details.
- **NO padding.** If there are 4 genuine failures, stop at 4. Don't force more.
- **NO softening.** The value is in honest, direct failure identification.
- **NO vague revisions.** "Consider your pricing" is useless. "Test $X with 20 people" is actionable.
- **NO running without sufficient context.** Get the minimum threshold (what/who/success) before starting.
- **NO skipping the HTML report.** The visual output is what makes findings scannable and actionable.
- **NO workarounds** — don't steer around issues, don't paper over them; fix the root cause or STOP and report (CLAUDE.md rule)
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
