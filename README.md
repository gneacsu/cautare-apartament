# Căutare apartament

Aplicație personală în limba română pentru a găsi posibile anunțuri publicate de
proprietarii unor apartamente **de vânzare, cu 2–3 camere, în București**.
Pornește de la un singur link sau o descriere copiată. Compară fragmente distinctive
și caracteristici, păstrând separat potrivirea proprietății și clasificarea autorului.

## Instalare pe Windows

Ai nevoie de Python 3.12, acces la internet și o cheie pentru **Gemini Developer API**.
Din PowerShell, în directorul proiectului:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Dacă `.env` există deja, păstrează-l; nu îl suprascrie cu exemplul.
Completează `GEMINI_API_KEY` în editorul local. Nu publica cheia în Git sau în chat.

Pornire, fără a modifica politica PowerShell pentru executarea scripturilor:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Cu mediul virtual deja activat, comanda echivalentă este:

```console
streamlit run app.py
```

Pe Linux/macOS:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
# Numai dacă nu ai deja .env:
cp .env.example .env
# Editează local .env și completează cheia.
streamlit run app.py
```

## Acces Gemini și costuri

1. Accesează [Google AI Studio](https://aistudio.google.com/apikey) cu contul Google.
2. Selectează sau creează proiectul și generează o cheie pentru Gemini API.
3. Consultă accesul, cotele și condițiile proiectului tău. Disponibilitatea nivelului
   gratuit, a modelelor și a Google Search depinde de oferta și contul Google.
4. Pune cheia în `GEMINI_API_KEY` din `.env` sau în variabila de mediu cu același nume.
   Variabilele deja existente au prioritate față de `.env`.
5. Modelul implicit este `gemini-3.6-flash`, cu nivel de gândire `medium`.
   Pentru configurare explicită, adaugă în `.env`:

   ```env
   GEMINI_MODEL=gemini-3.6-flash
   GEMINI_THINKING_LEVEL=medium
   ```

   Nivelurile acceptate sunt `minimal`, `low`, `medium`, `high`. Repornește aplicația
   după modificarea `.env`. O variabilă de mediu existentă are prioritate față de fișier.
   Verifică disponibilitatea modelului în proiectul tău înaintea utilizării reale.

Un abonament pentru aplicația Gemini nu dovedește acces sau credit pentru API.
Utilizarea poate include costuri pentru tokenii de intrare/ieșire și pentru
**grounding cu Google Search**, în funcție de model și nivelul de facturare.
Consultă [tarifele Google](https://ai.google.dev/gemini-api/docs/pricing) și
[cotele](https://ai.google.dev/gemini-api/docs/rate-limits) înainte de activarea
facturării. Nu există un buget financiar aprobat sau un plafon monetar implementat.
Limitele tehnice de mai jos reduc consumul, dar nu garantează un cost fix.

Nu includem tarife numerice neverificate. Modelul și nivelul de gândire au fost
verificate în documentația oficială Google, iar contractul SDK în referința API;
sursele sunt în
[docs/gemini-integration.md](docs/gemini-integration.md).

## Utilizare

1. Introdu linkul și/sau descrierea copiată. Dacă sunt completate ambele, descrierea
   manuală are prioritate, iar linkul este păstrat ca referință.
2. Apasă **Caută proprietarul**. Pagina este citită prin HTTP, iar Gemini interpretează
   descrierea. Dacă pagina este blocată, copiază descrierea în câmpul alternativ.
3. Dacă autorul anunțului introdus se declară proprietar, căutarea se oprește imediat.
   Pentru input manual, aplicația precizează că declarația nu a fost verificată pe site.
4. Altfel, încearcă până la șase variante: fragmente exacte, un alt fragment fără
   filtre suplimentare, variante fără diacritice, fragmente scurtate, caracteristici
   și o căutare țintită pe Facebook public. Prețul nu este obligatoriu în căutări
   și nu exclude singur o potrivire. Fără fragmente distinctive se folosesc doar
   variante bazate pe caracteristicile disponibile.
5. Primești linkuri justificate sau una dintre stările:
   - „Am găsit posibile anunțuri ale proprietarului.”
   - „Nu am găsit un anunț al proprietarului în sursele verificate.”
   - „Nu am putut finaliza verificarea.”
6. Pentru alt anunț apasă **Verificare nouă**. Schimbarea intrării șterge rezultatul
   anterior din interfață. O reîncercare necesită apăsarea explicită a butonului.

Intrările cu informații lipsă sunt acceptate. Nu deducem orașul sau camerele numai
din obiectivul aplicației. Un anunț identificat explicit ca închiriere este semnalat
ca fiind în afara fluxului de vânzare. Nu se accesează conturi sau grupuri private.

## Verificarea concluziilor

- URL-urile de căutare vin numai din `grounding_metadata.grounding_chunks`, nu din
  linkuri inventate în textul generat. Redirecționările HTTP sunt verificate separat.
- O pagină accesibilă nu este automat o potrivire. AI compară proprietățile, apoi
  codul verifică citatele, contradicțiile și existența unor indicii suficiente.
- O potrivire pozitivă necesită o declarație de proprietar susținută prin citate,
  o pagină citită și fie un fragment distinctiv comun de minimum cinci cuvinte,
  fie coincidența zonei/adresei, suprafeței de același tip, etajului și camerelor.
  Aceasta este o regulă conservatoare de triere, **nu o metodă statistică validată**.
- Diferențele de camere, tranzacție sau localitate sunt verificate și în cod.
  AI trebuie să semnaleze diferențele materiale de adresă, etaj și suprafață;
  câmpurile lipsă nu sunt contradicții. Suprafața utilă și cea construită rămân distincte.
- „Nu colaborez cu agenții” nu este acceptat drept dovadă că autorul este agent.
  Un agregator poate reproduce o declarație de proprietar fără a fi proprietarul.
- Sursele inaccesibile și rezumatele de căutare nu sunt rezultate verificate.
  Candidații relevanți, inclusiv Facebook public, apar separat pentru verificare manuală.
- O potrivire verificată poate fi afișată chiar dacă alte pagini sunt inaccesibile,
  cu precizarea limitării. Fără potriviri și cu surse relevante neverificabile, starea
  este incompletă. Absența rezultatelor nu înseamnă că anunțul nu există.
- La atingerea plafonului de candidați, apeluri, timp sau variante de căutare,
  fără o potrivire verificată, starea este incompletă: „Căutarea a fost limitată;
  pot exista surse relevante neverificate.” Nu este afișat un fals rezultat negativ.
  Poți mări plafonul indicat și relua analiza; reluarea pornește o nouă verificare,
  fără a reutiliza apelurile vechi, și poate genera costuri noi.
- Nu se atribuie procente, nu se confirmă dreptul de proprietate și nu se declară
  un „anunț original” pe baza datei mai vechi.

## Configurare și limite

Configurația este centralizată în `src/config.py`; `.env.example` arată suprascrierile.

| Setare | Implicit | Rol |
| --- | ---: | --- |
| `ANALYSIS_SECONDS` | 600 | Bugetul de timp al fluxului și timeoutul rămas pentru API; maxim 1200 |
| `HTTP_SECONDS` | 12 | Timeout pentru accesarea unei pagini |
| `MAX_INPUT_CHARS` | 16000 | Limita descrierii de intrare; maxim 32000 |
| `MAX_CANDIDATE_CHARS` | 8000 | Text transmis pentru fiecare candidat; maxim 16000 |
| `MAX_CANDIDATES` | 20 | Numărul total de pagini candidate încercate; maxim 60 |
| `MAX_SEARCHES` | 6 | Maximum șase variante/apeluri Gemini cu Google Search |
| `SEARCH_RESULTS_PER_CALL` | 8 | Numărul de rezultate cerut per apel de căutare; maxim 12 |
| `MAX_AI_CALLS` | 20 | Plafon comun pentru extragere, căutări și toate loturile de comparație; maxim 40 |
| `COMPARISON_BATCH_SIZE` | 3 | Cel mult trei surse comparate într-un apel; configurabil între 1 și 4 |
| `MAX_OUTPUT_TOKENS` | 8192 | Plafon total per apel, inclusiv tokenii de gândire; configurabil între 1000 și 16384 |

O singură încercare per apel (`HttpRetryOptions(attempts=1)`), fără retry automat.
Candidații sunt citiți și comparați progresiv, în loturi mici. Aplicația se oprește
după un lot cu potriviri verificate, înainte de a citi următorul lot sau de a începe
următoarea variantă de căutare. Limita lotului nu reduce plafonul total de candidați.
Metadatele Google pot conține mai multe surse decât numărul cerut; programul respectă
plafonul total `MAX_CANDIDATES`. Nivelurile mai mari de acoperire pot implica mai
multe apeluri și costuri decât configurația anterioară.
Modelul primește explicit `thinking_level=MEDIUM` prin SDK. Nivelul de gândire
nu este un număr fix de tokeni și poate crește consumul și durata. Plafonul de
8.192 de tokeni include gândirea: dacă este epuizat, diagnosticul arată `MAX_TOKENS`
și tokenii de gândire raportați. Pentru a reduce consumul de raționament poți seta
`GEMINI_THINKING_LEVEL=low`; modificarea `MAX_OUTPUT_TOKENS` trebuie făcută în
cunoștință de cauză, deoarece permite răspunsuri mai costisitoare.
Descărcările sunt limitate la 2 MB
per pagină și cel mult trei redirecționări. Nu există căutare în fundal sau buclă nelimitată.

**Un apel Google Search poate declanșa mai multe interogări interne.** API-ul folosit
nu oferă aici un plafon contractual pentru numărul lor. Limităm apelurile aplicației,
înregistrăm interogările raportate și utilizarea tokenilor. Timeoutul limitează
operațiile clientului; nu reprezintă o garanție de anulare a facturării pe server.

## Jurnal local și date

Fiecare analiză este salvată atomic într-un fișier `local_data/<identificator>.json`.
Aceste fișiere constituie jurnalul local, fără server de baze de date. Conțin inputul,
data UTC, starea, rezultatele și evaluările candidaților, sursele citite, dovezile,
prețul fiecărei apariții, interogările și utilizarea raportată de Gemini.

Se păstrează textul extras limitat, nu întregul HTML al paginilor. Excepția este
widgetul oficial de sugestii Google Search, primit în metadatele API și afișat în
iframe. Cheia API nu face parte din structura jurnalului. `.env` și `local_data/`
sunt ignorate de Git. Jurnalul rămâne local până îl ștergi manual; nu există tablou
de bord sau sincronizare. O eroare de salvare nu ascunde rezultatul analizei.

Textele analizate sunt trimise către Gemini; fragmentele sunt folosite pentru
căutarea Google. Verifică termenii de utilizare a datelor pentru nivelul API ales.

## Organizare

```text
app.py                         interfața Streamlit
src/config.py                  modelul și limitele
src/models.py                  structuri Pydantic validate
src/service.py                 analiza și salvarea jurnalului
src/extractors/pages.py         HTTP și extragerea HTML
src/analyzers/provider.py       singurul modul de integrare Gemini
src/analyzers/workflow.py       etapele și limitele analizei
src/analyzers/verification.py   verificările deterministe ale dovezilor
src/search/queries.py           strategia de căutare
src/utils/                     URL-uri, text și jurnal
tests/                         teste simulate și test real opțional
```

## Verificări

Instalează dependențele pentru dezvoltare și rulează testele pe Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app.py src tests
.\.venv\Scripts\python.exe -m pip check
```

