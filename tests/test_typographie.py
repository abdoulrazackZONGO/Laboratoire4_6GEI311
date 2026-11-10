"""Aucun tiret long ni demi-cadratin dans les fichiers texte du dépôt.

L'équipe a choisi le tiret simple partout (code, vues, documents) : ce test empêche ces
caractères de revenir. Ils sont écrits ici par leur code, pour ne pas figurer dans ce fichier.

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -t . -v
"""
from __future__ import annotations

import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
TIRETS_INTERDITS = {chr(0x2014): "tiret long", chr(0x2013): "demi-cadratin"}
EXTENSIONS_TEXTE = {
    ".py", ".md", ".txt", ".html", ".js", ".css", ".yaml", ".yml", ".json", ".drawio", ".toml",
}
# Environnement, historique et données produites à l'exécution : hors du dépôt.
DOSSIERS_IGNORES = {".venv", ".git", "__pycache__", ".idea", ".vscode"}
FICHIERS_IGNORES = {"sauvegarde.json"}


def fichiersTexte() -> list[Path]:
    return sorted(
        chemin
        for chemin in RACINE.rglob("*")
        if chemin.is_file()
        and chemin.suffix.lower() in EXTENSIONS_TEXTE
        and chemin.name not in FICHIERS_IGNORES
        and not DOSSIERS_IGNORES.intersection(chemin.relative_to(RACINE).parts)
    )


class TestTypographie(unittest.TestCase):
    def test_aucun_tiret_long(self) -> None:
        trouves = []
        for chemin in fichiersTexte():
            texte = chemin.read_text(encoding="utf-8", errors="replace")
            for numero, ligne in enumerate(texte.splitlines(), 1):
                for caractere, nom in TIRETS_INTERDITS.items():
                    if caractere in ligne:
                        trouves.append(f"{chemin.relative_to(RACINE).as_posix()}:{numero} ({nom})")
        self.assertEqual(trouves, [], "remplacer par un tiret simple")

    def test_le_test_voit_bien_les_fichiers(self) -> None:
        """Garde-fou : sans fichier lu, le test précédent passerait pour rien."""
        noms = {chemin.relative_to(RACINE).as_posix() for chemin in fichiersTexte()}
        for attendu in ("README.md", "openapi.yaml", "web/app.js", "ihm/vues/vue_connexion.py"):
            with self.subTest(attendu=attendu):
                self.assertIn(attendu, noms)


if __name__ == "__main__":
    unittest.main()
