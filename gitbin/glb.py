#!/usr/bin/env python3
"""
glb.py
Leitura, segmentacao e reconstrucao de arquivos GLB.
"""

import struct
import json
import hashlib
import copy


def parse_glb(filepath):
    """Le um arquivo GLB e retorna os chunks JSON e BIN separados."""
    with open(filepath, "rb") as f:
        magic, version, length = struct.unpack("<III", f.read(12))

        if magic != 0x46546C67:
            raise ValueError(f"Arquivo nao e um GLB valido: {filepath}")

        chunks = {}
        while f.tell() < length:
            chunk_length, chunk_type = struct.unpack("<II", f.read(8))
            chunk_data = f.read(chunk_length)

            if chunk_type == 0x4E4F534A:
                chunks["json"] = json.loads(
                    chunk_data.decode("utf-8").rstrip("\x00")
                )
            elif chunk_type == 0x004E4942:
                chunks["bin"] = chunk_data

    return chunks


def extrair_buffer_views(chunks):
    """
    Extrai cada bufferView como um segmento de bytes independente.
    Retorna dict: indice -> bytes
    """
    if "bin" not in chunks:
        return {}

    bin_data    = chunks["bin"]
    buffer_views = chunks["json"].get("bufferViews", [])
    segmentos   = {}

    for i, bv in enumerate(buffer_views):
        offset = bv.get("byteOffset", 0)
        length = bv["byteLength"]
        segmentos[i] = bin_data[offset: offset + length]

    return segmentos


def calcular_hashes(segmentos):
    """Calcula SHA-256 de cada segmento. Retorna dict: indice -> hash hex."""
    return {
        str(i): hashlib.sha256(dados).hexdigest()
        for i, dados in segmentos.items()
    }


def classificar(estado_anterior, hashes):
    """
    Compara os hashes da versao nova com os da anterior, por conteudo.

    Uma bufferView cujo hash ja existia na versao anterior, mesmo em outro
    indice, e "reaproveitada": seus bytes ja estao no disco. Isso torna o
    diff imune a reordenacao e a mudanca na quantidade de bufferViews.

    Retorna (novos, modificados, reaproveitados, removidos, inalterados);
    reaproveitados e dict indice_novo -> indice_antigo, os demais sao listas.
    """
    por_hash = {h: i for i, h in estado_anterior.items()}
    novos, modificados, removidos, inalterados = [], [], [], []
    reaproveitados = {}

    for idx_str, hash_atual in hashes.items():
        if estado_anterior.get(idx_str) == hash_atual:
            inalterados.append(idx_str)
        elif hash_atual in por_hash:
            reaproveitados[idx_str] = por_hash[hash_atual]
        elif idx_str in estado_anterior:
            modificados.append(idx_str)
        else:
            novos.append(idx_str)

    for idx_str in estado_anterior:
        if idx_str not in hashes:
            removidos.append(idx_str)

    return novos, modificados, reaproveitados, removidos, inalterados


def reconstruir_glb(gltf_json, bin_data):
    """Reconstroi um arquivo GLB a partir do JSON e do BIN."""
    json_bytes = json.dumps(
        gltf_json, separators=(",", ":")
    ).encode("utf-8")

    while len(json_bytes) % 4 != 0:
        json_bytes += b"\x20"

    bin_padded = bytearray(bin_data)
    while len(bin_padded) % 4 != 0:
        bin_padded += b"\x00"

    total_length = 12 + 8 + len(json_bytes) + 8 + len(bin_padded)

    glb  = bytearray()
    glb += struct.pack("<III", 0x46546C67, 2, total_length)
    glb += struct.pack("<II",  len(json_bytes), 0x4E4F534A)
    glb += json_bytes
    glb += struct.pack("<II",  len(bin_padded), 0x004E4942)
    glb += bin_padded

    return bytes(glb)


