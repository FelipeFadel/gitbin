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

        # Exporta o arquivo GLB sobrescrevendo
        self.report({"INFO"}, "Exportando GLB...")
        bpy.ops.export_scene.gltf(
            filepath=glb_path,
            export_format="GLB",
            use_selection=False,
        )

        # Roda gitbin save
        sucesso, output = rodar_gitbin(["save"], cwd=pasta)
        props.ultimo_status = output

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

        # Exporta temporariamente para verificar o status
        tmp_path = glb_path + ".tmp.glb"
        bpy.ops.export_scene.gltf(
            filepath=tmp_path,
            export_format="GLB",
            use_selection=False,
        )

        # Substitui temporariamente o arquivo para rodar o status
        import shutil
        backup = glb_path + ".bak"
        shutil.copy2(glb_path, backup)
        shutil.copy2(tmp_path, glb_path)

        sucesso, output = rodar_gitbin(["status"], cwd=pasta)

        # Restaura o arquivo original
        shutil.copy2(backup, glb_path)
        os.remove(backup)
        os.remove(tmp_path)

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
            # Reimporta o arquivo restaurado no Blender
            bpy.ops.import_scene.gltf(filepath=glb_path)
            self.report({"INFO"}, f"Versao {versao} restaurada.")
        else:
            self.report({"ERROR"}, "Erro no checkout.")

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
