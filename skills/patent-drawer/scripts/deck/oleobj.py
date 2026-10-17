"""Wrap CDX bytes as an embedded ChemDraw OLE object (the .bin part inside a .pptx)."""
import os
import cfb

HERE = os.path.dirname(os.path.abspath(__file__))
OLE_DIR = os.path.join(HERE, '..', '..', 'templates', 'chemdraw_ole')
# CLSID 41BA6D21-A02E-11CE-8FD9-0020AFD1F20C = ChemDraw.Document.6.0
ROOT_CLSID = bytes.fromhex('216DBA412EA0CE118FD90020AFD1F20C')
COMPOBJ = open(os.path.join(OLE_DIR, 'CompObj.bin'), 'rb').read()
OLE = open(os.path.join(OLE_DIR, 'Ole.bin'), 'rb').read()


def make(cdx: bytes) -> bytes:
    assert cdx[:8] == b'VjCD0100', 'not a CDX file'
    return cfb.build(ROOT_CLSID, {'\x01CompObj': COMPOBJ, '\x01Ole': OLE, 'CONTENTS': cdx})
