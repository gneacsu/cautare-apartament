# Căutare apartament

Aplicație personală în română: de la un anunț al unui agent la posibile anunțuri ale
proprietarului aceluiași apartament de vânzare, în București. **SerpApi caută pe Google,
Gemini interpretează și compară, Google Lens este folosit manual în browser.**
Identificarea unui proprietar declarat nu verifică dreptul de proprietate sau autorul
primei publicări.

## Instalare pe Windows (Python 3.12)

Descarcă proiectul și deschide PowerShell în directorul care conține `app.py`.
Într-un director nou creează un mediu virtual nou; nu copia `.venv` din altă versiune.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Creează `.env` **lângă `app.py`, nu în `.venv`**. Dacă există deja, păstrează cheia
Gemini și adaugă cheia SerpApi; nu suprascrie fișierul cu un exemplu gol.

```powershell
# Numai dacă nu există deja .env:
Copy-Item .env.example .env
notepad .env
```

Completează local:

```dotenv
GEMINI_API_KEY=cheia_ta_reala_Gemini
SERPAPI_API_KEY=cheia_ta_reala_SerpApi
GEMINI_MODEL=gemini-3.6-flash
GEMINI_THINKING_LEVEL=medium
```

Valorile de mai sus pentru chei sunt exemple, nu credențiale funcționale. Nu publica
cheile în chat, capturi sau Git. Variabilele de mediu existente au prioritate față de
`.env`. Repornește procesul după modificarea configurării.

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Oprire: **Ctrl+C** în terminal. Repornire: aceeași comandă. Cu mediul activat:

```console
streamlit run app.py
```

Pe Linux/macOS: `python3.12 -m venv .venv`, `source .venv/bin/activate`,
`python -m pip install -r requirements.txt`, apoi `streamlit run app.py`.

## Conturi și chei

