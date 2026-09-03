import streamlit as st
import requests
import json
import time
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="Campus Assistant",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700&family=Inter:wght@300;400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

h1, h2, h3, .sidebar-title {
    font-family: 'Syne', sans-serif !important;
}

.stApp {
    background: #0f0f11;
    color: #e8e6e0;
}

section[data-testid="stSidebar"] {
    background: #141416;
    border-right: 1px solid #2a2a2e;
}

.stButton > button {
    background: #1e1e22;
    color: #e8e6e0;
    border: 1px solid #2e2e34;
    border-radius: 8px;
    font-family: 'Inter', sans-serif;
    font-size: 13px;
    transition: all 0.2s;
}
.stButton > button:hover {
    background: #2a2a30;
    border-color: #8b5cf6;
    color: #c4b5fd;
}

.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    background: #1e1e22 !important;
    border: 1px solid #2e2e34 !important;
    color: #e8e6e0 !important;
    border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important;
}

.stSelectbox > div > div {
    background: #1e1e22;
    border: 1px solid #2e2e34;
    color: #e8e6e0;
}

.metric-card {
    background: #1e1e22;
    border: 1px solid #2e2e34;
    border-radius: 12px;
    padding: 16px 20px;
    margin: 8px 0;
}

.source-chip {
    display: inline-block;
    background: #1e1e22;
    border: 1px solid #2e2e34;
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 12px;
    color: #a09e99;
    margin: 3px;
}

.source-chip.high {
    border-color: #22c55e44;
    color: #4ade80;
}

.intent-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 500;
    margin-left: 8px;
}

