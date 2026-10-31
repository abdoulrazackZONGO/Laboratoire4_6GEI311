"""Génère donnees/demo.json et ses images avec l'API du modèle.

Lancer depuis n'importe quel dossier :  python outils/generer_demo.py
Relancer le script écrase les fichiers sous les mêmes noms, sans créer de doublons.
"""
from __future__ import annotations

import os
import struct
import sys
import zlib
from pathlib import Path

# Lancé comme script, Python met outils/ sur sys.path, et non la racine du dépôt.
RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from acteurs.admin import Admin  # noqa: E402
from acteurs.user import User  # noqa: E402
from modele.enums import Priorite  # noqa: E402
from modele.systeme_tickets import SystemeTickets  # noqa: E402
from modele.ticket import Ticket  # noqa: E402
from persistance.depot_json import DepotJSON  # noqa: E402

CHEMIN_DEMO = "donnees/demo.json"
DOSSIER_IMAGES = Path("donnees/images")

Couleur = tuple[int, int, int]

# Chaque image de 400 x 250 px : bandes horizontales (hauteur en pixels, couleur RVB).
IMAGES: dict[str, list[tuple[int, Couleur]]] = {
    "connexion": [
        (30, (45, 55, 72)), (70, (243, 244, 246)), (30, (255, 255, 255)),
        (20, (243, 244, 246)), (30, (37, 99, 235)), (20, (243, 244, 246)),
        (30, (220, 38, 38)), (20, (243, 244, 246)),
    ],
    "affichage_mobile": [
        (30, (88, 28, 135)), (40, (250, 245, 255)), (60, (234, 88, 12)),
        (40, (250, 245, 255)), (50, (147, 51, 234)), (30, (250, 245, 255)),
    ],
    "paiement": [
        (30, (6, 95, 70)), (60, (240, 253, 244)), (30, (255, 255, 255)),
        (30, (240, 253, 244)), (50, (185, 28, 28)), (50, (240, 253, 244)),
    ],
}

TEXTE_BUG_CONNEXION = (
    "Bug : impossible de se connecter à l'application.\n"
    "Depuis la dernière mise à jour, la page de connexion affiche « Identifiants invalides » "
    "même lorsque le nom d'utilisateur et le mot de passe sont corrects."
)


def ecrirePng(chemin: Path, bandes: list[tuple[int, Couleur]], largeur: int = 400) -> None:
    """PNG RVB 8 bits sans dépendance : zlib compresse les pixels, struct code les blocs."""
    pixels = bytearray()
    for hauteur, couleur in bandes:
        # Chaque ligne commence par l'octet de filtre 0 (aucun filtre).
        pixels += (b"\x00" + bytes(couleur) * largeur) * hauteur

    def bloc(nature: bytes, donnees: bytes) -> bytes:
        crc = zlib.crc32(nature + donnees) & 0xFFFFFFFF
        return struct.pack(">I", len(donnees)) + nature + donnees + struct.pack(">I", crc)

    entete = struct.pack(">IIBBBBB", largeur, sum(h for h, _ in bandes), 8, 2, 0, 0, 0)
    chemin.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + bloc(b"IHDR", entete)
        + bloc(b"IDAT", zlib.compress(bytes(pixels), 9))
        + bloc(b"IEND", b"")
    )


def cheminImage(nom: str) -> str:
    """Nom fixe, relatif à la racine et en notation POSIX, comme StockageImages."""
    return (DOSSIER_IMAGES / f"demo_{nom}.png").as_posix()


def creer(
    user: User,
    ticketID: int,
    titre: str,
    priorite: Priorite,
    texte: str,
    images: tuple[str, ...] = (),
    commentaires: tuple[str, ...] = (),
) -> Ticket:
    """Crée un ticket par une session de création, comme le fera l'interface."""
    ticket = Ticket(ticketID, titre, priorite)
    session = user.ouvrirSessionCreation(ticket)
    session.ajouterTexteSaisi(texte)
    for nom in images:
        session.ajouterElement("image", cheminImage(nom))
    for commentaire in commentaires:
        session.ajouterCommentaire(commentaire)
    rapport = session.appliquer()
    if rapport.nombreRefus:
        raise RuntimeError(f"Ticket #{ticketID} : modifications refusées {rapport.refus}")
    return ticket