Testele simulate acoperă prețuri diferite, proprietăți diferite cu texte similare,
refuzul colaborării cu agenții, copii de agregator, input manual după o pagină
inaccesibilă, erori API, două analize succesive, citate/URL-uri fabricate,
limitele de apeluri, jurnalizarea și interfața. Un transport HTTP simulat verifică
și serializarea cererilor prin SDK-ul Google instalat.
Sunt verificate și găsirea unui candidat după primii șase, o potrivire într-o
variantă de căutare ulterioară, loturile de cel mult trei surse, oprirea timpurie
și raportarea plafonului în locul unei concluzii negative.

**Aceste teste nu validează calitatea semantică a Gemini sau accesul la API.**
Testul real este omis implicit. Pentru un singur apel real de căutare, care poate
consuma cotă sau genera costuri, configurează cheia și rulează explicit:

```powershell
$env:RUN_LIVE_TESTS="1"
.\.venv\Scripts\python.exe -m pytest tests/test_live.py -q
Remove-Item Env:RUN_LIVE_TESTS
```

Testul real verifică accesul la căutare și returnarea surselor; nu certifică toate
portalurile sau precizia identificării unui apartament. În mediul de implementare
nu a fost configurată o cheie Gemini și nu au fost efectuate apeluri reale.
Comenzile Windows sunt documentate, dar verificările locale au rulat pe Linux/Python 3.12.

