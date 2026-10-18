bl_info = {
    "name": "gitbin",
    "author": "Felipe da Silva Fadel",
    "version": (0, 1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > gitbin",
    "description": "Versionamento diferencial de arquivos GLB com Btrfs CoW",
    "category": "Import-Export",
}

import bpy
import subprocess
import os
import json
import struct
import shutil
import hashlib
import tempfile
import numpy as np


def encontrar_gitbin():
    """Localiza o executavel gitbin no sistema."""
    resultado = subprocess.run(
        ["which", "gitbin"],
        capture_output=True, text=True
    )
    if resultado.returncode == 0:
        return resultado.stdout.strip()
    # Tenta o caminho do ambiente virtual padrao
    home = os.path.expanduser("~")
    candidatos = [
        os.path.join(home, "gitbin-env", "bin", "gitbin"),
        os.path.join(home, ".local", "bin", "gitbin"),
    ]
    for c in candidatos:
        if os.path.isfile(c):
            return c
    return None


def pasta_do_glb():
    """Retorna o diretorio do arquivo GLB aberto no Blender."""
    filepath = bpy.data.filepath
    if filepath:
        return os.path.dirname(filepath)
    # Tenta a partir do arquivo importado
    for img in bpy.data.images:
        if img.filepath:
            return os.path.dirname(bpy.path.abspath(img.filepath))
    return None


def rodar_gitbin(args, cwd=None):
    """Executa um comando gitbin e retorna (sucesso, output)."""
    gitbin = encontrar_gitbin()
    if not gitbin:
        return False, "gitbin nao encontrado. Instale com: pip install -e ~/gitbin"

    cmd = [gitbin] + args
    resultado = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd
    )
    output = resultado.stdout + resultado.stderr
    return resultado.returncode == 0, output.strip()


# Dimensao de cada tipo de atributo de malha, para ler com foreach_get
DIMENSOES = {
    "FLOAT": 1, "INT": 1, "INT8": 1, "BOOLEAN": 1,
    "FLOAT2": 2, "INT32_2D": 2, "INT16_2D": 2,
    "FLOAT_VECTOR": 3, "FLOAT_COLOR": 4, "BYTE_COLOR": 4,
    "QUATERNION": 4, "FLOAT4X4": 16,
}


def impressao_digital(me):
    """
    Hash de toda a geometria da malha (posicoes, topologia, UV, normais,
    materiais por face, shape keys). Selecao e visibilidade ficam de fora:
    entrar e sair do modo de edicao nao conta como alteracao.
    """
    h = hashlib.sha256()
    for a in sorted(me.attributes, key=lambda a: a.name):
        if a.name.startswith((".select", ".hide")):
            continue
        n = DIMENSOES.get(a.data_type)
        h.update(f"{a.name}:{a.domain}:{a.data_type}".encode())
        if n is None:
            continue
        if a.data_type in ("FLOAT2", "FLOAT_VECTOR"):
            chave = "vector"
        elif "COLOR" in a.data_type:
            chave = "color"
        else:
            chave = "value"
        if a.data_type == "BOOLEAN":
            tipo = bool
        elif a.data_type.startswith("FLOAT") or a.data_type == "QUATERNION" or "COLOR" in a.data_type:
            tipo = np.float32
        else:
            tipo = np.int32
        arr = np.empty(len(a.data) * n, dtype=tipo)
        a.data.foreach_get(chave, arr)
        h.update(arr.tobytes())

    inicio = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_start", inicio)
    h.update(inicio.tobytes())

    if me.shape_keys:
        for kb in me.shape_keys.key_blocks:
            co = np.empty(len(kb.data) * 3, dtype=np.float32)
            kb.data.foreach_get("co", co)
            h.update(kb.name.encode() + co.tobytes())
    return h.hexdigest()


def sha256_arquivo(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def ler_glb(path):
    """Devolve (json, bin) de um GLB. Versao minima do gitbin.glb.parse_glb."""
    with open(path, "rb") as f:
        dados = f.read()
    json_len = struct.unpack_from("<I", dados, 12)[0]
    gltf = json.loads(dados[20:20 + json_len].decode("utf-8").rstrip("\x00 "))
    return gltf, dados[20 + json_len:]


def escrever_glb(path, gltf, resto):
    """Grava um GLB trocando so o chunk JSON; o chunk BIN segue identico."""
    js = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + len(resto)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A))
        f.write(js)
        f.write(resto)


def limpar_cena():
    """Remove os objetos da cena e os dados que ficaram orfaos."""
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj)
    bpy.data.orphans_purge(do_recursive=True)


def marcar_malhas(meshes_gltf):
    """Guarda em cada malha do Blender o indice glTF e a impressao digital."""
    for j, m in enumerate(meshes_gltf):
        me = bpy.data.meshes.get(m.get("name", ""))
        if me is not None:
            me["gitbin_mesh"] = j
            me["gitbin_fp"] = impressao_digital(me)


