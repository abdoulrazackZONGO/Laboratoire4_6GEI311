"""Objets de lecture : ce que la GUI voit des données du serveur (C2).

Le serveur répond en JSON (voir openapi.yaml). Ces classes transforment ce JSON en objets
qui exposent les mêmes noms de propriétés que le modèle du lab 3 (ticketID, title, priority,
status, creator.name, comments, description.elements...), pour que les vues changent le moins
possible. Ils sont en lecture seule et se comparent par identifiant : chaque rafraîchissement
crée de nouveaux objets, donc `is` ne convient plus.

Un JSON qui ne respecte pas le contrat lève ReponseInvalide, comme une réponse illisible.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar

from ihm.passerelle.erreurs import ReponseInvalide
from modele.enums import Priorite, Statut

if TYPE_CHECKING:
    from collections.abc import Callable

ObjetJSON = dict[str, Any]
T = TypeVar("T")


# ------------------------------------------------------------------ lecture du JSON


def _construire(nom: str, fabrique: Callable[[], T]) -> T:
    """Exécute la lecture d'un objet ; tout écart au contrat devient ReponseInvalide."""
    try:
        return fabrique()
    except (KeyError, TypeError, ValueError, AttributeError) as erreur:
        raise ReponseInvalide(
            f"{nom} illisible dans la réponse du serveur ({type(erreur).__name__} : {erreur})",
            200,
        ) from erreur


def _champ(donnees: ObjetJSON, cle: str, classe: type[T]) -> T:
    """Champ obligatoire du type attendu (bool n'est pas accepté pour un int)."""
    valeur = donnees[cle]
    if not isinstance(valeur, classe) or (classe is int and isinstance(valeur, bool)):
        raise TypeError(f"{cle} doit être de type {classe.__name__}")
    return valeur


def _champOptionnel(donnees: ObjetJSON, cle: str, classe: type[T]) -> T | None:
    return _champ(donnees, cle, classe) if cle in donnees else None


def _date(donnees: ObjetJSON, cle: str) -> date:
    return date.fromisoformat(_champ(donnees, cle, str))


def _enum(donnees: ObjetJSON, cle: str, classe: type[Enum]) -> Any:
    nom = _champ(donnees, cle, str)
    if nom not in classe.__members__:
        raise ValueError(f"{cle} : valeur inconnue « {nom} »")
    return classe[nom]


def _liste(donnees: ObjetJSON, cle: str) -> list[Any]:
    return _champ(donnees, cle, list)


# ------------------------------------------------------------------ acteurs et éléments


class ActeurLu:
    """Acteur du système. Vient d'un Acteur du contrat (id, nom, courriel, role) ou d'un
    ActeurRef (id, nom seulement) : email et role valent alors None."""

    def __init__(
        self, id: int, name: str, email: str | None = None, role: str | None = None
    ) -> None:
        self._id: int = id
        self._name: str = name
        self._email: str | None = email
        self._role: str | None = role

    @classmethod
    def depuisJSON(cls, donnees: ObjetJSON) -> ActeurLu:
        def lire() -> ActeurLu:
            return cls(
                _champ(donnees, "id", int),
                _champ(donnees, "nom", str),
                _champOptionnel(donnees, "courriel", str),
                _champOptionnel(donnees, "role", str),
            )

        return _construire("Acteur", lire)

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def email(self) -> str | None:
        return self._email

    @property
    def role(self) -> str | None:
        return self._role

    def __eq__(self, autre: object) -> bool:
        if not isinstance(autre, ActeurLu):
            return NotImplemented
        return self._id == autre._id

    def __hash__(self) -> int:
        return hash(("acteur", self._id))

    def __repr__(self) -> str:
        return f"ActeurLu(id={self._id}, name={self._name!r})"


@dataclass(frozen=True)
class CommentaireLu:
    """Commentaire d'un ticket, avec les mêmes champs que modele.commentaire.Commentaire."""

    texte: str
    auteur: ActeurLu
    date: date

    @classmethod
    def depuisJSON(cls, donnees: ObjetJSON) -> CommentaireLu:
        def lire() -> CommentaireLu:
            return cls(
                _champ(donnees, "texte", str),
                ActeurLu.depuisJSON(_champ(donnees, "auteur", dict)),
                _date(donnees, "date"),
            )

        return _construire("Commentaire", lire)