## Dacă Gemini nu finalizează verificarea

Interfața arată acum etapa și motivul concret: `MAX_TOKENS` înseamnă răspuns
trunchiat, `SAFETY`/alte coduri de blocare indică refuzul furnizorului, iar
`RECITATION` indică oprirea pentru reproducerea textului. Aceste cazuri nu sunt
rezultate negative ale căutării. Versiunile vechi le afișau prin același mesaj
generic și nu păstrau motivul; cauza unei execuții vechi nu poate fi recuperată
doar din acel mesaj.

În caz de eroare, deschide **Detalii pentru diagnostic** și folosește
**Descarcă diagnosticul**. Fișierul include etapele, modelul, codurile de oprire și
consumul raportat, fără cheia API, URL-uri sau textele anunțurilor. Sursele deja
găsite rămân accesibile separat ca surse cu comparația nefinalizată.

Comparația folosește identificatori scurți (`s0`, `s1` etc.), reconectați la URL-urile
reale de către program. Linkurile lungi de redirecționare Google nu mai sunt cerute
în răspunsul JSON. Aceasta reduce consumul fără creșterea plafonului de tokeni sau
apeluri. Dacă eroarea confirmată este `MAX_TOKENS`, verifică tokenii de gândire și
tokenii de răspuns din diagnostic. Cu `medium`, un plafon de 3.000 poate fi consumat
aproape integral de gândire înainte de generarea rezultatului JSON. Pentru a păstra
`medium`, setează `MAX_OUTPUT_TOKENS=8192` în `.env`. Plafonul nu este un consum
obligatoriu, dar permite un consum mai mare; rezultatul real trebuie reverificat.
Poți seta `GEMINI_THINKING_LEVEL=low` pentru a reduce raționamentul sau
`MAX_CANDIDATES=3` pentru a verifica mai puține surse. Nu există retry automat după
trunchiere. Setările explicite din `.env` sunt păstrate la actualizare: dacă ai
`MAX_OUTPUT_TOKENS=3000`, editează această linie și repornește aplicația.

