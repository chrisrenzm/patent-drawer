# What a run needs

**Where it runs:** on the user's own computer, in Claude Code (terminal or desktop app). CLogP needs the user's own ChemDraw, which only a local agent can reach. In a cloud session or on claude.ai everything else works, but CLogP is left blank.

**Software**
- Python 3.10+ (first run: `bash scripts/setup_env.sh` makes `.venv` next to the skill).
- ChemDraw Professional or Signals ChemDraw for CLogP (Prime has no CLogP). Mac tested; Windows untested.
- PowerPoint to open the deck. Double-click editing of the cards works on Windows.

**Network:** `www.ebi.ac.uk` (OPSIN, name → structure) and `pubchem.ncbi.nlm.nih.gov` (patent compound list). For a scanned PDF, also the patent's text from `patents.google.com`.

**Permissions**
- Write to the run folder (`./patent-drawer-runs/...`) and `~/Downloads/<deck_name>/`.
- Mac: the CLogP step and `chemdraw_check` run ChemDraw through AppleScript (`osascript`). In Claude Code's sandbox that is blocked, so these commands run outside the sandbox (the user approves them). The first time, macOS asks to let Terminal/Claude control ChemDraw: click **Allow** (System Settings → Privacy & Security → Automation). No Accessibility or screen-control permission is needed.
- Windows: PowerShell runs ChemDraw through its COM automation.
- Subagents (checker, fix, cross-check groups) are optional; without them the main agent does the batches itself.

**During the run:** ChemDraw opens in the background for about a minute near the end. Don't click or close its windows.
