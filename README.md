# Glossalearn

A Greek vocabulary explorer for studying Ancient Greek texts. Browse vocabulary by author and work, explore morphological forms, and visualize derivational word families through an interactive radial tree.

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

To enable family editing features (add/remove words, merge/rename families):

```bash
GLOSSALEARN_SUPERUSER=1 python3 serve_api.py
```

## Architecture

- **Backend**: Flask REST API (`serve_api.py`) serving data from SQLite
- **Frontend**: React single-page app with D3.js radial visualization (`vocab-viz/src/App.jsx`)
- **Database**: `greek_vocab.db` (~1.3 GB) containing the full Greek corpus with morphology, lemmatization, and occurrence data

## Database Schema

### Core Tables

#### `works`
Texts in the corpus (Perseus, TLG).

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

### Entity Relationships

```
works --< work_lemma_counts >-- lemmas
works --< occurrences >-- lemmas
                    \---- forms --> lemmas
lemmas --< lemma_families >-- derivational_families
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

## Frontend Components

| Component | Description |
|-----------|-------------|
| `App` | Main orchestrator -- state management, layout, data fetching |
| `WorkSelector` | Author and work selection with expandable author rows |
| `WordList` | Searchable, sortable vocabulary list with POS filter chips |
| `FamilyTree` | D3 radial visualization of derivational families with focus/expand on click |
| `FormsPanel` | Tabbed detail panel showing morphological forms, top works, and definitions |
| `CollapsiblePanel` | Hoverable/pinnable side panels |
| `AddWordModal` | Search and add words to a family with relation and parent selection |
| `NodeActionPopover` | Right-click context menu for editing family tree nodes |
| `MergeFamilyModal` | Search and merge families with similar roots |
| `RenameFamilyModal` | Edit family root stem and label |

## Build Scripts

| Script | Description |
|--------|-------------|
| `build_database.py` | Constructs the database from source corpus data |
| `download_greek_data.sh` | Downloads source Greek text data |
| `fix_lexica.py` | Repairs lexicon definition data |
| `fix_tlg_titles.py` | Corrects TLG author/title metadata |
| `repair_database.py` | General database repair utilities |
| `repair_families_and_titles.py` | Fixes family groupings and work titles |