# Valeurs de ElementDescription.type dans le contrat.
TYPES_ELEMENTS: frozenset[str] = frozenset({"texte_saisi", "texte", "image", "video"})


@dataclass(frozen=True)
class ElementLu:
    """Élément de description. typeArtefact vaut "texte", "image" ou "video", comme dans le
    modèle : un texte saisi est un "texte" (le contrat le distingue par texte_saisi).

    contenu n'existe que pour un texte, url que pour une image ; sinon None.
    """

    typeArtefact: str
    nom: str
    resume: str
    contenu: str | None = None
    url: str | None = None

    @classmethod
    def depuisJSON(cls, donnees: ObjetJSON) -> ElementLu:
        def lire() -> ElementLu:
            type_ = _champ(donnees, "type", str)
            if type_ not in TYPES_ELEMENTS:
                raise ValueError(f"type : valeur inconnue « {type_} »")
            return cls(
                "texte" if type_ == "texte_saisi" else type_,
                _champ(donnees, "nom", str),
                _champ(donnees, "resume", str),
                _champOptionnel(donnees, "contenu", str),
                _champOptionnel(donnees, "url", str),
            )

        return _construire("Élément de description", lire)


class DescriptionLue:
    """Description d'un ticket : liste ordonnée d'éléments, comme description.Description."""

    def __init__(self, elements: list[ElementLu]) -> None:
        self._elements: list[ElementLu] = list(elements)

    @property
    def elements(self) -> list[ElementLu]:
        return list(self._elements)

    @property
    def nombreElements(self) -> int:
        return len(self._elements)


# ------------------------------------------------------------------ tickets


class TicketRefLu:
    """Ticket réduit à son identifiant, son titre et sa priorité (ce que contient un brouillon).

    Deux tickets se comparent par identifiant, qu'ils soient réduits ou complets.
    """

    def __init__(self, ticketID: int, title: str, priority: Priorite) -> None:
        self._ticketID: int = ticketID
        self._title: str = title
        self._priority: Priorite = priority

    @classmethod
    def depuisJSON(cls, donnees: ObjetJSON) -> TicketRefLu:
        def lire() -> TicketRefLu:
            return cls(
                _champ(donnees, "id", int),
                _champ(donnees, "titre", str),
                _enum(donnees, "priorite", Priorite),
            )

        return _construire("Ticket de brouillon", lire)

    @property
    def ticketID(self) -> int:
        return self._ticketID

    @property
    def title(self) -> str:
        return self._title

    @property
    def priority(self) -> Priorite:
        return self._priority

    def __eq__(self, autre: object) -> bool:
        if not isinstance(autre, TicketRefLu):
            return NotImplemented
        return self._ticketID == autre._ticketID

    def __hash__(self) -> int:
        return hash(("ticket", self._ticketID))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(ticketID={self._ticketID}, title={self._title!r})"


