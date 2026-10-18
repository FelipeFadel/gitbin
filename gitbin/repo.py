#!/usr/bin/env python3
"""
repo.py
Utilitarios para localizar e ler o repositorio gitbin no diretorio atual
"""

import os
import json
import subprocess
import time

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
    """retorna a lista ordenada de snapshots existentes."""
    sd = snaps_dir()
    if not os.path.isdir(sd):
        return []
    return sorted([
        d for d in os.listdir(sd)
        if os.path.isdir(os.path.join(sd, d)) and d.startswith("v")
    ])

def copiar_reflink(src, dest):
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


def _rodar(cmd):
    """roda um comando e devolve o stdout, ou "" se ele falhar."""
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0:
        return ""
    return resultado.stdout.strip()

def _loop_do_disco():
    """devolve o /dev/loopN ligado ao disco.img, se precisar ele cria um novo"""

    saida = _rodar(["losetup", "-j", disco_img()])
    if saida:
        return saida.splitlines()[0].split(":", 1)[0]

    saida = _rodar(["udisksctl", "loop-setup", "--no-user-interaction",
                    "-f", disco_img()])
    if " as " in saida:
        return saida.rsplit(" as ", 1)[1].rstrip(".")
    return None

def _montagem_do_loop(dispositivo):
    """devolve onde o dispositivo esta montado, montando se preciso."""
    for _ in range(10):
        alvo = _rodar(["findmnt", "-n", "-o", "TARGET", "-S", dispositivo])
        if alvo:
            return alvo.splitlines()[0]

        # Pode falhar se o gnome montar no meio do caminho
        _rodar(["udisksctl", "mount", "--no-user-interaction",
                "-b", dispositivo])
        time.sleep(0.3)
    return None

def garantir_montado():
    """
    garante que .gitbin/mount aponta para a imagem Btrfs montada
    Monta via udisks
    """
    md = mount_dir()

    if os.path.ismount(os.path.realpath(md)):
        return

    dispositivo = _loop_do_disco()
    if not dispositivo:
        print("Erro: nao foi possivel ligar o disco.img a um dispositivo de loop.")
        print(f"Tente manualmente: udisksctl loop-setup -f {disco_img()}")
        raise SystemExit(1)

    alvo = _montagem_do_loop(dispositivo)
    if not alvo:
        print(f"Erro: nao foi possivel montar {dispositivo}.")
        print(f"Tente manualmente: udisksctl mount -b {dispositivo}")
        raise SystemExit(1)

    if os.path.islink(md):
        os.remove(md)
    elif os.path.isdir(md):
        os.rmdir(md)  # so apaga se estiver vazia
    os.symlink(alvo, md)