def construireSysteme() -> SystemeTickets:
    """Les acteurs de main.py et les 8 tickets des maquettes ; aucune vidéo."""
    systeme = SystemeTickets()
    ambroise = Admin(1, "Ambroise Fleury", "ambroise.fleury@uqac.ca", systeme)
    abdoul = User(2, "Abdoul Razack", "abdoul.razack@uqac.ca", systeme)
    julien = User(3, "T Julien", "t.julien@uqac.ca", systeme)
    mike = User(4, "Mike Tonny", "mike.tonny@uqac.ca", systeme)
    hein = User(5, "Hein Tommy", "hein.tommy@uqac.ca", systeme)
    for acteur in (ambroise, abdoul, julien, mike, hein):
        systeme.inscrireUtilisateur(acteur)

    t1 = creer(
        abdoul, 1, "Bug de connexion", Priorite.HAUTE, TEXTE_BUG_CONNEXION,
        images=("connexion",),
        commentaires=(
            "Le bug se reproduit sur Chrome et Firefox.",
            "Capture d'écran jointe à la description.",
        ),
    )
    t2 = creer(
        abdoul, 2, "Erreur d'affichage mobile", Priorite.MOYENNE,
        "Sur téléphone, le tableau des tickets dépasse de l'écran et le menu cache le contenu.",
        images=("affichage_mobile",),
    )
    t3 = creer(
        julien, 3, "Export CSV", Priorite.BASSE,
        "Pouvoir exporter la liste des tickets au format CSV.",
    )
    creer(
        julien, 6, "Bouton Annuler inactif", Priorite.MOYENNE,
        "Dans le formulaire de création, le bouton « Annuler » ne ferme pas la fenêtre.",
    )
    creer(
        mike, 7, "Lenteur de la recherche", Priorite.HAUTE,
        "La recherche de tickets prend plus de dix secondes au-delà de mille tickets.",
    )
    t8 = creer(
        hein, 8, "Erreur 500 au paiement", Priorite.CRITIQUE,
        "Le serveur renvoie une erreur 500 à la validation d'un paiement par carte.",
        images=("paiement",),
    )
    t9 = creer(
        julien, 9, "Faute dans le menu Aide", Priorite.BASSE,
        "Le menu Aide affiche « Aide en lgine » au lieu de « Aide en ligne ».",
    )
    t10 = creer(
        mike, 10, "Notification en double", Priorite.MOYENNE,
        "Chaque nouveau commentaire envoie deux notifications identiques.",
    )

    # Cycle de vie par les méthodes des acteurs, jamais par la machine à états directement.
    ambroise.assignTicket(t1, mike)
    mike.soumettreValidation(t1)
    ambroise.validerTicket(t1)  # TERMINE
    ambroise.assignTicket(t2, hein)  # ASSIGNE
    ambroise.closeTicket(t3)  # FERME, jamais assigné
    ambroise.assignTicket(t8, mike)
    mike.soumettreValidation(t8)  # VALIDATION
    ambroise.assignTicket(t9, abdoul)  # ASSIGNE
    ambroise.assignTicket(t10, julien)  # ASSIGNE
    return systeme


def main() -> None:
    # Chemins relatifs à la racine du dépôt, comme dans l'application.
    os.chdir(RACINE)
    DOSSIER_IMAGES.mkdir(parents=True, exist_ok=True)
    # Les images d'abord : ajouterElement() vérifie que le fichier existe.
    for nom, bandes in IMAGES.items():
        ecrirePng(Path(cheminImage(nom)), bandes)
    systeme = construireSysteme()
    DepotJSON(CHEMIN_DEMO).sauvegarder(systeme)
    print(
        f"{CHEMIN_DEMO} : {len(systeme.utilisateurs)} acteurs, "
        f"{len(systeme.tickets)} tickets, {len(IMAGES)} images"
    )


if __name__ == "__main__":
    main()
