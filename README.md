# Căutare apartament

Aplicație pentru extragerea informațiilor relevante din anunțuri imobiliare și,
ulterior, identificarea altor anunțuri care par să aparțină aceluiași proprietar.

În această etapă, interfața acceptă un link sau textul copiat al unui anunț și
confirmă primirea inputului. Analiza și căutarea nu sunt încă implementate.

## Tehnologii

- Python 3.12
- Streamlit pentru interfața web
- python-dotenv, requests și Beautiful Soup 4 ca dependențe pentru etapele următoare

## Instalare

Din directorul proiectului, folosind Python 3.12:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Pe Windows, activează mediul virtual cu `.venv\Scripts\activate`.

Fișierul `.env.example` conține doar un exemplu comentat, fără chei reale.
Nu sunt necesare variabile de mediu pentru această etapă. Dacă ulterior ai nevoie
de configurare locală, copiază-l în `.env`; `.env` este ignorat de Git.

## Pornire

Cu mediul virtual activat, din directorul proiectului:

```bash
streamlit run app.py
```

Alege „Link anunț” sau „Text anunț”, introdu conținutul și apasă „Analizează”.

## Structură

```text
app.py
src/
    __init__.py
    extractors/__init__.py
    analyzers/__init__.py
    search/__init__.py
    utils/__init__.py
tests/
    __init__.py
.env.example
requirements.txt
```

Pachetele din `src/` și `tests/` sunt pregătite pentru dezvoltarea ulterioară.

## Verificarea sintaxei

```bash
python -m compileall -q app.py src tests
```
