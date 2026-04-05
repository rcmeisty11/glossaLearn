# Glossalearn

A Greek vocabulary explorer for studying Ancient Greek texts. Browse vocabulary by author and work, explore morphological forms, and visualize derivational word families through an interactive radial tree.

**Author:** Randall Craig Meister (randallcraigmeister@gmail.com)

This project was developed with the assistance of [Claude Code](https://claude.ai/claude-code) by Anthropic.

## Quick Start

```bash
# Install dependencies
pip3 install flask flask-cors
cd vocab-viz && npm install

# Start the API server
python3 serve_api.py

# Start the frontend (in a separate terminal)
cd vocab-viz && npm run dev
```

The app will be available at `http://localhost:5173` with the API on `http://localhost:5000`.

### Superuser Mode

To enable family editing features (add/remove words, merge/rename families, link families):

```bash
GLOSSALEARN_SUPERUSER=1 python3 serve_api.py
```

## Architecture

- **Backend**: Flask REST API (`serve_api.py`) serving data from SQLite
- **Frontend**: React single-page app with D3.js radial visualization (`vocab-viz/src/App.jsx`)
- **Database**: `greek_vocab.db` (~2.1 GB) containing the full Greek corpus with morphology, lemmatization, and occurrence data
- **Production**: Deployed on AWS Lightsail with API at `https://apiaws.glossalearn.com`

## Database Schema

### Core Tables

#### `works`
Texts in the corpus (Perseus, TLG, First1KGreek).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Auto-increment ID |
| filename | TEXT | NOT NULL UNIQUE | Source filename |
| cts_urn | TEXT | | CTS URN identifier |
| author_code | TEXT | | TLG/Perseus author code |
| work_code | TEXT | | TLG/Perseus work code |
| author | TEXT | | Author name |
| title | TEXT | | Work title |
| corpus | TEXT | DEFAULT 'perseus' | Source corpus (e.g. "tlg", "perseus") |

#### `lemmas`
Greek vocabulary base forms (headwords).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Auto-increment ID |
| lemma | TEXT | NOT NULL, UNIQUE(lemma, pos) | Greek headword |
| pos | TEXT | | Part of speech (noun, verb, adjective, adverb, etc.) |
| short_def | TEXT | | Short English definition |
| lsj_def | TEXT | | LSJ lexicon definition |
| middle_liddell | TEXT | | Middle Liddell definition |
| total_occurrences | INTEGER | DEFAULT 0 | Total token count across entire corpus |
| frequency_rank | INTEGER | | Rank by frequency (1 = most common) |

#### `forms`
Morphological variants (inflected forms) of each lemma.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Auto-increment ID |
| lemma_id | INTEGER | NOT NULL, FK -> lemmas(id) | Parent lemma |
| form | TEXT | NOT NULL | The inflected Greek form |
| morph_tag | TEXT | | Full morphology tag string |
| pos | TEXT | | Part of speech |
| person | TEXT | | 1st, 2nd, 3rd |
| number | TEXT | | singular, dual, plural |
| tense | TEXT | | present, aorist, future, etc. |
| mood | TEXT | | indicative, subjunctive, optative, etc. |
| voice | TEXT | | active, middle, passive |
| gender | TEXT | | masculine, feminine, neuter |
| gram_case | TEXT | | nominative, genitive, dative, accusative, vocative |
| degree | TEXT | | comparative, superlative |

Unique constraint on `(lemma_id, form, morph_tag)`.

#### `occurrences`
Individual token instances in texts. This is the largest table (~18M rows).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Auto-increment ID |
| lemma_id | INTEGER | NOT NULL, FK -> lemmas(id) | Parent lemma |
| form_id | INTEGER | FK -> forms(id) | The specific inflected form |
| work_id | INTEGER | NOT NULL, FK -> works(id) | The work this token appears in |
| passage | TEXT | | CTS passage reference |
| sentence_n | INTEGER | | Sentence number within work |
| token_n | INTEGER | | Token position within sentence |

#### `sentences`
Reconstructed sentence text for each work, linked to lemmas for contextual lookup.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Auto-increment ID |
| work_id | INTEGER | NOT NULL, FK -> works(id) | The work this sentence appears in |
| passage | TEXT | | CTS passage reference |
| sentence_pos | INTEGER | | Position of sentence within the passage |
| sentence_text | TEXT | NOT NULL | Full reconstructed Greek sentence text |

#### `sentence_lemmas`
Join table linking sentences to the lemmas they contain, enabling "find sentences containing this word" queries.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| sentence_id | INTEGER | NOT NULL, FK -> sentences(id) | The sentence |
| lemma_id | INTEGER | NOT NULL, FK -> lemmas(id) | A lemma appearing in that sentence |

Primary key on `(sentence_id, lemma_id)`.

#### `definitions`
Lexicon entries from various sources.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Auto-increment ID |
| lemma_id | INTEGER | NOT NULL, FK -> lemmas(id) | Parent lemma |
| source | TEXT | NOT NULL | Lexicon source (e.g. "lsj", "middle_liddell") |
| entry_key | TEXT | | Lookup key in source lexicon |
| definition | TEXT | NOT NULL | Full definition text |
| short_def | TEXT | | Abbreviated definition |

### Derivational Family Tables

#### `derivational_families`
Word family groupings by shared root.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Auto-increment ID |
| root | TEXT | NOT NULL | Root stem (e.g. "βαλ-") |
| label | TEXT | | Human-readable label |

#### `lemma_families`
Links lemmas to their derivational family with hierarchical relationships. The `parent_lemma_id` column enables multi-level derivation chains (e.g. βάλλω -> διαβάλλω -> διάβολος).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| lemma_id | INTEGER | NOT NULL, FK -> lemmas(id) | The member lemma |
| family_id | INTEGER | NOT NULL, FK -> derivational_families(id) | The family it belongs to |
| relation | TEXT | | Relationship type (root, derived, compound, etc.) |
| parent_lemma_id | INTEGER | FK -> lemmas(id) | Parent in the derivation chain (null = derives directly from root) |

Primary key on `(lemma_id, family_id)`.

#### `family_links`
Explicit links between related derivational families, enabling cross-family visualization.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Auto-increment ID |
| family_id_a | INTEGER | NOT NULL, FK -> derivational_families(id) | First family |
| family_id_b | INTEGER | NOT NULL, FK -> derivational_families(id) | Second family |
| link_type | TEXT | | Type of link (e.g. "related", "compound", "split") |
| note | TEXT | | Optional note describing the relationship |

Unique constraint on `(family_id_a, family_id_b)`.

### Aggregate & Utility Tables

#### `work_lemma_counts`
Pre-computed frequency of each lemma in each work. Used for fast vocabulary queries without scanning the full occurrences table.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| work_id | INTEGER | NOT NULL, FK -> works(id) | The work |
| lemma_id | INTEGER | NOT NULL, FK -> lemmas(id) | The lemma |
| count | INTEGER | DEFAULT 1 | Number of occurrences in this work |

Primary key on `(work_id, lemma_id)`.

#### `family_edit_log`
Audit trail for superuser family edits.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Auto-increment ID |
| timestamp | TEXT | | ISO timestamp |
| action | TEXT | | Action performed |
| family_id | INTEGER | | Family affected |
| lemma_id | INTEGER | | Lemma affected |
| detail | TEXT | | JSON detail of the change |
| user | TEXT | | User identifier |

#### `lemmas_fts`
FTS5 virtual table for full-text search across `lemma`, `short_def`, and `lsj_def` columns from the lemmas table.

### Indexes

| Index | Table(Column) |
|-------|---------------|
| idx_lemmas_lemma | lemmas(lemma) |
| idx_lemmas_pos | lemmas(pos) |
| idx_forms_lemma | forms(lemma_id) |
| idx_forms_form | forms(form) |
| idx_occ_lemma | occurrences(lemma_id) |
| idx_occ_work | occurrences(work_id) |
| idx_occ_passage | occurrences(passage) |
| idx_wlc_work | work_lemma_counts(work_id) |
| idx_wlc_lemma | work_lemma_counts(lemma_id) |
| idx_sentence_lemmas_lemma | sentence_lemmas(lemma_id) |
| idx_sentences_work | sentences(work_id) |

### Entity Relationships

```
works --< work_lemma_counts >-- lemmas
works --< occurrences >-- lemmas
                    \---- forms --> lemmas
works --< sentences --< sentence_lemmas >-- lemmas
lemmas --< lemma_families >-- derivational_families
derivational_families --< family_links >-- derivational_families
lemmas --< definitions
lemma_families.parent_lemma_id --> lemmas (hierarchical derivation chain)
```

## API Endpoints

### Read Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/status` | Health check and database stats |
| GET | `/api/works` | List works (filter by `author`, `corpus`) |
| GET | `/api/authors` | List authors with work and token counts |
| GET | `/api/vocab` | Vocabulary list (filter by `work_id`, `author`, `author_code`, `min_freq`, `max_rank`, `pos`; sort by `frequency`, `alpha`, `rank`) |
| GET | `/api/lemma/<id>` | Full lemma details: forms, definitions, family, top works, passages. Optional `?work_id=` to filter forms by work |
| GET | `/api/lemma/by-name/<text>` | Lookup lemma by Greek text (optional `?pos=` filter) |
| GET | `/api/search?q=` | Multi-strategy search: exact match, prefix, FTS, substring |
| GET | `/api/compare` | Compare vocabulary between two works/authors |
| GET | `/api/pos-stats` | Part-of-speech breakdown (optional `author` or `work_id` filter) |
| GET | `/api/family/<id>` | Get family with all members |
| GET | `/api/family/<id>/linked` | Get family with both explicit and implicit linked families |
| GET | `/api/family/search?q=` | Search families by root, label, or member word |

### Superuser Write Endpoints

Require `GLOSSALEARN_SUPERUSER=1` environment variable.

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/family/create` | Create a new derivational family |
| POST | `/api/family/<id>/add-member` | Add a word to a family (with relation and optional parent_lemma_id) |
| DELETE | `/api/family/<id>/member/<lemma_id>` | Remove a word from a family |
| PATCH | `/api/family/<id>/member/<lemma_id>` | Update member relation or parent |
| POST | `/api/family/<id>/merge/<other_id>` | Merge two families |
| PATCH | `/api/family/<id>` | Rename family root and/or label |
| POST | `/api/family/<id>/link/<other_id>` | Link two related families |
| DELETE | `/api/family/<id>/link/<other_id>` | Remove a family link |
| POST | `/api/family/<id>/split` | Split a subtree into a new linked family |

### Admin Sync Endpoint

Requires `GLOSSALEARN_ADMIN_TOKEN` environment variable.

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/admin/sync` | Replay edit operations from a local machine to production |

## Frontend Components

| Component | Description |
|-----------|-------------|
| `App` | Main orchestrator -- state management, layout, data fetching |
| `WorkSelector` | Author and work selection with expandable author rows |
| `WordList` | Searchable, sortable vocabulary list with POS filter chips |
| `FamilyTree` | D3 radial visualization of derivational families with focus/expand on click |
| `FamilyTreeSunburst` | Sunburst visualization for hierarchical family structure |
| `FormsPanel` | Tabbed detail panel showing morphological forms, top works, and definitions |
| `CollapsiblePanel` | Hoverable/pinnable side panels |
| `AddWordModal` | Search and add words to a family with relation and parent selection |
| `NodeActionPopover` | Right-click context menu for editing family tree nodes |
| `MergeFamilyModal` | Search and merge families with similar roots |
| `RenameFamilyModal` | Edit family root stem and label |

## Embeddable Widget (Scaife Viewer Integration)

GlossaLearn includes a lightweight embeddable widget designed for integration into external reading environments such as the [Scaife Viewer](https://scaife.perseus.org/). The widget displays the derivational family visualization for a given Greek word, with both tree and sunburst view modes.

### Widget Files

| File | Purpose |
|------|---------|
| `vocab-viz/widget.html` | Separate HTML entry point for the widget |
| `vocab-viz/src/widget-main.jsx` | Minimal React bootstrap for the widget |
| `vocab-viz/src/EmbedSunburst.jsx` | Widget component: data fetching, tree + sunburst rendering, postMessage communication |
| `vocab-viz/src/embed-theme.js` | Light theme matching Scaife Viewer's color palette |

The widget is built as a second Vite entry point alongside the main app. It produces a separate, small bundle (~7 KB gzipped) and shares no runtime code with the main GlossaLearn application. Changes to the main app do not affect the widget, and vice versa.

### Usage

Embed the widget as an iframe, passing a Greek lemma as a query parameter:

```html
<iframe src="https://glossalearn.com/widget.html?lemma=λόγος"
        style="width: 100%; height: 400px; border: none;"
        sandbox="allow-scripts allow-same-origin"></iframe>
```

The default view mode is tree. To start in sunburst mode, add `&mode=sunburst` to the URL.

### postMessage API

The widget communicates with the parent page via `postMessage`, allowing dynamic word changes without reloading the iframe.

**Parent to widget** — change the displayed word:

```js
iframe.contentWindow.postMessage(
  { type: 'glossalearn:setLemma', lemma: 'φύσις' },
  'https://glossalearn.com'
);
```

**Widget to parent** — events emitted by the widget:

| Message Type | Payload | Description |
|-------------|---------|-------------|
| `glossalearn:ready` | `{}` | Widget has loaded and is ready to receive messages |
| `glossalearn:selectWord` | `{ lemma, id, pos }` | User clicked a word node in the visualization |
| `glossalearn:error` | `{ message }` | Word not found or API unreachable |

### Features

- **Tree and sunburst views** with a toggle in the top-right corner
- **Linked families** — in tree mode, nodes that belong to multiple families show a ⟷ badge; clicking it expands the linked family
- **Pan and zoom** — mouse drag to pan, scroll to zoom
- **Light theme** — white background with terracotta accent (#b45141) and Noto Serif font, designed to blend with the Scaife Viewer interface
- Pulls data from the same production API (`apiaws.glossalearn.com`) — no separate backend required

### Local Development

```bash
cd vocab-viz && npm run dev
# Open http://localhost:5173/widget.html?lemma=λόγος
```

### Build

The widget is included in the standard build. Running `npm run build` produces both `dist/index.html` (main app) and `dist/widget.html` (widget) with separate JS bundles.

## Build & Data Scripts

| Script | Description |
|--------|-------------|
| `build_database.py` | Constructs the database from source corpus data |
| `build_sentences.py` | Populates `sentences` and `sentence_lemmas` tables from lemmatized XML |
| `improve_families.py` | Enriches derivational families using Morpheus stem data |
| `add_work.py` | Ingest a single new work into an existing database (with forms, occurrences, sentences) |
| `sync_edits.py` | Sync local superuser family edits to the production API on Lightsail |
| `sync_work.py` | Push a newly ingested work (all data) to the production database on Lightsail via SSH |
| `download_greek_data.sh` | Downloads source Greek text data |
| `fix_lexica.py` | Repairs lexicon definition data |
| `fix_tlg_titles.py` | Corrects TLG author/title metadata |
| `repair_database.py` | General database repair utilities |
| `repair_families_and_titles.py` | Fixes family groupings and work titles |

## Data Sources & Derivational Families

### Corpus & Lemmatization

The database is built from XML-lemmatized Ancient Greek texts sourced from the [Perseus Digital Library](http://www.perseus.tufts.edu/), the Thesaurus Linguae Graecae (TLG), and the [First1KGreek Project](https://opengreekandlatin.github.io/First1KGreek/). Lexicon definitions come from the LSJ (Liddell-Scott-Jones) and Middle Liddell dictionaries via [PerseusDL/lexica](https://github.com/PerseusDL/lexica).

### Derivational Families

Derivational families group Greek words that share a common root (e.g. βάλλω, διαβάλλω, διάβολος, καταβολή). Families are built in two stages:

1. **Approximate stemming** (`build_database.py`): An initial pass groups lemmas by shared character stems after stripping known Greek prefixes (ἀνα-, δια-, ἐκ-, κατα-, etc.) and common suffixes (-ος, -ία, -ίζω, etc.). This provides broad coverage but produces some inaccurate groupings.

2. **Morpheus enrichment** (`improve_families.py`): A second pass uses stem data from the [Perseus Morpheus morphological parser](https://github.com/PerseusDL/morpheus) to improve and correct the families. Specifically, the script parses:
   - **Compound verb decompositions** (`stemsrc/vbs.cmp.lsj`, `stemsrc/vbs.cmp.ml`) — these files map compound Greek verbs to their constituent prefix + base verb (e.g. ἀφησυχάζω = ἀπό + ἡσυχάζω), providing linguistically accurate parent-child derivation chains.
   - **Simple verb stems** (`stemsrc/vbs.simp.ml`) — these provide canonical stem forms for grouping verbs that share a root.
   - **Nominal stem files** (`stemsrc/nom01`–`nom07`, `nom.irreg`) — these contain noun and adjective stems with prefix decomposition (e.g. ἄβατος = ἀ-privative + βατ-), enabling accurate prefix-based derivational linking.

   The Morpheus data is converted from Perseus Beta Code to Unicode, matched against the lemma table, and used to: create new families from shared stems, set hierarchical parent-child links within families, and merge families that Morpheus reveals share the same root. Existing manually curated families are preserved and enriched, not overwritten.

3. **Superuser curation**: A superuser mode enables manual refinement of family connections — linking related families, splitting subtrees, and correcting automated groupings. As the dataset grows, additional editors may be granted access to further curate the derivational data.

### Cross-Family Links

Families can be linked to show etymological relationships that span separate root groups. Links are created through the superuser interface and synced to production via `sync_edits.py`. The frontend visualizes linked families as connected radial trees, with shared members shown as bridges between families.

### Adding New Works

New works can be added to the database without a full rebuild using `add_work.py`, which ingests a single work from the lemmatized XML corpus. The `sync_work.py` script then pushes the new work data to the production database on Lightsail via SSH.

```bash
# Ingest locally
python3 add_work.py --tlg-author tlg1311 --tlg-work tlg001 --author "Apostolic Fathers" --title "Didache"

# Push to production
python3 sync_work.py --title "Didache" --push
```

### Data Access

For those who would like access to the data, you may write randallcraigmeister [at] gmail [dot] com and request a token and download the data at the endpoint: `https://api.glossalearn.com/api/download-db?token=[TOKEN]`

### Attribution & License

The Morpheus stem data is from the [Perseus Digital Library](http://www.perseus.tufts.edu/) at Tufts University:

> Gregory Crane, ed. *Morpheus: Greek and Latin Morphological Analysis*. Perseus Digital Library Project, Tufts University. [github.com/PerseusDL/morpheus](https://github.com/PerseusDL/morpheus)

The Morpheus data is licensed under a [Creative Commons Attribution-ShareAlike 3.0 United States License](https://creativecommons.org/licenses/by-sa/3.0/us/) (CC BY-SA 3.0 US). Copyright is held by the Trustees of Tufts University. In accordance with the license terms:

- This project provides **attribution** to Perseus Digital Library and its contributors.
- Any **modifications or derived data** produced by this project (the derivational family groupings built from Morpheus stems) are shared under the same CC BY-SA 3.0 US license.
- The Morpheus stem files are downloaded at build time and cached locally; they are not redistributed in this repository.

Lexicon data (LSJ, Middle Liddell) is similarly sourced from [PerseusDL/lexica](https://github.com/PerseusDL/lexica) under the same CC BY-SA 3.0 US license.

## Build Scripts

| Script | Description |
|--------|-------------|
| `build_database.py` | Constructs the database from source corpus data |
| `improve_families.py` | Enriches derivational families using Morpheus stem data |
| `download_greek_data.sh` | Downloads source Greek text data |
| `fix_lexica.py` | Repairs lexicon definition data |
| `fix_tlg_titles.py` | Corrects TLG author/title metadata |
| `repair_database.py` | General database repair utilities |
| `repair_families_and_titles.py` | Fixes family groupings and work titles |
| `./speech/download_datasets.sh` | Download and index speech corpora |

