#!/usr/bin/env python3
"""
commands/mesclar.py
Implementa: gitbin mesclar <novo.glb> <base.glb> <preservar.json> <saida.glb>

Usado pelo addon do Blender antes do save. O exportador do Blender reconstroi
a geometria de todas as malhas a cada exportacao; este comando devolve, para
as malhas que o addon detectou como inalteradas, os bytes originais da base.

preservar.json: {"<indice da malha no novo>": <indice da malha na base>, ...}
"""

import json

from gitbin.glb import parse_glb, mesclar, reconstruir_glb


def cmd_mesclar(novo_path, base_path, preservar_path, saida_path):
    with open(preservar_path) as f:
        preservar = json.load(f)

    novo = parse_glb(novo_path)
    gltf_json, bin_data = mesclar(parse_glb(base_path), novo, preservar)

    with open(saida_path, "wb") as f:
        f.write(reconstruir_glb(gltf_json, bin_data))

    print(f"Malhas preservadas: {len(preservar)} de {len(novo['json'].get('meshes', []))}")
    print(f"bufferViews: {len(novo['json'].get('bufferViews', []))} no export, "
          f"{len(gltf_json['bufferViews'])} no resultado")