def importar_marcado(context, glb_path):
    """
    Importa o GLB rastreado numa cena limpa, marcando cada malha com o indice
    da malha glTF de origem (via extras, que o importador vira propriedade
    customizada) e com a impressao digital da geometria importada. No save,
    as malhas com a mesma impressao digital reaproveitam os bytes originais.
    """
    limpar_cena()
    gltf, resto = ler_glb(glb_path)
    for j, m in enumerate(gltf.get("meshes", [])):
        m.setdefault("extras", {})["gitbin_mesh"] = j

    with tempfile.TemporaryDirectory() as tmp:
        marcado = os.path.join(tmp, "marcado.glb")
        escrever_glb(marcado, gltf, resto)
        bpy.ops.import_scene.gltf(filepath=marcado)

    for me in bpy.data.meshes:
        if "gitbin_mesh" in me:
            me["gitbin_fp"] = impressao_digital(me)
    context.scene.gitbin_props.base_sha = sha256_arquivo(glb_path)


def gerar_glb(context, glb_path, destino):
    """
    Exporta a cena e mescla com a versao base: malhas inalteradas desde o
    import (ou desde o ultimo save) voltam com os bytes originais.
    Retorna (sucesso, mensagem, meshes_gltf_exportadas).
    """
    props = context.scene.gitbin_props
    base_ok = (os.path.isfile(glb_path)
               and props.base_sha == sha256_arquivo(glb_path))

    with tempfile.TemporaryDirectory() as tmp:
        novo = os.path.join(tmp, "novo.glb")
        bpy.ops.export_scene.gltf(
            filepath=novo,
            export_format="GLB",
            use_selection=False,
            export_extras=True,
        )
        meshes = ler_glb(novo)[0].get("meshes", [])

        preservar = {}
        if base_ok:
            for j, m in enumerate(meshes):
                src = m.get("extras", {}).get("gitbin_mesh")
                me = bpy.data.meshes.get(m.get("name", ""))
                if src is not None and me is not None \
                        and me.get("gitbin_fp") == impressao_digital(me):
                    preservar[j] = src

        mapa = os.path.join(tmp, "preservar.json")
        with open(mapa, "w") as f:
            json.dump(preservar, f)

        if not base_ok:
            # Sem base valida (arquivo trocado por fora do Blender ou cena
            # nao importada pelo gitbin): nada a preservar, mescla consigo mesmo
            # so para limpar as marcas.
            glb_path = novo
        sucesso, output = rodar_gitbin(["mesclar", novo, glb_path, mapa, destino])

    aviso = "" if base_ok else "Cena sem base do gitbin: geometria exportada do zero.\n"
    return sucesso, aviso + output, meshes


class GITBIN_OT_save(bpy.types.Operator):
    """Exporta o arquivo GLB e salva uma nova versao no gitbin"""
    bl_idname = "gitbin.save"
    bl_label = "Save Version"

    def execute(self, context):
        props = context.scene.gitbin_props
        glb_path = bpy.path.abspath(props.glb_path)
        pasta = os.path.dirname(glb_path)

        if not glb_path or not os.path.isdir(pasta):
            self.report({"ERROR"}, "Caminho do arquivo GLB invalido.")
            return {"CANCELLED"}

        if not os.path.isdir(os.path.join(pasta, ".gitbin")):
            self.report({"ERROR"}, "Nenhum repositorio gitbin encontrado nesta pasta.")
            return {"CANCELLED"}

        with tempfile.TemporaryDirectory() as tmp:
            saida = os.path.join(tmp, "saida.glb")
            sucesso, output, meshes = gerar_glb(context, glb_path, saida)
            if not sucesso:
                props.ultimo_status = output
                self.report({"ERROR"}, "Falha ao gerar o GLB.")
                return {"CANCELLED"}
            shutil.copyfile(saida, glb_path)

        # O arquivo salvo vira a nova base: reindexa as malhas pela ordem
        # do export e atualiza as impressoes digitais.
        marcar_malhas(meshes)
        props.base_sha = sha256_arquivo(glb_path)

        sucesso, saida_save = rodar_gitbin(["save"], cwd=pasta)
        props.ultimo_status = output + "\n" + saida_save

        if sucesso:
            self.report({"INFO"}, "Versao salva com sucesso.")
        else:
            self.report({"WARNING"}, "gitbin save retornou erro.")

        return {"FINISHED"}


class GITBIN_OT_status(bpy.types.Operator):
    """Mostra o que mudou desde o ultimo save"""
    bl_idname = "gitbin.status"
    bl_label = "Status"

    def execute(self, context):
        props = context.scene.gitbin_props
        glb_path = bpy.path.abspath(props.glb_path)
        pasta = os.path.dirname(glb_path)

        if not os.path.isdir(os.path.join(pasta, ".gitbin")):
            self.report({"ERROR"}, "Nenhum repositorio gitbin encontrado.")
            return {"CANCELLED"}

        with tempfile.TemporaryDirectory() as tmp:
            gerado = os.path.join(tmp, "gerado.glb")
            sucesso, output, _ = gerar_glb(context, glb_path, gerado)
            if not sucesso:
                props.ultimo_status = output
                return {"CANCELLED"}

            # Troca o arquivo so durante o status e restaura o original
            backup = os.path.join(tmp, "original.glb")
            shutil.copy2(glb_path, backup)
            shutil.copy2(gerado, glb_path)
            try:
                sucesso, output = rodar_gitbin(["status"], cwd=pasta)
            finally:
                shutil.copy2(backup, glb_path)

        props.ultimo_status = output
        return {"FINISHED"}


