#!/usr/bin/env python3
"""
repo.py
Utilitarios para localizar e ler o repositorio gitbin no diretorio atual
"""

import os
import json

GITBIN_DIR  = ".gitbin"
CONFIG_FILE = "config.json"
DISCO_IMG   = "disco.img"
MOUNT_DIR   = "mount"
VERSOES_DIR = "versoes"
ATUAL_DIR   = "versoes/atual"
SNAPS_DIR   = "snapshots"
ESTADO_FILE = "estado.json"


def gitbin_dir():
    return os.path.join(os.getcwd(), GITBIN_DIR)


def mount_dir():
    return os.path.join(gitbin_dir(), MOUNT_DIR)


def disco_img():
    return os.path.join(gitbin_dir(), DISCO_IMG)


def atual_dir():
    return os.path.join(mount_dir(), ATUAL_DIR)


def snaps_dir():
    return os.path.join(mount_dir(), SNAPS_DIR)


def estado_path():
    return os.path.join(gitbin_dir(), ESTADO_FILE)


def config_path():
    return os.path.join(gitbin_dir(), CONFIG_FILE)


def assert_repo():
    """Garante que existe um repositorio gitbin no diretorio atual."""
    if not os.path.isdir(gitbin_dir()):
        print("Erro: nenhum repositorio gitbin encontrado.")
        print("Execute 'gitbin init <arquivo.glb>' primeiro.")
        raise SystemExit(1)


def ler_config():
    with open(config_path(), "r") as f:
        return json.load(f)


def salvar_config(config):
    with open(config_path(), "w") as f:
        json.dump(config, f, indent=2)


def ler_estado():
    path = estado_path()
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def salvar_estado(estado):
    with open(estado_path(), "w") as f:
        json.dump(estado, f, indent=2)


def proxima_versao(config):
    """
    Retorna o nome da proxima versao livre (ex: v0004).

    Usa o maior snapshot ja existente como base, e nao apenas
    config['versao_atual']: depois de um checkout para uma versao antiga,
    versao_atual volta a apontar para tras e um save reutilizaria um nome
    de snapshot que ja existe.
    """
    maior = config.get("versao_atual", 0)

    for snap in listar_snapshots():
        try:
            maior = max(maior, int(snap[1:]))
        except ValueError:
            continue

    return f"v{maior + 1:04d}"


def snapshot_path(versao_str):
    return os.path.join(snaps_dir(), versao_str)


def listar_snapshots():
    """Retorna lista ordenada de snapshots existentes."""
    sd = snaps_dir()
    if not os.path.isdir(sd):
        return []
    return sorted([
        d for d in os.listdir(sd)
        if os.path.isdir(os.path.join(sd, d)) and d.startswith("v")
    ])