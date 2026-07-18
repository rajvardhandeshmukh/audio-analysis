import streamlit as st
import httpx
import time
import os

BASE_URL = "http://127.0.0.1:8000/api/v1"

st.set_page_config(page_title="Audio Analysis Pipeline", page_icon="🎙️", layout="wide")

# Initialize Session State
if "token" not in st.session_state:
    st.session_state.token = None
if "job_id" not in st.session_state:
    st.session_state.job_id = None
if "source_id" not in st.session_state:
    st.session_state.source_id = None

# Sidebar - Auth
st.sidebar.title("🔐 Login")
if not st.session_state.token:
    with st.sidebar.form("login_form"):
        email = st.text_input("Email", value="admin@example.com")
        password = st.text_input("Password", type="password", value="admin123")
        submit = st.form_submit_button("Login")
        
        if submit:
            with st.spinner("Logging in..."):
                r = httpx.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
                if r.status_code == 200:
                    st.session_state.token = r.json()["data"]["access_token"]
                    st.sidebar.success("Logged in successfully!")
                    st.rerun()
                else:
                    st.sidebar.error("Invalid credentials.")
else:
    st.sidebar.success("✅ Logged in")
    if st.sidebar.button("Logout"):
        st.session_state.token = None
        st.session_state.job_id = None
        st.rerun()


# Main Application Header
st.title("🎙️ AI Audio Analysis Pipeline")
st.markdown("Automated speech-to-text, diarization, sentiment analysis, compliance checking, and coaching notes generation.")

if not st.session_state.token:
    st.info("Please login using the sidebar to continue.")
    st.stop()

headers = {"Authorization": f"Bearer {st.session_state.token}"}

nav_tab1, nav_tab2, nav_tab3 = st.tabs(["🎙️ Analyze Call", "📂 Watcher Settings", "📑 Exported Reports Browser"])

