"use strict";
// Page web du bonus W1 : un client de l'API comme la GUI, qui ne passe que par openapi.yaml.
// Aucune règle métier ici : les boutons suivent transitionsPermises, et chaque refus vient
// du serveur, affiché tel quel. Les données sont toujours insérées comme du texte
// (textContent), jamais comme du HTML : un titre de ticket ne peut pas injecter de script.

const INTERVALLE_SONDAGE_MS = 1000;
// Sans délai, une requête vers un serveur figé ne finirait jamais, et le sondage resterait
// bloqué derrière elle : la page ne dirait jamais que le serveur est perdu.
const DELAI_REQUETE_MS = 5000;
const DUREE_NOTIFICATION_MS = 4000;
const CLE_ACTEUR = "gestion-tickets.acteur";

const LIBELLES_STATUT = {
  OUVERT: "Ouvert",
  ASSIGNE: "Assigné",
  VALIDATION: "Validation",
  TERMINE: "Terminé",
  FERME: "Fermé",
};
const LIBELLES_PRIORITE = { BASSE: "Basse", MOYENNE: "Moyenne", HAUTE: "Haute", CRITIQUE: "Critique" };
// Les deux onglets d'un User, comme F3 dans la GUI : chacun est un filtre de GET /tickets.
const ONGLETS_USER = {
  crees: { libelle: "Créés par moi", parametre: "createur", personne: "Assigné" },
  assignes: { libelle: "Assignés à moi", parametre: "assigne", personne: "Créateur" },
};

const etat = {
  acteurs: [],
  users: [],
  acteur: null,
  onglet: "crees",
  filtre: null,
  crees: [],
  assignes: [],
  base: [],
  tickets: [],
  choisi: null,
  detail: null,
  version: null,
  serveurPerdu: false,
  sondageEnCours: false,
};

const $ = (id) => document.getElementById(id);
const estAdmin = () => etat.acteur !== null && etat.acteur.role === "Admin";

// ------------------------------------------------------------------ accès à l'API

class ErreurAPI extends Error {
  constructor(code, type, message) {
    super(message);
    this.code = code;
    this.type = type;
  }
}

/** Requête JSON avec X-Acteur-Id ; une réponse d'erreur devient une ErreurAPI (type, message). */
async function api(methode, chemin, corps) {
  const entetes = {};
  if (etat.acteur) entetes["X-Acteur-Id"] = String(etat.acteur.id);
  const options = {
    method: methode,
    headers: entetes,
    cache: "no-store",
    signal: AbortSignal.timeout(DELAI_REQUETE_MS),
  };
  if (corps !== undefined) {
    entetes["Content-Type"] = "application/json";
    options.body = JSON.stringify(corps);
  }
  let reponse;
  try {
    reponse = await fetch(chemin, options);
  } catch {
    throw new ErreurAPI(0, "ServeurInjoignable", "Le serveur ne répond pas.");
  }
  let texte;
  try {
    texte = await reponse.text();
  } catch {
    throw new ErreurAPI(0, "ServeurInjoignable", "Le serveur a coupé la réponse.");
  }
  let donnees = null;
  try {
    donnees = texte ? JSON.parse(texte) : null;
  } catch {
    donnees = null;
  }
  if (!reponse.ok) {
    const erreur = donnees && donnees.erreur;
    throw new ErreurAPI(
      reponse.status,
      erreur ? erreur.type : "ReponseInvalide",
      erreur ? erreur.message : `Réponse inattendue du serveur (code ${reponse.status})`,
    );
  }
  return donnees;
}

// ------------------------------------------------------------------ construction du DOM

