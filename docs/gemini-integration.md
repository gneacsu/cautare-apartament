# Integrarea Gemini

Contractul curent este documentat în [integration.md](integration.md).
Căutarea principală se face acum prin SerpApi, iar Gemini realizează extracția,
compararea și transcrierea capturilor. Google Lens rămâne manual.

Codul și testele vechii căutări Gemini sunt păstrate pentru regresii; ele nu sunt
apelate de fluxul principal SerpApi.