# ==========================================
# TAB 1: Analyze Call
# ==========================================
with nav_tab1:
    st.subheader("Upload & Analyze Audio")
    uploaded_file = st.file_uploader("Upload Audio File (.mp3, .wav)", type=["mp3", "wav"])

    if uploaded_file and not st.session_state.job_id:
        if st.button("🚀 Analyze Call"):
            
            # 1. Ensure Source exists
            if not st.session_state.source_id:
                with st.spinner("Setting up storage source..."):
                    r = httpx.post(f"{BASE_URL}/sources", json={
                        "name": "Streamlit Uploads",
                        "source_type": "local_filesystem",
                        "path": "/streamlit_uploads",
                        "file_patterns": ["*.mp3", "*.wav"]
                    }, headers=headers)
                    
                    if r.status_code in (200, 201, 409):
                        if r.status_code != 409:
                            st.session_state.source_id = r.json()["data"]["id"]
                        else:
                            sources_r = httpx.get(f"{BASE_URL}/sources", headers=headers)
                            st.session_state.source_id = sources_r.json()["data"][0]["id"]
                    else:
                        st.error("Failed to create source.")
                        st.stop()

            # 2. Get Presigned URL
            with st.spinner("Getting upload permissions..."):
                r = httpx.post(f"{BASE_URL}/uploads/presign", json={
                    "file_name": uploaded_file.name,
                    "source_id": st.session_state.source_id
                }, headers=headers)
                if r.status_code != 200:
                    st.error("Failed to generate upload URL.")
                    st.stop()
                
                presign_data = r.json()["data"]
                upload_url = presign_data["upload_url"]
                storage_key = presign_data["storage_key"]
                
            # 3. Upload to MinIO
            with st.spinner("Uploading file to secure storage..."):
                audio_bytes = uploaded_file.read()
                upload_r = httpx.put(upload_url, content=audio_bytes, headers={"Content-Type": "audio/mpeg"})
                if upload_r.status_code not in (200, 204):
                    st.error("Failed to upload to storage.")
                    st.stop()

            # 4. Confirm Job
            with st.spinner("Creating analysis job..."):
                r = httpx.post(f"{BASE_URL}/uploads/confirm", json={
                    "source_id": st.session_state.source_id,
                    "file_name": uploaded_file.name,
                    "storage_key": storage_key
                }, headers=headers)
                
                if r.status_code in (200, 201):
                    st.session_state.job_id = r.json()["data"]["id"]
                    st.success("Job started successfully!")
                    st.rerun()
                else:
                    st.error("Failed to create job.")

    # Live Tracking
    if st.session_state.job_id:
        st.divider()
        st.subheader(f"🔄 Tracking Job: `{st.session_state.job_id}`")
        
        stages = ["pending", "ingesting", "stt", "repairing", "analyzing", "reporting", "completed"]
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        job_completed = False
        job_failed = False
        
        while not job_completed and not job_failed:
            try:
                r = httpx.get(f"{BASE_URL}/jobs/{st.session_state.job_id}", headers=headers)
                if r.status_code == 200:
                    status = r.json()["data"]["status"]
                    
                    if status in stages:
                        pct = (stages.index(status)) / (len(stages) - 1)
                        progress_bar.progress(pct)
                        status_text.markdown(f"**Current Stage:** `{status.upper()}`")
                    
                    if status == "completed":
                        job_completed = True
                        st.success("Pipeline Analysis Complete!")
                    elif status == "failed":
                        job_failed = True
                        error_msg = r.json()["data"].get("error_message", "Unknown error")
                        st.error(f"Job Failed: {error_msg}")
                
                if not job_completed and not job_failed:
                    time.sleep(2)
            except Exception as e:
                st.error(f"Lost connection to API: {e}")
                break
                
        if st.button("Reset / Analyze Another File"):
            st.session_state.job_id = None
            st.rerun()

        # Dashboard / Results
        if job_completed:
            st.divider()
            st.header("📊 Final Analysis Report")
            
            res_tab1, res_tab2, res_tab3 = st.tabs(["AI Coaching & Scores", "Call Metrics", "Transcript"])
            
            analysis_data = httpx.get(f"{BASE_URL}/jobs/{st.session_state.job_id}/analysis", headers=headers).json().get("data", {})
            transcript_data = httpx.get(f"{BASE_URL}/jobs/{st.session_state.job_id}/transcript", headers=headers).json().get("data", {})
            
            with res_tab1:
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("Performance Scores")
                    st.metric("Agent Performance", f"{analysis_data.get('agent_performance_score', 0)} / 100")
                    st.metric("Customer Satisfaction", f"{analysis_data.get('customer_satisfaction_score', 0)} / 100")
                    st.metric("Call Resolution", f"{analysis_data.get('call_resolution_score', 0)} / 100")
                    st.metric("Empathy", f"{analysis_data.get('empathy_score', 0)} / 100")
                    st.metric("Closing Effectiveness", f"{analysis_data.get('closing_effectiveness_score', 0)} / 100")
                    
                with col2:
                    st.subheader("AI Coaching Notes")
                    st.info(analysis_data.get("summary", ""))
                    st.markdown("**Strengths:**")
                    for s in analysis_data.get("strengths", []):
                        st.markdown(f"- ✅ {s}")
                    st.markdown("**Improvement Areas:**")
                    for i in analysis_data.get("improvement_areas", []):
                        st.markdown(f"- 🔧 {i}")
                    
                    st.markdown("**Recommendation:**")
                    st.write(analysis_data.get("recommendation", ""))
                    
                    st.markdown("**Detailed Coaching:**")
                    st.write(analysis_data.get("coaching_notes", ""))
                    
            with res_tab2:
                metrics = analysis_data.get("call_metrics", {})
                st.subheader("Talk Time Distribution")
                
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Agent Talk Time", f"{metrics.get('agent_talk_time_pct', 0):.1f}%")
                c2.metric("Customer Talk Time", f"{metrics.get('customer_talk_time_pct', 0):.1f}%")
                c3.metric("Silence", f"{metrics.get('silence_pct', 0):.1f}%")
                c4.metric("Interruptions", f"{metrics.get('interruption_count', 0)}")
                
                st.subheader("Compliance")
                if analysis_data.get("compliance_passed"):
                    st.success("✅ Passed all compliance checks")
                else:
                    st.error("❌ Failed compliance checks")
                for flag in analysis_data.get("compliance_flags", []):
                    st.warning(flag.get("description", str(flag)))
                    
            with res_tab3:
                st.subheader("Full Transcript (Repaired & Diarized)")
                st.caption(f"Language: {transcript_data.get('language')} | Confidence: {transcript_data.get('confidence', 0):.0%}")
                
                for seg in transcript_data.get("segments", []):
                    speaker = seg.get("speaker_id", "?")
                    text = seg.get("text", "")
                    
                    if "agent" in str(speaker).lower() or speaker == "SPEAKER_00":
                        st.info(f"**[{speaker}]** {text}")
                    else:
                        st.success(f"**[{speaker}]** {text}")