/** Élément avec attributs et enfants ; un enfant texte reste du texte. */
function el(balise, attributs = {}, ...enfants) {
  const element = document.createElement(balise);
  for (const [nom, valeur] of Object.entries(attributs)) {
    if (valeur === null || valeur === undefined || valeur === false) continue;
    if (nom === "class") element.className = valeur;
    else if (nom.startsWith("on")) element.addEventListener(nom.slice(2), valeur);
    else element.setAttribute(nom, valeur === true ? "" : String(valeur));
  }
  for (const enfant of enfants.flat()) {
    if (enfant === null || enfant === undefined || enfant === false) continue;
    element.append(enfant instanceof Node ? enfant : document.createTextNode(String(enfant)));
  }
  return element;
}

const badgeStatut = (statut) => el("span", { class: `badge statut-${statut}` }, LIBELLES_STATUT[statut] ?? statut);
const marquePriorite = (priorite) =>
  el("span", { class: `priorite priorite-${priorite}` }, LIBELLES_PRIORITE[priorite] ?? priorite);

function dateLisible(iso) {
  const date = new Date(`${iso}T00:00:00`);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleDateString("fr-CA", { day: "numeric", month: "long", year: "numeric" });
}

function blocErreur(erreur) {
  return el("p", { class: "erreur", role: "alert" }, el("span", { class: "type" }, erreur.type), erreur.message);
}

function notifier(message) {
  const zone = $("notification");
  zone.textContent = message;
  zone.hidden = false;
  clearTimeout(notifier.minuterie);
  notifier.minuterie = setTimeout(() => (zone.hidden = true), DUREE_NOTIFICATION_MS);
}

// ------------------------------------------------------------------ connexion

async function demarrer() {
  try {
    etat.acteurs = await api("GET", "/acteurs");
    etat.users = await api("GET", "/acteurs?role=User");
  } catch (erreur) {
    $("erreur-acteurs").textContent = `Impossible de lire les comptes : ${erreur.message}`;
    return;
  }
  const choix = $("acteur");
  for (const acteur of etat.acteurs) {
    choix.append(el("option", { value: acteur.id }, `${acteur.nom} (${acteur.role})`));
  }
  choix.addEventListener("change", () => choisirActeur(Number(choix.value) || null));
  $("bouton-nouveau").addEventListener("click", ouvrirFormulaire);
  $("bouton-annuler").addEventListener("click", fermerFormulaire);
  $("formulaire").addEventListener("submit", creerTicket);

  let memorise = null;
  try {
    memorise = Number(localStorage.getItem(CLE_ACTEUR)) || null;
  } catch {
    memorise = null; // Stockage indisponible (navigation privée) : on redemande simplement.
  }
  if (memorise && etat.acteurs.some((a) => a.id === memorise)) {
    choix.value = String(memorise);
    await choisirActeur(memorise);
  }
  setInterval(sonder, INTERVALLE_SONDAGE_MS);
}

async function choisirActeur(identifiant) {
  etat.acteur = etat.acteurs.find((a) => a.id === identifiant) ?? null;
  try {
    if (etat.acteur) localStorage.setItem(CLE_ACTEUR, String(etat.acteur.id));
    else localStorage.removeItem(CLE_ACTEUR);
  } catch {
    // Sans stockage, le choix vaut pour cette page seulement.
  }
  etat.choisi = null;
  etat.detail = null;
  etat.version = null;
  etat.onglet = "crees";
  etat.filtre = null;
  fermerFormulaire();
  $("accueil").hidden = etat.acteur !== null;
  $("application").hidden = etat.acteur === null;
  // Deux vues, comme F2 et F3 dans la GUI : l'Admin voit tout, le User ses tickets.
  $("bouton-nouveau").hidden = !etat.acteur || estAdmin();
  $("onglets").hidden = !etat.acteur || estAdmin();
  $("titre-liste").textContent = estAdmin() ? "Tous les tickets" : "Mes tickets";
  $("role").hidden = !etat.acteur;
  $("role").textContent = etat.acteur ? etat.acteur.role : "";
  $("role").className = estAdmin() ? "role admin" : "role";
  dessinerDetail();
  if (etat.acteur) await rafraichir();
}

