import streamlit as st
from pathlib import Path

from src.kb import (
    _normalize_tags,
    attach_file_to_note,
    create_note,
    delete_attachment,
    delete_note,
    list_notes,
    read_note,
    update_note,
    append_feedback_record,
)
from src.ai import rebuild_index, answer_with_gpt, infer_note_metadata, sync_index, get_last_sync_info


st.set_page_config(page_title="Tietopankki", layout="wide")

st.title("Tietopankki")
st.caption("Lisää muistiinpanoja ja tiedostoja, kysy chatista.")

if "chat" not in st.session_state:
    st.session_state.chat = []  # list of {"role": "user"/"assistant", "content": str}
if "history_pairs" not in st.session_state:
    st.session_state.history_pairs = []  # list of (q,a) for ai.py history
if "last_qa" not in st.session_state:
    st.session_state.last_qa = None


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
    if st.button("Pakota synkronointi (siivoaa poistetut tiedostot)"):
        with st.spinner("Synkronoidaan indeksi..."):
            sync_index(include_attachments=True, verbose=True)
        info = get_last_sync_info()
        if info:
            st.success(
                f"Synkronointi valmis. Poistetut dokumentit: {len(info.get('deleted_doc_keys', []))}, "
                f"poistetut chunkit: {info.get('deleted_chunks', 0)}, "
                f"uudet chunkit: {info.get('created_chunks', 0)}"
            )
            if info.get("deleted_doc_keys"):
                st.session_state.chat = []
                st.session_state.history_pairs = []
                st.info("Chat-historia tyhjennettiin poistojen vuoksi.")
        st.rerun()
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
            with st.expander("Näytä ja muokkaa muistiinpanoa"):
                meta, body = read_note(n.id)
                st.write(f"**Otsikko:** {meta.title if meta else n.title}")
                st.write(f"**Laite:** {meta.device if meta else n.device}")
                st.write(f"**Tagit:** {', '.join(meta.tags) if meta and meta.tags else '-'}")
                new_body = st.text_area(
                    "Sisältö",
                    value=body or "",
                    key=f"body_{n.id}",
                    height=220,
                )
                if st.button("Tallenna muutokset", key=f"save_{n.id}"):
                    if meta:
                        update_note(meta, new_body)
                        with st.spinner("Päivitetään AI-indeksi..."):
                            sync_index(include_attachments=True, verbose=False)
                        st.success("Muistiinpano päivitetty.")
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
    info = get_last_sync_info()
    if info:
        st.caption(
            f"Viimeisin sync: poistettuja dokumentteja {len(info.get('deleted_doc_keys', []))}, "
            f"poistettuja chunkeja {info.get('deleted_chunks', 0)}, "
            f"uusia chunkeja {info.get('created_chunks', 0)}, "
            f"index_version={info.get('index_version', 0)}"
        )

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
        st.session_state.last_qa = {"q": user_q, "a": answer}

    if st.session_state.last_qa:
        st.markdown("---")
        st.subheader("Oliko ohje toimiva?")
        with st.form("feedback_form"):
            status = st.radio(
                "Valitse",
                ["Kyllä", "Osittain / ongelmia", "Ei ratkaisua"],
                index=0,
            )
            resolution = ""
            if status != "Kyllä":
                resolution = st.text_area(
                    "Mikä jäi puutteelliseksi tai mikä oli oikea ratkaisu?",
                    height=120,
                )
            submitted = st.form_submit_button("Lähetä palaute")

        if submitted:
            if status != "Kyllä" and not resolution.strip():
                st.warning("Kirjoita lyhyt kuvaus ratkaisusta tai ongelmasta.")
            else:
                q = st.session_state.last_qa["q"]
                a = st.session_state.last_qa["a"]
                title = f"Feedback: {q}"[:80]
                body = (
                    f"Kysymys:\n{q}\n\n"
                    f"AI-vastaus:\n{a}\n\n"
                    f"Kayttajan palaute / ratkaisu:\n{resolution.strip() or '-'}\n\n"
                    f"Tila: {status}\n"
                )
                try:
                    system, tags = infer_note_metadata(title=title, body=resolution or q)
                except Exception:
                    system, tags = "", []
                tags = list(dict.fromkeys(tags + ["feedback"]))
                meta = create_note(
                    title=title,
                    system=system,
                    device="",
                    tags=tags,
                    body=body,
                )
                append_feedback_record(q, a, resolution.strip(), status, note_id=meta.id)
                with st.spinner("Päivitetään AI-indeksi..."):
                    sync_index(include_attachments=True, verbose=False)
                st.success("Kiitos! Palaute tallennettu tietopankkiin.")
                st.session_state.last_qa = None
                st.rerun()

cols = st.columns(2)
with cols[0]:
    if st.button("Tyhjennä chat"):
        st.session_state.chat = []
        st.session_state.history_pairs = []
        st.rerun()
