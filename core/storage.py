"""
Gestion de la bibliothèque d'applications importées.

Les métadonnées (nom, package, version, chemin de l'APK, icône extraite)
sont persistées dans un fichier JSON local à l'application
(App.user_data_dir), qui est le seul emplacement où l'app écrit sans
permission particulière sur Android.
"""

import json
import os
import threading


class LibraryStorage:
    def __init__(self, db_path, icons_dir):
        self.db_path = db_path
        self.icons_dir = icons_dir
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(self.icons_dir, exist_ok=True)
        if not os.path.exists(self.db_path):
            self._write([])

    # ------------------------------------------------------------------
    # I/O bas niveau
    # ------------------------------------------------------------------
    def _read(self):
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write(self, entries):
        with self._lock:
            tmp_path = self.db_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.db_path)

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------
    def get_all(self):
        return self._read()

    def get_by_package(self, package_name):
        for entry in self._read():
            if entry["package_name"] == package_name:
                return entry
        return None

    def add_app(self, name, package_name, version_name, apk_path, icon_path=""):
        entries = self._read()
        # Remplace une éventuelle entrée existante pour le même package
        entries = [e for e in entries if e["package_name"] != package_name]
        entries.append(
            {
                "name": name,
                "package_name": package_name,
                "version_name": version_name,
                "apk_path": apk_path,
                "icon_path": icon_path,
            }
        )
        self._write(entries)

    def remove_app(self, package_name):
        entries = self._read()
        target = next((e for e in entries if e["package_name"] == package_name), None)
        entries = [e for e in entries if e["package_name"] != package_name]
        self._write(entries)
        # Nettoyage best-effort des fichiers associés (APK importé, icône).
        if target:
            for path in (target.get("apk_path"), target.get("icon_path")):
                if path and os.path.exists(path) and path.startswith(self.icons_dir):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    def rename_app(self, package_name, new_name):
        entries = self._read()
        for entry in entries:
            if entry["package_name"] == package_name:
                entry["name"] = new_name
        self._write(entries)
