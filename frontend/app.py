import streamlit as st
import httpx
import time
import os

BASE_URL = "http://localhost:8000/api/v1"

st.set_page_config(page_title=" Audio analysis", page_icon="🎙️", layout="wide")

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


# Main Application
st.title("🎙️ AI Audio Analysis Pipeline")
st.markdown("Upload a sales call to transcribe, analyze sentiment, and generate coaching notes.")

if not st.session_state.token:
    st.info("Please login using the sidebar to continue.")
    st.stop()

headers = {"Authorization": f"Bearer {st.session_state.token}"}

# --- 1. File Upload ---
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
                    # We might get 409 if it exists, but the API doesn't return the ID on 409 usually.
                    # This is just a basic demo.
                    if r.status_code != 409:
                        st.session_state.source_id = r.json()["data"]["id"]
                    else:
                        # Fallback if already exists: just get all sources and find one.
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

# --- 2. Live Tracking ---
if st.session_state.job_id:
    st.divider()
    st.subheader(f"🔄 Tracking Job: `{st.session_state.job_id}`")
    
    # Progress Bar mapping
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

    # --- 3. Dashboard / Results ---
    if job_completed:
        st.divider()
        st.header("📊 Final Analysis Report")
        
        tab1, tab2, tab3 = st.tabs(["AI Coaching & Scores", "Call Metrics", "Transcript"])
        
        # Fetch data
        analysis_data = httpx.get(f"{BASE_URL}/jobs/{st.session_state.job_id}/analysis", headers=headers).json().get("data", {})
        transcript_data = httpx.get(f"{BASE_URL}/jobs/{st.session_state.job_id}/transcript", headers=headers).json().get("data", {})
        
        with tab1:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Performance Scores")
                st.metric("Agent Performance", f"{analysis_data.get('agent_performance_score', 0)} / 10")
                st.metric("Customer Satisfaction", f"{analysis_data.get('customer_satisfaction_score', 0)} / 10")
                st.metric("Call Resolution", f"{analysis_data.get('call_resolution_score', 0)} / 10")
                st.metric("Empathy", f"{analysis_data.get('empathy_score', 0)} / 10")
                st.metric("Closing Effectiveness", f"{analysis_data.get('closing_effectiveness_score', 0)} / 10")
                
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
                
        with tab2:
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
                
        with tab3:
            st.subheader("Full Transcript (Repaired & Diarized)")
            st.caption(f"Language: {transcript_data.get('language')} | Confidence: {transcript_data.get('confidence', 0):.0%}")
            
            for seg in transcript_data.get("segments", []):
                speaker = seg.get("speaker_id", "?")
                text = seg.get("text", "")
                
                if "agent" in str(speaker).lower() or speaker == "SPEAKER_00":
                    st.info(f"**[{speaker}]** {text}")
                else:
                    st.success(f"**[{speaker}]** {text}")