// ------------------------------------------------------------------ liste, onglets et filtres

/** Filtre de la vue : aucun pour l'Admin, créateur ou assigné (l'acteur) pour un User. */
function parametresVue() {
  if (estAdmin()) return {};
  return { [ONGLETS_USER[etat.onglet].parametre]: etat.acteur.id };
}

function requete(parametres) {
  const chaine = new URLSearchParams(parametres).toString();
  return chaine ? `?${chaine}` : "";
}

/** Relit la liste, filtrée par le serveur, et ce qu'il faut pour les compteurs. */
async function rafraichir() {
  const vue = parametresVue();
  const filtre = etat.filtre;
  try {
    const [crees, assignes, tous, filtres] = await Promise.all([
      estAdmin() ? null : api("GET", "/tickets" + requete({ createur: etat.acteur.id })),
      estAdmin() ? null : api("GET", "/tickets" + requete({ assigne: etat.acteur.id })),
      estAdmin() ? api("GET", "/tickets") : null,
      filtre ? api("GET", "/tickets" + requete({ ...vue, statut: filtre })) : null,
    ]);
    etat.crees = crees ?? [];
    etat.assignes = assignes ?? [];
    etat.base = estAdmin() ? tous : etat.onglet === "assignes" ? etat.assignes : etat.crees;
    etat.tickets = filtres ?? etat.base;
    serveurRetrouve();
  } catch (erreur) {
    if (erreur.code === 0) serveurPerdu();
    return;
  }
  dessinerOnglets();
  dessinerFiltres();
  dessinerListe();
  if (etat.choisi !== null) await chargerDetail(etat.choisi, false);
}

function dessinerOnglets() {
  if (estAdmin()) return;
  const nombres = { crees: etat.crees.length, assignes: etat.assignes.length };
  $("onglets").replaceChildren(
    ...Object.entries(ONGLETS_USER).map(([cle, onglet]) =>
      el(
        "button",
        {
          type: "button",
          role: "tab",
          "aria-selected": etat.onglet === cle ? "true" : "false",
          onclick: () => {
            if (etat.onglet === cle) return;
            etat.onglet = cle;
            etat.filtre = null;
            etat.choisi = null;
            etat.detail = null;
            dessinerDetail();
            rafraichir();
          },
        },
        onglet.libelle,
        el("span", { class: "nombre" }, nombres[cle]),
      ),
    ),
  );
}

function dessinerFiltres() {
  const zone = $("filtres");
  const boutons = [[null, "Tous", etat.base.length]].concat(
    Object.entries(LIBELLES_STATUT).map(([statut, libelle]) => [
      statut,
      libelle,
      etat.base.filter((t) => t.statut === statut).length,
    ]),
  );
  zone.replaceChildren(
    ...boutons.map(([statut, libelle, nombre]) =>
      el(
        "button",
        {
          type: "button",
          "aria-pressed": etat.filtre === statut ? "true" : "false",
          onclick: () => {
            etat.filtre = statut;
            rafraichir();
          },
        },
        libelle,
        el("span", { class: "nombre" }, nombre),
      ),
    ),
  );
}

