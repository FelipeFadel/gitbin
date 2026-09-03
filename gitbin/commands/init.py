#!/usr/bin/env python3
"""
commands/init.py
Implementa: gitbin init <arquivo.glb>

Cria a estrutura .gitbin no diretorio atual:
  .gitbin/
    - disco.img             imagem Btrfs de 10 GB
    - mount/                ponto de montagem
    -  -  versoes/atual/    subvolume ativo
    -  -  snapshots/        versoes imutaveis
    -config.json            metadados do repositorio
    -estado.json            hashes da ultima versao salva
"""

import os
import subprocess
import json

from gitbin import repo
from gitbin.glb import parse_glb, extrair_buffer_views, calcular_hashes


def cmd_init(arquivo_glb):
    arquivo_glb = os.path.abspath(arquivo_glb)

    if not os.path.isfile(arquivo_glb):
        print(f"Erro: arquivo nao encontrado: {arquivo_glb}")
        raise SystemExit(1)

    if not arquivo_glb.endswith(".glb"):
        print("Erro: apenas arquivos .glb sao suportados.")
        raise SystemExit(1)

    gd = repo.gitbin_dir()
    if os.path.isdir(gd):
        print("Erro: repositorio gitbin ja existe neste diretorio.")
        raise SystemExit(1)

    print(f"Inicializando repositorio gitbin para: {os.path.basename(arquivo_glb)}")

    # Cria estrutura de diretorios
    md = repo.mount_dir()
    os.makedirs(md, exist_ok=True)

    # Cria imagem Btrfs de 10 GB
    disco = repo.disco_img()
    print("Criando imagem Btrfs (10 GB)...")
    subprocess.run(
        ["dd", "if=/dev/zero", f"of={disco}", "bs=1M", "count=10240"],
        check=True, capture_output=True
    )

    # Formata como Btrfs
    subprocess.run(
        ["mkfs.btrfs", disco],
        check=True, capture_output=True
    )

    # Monta via loopback
    subprocess.run(
        ["sudo", "mount", "-o", "loop", disco, md],
        check=True
    )

    # Cria subvolumes
    subprocess.run(
        ["sudo", "btrfs", "subvolume", "create",
         os.path.join(md, repo.VERSOES_DIR)],
        check=True, capture_output=True
    )
    subprocess.run(
        ["sudo", "btrfs", "subvolume", "create",
         os.path.join(md, repo.ATUAL_DIR)],
        check=True, capture_output=True
    )

    # Cria diretorio de snapshots
    subprocess.run(
        ["sudo", "mkdir", "-p", os.path.join(md, repo.SNAPS_DIR)],
        check=True
    )

    # Ajusta permissoes para o usuario atual
    usuario = os.environ.get("USER", "ubuntu")
    subprocess.run(
        ["sudo", "chown", "-R", f"{usuario}:{usuario}", md],
        check=True
    )

    # Salva config
    config = {
        "arquivo":       arquivo_glb,
        "versao_atual":  0,
        "total_versoes": 0,
    }
    repo.salvar_config(config)

    # Estado inicial vazio
    repo.salvar_estado({})

    print(f"Repositorio inicializado em {gd}")
    print(f"Arquivo rastreado: {arquivo_glb}")
    print("Execute 'gitbin save' para registrar a primeira versao.")