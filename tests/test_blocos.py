"""Rodar com: python3 tests/test_blocos.py"""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gitbin.repo import gravar_blocos, BLOCO

with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "bv.bin")
    antigo = bytes(3 * BLOCO + 100)
    with open(path, "wb") as f:
        f.write(antigo)

    # um byte alterado no segundo bloco: so ele e regravado
    novo = bytearray(antigo); novo[BLOCO + 7] = 1
    assert gravar_blocos(path, bytes(novo)) == BLOCO
    assert open(path, "rb").read() == novo

    # arquivo encolhe: nada a regravar, so truncar
    assert gravar_blocos(path, bytes(novo[:BLOCO])) == 0
    assert open(path, "rb").read() == novo[:BLOCO]
print("ok")
