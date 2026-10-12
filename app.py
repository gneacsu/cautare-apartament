import streamlit as st


st.set_page_config(page_title="Căutare apartament", page_icon="🏠")
st.title("Căutare apartament")
st.write("Introdu un link sau textul unui anunț imobiliar.")

input_type = st.radio("Tipul anunțului", ["Link anunț", "Text anunț"])

if input_type == "Link anunț":
    listing_input = st.text_input("URL-ul anunțului", placeholder="https://exemplu.ro/anunt")
else:
    listing_input = st.text_area("Textul anunțului", height=300)

if st.button("Analizează"):
    if listing_input.strip():
        st.success("Inputul a fost primit. Analiza va fi disponibilă într-o etapă viitoare.")
    else:
        st.warning("Introdu un link sau textul unui anunț înainte de a continua.")
