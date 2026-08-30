[app]

title = Parallel Space Clone
package.name = parallelspaceclone
package.domain = org.example

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,xml,json

version = 0.1.0

requirements = python3==3.11.9,kivy==2.3.0,pyjnius,plyer,pillow,android

# Icône / écran de démarrage (facultatif : ajoutez vos fichiers dans assets/)
icon.filename = %(source.dir)s/assets/default_icon.png

orientation = portrait
fullscreen = 0

[android]

# API cible / minimale
android.api = 34
android.minapi = 24
android.ndk = 25b
android.build_tools_version = 34.0.0

android.archs = arm64-v8a, armeabi-v7a

# Permissions officielles nécessaires :
# - lire/écrire le stockage pour copier l'APK sélectionné par l'utilisateur
# - REQUEST_INSTALL_PACKAGES pour pouvoir déclencher l'installateur système
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,REQUEST_INSTALL_PACKAGES,QUERY_ALL_PACKAGES

# AndroidX est requis pour androidx.core.content.FileProvider
android.enable_androidx = True
android.gradle_dependencies = androidx.core:core:1.12.0

# Hook exécuté par python-for-android avant la compilation de l'APK :
# il injecte le <provider> FileProvider nécessaire à l'installation
# d'APK sur Android 7+ (voir hooks.py).
p4a.hook = %(source.dir)s/hooks.py

android.allow_backup = True
android.presplash_color = #121218

# Empêche la mise en cache d'une ancienne configuration entre deux builds CI
android.accept_sdk_license = True

[buildozer]

log_level = 2
warn_on_root = 1
