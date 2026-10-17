# Patent Drawer: cost per run

*Measured on WO 2020/243027 (CYP46A1, 96 compounds), 2026-10-17. Prices as of 2026-10-06.*

## What was measured

Code does the bulk work for free: reading the PDF, names → structures, database and formula checks, writing cards, deck and Excel. Tokens are only spent by agents.

| Agent group | Agents | Work per agent | Tokens reported per agent |
|---|---|---|---|
| Scope (read activity tables) | 2 | 13 pages | ~104k |
| Structure check (vs drawing) | 5 | 16–20 compounds | 100–114k |
| MW check (formula/MS mismatches) | 1 | 3 compounds | ~94k |
| Cross-check (20 % sample + flagged) | 2 | 8 and 20 compounds | 117k, 145k |
| **Total** | **10** | | **~1.09M** |

Main reading: **every agent costs about 90k tokens just to start** (instructions, tools, reading its task). Each extra item adds only about 1–3k. So cost depends mostly on **how many agents** run, not on how many compounds each one handles.

## Prices (Claude API, per million tokens)

| Model | Used for | New input | Cache write | Cache read | Output |
|---|---|---|---|---|---|
| Sonnet 5.5 | all subagents | $2.00 | $2.50 | $0.20 | $10.00 |
| Opus 5.5 | main agent (orchestrator) | $4.00 | $5.00 | $0.20 | $20.00 |

Agents re-read their context on every step. Most of that is cached, which is cheap.
**Estimated cost per subagent: $0.50–1.00** (about $0.25 cache writes + $0.25 cache reads + $0.05–0.10 output, over ~25 steps).
**Main agent: $1–3** for ~100 compounds. It grows slowly with the number of batches.

## General formula

For **N** selected compounds:

| Agent group | Number of agents |
|---|---|
| Scope | ceil(P / 13), where P = activity-table pages (≈ N / 4 here) |
| Structure check | ceil(N / 20) in thorough mode; ceil(F / 20) in lean mode |
| MW check | ceil(M / 20), where M = formula/MS mismatches (≈ 3 % of N, often 0–1 agents) |
| Cross-check | ceil((F + 0.2 × (N − F)) / 20), where F = flagged (≈ 12 % of N here) |

**Cost ≈ (number of subagents × $0.50–1.00) + main agent $1–3 (more for big runs).**

## Estimates by patent size (thorough mode)

| Compounds | Subagents | Cost (API prices) | Per compound |
|---|---|---|---|
| 25 | ~5 | $4–7 | ~20–30¢ |
| **96 (measured)** | **10** | **$6–13** | **~6–13¢** |
| 300 | ~27 | $16–32 | ~5–11¢ |
| 1,000 | ~87 | $50–100 | ~5–10¢ |

**Lean mode** (only code-flagged compounds go to the structure checkers) cuts the structure-check agents to about 1 per 100 compounds. 96 compounds would drop to about 6 agents, **$4–8**. But lean mode would have **missed** the A22 and R/S name errors on CYP46A1, because those names were still real compounds. Use thorough mode unless cost really matters.

## On a subscription (Pro / Max)

There is no per-token bill. A run uses part of the plan's usage limits. The whole build-and-test session (two full runs plus development) used about 10 % of a Pro weekly limit, so one run of ~100 compounds is only a few percent. A 1,000-compound patent should be split across days: the skill can stop and resume at any batch.

## Caveats

- Token numbers are as reported per agent by the app. The split between input and output was not available, so dollar figures are ranges.
- The main agent's share was not measured separately, because it ran inside a longer development conversation.
- For an exact figure, run once with an API key and read the usage in the Console.
- How many compounds get flagged (F) and how many formulas mismatch (M) depends on the patent's quality. Badly scanned patents mean more checks.
