"""
Couche d'accès aux données pour l'application de facturation.

Deux modes de fonctionnement :

- Local (par défaut) : base SQLite dans un fichier `facturation.db`, créé
  automatiquement au premier lancement. Aucune configuration nécessaire.
- Partagé (équipe) : si une variable d'environnement `DATABASE_URL` (ou un
  secret Streamlit du même nom) pointe vers une base PostgreSQL, elle est
  utilisée à la place. Toutes les fonctions ci-dessous fonctionnent à
  l'identique dans les deux cas.
"""

import os
import sqlite3
from pathlib import Path
from datetime import datetime, date

DB_PATH = Path(__file__).parent / "facturation.db"

TAUX_TVA_DISPONIBLES = [20.0, 10.0, 5.5, 2.1, 0.0]

STATUTS_DEVIS = ["Brouillon", "Envoyé", "Accepté", "Refusé", "Expiré"]
STATUTS_FACTURE = ["Brouillon", "Envoyée", "Payée partiellement", "Payée", "En retard", "Annulée"]

MODES_REGLEMENT = ["Virement bancaire", "Chèque", "Espèces", "Carte bancaire", "Prélèvement SEPA", "Autre"]


def _lire_database_url():
    """Cherche une URL PostgreSQL dans l'environnement, puis dans les secrets Streamlit."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        import streamlit as st
        return st.secrets.get("DATABASE_URL")
    except Exception:
        return None


DATABASE_URL = _lire_database_url()
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras


# ---------------------------------------------------------------------------
# CONNEXION & PETITE COUCHE DE COMPATIBILITÉ SQLite / PostgreSQL
# ---------------------------------------------------------------------------

def get_conn():
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def executer(conn, sql, params=()):
    """Exécute une requête et retourne le curseur.

    Le reste du fichier écrit ses requêtes avec des `?` comme en SQLite ;
    cette fonction les convertit en `%s` pour PostgreSQL, et fait en sorte
    que les lignes retournées se comportent comme des dictionnaires
    (`dict(row)`) dans les deux cas.
    """
    if USE_POSTGRES:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql.replace("?", "%s"), params)
    else:
        cur = conn.cursor()
        cur.execute(sql, params)
    return cur


def executer_insertion(conn, sql, params=()):
    """Exécute un INSERT et retourne l'id généré (SQLite : lastrowid, PostgreSQL : RETURNING id)."""
    if USE_POSTGRES:
        cur = executer(conn, sql + " RETURNING id", params)
        return cur.fetchone()["id"]
    cur = executer(conn, sql, params)
    return cur.lastrowid


def init_db():
    conn = get_conn()
    if USE_POSTGRES:
        _init_schema_postgres(conn)
    else:
        _init_schema_sqlite(conn)
    conn.commit()
    conn.close()


