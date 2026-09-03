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


def reconstruir_glb_de_segmentos(chunks, segmentos):
    """
    Reconstroi o BIN a partir dos segmentos extraidos e devolve o GLB completo.
    Util para restaurar uma versao a partir dos arquivos de bufferView.
    """
    gltf_json    = chunks["json"]
    buffer_views = gltf_json.get("bufferViews", [])

    novo_bin = bytearray(len(chunks["bin"]))

    for i, bv in enumerate(buffer_views):
        offset = bv.get("byteOffset", 0)
        length = bv["byteLength"]
        novo_bin[offset: offset + length] = segmentos[i]

    return reconstruir_glb(gltf_json, bytes(novo_bin))