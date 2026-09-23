#!/usr/bin/env python3
"""
commands/log.py
Implementa: gitbin log

Lista todos os snapshots salvos com informacoes basicas.
"""

import os
import json

from gitbin import repo
from datetime import datetime


def cmd_log():
    repo.assert_repo()
    repo.garantir_montado()
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

        # Data gravada pelo save. Snapshots antigos nao tem meta.json:
        # usa o mtime da pasta, que fica proximo da hora do save.
        meta_path = os.path.join(snap_path, "meta.json")
        if os.path.isfile(meta_path):
            with open(meta_path, "r") as f:
                data = json.load(f).get("data", "")
        else:
            # O gltf.json e reescrito em todo save; a pasta so muda de
            # mtime quando arquivos sao criados ou apagados.
            ref = os.path.join(snap_path, "gltf.json")
            if not os.path.isfile(ref):
                ref = snap_path
            mtime = os.stat(ref).st_mtime
            data = "~" + datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")


        marcador = " <- atual" if snap == versao_atual else ""
        print(f"  {snap}{marcador}")
        if data:
            print(f"    Criado em: {data}")
        print(f"    Caminho:   {snap_path}")
        print()