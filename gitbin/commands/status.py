#!/usr/bin/env python3
"""
commands/status.py
Implementa: gitbin status

Compara o arquivo GLB atual com o ultimo estado salvo
sem gravar nada em disco.
"""

import os

from gitbin import repo
from gitbin.glb import (parse_glb, extrair_buffer_views, calcular_hashes,
                        classificar)


def cmd_status():
    repo.assert_repo()
    config          = repo.ler_config()
    estado_anterior = repo.ler_estado()

    arquivo_glb = config["arquivo"]

    if not os.path.isfile(arquivo_glb):
        print(f"Erro: arquivo rastreado nao encontrado: {arquivo_glb}")
        raise SystemExit(1)

    if not estado_anterior:
        print("Nenhuma versao salva ainda. Execute 'gitbin save'.")
        return

    chunks    = parse_glb(arquivo_glb)
    segmentos = extrair_buffer_views(chunks)
    hashes    = calcular_hashes(segmentos)

    novos, modificados, reaproveitados, removidos, inalterados = \
        classificar(estado_anterior, hashes)

    versao_atual = f"v{config['versao_atual']:04d}"
    print(f"\nArquivo: {os.path.basename(arquivo_glb)}")
    print(f"Versao atual: {versao_atual}")
    print()

    if not novos and not modificados and not removidos and not reaproveitados:
        print("Nenhuma alteracao desde o ultimo save.")
        return

    tamanho_total = os.path.getsize(arquivo_glb)
    bytes_pendentes = sum(
        len(segmentos[int(i)]) for i in novos + modificados
    )
    economia = (1 - bytes_pendentes / tamanho_total) * 100

    if modificados:
        print(f"Modificadas ({len(modificados)}):")
        for idx_str in sorted(modificados, key=int):
            tamanho = len(segmentos[int(idx_str)])
            print(f"  bufferView_{int(idx_str):04d}  {tamanho:>10,} bytes")

    if novos:
        print(f"\nNovas ({len(novos)}):")
        for idx_str in sorted(novos, key=int):
            tamanho = len(segmentos[int(idx_str)])
            print(f"  bufferView_{int(idx_str):04d}  {tamanho:>10,} bytes")

    if removidos:
        print(f"\nRemovidas ({len(removidos)}):")
        for idx_str in sorted(removidos, key=int):
            print(f"  bufferView_{int(idx_str):04d}")

    if reaproveitados:
        print(f"\nReaproveitadas ({len(reaproveitados)}, mesmo conteudo em outro indice):")
        for idx_str in sorted(reaproveitados, key=int):
            print(f"  bufferView_{int(idx_str):04d} <- bufferView_{int(reaproveitados[idx_str]):04d}")

    print(f"\nInalteradas: {len(inalterados)} bufferViews")
    print(f"A gravar:    {bytes_pendentes / 1024 / 1024:.2f} MB")
    print(f"Economia:    {economia:.2f}%")