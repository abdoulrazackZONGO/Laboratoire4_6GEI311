from __future__ import annotations


class RapportExecution:
    """Bilan de l'application d'une session : succès et refus motivés."""

    def __init__(self) -> None:
        self._succes: list[str] = []
        self._refus: list[tuple[str, str]] = []

    def ajouterSucces(self, libelle: str) -> None:
        self._succes.append(libelle)

    def ajouterRefus(self, libelle: str, motif: str) -> None:
        self._refus.append((libelle, motif))

    @property
    def succes(self) -> list[str]:
        return list(self._succes)

    @property
    def refus(self) -> list[tuple[str, str]]:
        return list(self._refus)

    @property
    def nombreSucces(self) -> int:
        return len(self._succes)

    @property
    def nombreRefus(self) -> int:
        return len(self._refus)

    def afficher(self) -> None:
        """MÉTHODE D'AFFICHAGE : succès, refus avec motif, puis bilan chiffré."""
        print("  Succès :")
        if not self._succes:
            print("    (aucun)")
        for libelle in self._succes:
            print(f"    [OK]    {libelle}")
        print("  Refus :")
        if not self._refus:
            print("    (aucun)")
        for libelle, motif in self._refus:
            print(f"    [REFUS] {libelle}")
            print(f"            motif : {motif}")
        print(f"  Bilan : {self.nombreSucces} succès, {self.nombreRefus} refus")
