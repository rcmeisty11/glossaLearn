#!/usr/bin/env python3
"""
fix_tlg_titles.py
Comprehensive fix for TLG codes still showing as author/title in greek_vocab.db.
Updates both author names and work titles from the TLG canon.

Usage:
    python3 fix_tlg_titles.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("./greek_vocab.db")
if not DB_PATH.exists():
    print("ERROR: greek_vocab.db not found")
    raise SystemExit(1)

conn = sqlite3.connect(str(DB_PATH))
conn.execute("PRAGMA journal_mode=WAL")
cur = conn.cursor()

# ── Author code → name ──────────────────────────────────────────
AUTHORS = {
    "stoa0033a": "Aesop",
    "tlg0001":  "Apollonius Rhodius",
    "tlg0003":  "Thucydides",
    "tlg0006":  "Euripides",
    "tlg0007":  "Plutarch",
    "tlg0008":  "Athenaeus",
    "tlg0009":  "Sappho",
    "tlg0010":  "Isocrates",
    "tlg0011":  "Sophocles",
    "tlg0012":  "Homer",
    "tlg0013":  "Homeric Hymns",
    "tlg0014":  "Demosthenes",
    "tlg0015":  "Hippocrates",
    "tlg0016":  "Herodotus",
    "tlg0017":  "Isaeus",
    "tlg0018":  "Apollonius Dyscolus",
    "tlg0019":  "Aristophanes",
    "tlg0020":  "Hesiod",
    "tlg0028":  "Antiphon",
    "tlg0031":  "New Testament",
    "tlg0032":  "Xenophon",
    "tlg0033":  "Polybius",
    "tlg0036":  "Apollodorus",
    "tlg0046":  "Pausanias",
    "tlg0057":  "Galen",
    "tlg0059":  "Plato",
    "tlg0060":  "Diodorus Siculus",
    "tlg0062":  "Lucian",
    "tlg0074":  "Callimachus",
    "tlg0081":  "Athenaeus",
    "tlg0082":  "Aeschines",
    "tlg0085":  "Aeschylus",
    "tlg0086":  "Aristotle",
    "tlg0088":  "Dinarchus",
    "tlg0090":  "Strabo",
    "tlg0093":  "Theophrastus",
    "tlg0096":  "Aratus",
    "tlg0099":  "Pindar",
    "tlg0358":  "Quintus Smyrnaeus",
    "tlg0363":  "Nonnus",
    "tlg0525":  "Josephus",
    "tlg0526":  "Philo",
    "tlg0527":  "Septuagint",
    "tlg0530":  "Dio Chrysostom",
    "tlg0540":  "Lysias",
    "tlg0541":  "Hyperides",
    "tlg0543":  "Lycurgus",
    "tlg0544":  "Andocides",
    "tlg0548":  "Demetrius",
    "tlg0551":  "Dio Cassius",
    "tlg0553":  "Appian",
    "tlg0554":  "Arrian",
    "tlg0555":  "Marcus Aurelius",
    "tlg0557":  "Epictetus",
    "tlg0561":  "Epictetus",
    "tlg0565":  "Aelian",
    "tlg0610":  "Oppian",
    "tlg0612":  "Babrius",
    "tlg0614":  "Longus",
    "tlg0615":  "Chariton",
    "tlg0616":  "Achilles Tatius",
    "tlg0627":  "Hippocrates",
    "tlg0640":  "Pseudo-Apollodorus",
    "tlg0643":  "Heliodorus",
    "tlg0645":  "Philostratus",
    "tlg0646":  "Philostratus the Elder",
    "tlg0658":  "Parthenius",
    "tlg0661":  "Diogenes Laertius",
    "tlg0708":  "Alexander of Aphrodisias",
    "tlg0732":  "Sextus Empiricus",
    "tlg0751":  "Porphyry",
    "tlg1126":  "Colluthus",
    "tlg1205":  "Tryphiodorus",
    "tlg1210":  "Musaeus",
    "tlg1216":  "Bion",
    "tlg1220":  "Moschus",
    "tlg1252":  "Theocritus",
    "tlg1271":  "Apollonius Sophista",
    "tlg1311":  "Cornutus",
    "tlg1337":  "Hermogenes",
    "tlg1389":  "Aelius Aristides",
    "tlg1419":  "Maximus of Tyre",
    "tlg1443":  "Dionysius of Halicarnassus",
    "tlg1447":  "Longinus",
    "tlg1463":  "Aelius Herodianus",
    "tlg1484":  "Pollux",
    "tlg1487":  "Harpocration",
    "tlg1551":  "Artemidorus",
    "tlg1600":  "Hesychius",
    "tlg1622":  "Numenius",
    "tlg1701":  "Cassius Dio",
    "tlg1724":  "Ps.-Plutarch",
    "tlg1725":  "Ps.-Plutarch",
    "tlg1765":  "Iamblichus",
    "tlg1766":  "Julian",
    "tlg1799":  "Libanius",
    "tlg2000":  "Didymus",
    "tlg2001":  "Athanasius",
    "tlg2018":  "Clement of Alexandria",
    "tlg2021":  "Hippolytus",
    "tlg2022":  "Origen",
    "tlg2023":  "Gregory Thaumaturgus",
    "tlg2034":  "Methodius",
    "tlg2036":  "Eustathius of Antioch",
    "tlg2040":  "Basil of Caesarea",
    "tlg2041":  "Gregory of Nazianzus",
    "tlg2042":  "John Chrysostom",
    "tlg2048":  "Ps.-Macarius",
    "tlg2050":  "Didymus the Blind",
    "tlg2057":  "Epiphanius",
    "tlg2058":  "Ephrem the Syrian",
    "tlg2115":  "Cyril of Alexandria",
    "tlg2200":  "Plotinus",
    "tlg2371":  "Proclus",
    "tlg2583":  "Simplicius",
    "tlg2703":  "George Syncellus",
    "tlg2733":  "Leontius of Byzantium",
    "tlg2768":  "John Philoponus",
    "tlg2959":  "Photius",
    "tlg3118":  "Michael Psellus",
    "tlg3135":  "Eustathius of Thessalonica",
    "tlg3156":  "Nicetas Choniates",
    "tlg4013":  "Methodius of Olympus",
    "tlg4015":  "Eusebius",
    "tlg4016":  "Cyril of Jerusalem",
    "tlg4017":  "Amphilochius of Iconium",
    "tlg4018":  "Didymus the Blind",
    "tlg4019":  "Ps.-Athanasius",
    "tlg4020":  "Gregory of Nyssa",
    "tlg4021":  "Nemesius",
    "tlg4024":  "Theodore of Mopsuestia",
    "tlg4027":  "Nestorius",
    "tlg4030":  "Theodoret",
    "tlg4031":  "Isidore of Pelusium",
    "tlg4033":  "Mark the Hermit",
    "tlg4034":  "Nilus of Ancyra",
    "tlg4036":  "Ps.-Dionysius the Areopagite",
    "tlg4075":  "Maximus the Confessor",
    "tlg4084":  "Leontius of Jerusalem",
    "tlg4089":  "Anastasius of Sinai",
    "tlg4090":  "Germanus of Constantinople",
    "tlg4102":  "John of Damascus",
    "tlg4170":  "Symeon the New Theologian",
    "tlg4193":  "Michael Glycas",
    "tlg5022":  "Scholia",
    "tlg5026":  "Scholia in Homerum",
    "tlg5034":  "Scholia in Aristophanem",
    "tlg9004":  "Anthology",
    "tlg9006":  "Anthology",
    "tlg9019":  "Anthology",
}

# ── (author_code, work_code) → title ────────────────────────────
TITLES = {
    # Aesop
    ("stoa0033a", "tlg028"): "Fables (Perry)",
    ("stoa0033a", "tlg043"): "Fables (Chambry)",
    # Plutarch — Lives
    ("tlg0007", "tlg006"): "Camillus",
    ("tlg0007", "tlg008"): "Aristides",
    ("tlg0007", "tlg010"): "Cimon",
    ("tlg0007", "tlg011"): "Lucullus",
    ("tlg0007", "tlg013"): "Nicias",
    ("tlg0007", "tlg015"): "Lysander",
    ("tlg0007", "tlg016"): "Sulla",
    ("tlg0007", "tlg017"): "Agesilaus",
    ("tlg0007", "tlg018"): "Pompey",
    ("tlg0007", "tlg021"): "Timoleon",
    ("tlg0007", "tlg047"): "Moralia",
    # Athenaeus
    ("tlg0008", "tlg001"): "Deipnosophistae",
    # Isocrates — Orations
    ("tlg0010", "tlg001"): "To Demonicus",
    ("tlg0010", "tlg002"): "To Nicocles",
    ("tlg0010", "tlg003"): "Nicocles",
    ("tlg0010", "tlg004"): "Panegyricus",
    ("tlg0010", "tlg005"): "To Philip",
    ("tlg0010", "tlg006"): "Archidamus",
    ("tlg0010", "tlg007"): "Areopagiticus",
    ("tlg0010", "tlg008"): "On the Peace",
    ("tlg0010", "tlg009"): "Evagoras",
    ("tlg0010", "tlg010"): "Helen",
    ("tlg0010", "tlg011"): "Busiris",
    ("tlg0010", "tlg012"): "Panathenaicus",
    ("tlg0010", "tlg013"): "Against the Sophists",
    ("tlg0010", "tlg014"): "Plataicus",
    ("tlg0010", "tlg015"): "Antidosis",
    ("tlg0010", "tlg016"): "De Pace",
    ("tlg0010", "tlg017"): "Trapeziticus",
    ("tlg0010", "tlg018"): "Against Callimachus",
    ("tlg0010", "tlg019"): "Aegineticus",
    ("tlg0010", "tlg020"): "Against Lochites",
    ("tlg0010", "tlg021"): "Against Euthynus",
    ("tlg0010", "tlg022"): "Letters 1",
    ("tlg0010", "tlg023"): "Letters 2",
    ("tlg0010", "tlg024"): "Letters 3",
    ("tlg0010", "tlg025"): "Letters 4",
    ("tlg0010", "tlg026"): "Letters 5",
    ("tlg0010", "tlg027"): "Letters 6",
    ("tlg0010", "tlg028"): "Letters 7",
    ("tlg0010", "tlg029"): "Letters 8",
    ("tlg0010", "tlg030"): "Letters 9",
    # Sophocles — Fragments
    ("tlg0011", "tlg008"): "Fragments",
    # Homeric Hymns 6–33
    ("tlg0013", "tlg006"): "Hymn to Aphrodite II",
    ("tlg0013", "tlg007"): "Hymn to Dionysus II",
    ("tlg0013", "tlg008"): "Hymn to Ares",
    ("tlg0013", "tlg009"): "Hymn to Artemis I",
    ("tlg0013", "tlg010"): "Hymn to Aphrodite III",
    ("tlg0013", "tlg011"): "Hymn to Athena",
    ("tlg0013", "tlg012"): "Hymn to Hera",
    ("tlg0013", "tlg013"): "Hymn to Demeter II",
    ("tlg0013", "tlg014"): "Hymn to the Mother of the Gods",
    ("tlg0013", "tlg015"): "Hymn to Heracles",
    ("tlg0013", "tlg016"): "Hymn to Asclepius",
    ("tlg0013", "tlg017"): "Hymn to the Dioscuri I",
    ("tlg0013", "tlg018"): "Hymn to Hermes II",
    ("tlg0013", "tlg019"): "Hymn to Pan",
    ("tlg0013", "tlg020"): "Hymn to Hephaestus",
    ("tlg0013", "tlg021"): "Hymn to Apollo II",
    ("tlg0013", "tlg022"): "Hymn to Poseidon",
    ("tlg0013", "tlg023"): "Hymn to Zeus",
    ("tlg0013", "tlg024"): "Hymn to Hestia I",
    ("tlg0013", "tlg025"): "Hymn to the Muses and Apollo",
    ("tlg0013", "tlg026"): "Hymn to Dionysus III",
    ("tlg0013", "tlg027"): "Hymn to Artemis II",
    ("tlg0013", "tlg028"): "Hymn to Athena II",
    ("tlg0013", "tlg029"): "Hymn to Hestia II",
    ("tlg0013", "tlg030"): "Hymn to Earth",
    ("tlg0013", "tlg031"): "Hymn to Helios",
    ("tlg0013", "tlg032"): "Hymn to Selene",
    ("tlg0013", "tlg033"): "Hymn to the Dioscuri II",
    # Hippocrates (tlg0015)
    ("tlg0015", "tlg001"): "On Ancient Medicine",
    # Apollonius Dyscolus — grammar works (tlg0018)
    ("tlg0018", "tlg001"): "On Syntax",
    ("tlg0018", "tlg002"): "On Pronouns",
    ("tlg0018", "tlg003"): "On Conjunctions",
    ("tlg0018", "tlg004"): "On Adverbs",
    ("tlg0018", "tlg005"): "Fragments 5",
    ("tlg0018", "tlg006"): "Fragments 6",
    ("tlg0018", "tlg007"): "Fragments 7",
    ("tlg0018", "tlg008"): "Fragments 8",
    ("tlg0018", "tlg009"): "Fragments 9",
    ("tlg0018", "tlg010"): "Fragments 10",
    ("tlg0018", "tlg011"): "Fragments 11",
    ("tlg0018", "tlg012"): "Fragments 12",
    ("tlg0018", "tlg013"): "Fragments 13",
    ("tlg0018", "tlg014"): "Fragments 14",
    ("tlg0018", "tlg015"): "Fragments 15",
    ("tlg0018", "tlg016"): "Fragments 16",
    ("tlg0018", "tlg017"): "Fragments 17",
    ("tlg0018", "tlg018"): "Fragments 18",
    ("tlg0018", "tlg019"): "Fragments 19",
    ("tlg0018", "tlg020"): "Fragments 20",
    ("tlg0018", "tlg021"): "Fragments 21",
    ("tlg0018", "tlg022"): "Fragments 22",
    ("tlg0018", "tlg023"): "Fragments 23",
    ("tlg0018", "tlg024"): "Fragments 24",
    ("tlg0018", "tlg025"): "Fragments 25",
    ("tlg0018", "tlg026"): "Fragments 26",
    ("tlg0018", "tlg027"): "Fragments 27",
    ("tlg0018", "tlg028"): "Fragments 28",
    ("tlg0018", "tlg029"): "Fragments 29",
    ("tlg0018", "tlg030"): "Fragments 30",
    ("tlg0018", "tlg031"): "Fragments 31",
    # Antiphon
    ("tlg0028", "tlg005"): "On the Murder of Herodes",
    # Polybius
    ("tlg0033", "tlg002"): "Histories (Exc.)",
    ("tlg0033", "tlg003"): "Fragments",
    ("tlg0033", "tlg004"): "Fragments",
    # Galen — major works
    ("tlg0057", "tlg002"): "On the Use of the Parts",
    ("tlg0057", "tlg003"): "On the Doctrines of Hippocrates and Plato",
    ("tlg0057", "tlg004"): "On the Composition of Drugs by Kind",
    ("tlg0057", "tlg006"): "On the Affected Parts",
    ("tlg0057", "tlg007"): "On the Pulse",
    ("tlg0057", "tlg008"): "On Anatomical Procedures",
    ("tlg0057", "tlg010"): "On Temperaments",
    ("tlg0057", "tlg011"): "On the Elements According to Hippocrates",
    ("tlg0057", "tlg012"): "On Critical Days",
    ("tlg0057", "tlg013"): "On Crises",
    ("tlg0057", "tlg014"): "On the Causes of Symptoms",
    ("tlg0057", "tlg015"): "On the Differences of Fevers",
    ("tlg0057", "tlg016"): "On the Causes of Diseases",
    ("tlg0057", "tlg017"): "Commentary on Hippocrates' Aphorisms",
    ("tlg0057", "tlg018"): "Commentary on Hippocrates' Epidemics",
    ("tlg0057", "tlg019"): "Commentary on Hippocrates' Prognostic",
    ("tlg0057", "tlg020"): "Commentary on Hippocrates' Regimen in Acute Diseases",
    ("tlg0057", "tlg021"): "On the Powers of Simple Drugs",
    ("tlg0057", "tlg022"): "On the Composition of Drugs by Place",
    ("tlg0057", "tlg023"): "On Prognosis",
    ("tlg0057", "tlg024"): "On the Preservation of Health",
    ("tlg0057", "tlg025"): "On Bloodletting",
    ("tlg0057", "tlg027"): "On the Movement of Muscles",
    ("tlg0057", "tlg028"): "On Semen",
    ("tlg0057", "tlg029"): "On the Formation of the Fetus",
    ("tlg0057", "tlg030"): "On Bones for Beginners",
    ("tlg0057", "tlg031"): "On the Anatomy of Veins and Arteries",
    ("tlg0057", "tlg032"): "On the Anatomy of Nerves",
    ("tlg0057", "tlg034"): "On the Order of His Own Books",
    ("tlg0057", "tlg035"): "On His Own Books",
    ("tlg0057", "tlg036"): "On the Best Sect",
    ("tlg0057", "tlg038"): "On Medical Experience",
    ("tlg0057", "tlg039"): "An Outline of Empiricism",
    ("tlg0057", "tlg040"): "On the Sects for Beginners",
    ("tlg0057", "tlg041"): "On the Best Constitution of Our Body",
    ("tlg0057", "tlg042"): "Exhortation to Medicine",
    ("tlg0057", "tlg043"): "That the Best Physician is Also a Philosopher",
    ("tlg0057", "tlg044"): "On Diagnosis of Pulses",
    ("tlg0057", "tlg045"): "On the Causes of Pulses",
    ("tlg0057", "tlg046"): "On Prognosis from Pulses",
    ("tlg0057", "tlg047"): "Synopsis on Pulses",
    ("tlg0057", "tlg048"): "On Tremor",
    ("tlg0057", "tlg049"): "On the Differences of Symptoms",
    ("tlg0057", "tlg050"): "On Plethora",
    ("tlg0057", "tlg051"): "On Uneven Distemperament",
    ("tlg0057", "tlg052"): "On Marasmus",
    ("tlg0057", "tlg053"): "On the Causes of Procatarctic Causes",
    ("tlg0057", "tlg054"): "On Difficult Breathing",
    ("tlg0057", "tlg055"): "On the Usefulness of Breathing",
    ("tlg0057", "tlg056"): "On Antecedent Causes",
    ("tlg0057", "tlg057"): "On the Different Types of Homogeneous Parts",
    ("tlg0057", "tlg058"): "On Medical Definitions",
    ("tlg0057", "tlg059"): "On Habits",
    ("tlg0057", "tlg060"): "On Good and Bad Humors",
    ("tlg0057", "tlg061"): "On Black Bile",
    ("tlg0057", "tlg062"): "On the Properties of Foods",
    ("tlg0057", "tlg063"): "On the Thinning Diet",
    ("tlg0057", "tlg064"): "On Barley Soup",
    ("tlg0057", "tlg065"): "On Exercise with a Small Ball",
    ("tlg0057", "tlg066"): "On the Natural Faculties (alt.)",
    ("tlg0057", "tlg067"): "Medical work 67",
    ("tlg0057", "tlg068"): "Medical work 68",
    ("tlg0057", "tlg069"): "Medical work 69",
    ("tlg0057", "tlg070"): "Medical work 70",
    ("tlg0057", "tlg071"): "Medical work 71",
    ("tlg0057", "tlg072"): "Medical work 72",
    ("tlg0057", "tlg073"): "Medical work 73",
    ("tlg0057", "tlg074"): "Medical work 74",
    ("tlg0057", "tlg075"): "Medical work 75",
    ("tlg0057", "tlg076"): "Medical work 76",
    ("tlg0057", "tlg077"): "Medical work 77",
    ("tlg0057", "tlg078"): "Medical work 78",
    ("tlg0057", "tlg079"): "Medical work 79",
    ("tlg0057", "tlg081"): "Medical work 81",
    ("tlg0057", "tlg082"): "Medical work 82",
    ("tlg0057", "tlg083"): "Medical work 83",
    ("tlg0057", "tlg084"): "Medical work 84",
    ("tlg0057", "tlg085"): "Medical work 85",
    ("tlg0057", "tlg087"): "Medical work 87",
    ("tlg0057", "tlg089"): "Medical work 89",
    ("tlg0057", "tlg092"): "Medical work 92",
    ("tlg0057", "tlg093"): "Medical work 93",
    ("tlg0057", "tlg094"): "Medical work 94",
    ("tlg0057", "tlg095"): "Medical work 95",
    ("tlg0057", "tlg099"): "Medical work 99",
    ("tlg0057", "tlg100"): "Medical work 100",
    ("tlg0057", "tlg101"): "Medical work 101",
    ("tlg0057", "tlg102"): "Medical work 102",
    ("tlg0057", "tlg103"): "Medical work 103",
    ("tlg0057", "tlg107"): "Medical work 107",
    ("tlg0057", "tlg114"): "Medical work 114",
    # Plato
    ("tlg0059", "tlg037"): "Definitions",
    # Lucian
    ("tlg0062", "tlg016"): "The Dream",
    ("tlg0062", "tlg017"): "Prometheus",
    ("tlg0062", "tlg018"): "Icaromenippus",
    ("tlg0062", "tlg019"): "Timon",
    ("tlg0062", "tlg020"): "Charon",
    ("tlg0062", "tlg021"): "Philosophies for Sale",
    ("tlg0062", "tlg022"): "The Fisher",
    ("tlg0062", "tlg023"): "The Double Indictment",
    ("tlg0062", "tlg024"): "On Sacrifices",
    ("tlg0062", "tlg025"): "The Ignorant Book Collector",
    ("tlg0062", "tlg026"): "The Cock",
    ("tlg0062", "tlg027"): "Lexiphanes",
    ("tlg0062", "tlg028"): "The Eunuch",
    ("tlg0062", "tlg029"): "Astrology",
    ("tlg0062", "tlg030"): "The Parasite",
    ("tlg0062", "tlg031"): "The Lover of Lies",
    ("tlg0062", "tlg032"): "The Judgment of the Goddesses",
    ("tlg0062", "tlg033"): "On the Syrian Goddess",
    ("tlg0062", "tlg042"): "A True Story I",
    ("tlg0062", "tlg043"): "A True Story II",
    ("tlg0062", "tlg044"): "Dialogues of the Gods",
    ("tlg0062", "tlg045"): "Dialogues of the Sea Gods",
    ("tlg0062", "tlg046"): "Dialogues of the Dead (alt.)",
    ("tlg0062", "tlg047"): "Dialogues of the Courtesans",
    ("tlg0062", "tlg048"): "Alexander the False Prophet",
    ("tlg0062", "tlg049"): "Essays in Portraiture",
    ("tlg0062", "tlg050"): "Essays in Portraiture Defended",
    ("tlg0062", "tlg051"): "The Passing of Peregrinus",
    ("tlg0062", "tlg052"): "The Runaways",
    ("tlg0062", "tlg067"): "Toxaris",
    # Callimachus
    ("tlg0074", "tlg001"): "Hymns",
    ("tlg0074", "tlg002"): "Epigrams",
    ("tlg0074", "tlg003"): "Aetia",
    ("tlg0074", "tlg004"): "Iambi",
    ("tlg0074", "tlg005"): "Hecale",
    ("tlg0074", "tlg006"): "Fragments",
    # Aeschines
    ("tlg0082", "tlg001"): "Against Timarchus",
    ("tlg0082", "tlg002"): "On the Embassy",
    ("tlg0082", "tlg004"): "Letters",
    # Aristotle — additional works
    ("tlg0086", "tlg014"): "On Sense and Sensibilia",
    ("tlg0086", "tlg016"): "On Memory",
    ("tlg0086", "tlg017"): "On Sleep",
    ("tlg0086", "tlg018"): "On Dreams",
    ("tlg0086", "tlg020"): "On Length and Shortness of Life",
    ("tlg0086", "tlg022"): "On Breath",
    ("tlg0086", "tlg024"): "History of Animals",
    ("tlg0086", "tlg026"): "Parts of Animals",
    ("tlg0086", "tlg030"): "Generation of Animals",
    ("tlg0086", "tlg037"): "Problems",
    ("tlg0086", "tlg042"): "On Marvellous Things Heard",
    ("tlg0086", "tlg044"): "On Virtues and Vices",
    ("tlg0086", "tlg052"): "On the Motion of Animals",
    ("tlg0086", "tlg054"): "On the Progression of Animals",
    # Dinarchus
    ("tlg0088", "tlg001"): "Against Demosthenes",
    # Aratus
    ("tlg0096", "tlg002"): "Phaenomena",
    # Quintus Smyrnaeus
    ("tlg0358", "tlg001"): "Posthomerica",
    ("tlg0358", "tlg005"): "Fragments",
    # Nonnus
    ("tlg0363", "tlg001"): "Dionysiaca",
    ("tlg0363", "tlg007"): "Paraphrase of the Gospel of John",
    # Josephus
    ("tlg0525", "tlg001"): "Jewish War",
    # Dio Chrysostom
    ("tlg0530", "tlg005"): "Oration 5",
    ("tlg0530", "tlg006"): "Oration 6",
    ("tlg0530", "tlg012"): "Oration 12 (Olympic Discourse)",
    ("tlg0530", "tlg029"): "Oration 29",
    ("tlg0530", "tlg032"): "Oration 32",
    ("tlg0530", "tlg043"): "Oration 43",
    # Lysias — Orations
    ("tlg0540", "tlg001"): "On the Murder of Eratosthenes",
    ("tlg0540", "tlg002"): "Funeral Oration",
    ("tlg0540", "tlg003"): "Against Simon",
    ("tlg0540", "tlg004"): "On a Wound by Premeditation",
    ("tlg0540", "tlg005"): "For Callias",
    ("tlg0540", "tlg006"): "Against Andocides",
    ("tlg0540", "tlg007"): "On the Olive Stump",
    ("tlg0540", "tlg008"): "Accusation of Calumny",
    ("tlg0540", "tlg009"): "For the Soldier",
    ("tlg0540", "tlg010"): "Against Theomnestus I",
    ("tlg0540", "tlg011"): "Against Theomnestus II",
    ("tlg0540", "tlg012"): "Against Eratosthenes",
    ("tlg0540", "tlg013"): "Against Agoratus",
    ("tlg0540", "tlg014"): "Against Alcibiades I",
    ("tlg0540", "tlg015"): "Against Alcibiades II",
    ("tlg0540", "tlg016"): "For Mantitheus",
    ("tlg0540", "tlg017"): "On the Property of Eraton",
    ("tlg0540", "tlg018"): "On the Confiscation of the Property of the Brother of Nicias",
    ("tlg0540", "tlg019"): "On the Property of Aristophanes",
    ("tlg0540", "tlg020"): "For Polystratus",
    ("tlg0540", "tlg021"): "Defence against a Charge of Taking Bribes",
    ("tlg0540", "tlg022"): "Against the Corn Dealers",
    ("tlg0540", "tlg023"): "Against Pancleon",
    ("tlg0540", "tlg024"): "On the Refusal of a Pension",
    ("tlg0540", "tlg025"): "On the Subversion of the Ancestral Constitution",
    ("tlg0540", "tlg026"): "On the Scrutiny of Evandros",
    ("tlg0540", "tlg027"): "Against Epicrates",
    ("tlg0540", "tlg028"): "Against Ergocles",
    ("tlg0540", "tlg029"): "Against Philocrates",
    ("tlg0540", "tlg030"): "Against Nicomachus",
    ("tlg0540", "tlg031"): "Against Philon",
    ("tlg0540", "tlg032"): "Against Diogeiton",
    ("tlg0540", "tlg033"): "Olympic Oration",
    ("tlg0540", "tlg034"): "Against the Subversion of the Ancestral Constitution",
    # Hyperides
    ("tlg0541", "tlg042"): "Fragments",
    # Lycurgus
    ("tlg0543", "tlg001"): "Against Leocrates",
    # Andocides
    ("tlg0544", "tlg001"): "On the Mysteries",
    ("tlg0544", "tlg002"): "On His Return",
    # Demetrius
    ("tlg0548", "tlg001"): "On Style",
    ("tlg0548", "tlg002"): "Fragments",
    # Dio Cassius — Roman History
    ("tlg0551", "tlg002"): "Roman History 2",
    ("tlg0551", "tlg003"): "Roman History 3",
    ("tlg0551", "tlg004"): "Roman History 4",
    ("tlg0551", "tlg005"): "Roman History 5",
    ("tlg0551", "tlg006"): "Roman History 6",
    ("tlg0551", "tlg007"): "Roman History 7",
    ("tlg0551", "tlg008"): "Roman History 8",
    ("tlg0551", "tlg009"): "Roman History 9",
    ("tlg0551", "tlg010"): "Roman History 10",
    ("tlg0551", "tlg011"): "Roman History 11",
    ("tlg0551", "tlg012"): "Roman History 12",
    ("tlg0551", "tlg013"): "Roman History 13",
    ("tlg0551", "tlg014"): "Roman History 14",
    ("tlg0551", "tlg017"): "Roman History 17",
    # Appian
    ("tlg0553", "tlg001"): "Roman History",
    # Arrian
    ("tlg0554", "tlg001"): "Anabasis of Alexander",
    # Marcus Aurelius
    ("tlg0555", "tlg001"): "Meditations",
    ("tlg0555", "tlg002"): "Letters",
    ("tlg0555", "tlg004b"): "Fragments",
    ("tlg0555", "tlg005"): "Fragments",
    ("tlg0555", "tlg006"): "Fragments",
    ("tlg0555", "tlg007"): "Fragments",
    # Epictetus
    ("tlg0557", "tlg001"): "Discourses",
    ("tlg0557", "tlg002"): "Enchiridion",
    ("tlg0561", "tlg001"): "Discourses",
    # Aelian
    ("tlg0565", "tlg001"): "De Natura Animalium",
    ("tlg0565", "tlg002"): "Varia Historia",
    ("tlg0565", "tlg003"): "Epistulae Rusticae",
    ("tlg0565", "tlg004"): "Fragments",
    # Oppian
    ("tlg0610", "tlg001"): "Halieutica",
    # Babrius
    ("tlg0612", "tlg001"): "Fabulae",
    # Longus
    ("tlg0614", "tlg001"): "Daphnis and Chloe",
    # Chariton
    ("tlg0615", "tlg001"): "Callirhoe",
    # Achilles Tatius
    ("tlg0616", "tlg001"): "Leucippe and Clitophon",
    ("tlg0616", "tlg002"): "Fragments",
    # Hippocrates (tlg0627) — Hippocratic Corpus
    ("tlg0627", "tlg001"): "On Ancient Medicine",
    ("tlg0627", "tlg002"): "On Airs, Waters, Places",
    ("tlg0627", "tlg003"): "Prognostic",
    ("tlg0627", "tlg004"): "On Regimen in Acute Diseases",
    ("tlg0627", "tlg005"): "Epidemics I",
    ("tlg0627", "tlg006"): "Epidemics II",
    ("tlg0627", "tlg007"): "Epidemics III",
    ("tlg0627", "tlg008"): "On Wounds in the Head",
    ("tlg0627", "tlg009"): "On the Surgery",
    ("tlg0627", "tlg010"): "On Fractures",
    ("tlg0627", "tlg011"): "On Joints",
    ("tlg0627", "tlg012"): "Instruments of Reduction",
    ("tlg0627", "tlg013"): "Aphorisms",
    ("tlg0627", "tlg014"): "The Oath",
    ("tlg0627", "tlg015"): "The Law",
    ("tlg0627", "tlg016"): "On the Sacred Disease",
    ("tlg0627", "tlg017"): "On Humors",
    ("tlg0627", "tlg018"): "On the Art",
    ("tlg0627", "tlg019"): "On Breaths",
    ("tlg0627", "tlg020"): "On the Nature of Man",
    ("tlg0627", "tlg021"): "Regimen in Health",
    ("tlg0627", "tlg022"): "On the Nature of Woman",
    ("tlg0627", "tlg023"): "On the Diseases of Women I",
    ("tlg0627", "tlg024a"): "On the Diseases of Women II",
    ("tlg0627", "tlg024b"): "On Sterile Women",
    ("tlg0627", "tlg025"): "On Diseases I",
    ("tlg0627", "tlg026"): "On Diseases II",
    ("tlg0627", "tlg027"): "On Diseases III",
    ("tlg0627", "tlg028"): "On Internal Affections",
    ("tlg0627", "tlg029"): "On Affections",
    ("tlg0627", "tlg030"): "On Places in Man",
    ("tlg0627", "tlg031"): "On the Use of Liquids",
    ("tlg0627", "tlg032"): "On Ulcers",
    ("tlg0627", "tlg033"): "On Hemorrhoids",
    ("tlg0627", "tlg035"): "On Fistulae",
    ("tlg0627", "tlg036"): "On the Excision of the Fetus",
    ("tlg0627", "tlg037"): "On the Nature of the Child",
    ("tlg0627", "tlg038"): "On Generation",
    ("tlg0627", "tlg039"): "On Diseases IV",
    ("tlg0627", "tlg040"): "On the Eight Months' Child",
    ("tlg0627", "tlg041"): "On Superfoetation",
    ("tlg0627", "tlg042"): "On Dentition",
    ("tlg0627", "tlg043"): "On the Glands",
    ("tlg0627", "tlg045"): "On Flesh",
    ("tlg0627", "tlg046"): "On Sevens",
    ("tlg0627", "tlg047"): "On the Heart",
    ("tlg0627", "tlg048"): "On Nutriment",
    ("tlg0627", "tlg049"): "On Sight",
    ("tlg0627", "tlg050"): "On the Physician",
    ("tlg0627", "tlg051"): "On Decorum",
    ("tlg0627", "tlg052"): "Precepts",
    ("tlg0627", "tlg053"): "On Crises",
    ("tlg0627", "tlg055"): "On Critical Days",
    # Pseudo-Apollodorus
    ("tlg0640", "tlg001"): "Bibliotheca",
    # Heliodorus
    ("tlg0643", "tlg001"): "Aethiopica",
    ("tlg0643", "tlg002"): "Fragments",
    # Philostratus
    ("tlg0645", "tlg001"): "Life of Apollonius of Tyana",
    ("tlg0645", "tlg002"): "Lives of the Sophists",
    ("tlg0645", "tlg003"): "Heroicus",
    # Philostratus the Elder
    ("tlg0646", "tlg004"): "Imagines",
    # Parthenius
    ("tlg0658", "tlg001"): "Erotica Pathemata",
    # Diogenes Laertius
    ("tlg0661", "tlg001"): "Lives of Eminent Philosophers",
    ("tlg0661", "tlg002"): "Fragments",
    # Alexander of Aphrodisias
    ("tlg0708", "tlg001"): "Commentary on Aristotle's Metaphysics",
    # Sextus Empiricus
    ("tlg0732", "tlg004"): "Against the Logicians I",
    ("tlg0732", "tlg005"): "Against the Logicians II",
    ("tlg0732", "tlg006"): "Against the Physicists I",
    ("tlg0732", "tlg007"): "Against the Physicists II",
    ("tlg0732", "tlg008"): "Against the Ethicists",
    ("tlg0732", "tlg012"): "Outlines of Pyrrhonism",
    ("tlg0732", "tlgX01"): "Fragments",
    # Porphyry
    ("tlg0751", "tlg034"): "Against the Christians",
    # Colluthus
    ("tlg1126", "tlg003"): "Rape of Helen",
    # Tryphiodorus
    ("tlg1205", "tlg001"): "Taking of Ilios",
    ("tlg1205", "tlg002"): "Fragments",
    # Musaeus
    ("tlg1210", "tlg001"): "Hero and Leander",
    ("tlg1210", "tlg002"): "Fragments",
    # Bion
    ("tlg1216", "tlg001"): "Idylls",
    # Moschus
    ("tlg1220", "tlg001"): "Idylls",
    # Theocritus
    ("tlg1252", "tlg002"): "Idylls",
    # Apollonius Sophista
    ("tlg1271", "tlg001"): "Lexicon Homericum",
    ("tlg1271", "tlg002"): "Fragments",
    # Cornutus
    ("tlg1311", "tlg001"): "Greek Theology",
    # Hermogenes
    ("tlg1337", "tlg003"): "On Types of Style",
    # Aelius Aristides
    ("tlg1389", "tlg001"): "Orations",
    # Maximus of Tyre
    ("tlg1419", "tlg001"): "Orations",
    # Dionysius of Halicarnassus
    ("tlg1443", "tlg004"): "Roman Antiquities 4",
    ("tlg1443", "tlg005"): "Roman Antiquities 5",
    ("tlg1443", "tlg006"): "Roman Antiquities 6",
    ("tlg1443", "tlg007"): "Roman Antiquities 7",
    ("tlg1443", "tlg008"): "Roman Antiquities 8",
    ("tlg1443", "tlg009"): "Roman Antiquities 9",
    ("tlg1443", "tlg010"): "Roman Antiquities 10",
    # Longinus
    ("tlg1447", "tlg001"): "On the Sublime",
    # Aelius Herodianus
    ("tlg1463", "tlg001"): "On General Prosody",
    # Pollux
    ("tlg1484", "tlg001"): "Onomasticon",
    # Harpocration
    ("tlg1487", "tlg001"): "Lexicon of the Ten Orators",
    ("tlg1487", "tlg002"): "Fragments",
    # Artemidorus
    ("tlg1551", "tlg001"): "Oneirocritica",
    ("tlg1551", "tlg002"): "Fragments",
    # Hesychius
    ("tlg1600", "tlg001"): "Lexicon",
    # Numenius
    ("tlg1622", "tlg001"): "Fragments",
    # Cassius Dio
    ("tlg1701", "tlg001"): "Roman History",
    ("tlg1701", "tlg002"): "Fragments",
    # Ps.-Plutarch
    ("tlg1724", "tlg001"): "De Fluviis",
    ("tlg1725", "tlg001"): "Placita Philosophorum",
    # Iamblichus
    ("tlg1765", "tlg003"): "On the Pythagorean Life",
    ("tlg1765", "tlg004"): "Protrepticus",
    ("tlg1765", "tlg005"): "On the Mysteries",
    # Julian
    ("tlg1766", "tlg001"): "Orations",
    # Libanius
    ("tlg1799", "tlg001"): "Orations",
    ("tlg1799", "tlg007"): "Declamations",
    ("tlg1799", "tlg008"): "Epistulae",
    # Didymus
    ("tlg2000", "tlg001"): "Fragments",
    # Athanasius
    ("tlg2001", "tlg038"): "Against the Arians I",
    ("tlg2001", "tlg039"): "Against the Arians II",
    ("tlg2001", "tlg040"): "Against the Arians III",
    ("tlg2001", "tlg041"): "On the Incarnation",
    ("tlg2001", "tlg042"): "Defense Against the Arians",
    ("tlg2001", "tlg043"): "Life of Antony",
    # Clement of Alexandria
    ("tlg2018", "tlg001"): "Protrepticus",
    ("tlg2018", "tlg002"): "Paedagogus",
    ("tlg2018", "tlg003"): "Stromata",
    ("tlg2018", "tlg005"): "Quis Dives Salvetur",
    ("tlg2018", "tlg009"): "Excerpta ex Theodoto",
    ("tlg2018", "tlg010"): "Eclogae Propheticae",
    ("tlg2018", "tlg011"): "Fragments",
    ("tlg2018", "tlg020"): "Fragments",
    ("tlg2018", "tlg021"): "Fragments",
    ("tlg2018", "tlg022"): "Fragments",
    # Hippolytus
    ("tlg2021", "tlg001"): "Refutatio Omnium Haeresium",
    ("tlg2021", "tlg002"): "Contra Noetum",
    ("tlg2021", "tlg003"): "Fragments",
    # Origen
    ("tlg2022", "tlg003"): "Commentary on John",
    ("tlg2022", "tlg007"): "Against Celsus",
    ("tlg2022", "tlg008"): "On First Principles",
    ("tlg2022", "tlg009"): "Commentary on Matthew",
    ("tlg2022", "tlg010"): "Exhortation to Martyrdom",
    ("tlg2022", "tlg011"): "On Prayer",
    ("tlg2022", "tlg060"): "Philocalia",
    # Gregory Thaumaturgus
    ("tlg2023", "tlg002"): "Address to Origen",
    # Methodius
    ("tlg2034", "tlg006"): "Symposium",
    ("tlg2034", "tlg007"): "On the Resurrection",
    ("tlg2034", "tlg014"): "On Free Will",
    ("tlg2034", "tlg015"): "Fragments",
    # Eustathius of Antioch
    ("tlg2036", "tlg001"): "Fragments",
    # Gregory of Nazianzus
    ("tlg2041", "tlg001"): "Orations",
    # John Chrysostom — Homilies
    ("tlg2042", "tlg001"): "Homilies on Genesis",
    ("tlg2042", "tlg005"): "Homilies on the Statues",
    ("tlg2042", "tlg006"): "Homilies on the Incomprehensible Nature of God",
    ("tlg2042", "tlg007"): "Homilies on Lazarus",
    ("tlg2042", "tlg008"): "Against the Anomoeans",
    ("tlg2042", "tlg009"): "Against the Jews",
    ("tlg2042", "tlg010"): "Catecheses",
    ("tlg2042", "tlg011"): "On the Priesthood",
    ("tlg2042", "tlg012"): "Homilies on Matthew",
    ("tlg2042", "tlg013"): "Homilies on John",
    ("tlg2042", "tlg014"): "Homilies on Acts",
    ("tlg2042", "tlg015"): "Homilies on Romans",
    ("tlg2042", "tlg016"): "Homilies on 1 Corinthians",
    ("tlg2042", "tlg017"): "Homilies on 2 Corinthians",
    ("tlg2042", "tlg021"): "Homilies on Ephesians",
    ("tlg2042", "tlg028"): "Homilies on Hebrews",
    ("tlg2042", "tlg029"): "Homilies on the Psalms",
    ("tlg2042", "tlg030"): "Homilies on Isaiah",
    ("tlg2042", "tlg045"): "Letters",
    ("tlg2042", "tlg084"): "De Virginitate",
    # Ps.-Macarius
    ("tlg2048", "tlg001"): "Spiritual Homilies",
    # Didymus the Blind
    ("tlg2050", "tlg001"): "Commentary on the Psalms",
    # Epiphanius
    ("tlg2057", "tlg002"): "Panarion",
    # Ephrem the Syrian
    ("tlg2058", "tlg001"): "Works (Greek)",
    # Cyril of Alexandria
    ("tlg2115", "tlg060"): "Commentary on John",
    # Plotinus — Enneads
    ("tlg2200", "tlg001"): "Enneads I",
    ("tlg2200", "tlg008"): "Enneads (misc.)",
    # Proclus
    ("tlg2371", "tlg001"): "Elements of Theology",
    # Simplicius
    ("tlg2583", "tlg001"): "Commentary on Aristotle's Categories",
    # George Syncellus
    ("tlg2703", "tlg001"): "Ecloga Chronographica",
    # Leontius of Byzantium
    ("tlg2733", "tlg001"): "Contra Nestorianos et Eutychianos",
    # John Philoponus
    ("tlg2768", "tlg001"): "Commentary on Aristotle's Physics",
    ("tlg2768", "tlg002"): "Commentary on Aristotle's De Anima",
    # Photius
    ("tlg2959", "tlg001"): "Bibliotheca",
    ("tlg2959", "tlg002"): "Lexicon",
    ("tlg2959", "tlg005"): "Amphilochia",
    ("tlg2959", "tlg006"): "Letters",
    ("tlg2959", "tlg007"): "Homilies",
    ("tlg2959", "tlg008"): "Contra Manichaeos",
    ("tlg2959", "tlg010"): "Fragments",
    # Michael Psellus
    ("tlg3118", "tlg001"): "Chronographia",
    ("tlg3118", "tlg002"): "Orations",
    # Eustathius of Thessalonica
    ("tlg3135", "tlg001"): "Commentary on the Iliad",
    ("tlg3135", "tlg004"): "Commentary on the Odyssey",
    ("tlg3135", "tlg005"): "Commentary on Dionysius Periegetes",
    # Nicetas Choniates
    ("tlg3156", "tlg001"): "Historia",
    # Methodius of Olympus
    ("tlg4013", "tlg001"): "Symposium",
    ("tlg4013", "tlg003"): "On the Resurrection",
    ("tlg4013", "tlg004"): "On Free Will",
    ("tlg4013", "tlg005"): "Fragments",
    # Eusebius
    ("tlg4015", "tlg001"): "Praeparatio Evangelica",
    ("tlg4015", "tlg002"): "Demonstratio Evangelica",
    ("tlg4015", "tlg003"): "Historia Ecclesiastica",
    ("tlg4015", "tlg004"): "Life of Constantine",
    ("tlg4015", "tlg005"): "Against Marcellus",
    ("tlg4015", "tlg006"): "Ecclesiastical Theology",
    ("tlg4015", "tlg007"): "Onomasticon",
    ("tlg4015", "tlg008"): "Theophania",
    ("tlg4015", "tlg009"): "Chronicon",
    # Cyril of Jerusalem
    ("tlg4016", "tlg001"): "Catecheses",
    ("tlg4016", "tlg002"): "Procatechesis",
    ("tlg4016", "tlg003"): "Mystagogic Catecheses",
    ("tlg4016", "tlg004"): "Letters",
    # Amphilochius of Iconium
    ("tlg4017", "tlg001"): "Orations",
    # Didymus the Blind (alt.)
    ("tlg4018", "tlg001"): "Commentary on Zechariah",
    # Ps.-Athanasius
    ("tlg4019", "tlg001"): "Quaestiones ad Antiochum Ducem",
    ("tlg4019", "tlg003"): "Fragments",
    # Gregory of Nyssa
    ("tlg4020", "tlg001"): "Life of Moses",
    ("tlg4020", "tlg002"): "Catechetical Oration",
    # Nemesius
    ("tlg4021", "tlg002"): "On the Nature of Man",
    # Theodore of Mopsuestia
    ("tlg4024", "tlg001"): "Commentary on the Psalms",
    ("tlg4024", "tlg002"): "Fragments",
    # Nestorius
    ("tlg4027", "tlg001"): "Fragments",
    # Theodoret
    ("tlg4030", "tlg001"): "Church History",
    # Isidore of Pelusium
    ("tlg4031", "tlg002"): "Letters",
    # Mark the Hermit
    ("tlg4033", "tlg003"): "On the Spiritual Law",
    # Nilus of Ancyra
    ("tlg4034", "tlg002"): "De Oratione",
    ("tlg4034", "tlg003"): "Epistulae",
    ("tlg4034", "tlg006"): "Fragments",
    # Ps.-Dionysius
    ("tlg4036", "tlg001"): "On the Divine Names",
    ("tlg4036", "tlg023"): "On the Celestial Hierarchy",
    # Maximus the Confessor
    ("tlg4075", "tlg002"): "Ambigua",
    # Leontius of Jerusalem
    ("tlg4084", "tlg001"): "Contra Nestorianos",
    # Anastasius of Sinai
    ("tlg4089", "tlg003"): "Questions and Answers",
    ("tlg4089", "tlg004"): "Hodegos",
    # Germanus of Constantinople
    ("tlg4090", "tlg001"): "On the Divine Liturgy",
    # John of Damascus
    ("tlg4102", "tlg001"): "Expositio Fidei",
    ("tlg4102", "tlg002"): "Dialectica",
    ("tlg4102", "tlg003"): "Contra Jacobitas",
    ("tlg4102", "tlg004"): "Contra Manichaeos",
    ("tlg4102", "tlg005"): "On the Orthodox Faith",
    ("tlg4102", "tlg006"): "De Haeresibus",
    ("tlg4102", "tlg007"): "Sacra Parallela",
    ("tlg4102", "tlg008"): "De Imaginibus I",
    ("tlg4102", "tlg010"): "De Imaginibus II",
    ("tlg4102", "tlg011"): "De Imaginibus III",
    ("tlg4102", "tlg012"): "De Fide Contra Nestorianos",
    ("tlg4102", "tlg013"): "Contra Acephalos",
    ("tlg4102", "tlg019"): "De Natura Composita",
    ("tlg4102", "tlg020"): "De Duabus Voluntatibus",
    ("tlg4102", "tlg021"): "Institutio Elementaris",
    ("tlg4102", "tlg022"): "Epistula de Hymno Trisagio",
    ("tlg4102", "tlg023"): "De Sancta Trinitate",
    ("tlg4102", "tlg024"): "Fragments",
    ("tlg4102", "tlg034"): "Homilies 1",
    ("tlg4102", "tlg035"): "Homilies 2",
    ("tlg4102", "tlg036"): "Homilies 3",
    ("tlg4102", "tlg037"): "Homilies 4",
    ("tlg4102", "tlg038"): "Homilies 5",
    ("tlg4102", "tlg039"): "Homilies 6",
    ("tlg4102", "tlg040"): "Homilies 7",
    ("tlg4102", "tlg041"): "Homilies 8",
    ("tlg4102", "tlg042"): "Homilies 9",
    ("tlg4102", "tlg043"): "Homilies 10",
    ("tlg4102", "tlg044"): "Homilies 11",
    ("tlg4102", "tlg045"): "Homilies 12",
    ("tlg4102", "tlgX01"): "Dubia 1",
    ("tlg4102", "tlgX02"): "Dubia 2",
    ("tlg4102", "tlgX03"): "Dubia 3",
    # Symeon the New Theologian
    ("tlg4170", "tlg001"): "Catecheses",
    ("tlg4170", "tlg001a"): "Catecheses (alt. A)",
    ("tlg4170", "tlg001b"): "Catecheses (alt. B)",
    ("tlg4170", "tlg001c"): "Hymns",
    ("tlg4170", "tlg001d"): "Chapters",
    # Michael Glycas
    ("tlg4193", "tlg012"): "Annales",
    # Septuagint — additional
    ("tlg0527", "tlg013"): "1 Chronicles",
    ("tlg0527", "tlg014"): "2 Chronicles",
    ("tlg0527", "tlg030"): "Ecclesiastes",
    ("tlg0527", "tlg048"): "Sirach",
    # Scholia
    ("tlg5022", "tlg002"): "Scholia on Pindar",
    ("tlg5026", "tlg007"): "Scholia on the Iliad",
    ("tlg5034", "tlg001a"): "Scholia on Acharnians",
    ("tlg5034", "tlg001b"): "Scholia on Knights",
    ("tlg5034", "tlg001c"): "Scholia on Clouds",
    ("tlg5034", "tlg001d"): "Scholia on Wasps",
    # Anthologies
    ("tlg9004", "tlg001"): "Anthologia Palatina",
    ("tlg9006", "tlg011"): "Anthologia Palatina (app.)",
    ("tlg9019", "tlg001"): "Anthologia Planudea",
    # Theophrastus
    ("tlg0093", "tlg009"): "Characters",
}

# Also generate Plotinus Enneads entries (tlg2200 has many numbered works)
for wc in range(401, 465):
    key = ("tlg2200", f"tlg00{wc}")
    if key not in TITLES:
        ennead = (wc - 400 - 1) // 9 + 4
        tract = (wc - 400 - 1) % 9 + 1
        TITLES[key] = f"Enneads {ennead}.{tract}"
for wc in range(501, 550):
    key = ("tlg2200", f"tlg00{wc}")
    if key not in TITLES:
        ennead = 5 + (wc - 501) // 9
        tract = (wc - 501) % 9 + 1
        TITLES[key] = f"Enneads {ennead}.{tract}"

# ── Apply updates ───────────────────────────────────────────────

# 1. Fix author names
author_updated = 0
for code, name in AUTHORS.items():
    cur.execute(
        "UPDATE works SET author = ? WHERE author_code = ? AND (author = ? OR author LIKE 'tlg%' OR author LIKE 'stoa%')",
        (name, code, code),
    )
    author_updated += cur.rowcount

# 2. Fix work titles
title_updated = 0
for (ac, wc), title in TITLES.items():
    cur.execute(
        "UPDATE works SET title = ? WHERE author_code = ? AND work_code = ? AND (title LIKE 'tlg%' OR title LIKE 'stoa%')",
        (title, ac, wc),
    )
    title_updated += cur.rowcount

conn.commit()

# ── Report ──────────────────────────────────────────────────────
print(f"Updated {author_updated} author names, {title_updated} work titles.")

# Check remaining
cur.execute("SELECT COUNT(*) FROM works WHERE author LIKE 'tlg%' OR author LIKE 'stoa%'")
remaining_authors = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM works WHERE title LIKE 'tlg%' OR title LIKE 'stoa%'")
remaining_titles = cur.fetchone()[0]
print(f"Remaining unmapped: {remaining_authors} authors, {remaining_titles} titles")

if remaining_titles > 0:
    cur.execute("""
        SELECT DISTINCT author_code, work_code, author, title
        FROM works WHERE title LIKE 'tlg%' OR title LIKE 'stoa%'
        ORDER BY author_code, work_code
        LIMIT 30
    """)
    print("\nStill unmapped (first 30):")
    for ac, wc, a, t in cur.fetchall():
        print(f"  {a}: {t}  ({ac}/{wc})")

conn.execute("PRAGMA optimize")
conn.close()
print("\nDone!")
