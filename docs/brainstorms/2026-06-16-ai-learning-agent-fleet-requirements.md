---
date: 2026-06-16
topic: ai-learning-agent-fleet
---

# AI Learning Agent Fleet — Requirements

## Summary

A staged fleet of five agents that compounds the user's AI literacy daily and doubles as interview proof of hands-on, AI-fluent product judgment. The agents share a single memory file (the Knowledge Ledger) so scaffolding gets personalized over time. All run on Claude Code with a local scheduler at negligible cost. Agents ship and demo individually, in build order: Decoder → Scout → Drill → Showcase → Conductor.

## Problem Frame

The user is a non-technical PM trying to climb the AI-literacy ladder (comprehension → credible conversation → defensible POV → building) but stalls at the bottom rung. Two distinct failures keep recurring:

- **Discovery gap** — no sense of what to read or in what order, so learning never starts.
- **Comprehension tax** — when reading does happen, missing prerequisite context triggers a 10-tab Google spiral on jargon and technical terms; the article gets abandoned half-understood.

Generic intent ("read more about AI") slips because nothing makes the next step concrete, calibrated to the user's actual level, or self-reinforcing. The cost is a literacy gap that blocks both daily work and credibility in PM interviews where AI fluency is now table stakes.

## Key Decisions

- **The Knowledge Ledger is the spine, not any single agent.** A shared memory of what the user already understands is what makes the system compound and is itself the strongest interview artifact (a memory + personalization + eval system). Anyone can prompt "explain this article"; almost no one builds the layer that personalizes it and proves growth.
- **Staged fleet, fixed build order.** Decoder first (relieves real pain day one, near-zero build), then Scout (daily habit), then Drill (retention), then Showcase (interview/ATS proof), then Conductor (orchestration). Each ships value before the next exists.
- **Learning exhaust doubles as portfolio + ATS evidence.** The persona being optimized for is ATS keyword screens plus hiring PMs/CXOs, so Showcase converts learning into shareable artifacts and a claimable-skills map rather than keeping learning private.
- **Claude Code + local scheduling is the substrate.** Near-zero cost, fully under the user's control; "I architected and run a multi-agent system on my own machine" is the headline interview line.
- **Destination is the whole ladder, not one rung.** Daily compounding starts at comprehension; the interview headline lands near building. The system is designed to walk the user up the rungs over ~90 days.

## Actors

- A1. **Learner** — the user; non-technical PM. Consumes scaffolded content, answers quizzes, reviews artifacts before they go out.
- A2. **The agents** — Decoder, Scout, Drill, Showcase, Conductor.
- A3. **Knowledge Ledger** — shared state / source of truth all agents read and write.
- A4. **Scheduler** — OS-level trigger that runs agents unattended (Windows Task Scheduler on this machine).
- A5. **External sources** — articles, newsletters, and feeds the Scout pulls from.

## Requirements

**Knowledge Ledger (foundation)**

- R1. A single shared state file records concepts the user has encountered, a comprehension level per concept, recurring gaps, and the user's target-role JD keywords.
- R2. Every agent reads the Ledger before acting and writes updates after acting.
- R3. Scaffolding depth is calibrated from the Ledger — concepts marked known are not re-explained.

**Decoder (ambient reading copilot)**

- R4. Accepts a URL or pasted text and returns missing prerequisites, an inline glossary of jargon, an ELI5 explanation, a "why it matters for a PM" framing, and 3 recall questions.
- R5. Calibrates that output to the user's current level using the Ledger.
- R6. Logs the concepts it covered and any flagged gaps back to the Ledger.

**Scout (morning digest)**

- R7. Runs on a daily schedule with no manual trigger.
- R8. Pulls from a user-defined source set and filters items to the user's current rung and target role.
- R9. Pre-scaffolds the top one to two items and delivers a brief to the chosen surface.
- R10. Records delivered items and a streak signal to the Ledger.

**Drill (recall tutor)**

- R11. Selects concepts due for review from the Ledger on a spaced-repetition cadence.
- R12. Quizzes the user, adapts difficulty to responses, and re-teaches missed concepts.
- R13. Updates per-concept comprehension level in the Ledger from quiz results.

**Showcase (learning exhaust → proof)**