class TicketLu(TicketRefLu):
    """Ticket tel que le serveur le décrit, avec les propriétés du Ticket du modèle.

    Venu d'une liste (TicketResume), il ne connaît que le nombre de commentaires : comments
    et description lèvent RuntimeError tant qu'on n'a pas lu le détail (estDetaille est faux).
    Venu de GET /ticket/{id} (TicketDetail), il a tout.
    """

    def __init__(
        self,
        *,
        ticketID: int,
        title: str,
        priority: Priorite,
        status: Statut,
        creationDate: date,
        updateDate: date,
        creator: ActeurLu | None,
        assignedUser: ActeurLu | None,
        aDejaEteAssigne: bool,
        transitionsPermises: frozenset[Statut],
        nombreCommentaires: int,
        comments: list[CommentaireLu] | None = None,
        description: DescriptionLue | None = None,
    ) -> None:
        super().__init__(ticketID, title, priority)
        self._status: Statut = status
        self._creationDate: date = creationDate
        self._updateDate: date = updateDate
        self._creator: ActeurLu | None = creator
        self._assignedUser: ActeurLu | None = assignedUser
        self._aDejaEteAssigne: bool = aDejaEteAssigne
        self._transitionsPermises: frozenset[Statut] = transitionsPermises
        self._nombreCommentaires: int = nombreCommentaires
        self._comments: list[CommentaireLu] | None = (
            list(comments) if comments is not None else None
        )
        self._description: DescriptionLue | None = description

    @classmethod
    def depuisJSON(cls, donnees: ObjetJSON) -> TicketLu:
        """Lit un TicketResume, ou un TicketDetail s'il a commentaires et description."""

        def acteur(cle: str) -> ActeurLu | None:
            valeur = donnees[cle]
            return None if valeur is None else ActeurLu.depuisJSON(valeur)

        def lire() -> TicketLu:
            detaille = "commentaires" in donnees and "description" in donnees
            comments = description = None
            if detaille:
                comments = [CommentaireLu.depuisJSON(c) for c in _liste(donnees, "commentaires")]
                description = DescriptionLue(
                    [ElementLu.depuisJSON(e) for e in _liste(donnees, "description")]
                )
            return cls(
                ticketID=_champ(donnees, "id", int),
                title=_champ(donnees, "titre", str),
                priority=_enum(donnees, "priorite", Priorite),
                status=_enum(donnees, "statut", Statut),
                creationDate=_date(donnees, "dateCreation"),
                updateDate=_date(donnees, "dateMiseAJour"),
                creator=acteur("createur"),
                assignedUser=acteur("assigne"),
                aDejaEteAssigne=_champ(donnees, "dejaAssigne", bool),
                transitionsPermises=frozenset(
                    Statut[nom] for nom in _liste(donnees, "transitionsPermises")
                ),
                nombreCommentaires=_champ(donnees, "nombreCommentaires", int),
                comments=comments,
                description=description,
            )

        return _construire("Ticket", lire)

    @property
    def status(self) -> Statut:
        return self._status

    @property
    def creationDate(self) -> date:
        return self._creationDate

    @property
    def updateDate(self) -> date:
        return self._updateDate

    @property
    def creator(self) -> ActeurLu | None:
        return self._creator

    @property
    def assignedUser(self) -> ActeurLu | None:
        return self._assignedUser

    @property
    def aDejaEteAssigne(self) -> bool:
        return self._aDejaEteAssigne

    @property
    def transitionsPermises(self) -> frozenset[Statut]:
        """Statuts accessibles depuis le statut courant, tels que le serveur les donne."""
        return self._transitionsPermises

    def transitionPossible(self, nouveau_statut: Statut) -> bool:
        """Sert à activer ou griser un bouton, sans recopier les règles de la machine à états."""
        return nouveau_statut in self._transitionsPermises

    @property
    def nombreCommentaires(self) -> int:
        """Connu pour un ticket de liste comme pour un ticket détaillé."""
        return self._nombreCommentaires

    @property
    def estDetaille(self) -> bool:
        return self._comments is not None

    @property
    def comments(self) -> list[CommentaireLu]:
        if self._comments is None:
            raise RuntimeError(self._messageResume("ses commentaires"))
        return list(self._comments)

    @property
    def description(self) -> DescriptionLue:
        if self._description is None:
            raise RuntimeError(self._messageResume("sa description"))
        return self._description

    def _messageResume(self, quoi: str) -> str:
        return (
            f"Le ticket #{self._ticketID} vient d'une liste : {quoi} ne sont pas chargés "
            f"(lire le détail avec SourceTickets.lireDetail)"
        )


# ------------------------------------------------------------------ brouillons et rapports


