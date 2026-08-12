"""
Application locale de gestion des devis et factures (Streamlit + SQLite).

Lancement :
    streamlit run app.py
"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

import db
from pdf_generator import generer_pdf, LOGO_PATH

st.set_page_config(page_title="Devis & Factures", page_icon="🧾", layout="wide")
db.init_db()


# ---------------------------------------------------------------------------
# UTILITAIRES
# ---------------------------------------------------------------------------

def eur(montant):
    return f"{montant:,.2f} €".replace(",", " ").replace(".", ",")


def reset_formulaire_document():
    for cle in list(st.session_state.keys()):
        if cle.startswith(("desc_", "detail_", "qte_", "pu_", "tva_")) or cle in (
            "edit_doc_id", "type_doc_input", "client_select", "numero_doc_input",
            "date_emission_input", "date_echeance_input", "def_echeance_checkbox",
            "statut_input", "conditions_input", "notes_input", "num_lignes",
            "mode_reglement_input", "montant_acompte_input",
        ):
            del st.session_state[cle]


def charger_document_pour_edition(document_id):
    reset_formulaire_document()
    document = db.get_document(document_id)
    lignes = db.get_lignes(document_id)

    st.session_state.edit_doc_id = document_id
    st.session_state.type_doc_input = document["type_doc"]
    st.session_state.client_select = document["client_id"]
    st.session_state.numero_doc_input = document["numero"]
    st.session_state.date_emission_input = date.fromisoformat(document["date_emission"])
    if document["date_echeance"]:
        st.session_state.def_echeance_checkbox = True
        st.session_state.date_echeance_input = date.fromisoformat(document["date_echeance"])
    else:
        st.session_state.def_echeance_checkbox = False
    st.session_state.statut_input = document["statut"]
    st.session_state.conditions_input = document["conditions_paiement"] or ""
    st.session_state.notes_input = document["notes"] or ""
    st.session_state.mode_reglement_input = document.get("mode_reglement") or db.MODES_REGLEMENT[0]
    st.session_state.montant_acompte_input = document.get("montant_acompte") or 0.0

    st.session_state.num_lignes = max(len(lignes), 1)
    for i, ligne in enumerate(lignes):
        st.session_state[f"desc_{i}"] = ligne["description"]
        st.session_state[f"detail_{i}"] = ligne.get("detail") or ""
        st.session_state[f"qte_{i}"] = ligne["quantite"]
        st.session_state[f"pu_{i}"] = ligne["prix_unitaire_ht"]
        st.session_state[f"tva_{i}"] = ligne["taux_tva"]


def aller_a_edition(document_id):
    """Callback (on_click) : charge le document et bascule sur la page d'édition.

    Doit s'exécuter en tant que callback : modifier st.session_state.page_actuelle
    après que le widget radio (key="page_actuelle") a déjà été instancié dans le
    run en cours est interdit par Streamlit.
    """
    charger_document_pour_edition(document_id)
    st.session_state.page_actuelle = "🆕 Créer / Éditer"


def dupliquer_document(document_id):
    document = db.get_document(document_id)
    lignes = db.get_lignes(document_id)
    lignes_pour_creation = [
        {
            "description": l["description"],
            "detail": l.get("detail"),
            "quantite": l["quantite"],
            "prix_unitaire": l["prix_unitaire_ht"],
            "taux_tva": l["taux_tva"],
        }
        for l in lignes
    ]
    numero = db.next_numero(document["type_doc"])
    statut_defaut = db.STATUTS_DEVIS[0] if document["type_doc"] == "Devis" else db.STATUTS_FACTURE[0]
    return db.create_document(
        document["type_doc"], numero, document["client_id"], date.today(), None,
        statut_defaut, document["notes"], document["conditions_paiement"], lignes_pour_creation,
        mode_reglement=document.get("mode_reglement"), montant_acompte=0.0,
    )


def supprimer_ligne(index):
    """Callback (on_click) : retire la ligne `index` et décale les suivantes.

    Doit s'exécuter en tant que callback (avant l'instanciation des widgets de
    la prochaine exécution du script) : Streamlit interdit de modifier
    st.session_state pour une clé dont le widget a déjà été créé dans le run
    en cours.
    """
    n = st.session_state.num_lignes
    for j in range(index, n - 1):
        st.session_state[f"desc_{j}"] = st.session_state.get(f"desc_{j + 1}", "")
        st.session_state[f"detail_{j}"] = st.session_state.get(f"detail_{j + 1}", "")
        st.session_state[f"qte_{j}"] = st.session_state.get(f"qte_{j + 1}", 1.0)
        st.session_state[f"pu_{j}"] = st.session_state.get(f"pu_{j + 1}", 0.0)
        st.session_state[f"tva_{j}"] = st.session_state.get(f"tva_{j + 1}", db.TAUX_TVA_DISPONIBLES[0])
    dernier = n - 1
    for prefixe in ("desc_", "detail_", "qte_", "pu_", "tva_"):
        st.session_state.pop(f"{prefixe}{dernier}", None)
    st.session_state.num_lignes = n - 1


st.title("🧾 Devis & Factures")

PAGES = ["🆕 Créer / Éditer", "🗂️ Documents", "💰 Tarifs", "👤 Clients", "🏢 Paramètres", "📊 Tableau de bord"]
st.session_state.setdefault("page_actuelle", PAGES[0])
page = st.radio("Navigation", PAGES, key="page_actuelle", horizontal=True, label_visibility="collapsed")
st.markdown("---")


# ---------------------------------------------------------------------------
# PAGE 1 : CRÉER / ÉDITER UN DOCUMENT
# ---------------------------------------------------------------------------
if page == "🆕 Créer / Éditer":
    if st.session_state.get("edit_doc_id"):
        col_titre, col_annuler = st.columns([4, 1])
        with col_titre:
            st.info(f"Modification du document **{st.session_state.get('numero_doc_input', '')}**")
        with col_annuler:
            if st.button("➕ Nouveau document", use_container_width=True):
                reset_formulaire_document()
                st.rerun()

    clients = db.list_clients()
    if not clients:
        st.warning("Aucun client enregistré. Ajoutez d'abord un client dans l'onglet **Clients**.")
    else:
        clients_par_id = {c["id"]: c["nom"] for c in clients}

        st.session_state.setdefault("type_doc_input", "Devis")
        st.session_state.setdefault("num_lignes", 1)
        st.session_state.setdefault("client_select", clients[0]["id"])
        st.session_state.setdefault("date_emission_input", date.today())
        st.session_state.setdefault("def_echeance_checkbox", False)
        st.session_state.setdefault("conditions_input", "")
        st.session_state.setdefault("notes_input", "")

        type_doc = st.selectbox("Type de document", ["Devis", "Facture"], key="type_doc_input")

        # Suggestion automatique du numéro (uniquement en création)
        if not st.session_state.get("edit_doc_id"):
            prefixe_attendu = "DEV" if type_doc == "Devis" else "FAC"
            valeur_actuelle = st.session_state.get("numero_doc_input", "")
            if not valeur_actuelle.startswith(prefixe_attendu):
                st.session_state["numero_doc_input"] = db.next_numero(type_doc)

        # Garde-fou : le statut doit correspondre au type de document sélectionné
        statuts = db.STATUTS_DEVIS if type_doc == "Devis" else db.STATUTS_FACTURE
        if st.session_state.get("statut_input") not in statuts:
            st.session_state["statut_input"] = statuts[0]

        col1, col2 = st.columns(2)
        with col1:
            client_id = st.selectbox(
                "Client", options=list(clients_par_id.keys()),
                format_func=lambda cid: clients_par_id[cid], key="client_select",
            )
            numero_doc = st.text_input("Numéro du document", key="numero_doc_input")
            statut = st.selectbox("Statut", statuts, key="statut_input")

        with col2:
            date_emission = st.date_input("Date d'émission", key="date_emission_input")
            definir_echeance = st.checkbox("Définir une date d'échéance", key="def_echeance_checkbox")
            date_echeance = None
            if definir_echeance:
                st.session_state.setdefault("date_echeance_input", date.today() + timedelta(days=30))
                date_echeance = st.date_input("Date d'échéance", key="date_echeance_input")

        mode_reglement = None
        montant_acompte = 0.0
        if type_doc == "Facture":
            st.session_state.setdefault("mode_reglement_input", db.MODES_REGLEMENT[0])
            st.session_state.setdefault("montant_acompte_input", 0.0)

            col3, col4 = st.columns(2)
            with col3:
                mode_reglement = st.selectbox(
                    "Mode de règlement", db.MODES_REGLEMENT, key="mode_reglement_input"
                )
            with col4:
                montant_acompte = st.number_input(
                    "Acompte(s) déjà versé(s) — TTC (€)", key="montant_acompte_input",
                    min_value=0.0, step=10.0, format="%.2f",
                    help="À déduire du total, par exemple si un acompte a déjà été réglé avant l'envoi de cette facture.",
                )

        st.markdown("---")
        st.markdown("**Lignes du document**")

        col_plus, col_catalogue, col_catalogue_btn = st.columns([1, 2, 2])
        with col_plus:
            if st.button("➕ Ajouter une ligne vide", use_container_width=True):
                st.session_state.num_lignes += 1
                st.rerun()

        tarifs_actifs = db.list_tarifs(actifs_seulement=True)
        if tarifs_actifs:
            tarifs_par_id = {t["id"]: f"{t['designation']} — {t['montant_ttc']:.2f} € TTC" for t in tarifs_actifs}
            with col_catalogue:
                tarif_choisi_id = st.selectbox(
                    "Depuis le catalogue de tarifs", options=list(tarifs_par_id.keys()),
                    format_func=lambda tid: tarifs_par_id[tid], key="tarif_catalogue_select",
                    label_visibility="collapsed",
                )
            with col_catalogue_btn:
                if st.button("📥 Ajouter ce tarif comme ligne", use_container_width=True):
                    tarif = db.get_tarif(tarif_choisi_id)
                    index = st.session_state.num_lignes
                    st.session_state.num_lignes += 1
                    st.session_state[f"desc_{index}"] = tarif["designation"]
                    st.session_state[f"detail_{index}"] = tarif["description"] or ""
                    st.session_state[f"qte_{index}"] = 1.0
                    st.session_state[f"pu_{index}"] = round(db.tarif_prix_unitaire_ht(tarif), 4)
                    st.session_state[f"tva_{index}"] = tarif["taux_tva"]
                    st.rerun()
        else:
            with col_catalogue:
                st.caption("Aucun tarif dans le catalogue — voir la page **Tarifs**.")

        if st.session_state.num_lignes > 0:
            st.write("")
            col_h = st.columns([4, 1, 2, 1, 1.3, 0.6])
            col_h[0].markdown("**Description**")
            col_h[1].markdown("**Qté**")
            col_h[2].markdown("**Prix unit. HT (€)**")
            col_h[3].markdown("**TVA (%)**")
            col_h[4].markdown("**Total TTC ligne**")

        for i in range(st.session_state.num_lignes):
            st.session_state.setdefault(f"desc_{i}", "")
            st.session_state.setdefault(f"detail_{i}", "")
            st.session_state.setdefault(f"qte_{i}", 1.0)
            st.session_state.setdefault(f"pu_{i}", 0.0)
            st.session_state.setdefault(f"tva_{i}", db.TAUX_TVA_DISPONIBLES[0])

            c1, c2, c3, c4, c5, c6 = st.columns([4, 1, 2, 1, 1.3, 0.6])
            with c1:
                st.text_input(
                    f"Description ligne {i + 1}", key=f"desc_{i}",
                    label_visibility="collapsed", placeholder=f"Produit / prestation {i + 1}",
                )
                st.text_input(
                    f"Détail ligne {i + 1}", key=f"detail_{i}",
                    label_visibility="collapsed",
                    placeholder="Détail complémentaire (optionnel, affiché en italique sur le PDF)",
                )
            with c2:
                st.number_input(
                    f"Qté ligne {i + 1}", key=f"qte_{i}", min_value=0.0,
                    step=1.0, label_visibility="collapsed",
                )
            with c3:
                st.number_input(
                    f"Prix unitaire ligne {i + 1}", key=f"pu_{i}", min_value=0.0,
                    step=10.0, format="%.2f", label_visibility="collapsed",
                )
            with c4:
                st.selectbox(
                    f"TVA ligne {i + 1}", db.TAUX_TVA_DISPONIBLES, key=f"tva_{i}",
                    label_visibility="collapsed",
                )
            with c5:
                total_ligne_ttc = (
                    st.session_state[f"qte_{i}"] * st.session_state[f"pu_{i}"]
                    * (1 + st.session_state[f"tva_{i}"] / 100)
                )
                st.markdown(f"<div style='padding-top: 8px'>{eur(total_ligne_ttc)}</div>", unsafe_allow_html=True)
            with c6:
                st.button(
                    "🗑️", key=f"suppr_ligne_{i}", help="Retirer cette ligne",
                    on_click=supprimer_ligne, args=(i,),
                )

        if st.session_state.num_lignes == 0:
            st.caption("Aucune ligne — ajoutez-en une ci-dessus ou choisissez un tarif du catalogue.")

        st.markdown("---")
        conditions = st.text_area(
            "Conditions de paiement", key="conditions_input",
            placeholder="Ex : paiement à 30 jours, acompte de 30 % à la commande...",
        )
        notes = st.text_area("Notes", key="notes_input")

        # Aperçu des totaux en direct
        lignes_apercu = []
        for i in range(st.session_state.num_lignes):
            qte = st.session_state.get(f"qte_{i}", 0.0)
            pu = st.session_state.get(f"pu_{i}", 0.0)
            tva = st.session_state.get(f"tva_{i}", 0.0)
            if qte > 0:
                lignes_apercu.append({"quantite": qte, "prix_unitaire": pu, "taux_tva": tva})
        if lignes_apercu:
            total_ht, detail_tva, total_ttc = db.calculer_totaux(lignes_apercu)
            if type_doc == "Facture" and montant_acompte > 0:
                colA, colB, colC, colD = st.columns(4)
                colA.metric("Total HT", eur(total_ht))
                colB.metric("TVA", eur(sum(detail_tva.values())))
                colC.metric("Total TTC", eur(total_ttc))
                colD.metric("Net à payer", eur(db.net_a_payer(total_ttc, montant_acompte)))
            else:
                colA, colB, colC = st.columns(3)
                colA.metric("Total HT", eur(total_ht))
                colB.metric("TVA", eur(sum(detail_tva.values())))
                colC.metric("Total TTC", eur(total_ttc))

        st.markdown("---")
        if st.button("💾 Enregistrer le document", use_container_width=True, type="primary"):
            lignes_saisies = []
            for i in range(st.session_state.num_lignes):
                desc = st.session_state.get(f"desc_{i}", "").strip()
                detail = st.session_state.get(f"detail_{i}", "").strip()
                qte = st.session_state.get(f"qte_{i}", 0.0)
                pu = st.session_state.get(f"pu_{i}", 0.0)
                tva = st.session_state.get(f"tva_{i}", 0.0)
                if desc and qte > 0:
                    lignes_saisies.append(
                        {"description": desc, "detail": detail, "quantite": qte, "prix_unitaire": pu, "taux_tva": tva}
                    )

            if not numero_doc.strip():
                st.error("Le numéro de document est obligatoire.")
            elif not lignes_saisies:
                st.error("Ajoutez au moins une ligne valide (description renseignée + quantité > 0).")
            else:
                if st.session_state.get("edit_doc_id"):
                    db.update_document(
                        st.session_state.edit_doc_id, type_doc, numero_doc.strip(), client_id,
                        date_emission, date_echeance, statut, notes, conditions, lignes_saisies,
                        mode_reglement=mode_reglement, montant_acompte=montant_acompte,
                    )
                    st.success(f"Document **{numero_doc}** mis à jour.")
                else:
                    db.create_document(
                        type_doc, numero_doc.strip(), client_id, date_emission, date_echeance,
                        statut, notes, conditions, lignes_saisies,
                        mode_reglement=mode_reglement, montant_acompte=montant_acompte,
                    )
                    st.success(f"Document **{numero_doc}** enregistré.")
                reset_formulaire_document()
                st.rerun()


# ---------------------------------------------------------------------------
# PAGE 2 : DOCUMENTS (LISTE, FILTRES, ACTIONS)
# ---------------------------------------------------------------------------
elif page == "🗂️ Documents":
    entreprise = db.get_entreprise()

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        filtre_type = st.selectbox("Type", ["Tous", "Devis", "Facture"], key="filtre_type")
    with col_f2:
        statuts_possibles = ["Tous"] + sorted(set(db.STATUTS_DEVIS + db.STATUTS_FACTURE))
        filtre_statut = st.selectbox("Statut", statuts_possibles, key="filtre_statut")
    with col_f3:
        clients = db.list_clients()
        options_client = {0: "Tous"} | {c["id"]: c["nom"] for c in clients}
        filtre_client = st.selectbox(
            "Client", options=list(options_client.keys()),
            format_func=lambda cid: options_client[cid], key="filtre_client",
        )

    documents = db.list_documents(
        type_doc=filtre_type, statut=filtre_statut, client_id=filtre_client or None
    )

    if not documents:
        st.info("Aucun document ne correspond aux filtres sélectionnés.")
    else:
        lignes_tableau = []
        for doc in documents:
            lignes_doc = db.get_lignes(doc["id"])
            total_ht, _, total_ttc = db.calculer_totaux(
                [{"quantite": l["quantite"], "prix_unitaire": l["prix_unitaire_ht"], "taux_tva": l["taux_tva"]} for l in lignes_doc]
            )
            lignes_tableau.append({
                "Numéro": doc["numero"],
                "Type": doc["type_doc"],
                "Client": doc["client_nom"],
                "Date": doc["date_emission"],
                "Statut": doc["statut"],
                "Total HT": total_ht,
                "Total TTC": total_ttc,
            })

        df = pd.DataFrame(lignes_tableau)
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("Actions sur un document")

        numeros = [d["numero"] for d in documents]
        numero_selectionne = st.selectbox("Sélectionner un document", numeros, key="doc_selectionne")
        doc = next(d for d in documents if d["numero"] == numero_selectionne)
        lignes_doc = db.get_lignes(doc["id"])
        client_doc = db.get_client(doc["client_id"])

        with st.expander("Détail du document", expanded=True):
            total_ht, detail_tva, total_ttc = db.calculer_totaux(
                [{"quantite": l["quantite"], "prix_unitaire": l["prix_unitaire_ht"], "taux_tva": l["taux_tva"]} for l in lignes_doc]
            )
            st.write(f"**Client :** {client_doc['nom']}")
            st.write(f"**Émis le :** {doc['date_emission']}" + (f" • **Échéance :** {doc['date_echeance']}" if doc["date_echeance"] else ""))
            if doc["type_doc"] == "Facture" and doc.get("mode_reglement"):
                st.write(f"**Mode de règlement :** {doc['mode_reglement']}")
            st.dataframe(
                pd.DataFrame([
                    {
                        "Description": l["description"], "Détail": l.get("detail") or "",
                        "Quantité": l["quantite"],
                        "Prix unitaire HT": l["prix_unitaire_ht"], "TVA %": l["taux_tva"],
                        "Total HT": l["quantite"] * l["prix_unitaire_ht"],
                    } for l in lignes_doc
                ]),
                use_container_width=True, hide_index=True,
            )
            montant_acompte_doc = doc.get("montant_acompte") or 0.0
            if doc["type_doc"] == "Facture" and montant_acompte_doc > 0:
                colA, colB, colC, colD = st.columns(4)
                colA.metric("Total HT", eur(total_ht))
                colB.metric("TVA", eur(sum(detail_tva.values())))
                colC.metric("Total TTC", eur(total_ttc))
                colD.metric("Net à payer", eur(db.net_a_payer(total_ttc, montant_acompte_doc)))
                st.caption(f"Acompte déjà versé déduit : {eur(montant_acompte_doc)}")
            else:
                colA, colB, colC = st.columns(3)
                colA.metric("Total HT", eur(total_ht))
                colB.metric("TVA", eur(sum(detail_tva.values())))
                colC.metric("Total TTC", eur(total_ttc))

        col_a1, col_a2, col_a3, col_a4 = st.columns(4)

        with col_a1:
            st.button(
                "✏️ Éditer", use_container_width=True,
                on_click=aller_a_edition, args=(doc["id"],),
            )

        with col_a2:
            pdf_bytes = generer_pdf(doc, client_doc, lignes_doc, entreprise)
            st.download_button(
                "📄 Télécharger le PDF", data=pdf_bytes, file_name=f"{doc['numero']}.pdf",
                mime="application/pdf", use_container_width=True,
            )

        with col_a3:
            if doc["type_doc"] == "Devis":
                if st.button("➡️ Transformer en facture", use_container_width=True):
                    nouvel_id = db.transformer_devis_en_facture(doc["id"])
                    st.success(f"Facture créée à partir du devis {doc['numero']}.")
                    st.rerun()
            else:
                if st.button("🔀 Dupliquer", use_container_width=True):
                    dupliquer_document(doc["id"])
                    st.success("Document dupliqué.")
                    st.rerun()

        with col_a4:
            if st.button("🗑️ Supprimer", use_container_width=True):
                st.session_state.confirm_suppr = doc["id"]
                st.rerun()

        if st.session_state.get("confirm_suppr") == doc["id"]:
            st.error(f"Confirmer la suppression définitive du document {doc['numero']} ?")
            colc1, colc2 = st.columns(2)
            with colc1:
                if st.button("✅ Oui, supprimer"):
                    db.delete_document(doc["id"])
                    del st.session_state["confirm_suppr"]
                    st.success("Document supprimé.")
                    st.rerun()
            with colc2:
                if st.button("❌ Annuler"):
                    del st.session_state["confirm_suppr"]
                    st.rerun()


# ---------------------------------------------------------------------------
# PAGE : CATALOGUE DE TARIFS (montants pré-définis, saisis en TTC)
# ---------------------------------------------------------------------------
elif page == "💰 Tarifs":
    st.subheader("Ajouter un tarif")
    st.caption(
        "Les montants du catalogue sont saisis en TTC (ex : forfait global d'une prestation). "
        "Le prix HT est recalculé automatiquement à partir du taux de TVA pour les documents."
    )
    with st.form("form_nouveau_tarif", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            designation = st.text_input("Désignation *", placeholder="Ex : Location de piste — forfait soirée")
            description = st.text_area("Description (optionnel)", height=70)
        with col2:
            montant_ttc = st.number_input("Montant TTC (€)", min_value=0.0, step=10.0, format="%.2f")
            taux_tva = st.selectbox("Taux de TVA (%)", db.TAUX_TVA_DISPONIBLES)
            unite = st.text_input("Unité", value="forfait", placeholder="forfait, heure, jour, personne...")

        if st.form_submit_button("➕ Ajouter au catalogue"):
            if not designation.strip():
                st.error("La désignation est obligatoire.")
            else:
                db.create_tarif(designation.strip(), description, montant_ttc, taux_tva, unite.strip() or "forfait")
                st.success(f"Tarif **{designation}** ajouté au catalogue.")
                st.rerun()

    st.markdown("---")
    st.subheader("Catalogue de tarifs")
    tarifs = db.list_tarifs()

    if not tarifs:
        st.info("Aucun tarif enregistré pour le moment.")
    else:
        for tarif in tarifs:
            libelle = f"{tarif['designation']} — {tarif['montant_ttc']:.2f} € TTC"
            if not tarif["actif"]:
                libelle += " (inactif)"
            with st.expander(libelle):
                with st.form(f"form_edit_tarif_{tarif['id']}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        designation_e = st.text_input(
                            "Désignation *", value=tarif["designation"], key=f"tdesg_{tarif['id']}"
                        )
                        description_e = st.text_area(
                            "Description", value=tarif["description"] or "", key=f"tdesc_{tarif['id']}", height=70
                        )
                    with col2:
                        montant_ttc_e = st.number_input(
                            "Montant TTC (€)", min_value=0.0, step=10.0, format="%.2f",
                            value=float(tarif["montant_ttc"] or 0.0), key=f"tmont_{tarif['id']}",
                        )
                        index_tva = (
                            db.TAUX_TVA_DISPONIBLES.index(tarif["taux_tva"])
                            if tarif["taux_tva"] in db.TAUX_TVA_DISPONIBLES else 0
                        )
                        taux_tva_e = st.selectbox(
                            "Taux de TVA (%)", db.TAUX_TVA_DISPONIBLES, index=index_tva, key=f"ttva_{tarif['id']}"
                        )
                        unite_e = st.text_input("Unité", value=tarif["unite"] or "forfait", key=f"tunite_{tarif['id']}")
                        actif_e = st.checkbox(
                            "Tarif actif (visible dans le catalogue de sélection rapide)",
                            value=bool(tarif["actif"]), key=f"tactif_{tarif['id']}",
                        )

                    col_save, col_del = st.columns(2)
                    with col_save:
                        if st.form_submit_button("💾 Enregistrer", use_container_width=True):
                            db.update_tarif(
                                tarif["id"], designation_e.strip(), description_e, montant_ttc_e,
                                taux_tva_e, unite_e.strip() or "forfait", int(actif_e),
                            )
                            st.success("Tarif mis à jour.")
                            st.rerun()
                    with col_del:
                        if st.form_submit_button("🗑️ Supprimer", use_container_width=True):
                            db.delete_tarif(tarif["id"])
                            st.success("Tarif supprimé.")
                            st.rerun()


# ---------------------------------------------------------------------------
# PAGE 3 : CLIENTS
# ---------------------------------------------------------------------------
elif page == "👤 Clients":
    st.subheader("Ajouter un client")
    with st.form("form_nouveau_client", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nom = st.text_input("Nom / Raison sociale *")
            adresse = st.text_input("Adresse")
            code_postal_ville = st.text_input("Code postal / Ville")
        with col2:
            email = st.text_input("Email")
            telephone = st.text_input("Téléphone")
            siret = st.text_input("SIRET")

        if st.form_submit_button("➕ Ajouter le client"):
            if not nom.strip():
                st.error("Le nom du client est obligatoire.")
            else:
                db.create_client(nom.strip(), adresse, code_postal_ville, email, telephone, siret)
                st.success(f"Client **{nom}** ajouté.")
                st.rerun()

    st.markdown("---")
    st.subheader("Clients enregistrés")
    clients = db.list_clients()

    if not clients:
        st.info("Aucun client enregistré pour le moment.")
    else:
        for client in clients:
            with st.expander(f"{client['nom']}"):
                edit_key = f"edit_client_{client['id']}"
                with st.form(f"form_edit_client_{client['id']}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        nom_e = st.text_input("Nom / Raison sociale *", value=client["nom"], key=f"nom_{client['id']}")
                        adresse_e = st.text_input("Adresse", value=client["adresse"] or "", key=f"adresse_{client['id']}")
                        cpv_e = st.text_input("Code postal / Ville", value=client["code_postal_ville"] or "", key=f"cpv_{client['id']}")
                    with col2:
                        email_e = st.text_input("Email", value=client["email"] or "", key=f"email_{client['id']}")
                        tel_e = st.text_input("Téléphone", value=client["telephone"] or "", key=f"tel_{client['id']}")
                        siret_e = st.text_input("SIRET", value=client["siret"] or "", key=f"siret_{client['id']}")

                    col_save, col_del = st.columns(2)
                    with col_save:
                        if st.form_submit_button("💾 Enregistrer", use_container_width=True):
                            db.update_client(client["id"], nom_e.strip(), adresse_e, cpv_e, email_e, tel_e, siret_e)
                            st.success("Client mis à jour.")
                            st.rerun()
                    with col_del:
                        if st.form_submit_button("🗑️ Supprimer", use_container_width=True):
                            try:
                                db.delete_client(client["id"])
                                st.success("Client supprimé.")
                                st.rerun()
                            except ValueError as erreur:
                                st.error(str(erreur))


# ---------------------------------------------------------------------------
# PAGE 4 : PARAMÈTRES (ENTREPRISE ÉMETTRICE)
# ---------------------------------------------------------------------------
elif page == "🏢 Paramètres":
    st.subheader("Logo")
    st.caption("Affiché en haut à gauche de tous les devis et factures générés en PDF.")

    col_logo1, col_logo2 = st.columns([1, 3])
    with col_logo1:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=100)
        else:
            st.caption("Aucun logo pour le moment.")
    with col_logo2:
        fichier_logo = st.file_uploader("Changer le logo (PNG ou JPG)", type=["png", "jpg", "jpeg"])
        if fichier_logo is not None:
            from io import BytesIO
            from PIL import Image
            # Reconverti systématiquement en PNG, quel que soit le format d'origine,
            # pour garantir un fichier logo.png toujours valide.
            image = Image.open(BytesIO(fichier_logo.getvalue())).convert("RGBA")
            image.save(LOGO_PATH, format="PNG")
            st.success("Logo mis à jour.")
            st.rerun()
        if LOGO_PATH.exists():
            if st.button("🗑️ Supprimer le logo"):
                LOGO_PATH.unlink()
                st.success("Logo supprimé.")
                st.rerun()

    st.markdown("---")
    st.subheader("Informations de votre entreprise")
    st.caption("Ces informations apparaissent sur tous les devis et factures générés en PDF.")

    entreprise = db.get_entreprise()
    with st.form("form_entreprise"):
        col1, col2 = st.columns(2)
        with col1:
            nom = st.text_input("Nom de l'entreprise", value=entreprise.get("nom") or "")
            adresse = st.text_input("Adresse", value=entreprise.get("adresse") or "")
            code_postal_ville = st.text_input("Code postal / Ville", value=entreprise.get("code_postal_ville") or "")
            siret = st.text_input("SIRET", value=entreprise.get("siret") or "")
            tva_intracom = st.text_input("N° TVA intracommunautaire", value=entreprise.get("tva_intracom") or "")
        with col2:
            email = st.text_input("Email", value=entreprise.get("email") or "")
            telephone = st.text_input("Téléphone", value=entreprise.get("telephone") or "")
            iban = st.text_input("IBAN", value=entreprise.get("iban") or "")
            bic = st.text_input("BIC", value=entreprise.get("bic") or "")

        mentions_legales = st.text_area(
            "Mentions légales (pied de page des PDF)",
            value=entreprise.get("mentions_legales") or "", height=100,
        )

        if st.form_submit_button("💾 Enregistrer les paramètres", use_container_width=True):
            db.update_entreprise(
                nom=nom, adresse=adresse, code_postal_ville=code_postal_ville, siret=siret,
                tva_intracom=tva_intracom, email=email, telephone=telephone, iban=iban,
                bic=bic, mentions_legales=mentions_legales,
            )
            st.success("Paramètres enregistrés.")


# ---------------------------------------------------------------------------
# PAGE 5 : TABLEAU DE BORD
# ---------------------------------------------------------------------------
elif page == "📊 Tableau de bord":
    tous_les_documents = db.list_documents()

    if not tous_les_documents:
        st.info("Aucune donnée à afficher pour le moment.")
    else:
        lignes_dashboard = []
        for doc in tous_les_documents:
            lignes_doc = db.get_lignes(doc["id"])
            _, _, total_ttc = db.calculer_totaux(
                [{"quantite": l["quantite"], "prix_unitaire": l["prix_unitaire_ht"], "taux_tva": l["taux_tva"]} for l in lignes_doc]
            )
            lignes_dashboard.append({**doc, "total_ttc": total_ttc})

        df = pd.DataFrame(lignes_dashboard)

        ca_paye = df.loc[(df["type_doc"] == "Facture") & (df["statut"] == "Payée"), "total_ttc"].sum()
        factures_en_attente = df.loc[
            (df["type_doc"] == "Facture") & (df["statut"].isin(["Envoyée", "En retard", "Payée partiellement"])),
            "total_ttc",
        ].sum()
        devis_en_cours = df.loc[
            (df["type_doc"] == "Devis") & (df["statut"].isin(["Brouillon", "Envoyé"])), "total_ttc"
        ].sum()

        devis_clos = df[(df["type_doc"] == "Devis") & (df["statut"].isin(["Accepté", "Refusé", "Expiré"]))]
        taux_conversion = (
            (devis_clos["statut"] == "Accepté").sum() / len(devis_clos) * 100 if len(devis_clos) else 0
        )

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("CA facturé encaissé", eur(ca_paye))
        col2.metric("Factures en attente de paiement", eur(factures_en_attente))
        col3.metric("Devis en cours", eur(devis_en_cours))
        col4.metric("Taux de conversion devis", f"{taux_conversion:.0f} %")

        st.markdown("---")
        st.subheader("Chiffre d'affaires facturé par mois")
        df_factures = df[df["type_doc"] == "Facture"].copy()
        if not df_factures.empty:
            df_factures["mois"] = pd.to_datetime(df_factures["date_emission"]).dt.to_period("M").astype(str)
            par_mois = df_factures.groupby("mois")["total_ttc"].sum()
            st.bar_chart(par_mois)
        else:
            st.caption("Aucune facture pour le moment.")