- **SerpApi:** [cont și cheie](https://serpapi.com/manage-api-key),
  [planuri](https://serpapi.com/pricing). Contul trebuie să aibă căutări disponibile.
  Aplicația folosește endpointul Google organic, nu Google Lens API.
- **Gemini Developer API:** [Google AI Studio](https://aistudio.google.com/apikey).
  Creează/selectează proiectul, generează cheia și verifică disponibilitatea modelului,
  [cotele](https://ai.google.dev/gemini-api/docs/rate-limits) și
  [tarifele](https://ai.google.dev/gemini-api/docs/pricing). Abonamentul aplicației
  Gemini nu este echivalent cu acces sau credit API.
- **Google Lens:** folosit manual în browser, fără cheie în această aplicație.
- **Facebook:** contul personal, numai pentru căutările pe care le faci tu în grupurile
  la care ai acces. Aplicația nu se autentifică și nu citește grupuri private.

SerpApi se contorizează separat de tokenii Gemini. Nu afișăm prețuri neverificate și
nu există un plafon monetar implementat. Nu se efectuează apeluri API la simpla pornire
sau la afișarea unui jurnal. Butoanele de analiză, continuare, comparație și transcriere
pot genera consum.

## Fluxul complet

1. Introdu URL-ul și/sau descrierea. Dacă sunt ambele, textul manual are prioritate.
   Manualul funcționează fără accesarea paginii. Poți încărca separat fotografii.
2. Apasă **Caută proprietarul**. Citirea inițială, extragerea și căutările rulează într-un
   fir de lucru; interfața continuă să afișeze progresul și fotografiile disponibile.
3. Fotografia extrasă sau încărcată poate fi folosită imediat în Lens. În Chrome:
   click dreapta pe imagine → Caută cu Google Lens. Alternativ, deschide fotografia
   sau Lens și încarcă o captură decupată. Nu trimitem automat imagini către Lens.
   Încearcă prima imagine, apoi alte două camere dacă nu apar rezultate utile.
4. Dacă anunțul de referință are autor declarat proprietar, căutarea se oprește.
   „Comision 0” singur nu este dovadă. O copie pe agregator nu face agregatorul proprietar.
5. SerpApi caută expresii exacte, Facebook public (a doua direcție), caracteristici,
   portaluri, variante fără diacritice și fragmente mai scurte. Prețul nu este obligatoriu.
   Fiecare primă pagină este explorată înaintea paginării. După fiecare căutare este
   comparat un lot mic, pentru a găsi devreme o potrivire fără a epuiza runda pe o sursă.
6. URL-urile sunt deduplicate, inclusiv după redirecționare. Paginile sunt citite prin
   HTTP/HTML și JSON-LD. Linkurile etichetate explicit ca sursă originală pot fi urmărite.
   Indiciile textuale noi observate în copii probabile pot genera câteva căutări suplimentare.
7. Gemini compară fiecare candidat; codul verifică schema, citatele și contradicțiile.
   Se păstrează prețul fiecărei apariții. Fotografiile accesibile sunt comparate local
   prin identitatea pixelilor și o euristică de asemănare; nu este recunoaștere vizuală
   semantică. Filigranele, decupările sau schimbările de unghi pot împiedica potrivirea.
8. Linkurile descoperite manual în Lens/Facebook pot fi adăugate în aceeași analiză.
   În timpul unei runde poți completa câmpurile; comparația candidatului se pornește
   după terminarea sau oprirea rundei. Pentru postări inaccesibile adaugă text sau capturi.
   **Transcrie capturile cu Gemini** citește textul vizibil; verifică și corectează
   transcrierea înainte de comparare. Poți adăuga separat fotografiile candidatului.
9. O potrivire susținută cu un proprietar declarat oprește căutarea. Materialul introdus
   manual este etichetat explicit și nu este prezentat ca pagină verificată independent.
10. **Oprește și păstrează progresul** se aplică după cererea în curs. **Continuă căutarea**
    reia pașii rămași, fără a repeta extracția, căutările sau comparațiile deja finalizate.
    Dacă au rămas pagini dincolo de profunzimea inițială, continuarea permite încă un nivel,
    până la cinci pagini/interogare. **Reia o analiză salvată** funcționează și după restart.
11. **Fișa apartamentului** permite corectarea localității, zonei, adresei, camerelor,
    suprafeței, tipului suprafeței, etajului și tranzacției. Corectarea invalidează
    comparațiile și planul; paginile citite rămân salvate. Reanalizarea poate genera cost.
12. **Verificare nouă** separă complet intrările și rezultatele; jurnalul vechi rămâne local.

## Stări și limite reale

- „Am găsit posibile anunțuri ale proprietarului.”: există dovezi de potrivire și autor.
- „Nu am găsit un anunț al proprietarului în sursele verificate.”: planul s-a terminat,
  fără candidați neclarificați. Nu este o afirmație despre întregul internet.
- „Nu am putut finaliza verificarea.”: lipsă cheie, eroare API, timp, paginare rămasă,
  conținut inaccesibil sau dovezi insuficiente. Pașii finalizați rămân salvați.

Un HTTP 200 nu dovedește potrivirea. Snippetul Google nu este pagina originală.
Imaginile identice pot fi copiate; nu dovedesc autorul. Asemănarea locală a fotografiilor
nu produce singură un rezultat pozitiv. Nu atribuim procente de certitudine.

Extractorul actual citește HTML și JSON-LD; **nu execută JavaScript și nu ocolește login,
CAPTCHA sau blocaje**. Paginile dinamice și galeriile încărcate exclusiv prin JavaScript
necesită text/fotografii manuale. Nu există un browser automatizat în această versiune.
Un serviciu de căutare nu poate descoperi o postare neindexată sau dintr-un grup privat.

## Configurare

Toate setările sunt în `src/config.py`; exemplul complet este `.env.example`.

| Variabilă | Implicit | Sens |
|---|---:|---|
| `MAX_OUTPUT_TOKENS` | 8192 | Plafon per apel, include gândirea; până la 16384 |
| `GEMINI_THINKING_LEVEL` | medium | minimal / low / medium / high, în funcție de model |
| `COMPARISON_BATCH_SIZE` | 3 | Surse comparate într-un apel |
| `ANALYSIS_SECONDS` | 900 | Durată pe rundă, reluabilă; până la 3600 |
| `HTTP_SECONDS` | 12 | Timeout pentru pagini și imagini |
| `SEARCH_SECONDS` | 60 | Timeout per cerere SerpApi |
| `PAGES_PER_QUERY` | 2 | Profunzime inițială, folosind paginarea returnată de SerpApi |
| `MAX_FOLLOWUP_QUERIES` | 4 | Căutări suplimentare din indicii observate |
| `MAX_INPUT_CHARS` | 16000 | Limită intrare; până la 32000 |
| `MAX_CANDIDATE_CHARS` | 8000 | Text extras per candidat; până la 16000 |
| `MAX_IMAGES_PER_LISTING` | 6 | Fotografii încercate pentru comparația locală |

**Nu există plafon total de tokeni, de candidați sau de apeluri AI în noul flux SerpApi.**
Vechile `MAX_CANDIDATES`, `MAX_SEARCHES`, `MAX_AI_CALLS`, `SEARCH_RESULTS_PER_CALL`
nu mai sunt citite din `.env` pentru acest flux; le poți șterge. Planul finit,
paginarea, timeouturile și reluările explicite împiedică buclele fără sfârșit.
Un `MAX_TOKENS` este o eroare per apel: păstrează lotul pentru reîncercare, fără rezultat
negativ fals. Poți mări plafonul per apel sau reduce lotul, apoi reporni și continua jurnalul.

## Jurnal și măsurarea consumului

`local_data/<id>.json` este scris atomic după fiecare etapă finalizată. Păstrează intrarea,
fișa, sursele, datele observate, prețurile distincte, interogările, coada rămasă, rezultatele,
consumul, corectările și diagnosticele. Nu salvează cheile, HTML-ul integral sau fișierele
fotografiilor. Sunt păstrate URL-uri și amprente de imagini, iar imaginile încărcate trebuie
selectate din nou după restart pentru vizualizare. Jurnalele conțin textul anunțurilor.

Diagnosticul descărcabil exclude URL-uri, interogări și texte. În **Reia o analiză salvată**,
**Calculează consumul analizelor salvate** afișează medie, mediană și maxim, separând
analizele finalizate de cele nefinalizate. Nu estimează eficacitatea căutării.

Pentru pilot, verifică 15–20 de cazuri, inclusiv perechi cunoscute agent–proprietar și
apartamente similare dar diferite. Aplicația primește numai anunțul agentului. Notează
separat: descoperirea linkului, accesul, potrivirea, autorul, timpul și consumul. Testele
simulate nu măsoară rata de găsire pe internet.

## Teste

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app.py src tests
```

Suita implicită folosește răspunsuri simulate: protocol SerpApi, erori/cote, paginare,
reluare fără apeluri duplicate, Facebook manual, prețuri diferite, citate inventate,
proprietăți diferite, fotografii, anulare și interacțiuni Streamlit. Include și regresii
pentru vechiul flux Gemini. Cele două teste reale sunt omise implicit.

Pentru a efectua explicit **o căutare SerpApi și o extragere Gemini**, cu posibil cost:

```powershell
$env:RUN_LIVE_TESTS="1"
.\.venv\Scripts\python.exe -m pytest tests/test_live.py -q
Remove-Item Env:RUN_LIVE_TESTS
```

Acestea verifică accesul API, nu identificarea unui proprietar real. Pentru o verificare
completă, rulează aplicația cu un anunț cunoscut și inspectează sursele.

## Organizare

`app.py` gestionează interfața și progresul; `src/service.py` operațiile și lucrătorul
asincron; `src/analyzers/pipeline.py` planul reluabil; `src/search/serpapi.py` integrarea
căutării; `src/search/plan.py` interogările; `src/analyzers/provider.py` toate apelurile
Gemini; `src/extractors/pages.py` citirea paginilor; `src/extractors/images.py` fotografiile;
`src/analyzers/verification.py` regulile de dovezi; `src/utils/journal.py` salvarea.
Nu este necesară o bază de date sau un server separat.

Contractele și documentația consultată sunt în [docs/integration.md](docs/integration.md).