Un `.env` care conține doar `GEMINI_API_KEY` este valid: celelalte valori au
implicite în `src/config.py`. Nu este necesar să suprascrii cheia când actualizezi aplicația.
Valorile vechi scrise explicit (de exemplu `MAX_SEARCHES=2` și `MAX_AI_CALLS=5`)
continuă să se aplice. Pentru profilul mai amplu, copiază valorile din
`.env.example` în `.env`, păstrând cheia reală. Aplicația arată numărul căutărilor,
paginilor încercate și surselor comparate, inclusiv în diagnosticul descărcabil.

## Limite cunoscute

Requests/Beautiful Soup nu execută JavaScript și nu ocolesc autentificarea sau
protecțiile anti-bot. Unele site-uri vor necesita text copiat. Extragerea este generică,
fără adaptoare dedicate fiecărui portal. Paginile trunchiate pot pierde informații.
Rezultatele de căutare pot fi vechi sau incomplete; AI poate interpreta greșit textul,
chiar dacă răspunsul este JSON valid. Verifică manual anunțul înainte de contact.

Într-un mediu cloud cu rețea restricționată sunt necesare accesul HTTPS la
`generativelanguage.googleapis.com`, redirecționările de surse Google (de exemplu
`vertexaisearch.cloud.google.com`) și domeniile portalurilor consultate. Accesul la
un domeniu Google nu permite automat citirea tuturor portalurilor. Pe calculatorul
personal aceste reguli depind de rețeaua și firewallul propriu.