.intent-casual        { background: #1e3a2f; color: #4ade80; }
.intent-personal_rag  { background: #2d1f4e; color: #a78bfa; }
.intent-conversational{ background: #1a2d3d; color: #60a5fa; }
.intent-introspect    { background: #3d2a1a; color: #fb923c; }

.stChatMessage {
    background: transparent !important;
}

[data-testid="stChatMessageContent"] {
    background: #1e1e22 !important;
    border: 1px solid #2e2e34 !important;
    border-radius: 12px !important;
}

.stFileUploader {
    background: #1e1e22;
    border: 1px dashed #2e2e34;
    border-radius: 12px;
}

.stTabs [data-baseweb="tab-list"] {
    background: #141416;
    border-bottom: 1px solid #2e2e34;
}

.stTabs [data-baseweb="tab"] {
    color: #6b6966;
    font-family: 'Inter', sans-serif;
    font-size: 13px;
}

.stTabs [aria-selected="true"] {
    color: #a78bfa !important;
    border-bottom-color: #8b5cf6 !important;
}

div[data-testid="stExpander"] {
    background: #1e1e22;
    border: 1px solid #2e2e34;
    border-radius: 10px;
}

.stSuccess {
    background: #1a2e1a !important;
    color: #4ade80 !important;
}

.stError {
    background: #2e1a1a !important;
    color: #f87171 !important;
}

.stWarning {
    background: #2e2a1a !important;
    color: #fbbf24 !important;
}

.stSpinner > div {
    border-top-color: #8b5cf6 !important;
}

hr {
    border-color: #2e2e34 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Session state init ─────────────────────────────────────────────────────────
if "api_key"          not in st.session_state: st.session_state.api_key = ""
if "notion_token"     not in st.session_state: st.session_state.notion_token = ""
if "user_id"          not in st.session_state: st.session_state.user_id = ""
if "conversation_id"  not in st.session_state: st.session_state.conversation_id = ""
if "messages"         not in st.session_state: st.session_state.messages = []
if "conversations"    not in st.session_state: st.session_state.conversations = []
if "last_intent"      not in st.session_state: st.session_state.last_intent = ""

# ── API helpers ────────────────────────────────────────────────────────────────

def api(method, path, **kwargs):
    try:
        r = getattr(requests, method)(f"{API_BASE}{path}", timeout=60, **kwargs)
        return r.json(), r.status_code
    except requests.exceptions.ConnectionError:
        return {"detail": "Backend not running. Start with: uvicorn main:app --reload"}, 503
    except Exception as e:
        return {"detail": str(e)}, 500

def connected():
    data, code = api("get", "/health")
    return code == 200

# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("<h2 style='font-family:Syne;font-size:22px;margin:0 0 4px'>Campus Assistant</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color:#6b6966;font-size:13px;margin:0 0 16px'>AI-powered personal study assistant</p>", unsafe_allow_html=True)

    # Connection status
    if connected():
        st.markdown("<div style='display:flex;align-items:center;gap:8px;margin-bottom:16px'><div style='width:8px;height:8px;border-radius:50%;background:#4ade80'></div><span style='color:#4ade80;font-size:12px'>Backend connected</span></div>", unsafe_allow_html=True)
    else:
        st.markdown("<div style='display:flex;align-items:center;gap:8px;margin-bottom:16px'><div style='width:8px;height:8px;border-radius:50%;background:#f87171'></div><span style='color:#f87171;font-size:12px'>Backend offline</span></div>", unsafe_allow_html=True)

    st.divider()

    # Settings
    with st.expander("⚙️ Settings", expanded=not st.session_state.api_key):
        uid = st.text_input("User ID", value=st.session_state.user_id, placeholder="student1")
        key = st.text_input("Gemini API Key", value=st.session_state.api_key, type="password", placeholder="AIza...")
        notion = st.text_input("Notion Token (optional)", value=st.session_state.notion_token, type="password", placeholder="secret_...")
        if st.button("Save settings", use_container_width=True):
            st.session_state.user_id = uid
            st.session_state.api_key = key
            st.session_state.notion_token = notion
            st.success("Saved")

    st.divider()

    # Conversations
    st.markdown("<p style='font-family:Syne;font-size:14px;font-weight:600;margin:0 0 8px'>Conversations</p>", unsafe_allow_html=True)

    if st.button("+ New conversation", use_container_width=True):
        if not st.session_state.user_id:
            st.error("Set a user ID first")
        else:
            data, code = api("post", "/conversations/new", json={"user_id": st.session_state.user_id})
            if code == 200:
                st.session_state.conversation_id = data["conversation_id"]
                st.session_state.messages = []
                st.session_state.last_intent = ""
                st.rerun()
            else:
                st.error(data.get("detail", "Error"))

    if st.session_state.user_id:
        convs, code = api("get", f"/conversations/{st.session_state.user_id}")
        if code == 200:
            for conv in convs.get("conversations", [])[:8]:
                is_active = conv["conversation_id"] == st.session_state.conversation_id
                label = conv["title"][:32] + ("..." if len(conv["title"]) > 32 else "")
                btn_style = "border-left: 2px solid #8b5cf6;" if is_active else ""
                if st.button(f"{'▶ ' if is_active else ''}{label}", key=conv["conversation_id"], use_container_width=True):
                    st.session_state.conversation_id = conv["conversation_id"]
                    # Load history
                    hist, hcode = api("get", f"/conversations/{conv['conversation_id']}/history")
                    if hcode == 200:
                        st.session_state.messages = [
                            {"role": m["role"], "content": m["content"]}
                            for m in hist.get("messages", [])
                        ]
                    st.rerun()
                st.markdown(f"<p style='color:#4a4a50;font-size:11px;margin:-6px 0 4px 4px'>{conv['last_active'][:10]}</p>", unsafe_allow_html=True)

    st.divider()

    # Library stats
    st.markdown("<p style='font-family:Syne;font-size:14px;font-weight:600;margin:0 0 8px'>My Library</p>", unsafe_allow_html=True)
    if st.session_state.user_id:
        stats, code = api("get", f"/my/docs/{st.session_state.user_id}")
        if code == 200:
            st.markdown(f"""
            <div class='metric-card'>
                <div style='font-size:24px;font-weight:600;color:#a78bfa;font-family:Syne'>{stats.get('doc_count', 0)}</div>
                <div style='font-size:12px;color:#6b6966'>chunks indexed</div>
            </div>
            """, unsafe_allow_html=True)

# ── Main area ──────────────────────────────────────────────────────────────────

tab_chat, tab_upload, tab_image, tab_youtube, tab_notion = st.tabs([
    "💬 Chat", "📄 Upload to Library", "🖼️ Image", "🎬 YouTube Tool", "📤 Notion"
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — CHAT
# ══════════════════════════════════════════════════════════════════════════════

with tab_chat:
    if not st.session_state.conversation_id:
        st.markdown("""
        <div style='text-align:center;padding:80px 20px;color:#4a4a50'>
            <div style='font-size:40px;margin-bottom:16px'>📚</div>
            <div style='font-family:Syne;font-size:20px;color:#6b6966;margin-bottom:8px'>No conversation selected</div>
            <div style='font-size:14px'>Create a new conversation from the sidebar to start chatting</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Intent badge
        if st.session_state.last_intent:
            intent = st.session_state.last_intent
            intent_labels = {
                "casual": "Casual",
                "personal_rag": "RAG retrieval",
                "conversational": "Conversational",
                "introspect": "Introspect"
            }
            st.markdown(f"""
            <div style='margin-bottom:12px'>
                <span style='color:#4a4a50;font-size:12px'>Last intent:</span>
                <span class='intent-badge intent-{intent}'>{intent_labels.get(intent, intent)}</span>
            </div>
            """, unsafe_allow_html=True)

        # Chat history
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("sources"):
                    with st.expander("📎 Sources", expanded=False):
                        for src in msg["sources"]:
                            score = src.get("score", 0)
                            cls = "high" if score > 0.7 else ""
                            page = f" · p{src['page']}" if src.get("page") != "" else ""
                            st.markdown(f"""
                            <span class='source-chip {cls}'>
                                {src['doc_title']}{page} · {score:.2f}
                            </span>
                            """, unsafe_allow_html=True)

        # Chat input
        if prompt := st.chat_input("Ask anything about your notes..."):
            if not st.session_state.api_key:
                st.error("Add your Gemini API key in Settings")
            else:
                # Show user message immediately
                with st.chat_message("user"):
                    st.markdown(prompt)

                # Call backend
                with st.chat_message("assistant"):
                    with st.spinner(""):
                        data, code = api("post", "/chat", json={
                            "user_id":         st.session_state.user_id,
                            "message":         prompt,
                            "conversation_id": st.session_state.conversation_id,
                            "api_key":         st.session_state.api_key,
                            "fast_mode":       False,
                        })

                    if code == 200:
                        response = data.get("response", "")
                        sources  = data.get("sources", [])
                        intent   = data.get("intent", "")

                        st.markdown(response)

                        if sources:
                            with st.expander("📎 Sources", expanded=False):
                                for src in sources:
                                    score = src.get("score", 0)
                                    cls = "high" if score > 0.7 else ""
                                    page = f" · p{src['page']}" if src.get("page") != "" else ""
                                    st.markdown(f"""
                                    <span class='source-chip {cls}'>
                                        {src['doc_title']}{page} · {score:.2f}
                                    </span>
                                    """, unsafe_allow_html=True)

                        # Save to session
                        st.session_state.messages.append({"role": "user", "content": prompt})
                        st.session_state.messages.append({"role": "assistant", "content": response, "sources": sources})
                        st.session_state.last_intent = intent
                        st.rerun()
                    else:
                        st.error(data.get("detail", "Something went wrong"))

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — UPLOAD TO LIBRARY
# ══════════════════════════════════════════════════════════════════════════════

with tab_upload:
    st.markdown("<h3 style='font-family:Syne'>Add to your knowledge base</h3>", unsafe_allow_html=True)
    st.markdown("<p style='color:#6b6966;font-size:14px'>Files uploaded here are permanently indexed and searchable in chat.</p>", unsafe_allow_html=True)

    up1, up2 = st.columns(2)

    with up1:
        st.markdown("#### 📄 PDF")
        pdf_file  = st.file_uploader("Choose a PDF", type=["pdf"], key="pdf_upload")
        pdf_title = st.text_input("Document title (optional)", placeholder="ERA Research Notes", key="pdf_title")
        pdf_type  = st.selectbox("Document type", ["pdf", "syllabus", "notes", "exam", "hostel", "general"], key="pdf_type")

        if st.button("Upload and index PDF", disabled=pdf_file is None, use_container_width=True):
            if not st.session_state.user_id:
                st.error("Set a user ID in Settings first")
            else:
                with st.spinner("Chunking and indexing..."):
                    data, code = api("post", "/ingest/pdf",
                        files={"file": (pdf_file.name, pdf_file.getvalue(), "application/pdf")},
                        data={"user_id": st.session_state.user_id, "doc_title": pdf_title, "doc_type": pdf_type}
                    )
                if code == 200:
                    st.success(f"✓ Added {data.get('chunks_added', 0)} chunks from {data.get('file', '')}")
                else:
                    st.error(data.get("detail", "Upload failed"))

    with up2:
        st.markdown("#### 🖼️ Image (OCR → RAG)")
        img_file  = st.file_uploader("Choose an image", type=["jpg","jpeg","png","webp"], key="img_rag_upload")
        img_title = st.text_input("Image title (optional)", placeholder="Lecture notes photo", key="img_rag_title")

        if st.button("Upload and index image", disabled=img_file is None, use_container_width=True):
            if not st.session_state.user_id:
                st.error("Set a user ID in Settings first")
            else:
                with st.spinner("Running OCR and indexing..."):
                    data, code = api("post", "/ingest/image",
                        files={"file": (img_file.name, img_file.getvalue(), img_file.type)},
                        data={"user_id": st.session_state.user_id, "doc_title": img_title}
                    )
                if code == 200:
                    st.success(f"✓ {data.get('chunks_added', 0)} chunks added · {data.get('extracted_chars', 0)} chars extracted")
                else:
                    st.error(data.get("detail", "Upload failed"))

    st.divider()

    # Library contents
    st.markdown("#### Current library")
    if st.session_state.user_id:
        if st.button("Refresh", key="refresh_lib"):
            st.rerun()
        stats, code = api("get", f"/my/docs/{st.session_state.user_id}")
        if code == 200:
            st.markdown(f"""
            <div class='metric-card'>
                <b style='color:#a78bfa'>{stats.get('doc_count', 0)}</b>
                <span style='color:#6b6966;font-size:13px'> chunks indexed in {stats.get('collection', '')}</span>
            </div>
            """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — IMAGE (Ephemeral context)
# ══════════════════════════════════════════════════════════════════════════════

with tab_image:
    st.markdown("<h3 style='font-family:Syne'>Image — visual Q&A</h3>", unsafe_allow_html=True)
    st.markdown("<p style='color:#6b6966;font-size:14px'>Drop an image in conversation — OCR + Gemma 4 vision analyses it. Saved to your active chat thread if provided.</p>", unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1])

    with col1:
        ctx_img  = st.file_uploader("Upload image", type=["jpg","jpeg","png","webp"], key="ctx_img")
        ctx_q    = st.text_area("Your question about this image", placeholder="Explain the diagram in this image", height=100)
        use_conv = st.checkbox("Save to active conversation", value=True)

        if st.button("Analyse image", disabled=ctx_img is None, use_container_width=True):
            if not st.session_state.api_key:
                st.error("Add your Gemini API key in Settings")
            else:
                conv_id = st.session_state.conversation_id if use_conv else ""
                with st.spinner("Running OCR + Gemma 4 vision..."):
                    data, code = api("post", "/context/image",
                        files={"file": (ctx_img.name, ctx_img.getvalue(), ctx_img.type)},
                        data={
                            "user_id":         st.session_state.user_id,
                            "question":        ctx_q,
                            "conversation_id": conv_id,
                            "api_key":         st.session_state.api_key,
                        }
                    )
                if code == 200:
                    st.session_state["img_result"] = data
                else:
                    st.error(data.get("detail", "Error"))

    with col2:
        if ctx_img:
            st.image(ctx_img, use_container_width=True)

        if "img_result" in st.session_state:
            res = st.session_state["img_result"]
            st.divider()
            st.markdown("**Response**")
            st.markdown(res.get("response", ""))

            if res.get("has_text") and res.get("ocr_text"):
                with st.expander("📝 Extracted text (OCR)"):
                    st.text(res["ocr_text"])

            if use_conv and st.session_state.conversation_id:
                st.success("Saved to active conversation — ask follow-ups in Chat tab")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — YOUTUBE TOOL
# ══════════════════════════════════════════════════════════════════════════════

with tab_youtube:
    st.markdown("<h3 style='font-family:Syne'>YouTube Transcript Tool</h3>", unsafe_allow_html=True)
    st.markdown("<p style='color:#6b6966;font-size:14px'>Fetch, process, and copy YouTube transcripts. Optionally save to your active chat.</p>", unsafe_allow_html=True)

    yt_url = st.text_input("YouTube URL", placeholder="https://youtu.be/...")

    col1, col2 = st.columns([1, 2])

    with col1:
        lang_options = []
        if yt_url:
            if st.button("Fetch languages"):
                with st.spinner("Checking available languages..."):
                    data, code = api("get", f"/tools/youtube/languages", params={"url": yt_url})
                if code == 200:
                    st.session_state["yt_langs"] = data.get("languages", [])
                    st.session_state["yt_video_id"] = data.get("video_id", "")
                else:
                    st.error(data.get("detail", "Could not fetch languages"))

        if st.session_state.get("yt_langs"):
            langs = st.session_state["yt_langs"]
            lang_labels = [f"{l['name']} {'(auto)' if l['auto_generated'] else ''}" for l in langs]
            selected_idx = st.selectbox("Transcript language", range(len(langs)), format_func=lambda i: lang_labels[i])
            selected_lang = langs[selected_idx]["code"]
            auto_gen = langs[selected_idx]["auto_generated"]
            if auto_gen:
                st.warning("Auto-generated captions — may contain errors")

            style = st.selectbox("Processing style", [
                "bullet_summary", "detailed", "eli5", "raw", "custom"
            ], format_func=lambda x: {
                "bullet_summary": "Bullet summary",
                "detailed":       "Detailed paragraphs",
                "eli5":           "ELI5 (simple)",
                "raw":            "Raw transcript",
                "custom":         "Custom prompt",
            }[x])

            custom_prompt = ""
            if style == "custom":
                custom_prompt = st.text_area("Your prompt", placeholder="List all technical terms mentioned...")

            out_lang = st.selectbox("Output language", ["English", "Hindi", "Kannada", "Tamil", "Telugu", "Bengali"])

            save_to_chat = st.checkbox("Save to active conversation", value=False)

            if st.button("Process transcript", use_container_width=True):
                if not st.session_state.api_key:
                    st.error("Add your Gemini API key in Settings")
                else:
                    with st.spinner("Fetching and processing..."):
                        payload = {
                            "url":             yt_url,
                            "language_code":   selected_lang,
                            "prompt_style":    style,
                            "custom_prompt":   custom_prompt,
                            "output_language": out_lang,
                            "api_key":         st.session_state.api_key,
                        }
                        if save_to_chat and st.session_state.conversation_id:
                            payload["conversation_id"] = st.session_state.conversation_id
                            payload["user_id"]         = st.session_state.user_id

                        data, code = api("post", "/tools/youtube", json=payload)
                    if code == 200:
                        st.session_state["yt_result"] = data
                    else:
                        st.error(data.get("detail", "Error"))

    with col2:
        if "yt_result" in st.session_state:
            res = st.session_state["yt_result"]
            st.markdown(f"""
            <div style='display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap'>
                <span class='source-chip'>Video: {res.get('video_id','')}</span>
                <span class='source-chip'>Language: {res.get('detected_language','')}</span>
                <span class='source-chip'>Output: {res.get('output_language','')}</span>
                {'<span class="source-chip" style="color:#fbbf24;border-color:#fbbf2444">Auto-generated</span>' if res.get('auto_generated') else ''}
            </div>
            """, unsafe_allow_html=True)

            st.markdown("**Processed output**")
            st.markdown(res.get("processed_text", ""))

            st.divider()
            with st.expander("📄 Raw transcript"):
                st.text_area("", value=res.get("raw_transcript", ""), height=200, key="raw_transcript_area")

            if res.get("prompt_style") != "raw":
                st.text_area("Copy processed text", value=res.get("processed_text", ""), height=150, key="copy_processed")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — NOTION PUSH
# ══════════════════════════════════════════════════════════════════════════════

with tab_notion:
    st.markdown("<h3 style='font-family:Syne'>Push to Notion</h3>", unsafe_allow_html=True)
    st.markdown("<p style='color:#6b6966;font-size:14px'>Save any assistant response directly to your Notion workspace.</p>", unsafe_allow_html=True)

    if not st.session_state.user_id:
        st.warning("Set a user ID in Settings first.")
    else:
        # ── Check connection status ───────────────────────────────────────────
        status, scode = api("get", f"/notion/status/{st.session_state.user_id}")
        notion_connected = scode == 200 and status.get("connected", False)

        # ── Setup section ─────────────────────────────────────────────────────
        with st.expander("⚙️ Notion Setup", expanded=not notion_connected):
            if notion_connected:
                st.success("✓ Notion connected")
                st.markdown(f"<p style='color:#6b6966;font-size:12px'>Page ID: {status.get('notion_page_id','')}</p>", unsafe_allow_html=True)

            st.markdown("""
            <div style='background:#1e1e22;border:1px solid #2e2e34;border-radius:10px;padding:16px;margin-bottom:16px'>
                <p style='font-family:Syne;font-size:14px;margin:0 0 8px'>Setup steps</p>
                <ol style='color:#6b6966;font-size:13px;margin:0;padding-left:20px;line-height:1.8'>
                    <li>Go to <b style='color:#a09e99'>notion.so/my-integrations</b></li>
                    <li>Create integration → copy the secret token</li>
                    <li>Open your Notion page → ··· → Connections → add integration</li>
                    <li>Copy the page URL or ID and paste below</li>
                </ol>
            </div>
            """, unsafe_allow_html=True)

            setup_key     = st.text_input("Notion integration token", type="password", placeholder="secret_...")
            setup_page_id = st.text_input("Notion master page URL or ID", placeholder="https://notion.so/... or page-id")

            if st.button("Connect Notion", use_container_width=True,
                         disabled=not (setup_key and setup_page_id)):
                with st.spinner("Connecting..."):
                    data, code = api("post", "/notion/setup", json={
                        "user_id":        st.session_state.user_id,
                        "notion_key":     setup_key,
                        "notion_page_id": setup_page_id,
                    })
                if code == 200:
                    st.success("✓ Notion connected successfully")
                    st.rerun()
                else:
                    st.error(data.get("detail", "Connection failed. Check your token and page ID."))

        st.divider()

        # ── Push section ──────────────────────────────────────────────────────
        if not notion_connected:
            st.info("Connect Notion above before pushing content.")
        else:
            st.markdown("<p style='color:#6b6966;font-size:13px'>Copy any assistant response from Chat and paste it here, or write your own notes.</p>", unsafe_allow_html=True)

            notion_title   = st.text_input("Page title (optional)",
                                           placeholder="Leave empty to auto-generate from date + content")
            notion_content = st.text_area("Content to push", height=250,
                                          placeholder="Paste assistant response or your notes here...")

            if st.button("Push to Notion", use_container_width=True,
                         disabled=not notion_content.strip()):
                with st.spinner("Creating Notion page..."):
                    data, code = api("post", "/notion/push", json={
                        "user_id":    st.session_state.user_id,
                        "content":    notion_content,
                        "page_title": notion_title,
                    })
                if code == 200:
                    st.success("✓ Page created in Notion")
                    if data.get("page_url"):
                        st.markdown(f"**[Open in Notion →]({data['page_url']})**")
                    st.markdown(f"<p style='color:#6b6966;font-size:12px'>Title: {data.get('title','')}</p>",
                                unsafe_allow_html=True)
                else:
                    st.error(data.get("detail", "Push failed"))