"""Point d'entrée de l'interface graphique : python app.py [--url http://127.0.0.1:5000].

La GUI est un client de l'API : elle ne lit ni n'écrit aucun fichier de données. Le serveur
(python serveur.py) doit être lancé avant elle.
"""
from __future__ import annotations

import argparse
import tkinter as tk

from ihm.controleurs.controleur_principal import ControleurPrincipal
from ihm.passerelle.client_api import URL_PAR_DEFAUT


def analyserArguments(argv: list[str] | None = None) -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(description="Interface graphique du gestionnaire de tickets")
    analyseur.add_argument(
        "--url", default=URL_PAR_DEFAUT,
        help=f"adresse du serveur de l'API (défaut : {URL_PAR_DEFAUT})",
    )
    return analyseur.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    arguments = analyserArguments(argv)
    racine = tk.Tk()
    # La racine reste cachée : chaque fenêtre visible est une FenetreBase.
    racine.withdraw()
    principal = ControleurPrincipal(racine, arguments.url)
    # Sans serveur, l'utilisateur peut renoncer : la racine est alors déjà détruite.
    if principal.demarrer():
        racine.mainloop()


if __name__ == "__main__":
    main()
