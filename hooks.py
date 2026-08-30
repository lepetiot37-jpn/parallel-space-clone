"""
Hook python-for-android (référencé par `p4a.hook` dans buildozer.spec).

L'installation d'un APK sur Android 7+ via Intent.ACTION_VIEW exige une
URI "content://" et non "file://". Cela nécessite un <provider> de type
androidx.core.content.FileProvider déclaré dans AndroidManifest.xml, ainsi
qu'un fichier de configuration res/xml/file_paths.xml.

Buildozer/python-for-android ne proposent pas (à la date d'écriture) une
option buildozer.spec dédiée pour ajouter un <provider> personnalisé : ce
hook patch donc directement l'AndroidManifest.xml généré, juste avant la
compilation de l'APK (étape `before_apk_build`).

⚠️ Ce mécanisme dépend de la structure interne générée par
python-for-android, qui peut changer d'une version à l'autre. Si le build
échoue à cette étape, vérifiez la version de p4a utilisée par le workflow
et adaptez le hook si nécessaire (voir README, section "Limitations").
"""

import os
import re
import shutil


FILE_PATHS_XML = """<?xml version="1.0" encoding="utf-8"?>
<paths xmlns:android="http://schemas.android.com/apk/res/android">
    <files-path name="imported_apks" path="imported_apks/" />
    <files-path name="icons" path="icons/" />
    <external-files-path name="external_files" path="." />
</paths>
"""

PROVIDER_TEMPLATE = """
        <provider
            android:name="androidx.core.content.FileProvider"
            android:authorities="{package}.fileprovider"
            android:exported="false"
            android:grantUriPermissions="true">
            <meta-data
                android:name="android.support.FILE_PROVIDER_PATHS"
                android:resource="@xml/file_paths" />
        </provider>
"""


def _find_manifest(build_dir):
    for root, _dirs, files in os.walk(build_dir):
        if "AndroidManifest.xml" in files and "app" in root:
            return os.path.join(root, "AndroidManifest.xml")
    for root, _dirs, files in os.walk(build_dir):
        if "AndroidManifest.xml" in files:
            return os.path.join(root, "AndroidManifest.xml")
    return None


def before_apk_build(hook_ctx):
    try:
        build_dir = hook_ctx.buildozer.platform_dir
        package_name = hook_ctx.buildozer.config.get("app", "package.domain") + "." + \
            hook_ctx.buildozer.config.get("app", "package.name")

        manifest_path = _find_manifest(build_dir)
        if not manifest_path:
            print("[hooks.py] AndroidManifest.xml introuvable, provider non injecté.")
            return

        # Ajoute res/xml/file_paths.xml à côté du manifeste.
        res_dir = os.path.join(os.path.dirname(manifest_path), "res", "xml")
        os.makedirs(res_dir, exist_ok=True)
        with open(os.path.join(res_dir, "file_paths.xml"), "w", encoding="utf-8") as f:
            f.write(FILE_PATHS_XML)

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = f.read()

        if "fileprovider" in manifest:
            return  # déjà patché

        provider_xml = PROVIDER_TEMPLATE.format(package=package_name)
        manifest = re.sub(r"</application>", provider_xml + "\n    </application>", manifest, count=1)

        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(manifest)

        print("[hooks.py] FileProvider injecté dans AndroidManifest.xml")
    except Exception as exc:
        print(f"[hooks.py] Échec de l'injection du FileProvider: {exc}")
