import sys
import youtube_transcript_api
 
print("="*80)
print("PYTHON :", sys.executable)
print("YT API :", youtube_transcript_api.__file__)
print("YT API version :", getattr(youtube_transcript_api, "__version__", "unknown"))
print("YT API members :", dir(youtube_transcript_api.YouTubeTranscriptApi))
print("="*80)
 
import os
import re
import tempfile
import traceback
 
from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader,
    WebBaseLoader,
)
 
from youtube_transcript_api import YouTubeTranscriptApi
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_groq import ChatGroq
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationalRetrievalChain
 
 
# ===============================================================================
# 1. DOCUMENT LOADERS
# ===============================================================================
 
def load_pdf(uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name
 
    loader = PyPDFLoader(tmp_path)
    docs = loader.load()
 
    for doc in docs:
        doc.metadata["source"] = uploaded_file.name
    os.unlink(tmp_path)
    return docs
 
 
def load_docx(uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name
 
    loader = Docx2txtLoader(tmp_path)
    docs = loader.load()
 
    for doc in docs:
        doc.metadata["source"] = uploaded_file.name
    os.unlink(tmp_path)
    return docs
 
 
def load_txt(uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="wb") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name
 
    loader = TextLoader(tmp_path, encoding="utf-8")
    docs = loader.load()
 
    for doc in docs:
        doc.metadata["source"] = uploaded_file.name
    os.unlink(tmp_path)
    return docs
 
 
def _extract_video_id(url: str) -> str:
    """Pull the 11-character video ID out of any common YouTube URL format.
 
    Handles:
        https://www.youtube.com/watch?v=VIDEO_ID
        https://youtu.be/VIDEO_ID
        https://youtube.com/shorts/VIDEO_ID
        https://www.youtube.com/embed/VIDEO_ID
    """
    patterns = [
        r"(?:v=)([A-Za-z0-9_-]{11})",              # ?v=...
        r"youtu\.be/([A-Za-z0-9_-]{11})",           # youtu.be/...
        r"/(?:shorts|embed)/([A-Za-z0-9_-]{11})",   # /shorts/ or /embed/
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(
        f"Could not extract a YouTube video ID from this URL: {url}\n"
        "Make sure it's a full YouTube link, e.g. https://www.youtube.com/watch?v=VIDEO_ID"
    )
 
 
def load_youtube(url):
    """
    Load transcript from a YouTube video using youtube-transcript-api.
 
    IMPORTANT: youtube-transcript-api v1.x removed the old classmethods
    `YouTubeTranscriptApi.get_transcript(...)` and
    `YouTubeTranscriptApi.list_transcripts(...)`.
    You must now instantiate the class and call `.fetch()` / `.list()`
    on the instance. The returned object is also no longer a list of
    dicts — it's a `FetchedTranscript` whose items are
    `FetchedTranscriptSnippet` objects, accessed via `.text`, `.start`,
    `.duration` (attributes, not dict keys).
    """
    video_id = _extract_video_id(url)
    print("Video ID:", video_id)
 
    ytt_api = YouTubeTranscriptApi()
 
    try:
        # Try Hindi first, then English, matching your original preference order.
        fetched = ytt_api.fetch(video_id, languages=["hi", "en"])
    except Exception as first_error:
        # Fallback: enumerate whatever transcripts actually exist for this
        # video (manual or auto-generated, any language) and use the best match.
        try:
            transcript_list = ytt_api.list(video_id)
            try:
                transcript = transcript_list.find_transcript(["hi", "en"])
            except Exception:
                transcript = next(iter(transcript_list))
            fetched = transcript.fetch()
        except Exception:
            # Re-raise the original error if the fallback also fails —
            # gives a clearer message (e.g. "TranscriptsDisabled").
            raise first_error
 
    # fetched is a FetchedTranscript: iterating yields FetchedTranscriptSnippet
    # objects with a `.text` attribute (NOT a dict with a "text" key).
    text = " ".join(snippet.text for snippet in fetched)
 
    return [
        Document(
            page_content=text,
            metadata={"source": url},
        )
    ]
 
 
def load_website(url: str) -> list[Document]:
    """Scrapes readable text from a webpage."""
    loader = WebBaseLoader(url)
    docs = loader.load()
    for doc in docs:
        doc.metadata["source"] = url
    return docs
 
 
def load_any_source(
    uploaded_files=None,
    youtube_url: str = None,
    website_url: str = None,
    on_warning=None,
):
    """One-stop loader: pass in whatever sources you have, get back
    (all_docs, sources_loaded).
 
    `on_warning` is an optional callback (e.g. st.sidebar.warning) so
    errors surface in the UI without this module importing Streamlit.
    """
    all_docs = []
    sources_loaded = []
 
    def warn(msg):
        if on_warning:
            on_warning(msg)
 
    for f in uploaded_files or []:
        ext = f.name.split(".")[-1].lower()
        try:
            if ext == "pdf":
                all_docs.extend(load_pdf(f))
            elif ext == "docx":
                all_docs.extend(load_docx(f))
            elif ext == "txt":
                all_docs.extend(load_txt(f))
            else:
                warn(f"Unsupported file type skipped: {f.name}")
                continue
            sources_loaded.append(f"📄 {f.name}")
        except Exception as e:
            warn(f"Couldn't read {f.name}: {e}")
 
    if youtube_url:
        try:
            all_docs.extend(load_youtube(youtube_url))
            sources_loaded.append(f"▶️ {youtube_url}")
        except Exception as e:
            traceback.print_exc()
            warn(f"Couldn't read YouTube link: {e}")
 
    if website_url:
        try:
            all_docs.extend(load_website(website_url))
            sources_loaded.append(f"🌐 {website_url}")
        except Exception as e:
            warn(f"Couldn't read website: {e}")
 
    return all_docs, sources_loaded
 
 
# ===============================================================================
# 2. INGESTION PIPELINE — chunk → embed → store
# ===============================================================================
 
def build_vectorstore(all_docs, persist_directory=None):
    """Chunk documents, embed with a free local HuggingFace model, store in
    ChromaDB.
 
    Pass persist_directory="./chroma_db" for a store that survives restarts;
    leave it None for a fresh in-memory store each session.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(all_docs)
 
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
 
    kwargs = {
        "documents": chunks,
        "embedding": embeddings,
        "collection_name": "knowledge_base",
    }
    if persist_directory:
        kwargs["persist_directory"] = persist_directory
 
    vectorstore = Chroma.from_documents(**kwargs)
    return vectorstore
 
 
def build_chain(vectorstore, groq_api_key: str, model_name: str = "llama-3.3-70b-versatile"):
    """Wires together the LLM, retriever, and conversation memory into one
    chain that can answer follow-up questions and return source chunks."""
    llm = ChatGroq(
        groq_api_key=groq_api_key,
        model_name=model_name,
        temperature=0.2,
    )
 
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
        output_key="answer",
    )
 
    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=vectorstore.as_retriever(search_kwargs={"k": 4}),
        memory=memory,
        return_source_documents=True,
    )
    return chain, memory
 
 
def ask_question(chain, question: str):
    """Ask a question; returns (answer_text, source_documents)."""
    result = chain.invoke({"question": question})
    return result["answer"], result.get("source_documents", [])