function dessinerListe() {
  // Dans « Assignés à moi », l'assigné est toujours moi : la colonne montre le créateur.
  const montrerCreateur = !estAdmin() && etat.onglet === "assignes";
  $("entete-personne").textContent = montrerCreateur ? "Créateur" : "Assigné";
  const personne = (ticket) => (montrerCreateur ? ticket.createur : ticket.assigne);
  const lignes = etat.tickets.map((ticket) =>
    el(
      "tr",
      {
        tabindex: 0,
        "aria-selected": ticket.id === etat.choisi ? "true" : "false",
        onclick: () => chargerDetail(ticket.id, true),
        onkeydown: (evenement) => {
          if (evenement.key === "Enter" || evenement.key === " ") {
            evenement.preventDefault();
            chargerDetail(ticket.id, true);
          }
        },
      },
      el("td", { class: "numero" }, ticket.id),
      el("td", {}, ticket.titre),
      el("td", { class: "col-priorite" }, marquePriorite(ticket.priorite)),
      el("td", {}, badgeStatut(ticket.statut)),
      el("td", { class: "col-assigne" }, personne(ticket) ? personne(ticket).nom : el("span", { class: "vide" }, "aucun")),
    ),
  );
  $("lignes").replaceChildren(...lignes);
  $("liste-vide").hidden = lignes.length > 0;
  $("liste-vide").textContent = etat.filtre
    ? `Aucun ticket « ${LIBELLES_STATUT[etat.filtre]} » ici.`
    : estAdmin()
      ? "Aucun ticket."
      : etat.onglet === "assignes"
        ? "Aucun ticket ne vous est assigné."
        : "Vous n'avez créé aucun ticket.";
}

// ------------------------------------------------------------------ détail

async function chargerDetail(ticketId, parClic) {
  etat.choisi = ticketId;
  if (parClic) dessinerListe();
  try {
    etat.detail = await api("GET", `/ticket/${ticketId}`);
  } catch (erreur) {
    if (erreur.code === 404) {
      etat.detail = null;
      etat.choisi = null;
      dessinerListe();
      $("detail").replaceChildren(el("p", { class: "vide" }, `Le ticket #${ticketId} a été retiré.`));
    } else if (erreur.code === 0) {
      serveurPerdu();
    } else {
      $("detail").replaceChildren(blocErreur(erreur));
    }
    return;
  }
  dessinerDetail();
}

function dessinerDetail(erreur) {
  const zone = $("detail");
  const t = etat.detail;
  if (!t) {
    zone.replaceChildren(el("p", { class: "vide" }, "Choisissez un ticket dans la liste pour voir son détail."));
    return;
  }
  const majDifferente = t.dateMiseAJour !== t.dateCreation;
  zone.replaceChildren(
    el("div", { class: "numero-ticket" }, `Ticket #${t.id}`),
    el("h2", {}, t.titre),
    el(
      "dl",
      { class: "fiche" },
      el("dt", {}, "Statut"), el("dd", {}, badgeStatut(t.statut)),
      el("dt", {}, "Priorité"), el("dd", {}, marquePriorite(t.priorite)),
      el("dt", {}, "Créateur"), el("dd", {}, t.createur ? t.createur.nom : "aucun"),
      el("dt", {}, "Assigné"), el("dd", {}, t.assigne ? t.assigne.nom : "aucun"),
      el("dt", {}, "Créé le"),
      el("dd", {}, dateLisible(t.dateCreation), majDifferente ? `, mis à jour le ${dateLisible(t.dateMiseAJour)}` : ""),
    ),
    el("h3", {}, "Description"),
    ...(t.description.length ? t.description.map(elementDescription) : [el("p", { class: "vide" }, "Aucune description.")]),
    el("h3", {}, `Commentaires (${t.commentaires.length})`),
    t.commentaires.length
      ? el(
          "ul",
          { class: "commentaires" },
          t.commentaires.map((c) =>
            el("li", {}, el("div", { class: "auteur" }, `${c.auteur.nom} · ${dateLisible(c.date)}`), el("p", {}, c.texte)),
          ),
        )
      : el("p", { class: "vide" }, "Aucun commentaire."),
    zoneActions(t, erreur),
  );
}

function elementDescription(element) {
  if (element.type === "image") {
    return el(
      "figure",
      {},
      // L'URL vient de l'API (/ticket/{id}/image/{nom}) : jamais le chemin disque.
      el("img", { src: element.url, alt: `Image : ${element.nom}`, loading: "lazy" }),
      el("figcaption", {}, element.nom),
    );
  }
  if (element.type === "texte_saisi") return el("p", { class: "texte" }, element.contenu);
  if (element.type === "texte") {
    return el("div", {}, el("p", { class: "aide" }, element.nom), el("p", { class: "texte" }, element.contenu));
  }
  return el("p", { class: "vide" }, `Vidéo non affichée : ${element.resume}`);
}