def _init_schema_sqlite(conn):
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS entreprise (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            nom TEXT,
            adresse TEXT,
            code_postal_ville TEXT,
            siret TEXT,
            tva_intracom TEXT,
            email TEXT,
            telephone TEXT,
            iban TEXT,
            bic TEXT,
            mentions_legales TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            adresse TEXT,
            code_postal_ville TEXT,
            email TEXT,
            telephone TEXT,
            siret TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_doc TEXT NOT NULL,
            numero TEXT UNIQUE NOT NULL,
            client_id INTEGER NOT NULL,
            date_emission TEXT,
            date_echeance TEXT,
            statut TEXT,
            notes TEXT,
            conditions_paiement TEXT,
            document_origine_id INTEGER,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        )
        """
    )

    # Migration légère : ajoute les colonnes mode de règlement / acompte si elles
    # n'existent pas encore (bases créées avant l'introduction de cette fonctionnalité).
    colonnes_documents = {row["name"] for row in cur.execute("PRAGMA table_info(documents)").fetchall()}
    if "mode_reglement" not in colonnes_documents:
        cur.execute("ALTER TABLE documents ADD COLUMN mode_reglement TEXT")
    if "montant_acompte" not in colonnes_documents:
        cur.execute("ALTER TABLE documents ADD COLUMN montant_acompte REAL DEFAULT 0")
    if "date_evenement" not in colonnes_documents:
        cur.execute("ALTER TABLE documents ADD COLUMN date_evenement TEXT")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS lignes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            ordre INTEGER,
            description TEXT,
            detail TEXT,
            quantite REAL,
            prix_unitaire_ht REAL,
            taux_tva REAL,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        )
        """
    )

    colonnes_lignes = {row["name"] for row in cur.execute("PRAGMA table_info(lignes)").fetchall()}
    if "detail" not in colonnes_lignes:
        cur.execute("ALTER TABLE lignes ADD COLUMN detail TEXT")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tarifs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            designation TEXT NOT NULL,
            description TEXT,
            montant_ttc REAL,
            taux_tva REAL,
            unite TEXT,
            actif INTEGER DEFAULT 1
        )
        """
    )

    cur.execute("SELECT COUNT(*) FROM entreprise")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO entreprise (id, nom, mentions_legales) VALUES (1, 'Mon Entreprise', ?)",
            (
                "En cas de retard de paiement, une pénalité de 3 fois le taux d'intérêt légal sera appliquée, "
                "ainsi qu'une indemnité forfaitaire de 40€ pour frais de recouvrement (art. L441-10 du Code de commerce).",
            ),
        )


def _init_schema_postgres(conn):
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS entreprise (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            nom TEXT,
            adresse TEXT,
            code_postal_ville TEXT,
            siret TEXT,
            tva_intracom TEXT,
            email TEXT,
            telephone TEXT,
            iban TEXT,
            bic TEXT,
            mentions_legales TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY,
            nom TEXT NOT NULL,
            adresse TEXT,
            code_postal_ville TEXT,
            email TEXT,
            telephone TEXT,
            siret TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            type_doc TEXT NOT NULL,
            numero TEXT UNIQUE NOT NULL,
            client_id INTEGER NOT NULL REFERENCES clients(id),
            date_emission TEXT,
            date_echeance TEXT,
            statut TEXT,
            notes TEXT,
            conditions_paiement TEXT,
            document_origine_id INTEGER,
            mode_reglement TEXT,
            montant_acompte REAL DEFAULT 0,
            date_evenement TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    # Idempotent : ne fait rien si les colonnes existent déjà (bases créées avec un schéma plus ancien).
    cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS mode_reglement TEXT")
    cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS montant_acompte REAL DEFAULT 0")
    cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS date_evenement TEXT")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS lignes (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            ordre INTEGER,
            description TEXT,
            detail TEXT,
            quantite REAL,
            prix_unitaire_ht REAL,
            taux_tva REAL
        )
        """
    )
    cur.execute("ALTER TABLE lignes ADD COLUMN IF NOT EXISTS detail TEXT")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tarifs (
            id SERIAL PRIMARY KEY,
            designation TEXT NOT NULL,
            description TEXT,
            montant_ttc REAL,
            taux_tva REAL,
            unite TEXT,
            actif INTEGER DEFAULT 1
        )
        """
    )

    cur.execute("SELECT COUNT(*) FROM entreprise")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO entreprise (id, nom, mentions_legales) VALUES (1, %s, %s)",
            (
                "Mon Entreprise",
                "En cas de retard de paiement, une pénalité de 3 fois le taux d'intérêt légal sera appliquée, "
                "ainsi qu'une indemnité forfaitaire de 40€ pour frais de recouvrement (art. L441-10 du Code de commerce).",
            ),
        )


# ---------------------------------------------------------------------------
# ENTREPRISE (paramètres émetteur)
# ---------------------------------------------------------------------------

def get_entreprise():
    conn = get_conn()
    row = executer(conn, "SELECT * FROM entreprise WHERE id = 1").fetchone()
    conn.close()
    return dict(row) if row else {}


def update_entreprise(**champs):
    conn = get_conn()
    cols = ", ".join(f"{k} = ?" for k in champs)
    executer(conn, f"UPDATE entreprise SET {cols} WHERE id = 1", tuple(champs.values()))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# CLIENTS
# ---------------------------------------------------------------------------

def list_clients():
    conn = get_conn()
    rows = executer(conn, "SELECT * FROM clients ORDER BY nom").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_client(client_id):
    conn = get_conn()
    row = executer(conn, "SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_client(nom, adresse="", code_postal_ville="", email="", telephone="", siret=""):
    conn = get_conn()
    new_id = executer_insertion(
        conn,
        "INSERT INTO clients (nom, adresse, code_postal_ville, email, telephone, siret) VALUES (?, ?, ?, ?, ?, ?)",
        (nom, adresse, code_postal_ville, email, telephone, siret),
    )
    conn.commit()
    conn.close()
    return new_id


def update_client(client_id, nom, adresse="", code_postal_ville="", email="", telephone="", siret=""):
    conn = get_conn()
    executer(
        conn,
        """UPDATE clients SET nom=?, adresse=?, code_postal_ville=?, email=?, telephone=?, siret=?
           WHERE id=?""",
        (nom, adresse, code_postal_ville, email, telephone, siret, client_id),
    )
    conn.commit()
    conn.close()


def delete_client(client_id):
    conn = get_conn()
    row = executer(conn, "SELECT COUNT(*) AS n FROM documents WHERE client_id = ?", (client_id,)).fetchone()
    en_cours = row["n"]
    if en_cours > 0:
        conn.close()
        raise ValueError("Impossible de supprimer ce client : des documents lui sont associés.")
    executer(conn, "DELETE FROM clients WHERE id = ?", (client_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# TARIFS (catalogue de prix pré-définis, saisis en TTC)
# ---------------------------------------------------------------------------

def list_tarifs(actifs_seulement=False):
    conn = get_conn()
    query = "SELECT * FROM tarifs"
    if actifs_seulement:
        query += " WHERE actif = 1"
    query += " ORDER BY designation"
    rows = executer(conn, query).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tarif(tarif_id):
    conn = get_conn()
    row = executer(conn, "SELECT * FROM tarifs WHERE id = ?", (tarif_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_tarif(designation, description, montant_ttc, taux_tva, unite="forfait"):
    conn = get_conn()
    new_id = executer_insertion(
        conn,
        """INSERT INTO tarifs (designation, description, montant_ttc, taux_tva, unite, actif)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (designation, description, montant_ttc, taux_tva, unite),
    )
    conn.commit()
    conn.close()
    return new_id


