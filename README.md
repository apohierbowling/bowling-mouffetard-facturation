# Devis & Factures

Application Streamlit pour créer, éditer et éditer en PDF des devis et factures. Fonctionne seule avec une base SQLite locale (par défaut), ou avec une base PostgreSQL partagée si vous voulez que toute l'équipe travaille sur les mêmes données.

Reprend l'idée du fichier `Factures.py` d'origine, en l'étendant : lignes multiples par document, gestion des clients, génération de PDF, numérotation automatique, transformation d'un devis en facture, et tableau de bord.

## Installation

```bash
pip install -r requirements.txt
```

## Lancement

```bash
streamlit run app.py
```

L'application s'ouvre dans le navigateur. Une base `facturation.db` est créée automatiquement au premier lancement, dans le même dossier.

## Fonctionnement

- **Créer / Éditer** : formulaire avec lignes multiples (description, quantité, **prix unitaire TTC**, TVA), calcul automatique des totaux, numérotation auto (`DEV-2026-001`, `FAC-2026-001`). Le prix TTC saisi est automatiquement reconverti en HT en interne (nécessaire pour le détail légal HT/TVA/TTC des documents). Un menu permet d'ajouter une ligne directement depuis le catalogue de tarifs.
- **Documents** : liste filtrable (type, statut, client), détail, édition, téléchargement PDF, transformation d'un devis en facture, duplication, suppression. Pour les factures : mode de règlement et déduction d'un ou plusieurs acomptes déjà versés (le « Net à payer » est calculé et affiché à l'écran comme sur le PDF).
- **Tarifs** : catalogue de prix pré-définis, saisis en TTC (y compris des montants globaux/forfaits pour une prestation). Modifiable à tout moment ; le prix HT est recalculé automatiquement selon le taux de TVA lors de l'ajout à un document. Un tarif peut être désactivé (masqué du sélecteur rapide) sans être supprimé.
- **Clients** : ajout, modification, suppression (bloquée si des documents y sont liés).
- **Paramètres** : logo (affiché en haut à gauche des PDF, modifiable à tout moment) et coordonnées de votre entreprise (SIRET, TVA intracom, IBAN, mentions légales) affichées sur les PDF.
- **Tableau de bord** : CA encaissé, factures en attente, devis en cours, taux de conversion, CA par mois.

## Fichiers

- `app.py` — interface Streamlit
- `db.py` — accès aux données (SQLite par défaut, ou PostgreSQL si `DATABASE_URL` est configuré)
- `pdf_generator.py` — génération des PDF (fpdf2)
- `requirements.txt` — dépendances
- `secrets.toml.exemple` — modèle de configuration pour la base partagée (voir ci-dessous)

## Limites connues

- Sans base partagée : application locale mono-poste (chaque ordinateur a sa propre base `facturation.db`, pas de synchronisation automatique entre eux).
- Pas d'authentification : toute personne ayant accès à l'appli (locale ou déployée) peut tout voir et modifier.
- Deux types de documents gérés (Devis / Facture) ; les factures d'acompte peuvent être précisées via les notes ou conditions de paiement.

## Utilisation en équipe (base de données partagée)

Par défaut, chaque installation de l'appli a sa propre base `facturation.db` sur son disque : deux personnes qui l'utilisent chacune sur leur PC ne voient pas les mêmes devis/factures. Pour que toute l'équipe travaille sur les **mêmes données en temps réel**, il faut une base de données centrale (PostgreSQL) au lieu du fichier SQLite local. Le code le permet déjà : il suffit de renseigner une variable `DATABASE_URL`, rien d'autre à modifier.

Deux façons de mettre ça en place, de la plus simple à la plus pratique pour une équipe non technique :

### Option A — Base partagée, appli toujours lancée en local sur chaque poste

Chaque personne continue de lancer l'appli sur son propre ordinateur (comme aujourd'hui), mais toutes pointent vers la même base PostgreSQL en ligne.

1. **Créer la base PostgreSQL gratuite** : allez sur [supabase.com](https://supabase.com) (ou [neon.tech](https://neon.tech)), créez un compte et un nouveau projet. Dans les paramètres du projet, section **Database**, copiez la **Connection string** au format URI (elle ressemble à `postgresql://postgres:VOTRE_MOT_DE_PASSE@db.xxxxx.supabase.co:5432/postgres`).
2. Sur **chaque ordinateur** de l'équipe qui doit utiliser l'appli :
   - Dans le dossier de l'appli, créez un sous-dossier nommé exactement `.streamlit`.
   - Copiez `secrets.toml.exemple` dedans, renommez-le `secrets.toml`.
   - Ouvrez-le et remplacez la ligne `DATABASE_URL` par la connection string de l'étape 1 (la même pour tout le monde).
3. Relancez l'appli sur chaque poste (`python -m streamlit run app.py`, ou le raccourci `.bat`). Tout le monde voit et modifie désormais les mêmes clients, devis et factures.

Avantage : rapide à mettre en place, rien à déployer. Inconvénient : chaque personne doit quand même avoir Python et l'appli installés sur sa machine.

### Option B — Appli hébergée en ligne, accessible depuis un simple lien (recommandé)

L'équipe n'installe plus rien : tout le monde ouvre une URL dans son navigateur, comme un site web.

1. Créez la base PostgreSQL gratuite comme à l'étape 1 de l'option A (Supabase ou Neon), et gardez la connection string de côté.
2. Mettez le code de l'appli (`app.py`, `db.py`, `pdf_generator.py`, `requirements.txt`) sur GitHub :
   - créez un compte gratuit sur [github.com](https://github.com) si besoin,
   - créez un nouveau dépôt (peut être privé), et déposez-y ces fichiers (via l'interface web "Add file → Upload files", pas besoin de ligne de commande).
3. Allez sur [streamlit.io/cloud](https://streamlit.io/cloud), connectez-vous avec votre compte GitHub, cliquez sur **New app**, choisissez votre dépôt et indiquez `app.py` comme fichier principal.
4. Avant de déployer (ou dans les paramètres de l'appli une fois créée), ouvrez l'onglet **Secrets** et collez :
   ```
   DATABASE_URL = "postgresql://postgres:VOTRE_MOT_DE_PASSE@db.xxxxx.supabase.co:5432/postgres"
   ```
5. Déployez. Streamlit vous donne une adresse du type `https://votre-appli.streamlit.app` : partagez-la à votre équipe, chacun l'ouvre dans son navigateur (téléphone, tablette, PC), sans rien installer.

Avantage : zéro installation pour l'équipe, accessible de partout, une seule version toujours à jour. C'est l'option la plus adaptée pour un usage régulier à plusieurs.

### Bon à savoir

- La bascule est automatique : sans `DATABASE_URL` configuré, l'appli continue à utiliser le fichier SQLite local exactement comme avant — vous pouvez tester tranquillement sans rien casser.
- Le premier lancement avec une base PostgreSQL vide recrée automatiquement toutes les tables (identique au comportement SQLite), mais **ne récupère pas vos anciennes données locales** : si vous avez déjà des devis/clients dans votre `facturation.db` actuel, dites-le-moi et je prépare un script pour les transférer vers la nouvelle base.
- Gardez `secrets.toml` et votre mot de passe de base de données confidentiels (ne les partagez pas publiquement, ni sur un dépôt GitHub public).
