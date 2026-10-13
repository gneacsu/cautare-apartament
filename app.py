"""Romanian UI. Worker threads perform analysis; Streamlit owns only rendering/state."""
import json
from dataclasses import replace
from queue import Empty

import streamlit as st

from src.config import ConfigurationError, Settings
from src.models import Status
from src.service import add_candidate, correct_facts, read_screenshots, start_job
from src.utils.journal import load_analysis, recent_analyses, save_analysis, usage_summary


def busy():
    return st.session_state.get("job") is not None


def clear_result():
    st.session_state.pop("report", None)
    st.session_state.pop("journal_warning", None)
    st.session_state.pop("ocr_text", None)
    st.session_state.pop("candidate_url", None)
    st.session_state.pop("candidate_text", None)


def new_analysis():
    if busy():
        st.session_state.job.cancel.set()
        st.session_state.discard_job = True
    clear_result()
    st.session_state.listing_url = ""
    st.session_state.listing_text = ""
    st.session_state.upload_generation = st.session_state.get("upload_generation", 0) + 1


def launch(settings, url, text, **kwargs):
    st.session_state.discard_job = False
    st.session_state.job = start_job(settings, url, text, **kwargs)


def persist(report):
    st.session_state.report = report
    try:
        save_analysis(report, settings.journal_dir)
    except OSError:
        st.warning("Jurnalul local nu a putut fi salvat. Rezultatul rămâne disponibil în această sesiune.")


def show_result(result):
    with st.container(border=True):
        st.text(result.title)
        if result.url:
            st.link_button("Deschide anunțul", result.url)
        st.write(result.justification)
        if result.facts.price:
            st.caption("Preț în această apariție: " + result.facts.price)
        st.caption("Autor: " + result.author.value)
        for quote in dict.fromkeys(result.evidence + result.author_evidence):
            st.text(f'„{quote}”')
        if result.verification == "manual":
            st.caption("Bazat pe material furnizat de utilizator; pagina nu a fost verificată independent.")
        elif result.verification == "snippet":
            st.caption("Bazat pe un fragment de căutare; pagina nu este verificată.")


def photo_panel(report):
    urls = report.sources[0].images if report.sources else []
    st.write("**Căutare după fotografie — Google Lens, manual**")
    if urls:
        index = st.selectbox("Fotografia pentru Lens", range(len(urls)), format_func=lambda i: f"Fotografia {i+1}", key=f"photo-{report.id}")
        st.image(urls[index], caption="Fotografie din pagina de referință; verifică dacă aparține apartamentului.", width=500)
        st.link_button("Deschide fotografia", urls[index])
    else:
        st.caption("Nu am extras o fotografie accesibilă. Folosește o fotografie sau o captură încărcată mai sus ori imaginea din pagina anunțului.")
    st.link_button("Deschide Google Lens", "https://lens.google/")
    st.caption("În Chrome: click dreapta pe fotografie → Caută cu Google Lens. Alternativ, deschide Lens și folosește imaginea. Caută pagini cu aceeași fotografie, apoi adaugă linkurile mai jos. Dacă nu ajută, încearcă o altă cameră. Nu trimitem automat imagini către Lens.")


def diagnostics(report):
    with st.expander("Consum și diagnostic"):
        data = {"analysis_id": report.id, "checked_at": report.checked_at,
                "calls": [c.model_dump(mode="json") for c in report.diagnostics],
                "search_calls": [c.model_dump(exclude={"query"}) for c in report.search_calls],
                "usage": report.usage, "coverage": report.coverage,
                "limited": report.limited, "limit_reason": report.limit_reason,
                "elapsed_seconds": report.checkpoint.elapsed_seconds if report.checkpoint else None}
        st.json(data)
        st.download_button("Descarcă diagnosticul", json.dumps(data, ensure_ascii=False, indent=2),
                           file_name=f"diagnostic-{report.id}.json", mime="application/json", key=f"diag-{report.id}")
        st.caption("Fără chei, interogări, URL-uri sau descrieri. Cererile SerpApi sunt măsurate separat de tokenii Gemini. Nu există un plafon total de tokeni pe analiză.")