def update_tarif(tarif_id, designation, description, montant_ttc, taux_tva, unite, actif=1):
    conn = get_conn()
    executer(
        conn,
        """UPDATE tarifs SET designation=?, description=?, montant_ttc=?, taux_tva=?, unite=?, actif=?
           WHERE id=?""",
        (designation, description, montant_ttc, taux_tva, unite, int(actif), tarif_id),
    )
    conn.commit()
    conn.close()


def delete_tarif(tarif_id):
    conn = get_conn()
    executer(conn, "DELETE FROM tarifs WHERE id = ?", (tarif_id,))
    conn.commit()
    conn.close()


def tarif_prix_unitaire_ht(tarif):
    """Convertit le montant TTC d'un tarif du catalogue en prix unitaire HT."""
    return ht_depuis_ttc(tarif["montant_ttc"], tarif["taux_tva"])


def ht_depuis_ttc(montant_ttc, taux_tva):
    """Convertit un montant TTC en montant HT pour un taux de TVA donné."""
    return montant_ttc / (1 + (taux_tva or 0) / 100)


def ttc_depuis_ht(montant_ht, taux_tva):
    """Convertit un montant HT en montant TTC pour un taux de TVA donné."""
    return montant_ht * (1 + (taux_tva or 0) / 100)


# ---------------------------------------------------------------------------
# NUMÉROTATION
# ---------------------------------------------------------------------------

def next_numero(type_doc, annee=None):
    annee = annee or date.today().year
    prefixe = "DEV" if type_doc == "Devis" else "FAC"
    motif = f"{prefixe}-{annee}-"

    conn = get_conn()
    rows = executer(conn, "SELECT numero FROM documents WHERE numero LIKE ?", (motif + "%",)).fetchall()
    conn.close()

    max_seq = 0
    for row in rows:
        suffixe = row["numero"].replace(motif, "")
        if suffixe.isdigit():
            max_seq = max(max_seq, int(suffixe))

    return f"{motif}{max_seq + 1:03d}"


# ---------------------------------------------------------------------------
# DOCUMENTS + LIGNES
# ---------------------------------------------------------------------------