class BrouillonLu:
    """Brouillon du serveur, avec les propriétés de la session du modèle (SessionEdition).

    Un brouillon se compare par identifiant : ceux d'un même acteur sont distincts.
    """

    def __init__(
        self,
        *,
        id: int,
        estCreation: bool,
        libelle: str,
        ticket: TicketRefLu,
        proprietaire: ActeurLu,
        estOuverte: bool,
        estEnPause: bool,
        modificationsEnAttente: list[str],
        nombreImages: int,
        texteBrouillon: str,
    ) -> None:
        self._id: int = id
        self._estCreation: bool = estCreation
        self._libelle: str = libelle
        self._ticket: TicketRefLu = ticket
        self._proprietaire: ActeurLu = proprietaire
        self._estOuverte: bool = estOuverte
        self._estEnPause: bool = estEnPause
        self._modificationsEnAttente: list[str] = list(modificationsEnAttente)
        self._nombreImages: int = nombreImages
        self._texteBrouillon: str = texteBrouillon

    @classmethod
    def depuisJSON(cls, donnees: ObjetJSON) -> BrouillonLu:
        def lire() -> BrouillonLu:
            type_ = _champ(donnees, "type", str)
            if type_ not in ("creation", "edition"):
                raise ValueError(f"type : valeur inconnue « {type_} »")
            modifications = _liste(donnees, "modificationsEnAttente")
            if not all(isinstance(m, str) for m in modifications):
                raise TypeError("modificationsEnAttente doit contenir des textes")
            return cls(
                id=_champ(donnees, "id", int),
                estCreation=type_ == "creation",
                libelle=_champ(donnees, "libelle", str),
                ticket=TicketRefLu.depuisJSON(_champ(donnees, "ticket", dict)),
                proprietaire=ActeurLu.depuisJSON(_champ(donnees, "proprietaire", dict)),
                estOuverte=_champ(donnees, "ouverte", bool),
                estEnPause=_champ(donnees, "enPause", bool),
                modificationsEnAttente=modifications,
                nombreImages=_champ(donnees, "nombreImages", int),
                texteBrouillon=_champ(donnees, "texteBrouillon", str),
            )

        return _construire("Brouillon", lire)

    @property
    def id(self) -> int:
        return self._id

    @property
    def estCreation(self) -> bool:
        """Vrai pour un brouillon de création : son ticket n'est pas encore dans le dépôt."""
        return self._estCreation

    @property
    def libelle(self) -> str:
        return self._libelle

    @property
    def ticket(self) -> TicketRefLu:
        return self._ticket

    @property
    def proprietaire(self) -> ActeurLu:
        return self._proprietaire

    @property
    def estOuverte(self) -> bool:
        return self._estOuverte

    @property
    def estEnPause(self) -> bool:
        return self._estEnPause

    @property
    def modificationsEnAttente(self) -> list[str]:
        return list(self._modificationsEnAttente)

    @property
    def nombreImages(self) -> int:
        return self._nombreImages

    @property
    def texteBrouillon(self) -> str:
        """Texte gardé sur le serveur pendant la pause."""
        return self._texteBrouillon

    def __eq__(self, autre: object) -> bool:
        if not isinstance(autre, BrouillonLu):
            return NotImplemented
        return self._id == autre._id

    def __hash__(self) -> int:
        return hash(("brouillon", self._id))

    def __repr__(self) -> str:
        return f"BrouillonLu(id={self._id}, ticket={self._ticket.ticketID})"


class RapportLu:
    """Bilan de l'application d'un brouillon ou d'un lot, comme sessions.RapportExecution.

    refus est une liste de couples (opération, motif). libelle et ticketId s'y ajoutent :
    le modèle les passait à part, ticketId vaut None pour un lot.
    """

    def __init__(
        self,
        *,
        libelle: str,
        succes: list[str],
        refus: list[tuple[str, str]],
        ticketId: int | None,
    ) -> None:
        self._libelle: str = libelle
        self._succes: list[str] = list(succes)
        self._refus: list[tuple[str, str]] = list(refus)
        self._ticketId: int | None = ticketId

    @classmethod
    def depuisJSON(cls, donnees: ObjetJSON) -> RapportLu:
        def lire() -> RapportLu:
            succes = _liste(donnees, "succes")
            if not all(isinstance(s, str) for s in succes):
                raise TypeError("succes doit contenir des textes")
            refus = [
                (_champ(r, "operation", str), _champ(r, "motif", str))
                for r in _liste(donnees, "refus")
            ]
            ticketId = _champ(donnees, "ticketId", int) if donnees["ticketId"] is not None else None
            rapport = cls(
                libelle=_champ(donnees, "libelle", str),
                succes=succes,
                refus=refus,
                ticketId=ticketId,
            )
            # Les compteurs du contrat doivent concorder avec les listes.
            if (
                _champ(donnees, "nombreSucces", int) != rapport.nombreSucces
                or _champ(donnees, "nombreRefus", int) != rapport.nombreRefus
            ):
                raise ValueError("nombreSucces ou nombreRefus ne concorde pas avec les listes")
            return rapport

        return _construire("Rapport", lire)

    @property
    def libelle(self) -> str:
        return self._libelle

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

    @property
    def ticketId(self) -> int | None:
        return self._ticketId
