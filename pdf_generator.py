"""
Génération de PDF pour les devis et factures, avec fpdf2.
"""

from datetime import date as _date
from pathlib import Path

from fpdf import FPDF

from db import calculer_totaux, net_a_payer

BLEU = (30, 60, 110)
GRIS = (90, 90, 90)
GRIS_CLAIR = (240, 240, 240)

LOGO_PATH = Path(__file__).parent / "logo.png"


def _fr(date_iso):
    """Convertit une date stockée au format ISO (AAAA-MM-JJ) en JJ/MM/AAAA pour l'affichage."""
    if not date_iso:
        return ""
    try:
        return _date.fromisoformat(str(date_iso)).strftime("%d/%m/%Y")
    except ValueError:
        return str(date_iso)


def _dimensions_logo(hauteur_mm):
    """Retourne (largeur, hauteur) en mm pour le logo, en conservant ses proportions."""
    try:
        from PIL import Image
        with Image.open(LOGO_PATH) as img:
            ratio = img.width / img.height
        return hauteur_mm * ratio, hauteur_mm
    except Exception:
        return hauteur_mm, hauteur_mm


class DocumentPDF(FPDF):
    def __init__(self, entreprise):
        super().__init__(format="A4")
        self.entreprise = entreprise
        self.set_auto_page_break(auto=True, margin=25)
        # Nécessaire pour que le symbole € (hors latin-1) s'affiche avec les polices core.
        self.core_fonts_encoding = "cp1252"

    def footer(self):
        self.set_y(-18)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*GRIS)
        mentions = self.entreprise.get("mentions_legales") or ""
        self.multi_cell(0, 3.5, mentions, align="C")
        self.set_y(-8)
        self.set_font("Helvetica", "", 7)
        self.cell(0, 4, f"Page {self.page_no()}", align="C")


def _ligne_info(pdf, label, valeur):
    if not valeur:
        return
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*GRIS)
    pdf.cell(0, 4, f"{label}", ln=1)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 4.5, str(valeur), ln=1)


