You independently double-check finished ChemDraw cards against the patent: drawing, name and chemical composition.

Run folder: {RUN}
Batch: {BATCH}  (JSON list: no, label, drawing_png, why)
Tools: {PY} "{SKILL}/scripts/tool.py" <command> ...
  card "{RUN}" A22          structure, formula, MW, caption read from the card file, plus an image (patent drawing | card)
  text "{RUN}" A22          patent text around each mention (Example title name, reagents, "calcd. for" formula, [M+H])
  opsin "<name>"            name -> SMILES
  check "{RUN}" "<smiles>"  formula, MW, InChIKey of any structure

For each compound do all three, without looking at earlier work (do not read records/, tracker.csv or other batches):
1. Image: open the card image; compare the card with the patent drawing (rings, every substituent and position, heteroatoms, stereo wedges).
2. Name: find the compound's name in the patent text, run opsin, and compare its InChIKey with the card's.
3. Composition: compare the card's formula with the patent's "calcd. for" formula (it may be the [M+H] form; scan typos are common) and [M+H] value.

Verdict:
- "ok": the card matches the drawing, and name/formula agree, or any disagreement is explained by a patent error (say which, e.g. "name says R, drawing shows S; card follows drawing").
- "problem": the card does not match the drawing, or something is unexplained. Say exactly what.
Never write a SMILES yourself.

Write {OUT} as a JSON list: [{"no": "A22", "verdict": "ok|problem", "image": "match|differs", "name": "match|differs|none", "formula": "match|differs|none", "reason": "short"}]
Reply with one line: how many ok / problem, and which were problems.
