"""
Demande des permissions Android nécessaires, uniquement via les API
officielles (android.permissions / Settings intents). Ne fait rien sur
les plateformes non-Android (permet de tester l'UI sur desktop).
"""

from kivy.utils import platform


def ensure_runtime_permissions():
    """Demande les permissions de stockage nécessaires pour lire les APK
    sélectionnés par l'utilisateur, via l'API officielle android.permissions.
    """
    if platform != "android":
        return
    try:
        from android.permissions import request_permissions, Permission

        perms = [
            Permission.READ_EXTERNAL_STORAGE,
            Permission.WRITE_EXTERNAL_STORAGE,
        ]
        # REQUEST_INSTALL_PACKAGES est une permission "normale" déclarée
        # dans le manifeste ; elle n'a pas besoin d'être demandée à
        # l'exécution, mais l'utilisateur doit activer "Installer des
        # applications inconnues" pour CETTE app depuis les paramètres
        # système (mécanisme officiel géré par open_install_unknown_apps_settings).
        request_permissions(perms)
    except Exception:
        # Selon la version d'Android/permissions déjà accordées, l'appel
        # peut échouer silencieusement ; ce n'est pas bloquant pour l'UI.
        pass


def open_install_unknown_apps_settings():
    """Ouvre l'écran système officiel permettant à l'utilisateur d'autoriser
    l'app à installer des paquets inconnus (Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES).
    C'est le mécanisme standard requis depuis Android 8 (API 26+).
    """
    if platform != "android":
        return
    try:
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        Settings = autoclass("android.provider.Settings")
        Uri = autoclass("android.net.Uri")

        activity = PythonActivity.mActivity
        package_name = activity.getPackageName()

        intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES)
        intent.setData(Uri.parse("package:" + package_name))
        activity.startActivity(intent)
    except Exception:
        pass
