"""Rodar com: python3 tests/test_classificar.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gitbin.glb import classificar

anterior = {"0": "a", "1": "b", "2": "c"}

# b saiu da posicao 1 e foi para a 2 (ex.: uma bufferView nova inserida antes)
novos, mod, reap, rem, inal = classificar(anterior, {"0": "a", "1": "x", "2": "b", "3": "c"})
assert inal == ["0"] and mod == ["1"] and novos == []
assert reap == {"2": "1", "3": "2"} and rem == []

# bufferView removida no fim e conteudo identico: nada a gravar
novos, mod, reap, rem, inal = classificar(anterior, {"0": "a", "1": "b"})
assert (novos, mod, reap, rem, inal) == ([], [], {}, ["2"], ["0", "1"])

# primeiro save: tudo novo
assert classificar({}, {"0": "a"})[0] == ["0"]
print("ok")
