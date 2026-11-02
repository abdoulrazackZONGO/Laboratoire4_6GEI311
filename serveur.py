"""Point d'entrée du serveur de l'API : python serveur.py [--port 5000]."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from api import creerApplication
from api.contexte import ContexteServeur

HOTE = "127.0.0.1"
PORT_PAR_DEFAUT = 5000


def main(argv: list[str] | None = None) -> None:
    analyseur = argparse.ArgumentParser(description="Serveur de l'API du gestionnaire de tickets")
    analyseur.add_argument(
        "--port", type=int, default=PORT_PAR_DEFAUT,
        help=f"port d'écoute (défaut : {PORT_PAR_DEFAUT})",
    )
    arguments = analyseur.parse_args(argv)
    # Les chemins des données (donnees/...) sont relatifs à la racine du dépôt :
    # on s'y place, d'où que le serveur soit lancé.
    os.chdir(Path(__file__).resolve().parent)
    contexte = ContexteServeur()
    print(f"Données chargées depuis {contexte.sourceChargee.as_posix()}")
    application = creerApplication(contexte)
    # Plusieurs fils : une GUI qui interroge /version ne bloque pas les autres clients.
    # Pas de mode debug : son rechargeur relancerait le processus et rechargerait les données.
    application.run(host=HOTE, port=arguments.port, threaded=True)


if __name__ == "__main__":
    main()
