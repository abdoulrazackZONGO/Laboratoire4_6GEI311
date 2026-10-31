from __future__ import annotations

from typing import TYPE_CHECKING

from etats.etat_assigne import EtatAssigne
from etats.etat_ferme import EtatFerme
from etats.etat_ouvert import EtatOuvert
from etats.etat_termine import EtatTermine
from etats.etat_validation import EtatValidation
from modele.enums import Statut

if TYPE_CHECKING:
    from etats.etat_ticket import EtatTicket


class FabriqueEtat:
    """Recrée l'objet état correspondant à un statut (patron Fabrique).

    Sert à restaurer un ticket sauvegardé : le statut est enregistré sous forme
    de texte, et doit redevenir un objet état. C'est le seul endroit, hors des
    états eux-mêmes, qui connaît les classes d'état concrètes.
    """

    _CLASSES: dict[Statut, type[EtatTicket]] = {
        Statut.OUVERT: EtatOuvert,
        Statut.ASSIGNE: EtatAssigne,
        Statut.VALIDATION: EtatValidation,
        Statut.TERMINE: EtatTermine,
        Statut.FERME: EtatFerme,
    }

    @staticmethod
    def creer(statut: Statut) -> EtatTicket:
        classe = FabriqueEtat._CLASSES.get(statut)
        if classe is None:
            raise ValueError(f"Aucun état ne correspond au statut {statut!r}")
        return classe()
