"""Règles de dépendances entre les couches, vérifiées en lisant les imports du code source.

Le code n'est pas exécuté : chaque fichier est lu avec ast, qui donne ses instructions import
avec leur numéro de ligne. Un import placé sous `if TYPE_CHECKING:` compte pour les règles
d'architecture (le client ne doit pas dépendre des classes du métier, même pour le typage),
mais pas pour la règle « sans tkinter », qui porte sur ce qui est chargé à l'exécution.

Règles (celles de l'équipe pour le lab 4) :
1. le métier n'importe ni flask, ni api, ni ihm, ni tkinter ;
2. api/ (et serveur.py) n'importe ni ihm ni tkinter ;
3. le client (ihm/ et app.py) n'importe du métier que le contrat partagé : modele.enums,
   modele.exceptions et modele.observateur ; ni flask ni api non plus ;
4. seul ihm/passerelle/client_api.py fait des requêtes HTTP ;
5. le client ne vise aucun fichier du dossier donnees/ (tout passe par le serveur) ;
6. les contrôleurs secondaires (tous sauf le principal) ne chargent pas tkinter, même
   indirectement, pour rester testables sans écran.
"""
from __future__ import annotations

import ast
import re
import unittest
from dataclasses import dataclass
from pathlib import Path

racineDepot = Path(__file__).resolve().parent.parent

PAQUETS_METIER: frozenset[str] = frozenset(
    {"modele", "etats", "acteurs", "description", "commandes", "sessions", "persistance"}
)
# Contrat partagé entre le serveur et le client.
CONTRAT_PARTAGE: frozenset[str] = frozenset(
    {"modele.enums", "modele.exceptions", "modele.observateur"}
)
MODULES_HTTP: frozenset[str] = frozenset({"urllib", "http", "socket", "requests", "httpx"})
PASSERELLE_HTTP = "ihm/passerelle/client_api.py"
CONTROLEURS_EXIGES: frozenset[str] = frozenset(
    {"controleur_admin", "controleur_user", "controleur_edition"}
)


@dataclass(frozen=True)
class Import:
    """Un module importé par un fichier ; executeAuChargement est faux sous TYPE_CHECKING."""

    module: str
    ligne: int
    executeAuChargement: bool

    @property
    def racine(self) -> str:
        return self.module.split(".")[0]


def nomModule(chemin: Path) -> str:
    """ihm/vues/vue_detail.py → ihm.vues.vue_detail ; ihm/__init__.py → ihm."""
    parties = list(chemin.relative_to(racineDepot).with_suffix("").parts)
    if parties[-1] == "__init__":
        parties.pop()
    return ".".join(parties)


def _estTypeChecking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def lireImports(chemin: Path) -> list[Import]:
    """Imports d'un fichier du dépôt."""
    return analyserImports(
        chemin.read_text(encoding="utf-8"), nomModule(chemin), chemin.name == "__init__.py"
    )


def analyserImports(source: str, module: str, estPaquet: bool = False) -> list[Import]:
    """Tous les imports d'un code source, avec les relatifs résolus en noms absolus.

    Pour `from a import b`, a est noté, et a.b aussi : b peut être un sous-module
    (`from modele import enums`). Un nom qui n'est pas un module ne gêne pas les règles.
    """
    arbre = ast.parse(source)
    paquet = module.split(".")
    if not estPaquet:
        paquet.pop()
    imports: list[Import] = []

    def visiter(noeuds: list[ast.stmt], execute: bool) -> None:
        for noeud in noeuds:
            if isinstance(noeud, ast.Import):
                imports.extend(Import(a.name, noeud.lineno, execute) for a in noeud.names)
            elif isinstance(noeud, ast.ImportFrom):
                if noeud.level:
                    base = paquet[: len(paquet) - (noeud.level - 1)]
                    origine = ".".join(base + ([noeud.module] if noeud.module else []))
                else:
                    origine = noeud.module or ""
                imports.append(Import(origine, noeud.lineno, execute))
                imports.extend(
                    Import(f"{origine}.{a.name}", noeud.lineno, execute)
                    for a in noeud.names if a.name != "*"
                )
            elif isinstance(noeud, ast.If):
                visiter(noeud.body, execute and not _estTypeChecking(noeud.test))
                visiter(noeud.orelse, execute)
            elif isinstance(noeud, (ast.Try, ast.With, ast.For, ast.While)):
                for bloc in ("body", "orelse", "finalbody"):
                    visiter(getattr(noeud, bloc, []), execute)
                for gestionnaire in getattr(noeud, "handlers", []):
                    visiter(gestionnaire.body, execute)
            elif isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # Un import local à une fonction s'exécute à l'appel : il compte aussi.
                visiter(noeud.body, execute)

    visiter(arbre.body, True)
    return imports


