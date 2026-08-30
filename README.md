# Parallel Space Clone (Kivy)

Application Android inspirée de *Parallel Space* : elle permet d'importer
des fichiers APK depuis le stockage du téléphone, d'afficher leur nom /
icône / version, de déclencher leur installation via l'installateur
officiel d'Android, d'ouvrir les applications déjà installées, et de
gérer cette bibliothèque (ajout, suppression, renommage).

**Important : ce projet n'utilise que des mécanismes officiels d'Android**
(`PackageManager`, `Intent.ACTION_VIEW` + `PackageInstaller` système,
`Intent.ACTION_MANAGE_UNKNOWN_APP_SOURCES`, Storage Access Framework via
`plyer.filechooser`). Aucune installation silencieuse ni contournement
des confirmations utilisateur n'est implémenté.

## Structure du projet

```
parallel_space_clone/
├── main.py                  # Point d'entrée, écrans, logique UI
├── core/
│   ├── apk_manager.py        # Import / lecture / installation / ouverture d'APK
│   ├── storage.py            # Bibliothèque persistée en JSON
│   └── permissions.py        # Demande de permissions (API officielles)
├── ui/
│   ├── library.kv             # Écran principal (grille + barre du haut)
│   └── appcard.kv             # Widget "carte" d'une application
├── assets/
│   └── default_icon.png      # Icône par défaut
├── hooks.py                  # Hook python-for-android (FileProvider)
├── buildozer.spec            # Configuration Buildozer
└── .github/workflows/build.yml
```

## Lancer la compilation depuis GitHub (recommandé)

1. Créez un dépôt GitHub et poussez-y l'intégralité de ce projet
   (en conservant l'arborescence, notamment `.github/workflows/build.yml`).
2. Poussez sur la branche `main` (ou déclenchez manuellement le workflow) :
   - Allez dans l'onglet **Actions** de votre dépôt GitHub.
   - Sélectionnez le workflow **Build Android APK**.
   - Cliquez sur **Run workflow** (bouton "workflow_dispatch"), ou faites
     simplement un `git push` sur `main`.
3. Attendez la fin du job `build` (le premier build est long : 20–40 min,
   car Buildozer télécharge le SDK/NDK Android et compile toutes les
   dépendances natives). Les builds suivants sont plus rapides grâce au
   cache configuré dans le workflow.
4. Une fois le job terminé, ouvrez l'onglet **Summary** du run, puis
   téléchargez l'artefact **parallel-space-clone-debug-apk** : il contient
   le fichier `.apk` généré (build *debug*, signé automatiquement avec la
   clé de debug — suffisant pour tester sur un appareil).

## Compiler localement (optionnel)

Sur une machine Linux (WSL2 fonctionne aussi) :

```bash
pip install buildozer cython==0.29.36
sudo apt-get install -y git zip unzip openjdk-17-jdk autoconf libtool \
    pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev cmake libffi-dev \
    libssl-dev automake build-essential
buildozer android debug
```

L'APK apparaît ensuite dans `bin/`.

## Fonctionnement des fonctionnalités clés

- **Import d'APK** : `plyer.filechooser` ouvre le sélecteur système
  (Storage Access Framework). Le fichier choisi est copié dans le
  stockage privé de l'app (`core/apk_manager.py::_materialize_apk`).
- **Lecture des métadonnées** : `PackageManager.getPackageArchiveInfo`
  extrait nom, package, version ; l'icône est convertie en PNG via
  `Bitmap`/`Canvas` (API Android standard) pour être affichable dans Kivy.
- **Installation** : une URI `content://` est générée via
  `androidx.core.content.FileProvider`, puis un `Intent.ACTION_VIEW` de
  type `application/vnd.android.package-archive` est envoyé au système —
  c'est l'installateur natif d'Android qui prend le relai et demande
  confirmation à l'utilisateur.
- **Ouverture d'une app installée** :
  `PackageManager.getLaunchIntentForPackage` puis `startActivity`,
  exactement comme le fait un launcher Android standard.
- **Bibliothèque** : stockée en JSON dans `App.user_data_dir`
  (`core/storage.py`), avec ajout/suppression/renommage.

## Limitations connues / points à vérifier

- **FileProvider via hook (`hooks.py`)** : Buildozer/python-for-android
  ne proposent pas nativement un champ pour ajouter un `<provider>`
  personnalisé dans `AndroidManifest.xml`. Ce projet utilise un hook
  `before_apk_build` (`p4a.hook` dans `buildozer.spec`) qui patche le
  manifeste généré. Ce mécanisme dépend de la structure interne de
  python-for-android, qui peut évoluer : si le build échoue à cette
  étape ou si l'installation ne se déclenche pas, inspectez le fichier
  `AndroidManifest.xml` généré dans `.buildozer/android/platform/build-*/dists/.../src/main/`
  pour vérifier que le `<provider>` a bien été injecté, et ajustez
  `hooks.py` selon la version de python-for-android utilisée.
- **"Installer des applications inconnues"** : depuis Android 8 (API 26),
  l'utilisateur doit explicitement autoriser cette application à
  installer des paquets, via l'écran système ouvert automatiquement par
  `core/permissions.py::open_install_unknown_apps_settings` si
  l'installation échoue une première fois.
- **Stockage étendu (Android 11+)** : le sélecteur de fichiers (SAF) est
  utilisé précisément pour rester compatible avec le stockage par étendue
  (*scoped storage*), sans nécessiter la permission `MANAGE_EXTERNAL_STORAGE`.
- **Icônes de très grande taille** : l'extraction d'icône (`_extract_icon`)
  fonctionne pour la grande majorité des APK, mais certains packages avec
  des ressources adaptatives complexes peuvent nécessiter des ajustements.
- Les versions exactes d'API/NDK/outils dans `buildozer.spec` peuvent
  nécessiter une mise à jour selon l'évolution de python-for-android ;
  vérifiez la documentation officielle si le workflow GitHub Actions
  échoue lors de la résolution du SDK/NDK.

## Tester l'interface sans Android

`main.py` détecte la plateforme (`kivy.utils.platform`) et bascule en
mode "stub" pour `core/apk_manager.py` lorsqu'il n'est pas exécuté sur
Android, ce qui permet de lancer `python main.py` sur desktop pour
itérer rapidement sur l'interface (les actions d'installation/ouverture
sont alors simulées et journalisées dans la console).
