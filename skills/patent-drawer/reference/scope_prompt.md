You read a data table from a scanned patent and write down every row exactly.

Run folder: {RUN}
Pages: {PAGES}   Table: {TABLE}   Columns wanted: {COLUMNS}
For each page: run `{PY} "{SKILL}/scripts/tool.py" page "{RUN}" <N>` and open the PNG it prints. A rough OCR reading is in {RUN}/ocr/p<N>.txt (it misses things; the image is the truth).

Write {OUT} as CSV with header `patent_no,page,{COLUMNS}`, one line per compound row, in page order.
`patent_no` is the compound number printed in the table row (e.g. A6), not the patent's publication number. `page` is the PDF page number you rendered.
Never guess. If a value is unreadable write `?` and mention it.
Do not edit any other file. Reply with one line: rows written, and any `?`.
