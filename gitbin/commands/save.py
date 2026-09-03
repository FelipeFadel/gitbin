#!/usr/bin/env python3
"""
commands/save.py
Implementa: gitbin save

Detecta quais bufferViews mudaram desde o ultimo save,
grava apenas as modificadas no subvolume Btrfs e
cria um snapshot imutavel da versao atual.
"""

import os
import subprocess
import time

from gitbin import repo
from gitbin.glb import parse_glb, extrair_buffer_views, calcular_hashes


def cmd_save():
    repo.assert_repo()
    config = repo.ler_config()
    estado_anterior = repo.ler_estado()

    arquivo_glb = config["arquivo"]

    if not os.path.isfile(arquivo_glb):
        print(f"Erro: arquivo rastreado nao encontrado: {arquivo_glb}")
        raise SystemExit(1)

    nome_versao = repo.proxima_versao(config)
    print(f"\nSalvando versao {nome_versao}...")
    print(f"Arquivo: {os.path.basename(arquivo_glb)}")

    inicio = time.perf_counter()

    # Leitura e segmentacao
    chunks    = parse_glb(arquivo_glb)
    segmentos = extrair_buffer_views(chunks)
    hashes    = calcular_hashes(segmentos)

    atual_dir = repo.atual_dir()

    # Deteccao diferencial
    novos       = []
    modificados = []
    removidos   = []
    inalterados = []

    for idx_str, hash_atual in hashes.items():
        if idx_str not in estado_anterior:
            novos.append(idx_str)
        elif estado_anterior[idx_str] != hash_atual:
            modificados.append(idx_str)
        else:
            inalterados.append(idx_str)

    for idx_str in estado_anterior:
        if idx_str not in hashes:
            removidos.append(idx_str)

    # Grava apenas os segmentos novos ou modificados
    para_gravar = novos + modificados
    bytes_gravados = 0

    for idx_str in para_gravar:
        idx  = int(idx_str)
        path = os.path.join(atual_dir, f"bufferView_{idx:04d}.bin")
        with open(path, "wb") as f:
            f.write(segmentos[idx])
        bytes_gravados += len(segmentos[idx])

    # Remove segmentos que deixaram de existir
    for idx_str in removidos:
        idx  = int(idx_str)
        path = os.path.join(atual_dir, f"bufferView_{idx:04d}.bin")
        if os.path.exists(path):
            os.remove(path)

    # Cria snapshot imutavel
    snap_path = repo.snapshot_path(nome_versao)
    subprocess.run(
        ["sudo", "btrfs", "subvolume", "snapshot", "-r",
         atual_dir, snap_path],
        check=True, capture_output=True
    )

    duracao = time.perf_counter() - inicio

    # Atualiza config e estado
    config["versao_atual"]  += 1
    config["total_versoes"] += 1
    repo.salvar_config(config)
    repo.salvar_estado(hashes)

    # Exibe resumo
    tamanho_total = os.path.getsize(arquivo_glb)
    economia = (1 - bytes_gravados / tamanho_total) * 100 if tamanho_total > 0 else 0

    print(f"\nVersao {nome_versao} salva.")
    print(f"  Novas:       {len(novos):>4} bufferViews")
    print(f"  Modificadas: {len(modificados):>4} bufferViews")
    print(f"  Removidas:   {len(removidos):>4} bufferViews")
    print(f"  Inalteradas: {len(inalterados):>4} bufferViews")
    print(f"  Gravados:    {bytes_gravados / 1024 / 1024:.2f} MB")
    print(f"  Economia:    {economia:.2f}%")
    print(f"  Tempo:       {duracao:.4f}s")
    print(f"  Snapshot:    {snap_path}")