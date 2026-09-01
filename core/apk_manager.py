"""
Toutes les interactions avec le système Android passent ici, et
UNIQUEMENT par des mécanismes officiels :

- Sélection de fichier : Storage Access Framework via plyer.filechooser
  (ACTION_OPEN_DOCUMENT / ACTION_GET_CONTENT), pas d'accès direct au
  système de fichiers.
- Lecture des métadonnées d'un APK : android.content.pm.PackageManager
  (getPackageArchiveInfo), API publique du SDK Android.
- Installation : Intent.ACTION_VIEW avec le type MIME officiel
  "application/vnd.android.package-archive", délégué à l'installateur
  système (PackageInstaller UI). L'app ne s'auto-installe jamais et ne
  contourne jamais la confirmation utilisateur.
- Ouverture d'une app installée : PackageManager.getLaunchIntentForPackage,
  puis Context.startActivity — l'API standard utilisée par les launchers
  Android.

Sur desktop (platform != "android"), ce module fonctionne en mode "stub"
pour permettre de tester l'interface sans APK réels.
"""

import os
import uuid
from kivy.utils import platform


class ApkManager:
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir
        self.imported_apk_dir = os.path.join(storage_dir, "imported_apks")
        self.icons_dir = os.path.join(storage_dir, "icons")
        os.makedirs(self.imported_apk_dir, exist_ok=True)
        os.makedirs(self.icons_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Sélection d'un fichier APK (Storage Access Framework, officiel)
    # ------------------------------------------------------------------
    def pick_apk_file(self, callback):
        """Ouvre le sélecteur de fichiers officiel Android (SAF) filtré sur
        les APK. `callback(local_path_or_None, error=None)` est appelé avec
        le chemin d'une copie locale (nécessaire car l'URI SAF n'est pas un
        chemin de fichier classique), ou un message d'erreur explicite si
        quelque chose a échoué (au lieu d'échouer silencieusement).
        """
        import traceback

        try:
            from plyer import filechooser
        except Exception:
            callback(None, error="import plyer.filechooser:\n" + traceback.format_exc())
            return

        def _on_selection(selection):
            if not selection:
                callback(None, error=None)
                return
            source = selection[0]
            try:
                local_path = self._materialize_apk(source)
            except Exception:
                callback(None, error="_materialize_apk:\n" + traceback.format_exc())
                return
            if local_path is None:
                callback(None, error=f"Copie du fichier échouée pour: {source}")
                return
            callback(local_path, error=None)

        try:
            filechooser.open_file(
                on_selection=_on_selection,
                filters=[["APK", "*.apk"]],
            )
        except Exception:
            callback(None, error="filechooser.open_file:\n" + traceback.format_exc())

    def _materialize_apk(self, source_uri_or_path):
        """Copie le fichier sélectionné (souvent un content:// URI sur
        Android) vers le stockage privé de l'application, afin de pouvoir
        le relire de façon fiable (PackageManager, FileProvider, etc.).
        """
        dest_path = os.path.join(self.imported_apk_dir, f"{uuid.uuid4().hex}.apk")

        if platform == "android" and str(source_uri_or_path).startswith("content://"):
            try:
                from jnius import autoclass, cast

                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                Uri = autoclass("android.net.Uri")
                activity = PythonActivity.mActivity
                resolver = activity.getContentResolver()
                uri = Uri.parse(source_uri_or_path)
                input_stream = resolver.openInputStream(uri)

                buffer_size = 1024 * 64
                java_buffer = autoclass("java.lang.reflect.Array").newInstance(
                    autoclass("java.lang.Byte").TYPE, buffer_size
                )

                with open(dest_path, "wb") as out_file:
                    while True:
                        read = input_stream.read(java_buffer)
                        if read == -1:
                            break
                        chunk = bytes([java_buffer[i] & 0xFF for i in range(read)])
                        out_file.write(chunk)
                input_stream.close()
                return dest_path
            except Exception:
                return None
        else:
            # Chemin de fichier classique (desktop, ou déjà un chemin local).
            try:
                import shutil

                shutil.copyfile(source_uri_or_path, dest_path)
                return dest_path
            except Exception:
                return None

    # ------------------------------------------------------------------
    # Lecture des métadonnées de l'APK (PackageManager, officiel)
    # ------------------------------------------------------------------
    def read_apk_info(self, apk_path):
        if platform != "android":
            # Mode stub pour développement/desktop.
            return {
                "label": os.path.basename(apk_path),
                "package_name": f"stub.{uuid.uuid4().hex[:8]}",
                "version_name": "1.0",
                "icon_path": "",
            }

        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            PackageManager = autoclass("android.content.pm.PackageManager")
            activity = PythonActivity.mActivity
            pm = activity.getPackageManager()

            package_info = pm.getPackageArchiveInfo(apk_path, PackageManager.GET_ACTIVITIES)
            if package_info is None:
                return None

            app_info = package_info.applicationInfo
            # Nécessaire pour que le PackageManager puisse charger l'icône
            # depuis un APK qui n'est pas encore installé.
            app_info.sourceDir = apk_path
            app_info.publicSourceDir = apk_path

            label = str(pm.getApplicationLabel(app_info))
            package_name = str(package_info.packageName)
            version_name = str(package_info.versionName) if package_info.versionName else ""

            icon_path = self._extract_icon(pm, app_info, package_name)

            return {
                "label": label,
                "package_name": package_name,
                "version_name": version_name,
                "icon_path": icon_path or "",
            }
        except Exception:
            return None

    def _extract_icon(self, pm, app_info, package_name):
        """Convertit le Drawable de l'icône en PNG lisible par Kivy."""
        try:
            from jnius import autoclass

            Bitmap = autoclass("android.graphics.Bitmap")
            BitmapConfig = autoclass("android.graphics.Bitmap$Config")
            CompressFormat = autoclass("android.graphics.Bitmap$CompressFormat")
            Canvas = autoclass("android.graphics.Canvas")
            FileOutputStream = autoclass("java.io.FileOutputStream")

            drawable = app_info.loadIcon(pm)
            width = drawable.getIntrinsicWidth()
            height = drawable.getIntrinsicHeight()
            width = width if width > 0 else 128
            height = height if height > 0 else 128

            bitmap = Bitmap.createBitmap(width, height, BitmapConfig.ARGB_8888)
            canvas = Canvas(bitmap)
            drawable.setBounds(0, 0, width, height)
            drawable.draw(canvas)

            icon_path = os.path.join(self.icons_dir, f"{package_name}.png")
            fos = FileOutputStream(icon_path)
            bitmap.compress(CompressFormat.PNG, 100, fos)
            fos.flush()
            fos.close()
            return icon_path
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Installation via l'installateur officiel d'Android
    # ------------------------------------------------------------------
    def install_apk(self, apk_path):
        if platform != "android":
            print(f"[stub] installation simulée de {apk_path}")
            return True

        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
            FileProviderCls = autoclass("androidx.core.content.FileProvider")
            File = autoclass("java.io.File")

            activity = PythonActivity.mActivity
            package_name = activity.getPackageName()
            authority = f"{package_name}.fileprovider"

            file_obj = File(apk_path)
            uri = FileProviderCls.getUriForFile(activity, authority, file_obj)

            intent = Intent(Intent.ACTION_VIEW)
            intent.setDataAndType(uri, "application/vnd.android.package-archive")
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            activity.startActivity(intent)
            return True
        except Exception as exc:
            print(f"Installation impossible: {exc}")
            return False

    # ------------------------------------------------------------------
    # Liste des applications déjà installées (PackageManager, officiel)
    # ------------------------------------------------------------------
    def list_installed_apps(self, include_system=False):
        """Retourne les applications lançables installées sur l'appareil,
        sous la forme d'une liste de dicts {label, package_name, icon_path}.
        Utilise exclusivement PackageManager (API publique), pas d'accès
        au système de fichiers d'autres applications.
        """
        if platform != "android":
            return []

        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            PackageManager = autoclass("android.content.pm.PackageManager")
            Intent = autoclass("android.content.Intent")
            activity = PythonActivity.mActivity
            pm = activity.getPackageManager()
            own_package = activity.getPackageName()

            ApplicationInfoFlags = PackageManager.GET_META_DATA
            installed = pm.getInstalledApplications(ApplicationInfoFlags)

            results = []
            count = installed.size()
            for i in range(count):
                app_info = installed.get(i)
                package_name = str(app_info.packageName)
                if package_name == own_package:
                    continue

                # Ne garder que les applis "lançables" (avec une icône dans
                # le launcher), pour éviter de lister des services/libs
                # système sans intérêt pour l'utilisateur.
                launch_intent = pm.getLaunchIntentForPackage(package_name)
                if launch_intent is None:
                    continue

                is_system = (app_info.flags & 1) != 0  # FLAG_SYSTEM
                if is_system and not include_system:
                    continue

                label = str(pm.getApplicationLabel(app_info))
                cached_icon = os.path.join(self.icons_dir, f"{package_name}.png")
                if os.path.exists(cached_icon):
                    icon_path = cached_icon
                else:
                    icon_path = self._extract_icon(pm, app_info, package_name)

                results.append({
                    "name": label,
                    "package_name": package_name,
                    "version_name": "",
                    "icon_path": icon_path or "",
                    "apk_path": None,
                    "installed": True,
                })

            results.sort(key=lambda e: e["name"].lower())
            return results
        except Exception:
            return []

    # ------------------------------------------------------------------
    # État / ouverture d'une application déjà installée
    # ------------------------------------------------------------------
    def is_package_installed(self, package_name):
        if platform != "android":
            return False
        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            pm = activity.getPackageManager()
            pm.getPackageInfo(package_name, 0)
            return True
        except Exception:
            return False

    def launch_app(self, package_name):
        if platform != "android":
            print(f"[stub] ouverture simulée de {package_name}")
            return True
        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            pm = activity.getPackageManager()
            intent = pm.getLaunchIntentForPackage(package_name)
            if intent is None:
                return False
            activity.startActivity(intent)
            return True
        except Exception:
            return False
