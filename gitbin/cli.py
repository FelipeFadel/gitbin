#!/usr/bin/env python3
"""
Comandos:
  gitbin init <arquivo.glb>   Inicializa um repositorio gitbin no diretorio atual
  gitbin save                 Salva uma nova versao do arquivo rastreado
  gitbin status               Mostra o que mudou desde o ultimo save
  gitbin log                  Lista o historico de versoes salvas
  gitbin checkout <versao>    Restaura uma versao anterior como estado atual
"""

import sys
import os

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    comando = sys.argv[1]

    if comando == "init":
        if len(sys.argv) < 3:
            print("Uso: gitbin init <arquivo.glb> [--size <tamanho>]")
            print("Exemplo: gitbin init modelo.glb --size 5G")
            sys.exit(1)

        tamanho = "5G"
        if "--size" in sys.argv:
            idx = sys.argv.index("--size")
            if idx + 1 >= len(sys.argv):
                print("Erro: --size requer um valor. Exemplo: --size 5G")
                sys.exit(1)
            tamanho = sys.argv[idx + 1]

        from gitbin.commands.init import cmd_init
        cmd_init(sys.argv[2], tamanho)

    elif comando == "save":
        from gitbin.commands.save import cmd_save
        cmd_save()

    elif comando == "status":
        from gitbin.commands.status import cmd_status
        cmd_status()

    elif comando == "log":
        from gitbin.commands.log import cmd_log
        cmd_log()

    elif comando == "checkout":
        if len(sys.argv) < 3:
            print("Como usar: gitbin checkout <versao>")
            print("Exemplo: gitbin checkout v0003")
            sys.exit(1)
        from gitbin.commands.checkout import cmd_checkout
        cmd_checkout(sys.argv[2])

    else:
        print(f"Comando desconhecido: {comando}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()