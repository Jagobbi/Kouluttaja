import streamlit as st
from pathlib import Path

from src.kb import (
    _normalize_tags,
    attach_file_to_note,
    create_note,
    list_notes,
    read_note,
)
from src.ai import rebuild_index, answer_with_gpt


st.set_page_config(page_title="Tietopankki", layout="wide")

st.title("Tietopankki (muistiinpanot + liitteet + AI)")

if "chat" not in st.session_state:
    st.session_state.chat = []  # list of {"role": "user"/"assistant", "content": str}
if "history_pairs" not in st.session_state:
    st.session_state.history_pairs = []  # list of (q,a) for ai.py history


left, right = st.columns([1, 1])

with left:
    st.header("Muistiinpanot")

    notes = list_notes(limit=300)
    note_ids = [n.id for n in notes]
    selected = st.selectbox("Valitse muistiinpano", [""] + note_ids)

    if selected:
        meta, body = read_note(selected)
        if meta:
            st.subheader(meta.title)
            st.write(f"**system:** {meta.system}")
            st.write(f"**device:** {meta.device}")
            st.write(f"**tags:** {', '.join(meta.tags) if meta.tags else '-'}")
            st.write(f"**linked_files:** {', '.join(meta.linked_files) if meta.linked_files else '-'}")
            st.markdown("---")
            st.text_area("Sisältö", value=body or "", height=240, disabled=True)

    st.markdown("---")
    st.subheader("Lisää uusi muistiinpano")
    with st.form("new_note"):
        title = st.text_input("Otsikko")
        system = st.text_input("Järjestelmä (esim. sap / zebra / jira)")
        device = st.text_input("Laite (valinnainen)")
        tags_in = st.text_input("Tagit (pilkulla eroteltu)")
        body = st.text_area("Muistiinpano (teksti)")
        submit = st.form_submit_button("Luo muistiinpano")

    if submit:
        tags = _normalize_tags(tags_in)
        meta = create_note(title=title, system=system, device=device, tags=tags, body=body)
        st.success(f"Luotu: {meta.id}")
        st.rerun()

with right:
    st.header("Liitteet + AI")

    st.subheader("Liitä tiedosto muistiinpanoon (drag & drop)")
    if selected:
        uploaded = st.file_uploader(
            "Tiputa tiedosto tähän (PDF/DOCX/TXT/MD/CSV/kuvat ym. tallentuu, mutta AI lukee tekstistä vain tuetut)",
            accept_multiple_files=True,
        )
        if uploaded:
            # tallenna väliaikaisesti ja käytä kb.attach_file_to_note (kopioi data/docs)
            tmp_dir = Path("data/tmp_uploads")
            tmp_dir.mkdir(parents=True, exist_ok=True)

            for uf in uploaded:
                tmp_path = tmp_dir / uf.name
                tmp_path.write_bytes(uf.getvalue())
                meta, msg = attach_file_to_note(selected, str(tmp_path))
                st.write(msg)

            st.info("Muista: rakenna AI-indeksi uudelleen, jotta liitteiden teksti tulee mukaan hakuun.")
            if st.button("Rakenna AI-indeksi nyt (muistiinpanot + liitteet)"):
                with st.spinner("Indeksoidaan..."):
                    rebuild_index(include_attachments=True, verbose=False)
                st.success("Indeksi valmis.")
                st.rerun()
    else:
        st.warning("Valitse ensin muistiinpano vasemmalta, jotta voit liittää tiedostoja siihen.")

    st.markdown("---")
    st.subheader("AI-chat (jatkokysymykset)")

    system_filter = st.text_input("Rajaa järjestelmään (valinnainen)", value="")

    # Näytä viestit
    for m in st.session_state.chat:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    user_q = st.chat_input("Kysy tietopankilta…")
    if user_q:
        st.session_state.chat.append({"role": "user", "content": user_q})
        with st.chat_message("user"):
            st.markdown(user_q)

        with st.chat_message("assistant"):
            with st.spinner("Ajattelen..."):
                answer, _used = answer_with_gpt(
                    user_q,
                    system_filter=system_filter,
                    history=st.session_state.history_pairs,
                )
                st.markdown(answer)

        st.session_state.chat.append({"role": "assistant", "content": answer})
        st.session_state.history_pairs.append((user_q, answer))

    cols = st.columns(2)
    with cols[0]:
        if st.button("Tyhjennä chat"):
            st.session_state.chat = []
            st.session_state.history_pairs = []
            st.rerun()
    with cols[1]:
        if st.button("Rakenna AI-indeksi (muistiinpanot + liitteet)"):
            with st.spinner("Indeksoidaan..."):
                rebuild_index(include_attachments=True, verbose=False)
            st.success("Indeksi valmis.")
            st.rerun()