// ------------------------------------------------------------------ actions

/** Les boutons suivent transitionsPermises : la règle reste dans les états du serveur. */
function zoneActions(t, erreur) {
  return estAdmin() ? actionsAdmin(t, erreur) : actionsUser(t, erreur);
}

/** Comme F3 : l'assigné soumet à validation, le créateur supprime un ticket jamais assigné.
 *  Ces conditions ne font que griser les boutons ; c'est le serveur qui décide. */
function actionsUser(t, erreur) {
  const moi = etat.acteur.id;
  const assigneAMoi = t.assigne !== null && t.assigne.id === moi;
  const creeParMoi = t.createur !== null && t.createur.id === moi;
  const peutSoumettre = assigneAMoi && t.transitionsPermises.includes("VALIDATION");
  const peutSupprimer = creeParMoi && !t.dejaAssigne;
  const raisons = [];
  if (assigneAMoi && !peutSoumettre) {
    raisons.push(`Soumission impossible depuis « ${LIBELLES_STATUT[t.statut]} ».`);
  }
  if (!assigneAMoi) raisons.push("Seul l'assigné soumet le ticket à validation.");
  if (creeParMoi && t.dejaAssigne) raisons.push("Ce ticket a déjà été assigné : il ne peut plus être supprimé.");
  if (!creeParMoi) raisons.push("Seul le créateur peut supprimer le ticket.");
  return el(
    "div",
    { class: "actions" },
    el("h3", {}, "Actions"),
    el(
      "div",
      { class: "ligne-actions" },
      el(
        "button",
        { type: "button", class: "bouton principal", disabled: !peutSoumettre, onclick: () => changerStatut(t, "VALIDATION") },
        "Soumettre à validation",
      ),
      el(
        "button",
        { type: "button", class: "bouton danger", disabled: !peutSupprimer, onclick: () => supprimerTicket(t) },
        "Supprimer…",
      ),
    ),
    raisons.length ? el("p", { class: "raison" }, raisons.join(" ")) : null,
    erreur ? blocErreur(erreur) : null,
  );
}

function actionsAdmin(t, erreur) {
  const permis = new Set(t.transitionsPermises);
  const choixUser = el(
    "select",
    { "aria-label": "Assigner à", disabled: !permis.has("ASSIGNE") },
    etat.users.map((u) =>
      el("option", { value: u.id, selected: t.assigne && t.assigne.id === u.id }, u.nom),
    ),
  );
  const bouton = (statut, libelle, classe, action) =>
    el("button", { type: "button", class: `bouton ${classe}`, disabled: !permis.has(statut), onclick: action }, libelle);
  const raison = permis.size
    ? `Depuis « ${LIBELLES_STATUT[t.statut]} », le serveur permet : ${t.transitionsPermises
        .map((s) => LIBELLES_STATUT[s])
        .join(", ")}.`
    : `Aucun changement de statut permis depuis « ${LIBELLES_STATUT[t.statut]} ».`;
  return el(
    "div",
    { class: "actions" },
    el("h3", {}, "Changer le statut"),
    el(
      "div",
      { class: "ligne-actions" },
      choixUser,
      bouton("ASSIGNE", t.assigne ? "Réassigner" : "Assigner", "principal", () =>
        changerStatut(t, "ASSIGNE", Number(choixUser.value)),
      ),
      bouton("OUVERT", "Désassigner", "", () => changerStatut(t, "OUVERT")),
      bouton("TERMINE", "Valider", "", () => changerStatut(t, "TERMINE")),
      bouton("FERME", "Fermer…", "danger", () => {
        if (confirm(`Fermer le ticket #${t.id} ? C'est définitif.`)) changerStatut(t, "FERME");
      }),
    ),
    el("p", { class: "raison" }, raison),
    erreur ? blocErreur(erreur) : null,
  );
}

