"""
Parallel Space Clone
=====================
Application Android (Kivy) permettant de gérer un espace d'applications :
- importer des APK depuis le stockage,
- afficher nom / icône / version,
- installer via l'installateur officiel d'Android,
- ouvrir une application déjà installée,
- gérer la bibliothèque (ajout, suppression, renommage).

Toutes les opérations Android (installation, ouverture d'appli, permissions)
passent exclusivement par les mécanismes officiels du système
(PackageManager, Intent.ACTION_VIEW / ACTION_INSTALL_PACKAGE,
Intent.ACTION_MANAGE_UNKNOWN_APP_SOURCES, startActivity...).

Aucune installation silencieuse, aucun contournement du système n'est
implémenté : l'utilisateur doit toujours confirmer l'installation via
l'écran natif d'Android.
"""

import os
from kivy.app import App
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.properties import ListProperty, StringProperty, BooleanProperty
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from core.storage import LibraryStorage
from core.apk_manager import ApkManager
from core.permissions import ensure_runtime_permissions, open_install_unknown_apps_settings

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Thème sombre global
# ---------------------------------------------------------------------------
Window.clearcolor = (0.07, 0.07, 0.09, 1)

COLORS = {
    "bg": (0.07, 0.07, 0.09, 1),
    "surface": (0.12, 0.12, 0.15, 1),
    "surface_light": (0.17, 0.17, 0.21, 1),
    "accent": (0.35, 0.55, 1, 1),
    "text": (0.92, 0.92, 0.95, 1),
    "text_dim": (0.6, 0.6, 0.65, 1),
    "danger": (0.9, 0.3, 0.3, 1),
}


def notify(title, message):
    """Popup simple pour retour utilisateur (succès / erreur)."""
    content = BoxLayout(orientation="vertical", padding=16, spacing=10)
    content.add_widget(Label(text=message, color=COLORS["text"]))
    popup = Popup(
        title=title,
        content=content,
        size_hint=(0.85, 0.35),
        separator_color=COLORS["accent"],
    )
    popup.open()
    return popup


def _make_button(text, color):
    from kivy.uix.button import Button
    return Button(text=text, background_normal="", background_color=color, color=COLORS["text"])


class AppCardWidget(BoxLayout):
    """Représente une application importée dans la grille."""
    app_name = StringProperty("")
    package_name = StringProperty("")
    version_name = StringProperty("")
    icon_path = StringProperty("")
    installed = BooleanProperty(False)

    def animate_press(self):
        anim = Animation(opacity=0.6, duration=0.08) + Animation(opacity=1, duration=0.12)
        anim.start(self)


class LibraryScreen(Screen):
    apps = ListProperty([])

    def on_pre_enter(self, *_args):
        Clock.schedule_once(lambda *_: self.refresh_apps(), 0)

    def refresh_apps(self):
        app = App.get_running_app()
        entries = app.storage.get_all()
        # Met à jour le statut "installé" via PackageManager officiel.
        for entry in entries:
            entry["installed"] = app.apk_manager.is_package_installed(entry["package_name"])
        self.apps = entries

    def on_apps(self, _instance, entries):
        """Reconstruit la grille à chaque mise à jour de la bibliothèque."""
        grid = self.ids.get("apps_grid")
        if grid is None:
            return
        grid.clear_widgets()
        for entry in entries:
            card = AppCardWidget(
                app_name=entry.get("name", ""),
                package_name=entry.get("package_name", ""),
                version_name=entry.get("version_name", ""),
                icon_path=entry.get("icon_path", ""),
                installed=entry.get("installed", False),
            )
            grid.add_widget(card)

    def open_options(self, package_name, current_name):
        """Popup officiel Kivy (pas Android) pour renommer / supprimer."""
        from kivy.uix.textinput import TextInput

        content = BoxLayout(orientation="vertical", padding=16, spacing=10)
        name_input = TextInput(text=current_name, multiline=False, size_hint_y=None, height=40)
        content.add_widget(Label(text="Nom de l'application", color=COLORS["text"], size_hint_y=None, height=24))
        content.add_widget(name_input)

        buttons = BoxLayout(size_hint_y=None, height=44, spacing=10)
        rename_btn = _make_button("Renommer", COLORS["accent"])
        delete_btn = _make_button("Supprimer", COLORS["danger"])
        close_btn = _make_button("Fermer", COLORS["surface_light"])
        buttons.add_widget(rename_btn)
        buttons.add_widget(delete_btn)
        buttons.add_widget(close_btn)
        content.add_widget(buttons)

        popup = Popup(title=current_name, content=content, size_hint=(0.85, 0.45))

        def do_rename(*_a):
            self.rename_app(package_name, name_input.text)
            popup.dismiss()

        def do_delete(*_a):
            self.remove_app(package_name)
            popup.dismiss()

        rename_btn.bind(on_release=do_rename)
        delete_btn.bind(on_release=do_delete)
        close_btn.bind(on_release=lambda *_a: popup.dismiss())
        popup.open()

    def import_apk(self):
        app = App.get_running_app()
        app.apk_manager.pick_apk_file(self.on_apk_picked)

    def on_apk_picked(self, apk_path):
        if not apk_path:
            return
        app = App.get_running_app()
        info = app.apk_manager.read_apk_info(apk_path)
        if info is None:
            notify("Erreur", "Impossible de lire les informations de cet APK.")
            return
        app.storage.add_app(
            name=info["label"],
            package_name=info["package_name"],
            version_name=info["version_name"],
            apk_path=apk_path,
            icon_path=info.get("icon_path", ""),
        )
        self.refresh_apps()
        notify("Import réussi", f"{info['label']} a été ajouté à la bibliothèque.")

    def install_app(self, package_name):
        app = App.get_running_app()
        entry = app.storage.get_by_package(package_name)
        if not entry:
            return
        ok = app.apk_manager.install_apk(entry["apk_path"])
        if not ok:
            notify(
                "Installation impossible",
                "Autorisez d'abord \u00ab Installer des applications inconnues \u00bb "
                "pour cette application dans les paramètres Android.",
            )
            open_install_unknown_apps_settings()

    def open_app(self, package_name):
        app = App.get_running_app()
        ok = app.apk_manager.launch_app(package_name)
        if not ok:
            notify("Introuvable", "Cette application n'est pas (ou plus) installée.")

    def rename_app(self, package_name, new_name):
        app = App.get_running_app()
        if new_name.strip():
            app.storage.rename_app(package_name, new_name.strip())
            self.refresh_apps()

    def remove_app(self, package_name):
        app = App.get_running_app()
        app.storage.remove_app(package_name)
        self.refresh_apps()


class ParallelSpaceApp(App):
    title = "Parallel Space Clone"

    def build(self):
        self.storage = LibraryStorage(
            db_path=os.path.join(self.user_data_dir, "library.json"),
            icons_dir=os.path.join(self.user_data_dir, "icons"),
        )
        self.apk_manager = ApkManager(storage_dir=self.user_data_dir)

        Builder.load_file(os.path.join(BASE_DIR, "ui", "appcard.kv"))
        Builder.load_file(os.path.join(BASE_DIR, "ui", "library.kv"))

        sm = ScreenManager(transition=FadeTransition(duration=0.18))
        sm.add_widget(LibraryScreen(name="library"))
        return sm

    def on_start(self):
        # Demande des permissions Android nécessaires (stockage, installation
        # de paquets) via les API officielles au premier lancement.
        ensure_runtime_permissions()


if __name__ == "__main__":
    ParallelSpaceApp().run()
