# London Property Price Analysis

Outil de recherche pour analyser les prix immobiliers a Londres.

## App visuelle

L'app locale couvre Chelsea et South Kensington:

- carte interactive;
- filtres prix, quartier, type, tenure, chambres, score;
- liste de listings, fiche detaillee, comparables;
- import CSV/JSON de listings autorises;
- export CSV des resultats filtres.

Lancer le serveur statique:

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\paulw\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m london_property_analysis serve --port 4173
```

Puis ouvrir:

```text
http://localhost:4173
```

Format d'import minimal: voir `data/listing_schema.csv`. Les champs essentiels sont `address`, `price`, `lat`, `lng`; les autres champs enrichissent l'analyse.

## Structure du projet

```text
app/                         Interface HTML/CSS/JS
data/                        Schema d'import et donnees demo
docs/                        Notes data et compliance
src/london_property_analysis/ Code Python ingestion, analyse, serveur local
tests/                       Tests Python
```

## GitLab

Le repo contient deja:

- `.gitignore`;
- `.editorconfig`;
- `.gitlab-ci.yml`;
- `pyproject.toml`;
- tests Python de base.

Quand ton projet GitLab est cree:

```powershell
git remote add origin <URL_GITLAB>
git branch -M main
git push -u origin main
```

## Positionnement data

Pour un outil robuste, la premiere brique doit etre un pipeline de donnees propre:

- **Prix realises**: HM Land Registry Price Paid Data, source officielle et mensuelle.
- **Listings live**: Rightmove/Zoopla seulement via accord, licence, API autorisee, ou donnees exportees manuellement. Le scraping automatise de ces plateformes est generalement interdit par leurs conditions.
- **Enrichissements utiles**: EPC, ONS, Transport for London, postcodes, crime, schools, planning.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Si `python` n'est pas dans le PATH sur cette machine, le runtime Codex peut etre appele ainsi:

```powershell
& 'C:\Users\paulw\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pip install -e .
```

## Exemple

Telecharger et filtrer les ventes 2025 a Londres:

```powershell
python -m london_property_analysis ppd fetch-year 2025 --out data/raw/pp-2025.csv
python -m london_property_analysis ppd filter-london data/raw/pp-2025.csv --out data/processed/london-2025.csv
python -m london_property_analysis ppd summary data/processed/london-2025.csv
```

## Attribution

Contains HM Land Registry data (C) Crown copyright and database right 2021. This data is licensed under the Open Government Licence v3.0.