def fichiersDe(*emplacements: str) -> list[Path]:
    """Fichiers .py des dossiers ou fichiers donnés, relatifs à la racine du dépôt."""
    fichiers: list[Path] = []
    for emplacement in emplacements:
        chemin = racineDepot / emplacement
        if chemin.is_file():
            fichiers.append(chemin)
        else:
            fichiers.extend(sorted(p for p in chemin.rglob("*.py") if "__pycache__" not in p.parts))
    return fichiers


def relatif(chemin: Path) -> str:
    return chemin.relative_to(racineDepot).as_posix()


class TestReglesDependances(unittest.TestCase):

    def violations(
        self, fichiers: list[Path], interdit, *, seulementExecutes: bool = False
    ) -> list[str]:
        """« fichier:ligne module » pour chaque import que interdit(fichier, import) refuse."""
        trouvees: list[str] = []
        for fichier in fichiers:
            for imp in lireImports(fichier):
                if seulementExecutes and not imp.executeAuChargement:
                    continue
                if interdit(fichier, imp):
                    trouvees.append(f"{relatif(fichier)}:{imp.ligne} {imp.module}")
        return sorted(set(trouvees))

    def assertAucune(self, violations: list[str], regle: str) -> None:
        self.assertEqual(violations, [], f"{regle} :\n  " + "\n  ".join(violations))

    # ------------------------------------------------------------------ l'analyse elle-même

    def test_l_analyse_voit_les_imports(self) -> None:
        """Témoin : sans lui, une analyse cassée ferait passer toutes les règles."""
        vue = lireImports(racineDepot / "ihm/vues/fenetre_base.py")
        self.assertIn("tkinter", {i.racine for i in vue})
        edition = lireImports(racineDepot / "ihm/controleurs/controleur_edition.py")
        sousTypage = [i for i in edition if i.module.startswith("ihm.controleurs.controleur_principal")]
        self.assertTrue(sousTypage, "import de ControleurPrincipal attendu (sous TYPE_CHECKING)")
        self.assertFalse(any(i.executeAuChargement for i in sousTypage))

    def test_les_imports_relatifs_sont_resolus(self) -> None:
        source = "from . import erreurs\nfrom ..vues.fenetre_base import FenetreBase\n"
        modules = {i.module for i in analyserImports(source, "ihm.passerelle.client_api")}
        self.assertIn("ihm.passerelle.erreurs", modules)
        self.assertIn("ihm.vues.fenetre_base", modules)
        modules = {i.module for i in analyserImports("from . import enums\n", "modele", True)}
        self.assertIn("modele.enums", modules)

    def test_un_import_local_ou_sous_type_checking_est_vu(self) -> None:
        source = (
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n    from modele.ticket import Ticket\n"
            "def f():\n    import tkinter\n"
        )
        imports = {i.module: i.executeAuChargement for i in analyserImports(source, "ihm.x")}
        self.assertFalse(imports["modele.ticket"])
        self.assertTrue(imports["tkinter"])

    # ------------------------------------------------------------------ règles 1 et 2

    def test_regle1_le_metier_n_importe_ni_flask_ni_api_ni_ihm_ni_tkinter(self) -> None:
        interdits = {"flask", "werkzeug", "api", "ihm", "tkinter"}
        fichiers = fichiersDe(*sorted(PAQUETS_METIER))
        self.assertTrue(fichiers)
        self.assertAucune(
            self.violations(fichiers, lambda _f, i: i.racine in interdits),
            "Règle 1 : le métier dépend d'une couche extérieure",
        )

    def test_regle2_l_api_n_importe_ni_ihm_ni_tkinter(self) -> None:
        fichiers = fichiersDe("api", "serveur.py")
        self.assertTrue(fichiers)
        self.assertAucune(
            self.violations(fichiers, lambda _f, i: i.racine in {"ihm", "tkinter"}),
            "Règle 2 : le serveur dépend du client",
        )

    # ------------------------------------------------------------------ règles 3 à 5 (client)

    def test_regle3_le_client_n_importe_du_metier_que_le_contrat_partage(self) -> None:
        def interdit(_fichier: Path, imp: Import) -> bool:
            if imp.racine in {"flask", "werkzeug", "api"}:
                return True
            if imp.racine not in PAQUETS_METIER:
                return False
            # « from modele import enums » note modele puis modele.enums : seul le second décide.
            if imp.module == "modele":
                return False
            return not any(
                imp.module == contrat or imp.module.startswith(contrat + ".")
                for contrat in CONTRAT_PARTAGE
            )

        self.assertAucune(
            self.violations(fichiersDe("ihm", "app.py"), interdit),
            "Règle 3 : le client importe du métier hors du contrat partagé",
        )

    def test_regle4_seule_la_passerelle_fait_des_requetes_http(self) -> None:
        self.assertAucune(
            self.violations(
                fichiersDe("ihm", "app.py"),
                lambda f, i: i.racine in MODULES_HTTP and relatif(f) != PASSERELLE_HTTP,
            ),
            f"Règle 4 : requête HTTP ailleurs que dans {PASSERELLE_HTTP}",
        )

    def test_regle5_le_client_ne_vise_pas_le_dossier_donnees(self) -> None:
        """Approximation lisible par ast : aucune chaîne du code client ne désigne donnees/.

        Les docstrings ne comptent pas : elles peuvent parler du dossier sans l'ouvrir.
        """
        motif = re.compile(r"(^|[/\\])donnees([/\\]|$)")
        trouvees: list[str] = []
        for fichier in fichiersDe("ihm", "app.py"):
            arbre = ast.parse(fichier.read_text(encoding="utf-8"))
            docstrings = {
                id(n.body[0].value)
                for n in ast.walk(arbre)
                if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and n.body and isinstance(n.body[0], ast.Expr)
                and isinstance(n.body[0].value, ast.Constant)
            }
            for noeud in ast.walk(arbre):
                if (
                    isinstance(noeud, ast.Constant) and isinstance(noeud.value, str)
                    and id(noeud) not in docstrings and motif.search(noeud.value)
                ):
                    trouvees.append(f"{relatif(fichier)}:{noeud.lineno} {noeud.value!r}")
        self.assertAucune(trouvees, "Règle 5 : le client désigne un fichier de donnees/")

    # ------------------------------------------------------------------ règle 6

    def test_regle6_les_controleurs_secondaires_ne_chargent_pas_tkinter(self) -> None:
        """Suit les imports exécutés de module en module dans le projet : un contrôleur qui
        importerait une vue chargerait tkinter par elle, même sans l'importer lui-même.
        """
        dossier = racineDepot / "ihm" / "controleurs"
        secondaires = sorted(
            p for p in dossier.glob("controleur_*.py") if p.stem != "controleur_principal"
        )
        self.assertLessEqual(CONTROLEURS_EXIGES, {p.stem for p in secondaires})
        fautifs: list[str] = []
        for controleur in secondaires:
            chaine = self._cheminVers(nomModule(controleur), "tkinter")
            if chaine is not None:
                fautifs.append(f"{relatif(controleur)} : " + " → ".join(chaine))
        self.assertAucune(fautifs, "Règle 6 : un contrôleur secondaire charge tkinter")

    def _cheminVers(self, depart: str, cible: str) -> list[str] | None:
        """Chaîne d'imports exécutés de depart à cible (parcours en largeur), ou None."""
        precedent: dict[str, str | None] = {depart: None}
        aVisiter = [depart]
        while aVisiter:
            module = aVisiter.pop(0)
            for suivant in self._importsExecutes(module):
                if suivant in precedent:
                    continue
                precedent[suivant] = module
                if suivant.split(".")[0] == cible:
                    chaine = [suivant]
                    while precedent[chaine[-1]] is not None:
                        chaine.append(precedent[chaine[-1]])  # type: ignore[arg-type]
                    return list(reversed(chaine))
                aVisiter.append(suivant)
        return None

    def _importsExecutes(self, module: str) -> list[str]:
        """Modules chargés à l'import de module : ses imports exécutés, et pour chacun ses
        paquets parents (importer a.b.c exécute a/__init__.py puis a/b/__init__.py).
        Un module hors du projet (bibliothèque) est une feuille.
        """
        fichier = self._fichierDuModule(module)
        if fichier is None:
            return []
        charges: list[str] = []
        for imp in lireImports(fichier):
            if not imp.executeAuChargement:
                continue
            parties = imp.module.split(".")
            for n in range(1, len(parties) + 1):
                nom = ".".join(parties[:n])
                if n == 1 or self._fichierDuModule(nom) is not None:
                    charges.append(nom)
        return charges

    def _fichierDuModule(self, module: str) -> Path | None:
        base = racineDepot.joinpath(*module.split("."))
        for chemin in (base.with_suffix(".py"), base / "__init__.py"):
            if chemin.is_file():
                return chemin
        return None


if __name__ == "__main__":
    unittest.main()