def details(report):
    if report.original:
        with st.expander("Fișa apartamentului și corectarea informațiilor"):
            st.text(report.original.title)
            st.json(report.original.facts.model_dump(exclude_none=True))
            st.text("Autor: " + report.original.author.value)
            for quote in report.original.author_evidence:
                st.text(quote)
            f = report.original.facts
            with st.form(f"correction-{report.id}"):
                city = st.text_input("Localitate", f.city or "")
                area = st.text_input("Zonă", f.area or "")
                address = st.text_input("Adresă", f.address or "")
                rooms = st.number_input("Camere (0 = necunoscut)", 0, 30, f.rooms or 0)
                surface = st.number_input("Suprafață (0 = necunoscută)", 0.0, 10000.0, float(f.surface or 0))
                kind = st.selectbox("Tip suprafață", ["necunoscută", "utilă", "construită"], index=["necunoscută", "utilă", "construită"].index(f.surface_kind))
                floor = st.text_input("Etaj", f.floor or "")
                transaction = st.selectbox("Tranzacție", ["necunoscută", "vânzare", "închiriere"], index=[None,"vânzare","închiriere"].index(f.transaction))
                corrected = st.form_submit_button("Salvează corectările", disabled=busy())
            if corrected:
                facts = f.model_dump()
                facts.update(city=city or None, area=area or None, address=address or None, rooms=rooms or None,
                             surface=surface or None, surface_kind=kind, floor=floor or None,
                             transaction=None if transaction == "necunoscută" else transaction)
                persist(correct_facts(report, facts))
                st.rerun()
    with st.expander("Surse, dovezi și pași rămași"):
        if report.checkpoint:
            for task in report.checkpoint.tasks:
                st.text(f'{"✓" if task.done else "○"} {task.category} · offset {task.start}: {task.query}')
                if task.error:
                    st.caption(task.error)
            for candidate in report.checkpoint.candidates:
                st.link_button(candidate.title or candidate.url, candidate.url)
                st.caption(f"Stare: {candidate.state}; descoperit prin: " + "; ".join(candidate.discovered_by))
                if candidate.error:
                    st.caption(candidate.error)
        for evaluation in report.evaluations:
            st.text(f"{evaluation.title}: {evaluation.same_property}; {evaluation.author.value}")
            st.text(evaluation.justification)
            for difference in evaluation.contradictions:
                st.caption(difference)
        for source in report.sources[1:]:
            for match in source.image_matches:
                st.caption("Fotografii cu pixeli identici" if match.kind == "identical" else "Fotografii posibil asemănătoare — euristică, nu dovadă independentă")
                st.text(f"{match.reference_url} → {match.candidate_url}")


def manual_candidate(report):
    if not report.original or report.results:
        return
    st.write("**Adaugă un candidat din Lens, Facebook sau alt site**")
    st.caption("Pentru o pagină inaccesibilă, introdu și textul. Capturile pot fi transcrise, apoi verificate și corectate înainte de comparație.")
    candidate_url = st.text_input("Linkul candidatului", key="candidate_url")
    uploads = st.file_uploader("Capturi ale postării (opțional)", type=["png", "jpg", "jpeg", "webp"],
                              accept_multiple_files=True, key=f"screens-{report.id}")
    if st.button("Transcrie capturile cu Gemini", disabled=busy() or not uploads):
        try:
            with st.spinner("Transcriu textul vizibil…"):
                transcript, usage, calls = read_screenshots(settings, [p.getvalue() for p in uploads[:4]])
            st.session_state.candidate_text = transcript.text
            for key, value in usage.items():
                report.usage[key] = report.usage.get(key, 0) + value
            report.usage["ai_calls"] = report.usage.get("ai_calls", 0) + len(calls)
            report.diagnostics.extend(calls)
            report.limitations.extend(transcript.limitations)
            persist(report)
            st.info("Verifică transcrierea de mai jos înainte să compari candidatul.")
        except (ValueError, RuntimeError) as exc:
            st.error(str(exc))
    photos = st.file_uploader("Fotografii ale apartamentului candidat (opțional)", type=["jpg", "jpeg", "png", "webp"],
                              accept_multiple_files=True, key=f"candidate-photos-{report.id}")
    candidate_text = st.text_area("Textul candidatului / transcriere verificată", key="candidate_text", height=150, max_chars=settings.max_candidate_chars)
    if st.button("Compară acest candidat", disabled=busy() or not candidate_url.strip()):
        try:
            updated = add_candidate(report, candidate_url, candidate_text, pictures=[p.getvalue() for p in photos[:6]])
            persist(updated)
            launch(settings, updated.input_url, updated.input_text, report=updated, manual_only=True)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    if busy():
        st.caption("Poți căuta în Lens între timp. Compararea linkului introdus este disponibilă după terminarea sau oprirea rundei curente.")


st.set_page_config(page_title="Căutare apartament", page_icon="🏠", layout="wide")
st.title("Căutare apartament")
st.write("De la anunțul agentului la posibile anunțuri ale proprietarului. Text automat și Google Lens asistat.")
try:
    settings = Settings.load()
except ConfigurationError as exc:
    st.error(str(exc))
    st.stop()
missing = [name for name, value in (("GEMINI_API_KEY", settings.api_key), ("SERPAPI_API_KEY", settings.serpapi_key)) if not value]
if missing:
    st.info("Configurează în .env lângă app.py: " + ", ".join(missing) + ". Nu introduce cheile în anunțuri sau în conversație.")

url = st.text_input("Linkul anunțului", key="listing_url", disabled=busy(), on_change=clear_result)
text = st.text_area("Descriere copiată (alternativă)", key="listing_text", height=180, max_chars=settings.max_input_chars,
                    disabled=busy(), on_change=clear_result)
