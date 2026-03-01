Here's the outline of the greek_vocab.db schema:

---
works

| Column | Type | Constraints |

|---|---|---|

| id | INTEGER | PRIMARY KEY AUTOINCREMENT |

| filename | TEXT | NOT NULL UNIQUE |

| cts_urn | TEXT | |

| author_code | TEXT | |

| work_code | TEXT | |

| author | TEXT | |

| title | TEXT | |

| corpus | TEXT | DEFAULT 'perseus' |



lemmas

| Column | Type | Constraints |

|---|---|---|

| id | INTEGER | PRIMARY KEY AUTOINCREMENT |

| lemma | TEXT | NOT NULL, UNIQUE(lemma, pos) |

| pos | TEXT | |

| short_def | TEXT | |

| lsj_def | TEXT | |

| middle_liddell | TEXT | |

| total_occurrences | INTEGER | DEFAULT 0 |

| frequency_rank | INTEGER | |



forms

| Column | Type | Constraints |

|---|---|---|

| id | INTEGER | PRIMARY KEY AUTOINCREMENT |

| lemma_id | INTEGER | NOT NULL, FK → lemmas(id) |

| form | TEXT | NOT NULL |

| morph_tag | TEXT | |

| pos | TEXT | |

| person | TEXT | |

| number | TEXT | |

| tense | TEXT | |

| mood | TEXT | |

| voice | TEXT | |

| gender | TEXT | |

| gram_case | TEXT | |

| degree | TEXT | |

| | | UNIQUE(lemma_id, form, morph_tag) |



occurrences

| Column | Type | Constraints |

|---|---|---|

| id | INTEGER | PRIMARY KEY AUTOINCREMENT |

| lemma_id | INTEGER | NOT NULL, FK → lemmas(id) |

| form_id | INTEGER | FK → forms(id) |

| work_id | INTEGER | NOT NULL, FK → works(id) |

| passage | TEXT | |

| sentence_n | INTEGER | |

| token_n | INTEGER | |



definitions

| Column | Type | Constraints |

|---|---|---|

| id | INTEGER | PRIMARY KEY AUTOINCREMENT |

| lemma_id | INTEGER | NOT NULL, FK → lemmas(id) |

| source | TEXT | NOT NULL |

| entry_key | TEXT | |

| definition | TEXT | NOT NULL |

| short_def | TEXT | |



derivational_families

| Column | Type | Constraints |

|---|---|---|

| id | INTEGER | PRIMARY KEY AUTOINCREMENT |

| root | TEXT | NOT NULL |

| label | TEXT | |



lemma_families

| Column | Type | Constraints |

|---|---|---|

| lemma_id | INTEGER | NOT NULL, FK → lemmas(id) |

| family_id | INTEGER | NOT NULL, FK → derivational_families(id) |

| relation | TEXT | |

| | | PRIMARY KEY(lemma_id, family_id) |



work_lemma_counts

| Column | Type | Constraints |

|---|---|---|

| work_id | INTEGER | NOT NULL, FK → works(id) |

| lemma_id | INTEGER | NOT NULL, FK → lemmas(id) |

| count | INTEGER | DEFAULT 1 |

| | | PRIMARY KEY(work_id, lemma_id) |



lemmas_fts (FTS5 virtual table)

Full-text search index over lemma, short_def, and lsj_def from the lemmas table.



Indexes
idx_lemmas_lemma → lemmas(lemma)
idx_lemmas_pos → lemmas(pos)
idx_forms_lemma → forms(lemma_id)
idx_forms_form → forms(form)
idx_occ_lemma → occurrences(lemma_id)
idx_occ_work → occurrences(work_id)
idx_occ_passage → occurrences(passage)
idx_wlc_work → work_lemma_counts(work_id)
idx_wlc_lemma → work_lemma_counts(lemma_id)