def tamanho_buffer(gltf_json):
    """
    Tamanho real do chunk BIN em bytes.

    Nao e a soma dos byteLength: bufferViews sao alinhados em 4 bytes,
    entao existem lacunas de padding entre eles. Usa o byteLength
    declarado em buffers[0]; se faltar, cai no maior byteOffset+byteLength.
    """
    buffers = gltf_json.get("buffers", [])
    if buffers and "byteLength" in buffers[0]:
        return buffers[0]["byteLength"]

    buffer_views = gltf_json.get("bufferViews", [])
    if not buffer_views:
        return 0

    return max(
        bv.get("byteOffset", 0) + bv["byteLength"]
        for bv in buffer_views
    )


def reconstruir_bin(gltf_json, segmentos):
    """Remonta o chunk BIN colocando cada segmento no seu byteOffset."""
    buffer_views = gltf_json.get("bufferViews", [])
    novo_bin     = bytearray(tamanho_buffer(gltf_json))

    for i, bv in enumerate(buffer_views):
        offset = bv.get("byteOffset", 0)
        length = bv["byteLength"]
        if offset + length > len(novo_bin):
            raise ValueError(
                f"bufferView {i} (offset {offset}, len {length}) "
                f"nao cabe no buffer de {len(novo_bin)} bytes."
            )
        novo_bin[offset: offset + length] = segmentos[i]

    return bytes(novo_bin)


def reconstruir_glb_de_segmentos(chunks, segmentos):
    """
    Reconstroi o BIN a partir dos segmentos extraidos e devolve o GLB completo.
    Util para restaurar uma versao a partir dos arquivos de bufferView.
    """
    gltf_json = chunks["json"]
    return reconstruir_glb(gltf_json, reconstruir_bin(gltf_json, segmentos))

def _remapear(j, campo_acc, campo_bv):
    """Aplica os mapas de accessors e bufferViews a todas as referencias do JSON."""
    for m in j.get("meshes", []):
        for p in m["primitives"]:
            p["attributes"] = {k: campo_acc[v] for k, v in p["attributes"].items()}
            if "indices" in p:
                p["indices"] = campo_acc[p["indices"]]
            if "targets" in p:
                p["targets"] = [{k: campo_acc[v] for k, v in t.items()} for t in p["targets"]]
    for s in j.get("skins", []):
        if "inverseBindMatrices" in s:
            s["inverseBindMatrices"] = campo_acc[s["inverseBindMatrices"]]
    for a in j.get("animations", []):
        for s in a["samplers"]:
            s["input"], s["output"] = campo_acc[s["input"]], campo_acc[s["output"]]
    for a in j.get("accessors", []):
        if "bufferView" in a:
            a["bufferView"] = campo_bv[a["bufferView"]]
        for parte in ("indices", "values"):
            if "sparse" in a:
                a["sparse"][parte]["bufferView"] = campo_bv[a["sparse"][parte]["bufferView"]]
    for img in j.get("images", []):
        if "bufferView" in img:
            img["bufferView"] = campo_bv[img["bufferView"]]


def _accessors_usados(j):
    usados = []
    for m in j.get("meshes", []):
        for p in m["primitives"]:
            usados += p["attributes"].values()
            usados += [p["indices"]] if "indices" in p else []
            for t in p.get("targets", []):
                usados += t.values()
    usados += [s["inverseBindMatrices"] for s in j.get("skins", []) if "inverseBindMatrices" in s]
    for a in j.get("animations", []):
        for s in a["samplers"]:
            usados += [s["input"], s["output"]]
    return set(usados)


