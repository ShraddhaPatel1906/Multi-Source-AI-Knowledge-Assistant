import os
import streamlit as st
from dotenv import load_dotenv
 
from multi_source_ai_knowledge import (
    load_any_source,
    build_vectorstore,
    build_chain,
    ask_question,
)
 
load_dotenv()
 
# ── 1. PAGE CONFIG ─────────────────────────────────────────────────────────────
# Must be the very first Streamlit call in the script.
st.set_page_config(
    page_title="Multi-Source AI Knowledge Assistant",
    page_icon="🧠",
    layout="wide",
)
 
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #6366f1, #8b5cf6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header { color: #6b7280; margin-bottom: 1.5rem; }
    .source-box {
        background-color: #f3f4f6;
        border-left: 4px solid #8b5cf6;
        padding: 0.6rem 0.9rem;
        border-radius: 6px;
        margin-top: 0.4rem;
        font-size: 0.85rem;
    }
    .stChatMessage { border-radius: 12px; }
</style>
""", unsafe_allow_html=True)
 
 
# ── 2. SESSION STATE ────────────────────────────────────────────────────────────
def init_session_state():
    defaults = {
        "vectorstore": None,
        "chat_history": [],
        "memory": None,
        "chain": None,
        "processed_sources": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
 
init_session_state()
 
 
# ── 3. SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Settings")
 
    groq_api_key = st.text_input(
        "Groq API key",
        type="password",
        value=os.getenv("GROQ_API_KEY", ""),
        help="Free key at console.groq.com",
    )
 
    model_name = st.selectbox(
        "Model",
        ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
        help="70b = smarter. 8b = faster.",
    )
 
    st.divider()
    st.markdown("### 📥 Add Knowledge Sources")
 
    uploaded_files = st.file_uploader(
        "PDF / DOCX / TXT files",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
    )
 
    youtube_url = st.text_input(
        "YouTube link (optional)",
        placeholder="https://www.youtube.com/watch?v=...",
    )
    website_url = st.text_input(
        "Website URL (optional)",
        placeholder="https://example.com",
    )
 
    process_btn = st.button("🚀 Process Sources", use_container_width=True)
 
    st.divider()
    if st.session_state.processed_sources:
        st.markdown("### 📚 Loaded Sources")
        for src in st.session_state.processed_sources:
            st.markdown(f"- {src}")
 
    if st.button("🗑️ Clear Everything", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
 
 
# ── 4. PROCESS BUTTON ───────────────────────────────────────────────────────────
if process_btn:
    if not groq_api_key:
        st.sidebar.error("Please add your Groq API key first.")
    elif not uploaded_files and not youtube_url and not website_url:
        st.sidebar.error("Add at least one file or link before processing.")
    else:
        with st.spinner("Reading and indexing your sources..."):
            all_docs, sources_loaded = load_any_source(
                uploaded_files=uploaded_files,
                youtube_url=youtube_url or None,
                website_url=website_url or None,
                on_warning=st.sidebar.warning,
            )
 
            if all_docs:
                vectorstore = build_vectorstore(all_docs)
                chain, memory = build_chain(vectorstore, groq_api_key, model_name)
 
                st.session_state.vectorstore = vectorstore
                st.session_state.chain = chain
                st.session_state.memory = memory
                st.session_state.processed_sources = sources_loaded
                st.session_state.chat_history = []
 
                st.sidebar.success(f"✅ Indexed {len(all_docs)} section(s) from {len(sources_loaded)} source(s).")
            else:
                st.sidebar.error("Nothing could be loaded. Check the sources and try again.")
 
 
# ── 5. CHAT AREA ────────────────────────────────────────────────────────────────
st.markdown('<div class="main-header">🧠 Multi-Source AI Knowledge Assistant</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Ask questions across your PDFs, DOCX, TXT files, YouTube videos, and websites — all in one chat.</div>',
    unsafe_allow_html=True,
)
 
if st.session_state.chain is None:
    st.info("👈 Add your Groq API key and at least one source in the sidebar, then click **Process Sources** to get started.")
else:
    for role, message in st.session_state.chat_history:
        with st.chat_message(role):
            st.markdown(message)
 
    user_question = st.chat_input("Ask something about your sources...")
 
    if user_question:
        st.session_state.chat_history.append(("user", user_question))
        with st.chat_message("user"):
            st.markdown(user_question)
 
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer, sources = ask_question(st.session_state.chain, user_question)
                st.markdown(answer)
 
                if sources:
                    with st.expander("📌 Sources used for this answer"):
                        seen = set()
                        for doc in sources:
                            src = doc.metadata.get("source", "unknown")
                            page = doc.metadata.get("page")
                            label = src + (f" (page {page + 1})" if page is not None else "")
                            if label in seen:
                                continue
                            seen.add(label)
                            snippet = doc.page_content[:220].replace("\n", " ") + "..."
                            st.markdown(
                                f'<div class="source-box"><b>{label}</b><br>{snippet}</div>',
                                unsafe_allow_html=True,
                            )
 
        st.session_state.chat_history.append(("assistant", answer))
 
    if st.session_state.chat_history:
        if st.button("🧹 Clear chat history only"):
            st.session_state.chat_history = []
            st.session_state.memory.clear()
            st.rerun()
 