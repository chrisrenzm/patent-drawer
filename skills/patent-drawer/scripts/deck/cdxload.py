"""Load a ChemDraw card as binary CDX bytes. Accepts .cdx or .cdxml (converted by cdxml2cdx)."""
import cdxml2cdx


def load(path):
    if path.lower().endswith('.cdx'):
        return open(path, 'rb').read()
    return cdxml2cdx.convert_file(path)