# ==========================================
# TAB 2: Watcher Settings
# ==========================================
with nav_tab2:
    st.header("📂 Automated Folder Watcher")
    st.markdown("Configure local directories for background automated ingestion. Files placed in watched folders are tracked via SHA-256 fingerprinting to prevent repeat analysis.")
    
    with st.form("watcher_form"):
        watch_dir = st.text_input("Local Folder Path to Watch", value="D:/projects/audio-analysis/drop_zone")
        patterns_str = st.text_input("File Patterns (comma separated)", value="*.mp3, *.wav")
        source_name = st.text_input("Source Name", value="Local Drop Zone")
        save_watcher = st.form_submit_button("💾 Save Watcher Source")
        
        if save_watcher:
            patterns = [p.strip() for p in patterns_str.split(",") if p.strip()]
            with st.spinner("Configuring watcher source..."):
                r = httpx.post(f"{BASE_URL}/sources", json={
                    "name": source_name,
                    "source_type": "local_filesystem",
                    "path": watch_dir,
                    "file_patterns": patterns
                }, headers=headers)
                if r.status_code in (200, 201):
                    st.success(f"Watcher source '{source_name}' configured for path `{watch_dir}`!")
                elif r.status_code == 409:
                    st.warning(f"A source for path `{watch_dir}` already exists.")
                else:
                    st.error(f"Failed to save watcher source: {r.text}")

    st.divider()
    st.subheader("Configured Storage Sources")
    if st.button("🔄 Refresh Sources"):
        st.rerun()
        
    try:
        r = httpx.get(f"{BASE_URL}/sources", headers=headers)
        if r.status_code == 200:
            sources = r.json().get("data", [])
            if sources:
                for s in sources:
                    st.markdown(f"- **{s.get('name')}** (`{s.get('source_type')}`) — Path: `{s.get('path')}` | Patterns: `{', '.join(s.get('file_patterns', []))}`")
            else:
                st.info("No sources configured yet.")
    except Exception as e:
        st.error(f"Could not fetch sources: {e}")

# ==========================================
# TAB 3: Exported Reports Browser
# ==========================================
with nav_tab3:
    st.header("📑 Exported Reports Browser")
    st.markdown("Browse and download formatted text (`.txt`) reports generated for each analyzed audio file.")
    
    export_dir = "D:/projects/audio-analysis/exported_reports"
    if not os.path.exists(export_dir):
        st.info(f"No exported reports directory found yet (`{export_dir}`). Reports will appear here once calls finish processing.")
    else:
        if st.button("🔄 Refresh Reports List"):
            st.rerun()
            
        files = sorted(
            [f for f in os.listdir(export_dir) if f.endswith(".txt")],
            key=lambda x: os.path.getmtime(os.path.join(export_dir, x)),
            reverse=True
        )
        if not files:
            st.info(f"No `.txt` report files found in `{export_dir}`.")
        else:
            selected_file = st.selectbox("Select Report File", files)
            if selected_file:
                file_path = os.path.join(export_dir, selected_file)
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption(f"Path: `{file_path}`")
                with col2:
                    st.download_button(
                        label="⬇️ Download .txt Report",
                        data=content,
                        file_name=selected_file,
                        mime="text/plain",
                        use_container_width=True
                    )
                st.text_area("Report Content Preview", value=content, height=600, disabled=True)
