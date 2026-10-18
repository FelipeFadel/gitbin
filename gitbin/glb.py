#!/usr/bin/env python3
"""
glb.py
Leitura, segmentacao e reconstrucao de arquivos GLB.
"""

import struct
import json
import hashlib


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