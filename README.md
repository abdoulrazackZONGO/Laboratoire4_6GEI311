# Laboratoire 4 : système de gestion de tickets en client-serveur, par une API REST

Cours **6GEI311 Architecture des logiciels**

**Équipe :** Zongo T Julien, Zongo A Razack

Le Lab 4 coupe l'application du Lab 3 en deux processus. Un serveur Flask (`serveur.py`) détient le modèle et l'expose par une API REST, décrite dans [`openapi.yaml`](openapi.yaml). La GUI Tkinter (`app.py`) n'appelle plus le modèle : elle passe par cette API, comme la page web servie par le même serveur (bonus). Le rapport du laboratoire est [`Lab4_6GEI311_Rapport.pdf`](Lab4_6GEI311_Rapport.pdf), avec sa source Word dans `documents/`.

Les sections [Lab 4](#lab-4--client-serveur) ci-dessous expliquent comment lancer le serveur et les clients. Les sections suivantes viennent des labs 2 et 3 : elles décrivent les fenêtres et le modèle, qui n'ont pas changé dans leur usage.

## Lab 4 : client-serveur

### Installation

**Prérequis :** Python 3.10 ou plus récent et Git. Le serveur a besoin de Flask ; la GUI n'utilise que la bibliothèque standard.

```bash
git clone https://github.com/abdoulrazackZONGO/Laboratoire4_6GEI311.git
```

```bash
cd Laboratoire4_6GEI311
```

```bash
python -m venv .venv
```

Activer l'environnement (PowerShell : `.venv\Scripts\Activate.ps1`), puis :

```bash
pip install -r requirements.txt
```

### Lancer le serveur et les clients

Dans un premier terminal, le serveur (http://127.0.0.1:5000) :

```bash
python serveur.py
```

Dans un deuxième terminal, la GUI, autant de fois que de fenêtres voulues (option `--url` pour un autre serveur) :

```bash
python app.py
```

La page web s'ouvre dans un navigateur à l'adresse http://127.0.0.1:5000/. Juste avant une démonstration, `python outils/essai_api.py` enchaîne quelques requêtes réelles contre le serveur lancé et affiche chaque code reçu à côté du code attendu.

- **Au démarrage**, le serveur charge `donnees/sauvegarde.json` s'il existe, sinon la démonstration `donnees/demo.json`. Il sauvegarde après chaque modification réussie.
- **Pour repartir de la démonstration**, arrêter le serveur, supprimer `donnees/sauvegarde.json`, puis relancer le serveur.
- Les brouillons (créations et éditions en cours) ne sont pas sauvegardés : un redémarrage du serveur les perd.

### Architecture

| Couche | Paquets | Rôle |
|---|---|---|
| Modèle métier | `modele`, `etats`, `acteurs`, `description`, `commandes`, `sessions` | Toutes les règles ; inchangé sauf quatre ajouts (rapport, section I.3). |
| Persistance | `persistance` | `DepotJSON`, `StockageImages`. |
| Contrôleur (serveur) | `api/` | Routes Flask : identifient l'acteur (`X-Acteur-Id`), vérifient la requête, appellent une méthode métier, sauvegardent, répondent en JSON. |
| Passerelle (client) | `ihm/passerelle` | `ClientAPI`, objets de lecture et `SourceTickets`, qui sonde `GET /version` chaque seconde. |
| Présentation | `ihm/controleurs`, `ihm/vues`, `web/` | Fenêtres F1 à F8 de la GUI, et page web. |

Le contrat de l'API ([`openapi.yaml`](openapi.yaml)) décrit les 21 opérations. Un test vérifie que chaque chemin du contrat existe dans le serveur, et inversement ; un autre vérifie les règles de dépendances entre les couches.

### La page web (bonus)

Le serveur sert une page à l'adresse http://127.0.0.1:5000/ (`web/index.html`, `app.js`, `style.css`), sans framework. Elle ne passe que par l'API, comme la GUI, et reprend ses deux vues : celle de l'Admin (F2) et celle du User (F3). Les captures ci-dessous sont celles de la page réelle, sur les données de démonstration ; elles sont dans `documents/captures_lab4/`.

| Élément | Comportement |
|---|---|
| Connexion | Une liste des acteurs (`GET /acteurs`). Le compte choisi est mémorisé par le navigateur, puis envoyé dans `X-Acteur-Id` à chaque requête. |
| Vue Admin | « Tous les tickets », filtrables par statut. Dans le détail, « Changer le statut » : assigner à un User, désassigner, valider, fermer (`PATCH`). |
| Vue User | « Mes tickets », en deux onglets : « Créés par moi » (`?createur=`) et « Assignés à moi » (`?assigne=`). Dans le détail : soumettre à validation (`PATCH`) et supprimer (`DELETE`). « Nouveau ticket » crée un ticket (`POST /tickets`). |
| Boutons | Actifs seulement si l'action est possible : statut dans `transitionsPermises`, ticket assigné à moi, ticket créé par moi et jamais assigné. Une ligne explique chaque bouton grisé. |
| Refus | Le type et le message renvoyés par l'API s'affichent dans la page, près de l'action. |
| Suivi | La page interroge `GET /version` chaque seconde : un changement fait dans la GUI apparaît en une ou deux secondes. Un bandeau prévient si le serveur ne répond plus. |

**Connexion.** Avant tout choix, la page invite à choisir un compte en haut à droite.

![Page web : choix du compte](documents/captures_lab4/web_1_connexion.jpg)

**Vue Admin.** Tous les tickets, filtrables par statut, et le détail du ticket choisi, avec son image servie par l'API. Seuls les changements de statut permis depuis « Assigné » sont actifs : « Valider » est grisé.

![Page web : vue Admin, détail du ticket 2](documents/captures_lab4/web_2_admin.jpg)

**Vue User, « Créés par moi ».** T Julien voit les trois tickets qu'il a créés. Le ticket 6 n'a jamais été assigné : « Supprimer… » est actif. « Soumettre à validation » est grisé, et la ligne du dessous dit pourquoi.

![Page web : vue User, onglet Créés par moi](documents/captures_lab4/web_3_user_crees.jpg)

**Vue User, « Assignés à moi ».** La dernière colonne montre le créateur. Le ticket 10 est assigné à T Julien : il peut le soumettre à validation, mais pas le supprimer.

![Page web : vue User, onglet Assignés à moi](documents/captures_lab4/web_4_user_assignes.jpg)

**Création d'un ticket.** Le formulaire s'ouvre au-dessus de la liste. Un titre vide est refusé par le serveur, et son message s'affiche dans le formulaire.

![Page web : formulaire de création avec un refus du serveur](documents/captures_lab4/web_5_user_creation.jpg)

### Scénario de démonstration (5 minutes)

Préparer : supprimer `donnees/sauvegarde.json`, lancer le serveur, puis deux GUI connectées l'une en Ambroise Fleury (Admin, F2), l'autre en T Julien (User, F3).

1. F3 : « Nouveau ticket », titre « Paiement refusé », priorité HAUTE, « Continuer ».
2. F5 : taper le texte, ajouter l'image `ressources/capture_ecran.png` et un commentaire (« Ajouter »).
3. F5 : « Mettre en pause » ; dans F3, onglet « Brouillons », « Reprendre l'édition » : le texte tapé est là.
4. F5 : « Créer le ticket ». Le ticket #11 apparaît dans F2 en une ou deux secondes.
5. F2 : « Voir le détail » de #11 : texte, image et commentaire.
6. F2 : #11, « Assigner… » à T Julien. Il apparaît dans « Assignés à moi » de F3.
7. F3 : « Soumettre à validation ». F2 affiche VALIDATION.
8. F2 : #6 et #3 (Ctrl+clic), « Assigner… » à Mike Tonny : rapport avec un succès et un refus (#3 est FERME).
9. PowerShell, sans GUI : valider #11.

```powershell
Invoke-RestMethod -Method Patch -Uri http://127.0.0.1:5000/ticket/11 -Headers @{"X-Acteur-Id"="1"} -ContentType "application/json" -Body '{"statut":"TERMINE"}'
```

10. PowerShell : tenter de le fermer, ce qui est refusé (409, transition invalide depuis TERMINE).

```powershell
try { Invoke-RestMethod -Method Patch -Uri http://127.0.0.1:5000/ticket/11 -Headers @{"X-Acteur-Id"="1"} -ContentType "application/json" -Body '{"statut":"FERME"}' } catch { $_.ErrorDetails.Message }
```

11. Page web http://127.0.0.1:5000/ : un ticket créé en User apparaît dans la GUI en une ou deux secondes, et l'inverse.

---

# Labs 2 et 3

Le Lab 3 donne une interface graphique au système de tickets du Lab 2. Depuis une même connexion, un Admin et plusieurs utilisateurs ouvrent chacun leur fenêtre. Les utilisateurs créent et décrivent leurs tickets, l'Admin les fait avancer dans leur cycle de vie, et chaque liste ouverte se met à jour dès qu'un autre acteur change quelque chose.

La vidéo de démonstration (scénarios de test de l'application) est jointe à la release [Lab 3 : remise en vidéo demo](https://github.com/zongo-julien/Laboratoire3_6GEI311_Architecture_des_logiciels/releases/download/lab3-remise/Lab3_demo_scenarios.mp4).

L'interface est écrite avec tkinter, sans dépendance externe, selon une architecture MVC posée sur le modèle du Lab 2. Ce modèle garde ses patrons (State, Template Method, Factory Method, Command) et en gagne un, l'Observateur. Les maquettes Figma et les captures de toutes les fenêtres sont dans `documents/`.

La Partie 1 du Lab 2 (implémentation littérale du diagramme de classes initial) est dans un dépôt séparé : [Laboratoire2_6GEI311_Architecture_des_logiciels_Partie1](https://github.com/zongo-julien/zongo-julien-Laboratoire2_6GEI311_Architecture_des_logiciels_Partie1).

## Sommaire

1. [Lab 4 : client-serveur](#lab-4--client-serveur), dont [la page web](#la-page-web-bonus)
2. [Lancer l'interface](#lancer-linterface)
3. [Les fenêtres](#les-fenêtres)
   - [Connexion (F1)](#connexion-f1)
   - [Gérer les tickets en Admin (F2, F7, F8)](#gérer-les-tickets-en-admin-f2-f7-f8)
   - [Mes tickets et détail d'un ticket (F3, F6)](#mes-tickets-et-détail-dun-ticket-f3-f6)
   - [Créer et éditer un ticket (F4, F5)](#créer-et-éditer-un-ticket-f4-f5)
4. [Architecture de l'interface](#architecture-de-linterface)
   - [Passerelle et objets de lecture](#passerelle-et-objets-de-lecture)
   - [Du patron Observateur au sondage de /version](#du-patron-observateur-au-sondage-de-version)
   - [Règles de dépendances](#règles-de-dépendances)
   - [Diagramme de classes du Lab 3](#diagramme-de-classes-du-lab-3)
5. [Lancer les tests](#lancer-les-tests)
6. [Le modèle](#le-modèle)
7. [Résultats du Lab 2](#résultats-du-lab-2)
8. [Ce que nous avons appris](#ce-que-nous-avons-appris)
9. [Structure du code](#structure-du-code)

## Lancer l'interface

Au Lab 4, l'interface est un **client** de l'API REST : elle ne détient plus les données, elle les demande au serveur. Le serveur doit donc être lancé en premier (`python serveur.py`). Chaque interface se lance ensuite dans son propre terminal, depuis la racine du dépôt :

```bash
python app.py
```

L'interface n'utilise que la bibliothèque standard : tkinter pour les fenêtres et `urllib` pour les requêtes HTTP. Flask ne sert qu'au serveur. Sous Linux, installer le paquet `python3-tk` s'il manque.

- **Adresse du serveur.** Par défaut `http://127.0.0.1:5000`. Pour un serveur sur un autre port : `python app.py --url http://127.0.0.1:5001`.
- **Plusieurs interfaces.** On peut en lancer autant que l'on veut, par exemple un Admin dans l'une et un utilisateur dans l'autre : ce que l'une change apparaît dans l'autre en une seconde environ.
- **Sans serveur**, l'interface affiche « Serveur injoignable » et propose de réessayer.
- **Serveur arrêté en cours de route** : une seule boîte d'erreur s'affiche, puis les listes se remettent à jour d'elles-mêmes dès que le serveur répond de nouveau.
- **Aucun fichier de données côté client.** L'interface ne lit ni n'écrit aucun fichier de `donnees/`. La fermer ne demande donc aucune confirmation et ne perd rien : chaque action a déjà été enregistrée par le serveur, et une création ou une édition commencée dans F5 reste en pause sur le serveur.

## Les fenêtres

L'interface compte huit fenêtres, numérotées comme dans les maquettes Figma de `documents/maquettes/`. Leur apparence n'a pas changé au Lab 4 : les captures ci-dessous, prises au Lab 3 sur les données de démonstration, restent valables ; toutes sont dans `documents/captures_lab3/`. Ce qui change, c'est d'où viennent les données (des requêtes `GET`) et où vont les actions (des requêtes `POST`, `PATCH` ou `DELETE`).

| Fenêtre | Rôle | Vue | Logique de présentation |
|---|---|---|---|
| F1 Connexion | Choisir l'acteur avec lequel ouvrir une session | `vue_connexion.py` | `ControleurPrincipal` |
| F2 Liste Admin | Tout le dépôt, filtre par statut, actions en lot | `vue_liste_admin.py` | `ControleurAdmin` |
| F3 Mes tickets | Tickets créés, tickets assignés et brouillons | `vue_liste_user.py` | `ControleurUser` |
| F4 Nouveau ticket | Titre et priorité d'un nouveau ticket | `vue_nouveau_ticket.py` | `ControleurPrincipal` |
| F5 Éditeur de description | Texte, images et commentaires, en création ou en édition | `vue_edition.py` | `ControleurEdition` |
| F6 Détail d'un ticket | Lecture d'un ticket, commune aux deux rôles | `vue_detail.py` | `ControleurDetail` |
| F7 Confirmation du lot | Opérations de l'Admin avant application | `vue_lot.py` | `ControleurAdmin` |
| F8 Rapport d'exécution | Succès et refus après application | `vue_rapport.py` | aucune (lecture seule) |

### Connexion (F1)

La connexion liste les acteurs lus sur le serveur (`GET /acteurs`), nom à gauche et rôle à droite. « Ouvrir la session », un double-clic ou Entrée ouvre F2 pour l'Admin et F3 pour un utilisateur. Chaque session envoie ensuite l'identifiant de son acteur dans l'en-tête `X-Acteur-Id` de chacune de ses requêtes : c'est ainsi que le serveur sait qui agit. La connexion reste ouverte : on peut mettre plusieurs acteurs côte à côte, dans la même interface ou dans plusieurs. Il n'y a pas de mot de passe, l'authentification sortant du cadre du laboratoire.

Fermer la connexion quitte l'application, sans confirmation : chaque action a déjà été enregistrée par le serveur, et les brouillons y restent.

![F1 Connexion](documents/captures_lab3/F1_connexion.png)

### Gérer les tickets en Admin (F2, F7, F8)

**Parcours.** Une session Admin ouvre F2 : tous les tickets du dépôt (numéro, titre, priorité, statut, créateur, assigné), filtrables par statut. On sélectionne un ou plusieurs tickets (Ctrl+clic), puis « Assigner… », « Désassigner », « Valider » ou « Fermer » ouvre F7, qui montre exactement les opérations du lot avant toute modification ; pour « Assigner… », on y choisit d'abord l'utilisateur. « Appliquer » envoie le lot en une seule requête (`POST /acteur/{acteurId}/lots`). Le serveur l'exécute « au mieux » : un refus ne bloque pas les opérations suivantes, et F8 affiche le rapport qu'il renvoie, succès et refus avec leur motif. « Voir le détail », ou un double-clic, ouvre F6 sur la sélection.

![F2 Liste Admin : deux tickets OUVERT sélectionnés](documents/captures_lab3/F2_liste_admin.png)

![F7 pour « Fermer » : avertissement et focus sur « Annuler »](documents/captures_lab3/F7_fermer.png)

![F8 après un lot : deux succès et un refus motivé](documents/captures_lab3/F8_rapport_lot.png)

F2 observe la `SourceTickets` de la session (voir [Du patron Observateur au sondage de /version](#du-patron-observateur-au-sondage-de-version)) : un ticket créé ou modifié par un autre acteur, même depuis une autre interface, y apparaît en une seconde environ, sans action de l'Admin, et la sélection est conservée. `ControleurAdmin` ne modifie jamais un ticket : il prépare l'aperçu du lot sur le client, sans rien envoyer, puis l'envoie au serveur à l'application. Il n'importe pas tkinter et est testé dans le CI contre les vraies routes du serveur (`tests/test_controleur_admin.py`).

**Tactiques d'utilisabilité.**

| Tactique | Dans l'interface |
|---|---|
| Agrégat | Une action s'applique en un seul lot, et une seule requête, à tous les tickets sélectionnés ; F6 parcourt toute la sélection. |
| Modèle du système | Un bouton d'action n'est actif que si au moins un ticket sélectionné permet la transition, d'après la liste `transitionsPermises` que le serveur envoie avec chaque ticket : les règles restent dans les états, sur le serveur. |
| Prévention des erreurs | Pour « Fermer », action définitive, F7 affiche un avertissement et met le focus sur « Annuler » : la touche Entrée ne ferme aucun ticket. Pour « Assigner… », aucun utilisateur n'est choisi d'avance et « Appliquer » reste grisé tant qu'il ne l'est pas. |
| Annuler | « Annuler », ou Échap, ferme F7 sans rien envoyer au serveur : le lot préparé est simplement oublié. |
| Retour d'information | F7 liste les opérations en attente ; F8 donne le bilan, puis chaque succès et chaque refus avec son motif. |

### Mes tickets et détail d'un ticket (F3, F6)

**Parcours.** Une session User ouvre F3, qui ne montre que les tickets qui concernent l'utilisateur, en trois onglets : « Créés par moi », « Assignés à moi » et « Brouillons ». Les listes viennent de `GET /tickets?createur=` et `GET /tickets?assigne=`. L'onglet « Brouillons » ne liste que les créations commencées et pas encore appliquées, dont le ticket n'est pas encore dans le dépôt. Une édition d'un ticket existant s'affiche plutôt dans la colonne « Édition » de sa ligne, « en pause » ou « en cours ». Depuis F3 : « Nouveau ticket » ouvre F4 ; « Éditer », ou « Reprendre l'édition » pour une session en pause, ouvre F5 ; « Supprimer » retire un ticket jamais assigné, après confirmation (`DELETE /ticket/{ticketId}`) ; « Soumettre à validation » fait passer un ticket assigné à l'état VALIDATION (`PATCH /ticket/{ticketId}`). « Voir le détail », ou un double-clic, ouvre F6.

F6 est commune aux deux rôles et ne fait que lire le ticket (`GET /ticket/{ticketId}`) : statut, priorité, créateur, assigné, dates, puis la description et les commentaires. Les images ne sont plus lues sur le disque : F6 les télécharge par l'API (`GET /ticket/{ticketId}/image/{nomImage}`), les garde le temps de la fenêtre et les affiche avec `tk.PhotoImage(data=...)`, réduites au-delà de 400 px de large. Une image indisponible est signalée sans empêcher la lecture du reste. « ‹ Précédent » et « Suivant › » parcourent la sélection reçue de F2, ou l'onglet de F3, sans revenir à la liste.

![F3, onglet « Brouillons » : une création en pause](documents/captures_lab3/F3_brouillons.png)

![F6 : informations, texte et image de la description](documents/captures_lab3/F6_detail.png)

F3 et F6 observent la `SourceTickets` de la session : un changement fait par un autre acteur s'affiche en une seconde environ. F6 suit le ticket affiché par son **identifiant**, et non plus avec `is` : chaque rafraîchissement crée de nouveaux objets, si bien que l'ancienne comparaison échouait toujours. Seul le ticket affiché est relu en détail, ce qui fait apparaître aussi un nouveau commentaire ou un ajout à la description ; si ce ticket est supprimé, un message l'annonce et F6 passe au suivant, ou se ferme.

Les brouillons, eux, ne changent pas le compteur de version du serveur. F3 les relit (`GET /acteur/{acteurId}/brouillons`) à chaque rafraîchissement, et dès qu'un éditeur F5 ouvre, met en pause, reprend, abandonne ou applique un brouillon : la relecture toutes les 500 ms du Lab 3 a disparu. `ControleurUser` et `ControleurDetail` n'importent pas tkinter et sont testés dans le CI (`tests/test_controleur_user.py`, `test_controleur_detail.py`).

**Tactiques d'utilisabilité.**

| Tactique | Dans l'interface |
|---|---|
| Pause et reprise | Une création en pause apparaît dans l'onglet « Brouillons », une édition en pause dans la colonne « Édition » ; « Reprendre l'édition » rouvre F5 avec le texte tapé et les ajouts en attente, gardés par le serveur. Le bouton s'appelle « Reprendre l'édition » dès qu'un brouillon est en pause sur le ticket choisi. |
| Prévention des erreurs | « Supprimer » n'est actif que pour un ticket créé par l'utilisateur et jamais assigné ; « Soumettre à validation » seulement pour un ticket qui lui est assigné et dont l'état le permet ; « Éditer » seulement pour un ticket qu'il a créé. La suppression demande une confirmation, « Non » par défaut. |
| Agrégat | F6 parcourt plusieurs tickets avec « ‹ Précédent » et « Suivant › » (ou Alt+← et Alt+→), sans revenir à la liste. |
| Retour d'information | Le nombre de lignes de chaque onglet est affiché dans son titre ; F6 indique « Ticket n sur N ». |

### Créer et éditer un ticket (F4, F5)

**Parcours.** Depuis la liste d'un utilisateur (F3), « Nouveau ticket » ouvre F4 : on y saisit le titre et la priorité, puis « Continuer » ouvre un **brouillon** de création sur le serveur (`POST /acteur/{acteurId}/brouillons`) et l'éditeur F5. Le serveur réserve alors le numéro du ticket, sans l'ajouter au dépôt. Dans F5, on tape le texte de la description, on ajoute des images PNG ou GIF et des commentaires (`POST .../modifications`), qui restent en attente dans le brouillon. Chaque image est lue sur le poste et envoyée en base64 : le serveur en garde une copie. « Créer le ticket » envoie le texte tapé avec la demande d'application (`POST .../application`) ; le serveur l'ajoute à la description, applique le brouillon et renvoie le rapport, affiché par F8. C'est seulement à ce moment que le ticket entre dans le dépôt et apparaît chez les autres acteurs.

Pour un ticket existant, « Éditer » dans F3 ouvre la même fenêtre F5 en mode édition, avec le bouton « Appliquer ». Éditer un ticket, c'est **compléter** sa description et ses commentaires : le modèle ne permet ni de modifier ni de retirer un élément existant, et le titre et la priorité ne changent plus après la création. F5 ne montre donc que ce que l'on ajoute ; le contenu existant se lit dans F6.

![F4 Nouveau ticket](documents/captures_lab3/F4_nouveau_ticket.png)

![F5 en création : deux images, un commentaire et le texte tapé](documents/captures_lab3/F5_creation.png)

Le brouillon vit sur le serveur : c'est lui qui garde, pendant une pause, le texte tapé (`PATCH` avec `enPause` et `texteBrouillon`) et les copies d'images. Côté client, `ControleurPrincipal` tient un seul `ControleurEdition` par brouillon : « Éditer » sur un ticket dont F5 est déjà ouverte la ramène au premier plan au lieu d'en ouvrir une seconde.

**Tactiques d'utilisabilité.**

| Tactique | Dans l'interface |
|---|---|
| Annuler une saisie | « Annuler » dans F4 ne crée rien. « Abandonner » dans F5 renonce à tout le brouillon (`DELETE`), après confirmation si du texte ou des modifications seraient perdus ; le serveur supprime ses copies d'images, et le ticket reste inchangé (ou n'est pas créé). |
| Undo de frappe | Dans la zone de texte, Ctrl+Z et Ctrl+Y annulent ou rétablissent la frappe. |
| Undo de brouillon | « Annuler le dernier ajout » retire la dernière modification en attente, image ou commentaire (`DELETE .../modification/derniere`) ; le serveur supprime la copie d'une image retirée. |
| Pause et reprise | « Mettre en pause », ou la fermeture de F5, met le brouillon en pause sans rien perdre, même si l'interface est fermée ensuite. Le reprendre rouvre F5 avec le texte tapé. |
| Agrégat | Plusieurs images s'ajoutent en une seule sélection ; les images refusées sont signalées ensemble dans une seule boîte, et les autres sont ajoutées. |
| Prévention des erreurs | Les boutons sans effet possible sont grisés : « Continuer » sans titre, « Créer le ticket » sans texte ni image, « Appliquer » sans texte ni modification, « Ajouter » sans commentaire, « Annuler le dernier ajout » sans modification en attente. |
| Retour d'information | F5 affiche le nombre et la liste des modifications en attente ; F8 présente le rapport d'exécution renvoyé par le serveur. |

## Architecture de l'interface

```
Vues (ihm/vues)                              fenêtres F1 à F8, tkinter
      │
Logique de présentation (ihm/controleurs)    ce que chaque fenêtre lit et envoie
      │
Passerelle (ihm/passerelle)                  seul endroit qui parle HTTP
      │
═════════ HTTP + JSON, en-tête X-Acteur-Id ═════════
      │
Serveur Flask (api/), puis modèle et persistance
```

Dans le vocabulaire MVC du Lab 4, le **contrôleur** est l'ensemble des routes de l'API, côté serveur. Les classes de `ihm/controleurs/` gardent leur nom (`ControleurAdmin`, `ControleurUser`…), mais jouent le rôle de **logique de présentation** de l'interface : elles décident de ce qu'une fenêtre affiche et de la requête à envoyer, jamais de ce qui est permis. C'est le serveur qui décide, avec les états et les acteurs du modèle.

| Couche | Paquet | Règle |
|---|---|---|
| Vues | `ihm/vues` | Lisent les objets de lecture par leurs propriétés et observent la `SourceTickets` ; ne parlent jamais au serveur directement. |
| Logique de présentation | `ihm/controleurs` | Transforme chaque action en requête par la passerelle ; ne modifie jamais un objet lu ; sans tkinter, sauf `ControleurPrincipal`. |
| Passerelle | `ihm/passerelle` | Seule à faire des requêtes HTTP ; transforme le JSON reçu en objets de lecture et les erreurs reçues en exceptions. |

- Seul `ControleurPrincipal` crée des fenêtres. Pour chaque session ouverte depuis F1, il tient sa `ClientAPI` et sa `SourceTickets`, ainsi qu'un registre des éditeurs ouverts : un seul `ControleurEdition` par brouillon.
- `ControleurAdmin`, `ControleurUser`, `ControleurEdition` et `ControleurDetail` n'importent ni tkinter ni les vues. Ils sont donc testés dans le CI, qui n'a pas d'écran, contre les vraies routes du serveur.
- Chaque fenêtre hérite de `FenetreBase`, qui l'abonne à ses sujets à l'ouverture et l'en désabonne à la fermeture, avant de la détruire.
- `FenetreBase.executer()` affiche dans une boîte les cinq exceptions métier de `modele/exceptions.py`, ainsi que les erreurs propres au client, comme `ServeurInjoignable`, et la fenêtre reste ouverte. Toute autre exception est un bug et remonte dans la console. En pratique, les boutons qui mèneraient à un refus sont grisés d'avance.

Au Lab 3, les constructeurs des vues et les signatures des contrôleurs avaient été figés dès la première étape du sprint, avec une ébauche de chaque fenêtre ; ce contrat est détaillé dans le rapport du Lab 3 (section 3.2). Au Lab 4, ce rôle de contrat est tenu par `openapi.yaml`, qui décrit l'API entre le client et le serveur.

### Passerelle et objets de lecture

- `ClientAPI` (`ihm/passerelle/client_api.py`) reçoit l'adresse du serveur et l'identifiant de l'acteur. Elle envoie chaque requête avec `urllib`, l'identifiant dans l'en-tête `X-Acteur-Id` et un délai d'attente de 2 s. Elle offre une méthode par opération de l'API (`listerTickets`, `changerStatut`, `ouvrirBrouillonCreation`, `appliquerLot`…).
- **Erreurs.** Le serveur décrit chaque erreur en JSON, avec le type et le message de l'exception métier, et un code HTTP (403, 404, 409…). `ClientAPI` relève la même exception, avec le même message : les vues l'affichent exactement comme au Lab 3. Un serveur qui ne répond pas lève `ServeurInjoignable`.
- **Objets de lecture.** `ActeurLu`, `TicketLu`, `CommentaireLu`, `ElementLu`, `BrouillonLu` et `RapportLu` sont construits à partir du JSON reçu. Ils exposent les mêmes noms de propriétés que le modèle (`ticketID`, `title`, `status`, `creator.name`, `comments`, `description.elements`, `transitionsPermises`…), ce qui a permis de garder les vues presque intactes. Ils sont en lecture seule et **se comparent par identifiant** : deux lectures du même ticket donnent deux objets différents mais égaux.

### Du patron Observateur au sondage de /version

Au Lab 3, les fenêtres s'abonnaient au `SystemeTickets`, qui les prévenait de chaque changement. Une interface ne peut pas s'abonner à un objet qui vit dans un autre processus, sur le serveur. Le patron est donc conservé de chaque côté, et le réseau est traversé par un compteur :

1. Sur le serveur, un compteur de version, lui-même observateur du `SystemeTickets`, augmente à chaque ajout, modification ou retrait de ticket. `GET /version` renvoie sa valeur.
2. Côté client, chaque session a une `SourceTickets`, sujet observable qui garde la dernière copie des tickets. Une seule boucle `after()` de Tkinter lui fait relire `/version` toutes les secondes.
3. Si le compteur a bougé, la `SourceTickets` relit les tickets, compare les nouvelles représentations JSON aux anciennes et notifie `ticketAjoute`, `ticketModifie` ou `ticketRetire`. Les fenêtres s'abonnent à elle exactement comme elles s'abonnaient au `SystemeTickets`.

Un tour sans changement ne coûte qu'une petite requête. Après une action faite dans l'interface même, la source est rafraîchie tout de suite, sans attendre le tour suivant.

### Règles de dépendances

Ces règles gardent les couches séparées. `tests/test_regles_dependances.py` les vérifie à chaque exécution des tests, en lisant les imports de chaque fichier :

1. Le métier n'importe ni `flask`, ni `api`, ni `ihm`, ni `tkinter`.
2. `api/` (et `serveur.py`) n'importe ni `ihm` ni `tkinter`.
3. Le client (`ihm/`, `app.py`) n'importe du métier que le contrat partagé : `modele.enums`, `modele.exceptions` et `modele.observateur`. Il ne crée jamais de `Ticket`, de `User` ni de session.
4. Seul `ihm/passerelle/client_api.py` fait des requêtes HTTP.
5. Le client ne lit ni n'écrit aucun fichier de `donnees/` : sans serveur, il ne fonctionne pas.
6. La logique de présentation (tous les contrôleurs sauf le principal) ne charge pas tkinter, même indirectement, pour rester testable sans écran.

### Diagramme de classes du Lab 3

Le diagramme de classes du Laboratoire 3 reprend celui de la Partie 2 et y intègre ce que le Laboratoire 3 a introduit : le patron Observateur, la session de création, la persistance (`DepotJSON`, `StockageImages`) et le paquet `ihm` de l'interface graphique (MVC). Le fichier source draw.io, [`documents/Lab3_6GEI311_diagramme_classes.drawio`](documents/Lab3_6GEI311_diagramme_classes.drawio), contient cinq pages, aussi exportées en PNG : [modèle](documents/Lab3_uml_1_modele.png), [interface](documents/Lab3_uml_2_interface.png), [instanciations](documents/Lab3_uml_3_instanciations.png), [exceptions](documents/Lab3_uml_4_exceptions.png) et [cycle de vie du ticket](documents/Lab3_uml_5_cycle_de_vie.png).

![Diagramme de classes du Laboratoire 3 : modèle](documents/Lab3_uml_1_modele.png)

![Diagramme de classes du Laboratoire 3 : interface (paquet ihm)](documents/Lab3_uml_2_interface.png)

La page de l'interface montre le paquet `ihm` du Lab 3, avant la séparation entre client et serveur : la passerelle et les objets de lecture n'y figurent pas encore.

## Lancer les tests

Depuis la racine du dépôt :

```bash
python -m unittest discover -s tests -t .
```

La suite compte 568 tests, lancés aussi par GitHub Actions à chaque push et à chaque pull request. Aucun ne crée de fenêtre et aucun n'a besoin d'un serveur lancé à part. Les routes du serveur sont testées avec le client de test de Flask, sans réseau ; quelques tests lancent eux-mêmes un vrai serveur sur un port libre (requêtes simultanées, `outils/essai_api.py`). Pour le client :

- **Passerelle** (`test_passerelle_client.py`, `test_passerelle_source.py`) : `ClientAPI` contre un faux transport et un petit serveur HTTP local ; `SourceTickets` (rafraîchissement, notifications, suivi d'un détail).
- **Logique de présentation** (`test_controleur_admin.py`, `test_controleur_user.py`, `test_controleur_edition.py`, `test_controleur_detail.py`) : chaque contrôleur contre les vraies routes du serveur. `tests/serveur_essai.py` branche la `ClientAPI` sur le client de test de Flask : la requête traverse tout le serveur, sans ouvrir de port.
- **Architecture** (`test_regles_dependances.py`) : les six règles de dépendances.

`tests/test_donnees_demo.py` vérifie que la démonstration se recharge sans avertissement.

Le test de non-régression exécute `main.py` et compare sa sortie, dates neutralisées, à `tests/reference_main.txt`. Si la sortie change volontairement, régénérer la référence avec `python tests/test_non_regression.py`.

## Le modèle

Le modèle vient du Lab 2. Avant d'écrire l'interface, nous l'avons complété : sessions de création, abandon d'une session, transitions consultables, patron Observateur, sauvegarde JSON et copie des images jointes. Cette section en donne l'usage.

### Lancer la démonstration du Lab 2

```bash
python main.py
```

Le programme doit être lancé depuis la racine du dépôt, car les chemins des ressources (`ressources/...`) sont relatifs. Il exécute 17 scénarios, de A à Q, présentés dans la section [Démonstration](#démonstration-captures-décran). Chaque scénario affiche le test effectué (`Test :`) puis son résultat (`Résultat :`). Quand une opération doit être refusée, le programme capture l'exception, affiche son message et vérifie que le ticket est resté inchangé.

### Utiliser le système dans son propre code

Tous les acteurs partagent un même dépôt, `SystemeTickets`, injecté dans leur constructeur :

```python
from acteurs.admin import Admin
from acteurs.user import User
from modele.enums import Priorite
from modele.exceptions import TransitionInvalideException
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket

systeme = SystemeTickets()
admin = Admin(1, "Ambroise Fleury", "ambroise@uqac.ca", systeme)
abdoul = User(2, "Abdoul Razack", "abdoul@uqac.ca", systeme)
julien = User(3, "T Julien", "julien@uqac.ca", systeme)

# 1. Un utilisateur crée un ticket (statut initial : OUVERT)
ticket = Ticket(1, "Bug de connexion", Priorite.HAUTE)
abdoul.createTicket(ticket)

# 2. Son créateur le complète dans une session d'édition, puis applique
session = abdoul.ouvrirSessionEdition(ticket)
session.ajouterCommentaire("Le bug se reproduit sur Chrome.")
session.ajouterElement("texte", "ressources/description_bug.txt")
session.appliquer().afficher()

# 3. Cycle de vie : OUVERT -> ASSIGNE -> VALIDATION -> TERMINE
admin.assignTicket(ticket, julien)
julien.soumettreValidation(ticket)
admin.validerTicket(ticket)
abdoul.viewTicket(ticket)

# 4. Une transition interdite est refusée et le ticket reste intact
try:
    admin.closeTicket(ticket)
except TransitionInvalideException as erreur:
    print(erreur)
```

Sortie :

```text
  Succès :
    [OK]    Ajouter le commentaire « Le bug se reproduit sur Chrome. » au ticket #1
    [OK]    Ajouter l'élément [Texte] description_bug.txt (434 caractères) au ticket #1
  Refus :
    (aucun)
  Bilan : 2 succès, 0 refus
  Ticket #1 : Bug de connexion
    Statut       : TERMINE
    Priorité     : HAUTE
    Créateur     : Abdoul Razack
    Assigné      : T Julien
    Créé le      : 2026-10-02 | mis à jour le : 2026-10-02
    Commentaires : 1
      - Abdoul Razack (2026-10-02) : Le bug se reproduit sur Chrome.
    Éléments de description : 1
Transition invalide : impossible de passer de l'état TERMINE au statut FERME
```

### Opérations disponibles

| Objet | Méthode | Règle |
|---|---|---|
| `User` | `createTicket(ticket)` | L'utilisateur devient le créateur du ticket |
| `User` | `supprimerTicket(ticket)` | Seulement par le créateur, et si le ticket n'a jamais été assigné |
| `User` | `soumettreValidation(ticket)` | Seulement par l'assigné : `ASSIGNE` → `VALIDATION` |
| `User` | `ouvrirSessionEdition(ticket)` | Seulement par le créateur, et une seule session ouverte par ticket ; retourne une `SessionEdition` |
| `User` | `ouvrirSessionCreation(ticket)` | Seulement pour un ticket sans créateur et absent du dépôt, et une seule session ouverte par ticket ; retourne une `SessionCreation` |
| `User` | `sessionEnCours(ticket)` | Session d'édition ou de création encore ouverte sur ce ticket, même en pause ; sinon `None` |
| `User` | `sessionsOuvertes` | Propriété en lecture seule : sessions d'édition et de création encore ouvertes |
| `User` | `mesTickets(ids=None)` | Tickets créés par l'utilisateur, filtrables par identifiant |
| `Admin` | `assignTicket(ticket, user)` | Assignation, réassignation ou rejet d'une validation |
| `Admin` | `desassignerTicket(ticket)` | `ASSIGNE` → `OUVERT` |
| `Admin` | `validerTicket(ticket)` | `VALIDATION` → `TERMINE` |
| `Admin` | `closeTicket(ticket)` | `OUVERT` ou `ASSIGNE` → `FERME` |
| `Admin` | `viewAllTickets()` | Affiche et retourne tous les tickets du dépôt |
| `Admin` | `ouvrirLot()` | Retourne un `LotAdmin` |
| `User`, `Admin` | `viewTicket(ticket)` | Affiche le détail d'un ticket |
| `SessionEdition` | `ajouterCommentaire(texte)`, `ajouterElement(type, chemin)` | Ajoute une modification en attente ; `type` vaut `"texte"`, `"image"` ou `"video"` |
| `SessionEdition` | `ajouterTexteSaisi(texte)` | Ajoute en attente un texte tapé, sans fichier ; un texte vide ou blanc est refusé (`ArtefactInvalideException`) |
| `SessionEdition` | `annulerDerniere()`, `mettreEnPause()`, `reprendre()` | Gestion de la pile de modifications |
| `SessionEdition` | `abandonner()` | Renonce à toute la session avant application : vide la pile, lève la pause et ferme la session ; permise en pause, refusée si la session est déjà appliquée ou abandonnée |
| `SessionEdition` | `estOuverte` | Propriété en lecture seule : vraie tant que la session n'est ni appliquée ni abandonnée |
| `SessionEdition` | `ticket` | Propriété en lecture seule : ticket visé par la session (aussi pour `SessionCreation`) |
| `SessionCreation` | mêmes opérations que `SessionEdition` | `appliquer()` vérifie d'abord la session (déjà appliquée, abandonnée, en pause), puis crée le ticket avec `createTicket()` et applique sa description ; un refus ou un abandon laisse le ticket hors du dépôt |
| `LotAdmin` | `assigner(ticket, user)`, `desassigner(ticket)`, `validerTicket(ticket)`, `fermer(ticket)` | Prépare une opération ; ni pause, ni reprise, ni annulation |
| `SessionEdition`, `LotAdmin` | `appliquer()` | Exécute les modifications en attente et retourne un `RapportExecution` |
| `ElementDescription` | `typeArtefact` | Propriété en lecture seule : `"texte"`, `"image"` ou `"video"`, les mêmes valeurs que `FabriqueDescription.creer()` |
| `DescriptionTexte` | `contenu` | Propriété en lecture seule : texte du fichier, disponible après `traiter()` |
| `SystemeTickets` | `ticketsAssignesA(user)` | Tickets dont `user` est l'assigné actuel, y compris ceux à l'état `TERMINE` ou `FERME`, où l'assigné est conservé |
| `SystemeTickets` | `inscrireUtilisateur(utilisateur)`, `utilisateurs`, `utilisateurParId(id)` | Annuaire des utilisateurs, utilisé par la sauvegarde ; l'inscription est idempotente, et un identifiant déjà pris par un autre utilisateur lève `ValueError` |
| `Ticket` | `transitionsPermises` | Propriété en lecture seule : statuts accessibles depuis l'état courant |
| `Ticket` | `transitionPossible(statut)` | Indique si la transition serait acceptée, sans rien modifier |
| `Ticket` | `ajouterElementDescription(element)` | Ajoute un élément à la description, met à jour la date et notifie les observateurs |
| `Ticket`, `SystemeTickets` | `abonner(observateur)`, `desabonner(observateur)` | Abonne ou désabonne un `ObservateurTickets` ; s'abonner deux fois n'a pas d'effet, et se désabonner sans être abonné ne lève pas d'erreur |
| `DepotJSON` | `sauvegarder(systeme)`, `charger()`, `existe()` | Écrit tout le système dans un fichier JSON, ou le reconstruit ; voir [Sauvegarder et recharger le système](#sauvegarder-et-recharger-le-système) |
| `StockageImages` | `copier(chemin)` | Copie une image `.png` ou `.gif` dans `donnees/images/` sous un nom unique et retourne le chemin de la copie (notation POSIX), à passer tel quel à `ajouterElement("image", ...)` ; un fichier introuvable ou un autre format est refusé (`ArtefactInvalideException`) |
| `StockageImages` | `supprimer(chemin)` | Supprime une copie du dossier de stockage ; sans effet sur un fichier absent ou hors de ce dossier, donc jamais sur une image d'origine |

L'Admin ne crée, ne supprime ni n'édite aucun ticket. Chacune de ses opérations demande **la transition d'abord, la donnée ensuite** : un refus ne modifie jamais le ticket.

### Sauvegarder et recharger le système

`DepotJSON` enregistre tout le système (utilisateurs, tickets, commentaires et descriptions) dans un fichier JSON, puis le reconstruit :

```python
from persistance.depot_json import DepotJSON

depot = DepotJSON("sauvegarde.json")
depot.sauvegarder(systeme)
systeme = depot.charger()
```

- Les utilisateurs sauvegardés sont ceux de l'annuaire (`inscrireUtilisateur()`) et ceux qui sont cités dans les tickets ; dans un ticket, chaque utilisateur est remplacé par son identifiant.
- Les fichiers de description sont sauvegardés par leur chemin, sans être copiés ; un texte saisi est sauvegardé avec son contenu.
- L'écriture passe par un fichier temporaire : une sauvegarde interrompue ne remplace pas l'ancienne.
- Au chargement, `Ticket.restaurer()` remet chaque ticket dans l'état sauvegardé, dates comprises, sans rejouer la machine à états ; `FabriqueEtat` construit l'état qui correspond au statut enregistré.
- Un fichier de description introuvable est ignoré et signalé dans `depot.avertissements`. Un fichier de sauvegarde illisible, d'une autre version ou incohérent lève `PersistanceException` ; un fichier absent lève `FileNotFoundError` (voir `depot.existe()`).
- Les sessions non appliquées ne sont pas sauvegardées.

### Patrons de conception

#### State - `etats/`, `modele/ticket.py`

Le statut d'un ticket n'est pas stocké : la propriété `status` (en lecture seule) est dérivée de l'état courant. `Ticket.updateStatus()` délègue entièrement la décision à l'état, qui accepte la transition (en instanciant le nouvel état) ou lève `TransitionInvalideException`.

| État | Transitions autorisées |
|---|---|
| `OUVERT` | `ASSIGNE`, `FERME` |
| `ASSIGNE` | `ASSIGNE` (réassignation), `OUVERT` (désassignation), `VALIDATION`, `FERME` |
| `VALIDATION` | `ASSIGNE` (rejet), `TERMINE` |
| `TERMINE` | aucune (état terminal) |
| `FERME` | aucune (état terminal) |

Chaque état déclare aussi les statuts qu'il accepte dans `transitionsPermises`. `Ticket.transitionPossible(statut)` permet ainsi de savoir si une transition serait acceptée sans la tenter et sans recopier les règles ailleurs. Comme ces règles sont écrites à deux endroits (`transitionsPermises` les annonce, `gererTransition()` les applique), un test essaie chaque état avec chaque statut et vérifie que les deux disent la même chose.

#### Template Method - `description/element_description.py`

`ElementDescription.traiter()` (marquée `@typing.final`) fixe l'ordre des étapes : `validerChemin()` → `charger()` → `preparerAffichage()`. `charger()` varie selon le type d'artefact (texte, image, vidéo) ; faute de fichier, `DescriptionTexteSaisi` (texte tapé par l'utilisateur) redéfinit aussi `validerChemin()`, qui refuse un texte vide, et `preparerAffichage()`, qui affiche le nom « texte saisi ». `DescriptionVideo` pratique le **chargement différé** : `charger()` ne lit que la taille du fichier, et le contenu n'est lu que par `chargerContenuReel()`.

#### Factory Method - `description/fabrique_description.py`, `etats/fabrique_etat.py`

`FabriqueDescription.creer(type_artefact, chemin)` crée l'élément voulu (`"texte"`, `"image"`, `"video"`) sans le charger ; tout autre type lève `ArtefactInvalideException`. `FabriqueDescription.creerSaisie(texte)` crée de même, sans le charger, un élément à partir d'un texte tapé par l'utilisateur, sans fichier. La fabrique est le seul endroit du programme qui connaît les sous-classes concrètes.

`FabriqueEtat.creer(statut)` joue le même rôle pour les états : au chargement d'une sauvegarde, elle construit l'état qui correspond au statut enregistré. Un test vérifie que chaque valeur de `Statut` a son état.

#### Command - `commandes/`, `sessions/`

Les modifications sont empilées sous forme de commandes dans une session, puis appliquées d'un coup par `appliquer()`, qui retourne un `RapportExecution`. L'application se fait « au mieux » : une commande refusée ne bloque pas les suivantes, et une commande dont le ticket a été retiré du dépôt est refusée avec le motif « ticket retiré du dépôt ».

- `SessionEdition` (côté User) : commentaires et éléments de description ; annulation de la dernière modification, pause et reprise.
- `SessionCreation` (côté User) : session d'édition d'un nouveau ticket, qui n'existe pour les autres qu'une fois sa description appliquée. `appliquer()` l'enregistre dans le dépôt avec `createTicket()` juste avant d'exécuter les modifications ; un refus ou un abandon le laisse hors du dépôt.
- `LotAdmin` (côté Admin) : assigner, désassigner, valider, fermer ; ni pause, ni reprise, ni annulation.

Dans une session d'édition, `annulerDerniere()` défait seulement la dernière modification en attente (undo), alors que `abandonner()` renonce à toute la session : la pile est vidée, la session est fermée et le ticket reste inchangé.

#### Observateur - `modele/observateur.py`, `modele/ticket.py`, `modele/systeme_tickets.py`

`ObservateurTickets` est l'interface des observateurs : ses méthodes `ticketModifie`, `ticketAjoute` et `ticketRetire` ne font rien par défaut, et chaque observateur ne redéfinit que celles qui l'intéressent. `SujetTickets` tient la liste des abonnés (`abonner()`, `desabonner()`) et les notifie.

- `Ticket` est un sujet : toutes ses modifications (état, créateur, assigné, commentaire, élément de description) passent par `_signalerModification()`, qui met à jour `updateDate`, désormais à chaque modification du ticket et non plus seulement aux transitions comme au Lab 2, puis notifie ses abonnés. Une transition refusée ne notifie rien.
- `SystemeTickets` est à la fois sujet et observateur : il s'abonne à chaque ticket ajouté, s'en désabonne au retrait et retransmet ses modifications à ses propres abonnés (relais). Il notifie aussi les ajouts et les retraits de tickets.

Un observateur doit se désabonner quand il disparaît ; sinon, il continue d'être appelé et reste en mémoire. Pour que l'ajout d'un élément de description soit notifié, il faut passer par `ticket.ajouterElementDescription()` et non par `ticket.description.ajouterElement()` ; `CommandeAjouterElement` passe désormais par cette méthode.

## Résultats du Lab 2

### Partie 1 : diagramme initial

La Partie 1 traduit littéralement le diagramme de classes fourni : trois classes, `User`, `Admin` et `Ticket`. Le statut y est une simple chaîne de caractères, sans aucune règle de transition, et l'assigné et les commentaires ne sont pas mémorisés, faute d'attribut prévu dans le diagramme. Le code se trouve dans le [dépôt de la Partie 1](https://github.com/zongo-julien/Laboratoire2_6GEI311_Architecture_des_logiciels_Partie1).

![Diagramme de classes de la Partie 1](documents/uml_partie1.png)

### Partie 2 : diagramme amélioré

Le diagramme de la Partie 2 corrige les défauts de la Partie 1 et ajoute les sessions d'édition, les lots administrateur et les descriptions multimédias. Cliquer sur l'image pour l'agrandir. Le fichier source draw.io est disponible dans [`documents/Lab2_6GEI311_diagramme_classes_partie2.drawio`](documents/Lab2_6GEI311_diagramme_classes_partie2.drawio).

![Diagramme de classes de la Partie 2](documents/uml_partie2.png)

### Fonctionnalités implémentées

| Fonctionnalité | Acteur | Scénarios |
|---|---|---|
| Création de tickets | User | A |
| Suppression d'un ticket, seulement par son créateur et s'il n'a jamais été assigné | User | N |
| Consultation : `mesTickets()` avec ou sans filtre, `viewTicket()`, `viewAllTickets()` | User, Admin | B, C, G, Q |
| Session d'édition : modifications en attente, annulation, pause et reprise, application groupée avec rapport | User | D, E, F, G, H |
| Session de création : le ticket n'entre dans le dépôt qu'à l'application de sa description | User | - (tests unitaires) |
| Une seule session ouverte par ticket, de nouveau permise après application ou abandon | User | - (tests unitaires) |
| Consultation des tickets assignés à un utilisateur | User | - (tests unitaires) |
| Transitions permises consultables sans modifier le ticket | - | - (tests unitaires) |
| Notification des observateurs à chaque modification d'un ticket, relayée par le dépôt | - | - (tests unitaires) |
| Sauvegarde et rechargement du système en JSON | - | - (tests unitaires) |
| Description multimédia (texte, image, vidéo) avec chargement différé de la vidéo | User | D, G |
| Cycle de vie contrôlé par une machine à états | Admin, User | J, K, O |
| Réassignation directe et rejet d'une validation | Admin | L |
| Désassignation | Admin | M |
| Fermeture et états terminaux | Admin | O |
| Lot administrateur appliqué « au mieux » | Admin | P |
| Contrôles d'accès (créateur, assigné, rôle) | User, Admin | I, K, N, Q |
| Statut en lecture seule | - | Q |

### Démonstration (captures d'écran)

Sortie de `python main.py`, scénario par scénario.

#### A à C : création, agrégat `mesTickets()` et consultation par l'Admin

Deux utilisateurs créent quatre tickets, qui démarrent tous à l'état `OUVERT`. `mesTickets()` ne retourne que les tickets de leur créateur, et l'Admin voit l'ensemble du dépôt.

![Scénarios A à C](documents/captures/Output_ABC.png)

#### D à F : session d'édition, annulation, pause et reprise

Les cinq modifications restent en attente : le ticket T1 ne change pas avant `appliquer()`. L'annulation retire la dernière modification, et pendant la pause tout ajout, annulation ou application est refusé.

![Scénarios D à F](documents/captures/Output_DEF.png)

#### G à I : application de la session, session close et accès refusé

`appliquer()` produit un rapport de 5 succès. La vidéo n'est chargée réellement qu'à l'appel de `chargerContenuReel()`. Une session déjà appliquée refuse tout nouvel ajout, et un utilisateur qui n'est pas le créateur ne peut pas ouvrir de session sur le ticket.

![Scénarios G à I](documents/captures/Output_GHI.png)

#### J à M : cycle nominal, refus de transition, réassignation et désassignation

Le cycle `OUVERT` → `ASSIGNE` → `VALIDATION` → `TERMINE` est accepté. Un non-assigné ne peut pas soumettre en validation, et l'Admin ne peut pas valider un ticket qui n'est pas en validation. La réassignation directe, le rejet d'une validation et la désassignation fonctionnent.

![Scénarios J à M](documents/captures/Output_JKLM.png)

#### N et O : suppression, fermeture et états terminaux

Un ticket jamais assigné peut être supprimé par son créateur, mais pas un ticket déjà assigné ni le ticket d'un autre utilisateur. Une fois `TERMINE` ou `FERME`, un ticket n'accepte plus aucune transition.

![Scénarios N et O](documents/captures/Output_NO.png)

#### P et Q : lot administrateur, bilan et protections

Le lot de quatre opérations donne 1 succès et 3 refus : transition invalide deux fois, et ticket retiré du dépôt avant l'application. Écrire directement `T1.status` est refusé, et les méthodes réservées à un autre rôle n'existent tout simplement pas sur l'objet.

![Scénarios P et Q](documents/captures/Output_PQ.png)

## Ce que nous avons appris

### Au Lab 4

**Griser n'est pas protéger.** Au Lab 3, nous avions appris à griser les boutons plutôt que de laisser le modèle refuser. Avec deux clients, ce n'est plus suffisant : un ticket peut être assigné par l'Admin pendant que son créateur confirme la suppression, et seul le serveur le voit (409). Le client doit donc griser pour le confort, mais le serveur doit toujours revérifier. L'API doit aussi envoyer tout ce dont le client a besoin pour décider, comme `transitionsPermises` et `dejaAssigne`, au lieu que le client recopie les règles.

**Penser en ressources, pas en fonctions.** Au Lab 3, l'interface appelait des méthodes, comme `user.supprimerTicket(ticket)`. Au Lab 4, il a fallu décider ce qui mérite une adresse : les tickets, les acteurs, les images, et même le brouillon, qui n'existait jusque-là que dans la mémoire de l'interface. Les verbes HTTP donnent ensuite le sens de chaque action : « Soumettre à validation » n'est pas une nouvelle route, c'est un changement de statut, `PATCH /ticket/9` avec `{"statut": "VALIDATION"}`.

**HTTP ne pousse rien : il faut demander.** Une fenêtre ne peut pas s'abonner à un objet d'un autre programme, et en HTTP le serveur ne parle que si on l'interroge. Nous avons gardé l'Observateur de chaque côté, relié par un compteur de version que le client interroge chaque seconde. C'est simple et robuste, au prix d'une seconde de délai et d'une requête par seconde et par interface.

### Au Lab 3

**Figer le contrat avant le code.** Dès la première étape du sprint, toutes les fenêtres existaient sous forme d'ébauches, avec leurs constructeurs définitifs. Écrire des fenêtres qui ne faisaient rien ressemblait à du temps perdu ; c'est pourtant ce qui nous a laissés travailler en parallèle, avec quatre pull requests fusionnées sans conflit.

**L'Observateur a un coût de sortie.** S'abonner est facile ; le piège est la fenêtre fermée qui reste abonnée. Le désabonnement, avant la destruction, est devenu une règle de `FenetreBase` plutôt qu'une chose à laquelle chaque vue doit penser. Les sessions, elles, ne notifient rien : F3 relit leur état toutes les 500 ms, un contournement que nous remplacerions avec plus de temps.

**Griser plutôt que refuser.** Le modèle refusait déjà les opérations interdites par des exceptions. Griser les boutons d'avance, en posant au modèle la question qu'il se posera lui-même (`transitionPossible()`), s'est révélé plus clair pour l'utilisateur et plus simple à tester.

**Tester sans écran oblige à bien découper.** Le CI n'a pas d'écran. Cette contrainte nous a forcés à garder tkinter hors des contrôleurs, et c'est elle qui a rendu toute la logique de l'interface testable.

### Au Lab 2

**Voir le défaut avant de le corriger.** En Partie 1, rien n'empêche de passer d'`OUVERT` à `TERMINÉ`. En Partie 2, la même demande lève une exception, et `ticket.status = …` aussi. Avoir écrit la mauvaise version d'abord a rendu chaque critique de la conception initiale facile et vérifiable.

**Le principe ouvert/fermé a ses limites.** Ajouter un état oblige à modifier l'état qui doit y mener, et un nouveau type d'artefact coûte une ligne dans la fabrique. Les patrons ne suppriment pas la modification, ils la ramènent à un endroit qu'on sait retrouver.

**Relire l'énoncé contre le modèle.** Notre première version interdisait la réassignation, que le client a ensuite demandée. La corriger n'a touché que deux classes d'état. De même, Pylance a signalé qu'un `Admin` ne pouvait pas être l'auteur d'un commentaire typé `User` : l'erreur était dans le modèle, pas dans le code.

**L'essentiel.** Toujours revenir vers le client pour connaître ses besoins profonds, qu'il aura mal ou pas assez explicités, dans un cahier des charges par exemple.

## Structure du code

```
main.py                     scénarios de démonstration A à Q
app.py                      point d'entrée de l'interface (python app.py [--url http://127.0.0.1:5000])
serveur.py                  point d'entrée du serveur (python serveur.py [--port 5000])
openapi.yaml                contrat de l'API REST
requirements.txt            flask
Lab4_6GEI311_Rapport.pdf    rapport du Lab 4 (copie de documents/Lab4_6GEI311_Rapport.pdf)
api/                        SERVEUR : fabrique Flask, contexte, routes, représentations, erreurs
web/                        page web du bonus (index.html, app.js, style.css), servie par Flask
modele/
  enums.py                  Statut, Priorite
  exceptions.py             les cinq exceptions métier
  commentaire.py            Commentaire (dataclass gelée)
  observateur.py            ObservateurTickets, SujetTickets (patron Observateur)
  ticket.py                 Ticket, contexte de la machine à états
  systeme_tickets.py        SystemeTickets, dépôt des tickets et annuaire des utilisateurs
etats/                      EtatTicket, les cinq états concrets et FabriqueEtat
description/                Description, ElementDescription, sous-classes, fabrique
acteurs/                    UtilisateurSysteme, User, Admin
commandes/                  Commande et les six commandes concrètes
sessions/                   SessionOperations, SessionEdition, SessionCreation, LotAdmin, RapportExecution
persistance/
  depot_json.py             DepotJSON, sauvegarde et rechargement en JSON
  stockage_images.py        StockageImages, copie des images jointes dans donnees/images/
ihm/                        CLIENT de l'API REST
  passerelle/
    client_api.py           ClientAPI : seul endroit qui fait des requêtes HTTP (urllib)
    erreurs.py              ServeurInjoignable ; exceptions reconstruites à partir des réponses
    objets_lecture.py       ActeurLu, TicketLu, CommentaireLu, ElementLu, BrouillonLu, RapportLu
    source_tickets.py       SourceTickets : copie locale observable, rafraîchie par /version
  controleurs/              logique de présentation : ControleurPrincipal (fenêtres, sessions,
                            sondage) et, sans tkinter, ControleurAdmin, ControleurUser,
                            ControleurEdition, ControleurDetail
  vues/                     FenetreBase et une fenêtre tkinter par écran (F1 à F8)
outils/
  generer_demo.py           génère donnees/demo.json et ses images avec l'API du modèle
  essai_api.py              vérification rapide de l'API contre un serveur lancé
donnees/
  demo.json                 données de démonstration (versionnées)
  images/                   images de la démonstration (demo_*.png) et copies faites par l'application
  sauvegarde.json           état sauvegardé par le serveur après chaque modification (ignoré par Git)
ressources/                 artefacts de démonstration (texte, image PNG, vidéo factice)
documents/                  diagrammes UML, documents de sprint et rapports
  Lab4_6GEI311_Rapport.pdf  rapport du Lab 4 (source : Lab4_6GEI311_Rapport.docx)
  Lab3_uml_*.png            diagramme de classes du Lab 3 (source : Lab3_6GEI311_diagramme_classes.drawio)
  maquettes/                maquettes Figma des fenêtres de l'interface
  captures_lab3/            captures des fenêtres réelles de la GUI
  captures_lab4/            captures de la page web
  captures/                 captures de la sortie de main.py (Lab 2)
tests/                      tests unitaires et test de non-régression de main.py
```

### Conventions de code

- Tous les attributs d'instance sont privés (préfixe `_`) ; les lectures passent par des propriétés en lecture seule, et aucune méthode `getX()` n'existe.
- Seules quelques méthodes désignées affichent (`viewTicket`, `viewAllTickets`, `Description.afficher`, `RapportExecution.afficher`) ; le reste de l'affichage est fait dans `main.py`.
- Les imports servant uniquement aux annotations sont placés sous `if TYPE_CHECKING:`. Les états se référençant mutuellement, chaque état importe ses successeurs localement dans `gererTransition()`.