def create_document(type_doc, numero, client_id, date_emission, date_echeance, statut,
                     notes, conditions_paiement, lignes, document_origine_id=None,
                     mode_reglement=None, montant_acompte=0.0, date_evenement=None):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    document_id = executer_insertion(
        conn,
        """
        INSERT INTO documents
            (type_doc, numero, client_id, date_emission, date_echeance, statut,
             notes, conditions_paiement, document_origine_id, mode_reglement,
             montant_acompte, date_evenement, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (type_doc, numero, client_id, str(date_emission), str(date_echeance) if date_echeance else None,
         statut, notes, conditions_paiement, document_origine_id, mode_reglement,
         montant_acompte or 0.0, date_evenement, now, now),
    )
    _inserer_lignes(conn, document_id, lignes)
    conn.commit()
    conn.close()
    return document_id


def update_document(document_id, type_doc, numero, client_id, date_emission, date_echeance,
                     statut, notes, conditions_paiement, lignes, mode_reglement=None,
                     montant_acompte=0.0, date_evenement=None):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    executer(
        conn,
        """
        UPDATE documents SET
            type_doc=?, numero=?, client_id=?, date_emission=?, date_echeance=?,
            statut=?, notes=?, conditions_paiement=?, mode_reglement=?, montant_acompte=?,
            date_evenement=?, updated_at=?
        WHERE id=?
        """,
        (type_doc, numero, client_id, str(date_emission), str(date_echeance) if date_echeance else None,
         statut, notes, conditions_paiement, mode_reglement, montant_acompte or 0.0,
         date_evenement, now, document_id),
    )
    executer(conn, "DELETE FROM lignes WHERE document_id = ?", (document_id,))
    _inserer_lignes(conn, document_id, lignes)
    conn.commit()
    conn.close()


def _inserer_lignes(conn, document_id, lignes):
    for i, ligne in enumerate(lignes):
        executer(
            conn,
            """INSERT INTO lignes (document_id, ordre, description, detail, quantite, prix_unitaire_ht, taux_tva)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (document_id, i, ligne["description"], ligne.get("detail") or "", ligne["quantite"],
             ligne["prix_unitaire"], ligne["taux_tva"]),
        )


def delete_document(document_id):
    conn = get_conn()
    executer(conn, "DELETE FROM lignes WHERE document_id = ?", (document_id,))
    executer(conn, "DELETE FROM documents WHERE id = ?", (document_id,))
    conn.commit()
    conn.close()


def get_document(document_id):
    conn = get_conn()
    row = executer(conn, "SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_lignes(document_id):
    conn = get_conn()
    rows = executer(conn, "SELECT * FROM lignes WHERE document_id = ? ORDER BY ordre", (document_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_documents(type_doc=None, statut=None, client_id=None):
    query = """
        SELECT d.*, c.nom AS client_nom
        FROM documents d
        JOIN clients c ON c.id = d.client_id
        WHERE 1=1
    """
    params = []
    if type_doc and type_doc != "Tous":
        query += " AND d.type_doc = ?"
        params.append(type_doc)
    if statut and statut != "Tous":
        query += " AND d.statut = ?"
        params.append(statut)
    if client_id:
        query += " AND d.client_id = ?"
        params.append(client_id)
    query += " ORDER BY d.date_emission DESC, d.id DESC"

    conn = get_conn()
    rows = executer(conn, query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# CALCULS
# ---------------------------------------------------------------------------

def calculer_totaux(lignes):
    """Retourne (total_ht, detail_tva {taux: montant_tva}, total_ttc)."""
    total_ht = 0.0
    detail_tva = {}
    for ligne in lignes:
        montant_ligne_ht = ligne["quantite"] * ligne["prix_unitaire"]
        total_ht += montant_ligne_ht
        taux = ligne["taux_tva"]
        detail_tva[taux] = detail_tva.get(taux, 0.0) + montant_ligne_ht * (taux / 100)

    total_tva = sum(detail_tva.values())
    total_ttc = total_ht + total_tva
    return round(total_ht, 2), {k: round(v, 2) for k, v in detail_tva.items()}, round(total_ttc, 2)


def net_a_payer(total_ttc, montant_acompte):
    """Montant restant dû après déduction du ou des acomptes déjà versés."""
    return round(total_ttc - (montant_acompte or 0.0), 2)


def transformer_devis_en_facture(devis_id):
    """Duplique un devis accepté en nouvelle facture (brouillon) et retourne son id."""
    devis = get_document(devis_id)
    if not devis:
        raise ValueError("Devis introuvable.")
    lignes = get_lignes(devis_id)
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
    numero = next_numero("Facture")
    return create_document(
        type_doc="Facture",
        numero=numero,
        client_id=devis["client_id"],
        date_emission=date.today(),
        date_echeance=None,
        statut="Brouillon",
        notes=devis["notes"],
        conditions_paiement=devis["conditions_paiement"],
        lignes=lignes_pour_creation,
        document_origine_id=devis_id,
        date_evenement=devis.get("date_evenement"),
    )
