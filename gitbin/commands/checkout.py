#!/usr/bin/env python3
"""
commands/checkout.py
Implementa: gitbin checkout <versao>

Restaura uma versao anterior como estado atual.
O arquivo GLB no disco e sobrescrito com o conteudo da versao escolhida.
Todos os snapshots sao preservados.
"""

import os
import subprocess

from gitbin import repo
from gitbin.glb import parse_glb, reconstruir_glb_de_segmentos


def cmd_checkout(versao_str):
    repo.assert_repo()
    config = repo.ler_config()

    # Normaliza o nome da versao (aceita "3", "v3" e "v0003")
    if versao_str.isdigit():
        versao_str = f"v{int(versao_str):04d}"
    elif versao_str.startswith("v") and not versao_str[1:].zfill(4) == versao_str[1:]:
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

    # Le o arquivo GLB original para obter a estrutura JSON (bufferViews, etc)
    chunks = parse_glb(arquivo_glb)
    buffer_views = chunks["json"].get("bufferViews", [])

    # Carrega os segmentos do snapshot escolhido
    segmentos = {}
    for i, bv in enumerate(buffer_views):
        bv_path = os.path.join(snap_path, f"bufferView_{i:04d}.bin")
        if not os.path.isfile(bv_path):
            print(f"Erro: bufferView_{i:04d}.bin nao encontrada no snapshot {versao_str}.")
            raise SystemExit(1)
        with open(bv_path, "rb") as f:
            segmentos[i] = f.read()

    # Reconstroi o GLB e sobrescreve o arquivo no disco
    glb_restaurado = reconstruir_glb_de_segmentos(chunks, segmentos)
    with open(arquivo_glb, "wb") as f:
        f.write(glb_restaurado)

    # Sincroniza o subvolume ativo com o snapshot restaurado
    # Apaga os arquivos atuais e copia os do snapshot
    atual_dir = repo.atual_dir()
    for arquivo in os.listdir(atual_dir):
        if arquivo.endswith(".bin"):
            os.remove(os.path.join(atual_dir, arquivo))

    for i in segmentos:
        src  = os.path.join(snap_path, f"bufferView_{i:04d}.bin")
        dest = os.path.join(atual_dir, f"bufferView_{i:04d}.bin")
        with open(src, "rb") as f:
            dados = f.read()
        with open(dest, "wb") as f:
            f.write(dados)

    # Atualiza o estado para refletir a versao restaurada
    from gitbin.glb import extrair_buffer_views, calcular_hashes
    hashes = calcular_hashes({i: s for i, s in segmentos.items()})
    repo.salvar_estado(hashes)

    # Atualiza versao atual na config
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
    print("Execute 'gitbin save' para registrar este estado como uma nova versao.")