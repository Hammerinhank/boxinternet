#!/usr/bin/env python3
"""
heartbeat.py — mouchard commun à tous les scripts surveillés du Mac.

Version 1.0.0

À appeler à la fin de chaque script surveillé :

    python3 heartbeat.py sauvegarde-photos
    python3 heartbeat.py sauvegarde-photos --message "142 photos copiées"
    python3 heartbeat.py sauvegarde-photos --erreur "disque de destination plein"

Écrit heartbeats/<id>.json dans le dépôt local, puis commit + push.
Un fichier par script : deux scripts ne se marchent jamais dessus.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

VERSION = "1.1.0"

# Chemin du clone local du dépôt (modifiable via la variable d'environnement MONITORING_DEPOT)
DEPOT = os.environ.get("MONITORING_DEPOT", os.path.expanduser("~/boxinternet"))
TZ = ZoneInfo("Europe/Paris")
TENTATIVES = 3
HISTORIQUE_MAX = 50   # nombre d'exécutions conservées par script


def git(*args, check=False):
    return subprocess.run(
        ["git", "-C", DEPOT, *args],
        capture_output=True, text=True, check=check
    )


def main():
    p = argparse.ArgumentParser(description="Signale qu'un script a tourné (v%s)" % VERSION)
    p.add_argument("id", help="identifiant du script, tel qu'inscrit dans monitoring.json")
    p.add_argument("--message", default="", help="information libre affichée dans le rapport")
    p.add_argument("--erreur", default="", help="signale une exécution en échec")
    args = p.parse_args()

    if not os.path.isdir(os.path.join(DEPOT, ".git")):
        sys.exit(f"heartbeat v{VERSION} : dépôt introuvable dans {DEPOT} "
                 f"(définissez MONITORING_DEPOT).")

    maintenant = datetime.datetime.now(TZ)
    contenu = {
        "script": args.id,
        "derniere_execution": maintenant.isoformat(timespec="seconds"),
        "statut": "erreur" if args.erreur else "ok",
        "message": args.erreur or args.message,
        "machine": os.uname().nodename,
        "version_heartbeat": VERSION,
    }

    dossier = os.path.join(DEPOT, "heartbeats")
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, f"{args.id}.json")

    # On conserve les dernières exécutions pour alimenter l'historique de l'app
    historique = []
    if os.path.exists(chemin):
        try:
            with open(chemin, encoding="utf-8") as f:
                ancien = json.load(f)
            if isinstance(ancien, list):
                historique = ancien
            elif isinstance(ancien, dict):
                historique = [ancien]          # ancien format mono-relevé
        except (json.JSONDecodeError, OSError):
            historique = []                    # fichier abîmé : on repart proprement

    historique.append(contenu)
    historique = historique[-HISTORIQUE_MAX:]

    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(historique, f, ensure_ascii=False, indent=2)
        f.write("\n")

    relatif = os.path.join("heartbeats", f"{args.id}.json")
    message = f"heartbeat {args.id} : {contenu['statut']}"

    for tentative in range(1, TENTATIVES + 1):
        git("add", relatif)
        git("commit", "-m", message)          # échoue sans dommage s'il n'y a rien à committer
        git("pull", "--rebase", "--autostash")
        push = git("push")
        if push.returncode == 0:
            print(f"heartbeat v{VERSION} : {args.id} → {contenu['statut']} "
                  f"({maintenant.strftime('%d/%m %Hh%M')})")
            return 0
        if tentative < TENTATIVES:
            time.sleep(5 * tentative)

    print(f"heartbeat v{VERSION} : ÉCHEC du push pour {args.id}.\n{push.stderr.strip()}",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
