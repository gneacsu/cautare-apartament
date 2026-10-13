# Contracte de integrare — 13 octombrie 2026

## SerpApi

Surse oficiale consultate pe GitHub:
- https://github.com/serpapi/serpapi-python/blob/master/README.md (SDK-ul actual,
  `engine=google`, `q`, tratarea HTTP 401/400/429 și timeouturi).
- https://github.com/serpapi/google-search-results-python/blob/master/README.md
  (referința parametrilor `hl`, `gl`, `start`, `organic_results`, `serpapi_pagination`).
  Pachetul legacy este anunțat ca depreciat; aplicația nu îl instalează.
- Referința HTTP: https://serpapi.com/search-api
- Tarife: https://serpapi.com/pricing

Site-ul documentației și tarifele nu au putut fi accesate din mediul cloud curent.
Nu sunt afirmate tarife sau cote numerice. Nu a fost efectuat un apel autentificat.

Implementarea folosește Requests la `https://serpapi.com/search.json`, GET cu `engine`,
`q`, `hl=ro`, `gl=ro`, `start`, `api_key`. Nu presupune că parametrul `num` este respectat.
Linkurile vin exclusiv din rezultatele organice. Este necesar statusul `Success`;
rezultatele absente sunt acceptate numai într-un răspuns valid, nu la erori.
Pagination next este folosit numai pentru extragerea offsetului; URL-ul poate conține
cheia, deci nu se salvează și nu se execută direct. Nu există retry automat.
Mesajele brute HTTP/API nu sunt afișate pentru a evita expunerea cheii din URL-uri.

## Gemini

SDK `google-genai==1.75.0`, `generate_content`, `response_json_schema`, thinking level
configurabil. Modelul solicitat de utilizator este `gemini-3.6-flash`, `medium`.
Documentația modelului consultată în etapa precedentă:
- https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash
- https://ai.google.dev/gemini-api/docs/thinking
- https://ai.google.dev/api/generate-content
- https://github.com/googleapis/python-genai/blob/main/google/genai/types.py

Disponibilitatea pentru un cont necesită apel real. Aplicația principală nu mai folosește
Google Search grounding prin Gemini. Gemini primește date extrase, identificatori de
surse și indicii locale despre imagini. Nu poate introduce URL-uri candidate arbitrare.
Răspunsurile trebuie să aibă STOP, schemă validă, surse exacte și citate observate.
Transcrierea capturilor folosește părți multimodale JPEG și un răspuns JSON validabil;
utilizatorul verifică textul înainte să fie folosit ca dovadă manuală.

## Reluare și limite

Jurnalul persistă planul, offseturile, candidații și paginile citite după fiecare etapă.
O eroare de comparație nu repetă căutarea sau citirea la reluare. Timeoutul rundei și
oprirea utilizatorului se verifică între operații. O cerere deja trimisă nu poate fi
anulată retroactiv și poate fi facturată; poate termina după timeoutul rundei.
Dacă procesul moare după un apel, dar înainte de salvare, acel apel poate fi repetat:
nu pretindem garanția tranzacțională exact-once asupra furnizorilor externi.

Nu există plafon total de tokeni sau candidați. Rămân planul finit, maximum cinci pagini
per interogare la continuare, maximum patru căutări adaptive implicit și limitele
per răspuns/context ale furnizorului. Corectarea caracteristicilor regenerează planul
și comparațiile în mod explicit; poate repeta căutări.

## Imagini și acces

Google Lens este exclusiv manual, chiar dacă SerpApi oferă și produse vizuale.
Nu implementăm un API Lens fără o decizie nouă a utilizatorului. Amprenta pixelilor
și dHash local sunt indicii conservative, nu un model vizual validat. Nu recunosc
fiabil toate decupările, filigranele sau schimbările de unghi.

HTML și JSON-LD sunt citite fără JavaScript. Facebook privat și paginile cu autentificare
necesită material furnizat manual; cererile HTTP nu sunt prezentate ca acces la browser.
Nu se elimină filigrane și nu se generează fotografii modificate.
