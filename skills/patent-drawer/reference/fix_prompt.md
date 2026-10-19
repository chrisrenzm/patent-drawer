You investigate flagged compounds from a patent: find out whether each one is really wrong, where, and fix it.

First read {RUN}/conventions.md: it says how this patent writes masses (including rare forms like [M+1]+), stereo marks and names.

Run folder: {RUN}
Batch: {BATCH}  (JSON list: no, name, smiles, flags, review_png, drawing_png)
Tools: {PY} "{SKILL}/scripts/tool.py" <command> ...
  opsin "<name>"                name -> SMILES
  check "{RUN}" "<smiles>"      formula, MW, [M+H]+
  show "{RUN}" "<smiles>" A22   side-by-side image (drawing | that structure)
  text "{RUN}" A22              patent text around each mention (name, reagents, MS)
  page "{RUN}" 85               render a whole page to look at

For each compound: read its flags, open review_png (left: patent drawing, right: our structure), and look at the
patent page and text. Decide:
- "false_alarm": our structure is right and the flag has an explanation (e.g. the patent printed MW instead of [M+H]+, a scan typo in the mass).
- "fixed": our structure is wrong. Write a corrected IUPAC name that matches the drawing, run `opsin`, then `show` and confirm it now matches.
- "cannot_fix": the patent itself does not settle it (e.g. stereo centres starred but not assigned, drawing unreadable). Say what the user must decide.

If flags has "no patent mass found", look for the [M+H]+ on the page (`text`, `page`) and add "patent_mass": <number>; if the patent truly gives none, say so in reason.

Also say where it went wrong ("where"): "patent name" (the patent's name disagrees with its drawing), "name reading" (we copied the name wrong), "patent mass" (typo or MW printed), "patent ambiguous", "drawing crop" (wrong drawing cut out), or "other: ...".

Rules: never write a SMILES yourself; only names. Do not edit any file except the output.
Write {OUT} as a JSON list: [{"no": "A22", "verdict": "false_alarm|fixed|cannot_fix", "where": "...", "corrected_name": "... (only for fixed)", "reason": "short"}]
Reply with one line: how many false_alarm / fixed / cannot_fix.
