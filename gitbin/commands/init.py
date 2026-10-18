#!/usr/bin/env python3
"""
commands/init.py
Implementa: gitbin init <arquivo.glb> [--size <tamanho>]

Exemplos:
  gitbin init modelo.glb
  gitbin init modelo.glb --size 5G
  gitbin init modelo.glb --size 500M

Tamanho padrao: 5G
"""

import os
import subprocess
import json
import argparse
import tempfile

from gitbin import repo
from gitbin.glb import parse_glb, extrair_buffer_views, calcular_hashes


def parse_tamanho(tamanho_str):
    """
    Converte string de tamanho para numero de blocos de 1M para o dd.
    Aceita formatos: 5G, 5g, 500M, 500m
    Retorna: (count, unidade_legivel)
    """
    tamanho_str = tamanho_str.strip()
    unidade = tamanho_str[-1].upper()
    valor_str = tamanho_str[:-1]

    try:
        valor = float(valor_str)
    except ValueError:
        raise ValueError(
            f"Tamanho invalido: '{tamanho_str}'. "
            f"Use formato como '5G' ou '500M'."
        )

    if unidade == "G":
        count = int(valor * 1024)
        legivel = f"{valor:.0f}G"
    elif unidade == "M":
        count = int(valor)
        legivel = f"{valor:.0f}M"
    else:
        raise ValueError(
            f"Unidade desconhecida: '{unidade}'. Use 'G' para gigabytes ou 'M' para megabytes."
        )

    if count < 100:
        raise ValueError("Tamanho minimo e 100M.")

    return count, legivel


def cmd_init(arquivo_glb, tamanho_str="5G"):
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

    try:
        count, legivel = parse_tamanho(tamanho_str)
    except ValueError as e:
        print(f"Erro: {e}")
        raise SystemExit(1)

    print(f"Inicializando repositorio gitbin para: {os.path.basename(arquivo_glb)}")
    print(f"Tamanho da imagem Btrfs: {legivel}")

    # Cria estrutura de diretorios
    md = repo.mount_dir()
    os.makedirs(md, exist_ok=True)

    # Cria imagem Btrfs esparsa: so ocupa no disco o que for gravado
    disco = repo.disco_img()
    print("Criando imagem Btrfs...")
    with open(disco, "wb") as f:
        f.truncate(count * 1024 * 1024)

    # Formata ja com os subvolumes e o diretorio de snapshots.
    # --rootdir copia a arvore com o dono atual, entao nao precisa de sudo
    # para criar subvolumes nem para dar chown depois.
    with tempfile.TemporaryDirectory() as raiz:
        os.makedirs(os.path.join(raiz, repo.ATUAL_DIR))
        os.makedirs(os.path.join(raiz, repo.SNAPS_DIR))
        # Nodesize de 4 KiB (padrao 16 KiB): cada snapshot e cada arquivo
        # alterado copiam (CoW) nos menores da arvore de metadados; com nos
        # menores o custo fixo por versao cai de ~96 KB para ~24 KB.
        subprocess.run(
            ["mkfs.btrfs", "-q", "-n", "4096", "-r", raiz,
             "-u", f"rw:{repo.VERSOES_DIR}",
             "-u", f"rw:{repo.ATUAL_DIR}",
             disco],
            check=True, capture_output=True
        )

    # Monta via udisks (loop + mount sem root)
    repo.garantir_montado()

    # Salva config
    config = {
        "arquivo":       arquivo_glb,
        "versao_atual":  0,
        "total_versoes": 0,
        "tamanho_disco": legivel,
    }
    repo.salvar_config(config)

    # Estado inicial vazio
    repo.salvar_estado({})

    print(f"Repositorio inicializado em {gd}")
    print(f"Arquivo rastreado: {arquivo_glb}")
    print("Execute 'gitbin save' para registrar a primeira versao.")