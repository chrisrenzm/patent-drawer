You learn how this patent writes things, so later steps do not miss unusual formats.

Run folder: {RUN}
Patent text: {TEXT}  (if empty, use the tools below)
Tools: {PY} "{SKILL}/scripts/tool.py" <command> ...
  text "{RUN}" A22          patent text around each mention of A22
  page "{RUN}" 85           render a page to RUN/pages/p85.png (then open it to look)

Read {RUN}/conventions.md (a code count of formats), then the general-methods section and the first ~10 examples.
Look at the examples listed under "Rare" too. Do not read the whole patent.

Append to {RUN}/conventions.md a section "## Notes (reader)" with short bullets:
- How masses are reported (adduct forms, "calcd for" formula form, rare forms and which examples use them).
- Stereo conventions and what they mean for drawing (e.g. "or1" = one enantiomer, absolute unknown; "rac-" = racemate; R* = relative).
- Naming quirks (label style, name typos, salts, names that differ from the drawing).
- Anything else that would trip the name-to-structure or mass checks.

Never write a SMILES. Do not edit any other file. Reply with one line: the 2-3 most important points.
