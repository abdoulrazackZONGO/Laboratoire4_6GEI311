from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from acteurs.utilisateur_systeme import UtilisateurSysteme


@dataclass(frozen=True)
class Commentaire:
    """Commentaire immuable attaché à un ticket."""

    texte: str
    auteur: UtilisateurSysteme
    date: date
