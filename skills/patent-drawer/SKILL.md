---
name: patent-drawer
description: Turn compounds in a chemistry patent PDF into ChemDraw cards (.cdxml), a PowerPoint deck of double-click-editable ChemDraw objects, an Excel tracker and a validation report. Use when the user asks to draw, extract or tabulate structures from a patent (e.g. "draw the A-rated compounds from WO2020243027").
---

# Patent Drawer

You move the user's job from *drawing* structures to *reviewing* them. Code does the bulk work; you and small subagents only do what needs judgment.

**One check-in, then hands-off.** Stop only twice: if there is no patent PDF, and once after Phase 2 to confirm the compound list and the card labels (see "Confirm before drawing"). One exception: if a chemical convention is missing or absolutely unclear (e.g. what a stereo mark means, how the patent reports masses) and the patent and `conventions.md` cannot settle it, ask the user that one question. Do not ask about anything you can reasonably decide. For every other open point, take the default below (or the most reasonable reading of the request), write it to `RUN/decisions.md` (one line each: the question, what you chose, why), and keep going.

**Check ChemDraw first.** Before any other work, run `PD chemdraw_check` (outside the sandbox). It confirms ChemDraw is installed and can calculate CLogP; that needs ChemDraw Professional or Signals ChemDraw, since ChemDraw Prime has no CLogP. If it is not "ok", tell the user why in the message below (e.g. "ChemDraw isn't installed, so CLogP will be left blank") and continue with CLogP blank.

**Confirm before drawing.** After Phase 2, ask the user once (AskUserQuestion when available) and wait for the answer. Show, briefly:
- the selection rule and the number of compounds, with their numbers (e.g. "96 compounds: A6, A10, ... A287");
- one example card's text lines exactly as they will appear (label, MW, CLogP, activity line, any extra lines);
- the output folder;
- only if 100 or more compounds are selected: ask whether to visually double-check every compound (more thorough, more cost) or a random 20 % plus all flagged ones. Under 100, every compound is checked; do not ask.
Apply any changes the user asks for, then continue.

**Warn about ChemDraw, then step away.** In the same confirmation message, tell the user: "Near the end ChemDraw starts in the background to calculate CLogP. Its windows may appear for a minute; please don't click or close them. If macOS asks to let Terminal/Claude control ChemDraw, click Allow." After the user confirms, no more check-ins until the hand-back (except an absolutely unclear convention, as above).

**Golden rule: never write a SMILES or draw a structure yourself.** Structures come only from tools: a patent name through OPSIN (`tool.py opsin`). When a drawing disagrees with its name, write a *corrected name* and convert it with the tool.

Setup (first run): `bash scripts/setup_env.sh` creates `.venv` next to the skill. Below, `PD` means `<skill>/.venv/bin/python <skill>/scripts/pd.py` (on Windows `<skill>/.venv/Scripts/python`), `TOOL` means the same with `tool.py`. Network needed: `www.ebi.ac.uk` (OPSIN), `pubchem.ncbi.nlm.nih.gov`.

## Defaults (do not ask; labels and compounds are shown at the one check-in)
- Patent number: read it from the PDF front page (PubChem form, e.g. `WO-2020243027-A1`).
- Target: from the request, else from the patent title/claims.
- Label prefix: the patent's own numbering (e.g. `A` for A6), else none.
- RUN folder: `./patent-drawer-runs/<TARGET>_<WOxxxx>`. Final folder: `~/Downloads/<deck_name>/`.
- Activity: if the requested measure (e.g. IC50) is missing, use the patent's closest potency value (e.g. EC50, Ki) and label it with its real name.
- "Top N": exactly N by rank; note the values at the cutoff and any ties.
- Label: `<TARGET>_WO<last4>_<patent_no>`. Author: the user's name if known, else leave it out.
- Template: the user's template if given, else the default.
- Duplicates, unclear stereo, odd mass values: keep the compound and flag it.
- Every compound needs the patent's own mass: if none is found, it is flagged "no patent mass found" and never trusted until an agent finds it on the page.

## Phase 1: Which compounds?
1. `PD init RUN --pdf ... --patent-id ... --prefix A --target ...`, then `PD tables RUN` lists the data tables and the picture-only pages.
   - **Conventions first:** `PD conventions RUN` (scanned PDF: add `--text <text of the same patent, e.g. from Google Patents>`). Free: it counts how this patent writes masses, stereo marks and example titles into `RUN/conventions.md` and lists rare formats (e.g. `[M+1]+` instead of `[M+H]+`) with their example numbers. Then one **conventions subagent** (prompt `reference/conventions_prompt.md`) reads that file, the general methods, the first ~10 examples and the rare-format examples, and adds short notes. Every later agent reads `conventions.md` first.
