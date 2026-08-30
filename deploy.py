#!/usr/bin/env python3
"""
Script de déploiement : push vers GitHub, attend le build Actions,
télécharge l'APK dans /storage/emulated/0/Download/.
Le token doit être dans t.txt, à côté de ce script.
"""
import subprocess
import sys
import time
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, "t.txt")
DOWNLOAD_DIR = "/storage/emulated/0/Download/"
ARTIFACT_NAME = "parallel-space-clone-debug-apk"
WORKFLOW_FILE = "build.yml"

def run(cmd, **kwargs):
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=SCRIPT_DIR, text=True, capture_output=True, **kwargs)
    if result.stdout:
        print(result.stdout.strip())
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
    return result

def main():
    if not os.path.exists(TOKEN_FILE):
        print(f"Erreur : {TOKEN_FILE} introuvable.")
        sys.exit(1)
    with open(TOKEN_FILE) as f:
        token = f.read().strip()

    env = os.environ.copy()
    env["GH_TOKEN"] = token

    # Récupère l'URL du remote et y injecte le token pour éviter le prompt.
    remote = run(["git", "remote", "get-url", "origin"]).stdout.strip()
    if remote.startswith("https://") and "@" not in remote:
        authed_remote = remote.replace("https://", f"https://{token}@")
    else:
        authed_remote = remote

    print("== Ajout et commit des changements ==")
    run(["git", "add", "."])
    commit = subprocess.run(
        ["git", "commit", "-m", "Mise à jour automatique"],
        cwd=SCRIPT_DIR, text=True, capture_output=True
    )
    print(commit.stdout.strip() or "(rien à committer)")

    print("== Push vers GitHub ==")
    push = subprocess.run(["git", "push", authed_remote, "HEAD:main"],
                           cwd=SCRIPT_DIR, text=True, capture_output=True)
    print(push.stdout.strip())
    print(push.stderr.strip())

    print("== Attente du démarrage du workflow ==")
    time.sleep(8)
    run_id = None
    for _ in range(15):
        result = run([
            "gh", "run", "list",
            "--workflow", WORKFLOW_FILE,
            "--limit", "1",
            "--json", "databaseId,status,conclusion"
        ], env=env)
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            data = []
        if data:
            run_id = data[0]["databaseId"]
            break
        time.sleep(5)

    if not run_id:
        print("Impossible de trouver le run du workflow.")
        sys.exit(1)

    print(f"== Run trouvé : {run_id} — suivi de l'avancement ==")
    while True:
        result = run([
            "gh", "run", "view", str(run_id),
            "--json", "status,conclusion"
        ], env=env)
        try:
            info = json.loads(result.stdout)
        except json.JSONDecodeError:
            info = {}
        status = info.get("status")
        conclusion = info.get("conclusion")
        print(f"Statut : {status} / Conclusion : {conclusion}")
        if status == "completed":
            break
        time.sleep(20)

    if conclusion != "success":
        print(f"Le build a échoué (conclusion={conclusion}). Consultez les logs avec :")
        print(f"  gh run view {run_id} --log")
        sys.exit(1)

    print("== Téléchargement de l'APK ==")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    run([
        "gh", "run", "download", str(run_id),
        "--name", ARTIFACT_NAME,
        "--dir", DOWNLOAD_DIR
    ], env=env)

    print(f"Terminé. Vérifiez : {DOWNLOAD_DIR}")

if __name__ == "__main__":
    main()