def generer_pdf(document, client, lignes, entreprise):
    """Construit le PDF d'un devis ou d'une facture et retourne les octets."""
    pdf = DocumentPDF(entreprise)
    pdf.add_page()
    pdf.set_margins(15, 15, 15)

    # --- En-tête : logo + entreprise (gauche) / titre document (droite) ---
    x_texte = 15
    if LOGO_PATH.exists():
        hauteur_logo = 18
        largeur_logo, hauteur_logo = _dimensions_logo(hauteur_logo)
        pdf.image(str(LOGO_PATH), x=15, y=10, h=hauteur_logo)
        x_texte = 15 + largeur_logo + 4

    largeur_bloc_entreprise = 100 - (x_texte - 15)

    pdf.set_xy(x_texte, 12)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*BLEU)
    pdf.cell(largeur_bloc_entreprise, 8, entreprise.get("nom") or "", ln=0)

    titre = "DEVIS" if document["type_doc"] == "Devis" else "FACTURE"
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 8, titre, ln=1, align="R")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(60, 60, 60)
    coord_entreprise = "\n".join(
        filter(None, [entreprise.get("adresse"), entreprise.get("code_postal_ville")])
    )
    y_apres_titre = pdf.get_y()
    pdf.set_xy(x_texte, y_apres_titre)
    pdf.multi_cell(largeur_bloc_entreprise, 4.5, coord_entreprise)

    pdf.set_xy(115, y_apres_titre)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 5, f"N° {document['numero']}", ln=1, align="R")
    pdf.set_x(115)
    pdf.cell(0, 5, f"Date d'émission : {_fr(document['date_emission'])}", ln=1, align="R")
    if document.get("date_echeance"):
        pdf.set_x(115)
        pdf.cell(0, 5, f"Échéance : {_fr(document['date_echeance'])}", ln=1, align="R")

    details_entreprise = []
    if entreprise.get("siret"):
        details_entreprise.append(f"SIRET : {entreprise['siret']}")
    if entreprise.get("tva_intracom"):
        details_entreprise.append(f"TVA intracom. : {entreprise['tva_intracom']}")
    if entreprise.get("email"):
        details_entreprise.append(entreprise["email"])
    if entreprise.get("telephone"):
        details_entreprise.append(entreprise["telephone"])
    if details_entreprise:
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(90, 90, 90)
        pdf.set_x(x_texte)
        pdf.multi_cell(largeur_bloc_entreprise, 4, "\n".join(details_entreprise))

    pdf.ln(4)

    # --- Bloc client ---
    pdf.set_fill_color(*GRIS_CLAIR)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*BLEU)
    pdf.cell(0, 6, "Adressé à", ln=1, fill=True)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 5.5, client.get("nom", ""), ln=1)
    pdf.set_font("Helvetica", "", 9)
    for champ in (client.get("adresse"), client.get("code_postal_ville")):
        if champ:
            pdf.cell(0, 4.5, champ, ln=1)
    if client.get("siret"):
        pdf.cell(0, 4.5, f"SIRET : {client['siret']}", ln=1)

    pdf.ln(4)

    # --- Tableau des lignes ---
    largeurs = [85, 20, 28, 20, 27]
    entetes = ["Description", "Qté", "Prix unit. HT", "TVA", "Total HT"]

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(*BLEU)
    pdf.set_text_color(255, 255, 255)
    for largeur, entete in zip(largeurs, entetes):
        pdf.cell(largeur, 7, entete, border=0, fill=True, align="C" if entete != "Description" else "L")
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(20, 20, 20)
    alterner = False
    for ligne in lignes:
        total_ligne = ligne["quantite"] * ligne["prix_unitaire_ht"]
        pdf.set_fill_color(248, 248, 248) if alterner else pdf.set_fill_color(255, 255, 255)
        alterner = not alterner

        y_avant = pdf.get_y()
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(20, 20, 20)
        pdf.multi_cell(largeurs[0], 5.5, ligne["description"], border=0, fill=True)
        if ligne.get("detail"):
            pdf.set_x(15)
            pdf.set_font("Helvetica", "I", 7.5)
            pdf.set_text_color(120, 120, 120)
            pdf.multi_cell(largeurs[0], 4, ligne["detail"], border=0, fill=True)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(20, 20, 20)
        y_apres = pdf.get_y()
        hauteur = max(y_apres - y_avant, 5.5)

        pdf.set_xy(15 + largeurs[0], y_avant)
        pdf.cell(largeurs[1], hauteur, f"{ligne['quantite']:g}", align="C", fill=True)
        pdf.cell(largeurs[2], hauteur, f"{ligne['prix_unitaire_ht']:.2f} €", align="C", fill=True)
        pdf.cell(largeurs[3], hauteur, f"{ligne['taux_tva']:g} %", align="C", fill=True)
        pdf.cell(largeurs[4], hauteur, f"{total_ligne:.2f} €", align="C", fill=True)
        pdf.set_xy(15, y_apres)

    pdf.ln(3)

    # --- Totaux ---
    total_ht, detail_tva, total_ttc = calculer_totaux(
        [{"quantite": l["quantite"], "prix_unitaire": l["prix_unitaire_ht"], "taux_tva": l["taux_tva"]} for l in lignes]
    )

    largeur_label, largeur_valeur = 40, 30
    x_totaux = 210 - 15 - largeur_label - largeur_valeur

    def ligne_total(label, valeur, gras=False):
        pdf.set_x(x_totaux)
        pdf.set_font("Helvetica", "B" if gras else "", 9)
        pdf.cell(largeur_label, 6, label)
        pdf.cell(largeur_valeur, 6, valeur, align="R", ln=1)

    ligne_total("Total HT", f"{total_ht:.2f} €")
    for taux, montant in sorted(detail_tva.items()):
        if montant:
            ligne_total(f"TVA ({taux:g} %)", f"{montant:.2f} €")
    pdf.set_draw_color(*BLEU)
    pdf.set_x(x_totaux)
    pdf.cell(largeur_label + largeur_valeur, 0, "", border="T", ln=1)
    ligne_total("Total TTC", f"{total_ttc:.2f} €", gras=True)

    montant_acompte = document.get("montant_acompte") or 0.0
    if document["type_doc"] == "Facture" and montant_acompte > 0:
        ligne_total("Acompte(s) versé(s)", f"-{montant_acompte:.2f} €")
        pdf.set_x(x_totaux)
        pdf.cell(largeur_label + largeur_valeur, 0, "", border="T", ln=1)
        ligne_total("Net à payer", f"{net_a_payer(total_ttc, montant_acompte):.2f} €", gras=True)

    pdf.ln(6)

    # --- Mode de règlement ---
    if document["type_doc"] == "Facture" and document.get("mode_reglement"):
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*BLEU)
        pdf.cell(0, 5, "Mode de règlement", ln=1)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(20, 20, 20)
        pdf.cell(0, 5, document["mode_reglement"], ln=1)
        pdf.ln(2)

    # --- Conditions / notes ---
    if document.get("conditions_paiement"):
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*BLEU)
        pdf.cell(0, 5, "Conditions de paiement", ln=1)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(20, 20, 20)
        pdf.multi_cell(0, 5, document["conditions_paiement"])
        pdf.ln(2)

    if document.get("notes"):
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*BLEU)
        pdf.cell(0, 5, "Notes", ln=1)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(20, 20, 20)
        pdf.multi_cell(0, 5, document["notes"])

    return bytes(pdf.output())
