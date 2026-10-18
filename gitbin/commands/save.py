#!/usr/bin/env python3
"""
commands/save.py
Implementa: gitbin save

Detecta quais bufferViews mudaram desde o ultimo save,
grava apenas as modificadas no subvolume Btrfs e
cria um snapshot imutavel da versao atual.
"""

import os
import json
import subprocess
import time

from gitbin import repo
from gitbin.glb import (parse_glb, extrair_buffer_views, calcular_hashes,
                        classificar)
from datetime import datetime


def cmd_save():
    repo.assert_repo()
    repo.garantir_montado()
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

    # Deteccao diferencial por conteudo
    novos, modificados, reaproveitados, removidos, inalterados = \
        classificar(estado_anterior, hashes)

    # Grava o JSON desta versao junto dos segmentos.
    # Sem isso o checkout precisaria ler a estrutura do arquivo que esta
    # no disco agora, que pode ter outro layout de bufferViews.
    with open(os.path.join(atual_dir, "gltf.json"), "w") as f:
        json.dump(chunks["json"], f, separators=(",", ":"))

    # Grava apenas os segmentos novos ou modificados
    para_gravar = novos + modificados
    bytes_gravados = 0

    gravados_nesta = {}  # hash -> caminho, para conteudo repetido na mesma versao

    for idx_str in para_gravar:
        idx  = int(idx_str)
        path = os.path.join(atual_dir, f"bufferView_{idx:04d}.bin")
        if hashes[idx_str] in gravados_nesta:
            repo.copiar_reflink(gravados_nesta[hashes[idx_str]], path)
            continue
        if idx_str in modificados and os.path.isfile(path):
            # Versao anterior no mesmo indice: so os blocos diferentes
            bytes_gravados += repo.gravar_blocos(path, segmentos[idx])
        else:
            with open(path, "wb") as f:
                f.write(segmentos[idx])
            bytes_gravados += len(segmentos[idx])
        gravados_nesta[hashes[idx_str]] = path

    # Conteudo que ja existia em outro indice: clona do snapshot da versao
    # base. O snapshot e somente leitura, entao a ordem das copias nao importa,
    # e o reflink compartilha os extents em vez de gravar os bytes de novo.
    base_snap = repo.snapshot_path(f"v{config['versao_atual']:04d}")
    for idx_str, idx_antigo in reaproveitados.items():
        repo.copiar_reflink(
            os.path.join(base_snap, f"bufferView_{int(idx_antigo):04d}.bin"),
            os.path.join(atual_dir, f"bufferView_{int(idx_str):04d}.bin"),
        )

    # Remove segmentos que deixaram de existir
    for idx_str in removidos:
        idx  = int(idx_str)
        path = os.path.join(atual_dir, f"bufferView_{idx:04d}.bin")
        if os.path.exists(path):
            os.remove(path)

    # Metadados da versao, lidos pelo log sem precisar de root
    meta = {
        "versao":  nome_versao,
        "data":    datetime.now().isoformat(sep=" ", timespec="seconds"),
        "arquivo": os.path.basename(arquivo_glb),
        "gravados_bytes": bytes_gravados,
    }
    with open(os.path.join(atual_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    # Cria snapshot imutavel
    snap_path = repo.snapshot_path(nome_versao)
    subprocess.run(
        ["btrfs", "subvolume", "snapshot", "-r",
         atual_dir, snap_path],
        check=True, capture_output=True
    )

    duracao = time.perf_counter() - inicio

    # Atualiza config e estado
    config["versao_atual"]   = int(nome_versao[1:])
    config["total_versoes"] += 1
    repo.salvar_config(config)
    repo.salvar_estado(hashes)

    # Exibe resumo
    tamanho_total = os.path.getsize(arquivo_glb)
    economia = (1 - bytes_gravados / tamanho_total) * 100 if tamanho_total > 0 else 0

    print(f"\nVersao {nome_versao} salva.")
    print(f"  Novas:       {len(novos):>4} bufferViews")
    print(f"  Modificadas: {len(modificados):>4} bufferViews")
    print(f"  Reaproveit.: {len(reaproveitados):>4} bufferViews (reflink)")
    print(f"  Removidas:   {len(removidos):>4} bufferViews")
    print(f"  Inalteradas: {len(inalterados):>4} bufferViews")
    print(f"  Gravados:    {bytes_gravados / 1024 / 1024:.2f} MB")
    print(f"  Economia:    {economia:.2f}%")
    print(f"  Tempo:       {duracao:.4f}s")
    print(f"  Snapshot:    {snap_path}")