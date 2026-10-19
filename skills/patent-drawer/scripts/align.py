"""Shared-core alignment: compounds of one series get their common core drawn
in the same place and the same orientation, so cards can be compared by eye.

    cores = find_cores({"A1": smiles, ...})   # [{"smarts", "coords", "members"}]
    core_for(smiles, cores)                   # the core to draw this compound on, or None

A series is a set of compounds sharing a core of at least 8 atoms with a ring.
Start from the most typical compound and add the others from most to least
similar, keeping track of the core they share. A few odd compounds do not spoil
it: take the largest core found in all of them, else in 90 %, 75 % or 50 %.
Whatever is left is grouped again the same way.
"""
from rdkit import Chem, DataStructs
from rdkit.Chem import rdFMCS, rdFingerprintGenerator

MIN_ATOMS = 8


def _mcs(mols):
    res = rdFMCS.FindMCS(mols, timeout=10, ringMatchesRingOnly=True, completeRingsOnly=True)
    if res.numAtoms < MIN_ATOMS:
        return None
    p = Chem.MolFromSmarts(res.smartsString)
    Chem.FastFindRings(p)
    return res.smartsString if p.GetRingInfo().NumRings() else None


def _best_core(mols):
    gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    fps = [gen.GetFingerprint(m) for m in mols]
    sims = [DataStructs.BulkTanimotoSimilarity(f, fps) for f in fps]
    seed = max(range(len(mols)), key=lambda i: sum(sims[i]))
    order = sorted(range(len(mols)), key=lambda i: -sims[seed][i])
    group, found = [mols[seed]], []          # found: (core atoms, coverage, smarts)
    for i in order:
        if i == seed:
            continue
        sm = _mcs(group + [mols[i]])
        if not sm:
            continue                         # this one does not share a real core
        group.append(mols[i])
        p = Chem.MolFromSmarts(sm)
        found.append((p.GetNumAtoms(), sum(m.HasSubstructMatch(p) for m in mols), sm))
    for share in (1.0, 0.9, 0.75, 0.5):
        ok = [f for f in found if f[1] >= share * len(mols)]
        if ok:
            return max(ok)[2]
    return max(found, key=lambda f: (f[1], f[0]))[2] if found else None


def find_cores(smiles):
    from draw_card import _layout
    left = {no: Chem.MolFromSmiles(s) for no, s in smiles.items()}
    left = {no: m for no, m in left.items() if m is not None}
    cores = []
    while len(left) >= 2:
        sm = _best_core(list(left.values()))
        if not sm:
            break
        p = Chem.MolFromSmarts(sm)
        members = [no for no, m in left.items() if m.HasSubstructMatch(p)]
        # the core is placed as it sits in the smallest member's normal drawing
        ref = min(members, key=lambda no: (left[no].GetNumAtoms(), no))
        pts = _layout(left[ref])
        coords = [list(pts[i]) for i in left[ref].GetSubstructMatch(p)]
        cores.append({"smarts": sm, "coords": coords, "members": sorted(members)})
        for no in members:
            del left[no]
    return cores


def core_for(smiles, cores):
    """First core (largest series first) this compound contains: (pattern, coords)."""
    m = Chem.MolFromSmiles(smiles)
    for c in cores:
        p = Chem.MolFromSmarts(c["smarts"])
        if m is not None and m.HasSubstructMatch(p):
            return p, c["coords"]
    return None
