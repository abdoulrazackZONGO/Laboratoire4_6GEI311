from __future__ import annotations

from typing import TYPE_CHECKING

from acteurs.admin import Admin
from acteurs.user import User
from modele.enums import Priorite, Statut
from modele.exceptions import (
    AccesRefuseException,
    SessionIndisponibleException,
    SuppressionInterditeException,
    TransitionInvalideException,
)
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket

if TYPE_CHECKING:
    from acteurs.utilisateur_systeme import UtilisateurSysteme


def afficherBandeau(lettre: str, titre: str) -> None:
    print()
    print("=" * 70)
    print(f"{lettre}. {titre}")
    print("=" * 70)


def nomDe(utilisateur: UtilisateurSysteme | None) -> str:
    return utilisateur.name if utilisateur is not None else "aucun"


def instantane(ticket: Ticket) -> tuple[Statut, str, int, int]:
    """Photographie : statut, assigné, nombre de commentaires, nombre d'éléments."""
    return (
        ticket.status,
        nomDe(ticket.assignedUser),
        len(ticket.comments),
        ticket.description.nombreElements,
    )


def afficherInchange(ticket: Ticket, avant: tuple[Statut, str, int, int]) -> None:
    apres = instantane(ticket)
    verdict = "OUI" if apres == avant else "NON"
    statut, assigne, nbCommentaires, nbElements = apres
    print(
        f"Résultat : ticket inchangé ? {verdict} (T{ticket.ticketID} : statut {statut.name}, "
        f"assigné : {assigne}, {nbCommentaires} commentaire(s), {nbElements} élément(s))"
    )


