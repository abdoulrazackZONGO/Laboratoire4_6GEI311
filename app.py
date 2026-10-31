"""Point d'entrée de l'interface graphique : python app.py."""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path

from ihm.controleurs.controleur_principal import ControleurPrincipal


def main() -> None:
    # Les chemins des données (donnees/...) sont relatifs à la racine du dépôt :
    # on s'y place, d'où que l'application soit lancée.
    os.chdir(Path(__file__).resolve().parent)
    racine = tk.Tk()
    # La racine reste cachée : chaque fenêtre visible est une FenetreBase.
    racine.withdraw()
    principal = ControleurPrincipal(racine)
    principal.demarrer()
    racine.mainloop()


if __name__ == "__main__":
    main()
