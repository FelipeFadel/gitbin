"""Rodar com: blender -b --factory-startup --python tests/test_normais_degeneradas.py
(--factory-startup: sem ele o Blender carrega o addon instalado, nao o do repositorio)

Uma malha com uma face degenerada (area zero): o Blender devolve normal zero
nos vertices dela. Ao mover outro vertice, posicoes_na_ordem deve manter a
normal da base nesses vertices, e nao gravar uma normal zero (invalida no glTF).
"""
import os
import sys
import struct
import bpy
import bmesh
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "addon"))
import gitbin_blender_addon as ga

# Um quadrado normal e um triangulo com os 3 vertices alinhados (area zero)
me = bpy.data.meshes.new("teste")
bm = bmesh.new()
quad = [bm.verts.new(p) for p in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
bm.faces.new(quad).smooth = True
linha = [bm.verts.new(p) for p in ((2, 0, 0), (3, 0, 0), (4, 0, 0))]
# Malha toda suave (como no San Miguel): normal por vertice, media ponderada pela
# area das faces, que aqui e zero
bm.faces.new(linha).smooth = True
bm.to_mesh(me)
bm.free()
n = len(me.vertices)

# Base glTF em memoria: POSITION e NORMAL na ordem dos vertices do Blender,
# com uma normal valida (0, 1, 0) onde o Blender devolve zero.
co = np.empty(n * 3, dtype=np.float32)
me.vertices.foreach_get("co", co)
pos = ga.zup_para_yup(co.reshape(n, 3)).astype(np.float32)
nor = ga.zup_para_yup(ga.por_canto(me, me.corner_normals, "vector", 3)).astype(np.float32)
DEGENERADOS = np.where(np.linalg.norm(nor, axis=1) == 0)[0]
assert len(DEGENERADOS) and min(DEGENERADOS) >= 4, "a face deveria ser degenerada"
nor[DEGENERADOS] = (0, 1, 0)
bin_chunk = pos.tobytes() + nor.tobytes()
gltf = {
    "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 12 * n},
                    {"buffer": 0, "byteOffset": 12 * n, "byteLength": 12 * n}],
    "accessors": [{"bufferView": 0, "componentType": 5126, "count": n, "type": "VEC3"},
                  {"bufferView": 1, "componentType": 5126, "count": n, "type": "VEC3"}],
}
prim = {"attributes": {"POSITION": 0, "NORMAL": 1}}

# Move um vertice do quadrado, longe da face degenerada
me.vertices[0].co.z += 0.1
me.update()
novos = ga.posicoes_na_ordem(me, gltf, bin_chunk, prim)

comprimentos = np.linalg.norm(novos["NORMAL"], axis=1)
assert np.allclose(comprimentos, 1, atol=1e-5), f"normal nao unitaria: {comprimentos}"
assert np.array_equal(novos["NORMAL"][DEGENERADOS], nor[DEGENERADOS])
assert novos["POSITION"][0, 1] != pos[0, 1]  # o vertice movido mudou (z do Blender = y do glTF)
print("ok")
