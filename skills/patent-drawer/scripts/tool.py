"""Small tools for checker subagents. Every structure must come from here, never from the model.

  tool.py opsin "<name>"          name -> SMILES (null if the name does not parse)
  tool.py check RUN "<smiles>"    formula, MW, [M+H]+, InChIKey, in this patent's database list?
  tool.py text  RUN A22           patent text around each mention of A22
  tool.py page  RUN 85            render a PDF page to RUN/pages/p85.png (then open it to look)
  tool.py show  RUN "<smiles>" A22  new side-by-side image: drawing | this structure
  tool.py card  RUN A22           structure, formula, MW and caption read from the finished card + image drawing | card
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import patent as P

cmd = sys.argv[1]
if cmd == "opsin":
    out = P.opsin(sys.argv[2])
elif cmd == "check":
    run, s = sys.argv[2], sys.argv[3]
    out = P.mol_info(s)
    if out:
        out["in_patent_db"] = out["inchikey"] in P.db_keys(os.path.join(run, "patent_db.csv"))
elif cmd == "text":
    out = P.mentions(os.path.join(sys.argv[2], "patent.pdf"), sys.argv[3])
elif cmd == "page":
    run, pn = sys.argv[2], int(sys.argv[3])
    os.makedirs(os.path.join(run, "pages"), exist_ok=True)
    out = P.render_page(os.path.join(run, "patent.pdf"), pn, os.path.join(run, "pages", f"p{pn}.png"))
elif cmd == "show":
    import pd
    run, s, no = sys.argv[2], sys.argv[3], sys.argv[4]
    out = pd._review_image(run, no, s, out_name=no + "_alt")
elif cmd == "card":
    import pd
    run, no = sys.argv[2], sys.argv[3]
    out = pd.card_info(run, no)
    if out.get("smiles"):
        out["image"] = pd._review_image(run, no, out["smiles"], out_name=no + "_card")
else:
    raise SystemExit(__doc__)
print(json.dumps(out, indent=1))
