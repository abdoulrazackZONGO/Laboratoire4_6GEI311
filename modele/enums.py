from __future__ import annotations

from enum import Enum


class Statut(Enum):
    """Statuts possibles d'un ticket."""

    OUVERT = "OUVERT"
    ASSIGNE = "ASSIGNE"
    VALIDATION = "VALIDATION"
    TERMINE = "TERMINE"
    FERME = "FERME"


class Priorite(Enum):
    """Niveaux de priorité d'un ticket."""

    BASSE = "BASSE"
    MOYENNE = "MOYENNE"
    HAUTE = "HAUTE"
    CRITIQUE = "CRITIQUE"
