---
name: patent-drawer
description: Turn compounds in a chemistry patent PDF into ChemDraw cards (.cdxml), a PowerPoint deck of double-click-editable ChemDraw objects, an Excel tracker and a validation report. Use when the user asks to draw, extract or tabulate structures from a patent (e.g. "draw the A-rated compounds from WO2020243027").
---

# Patent Drawer

You move the user's job from *drawing* structures to *reviewing* them. Code does the bulk work; you and small subagents only do what needs judgment. Stop at each GATE and wait for the user.

**Golden rule: never write a SMILES or draw a structure yourself.** Structures come only from tools: a patent name through OPSIN (`tool.py opsin`). When a drawing disagrees with its name, write a *corrected name* and convert it with the tool.

Setup (first run): `bash scripts/setup_env.sh` creates `.venv` next to the skill. Below, `PD` means `<skill>/.venv/bin/python <skill>/scripts/pd.py`, `TOOL` means the same with `tool.py`. Network needed: `www.ebi.ac.uk` (OPSIN), `pubchem.ncbi.nlm.nih.gov`.

## Phase 0: Intake
Ask for anything missing: patent PDF, patent number (PubChem form, e.g. `WO-2020243027-A1`), target name, compound label prefix (e.g. `A` for A6), output folder (the RUN folder, default `./patent-drawer-runs/<TARGET>_<WOxxxx>`), the user's own deck template (optional), author name.
Run `PD init RUN --pdf ... --patent-id ... --prefix A --target ...`.

## Phase 1: Which compounds? → GATE 1
1. `PD tables RUN` lists the data tables and the picture-only pages.
2. Find the structure table (number | drawing) and the activity table(s). `PD crops RUN --pages a-b` cuts the structure table into `crops/<no>.png`. Check that it found the expected count.
3. Picture-only activity tables: `PD ocr RUN --pages a-b` gives a rough reading. OCR misses letters, so give the pages to **scope subagents** (≤ 25 pages each, prompt: `reference/scope_prompt.md`). They look at the page images and return every row. Never guess a value.
4. Restate the user's request as an explicit selection rule (e.g. "Table 3 activity A + every compound in Table 4"). Write `RUN/tracker.csv`, one row per candidate, columns:
   `order, patent_no, source_tables, pages, activity_raw, activity_display, selected, reason`, plus any extra data columns (e.g. `clint, papp, er`).
5. Show counts (selected, skipped and why, overlaps) and the list. **Wait for the user to confirm.**

## Phase 2: What goes on each card? → GATE 2
Start from `presets/acs1996_card.json`, fill it in and save it as `RUN/spec.json`: `label_pattern` (e.g. `CYP46A1_WO3027_{patent_no}`, last 4 digits of the WO number; point out likely typos), `caption_lines`, `extra_lines` (shown only when their fields are filled), `title_lines`, `deck_name`, optional `template`.
CLogP: ChemDraw's CLogP cannot be reproduced by free tools, so the default leaves it blank for the user to fill in ChemDraw. Say so.
**Wait for the user to confirm.**

## Phase 3: Structures
1. `PD resolve RUN` (default `--mode thorough`: every compound is checked against its drawing; `lean` checks only code-flagged ones and is cheaper but misses errors where the name is wrong but still a real compound, e.g. a copied substituent position). It writes `records/`, review images and `batches/batch_K.json` (≤ 20 each).
2. Tell the user the number of batches. Run one **checker subagent** per batch (at most 3 at a time, smallest capable model), prompt `reference/checker_prompt.md` with RUN and the batch file filled in.
3. `PD apply RUN`.

## Phase 4: Pilot → GATE 3
`PD draw RUN --only <one compound, ideally with stereo>`. Show the user its review image and the card file. **Wait for "go"**, or fix the spec and redo.

## Phase 5: Draw, double-check, validate, assemble → GATE 4
1. `PD draw RUN`.
2. **Double-check** (separate agent groups that did not do the structure check): `PD doublecheck RUN` (default `--sample 0.2`).
   - Stage A, code, all cards: the card's formula and [M+H]⁺ against the patent's own "calcd. for" formula and MS. Mismatches → `batches/mw_K.json`. Run the **MW group** (prompt `reference/mw_prompt.md`).
   - Stage B: every flagged compound plus a random 20 % of trusted ones → `batches/xc_K.json`. Run the **cross-check group** (prompt `reference/crosscheck_prompt.md`), which independently compares each card with its drawing, the patent name (via OPSIN) and the formula.
   - `PD dcapply RUN`. Any "problem" flags the compound for the user. If the cross-check finds a problem in a random-sample compound, tell the user: it suggests errors elsewhere, so offer a full check of the remaining compounds.
3. `PD validate RUN` (report in `validation/report.md`).
4. `PD outputs RUN` builds `out/<deck>.pptx`, `out/<deck>.xlsx`, `out/contact_sheet.pdf` (flagged first).
5. Hand back: deck, Excel, `cdx/`, report, contact sheet, and a short list of what needs the user's eyes (every flagged compound, with page and reason).
6. If the user fixes cards in ChemDraw, re-run `PD validate` and `PD outputs`.

All state is in RUN (`tracker.csv` is readable by humans). You can stop at any step and resume later; `PD status RUN` shows where things stand.

## Without subagents
Do the scope and checker batches yourself, one batch at a time, in the same way.
