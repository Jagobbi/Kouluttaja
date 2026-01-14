import streamlit as st
from pathlib import Path

from src.kb import (
    _normalize_tags,
    attach_file_to_note,
    create_note,
    delete_attachment,
    delete_note,
    list_notes,
)
from src.ai import rebuild_index, answer_with_gpt, infer_note_metadata


st.set_page_config(page_title="Tietopankki", layout="wide")

st.title("Tietopankki")
st.caption("Lisää muistiinpanoja ja tiedostoja, kysy chatista.")

if "chat" not in st.session_state:
    st.session_state.chat = []  # list of {"role": "user"/"assistant", "content": str}
if "history_pairs" not in st.session_state:
    st.session_state.history_pairs = []  # list of (q,a) for ai.py history


tabs = st.tabs(["Lisää muistiinpano", "Lisää tiedostot", "Selaa", "Chat"])

with tabs[0]:
    st.subheader("Uusi muistiinpano")
    st.write("Järjestelmä ja tagit tunnistetaan automaattisesti.")
    with st.form("new_note"):
        title = st.text_input("Otsikko")
        device = st.text_input("Laite (valinnainen)")
        body = st.text_area("Muistiinpano (teksti)")
        uploaded = st.file_uploader(
            "Liitä tiedostoja (drag & drop)",
            accept_multiple_files=True,
        )
        manual = st.checkbox("Muokkaa järjestelmää ja tageja")
        system_in = st.text_input("Järjestelmä", value="", disabled=not manual)
        tags_in = st.text_input("Tagit (pilkulla eroteltu)", value="", disabled=not manual)
        submit = st.form_submit_button("Luo muistiinpano")

    if submit:
        if manual:
            system = system_in.strip().lower()
            tags = _normalize_tags(tags_in)
        else:
            try:
                system, tags = infer_note_metadata(title=title, body=body)
            except Exception:
                system, tags = "", []

        meta = create_note(title=title, system=system, device=device, tags=tags, body=body)

        if uploaded:
            tmp_dir = Path("data/tmp_uploads")
            tmp_dir.mkdir(parents=True, exist_ok=True)
            for uf in uploaded:
                tmp_path = tmp_dir / uf.name
                tmp_path.write_bytes(uf.getvalue())
                _meta, msg = attach_file_to_note(meta.id, str(tmp_path))
                st.write(msg)

        with st.spinner("Päivitetään AI-indeksi..."):
            rebuild_index(include_attachments=True, verbose=False)
        st.success(f"Luotu: {meta.id} | system={system or '-'} | tags={', '.join(tags) if tags else '-'}")

with tabs[1]:
    st.subheader("Lisää tiedostot uutena muistiinpanona")
    st.write("Tiputa tiedostoja ja luo niistä uusi muistiinpano yhdellä kertaa.")
    with st.form("new_files"):
        title = st.text_input("Otsikko (valinnainen)")
        note_text = st.text_area("Kuvaus / muistiinpanot (valinnainen)")
        uploaded = st.file_uploader(
            "Tiedostot (drag & drop)",
            accept_multiple_files=True,
        )
        submit_files = st.form_submit_button("Luo muistiinpano tiedostoista")

    if submit_files:
        if not uploaded:
            st.warning("Lisää vähintään yksi tiedosto.")
        else:
            inferred_title = title.strip() or f"Tiedostot: {uploaded[0].name}"
            infer_body = note_text.strip()
            try:
                system, tags = infer_note_metadata(title=inferred_title, body=infer_body)
            except Exception:
                system, tags = "", []

            meta = create_note(
                title=inferred_title,
                system=system,
                device="",
                tags=tags,
                body=note_text,
            )

            tmp_dir = Path("data/tmp_uploads")
            tmp_dir.mkdir(parents=True, exist_ok=True)
            for uf in uploaded:
                tmp_path = tmp_dir / uf.name
                tmp_path.write_bytes(uf.getvalue())
                _meta, msg = attach_file_to_note(meta.id, str(tmp_path))
                st.write(msg)

            with st.spinner("Päivitetään AI-indeksi..."):
                rebuild_index(include_attachments=True, verbose=False)
            st.success(f"Luotu: {meta.id} | system={system or '-'} | tags={', '.join(tags) if tags else '-'}")

with tabs[2]:
    st.subheader("Muistiinpanot ja tiedostot")
    notes = list_notes(limit=500)
    if not notes:
        st.info("Ei vielä muistiinpanoja.")
    else:
        for n in notes:
            header_cols = st.columns([4, 1])
            with header_cols[0]:
                st.markdown(f"**{n.title}**  \nID: `{n.id}`  \nJärjestelmä: `{n.system or '-'}`")
            with header_cols[1]:
                if st.button("Poista muistiinpano", key=f"del_note_{n.id}"):
                    msg = delete_note(n.id, remove_files=True)
                    with st.spinner("Päivitetään AI-indeksi..."):
                        rebuild_index(include_attachments=True, verbose=False)
                    st.success(msg)
                    st.rerun()
            if n.linked_files:
                st.write("Liitteet:")
                for lf in n.linked_files:
                    cols = st.columns([4, 1])
                    with cols[0]:
                        st.write(f"- {lf}")
                    with cols[1]:
                        if st.button("Poista", key=f"del_{n.id}_{lf}"):
                            _count, msg = delete_attachment(lf)
                            with st.spinner("Päivitetään AI-indeksi..."):
                                rebuild_index(include_attachments=True, verbose=False)
                            st.success(msg)
                            st.rerun()
            else:
                st.write("Liitteet: -")
            st.markdown("---")

with tabs[3]:
    st.subheader("AI-chat")
    system_filter = st.text_input("Rajaa järjestelmään (valinnainen)", value="")

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
