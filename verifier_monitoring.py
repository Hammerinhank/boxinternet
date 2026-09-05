#!/usr/bin/env python3
"""
verifier_monitoring.py — contrôle quotidien de tous les scripts surveillés.

Version 1.0.0

Lit monitoring.json, vérifie la fraîcheur de chaque source, affiche un rapport
et sort en erreur (code 1) si au moins un script est muet ou en échec.
Utilisable tel quel en local sur le Mac pour tester :  python3 verifier_monitoring.py
"""

import datetime
import json
import os
import sys
from zoneinfo import ZoneInfo

VERSION = "1.0.0"
CONFIG = "monitoring.json"
TZ = ZoneInfo("Europe/Paris")

CHAMPS_DATE = ("derniere_execution", "heure", "date", "timestamp", "time", "ts",
               "datetime", "created_at", "recorded_at", "date_heure")


def lire_date(rec):
    """Extrait une date d'un enregistrement, quel que soit le nom du champ."""
    if not isinstance(rec, dict):
        return None
    for champ in CHAMPS_DATE:
        v = rec.get(champ)
        if v is None:
            continue
        if isinstance(v, (int, float)):
            secondes = v / 1000 if v > 1e11 else v
            return datetime.datetime.fromtimestamp(secondes, tz=TZ)
        if isinstance(v, str):
            try:
                d = datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                continue
            return d if d.tzinfo else d.replace(tzinfo=TZ)
    return None


def duree_lisible(heures):
    if heures >= 24:
        return f"{int(heures // 24)} j {int(heures % 24)} h"
    if heures >= 1:
        return f"{heures:.1f} h"
    return f"{int(heures * 60)} min"


def controler(entree, maintenant):
    """Renvoie (etat, detail) avec etat parmi 'ok', 'muet', 'erreur', 'absent'."""
    nom = entree.get("nom", entree["id"])
    seuil = float(entree.get("seuil_heures", 26))

    if entree.get("type") == "journal":
        fichier = entree.get("fichier", "activity.json")
    else:
        fichier = os.path.join("heartbeats", f"{entree['id']}.json")

    if not os.path.exists(fichier):
        return "absent", f"{nom} — aucun signe de vie ({fichier} introuvable)"

    try:
        with open(fichier, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return "absent", f"{nom} — fichier illisible ({fichier} : {e})"

    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = next((data[k] for k in ("records", "entries", "activities")
                        if isinstance(data.get(k), list)), [data])
    else:
        records = []

    dates = [d for d in (lire_date(r) for r in records) if d]
    if not dates:
        return "absent", f"{nom} — aucune date exploitable dans {fichier}"

    dernier = max(dates)
    heures = (maintenant - dernier).total_seconds() / 3600
    quand = dernier.strftime("%d/%m à %Hh%M")

    dernier_rec = records[-1] if records else {}
    statut = dernier_rec.get("statut") if isinstance(dernier_rec, dict) else None
    detail_msg = dernier_rec.get("message") if isinstance(dernier_rec, dict) else ""

    if heures > seuil:
        return "muet", (f"{nom} — SILENCIEUX depuis {duree_lisible(heures)} "
                        f"(dernier signe le {quand}, seuil {seuil:.0f} h)")
    if statut == "erreur":
        return "erreur", (f"{nom} — a signalé une ERREUR le {quand}"
                          + (f" : {detail_msg}" if detail_msg else ""))
    return "ok", f"{nom} — ok, il y a {duree_lisible(heures)} (le {quand})"


def main():
    maintenant = datetime.datetime.now(TZ)
    print(f"Contrôle du monitoring — version {VERSION} — "
          f"{maintenant.strftime('%d/%m/%Y %Hh%M')}\n")

    try:
        with open(CONFIG, encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        sys.exit(f"ALERTE : {CONFIG} introuvable.")
    except json.JSONDecodeError as e:
        sys.exit(f"ALERTE : {CONFIG} n'est pas du JSON valide ({e}).")

    entrees = [e for e in config.get("scripts", []) if e.get("actif", True)]
    if not entrees:
        sys.exit(f"ALERTE : aucun script actif dans {CONFIG}.")

    problemes, sains = [], []
    for entree in entrees:
        etat, detail = controler(entree, maintenant)
        (sains if etat == "ok" else problemes).append(detail)

    lignes = []
    if problemes:
        lignes.append(f"*** ALERTE — {len(problemes)} script(s) en défaut ***")
        lignes += [f"  ✖  {d}" for d in problemes]
        if sains:
            lignes.append("")
            lignes.append("Le reste va bien :")
            lignes += [f"  ✔  {d}" for d in sains]
    else:
        lignes.append(f"Tout va bien — {len(sains)} script(s) surveillé(s) :")
        lignes += [f"  ✔  {d}" for d in sains]

    rapport = "\n".join(lignes)
    print(rapport)

    # Rapport visible directement sur la page du run GitHub
    resume = os.environ.get("GITHUB_STEP_SUMMARY")
    if resume:
        titre = "🚨 Scripts en défaut" if problemes else "✅ Tous les scripts tournent"
        with open(resume, "a", encoding="utf-8") as f:
            f.write(f"## {titre}\n\n```\n{rapport}\n```\n")

    return 1 if problemes else 0


if __name__ == "__main__":
    sys.exit(main())
