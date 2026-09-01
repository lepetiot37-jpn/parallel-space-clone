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
from kivy.uix.behaviors import ButtonBehavior

from core.storage import LibraryStorage
from core.apk_manager import ApkManager
from core.permissions import ensure_runtime_permissions, open_install_unknown_apps_settings

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Thème clair (proche de l'app Parallel Space originale)
# ---------------------------------------------------------------------------
Window.clearcolor = (0.97, 0.97, 0.98, 1)

COLORS = {
    "bg": (0.97, 0.97, 0.98, 1),
    "surface": (1, 1, 1, 1),
    "surface_light": (0.90, 0.90, 0.93, 1),
    "header": (0.31, 0.38, 0.55, 1),
    "accent": (0.25, 0.45, 0.95, 1),
    "text": (0.12, 0.12, 0.14, 1),
    "text_on_header": (1, 1, 1, 1),
    "text_dim": (0.45, 0.45, 0.5, 1),
    "danger": (0.85, 0.25, 0.25, 1),
}


def notify(title, message):
    """Popup simple pour retour utilisateur (succès / erreur / traceback)."""
    from kivy.uix.scrollview import ScrollView
    from kivy.graphics import Color, Rectangle

    content = BoxLayout(orientation="vertical", padding=16, spacing=10)
    with content.canvas.before:
        Color(*COLORS["surface"])
        rect = Rectangle(pos=content.pos, size=content.size)
    content.bind(pos=lambda *_: setattr(rect, "pos", content.pos))
    content.bind(size=lambda *_: setattr(rect, "size", content.size))
    label = Label(
        text=message,
        color=COLORS["text"],
        size_hint_y=None,
        halign="left",
        valign="top",
        font_size="12sp",
    )
    label.bind(width=lambda *_: setattr(label, "text_size", (label.width, None)))
    label.bind(texture_size=lambda *_: setattr(label, "height", label.texture_size[1]))
    scroll = ScrollView()
    scroll.add_widget(label)
    content.add_widget(scroll)

    popup = Popup(
        title=title,
        content=content,
        size_hint=(0.9, 0.6),
        separator_color=COLORS["accent"],
    )
    popup.open()
    return popup


def _make_button(text, color):
    from kivy.uix.button import Button
    return Button(text=text, background_normal="", background_color=color, color=COLORS["text"])


class AppCardWidget(ButtonBehavior, BoxLayout):
    """Représente une application (installée ou importée) dans la grille."""
    app_name = StringProperty("")
    package_name = StringProperty("")
    version_name = StringProperty("")
    icon_path = StringProperty("")
    installed = BooleanProperty(False)

    def animate_press(self):
        anim = Animation(opacity=0.6, duration=0.08) + Animation(opacity=1, duration=0.12)
        anim.start(self)

    def on_release(self, *_args):
        """Tap sur la carte entière : ouvre si installée, sinon installe."""
        screen = App.get_running_app().root.get_screen("library")
        if self.installed:
            screen.open_app(self.package_name)
        else:
            screen.install_app(self.package_name)


class AddAppCardWidget(ButtonBehavior, BoxLayout):
    """Tuile finale de la grille : \u00ab Ajouter une App \u00bb (import APK)."""
    pass


class LibraryScreen(Screen):
    apps = ListProperty([])

    def on_pre_enter(self, *_args):
        Clock.schedule_once(lambda *_: self.refresh_apps(), 0)

    def refresh_apps(self):
        app = App.get_running_app()

        # 1) Toutes les applications déjà installées sur l'appareil
        #    (PackageManager), comme dans l'app Parallel Space originale.
        by_package = {}
        for entry in app.apk_manager.list_installed_apps():
            by_package[entry["package_name"]] = entry

        # 2) Les APK importés manuellement : s'ils sont déjà installés, on
        #    garde le nom personnalisé éventuel (renommage) ; sinon on les
        #    affiche avec le bouton "Installer".
        for stored in app.storage.get_all():
            pkg = stored["package_name"]
            if pkg in by_package:
                by_package[pkg]["name"] = stored.get("name") or by_package[pkg]["name"]
                by_package[pkg]["apk_path"] = stored.get("apk_path")
            else:
                stored["installed"] = False
                by_package[pkg] = stored

        self.apps = sorted(by_package.values(), key=lambda e: e.get("name", "").lower())

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
        # Tuile finale "Ajouter une App", toujours en dernier dans la grille.
        add_tile = AddAppCardWidget()
        add_tile.bind(on_release=lambda *_a: self.import_apk())
        grid.add_widget(add_tile)

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

    def on_apk_picked(self, apk_path, error=None):
        if error:
            # Popup avec le détail technique complet (affiché en <300
            # caractères pour rester lisible, le reste comptera pour le
            # debug si besoin de zoomer/scroller dans le popup).
            notify("Erreur import APK", error[:600])
            return
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