def mesclar(base, novo, preservar):
    """
    Monta um GLB a partir de `novo` (export do Blender) reaproveitando, para as
    malhas que nao mudaram, os accessors e os bytes originais de `base`.

    base, novo: dicts de parse_glb(). preservar: {malha_novo: malha_base}.
    Nos, materiais, imagens e malhas editadas vem do novo; a geometria das
    malhas preservadas vem byte a byte da base, entao as bufferViews delas
    tem o mesmo hash da versao anterior e nao sao gravadas de novo.

    Retorna (gltf_json, bin_data).
    """
    j  = copy.deepcopy(novo["json"])
    bj = base["json"]
    seg_novo, seg_base = extrair_buffer_views(novo), extrair_buffer_views(base)

    bvs  = [(dict(bv), seg_novo[i]) for i, bv in enumerate(j.get("bufferViews", []))]
    accs = j.setdefault("accessors", [])
    mapa_bv, mapa_acc = {}, {}

    def trazer_bv(bi):
        if bi not in mapa_bv:
            bvs.append((dict(bj["bufferViews"][bi]), seg_base[bi]))
            mapa_bv[bi] = len(bvs) - 1
        return mapa_bv[bi]

    def trazer_acc(ai):
        if ai not in mapa_acc:
            a = copy.deepcopy(bj["accessors"][ai])
            if "bufferView" in a:
                a["bufferView"] = trazer_bv(a["bufferView"])
            for parte in ("indices", "values"):
                if "sparse" in a:
                    a["sparse"][parte]["bufferView"] = trazer_bv(a["sparse"][parte]["bufferView"])
            accs.append(a)
            mapa_acc[ai] = len(accs) - 1
        return mapa_acc[ai]

    for ni, bi in preservar.items():
        pn, pb = j["meshes"][int(ni)]["primitives"], bj["meshes"][int(bi)]["primitives"]
        if len(pn) != len(pb):
            raise ValueError(f"malha {ni} tem {len(pn)} primitivas e a base {bi} tem {len(pb)}")
        for p, q in zip(pn, pb):
            p["attributes"] = {k: trazer_acc(v) for k, v in q["attributes"].items()}
            for chave in ("indices", "mode"):
                p.pop(chave, None)
                if chave in q:
                    p[chave] = trazer_acc(q[chave]) if chave == "indices" else q[chave]
            p.pop("targets", None)
            if "targets" in q:
                p["targets"] = [{k: trazer_acc(v) for k, v in t.items()} for t in q["targets"]]

    # Descarta accessors e bufferViews que ficaram sem uso (os do export
    # que foram substituidos) e compacta os indices.
    usados_acc = sorted(_accessors_usados(j))
    campo_acc  = {a: k for k, a in enumerate(usados_acc)}
    j["accessors"] = [accs[a] for a in usados_acc]
    usados_bv = set()
    for a in j["accessors"]:
        usados_bv.add(a.get("bufferView"))
        if "sparse" in a:
            usados_bv |= {a["sparse"]["indices"]["bufferView"], a["sparse"]["values"]["bufferView"]}
    usados_bv |= {img["bufferView"] for img in j.get("images", []) if "bufferView" in img}
    usados_bv.discard(None)
    usados_bv = sorted(usados_bv)
    campo_bv  = {b: k for k, b in enumerate(usados_bv)}
    _remapear(j, campo_acc, campo_bv)

    # Remonta o BIN com cada bufferView alinhada em 4 bytes
    novo_bin, novas_bvs = bytearray(), []
    for b in usados_bv:
        bv, dados = bvs[b]
        novo_bin += b"\x00" * (-len(novo_bin) % 4)
        bv.update(buffer=0, byteOffset=len(novo_bin), byteLength=len(dados))
        novas_bvs.append(bv)
        novo_bin += dados
    j["bufferViews"] = novas_bvs
    j["buffers"] = [{"byteLength": len(novo_bin)}]

    # As marcas do addon so servem para a mescla; nao vao para o arquivo
    for m in j.get("meshes", []):
        extras = m.get("extras", {})
        for k in [k for k in extras if k.startswith("gitbin_")]:
            del extras[k]
        if "extras" in m and not extras:
            del m["extras"]

    return j, bytes(novo_bin)
