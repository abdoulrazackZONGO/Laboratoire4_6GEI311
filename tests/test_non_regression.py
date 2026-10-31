from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

racineDepot = Path(__file__).resolve().parent.parent
cheminReference = Path(__file__).resolve().parent / "reference_main.txt"
motifDate = re.compile(r"\d{4}-\d{2}-\d{2}")


def executerMain() -> str:
    """Exécute main.py depuis la racine du dépôt et retourne sa sortie, dates neutralisées."""
    resultat = subprocess.run(
        [sys.executable, "main.py"],
        cwd=racineDepot,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    # main.py affiche date.today() : la date du jour ne doit pas casser la comparaison.
    return motifDate.sub("AAAA-MM-JJ", resultat.stdout)


class TestNonRegression(unittest.TestCase):
    """La sortie de main.py doit rester identique à la référence."""

    def testSortieIdentiqueALaReference(self) -> None:
        attendu = cheminReference.read_text(encoding="utf-8")
        self.assertEqual(executerMain(), attendu)


if __name__ == "__main__":
    # Exécuté directement : régénère la référence.
    cheminReference.write_text(executerMain(), encoding="utf-8", newline="\n")
    print(f"Référence régénérée : {cheminReference}")
