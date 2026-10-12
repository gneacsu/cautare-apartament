# Contractul integrării Gemini

Verificare documentară: 12 octombrie 2026. Furnizor ales de utilizator: Google Gemini.
Implementarea folosește SDK-ul oficial `google-genai==1.75.0`, API `generateContent`.

## Surse oficiale consultate

- [Documentația SDK, sursa oficială](https://github.com/googleapis/python-genai/blob/main/docs/_sources/index.rst.txt):
  `client.models.generate_content`, `response_json_schema`, configurarea clientului.
- [Exemplul oficial Google Search pentru generateContent](https://github.com/google-gemini/cookbook/blob/archive/generate-content-api/quickstarts/Search_Grounding.ipynb):
  `tools=[{"google_search": {}}]`, `grounding_metadata`, sursele și sugestiile de căutare;
  `gemini-2.5-flash` este inclus în lista de modele a exemplului.
- [Exemplul oficial pentru JSON](https://github.com/google-gemini/cookbook/blob/archive/generate-content-api/quickstarts/JSON_mode.ipynb).
- [Ghidul actual Google Search](https://github.com/google-gemini/cookbook/blob/main/quickstarts/Search_Grounding.ipynb)
  și [JSON](https://github.com/google-gemini/cookbook/blob/main/quickstarts/JSON_mode.ipynb):
  utilizează acum Interactions API și trimit explicit la exemplele generateContent arhivate.
  Aplicația nu amestecă parametrii celor două API-uri.
- Tipurile SDK instalat, disponibile și în [sursa oficială](https://github.com/googleapis/python-genai/blob/main/google/genai/types.py):
  `HttpOptions.timeout` este în milisecunde; `HttpRetryOptions.attempts` include prima
  încercare; `ThinkingConfig.thinking_budget=0` înseamnă dezactivare pentru modelele compatibile.

Paginile `ai.google.dev` pentru prețuri/modele/ghiduri au fost blocate de proxy-ul
mediului. Documentația GitHub și tipurile SDK sunt dovezi de contract, nu dovadă
că un model este disponibil pentru contul utilizatorului la momentul rulării.
[Tarifele](https://ai.google.dev/gemini-api/docs/pricing) trebuie verificate înaintea
activării facturării. Nu au fost folosite chei și nu au fost efectuate apeluri reale.

## Separarea căutării de răspunsul structurat

1. Extragere: fără instrumente, `response_mime_type=application/json` și
   `response_json_schema=Listing.model_json_schema()`.
2. Căutare: instrumentul `google_search`, fără forțarea unei scheme JSON.
   URL-urile sunt acceptate numai din `grounding_chunks.web.uri`. Textul liber al
   modelului nu poate introduce un URL candidat. Segmentele din `grounding_supports`
   sunt rezumate susținute de căutare, nu citate independente ale unei pagini.
3. Programul descarcă paginile și curăță HTML-ul. Sursele inaccesibile rămân marcate.
4. Comparare: un apel separat fără instrumente, cu schema `Comparison`, ce include
   stare, surse, rezultate, citate, caracteristici și limitări. Pe fir se folosește
   schema compactă `CandidateComparison`, cu identificatori scurți de sursă.
   Programul validează acoperirea exactă a identificatorilor și reconstruiește
   `Comparison` cu URL-urile originale; linkurile Google lungi nu sunt regenerate de AI.
5. Programul validează schema, proveniența URL-urilor, citatele și regulile de triere.
   Un răspuns invalid/trunchiat devine eroare, fără reparare automată sau retry plătit.

Această compoziție utilizează separat două funcții documentate și evită dependența
față de suportul unei combinații de instrumente și JSON pentru un anumit model.
Nicio sesiune AI nu este reutilizată între analize.

## Limitele contractului

Aplicația limitează apelurile de căutare, nu interogările interne pe care Google
le poate executa pentru fiecare apel. Nu promite un cost maxim în bani. Numărul
raportat de interogări și tokeni este păstrat în jurnal, fără estimări inventate.
Timeouturile și limitele de tokeni nu confirmă finalizarea semantică: răspunsul
este acceptat numai cu `finish_reason=STOP` și validarea completă a structurii.
Sugestiile oficiale din `search_entry_point.rendered_content` sunt afișate în iframe.

Fiecare apel înregistrează etapa, limita, utilizarea raportată, `finish_reason` și
eventualul `prompt_feedback.block_reason`, fără răspunsul brut sau cheia API.
Răspunsurile trunchiate/blocate rămân respinse, cu explicații distincte în interfață.