class GITBIN_OT_checkout(bpy.types.Operator):
    """Restaura uma versao anterior"""
    bl_idname = "gitbin.checkout"
    bl_label = "Checkout"

    def execute(self, context):
        props = context.scene.gitbin_props
        glb_path = bpy.path.abspath(props.glb_path)
        pasta = os.path.dirname(glb_path)
        versao = props.versao_checkout.strip()

        if not versao:
            self.report({"ERROR"}, "Informe o numero da versao.")
            return {"CANCELLED"}

        if not os.path.isdir(os.path.join(pasta, ".gitbin")):
            self.report({"ERROR"}, "Nenhum repositorio gitbin encontrado.")
            return {"CANCELLED"}

        sucesso, output = rodar_gitbin(["checkout", versao], cwd=pasta)
        props.ultimo_status = output

        if sucesso:
            # Reimporta o arquivo restaurado numa cena limpa
            importar_marcado(context, glb_path)
            self.report({"INFO"}, f"Versao {versao} restaurada.")
        else:
            self.report({"ERROR"}, "Erro no checkout.")

        return {"FINISHED"}


class GITBIN_OT_import(bpy.types.Operator):
    """Abre o GLB rastreado numa cena limpa, pronto para versionar"""
    bl_idname = "gitbin.import_glb"
    bl_label = "Importar"

    def execute(self, context):
        glb_path = bpy.path.abspath(context.scene.gitbin_props.glb_path)
        if not os.path.isfile(glb_path):
            self.report({"ERROR"}, "Caminho do arquivo GLB invalido.")
            return {"CANCELLED"}
        importar_marcado(context, glb_path)
        self.report({"INFO"}, "GLB importado.")
        return {"FINISHED"}


class GITBIN_OT_log(bpy.types.Operator):
    """Lista o historico de versoes"""
    bl_idname = "gitbin.log"
    bl_label = "Log"

    def execute(self, context):
        props = context.scene.gitbin_props
        glb_path = bpy.path.abspath(props.glb_path)
        pasta = os.path.dirname(glb_path)

        sucesso, output = rodar_gitbin(["log"], cwd=pasta)
        props.ultimo_status = output
        return {"FINISHED"}


class GitbinProperties(bpy.types.PropertyGroup):
    glb_path: bpy.props.StringProperty(
        name="Arquivo GLB",
        description="Caminho do arquivo GLB rastreado pelo gitbin",
        default="",
        subtype="FILE_PATH",
    )
    versao_checkout: bpy.props.StringProperty(
        name="Versao",
        description="Numero da versao para restaurar (ex: v0001 ou 1)",
        default="v0001",
    )
    ultimo_status: bpy.props.StringProperty(
        name="Status",
        default="",
    )
    base_sha: bpy.props.StringProperty(
        name="Base",
        description="SHA-256 do GLB que a cena representa (importado ou salvo)",
        default="",
    )


class GITBIN_PT_panel(bpy.types.Panel):
    bl_label = "gitbin"
    bl_idname = "GITBIN_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "gitbin"

    def draw(self, context):
        layout = self.layout
        props = context.scene.gitbin_props

        # Arquivo rastreado
        layout.label(text="Arquivo GLB:")
        layout.prop(props, "glb_path", text="")
        layout.operator("gitbin.import_glb", icon="IMPORT")
        layout.separator()

        # Botoes principais
        row = layout.row(align=True)
        row.operator("gitbin.save", icon="FILE_TICK")
        row.operator("gitbin.status", icon="INFO")

        row2 = layout.row(align=True)
        row2.operator("gitbin.log", icon="SEQUENCE")

        layout.separator()

        # Checkout
        layout.label(text="Restaurar versao:")
        layout.prop(props, "versao_checkout", text="")
        layout.operator("gitbin.checkout", icon="LOOP_BACK")

        layout.separator()

        # Output do ultimo comando
        if props.ultimo_status:
            layout.label(text="Ultimo comando:")
            box = layout.box()
            for linha in props.ultimo_status.split("\n")[:20]:
                box.label(text=linha)


classes = [
    GitbinProperties,
    GITBIN_OT_save,
    GITBIN_OT_status,
    GITBIN_OT_checkout,
    GITBIN_OT_import,
    GITBIN_OT_log,
    GITBIN_PT_panel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gitbin_props = bpy.props.PointerProperty(
        type=GitbinProperties
    )


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.gitbin_props


if __name__ == "__main__":
    register()
