from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modele.enums import Statut


class TransitionInvalideException(Exception):
    """Levée lorsque l'état courant d'un ticket refuse le statut demandé."""

    def __init__(self, etat_source: Statut, statut_demande: Statut) -> None:
        super().__init__(
            f"Transition invalide : impossible de passer de l'état "
            f"{etat_source.name} au statut {statut_demande.name}"
        )


class SessionIndisponibleException(Exception):
    """Levée lorsqu'une opération est impossible dans l'état actuel de la session."""

    def __init__(self, motif: str) -> None:
        super().__init__(motif)


class AccesRefuseException(Exception):
    """Levée lorsqu'un acteur n'a pas le droit d'effectuer l'opération."""

    def __init__(self, motif: str) -> None:
        super().__init__(motif)


class SuppressionInterditeException(Exception):
    """Levée lorsqu'un ticket ne peut plus être supprimé."""

    def __init__(self, motif: str) -> None:
        super().__init__(motif)


class ArtefactInvalideException(Exception):
    """Levée lorsqu'un artefact de description est inconnu ou introuvable."""

    def __init__(self, motif: str) -> None:
        super().__init__(motif)