async function changerStatut(ticket, statut, assigneId) {
  const corps = statut === "ASSIGNE" ? { statut, assigneId } : { statut };
  try {
    etat.detail = await api("PATCH", `/ticket/${ticket.id}`, corps);
  } catch (erreur) {
    if (erreur.code === 0) serveurPerdu();
    dessinerDetail(erreur);
    return;
  }
  notifier(`Ticket #${ticket.id} : ${LIBELLES_STATUT[etat.detail.statut]}`);
  dessinerDetail();
  await rafraichir();
}

async function supprimerTicket(ticket) {
  if (!confirm(`Supprimer le ticket #${ticket.id} « ${ticket.titre} » ? C'est définitif.`)) return;
  try {
    await api("DELETE", `/ticket/${ticket.id}`);
  } catch (erreur) {
    if (erreur.code === 0) serveurPerdu();
    dessinerDetail(erreur);
    return;
  }
  notifier(`Ticket #${ticket.id} supprimé`);
  etat.choisi = null;
  etat.detail = null;
  dessinerDetail();
  await rafraichir();
}

// ------------------------------------------------------------------ création par un User

function ouvrirFormulaire() {
  $("formulaire").hidden = false;
  $("erreur-formulaire").hidden = true;
  $("champ-titre").focus();
}

function fermerFormulaire() {
  $("formulaire").reset();
  $("formulaire").hidden = true;
  $("erreur-formulaire").hidden = true;
}

async function creerTicket(evenement) {
  evenement.preventDefault();
  const formulaire = evenement.currentTarget;
  const donnees = new FormData(formulaire);
  const corps = {
    titre: String(donnees.get("titre") ?? ""),
    priorite: String(donnees.get("priorite") ?? ""),
    texte: String(donnees.get("texte") ?? ""),
  };
  const bouton = $("bouton-creer");
  bouton.disabled = true;
  try {
    const resultat = await api("POST", "/tickets", corps);
    fermerFormulaire();
    notifier(`Ticket #${resultat.ticket.id} « ${resultat.ticket.titre} » créé`);
    // Le nouveau ticket est dans « Créés par moi » : on y revient pour le montrer.
    etat.onglet = "crees";
    etat.filtre = null;
    etat.choisi = resultat.ticket.id;
    etat.detail = resultat.ticket;
    dessinerDetail();
    await rafraichir();
  } catch (erreur) {
    if (erreur.code === 0) serveurPerdu();
    const zone = $("erreur-formulaire");
    zone.replaceChildren(el("span", { class: "type" }, erreur.type), erreur.message);
    zone.hidden = false;
  } finally {
    bouton.disabled = false;
  }
}

// ------------------------------------------------------------------ suivi des changements

/** Une fois par seconde : GET /version, et une relecture complète seulement s'il a changé. */
async function sonder() {
  if (!etat.acteur || etat.sondageEnCours) return;
  etat.sondageEnCours = true;
  try {
    const { version } = await api("GET", "/version");
    serveurRetrouve();
    if (version !== etat.version) {
      etat.version = version;
      await rafraichir();
    }
  } catch (erreur) {
    if (erreur.code === 0) serveurPerdu();
  } finally {
    etat.sondageEnCours = false;
  }
}

function serveurPerdu() {
  etat.serveurPerdu = true;
  $("bandeau").hidden = false;
  $("direct").textContent = "Serveur injoignable";
  $("direct").classList.add("perdu");
}

function serveurRetrouve() {
  if (etat.serveurPerdu) {
    etat.serveurPerdu = false;
    $("bandeau").hidden = true;
    etat.version = null; // Tout relire : on ne sait pas ce qui a changé pendant la coupure.
  }
  $("direct").classList.remove("perdu");
  $("direct").textContent = etat.version === null ? "À jour" : `À jour · version ${etat.version}`;
}

demarrer();
