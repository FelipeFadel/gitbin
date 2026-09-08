#!/usr/bin/env python3
"""
commands/checkout.py
Implementa: gitbin checkout <versao>

Restaura uma versao anterior como estado atual.
O arquivo GLB no disco e sobrescrito com o conteudo da versao escolhida.
Todos os snapshots sao preservados.
"""

import os
import json
import subprocess

from gitbin import repo
from gitbin.glb import reconstruir_glb, reconstruir_bin, calcular_hashes


def _copiar(src, dest):
    """Copia preservando reflink no Btrfs (nao duplica os extents)."""
    resultado = subprocess.run(
        ["cp", "--reflink=auto", src, dest],
        capture_output=True, text=True
    )
    if resultado.returncode != 0:
        with open(src, "rb") as f:
            dados = f.read()
        with open(dest, "wb") as f:
            f.write(dados)


def cmd_checkout(versao_str):
    repo.assert_repo()
    config = repo.ler_config()

    # Normaliza o nome da versao (aceita "3", "v3" e "v0003")
    if versao_str.isdigit():
        versao_str = f"v{int(versao_str):04d}"
    elif versao_str.startswith("v"):
        try:
            versao_str = f"v{int(versao_str[1:]):04d}"
        except ValueError:
            pass

    snap_path = repo.snapshot_path(versao_str)

    if not os.path.isdir(snap_path):
        snapshots = repo.listar_snapshots()
        print(f"Erro: versao '{versao_str}' nao encontrada.")
        if snapshots:
            print(f"Versoes disponiveis: {', '.join(snapshots)}")
        raise SystemExit(1)

    arquivo_glb = config["arquivo"]
    print(f"\nRestaurando {versao_str} -> {os.path.basename(arquivo_glb)}")

    # Le a estrutura gravada no proprio snapshot, e nao a do arquivo em disco:
    # o arquivo atual pode ter outro numero ou outro layout de bufferViews.
    json_path = os.path.join(snap_path, "gltf.json")
    if not os.path.isfile(json_path):
        print(f"Erro: gltf.json nao encontrado no snapshot {versao_str}.")
        print("Este snapshot foi criado por uma versao antiga do gitbin,")
        print("que nao guardava a estrutura do GLB junto dos segmentos.")
        print("Recrie o repositorio para poder restaurar esta versao.")
        raise SystemExit(1)

    with open(json_path, "r") as f:
        gltf_json = json.load(f)

    buffer_views = gltf_json.get("bufferViews", [])

    # Carrega os segmentos do snapshot escolhido
    segmentos = {}
    for i in range(len(buffer_views)):
        bv_path = os.path.join(snap_path, f"bufferView_{i:04d}.bin")
        if not os.path.isfile(bv_path):
            print(f"Erro: bufferView_{i:04d}.bin nao encontrada no snapshot {versao_str}.")
            raise SystemExit(1)
        with open(bv_path, "rb") as f:
            segmentos[i] = f.read()

    # Reconstroi o GLB e sobrescreve o arquivo no disco
    try:
        glb_restaurado = reconstruir_glb(
            gltf_json, reconstruir_bin(gltf_json, segmentos)
        )
    except ValueError as e:
        print(f"Erro ao remontar o GLB: {e}")
        raise SystemExit(1)

    with open(arquivo_glb, "wb") as f:
        f.write(glb_restaurado)

    # Sincroniza o subvolume ativo com o snapshot restaurado
    atual_dir = repo.atual_dir()
    for arquivo in os.listdir(atual_dir):
        if arquivo.endswith(".bin") or arquivo == "gltf.json":
            os.remove(os.path.join(atual_dir, arquivo))

    for i in segmentos:
        _copiar(
            os.path.join(snap_path, f"bufferView_{i:04d}.bin"),
            os.path.join(atual_dir, f"bufferView_{i:04d}.bin"),
        )
    _copiar(json_path, os.path.join(atual_dir, "gltf.json"))

    # Atualiza o estado para refletir a versao restaurada
    repo.salvar_estado(calcular_hashes(segmentos))

    # Atualiza versao atual na config.
    # Os snapshots seguintes continuam existindo; o proximo save recebe um
    # numero novo, calculado por repo.proxima_versao().
    try:
        num_versao = int(versao_str[1:])
    except ValueError:
        num_versao = config["versao_atual"]

    config["versao_atual"] = num_versao
    repo.salvar_config(config)

    print(f"Versao {versao_str} restaurada com sucesso.")
    print(f"Arquivo atualizado: {arquivo_glb}")
    print(f"Snapshots preservados: {', '.join(repo.listar_snapshots())}")
    print()
    print(f"Execute 'gitbin save' para registrar este estado como "
          f"{repo.proxima_versao(config)}.")