st.caption("Dacă introduci ambele, textul furnizat are prioritate. Fotografiile pot fi încărcate separat, fără citirea paginii.")
reference_uploads = st.file_uploader("Fotografii sau capturi pentru Lens (opțional)", type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True, key=f"reference-{st.session_state.get('upload_generation',0)}", disabled=busy(), on_change=clear_result)
if reference_uploads:
    chosen = st.selectbox("Fotografie încărcată pentru Lens", range(len(reference_uploads)), format_func=lambda i: f"Imaginea {i+1}")
    st.image(reference_uploads[chosen].getvalue(), width=450, caption="Folosește fotografia în Lens din meniul browserului.")
search_col, reset_col = st.columns(2)
search = search_col.button("Caută proprietarul", type="primary", disabled=busy())
reset_col.button("Verificare nouă", on_click=new_analysis)
if search:
    clear_result()
    if not url.strip() and not text.strip():
        st.warning("Introdu un link sau descrierea unui anunț.")
    else:
        launch(settings, url, text, reference_pictures=[p.getvalue() for p in reference_uploads[:settings.max_images_per_listing]])
        st.rerun()

with st.expander("Reia o analiză salvată"):
    history = recent_analyses(settings.journal_dir)
    if history:
        selected = st.selectbox("Analiză", history, format_func=lambda v: v[1] + " — " + v[2])
        if st.button("Încarcă analiza", disabled=busy()):
            try:
                clear_result()
                st.session_state.report = load_analysis(selected[0], settings.journal_dir)
                st.rerun()
            except (ValueError, OSError):
                st.error("Jurnalul nu poate fi citit sau nu este valid.")
    else:
        st.caption("Analizele sunt salvate local în directorul local_data.")
    if st.button("Calculează consumul analizelor salvate", disabled=busy()):
        st.json(usage_summary(settings.journal_dir))
        st.caption("Analizele nefinalizate sunt separate. Aceste valori măsoară consumul, nu rata de găsire a proprietarului.")


@st.fragment(run_every=1 if busy() else None)
def analysis_panel():
    job = st.session_state.get("job")
    if job:
        while True:
            try:
                snapshot = job.updates.get_nowait()
            except Empty:
                break
            if not st.session_state.get("discard_job"):
                st.session_state.report = snapshot
        if job.future.done():
            try:
                completed, warning = job.future.result()
                if not st.session_state.get("discard_job"):
                    st.session_state.report = completed
                    st.session_state.journal_warning = warning
            except Exception:
                # Never echo exceptions with request URLs/keys. Saved checkpoint remains available.
                st.session_state.journal_warning = "Eroare internă neașteptată. Încarcă ultima analiză salvată pentru reluare."
            st.session_state.job = None
            st.rerun()
        st.status("Analiza rulează. Poți folosi Google Lens în paralel.", state="running")
        if st.button("Oprește și păstrează progresul"):
            job.cancel.set()
            st.caption("Oprirea se aplică după cererea aflată în curs.")
    report = st.session_state.get("report")
    if not report:
        return
    if busy():
        st.caption(report.checkpoint.stage if report.checkpoint else "Pregătesc analiza…")
    else:
        render = st.success if report.status == Status.FOUND else st.info if report.status == Status.NOT_FOUND else st.warning
        render(report.status.value)
        st.write(report.message)
        if report.recovery_hint:
            st.caption(report.recovery_hint)
    photo_panel(report)
    if report.coverage:
        st.caption(f"Căutări finalizate: {report.coverage.get('completed_searches',0)}/{report.coverage.get('planned_searches',0)} · "
                   f"Candidați descoperiți: {report.coverage.get('candidates_discovered',0)} · Comparați: {report.coverage.get('sources_compared',0)}")
    for result in report.results:
        show_result(result)
    if report.manual_review:
        st.write("**Candidați care necesită verificare manuală**")
        for result in report.manual_review:
            show_result(result)
    if not busy() and not report.results and report.checkpoint:
        pending = [t for t in report.checkpoint.tasks if not t.done]
        if pending or any(c.state in {"pending", "read"} for c in report.checkpoint.candidates) or not report.original:
            depth = max(settings.pages_per_query, min((t.depth for t in pending), default=0)+1)
            if depth > 5 and not any(c.state in {"pending", "read"} for c in report.checkpoint.candidates):
                st.caption("Au rămas pagini dincolo de cele cinci niveluri automate. Folosește căutarea manuală și adaugă linkurile relevante mai jos.")
            elif st.button("Continuă căutarea"):
                launch(replace(settings, pages_per_query=min(depth,5)), report.input_url, report.input_text, report=report)
                st.rerun()
    manual_candidate(report)
    details(report)
    diagnostics(report)
    if report.limitations:
        with st.expander("Limitele verificării"):
            for limitation in report.limitations:
                st.text(limitation)
    st.caption("«Proprietar declarat» descrie afirmația autorului. Nu verifică dreptul de proprietate și nu demonstrează că acesta este anunțul inițial.")
    if warning := st.session_state.get("journal_warning"):
        st.warning(warning)


analysis_panel()
