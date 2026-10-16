#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Profil zawodowy: dane i inżynieria AI (Applied Data Science / AI Eng.).

Profil zbudowany pod kompetencje: Data Wrangling, Data Analysis,
Data Analytics, Data Processing, Data Integration, Data Science,
Python, Remote Debugging, JEE, Back-End, Full-Stack, aplikacje mobilne.

PODZIAŁ NA OBSZARY RDZENIOWE I WSPIERAJĄCE — tak samo jak w profilu
kultury, i z tego samego powodu: bez niego ofert „dopasowanych” jest
kilkakrotnie więcej, bo w IT prawie każde ogłoszenie wymienia Pythona,
SQL albo chmurę. Obszar wspierający sam nie kwalifikuje oferty —
samo „SQL” w wymaganiach nie czyni z ogłoszenia roli dla analityka
danych.

Rdzeniowe (mogą zakwalifikować): dane/analityka, data engineering,
AI/ML, Python, backend/JEE, full-stack, mobile.
Wspierające (tylko podbijają wynik): chmura, bazy danych, DevOps/CI,
BI/wizualizacja, testy.
"""

from typing import List, Tuple

LABEL = "Dane i AI (Applied DS / AI Engineering)"
SLUG = "it"

DESCRIPTION = (
    "Data science i analityka, inżynieria danych, AI/ML, Python, "
    "backend/JEE, full-stack, aplikacje mobilne."
)

# Wagi jak w profilu kultury: trafienie w tytule liczy się podwójnie
# (mnożnik jest w profile_match), więc 5 = obszar wiodący, 3 = pomocniczy.
PROFILE_KEYWORDS: List[Tuple[str, int, Tuple[str, ...]]] = [
    ("dane / analityka", 5, (
        "data scien", "data analy", "analityk danych", "analiza danych",
        "data wrangl", "data processing", "przetwarzanie danych",
        "data integration", "integracja danych", "data quality",
        "statyst", "analytics engineer", "quantitative",
    )),
    ("inżynieria danych", 5, (
        "data engineer", "inżynier danych", "inzynier danych",
        "etl", "elt", "data pipeline", "data platform", "hurtowni danych",
        "data warehouse", "lakehouse", "spark", "airflow", "dbt",
        "kafka", "databricks", "snowflake",
    )),
    ("AI / uczenie maszynowe", 5, (
        "machine learning", "uczenie maszynowe", "deep learning",
        "ai engineer", "mlops", "ml engineer", "sztuczn inteligencj",
        "nlp", "computer vision", "llm", "generative ai", "genai",
        "data mining", "mlflow",
    )),
    ("Python", 5, (
        "python", "pyspark", "pandas", "numpy", "scikit", "fastapi",
        "django", "flask", "jupyter",
    )),
    ("backend / JEE", 5, (
        "backend", "back-end", "back end", "java develop", "jee",
        "j2ee", "spring boot", "spring framework", "microservice",
        "mikroserwis", "rest api", "api develop",
    )),
    ("full-stack", 5, (
        "full stack", "full-stack", "fullstack",
    )),
    ("aplikacje mobilne", 5, (
        "android develop", "ios develop", "mobile develop",
        "aplikacji mobiln", "react native", "flutter", "kotlin develop",
    )),
    # --- obszary WSPIERAJĄCE: podbijają wynik, same nie kwalifikują ---
    ("chmura / infrastruktura", 3, (
        "aws", "azure", "google cloud", "gcp", "kubernetes", "terraform",
        "docker", "cloud engineer",
    )),
    ("bazy danych / SQL", 3, (
        "sql", "postgres", "oracle", "mysql", "mongodb", "nosql",
        "bigquery", "redshift",
    )),
    ("BI / wizualizacja", 4, (
        "power bi", "tableau", "looker", "qlik", "business intelligence",
        "raportowanie", "dashboard",
    )),
    ("DevOps / CI", 2, (
        "devops", "ci/cd", "jenkins", "gitlab ci", "github actions",
        "sre ", "platform engineer",
    )),
]

# Wykluczenia — liczone TYLKO z tytułu (jak w profilu kultury).
#
# Dwie pułapki specyficzne dla IT, obie potwierdzone w danych:
#  * „Programista-Operator CNC”, „Programista Robotów Przemysłowych” —
#    CBOP zwraca je dla frazy „programista”; to automatyka przemysłowa,
#    nie wytwarzanie oprogramowania,
#  * role sprzedażowo-rekrutacyjne wokół IT („IT Recruiter”, „Sales
#    Engineer”, „Account Manager”) mają w opisie pełno technologii.
EXCLUDE_KEYWORDS: Tuple[str, ...] = (
    "cnc", "operator cnc", "robotów przemysłowych", "robotow przemyslowych",
    "automatyk", "elektryk", "mechanik", "spawacz", "tokarz", "frezer",
    "recruiter", "rekruter", "sourcer", "account manager",
    "sales engineer", "przedstawiciel handlowy", "sprzedawca",
    "księgow", "ksiegow", "kadr", "sprzątan", "sprzatan", "ochrona",
    "kierowca", "magazynier", "kurier", "nauczyciel",
    "telemarketer", "call center", "obsługi klienta", "obslugi klienta",
    # Analityk z INNEJ dziedziny. Sam filtr homonimu nie wystarcza, bo
    # opis takiej oferty często zawiera „analiza danych” i „SQL”, co
    # podbijało wynik („Analityk kredytowy” wychodził jako dopasowanie).
    "analityk kredytow", "analityk ubezpieczen", "analityk finansow",
    "analityk biznesow", "analityk sprzedaz", "analityk ryzyka",
)

# Oferty wiarygodne, ale wymagające innego profilu niż aplikacyjny —
# degradowane do „może pasować”, nie wykluczane.
#
# Czysta inżynieria infrastruktury (SRE, administracja) i czysty front-end
# są pokrewne, lecz to inna specjalizacja niż Applied DS / AI Engineering.
# Decyzję o aplikowaniu zostawiamy człowiekowi — porządkujemy kolejność.
DEMOTE_KEYWORDS: Tuple[str, ...] = (
    "administrator", "helpdesk", "help desk", "support engineer",
    "service desk", "l1", "l2", "frontend develop", "front-end develop",
    "ui develop", "wordpress", "embedded", "firmware",
)

# Obszary RDZENIOWE — tylko one mogą samodzielnie zakwalifikować ofertę.
CORE_AREAS: Tuple[str, ...] = (
    "dane / analityka",
    "inżynieria danych",
    "AI / uczenie maszynowe",
    "Python",
    "backend / JEE",
    "full-stack",
    "aplikacje mobilne",
    # BI jest obszarem RDZENIOWYM, bo „Data Analytics” to jedna
    # z wymienionych kompetencji. Bez tego „Senior Power BI Engineer”
    # wypadał jako niedopasowany, mimo że to praca na danych.
    "BI / wizualizacja",
)

# Pracodawcy, przy których ogólny tytuł i tak oznacza mocne trafienie.
#
# Analogia do ``PREFERRED_EMPLOYERS`` w profilu kultury (tam ASP ratowała
# ofertę o tytule „Asystent w grupie badawczo-dydaktycznej”). Tu: firmy
# i jednostki, których PROFIL DZIAŁALNOŚCI to dane/AI, więc ogólne
# „Software Engineer” u nich znaczy więcej niż gdzie indziej.
PREFERRED_EMPLOYERS: Tuple[str, ...] = (
    "deepsense", "addepto", "databricks", "snowflake", "nvidia",
    "openai", "anthropic", "hugging face", "datawalk",
    "instytut", "uniwersytet", "akademia górniczo", "agh",
    "politechnik", "centrum badawcz", "laboratorium",
)

# Homonimy kontekstowe — w profilu kultury rozstrzygały „grafik”
# (zawód vs harmonogram). W IT odpowiednikiem jest „analityk”: bywa
# analitykiem BIZNESOWYM albo KREDYTOWYM, co nie jest tym profilem.
# Okno kontekstu sprawdza profile_match (SCHEDULE_CONTEXT_WORDS).
SCHEDULE_CONTEXT_WORDS: Tuple[str, ...] = (
    "kredytow", "ubezpiecze", "windykacj", "finansow sprawozdaw",
    "biznesow w obszarze sprzedaz",
)

# Frazy typu placówki, które myliłyby dopasowanie (odpowiednik
# „Poradni Psychologiczno-Pedagogicznej” z profilu kultury).
# Agencje pracy wymieniają w ogłoszeniu technologie klienta, co zawyżało
# wynik ofert niezwiązanych z profilem.
INSTITUTION_NOISE: Tuple[str, ...] = (
    "agencja pracy", "agencji pracy", "kraz", "praca tymczasowa",
    "outsourcing kadrowy",
)

# Progi interpretacji wyniku. Wyższe niż w profilu kultury, bo ogłoszenia
# IT są dłuższe i wymieniają po kilkanaście technologii — przy progu 8
# niemal każda oferta IT stawałaby się „mocnym trafieniem”.
# Jedno trafienie RDZENIOWE w tytule daje 10 punktów (waga 5 x2 za tytuł),
# i to ma wystarczać: „Data Engineer”, „Senior Java Developer” czy
# „Android Developer” są jednoznaczne same z siebie. Próg 12 wymagał dwóch
# obszarów i degradował je do „może pasować”.
SCORE_STRONG = 10
SCORE_WEAK = 5
