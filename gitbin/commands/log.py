#!/usr/bin/env python3
"""
commands/log.py
Implementa: gitbin log

Lista todos os snapshots salvos com informacoes basicas.
"""

import os
import subprocess

from gitbin import repo


def cmd_log():
    repo.assert_repo()
    config    = repo.ler_config()
    snapshots = repo.listar_snapshots()

    if not snapshots:
        print("Nenhuma versao salva ainda. Execute 'gitbin save'.")
        return

    versao_atual = f"v{config['versao_atual']:04d}"

    print(f"\nRepositorio: {os.path.basename(config['arquivo'])}")
    print(f"Total de versoes: {len(snapshots)}\n")

    for snap in reversed(snapshots):
        snap_path = repo.snapshot_path(snap)

        # Tamanho do snapshot via du
        resultado = subprocess.run(
            ["sudo", "btrfs", "subvolume", "show", snap_path],
            capture_output=True, text=True
        )

        # Data de criacao a partir dos metadados do subvolume
        data = ""
        for linha in resultado.stdout.splitlines():
            if "Creation time" in linha:
                data = linha.split(":", 1)[1].strip()
                break

        marcador = " <- atual" if snap == versao_atual else ""
        print(f"  {snap}{marcador}")
        if data:
            print(f"    Criado em: {data}")
        print(f"    Caminho:   {snap_path}")
        print()