2. Find the structure table (number | drawing) and the activity table(s). `PD crops RUN --pages a-b` cuts the structure table into `crops/<no>.png`. Check that it found the expected count.
3. Picture-only activity tables: `PD ocr RUN --pages a-b` gives a rough reading. OCR misses letters, so give the pages to **scope subagents** (≤ 25 pages each, prompt: `reference/scope_prompt.md`). They look at the page images and return every row. Never guess a value.
4. Restate the request as an explicit selection rule and add it to `decisions.md`. Write `RUN/tracker.csv`, one row per candidate, columns:
   `order, patent_no, source_tables, pages, activity_raw, activity_display, selected, reason`, plus any extra data columns (e.g. `clint, papp, er`).

## Phase 2: What goes on each card?
Start from `presets/acs1996_card.json`, fill it in and save it as `RUN/spec.json`: `label_pattern`, `caption_lines`, `extra_lines` (shown only when their fields are filled), `title_lines`, `deck_name`, optional `template`.
CLogP comes from the user's own ChemDraw (Phase 4), so it matches what they would get by hand.

## Phase 3: Structures
1. `PD resolve RUN` (default `--mode thorough`: every compound is checked against its drawing; `lean` checks only code-flagged ones). It writes `records/`, review images and `batches/batch_K.json` (≤ 20 each).
2. Run one **checker subagent** per batch (at most 3 at a time, smallest capable model), prompt `reference/checker_prompt.md` with RUN and the batch file filled in.
3. `PD apply RUN`.
4. **Fix loop** (whenever anything is flagged): `PD fixbatch RUN`, run one **fixer subagent** per batch (prompt `reference/fix_prompt.md`), then `PD fixapply RUN`. It decides whether each flag is a false alarm, a real error (fixed, with where it went wrong), or something the patent itself leaves open. Every case is logged in `RUN/mistakes.md`. Repeat once if anything new is flagged; whatever is still flagged after 2 rounds goes to the user.

## Phase 4: CLogP from ChemDraw
`PD clogp RUN` (ChemDraw Professional or Signals ChemDraw, Mac or Windows; run it outside the sandbox). For each structure it writes a file with a live ChemDraw CLogP link, ChemDraw opens, cleans and saves it (no clicks, no screen control), and the value ChemDraw wrote goes into `tracker.csv` (2 decimals). Under 1 s per compound. ChemDraw is started hidden in the background (it does not take over the screen) and quit afterwards if it was not already open; a fully invisible run is not possible without an extra macOS permission prompt.
If it fails, leave CLogP blank, say why in `decisions.md`, and continue. Re-run with `--only` for any compound fixed later.

## Phase 4b: Pilot
`PD draw RUN --only <one compound, ideally with stereo>`. Look at its review image yourself. If something is wrong, fix the spec and redo; otherwise continue.

## Phase 5: Draw, double-check, validate, assemble
1. `PD draw RUN`.
2. **Double-check** (separate agent groups that did not do the structure check): `PD doublecheck RUN` (default: every compound if fewer than 100 are selected, else flagged + a random 20 % of trusted; if the user chose a full check for 100 or more, add `--sample 1`).
   - Stage A, code, all cards: the card's formula and [M+H]⁺ against the patent's own "calcd. for" formula and MS. Mismatches → `batches/mw_K.json`. Run the **MW group** (prompt `reference/mw_prompt.md`).
   - Stage B: every compound (under 100), or every flagged compound plus a random 20 % of trusted ones (100 or more) → `batches/xc_K.json`. Run the **cross-check group** (prompt `reference/crosscheck_prompt.md`).
   - `PD dcapply RUN`. Any "problem" flags the compound. If the cross-check finds a problem in a random-sample compound, check all the remaining compounds the same way.
   - Fixed compounds (status `fixed`) stay unconfirmed until the cross-check says "ok". If anything is flagged or fixed now, run the **fix loop** again, then `PD clogp RUN --only <those>`, `PD draw RUN --only <those>` and `PD doublecheck RUN --sample 0` (checks only those), then `PD dcapply RUN`. At most 2 rounds.
3. `PD validate RUN` (report in `validation/report.md`).
4. `PD outputs RUN --export ~/Downloads/<deck_name>` builds the deck, Excel and contact sheet (flagged first), and copies them with the ChemDraw files, report, tracker, `decisions.md` and `mistakes.md` into that one folder.
5. Hand back, short, with only:
   1. **Files:** the Downloads folder path and the files in it.
   2. **Compounds flagged or changed:** each one with what was wrong and how it was fixed (from `mistakes.md`), and any still flagged (page and reason).
   Nothing else (decisions are in `decisions.md`). End with "done".
6. If the user later fixes cards in ChemDraw, re-run `PD validate` and `PD outputs --export ...`.

All state is in RUN (`tracker.csv` is readable by humans). `PD status RUN` shows where things stand.

## Without subagents
Do the scope and checker batches yourself, one batch at a time, in the same way.
