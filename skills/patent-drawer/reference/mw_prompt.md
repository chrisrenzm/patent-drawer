You review compounds whose finished ChemDraw card does not agree with the patent's own formula or mass-spec value.

Run folder: {RUN}
Batch: {BATCH}  (JSON list: no, label, name, card_formula, card_mw, patent_formulas, patent_ms, formula, ms)
Tools: {PY} "{SKILL}/scripts/tool.py" <command> ...
  card "{RUN}" A22          structure, formula, MW and caption read from the card file, plus an image (patent drawing | card)
  text "{RUN}" A22          patent text around each mention (look for "calcd. for ..." and "[M+H]")
  check "{RUN}" "<smiles>"  formula, MW, [M+H]+ of any structure

Patent formulas are often [M+H] or [M+Na] forms and have scan typos (i/l for 1, O/0, CI for Cl).
For each compound decide why they disagree:
- "ok": the card is right; the patent number is a scan typo, an adduct form, or a misprint copied from another compound (say which).
- "problem": the card's structure is probably wrong (e.g. the formula points to a different atom count). Say what you think is wrong.
Open the card image for every compound. Never write a SMILES yourself. Do not read records/ or other batch results.

Write {OUT} as a JSON list: [{"no": "A22", "verdict": "ok|problem", "reason": "short"}]
Reply with one line: how many ok / problem, and which were problems.
