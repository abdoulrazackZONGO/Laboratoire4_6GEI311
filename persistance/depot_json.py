"""Persistance JSON : sauvegarde et rechargement de tout le système de tickets."""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from acteurs.admin import Admin
from acteurs.user import User
from description.fabrique_description import FabriqueDescription
from modele.commentaire import Commentaire
from modele.enums import Priorite, Statut
from modele.exceptions import ArtefactInvalideException
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket

if TYPE_CHECKING:
    from acteurs.utilisateur_systeme import UtilisateurSysteme
    from description.element_description import ElementDescription


class PersistanceException(Exception):
    """Levée lorsqu'un fichier de sauvegarde est illisible ou incohérent."""


class DepotJSON:
    """Sauvegarde et recharge le système (utilisateurs et tickets) dans un fichier JSON.

    Les artefacts de description sont sauvegardés par leur chemin, comme au
    labo 2 : les fichiers eux-mêmes ne sont pas copiés. Un texte saisi, qui n'a
    pas de fichier, est sauvegardé avec son contenu. Les brouillons (sessions
    non appliquées) ne sont pas sauvegardés.
    """

    VERSION = 1
    _ROLES: dict[str, type[UtilisateurSysteme]] = {"User": User, "Admin": Admin}

    def __init__(self, chemin: str | os.PathLike[str]) -> None:
        self._chemin: Path = Path(chemin)
        self._avertissements: list[str] = []

    @property
    def chemin(self) -> Path:
        return self._chemin

    @property
    def avertissements(self) -> list[str]:
        """Problèmes non bloquants du dernier chargement (artefact introuvable, par exemple)."""
        return list(self._avertissements)

    def existe(self) -> bool:
        return self._chemin.is_file()

    # ------------------------------------------------------------------ sauvegarde

    def sauvegarder(self, systeme: SystemeTickets) -> None:
        """Écrit tout le système ; un fichier existant n'est remplacé qu'une fois l'écriture finie."""
        utilisateurs = self._utilisateursASauvegarder(systeme)
        donnees = {
            "version": self.VERSION,
            "utilisateurs": [self._utilisateurVersDict(u) for u in utilisateurs],
            "tickets": [self._ticketVersDict(t) for t in systeme.tickets],
        }
        temporaire = self._chemin.with_name(self._chemin.name + ".tmp")
        temporaire.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
        # Remplacement atomique : en cas d'arrêt brutal, l'ancienne sauvegarde reste intacte.
        os.replace(temporaire, self._chemin)

    def _utilisateursASauvegarder(self, systeme: SystemeTickets) -> list[UtilisateurSysteme]:
        """L'annuaire, complété par les utilisateurs cités dans les tickets."""
        utilisateurs = list(systeme.utilisateurs)
        for ticket in systeme.tickets:
            cites = [ticket.creator, ticket.assignedUser] + [c.auteur for c in ticket.comments]
            for utilisateur in cites:
                if utilisateur is not None and all(utilisateur is not u for u in utilisateurs):
                    utilisateurs.append(utilisateur)
        identifiants = [u.id for u in utilisateurs]
        doublons = sorted({i for i in identifiants if identifiants.count(i) > 1})
        if doublons:
            raise PersistanceException(
                f"Sauvegarde impossible : identifiants d'utilisateur en double {doublons}"
            )
        return utilisateurs

    @staticmethod
    def _utilisateurVersDict(utilisateur: UtilisateurSysteme) -> dict[str, Any]:
        return {
            "id": utilisateur.id,
            "name": utilisateur.name,
            "email": utilisateur.email,
            "role": utilisateur.role,
        }

    def _ticketVersDict(self, ticket: Ticket) -> dict[str, Any]:
        return {
            "ticketID": ticket.ticketID,
            "title": ticket.title,
            "priority": ticket.priority.name,
            "status": ticket.status.name,
            "creationDate": ticket.creationDate.isoformat(),
            "updateDate": ticket.updateDate.isoformat(),
            "creator": ticket.creator.id if ticket.creator is not None else None,
            "assignedUser": ticket.assignedUser.id if ticket.assignedUser is not None else None,
            "aDejaEteAssigne": ticket.aDejaEteAssigne,
            "comments": [
                {"texte": c.texte, "auteur": c.auteur.id, "date": c.date.isoformat()}
                for c in ticket.comments
            ],
            "description": [self._elementVersDict(e) for e in ticket.description.elements],
        }

    @staticmethod
    def _elementVersDict(element: ElementDescription) -> dict[str, Any]:
        # Le texte saisi partage le type "texte" avec le texte issu d'un fichier ; on le
        # distingue par ses propriétés publiques, sans isinstance (seule la fabrique connaît
        # les sous-classes concrètes) : il n'a pas de chemin, car validerChemin() exige un
        # fichier existant pour tout autre élément. Il est donc sauvegardé par son contenu.
        if element.typeArtefact == "texte" and not element.chemin:
            return {"type": "texte_saisi", "contenu": element.contenu}
        return {"type": element.typeArtefact, "chemin": element.chemin}

    # ------------------------------------------------------------------ chargement

    def charger(self) -> SystemeTickets:
        """Reconstruit un système complet ; les artefacts introuvables sont ignorés et signalés."""
        self._avertissements = []
        try:
            donnees = json.loads(self._chemin.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise
        except (OSError, json.JSONDecodeError) as erreur:
            raise PersistanceException(f"Fichier de sauvegarde illisible : {erreur}") from erreur
        if not isinstance(donnees, dict) or donnees.get("version") != self.VERSION:
            raise PersistanceException(
                f"Version de sauvegarde non prise en charge : {self._version(donnees)!r} "
                f"(attendue : {self.VERSION})"
            )
        try:
            systeme = SystemeTickets()
            parId = self._chargerUtilisateurs(donnees["utilisateurs"], systeme)
            for dictTicket in donnees["tickets"]:
                systeme.ajouterTicket(self._ticketDepuisDict(dictTicket, parId))
        except (KeyError, TypeError, ValueError) as erreur:
            raise PersistanceException(f"Fichier de sauvegarde incohérent : {erreur!r}") from erreur
        return systeme

    @staticmethod
    def _version(donnees: Any) -> Any:
        return donnees.get("version") if isinstance(donnees, dict) else None

    def _chargerUtilisateurs(
        self, liste: list[dict[str, Any]], systeme: SystemeTickets
    ) -> dict[int, UtilisateurSysteme]:
        parId: dict[int, UtilisateurSysteme] = {}
        for d in liste:
            classe = self._ROLES.get(d["role"])
            if classe is None:
                raise ValueError(f"rôle inconnu : {d['role']}")
            utilisateur = classe(d["id"], d["name"], d["email"], systeme)
            systeme.inscrireUtilisateur(utilisateur)
            parId[utilisateur.id] = utilisateur
        return parId

    def _ticketDepuisDict(
        self, d: dict[str, Any], parId: dict[int, UtilisateurSysteme]
    ) -> Ticket:
        def utilisateur(identifiant: int | None) -> Any:
            if identifiant is None:
                return None
            if identifiant not in parId:
                raise ValueError(f"utilisateur inconnu : {identifiant}")
            return parId[identifiant]

        return Ticket.restaurer(
            ticketID=d["ticketID"],
            title=d["title"],
            priority=Priorite[d["priority"]],
            status=Statut[d["status"]],
            creationDate=date.fromisoformat(d["creationDate"]),
            updateDate=date.fromisoformat(d["updateDate"]),
            creator=utilisateur(d["creator"]),
            assignedUser=utilisateur(d["assignedUser"]),
            aDejaEteAssigne=d["aDejaEteAssigne"],
            comments=[
                Commentaire(c["texte"], utilisateur(c["auteur"]), date.fromisoformat(c["date"]))
                for c in d["comments"]
            ],
            elements=self._elementsDepuisListe(d["ticketID"], d["description"]),
        )

    def _elementsDepuisListe(
        self, ticketID: int, liste: list[dict[str, Any]]
    ) -> list[ElementDescription]:
        elements: list[ElementDescription] = []
        for d in liste:
            try:
                if d["type"] == "texte_saisi":
                    element = FabriqueDescription.creerSaisie(d["contenu"])
                else:
                    element = FabriqueDescription.creer(d["type"], d["chemin"])
                element.traiter()
            except ArtefactInvalideException as erreur:
                self._avertissements.append(f"Ticket #{ticketID} : élément ignoré ({erreur})")
                continue
            elements.append(element)
        return elements