def main() -> None:
    systeme = SystemeTickets()
    ambroise = Admin(1, "Ambroise Fleury", "ambroise.fleury@uqac.ca", systeme)
    abdoul = User(2, "Abdoul Razack", "abdoul.razack@uqac.ca", systeme)
    julien = User(3, "T Julien", "t.julien@uqac.ca", systeme)
    mike = User(4, "Mike Tonny", "mike.tonny@uqac.ca", systeme)
    hein = User(5, "Hein Tommy", "hein.tommy@uqac.ca", systeme)

    # ------------------------------------------------------------------
    afficherBandeau("A", "Création des tickets")
    t1 = Ticket(1, "Bug de connexion", Priorite.HAUTE)
    t2 = Ticket(2, "Erreur d'affichage mobile", Priorite.MOYENNE)
    t3 = Ticket(3, "Export CSV", Priorite.BASSE)
    t4 = Ticket(4, "Lenteur du tableau de bord", Priorite.MOYENNE)
    for auteur, ticket in ((abdoul, t1), (abdoul, t2), (julien, t3), (julien, t4)):
        print(
            f"Test     : {auteur.name} crée T{ticket.ticketID} « {ticket.title} » "
            f"({ticket.priority.name})"
        )
        createurAvant = ticket.creator
        auteur.createTicket(ticket)
        print(
            f"Résultat : creator avant = {createurAvant}, après = {nomDe(ticket.creator)} ; "
            f"statut initial : {ticket.status.name}"
        )

    # ------------------------------------------------------------------
    afficherBandeau("B", "Agrégat : mesTickets()")
    print("Test     : les tickets d'Abdoul Razack")
    print(f"Résultat : {', '.join(f'T{t.ticketID} « {t.title} »' for t in abdoul.mesTickets())}")
    print("Test     : le ticket n°1 d'Abdoul Razack")
    print(f"Résultat : {', '.join(f'T{t.ticketID} « {t.title} »' for t in abdoul.mesTickets(ids=[1]))}")
    print("Test     : les tickets de T Julien")
    print(f"Résultat : {', '.join(f'T{t.ticketID} « {t.title} »' for t in julien.mesTickets())}")

    # ------------------------------------------------------------------
    afficherBandeau("C", "L'Admin consulte la liste des tickets")
    print("Test     : Ambroise Fleury appelle viewAllTickets()")
    print("Résultat :")
    liste = ambroise.viewAllTickets()
    print(f"Résultat : {len(liste)} ticket(s) retourné(s)")

    # ------------------------------------------------------------------
    afficherBandeau("D", "Session d'édition : modifications en attente")
    avantT1 = instantane(t1)
    print("Test     : Abdoul Razack ouvre une session d'édition sur T1")
    session = abdoul.ouvrirSessionEdition(t1)
    print(f"Résultat : session ouverte ({session.libelle})")
    print("Test     : ajout de 2 commentaires et de 3 éléments (texte, image, vidéo)")
    session.ajouterCommentaire("Le bug se reproduit sur Chrome et Firefox.")
    session.ajouterCommentaire("Capture d'écran et vidéo jointes à la description.")
    session.ajouterElement("texte", "ressources/description_bug.txt")
    session.ajouterElement("image", "ressources/capture_ecran.png")
    session.ajouterElement("video", "ressources/demo_bug.mp4")
    print(f"Résultat : modificationsEnAttente ({len(session.modificationsEnAttente)}) :")
    for numero, libelle in enumerate(session.modificationsEnAttente, start=1):
        print(f"  {numero}. {libelle}")
    print("Test     : T1 a-t-il changé avant appliquer() ?")
    afficherInchange(t1, avantT1)

    # ------------------------------------------------------------------
    afficherBandeau("E", "Annulation de la dernière modification")
    print("Test     : annulation de la dernière modification")
    retiree = session.annulerDerniere()
    print(f"Résultat : modification retirée : {retiree}")
    print(f"Résultat : pile restante ({len(session.modificationsEnAttente)}) :")
    for numero, libelle in enumerate(session.modificationsEnAttente, start=1):
        print(f"  {numero}. {libelle}")
    afficherInchange(t1, avantT1)

    # ------------------------------------------------------------------
    afficherBandeau("F", "Pause et reprise de la session")
    print("Test     : mise en pause de la session")
    session.mettreEnPause()
    print(f"Résultat : estEnPause = {session.estEnPause}")
    print("Test     : ajouterCommentaire() pendant la pause")
    try:
        session.ajouterCommentaire("Commentaire pendant la pause")
    except SessionIndisponibleException as erreur:
        print(f"Résultat : refusé ({type(erreur).__name__}) : {erreur}")
    afficherInchange(t1, avantT1)
    print("Test     : annulation de la dernière modification pendant la pause")
    try:
        session.annulerDerniere()
    except SessionIndisponibleException as erreur:
        print(f"Résultat : refusé ({type(erreur).__name__}) : {erreur}")
    afficherInchange(t1, avantT1)
    print("Test     : application des modifications pendant la pause")
    try:
        session.appliquer()
    except SessionIndisponibleException as erreur:
        print(f"Résultat : refusé ({type(erreur).__name__}) : {erreur}")
    afficherInchange(t1, avantT1)
    print("Test     : reprise, puis nouvel ajout de la vidéo")
    session.reprendre()
    session.ajouterElement("video", "ressources/demo_bug.mp4")
    print(f"Résultat : estEnPause = {session.estEnPause} ; ajout accepté, pile ({len(session.modificationsEnAttente)}) :")
    for numero, libelle in enumerate(session.modificationsEnAttente, start=1):
        print(f"  {numero}. {libelle}")

    # ------------------------------------------------------------------
    afficherBandeau("G", "Application de la session")
    print("Test     : appliquer()")
    rapport = session.appliquer()
    print("Résultat : rapport d'exécution :")
    rapport.afficher()
    print("Test     : T1 reflète-t-il enfin les modifications ?")
    print(
        f"Résultat : {len(t1.comments)} commentaire(s), {t1.description.nombreElements} élément(s) "
        f"(avant : {avantT1[2]} commentaire(s), {avantT1[3]} élément(s))"
    )
    abdoul.viewTicket(t1)
    print("Test     : T1.description.afficher()")
    print("Résultat :")
    t1.description.afficher()
    print("Test     : chargement différé de la vidéo (3e élément de T1)")
    video = t1.description.elements[2]
    print(f"Résultat : estCharge avant chargerContenuReel() : {video.estCharge}") # pyright: ignore[reportAttributeAccessIssue]
    video.chargerContenuReel() # pyright: ignore[reportAttributeAccessIssue]
    print(f"Résultat : estCharge après chargerContenuReel() : {video.estCharge}") # pyright: ignore[reportAttributeAccessIssue]
    print(f"Résultat : {video.resume}")

    # ------------------------------------------------------------------
    afficherBandeau("H", "Session close")
    avantT1 = instantane(t1)
    print("Test     : ajout de commentaire après application de la session")
    try:
        session.ajouterCommentaire("Ajout après application")
    except SessionIndisponibleException as erreur:
        print(f"Résultat : refusé ({type(erreur).__name__}) : {erreur}")
    afficherInchange(t1, avantT1)

    # ------------------------------------------------------------------
    afficherBandeau("I", "Accès refusé à la session d'édition")
    print("Test     : T Julien tente d'ouvrir une session d'édition sur T1")
    try:
        julien.ouvrirSessionEdition(t1)
    except AccesRefuseException as erreur:
        print(f"Résultat : refusé ({type(erreur).__name__}) : {erreur}")
    afficherInchange(t1, avantT1)

    # ------------------------------------------------------------------
    afficherBandeau("J", "Cycle nominal : OUVERT -> ASSIGNE -> VALIDATION -> TERMINE")
    print("Test     : Ambroise Fleury assigne T1 à Mike Tonny")
    ambroise.assignTicket(t1, mike)
    print(f"Résultat : statut {t1.status.name}, assigné : {nomDe(t1.assignedUser)}")
    print("Test     : Mike Tonny soumet T1 en validation")
    mike.soumettreValidation(t1)
    print(f"Résultat : statut {t1.status.name}")
    print("Test     : Ambroise Fleury valide T1")
    ambroise.validerTicket(t1)
    print(f"Résultat : statut {t1.status.name}, assigné : {nomDe(t1.assignedUser)}")

    # ------------------------------------------------------------------
    afficherBandeau("K", "Refus de transition")
    print("Test     : Ambroise Fleury assigne T2 à Mike Tonny")
    ambroise.assignTicket(t2, mike)
    print(f"Résultat : statut {t2.status.name}, assigné : {nomDe(t2.assignedUser)}")
    avantT2 = instantane(t2)
    print("Test     : Hein Tommy tente de soumettre T2 en validation")
    try:
        hein.soumettreValidation(t2)
    except AccesRefuseException as erreur:
        print(f"Résultat : refusé ({type(erreur).__name__}) : {erreur}")
    afficherInchange(t2, avantT2)
    print("Test     : Ambroise Fleury tente de valider T2 depuis ASSIGNE")
    try:
        ambroise.validerTicket(t2)
    except TransitionInvalideException as erreur:
        print(f"Résultat : refusé ({type(erreur).__name__}) : {erreur}")
    afficherInchange(t2, avantT2)

    # ------------------------------------------------------------------
    afficherBandeau("L", "Réassignation directe et rejet de validation")
    print("Test     : Ambroise Fleury réassigne T2 à Hein Tommy (ASSIGNE -> ASSIGNE)")
    assigneAvant = nomDe(t2.assignedUser)
    ambroise.assignTicket(t2, hein)
    print(
        f"Résultat : assigné avant : {assigneAvant} ; après : {nomDe(t2.assignedUser)} ; "
        f"statut {t2.status.name}"
    )
    print("Test     : Hein Tommy soumet T2 en validation")
    hein.soumettreValidation(t2)
    print(f"Résultat : statut {t2.status.name}")
    print("Test     : Ambroise Fleury rejette en réassignant T2 à Mike Tonny (VALIDATION -> ASSIGNE)")
    ambroise.assignTicket(t2, mike)
    print(f"Résultat : statut {t2.status.name}, assigné : {nomDe(t2.assignedUser)}")

    # ------------------------------------------------------------------
    afficherBandeau("M", "Désassignation")
    print("Test     : Ambroise Fleury désassigne T2")
    ambroise.desassignerTicket(t2)
    print(
        f"Résultat : statut {t2.status.name}, assigné : {nomDe(t2.assignedUser)}, "
        f"aDejaEteAssigne : {t2.aDejaEteAssigne}"
    )

    # ------------------------------------------------------------------
    afficherBandeau("N", "Suppression de tickets")
    print("Test     : T Julien supprime T4 (jamais assigné)")
    julien.supprimerTicket(t4)
    print(f"Résultat : accepté ; T4 dans le dépôt : {systeme.contient(t4)}")
    print("Test     : Abdoul Razack tente de supprimer T2 (OUVERT mais déjà assigné)")
    avantT2 = instantane(t2)
    try:
        abdoul.supprimerTicket(t2)
    except SuppressionInterditeException as erreur:
        print(f"Résultat : refusé ({type(erreur).__name__}) : {erreur}")
    afficherInchange(t2, avantT2)
    print(f"Résultat : T2 dans le dépôt : {systeme.contient(t2)}")
    print("Test     : T Julien tente de supprimer T1 (créé par Abdoul Razack)")
    avantT1 = instantane(t1)
    try:
        julien.supprimerTicket(t1)
    except AccesRefuseException as erreur:
        print(f"Résultat : refusé ({type(erreur).__name__}) : {erreur}")
    afficherInchange(t1, avantT1)
    print(f"Résultat : T1 dans le dépôt : {systeme.contient(t1)}")

    # ------------------------------------------------------------------
    afficherBandeau("O", "Fermeture et états terminaux")
    print("Test     : Ambroise Fleury ferme T3 (OUVERT -> FERME)")
    ambroise.closeTicket(t3)
    print(f"Résultat : statut {t3.status.name}")
    print("Test     : Ambroise Fleury tente de fermer T1 (TERMINE)")
    try:
        ambroise.closeTicket(t1)
    except TransitionInvalideException as erreur:
        print(f"Résultat : refusé ({type(erreur).__name__}) : {erreur}")
    afficherInchange(t1, avantT1)
    print("Test     : Ambroise Fleury tente d'assigner T1 (TERMINE) à Hein Tommy")
    try:
        ambroise.assignTicket(t1, hein)
    except TransitionInvalideException as erreur:
        print(f"Résultat : refusé ({type(erreur).__name__}) : {erreur}")
    afficherInchange(t1, avantT1)
    print(f"Résultat : l'assigné de T1 reste {nomDe(t1.assignedUser)}")

    # ------------------------------------------------------------------
    afficherBandeau("P", "Lot administrateur")
    print("Test     : T Julien crée T5 « Erreur d'export » (BASSE)")
    t5 = Ticket(5, "Erreur d'export", Priorite.BASSE)
    julien.createTicket(t5)
    print(f"Résultat : statut {t5.status.name}, T5 dans le dépôt : {systeme.contient(t5)}")
    print("Test     : Ambroise Fleury ouvre un lot et y prépare 4 opérations")
    lot = ambroise.ouvrirLot()
    lot.assigner(t2, hein)
    lot.validerTicket(t2)
    lot.fermer(t1)
    lot.assigner(t5, mike)
    print(f"Résultat : {lot.libelle}, modificationsEnAttente ({len(lot.modificationsEnAttente)}) :")
    for numero, libelle in enumerate(lot.modificationsEnAttente, start=1):
        print(f"  {numero}. {libelle}")
    print("Test     : T Julien supprime T5 avant l'application du lot")
    avantT5 = instantane(t5)
    julien.supprimerTicket(t5)
    print(f"Résultat : T5 dans le dépôt : {systeme.contient(t5)}")
    print("Test     : appliquer() le lot")
    avantT1 = instantane(t1)
    rapport = lot.appliquer()
    print("Résultat : rapport d'exécution :")
    rapport.afficher()
    print(
        f"Résultat : T2 : statut {t2.status.name}, assigné : {nomDe(t2.assignedUser)} "
        f"(assignation appliquée, validation refusée)"
    )
    afficherInchange(t1, avantT1)
    afficherInchange(t5, avantT5)

    # ------------------------------------------------------------------
    afficherBandeau("Q", "Bilan et protections")
    print("Test     : Ambroise Fleury appelle viewAllTickets()")
    print("Résultat :")
    ambroise.viewAllTickets()
    print("Test     : T1.status = Statut.OUVERT")
    avantT1 = instantane(t1)
    try:
        t1.status = Statut.OUVERT # pyright: ignore[reportAttributeAccessIssue]
    except AttributeError as erreur:
        print(f"Résultat : refusé ({type(erreur).__name__}) : {erreur}")
    print(f"Résultat : T1 toujours {t1.status.name}")
    afficherInchange(t1, avantT1)
    print("Test     : méthodes absentes selon le rôle ou le type de session")
    print(f"Résultat : existence attribut (Abdoul Razack, 'viewAllTickets')         = {hasattr(abdoul, 'viewAllTickets')}")
    print(f"Résultat : existence attribut(Ambroise Fleury, 'supprimerTicket')      = {hasattr(ambroise, 'supprimerTicket')}")
    print(f"Résultat : existence attribut(Ambroise Fleury, 'ouvrirSessionEdition') = {hasattr(ambroise, 'ouvrirSessionEdition')}")
    print(f"Résultat : existence attribut(lot, 'mettreEnPause')                    = {hasattr(lot, 'mettreEnPause')}")
    print(f"Résultat : existence attribut(lot, 'annulerDerniere')                  = {hasattr(lot, 'annulerDerniere')}")


if __name__ == "__main__":
    main()
