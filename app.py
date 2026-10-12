import streamlit as st
import streamlit.components.v1 as components

from src.config import ConfigurationError, Settings
from src.models import Status
from src.service import analyze


def clear_result():
    st.session_state.pop("report", None)
    st.session_state.pop("journal_warning", None)


def new_analysis():
    clear_result()
    st.session_state["listing_url"] = ""
    st.session_state["listing_text"] = ""


st.set_page_config(page_title="Căutare apartament", page_icon="🏠")
st.title("Căutare apartament")
st.write("Găsește posibile anunțuri ale proprietarului pentru apartamente de vânzare în București.")

try:
    settings = Settings.load()
except ConfigurationError as exc:
    st.error(str(exc))
    st.stop()

if not settings.api_key:
    st.info("Pentru analiză, configurează GEMINI_API_KEY în fișierul local .env. Instrucțiunile sunt în README.")

url = st.text_input("Linkul anunțului", key="listing_url", placeholder="https://…", on_change=clear_result)
text = st.text_area("Descriere copiată (alternativă)", key="listing_text", height=230,
                    max_chars=settings.max_input_chars, on_change=clear_result)
st.caption("Dacă introduci și link, și descriere, analizăm textul copiat și păstrăm linkul ca referință.")

search_column, reset_column = st.columns(2)
search = search_column.button("Caută proprietarul", type="primary", use_container_width=True)
reset_column.button("Verificare nouă", on_click=new_analysis, use_container_width=True)

if search:
    clear_result()
    if not url.strip() and not text.strip():
        st.warning("Introdu un link sau descrierea unui anunț.")
    else:
        bar = st.progress(0, text="Încep verificarea…")
        try:
            report, journal_warning = analyze(settings, url, text, lambda value, message: bar.progress(value, text=message))
            st.session_state["report"] = report
            st.session_state["journal_warning"] = journal_warning
        finally:
            bar.empty()

if report := st.session_state.get("report"):
    if report.status == Status.FOUND:
        st.success(report.status.value)
    elif report.status == Status.NOT_FOUND:
        st.info(report.status.value)
    else:
        st.warning(report.status.value)
    st.write(report.message)
    if report.status == Status.INCOMPLETE:
        st.caption("Poți copia descrierea în câmpul alternativ sau apăsa din nou «Caută proprietarul».")
    for result in report.results:
        with st.container(border=True):
            st.text(result.title)
            if result.url:
                st.link_button("Deschide anunțul", result.url)
            st.write(result.justification)
            if result.facts.price:
                st.caption(f"Preț în această apariție: {result.facts.price}")
            with st.expander("Dovezi"):
                st.text("Autor: " + result.author.value)
                for quote in dict.fromkeys(result.evidence + result.author_evidence):
                    st.text(f"„{quote}”")
                if result.verification == "manual":
                    st.caption("Declarație din textul introdus; pagina nu a fost verificată.")
    if report.manual_review:
        st.write("**Pentru verificare manuală — surse insuficient verificate**")
        for result in report.manual_review:
            st.link_button(result.title, result.url)
            st.text(result.justification)
            st.caption("Bazat pe informația returnată de căutare; conținutul paginii nu a putut fi confirmat.")
    st.caption("«Proprietar declarat» descrie afirmația autorului, fără verificarea dreptului de proprietate.")
    if report.limitations:
        with st.expander("Limitele acestei verificări"):
            for limitation in report.limitations:
                st.text(limitation)
    for html in report.search_suggestions_html:
        # Official Google Search suggestions only; never render HTML extracted from listing pages.
        components.html(html, height=160, scrolling=True)
    if warning := st.session_state.get("journal_warning"):
        st.warning(warning)