- R14. Generates shareable artifacts from Ledger activity: a weekly "what I learned in AI" post draft and at least one teardown or explainer.
- R15. Maintains an ATS keyword map of AI skills the user can credibly claim, against the user's target job descriptions.
- R16. Flags gaps between target-JD keywords and demonstrated knowledge as learning priorities fed back to Scout and Drill.
- R17. Never auto-publishes; the user reviews and edits every artifact before it goes out.

**Conductor (orchestrator)**

- R18. A single scheduled run fires the daily sequence: Scout → Ledger update → Drill scheduling → Showcase drafting.
- R19. Produces a run log of what each agent did, usable both as a status surface and as an interview artifact.
- R20. Degrades gracefully — a failure in one agent does not block the others.

**Cross-cutting**

- R21. Each agent is independently runnable and demoable before the Conductor exists.
- R22. The system runs at negligible cost; demos require no paid infrastructure.

## Key Flows

- F1. Ambient decode
  - **Trigger:** Learner pastes a URL or text into the Decoder.
  - **Actors:** A1, A2 (Decoder), A3
  - **Steps:** Decoder reads the Ledger for the learner's level; produces prerequisites, glossary, ELI5, PM framing, recall questions; writes covered concepts and gaps back to the Ledger.
  - **Covered by:** R4, R5, R6

- F2. Daily orchestrated run
  - **Trigger:** Scheduler fires the Conductor once per day.
  - **Actors:** A4, A2 (Conductor, Scout, Drill, Showcase), A3, A5
  - **Steps:** Conductor runs Scout (pull → filter → scaffold → deliver); Scout logs to the Ledger; Conductor schedules any due Drill review; Showcase drafts pending artifacts; Conductor writes a run log. A failing agent is skipped, not fatal.
  - **Covered by:** R7, R8, R9, R10, R18, R19, R20

## Dependencies / Assumptions

**Knowledge Ledger**
- Needs a durable local file format and location (decided in planning).
- Assumes a single user; no multi-user concurrency.

**Decoder**
- Needs to fetch URL content (web fetch) or accept pasted text as a fallback.
- Assumes article content is text-extractable; paywalled or JS-heavy pages rely on the paste fallback.

**Scout**
- Needs a user-curated source list (RSS / newsletter / feed URLs).
- Needs a scheduling mechanism — Windows Task Scheduler on this machine (win32), not cron.
- Needs a delivery surface (local markdown file, email, or messaging app) — undecided.
- Reuses Decoder's scaffolding capability; depends on the Decoder existing.

**Drill**
- Depends on the Ledger holding accumulated concepts, so Decoder and/or Scout must have run first.
- Needs a spaced-repetition cadence policy (decided in planning).

**Showcase**
- Needs the user's target job descriptions as input.
- Depends on Ledger activity history.
- Assumes user-in-the-loop review before any artifact is shared.

**Conductor**
- Depends on all other agents existing; built last.
- Shares the scheduling mechanism with Scout.

**Cross-cutting**
- Requires Claude Code installed with model access (already true).
- Assumes the win32 environment (Task Scheduler for scheduling).
- Negligible cost assumes usage stays within the user's existing Claude allowance.

## Scope Boundaries

**Deferred for later**
- Conductor orchestration until at least two agents exist.
- Multi-surface delivery for Scout (start with one surface).
- Any auto-publishing of Showcase artifacts.

**Outside this product's identity**
- Not a full-stack web app — no front end to build or host.
- Not a generic chatbot or a learning product for other people.
- Not the portfolio app clones from the source research; those are built separately via Lovable and are out of scope here.

## Success Criteria

- Daily: the learner stops tab-spiraling on scaffolded items — the Decoder output is enough to grasp them unaided.
- Compounding: the Ledger visibly grows and previously-learned concepts are not re-explained.
- Interview: each agent demos in under two minutes, the fleet plus Ledger reads as one coherent system, and the ATS map shows concrete claimable skills.
- Cost stays negligible.

## Outstanding Questions

**Deferred to Planning**
- Knowledge Ledger file format and location.
- Scout's delivery surface (local file vs. email vs. messaging app).
- Initial source list contents.
- Spaced-repetition cadence parameters for Drill.
- How target job descriptions are supplied and refreshed for Showcase.

## Sources / Research

- `compass_artifact_wf-ab36e404-7c22-4f9b-8439-c7fb74a7feaa_text_markdown.md` — the user's research doc on portfolio app references; this brainstorm draws its agentic-UI transparency patterns (Perplexity citations, Manus activity panel, Devin inline steps) as design inspiration for how the fleet surfaces its work.
