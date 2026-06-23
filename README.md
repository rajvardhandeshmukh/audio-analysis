# 🎙️ QubeFini Audio AI Pipeline

An enterprise-grade, highly scalable asynchronous AI pipeline designed for call centers and sales behavioral analysis.

This project automatically processes raw audio calls, transcribes them, corrects errors using AI, analyzes speaker sentiment and behavioral metrics, and packages the results into a comprehensive coaching report.

---

## 🏗️ Architecture

This project strictly adheres to **Hexagonal Architecture** (Ports & Adapters) combined with **Domain-Driven Design (DDD)**. 
Business logic is completely isolated from frameworks, databases, and message brokers.

### Key Rules Enforced:
- **Dependency Rule**: Dependencies always point INWARD toward the Domain.
- **Port/Adapter Separation**: External dependencies (OpenAI, PostgreSQL, MinIO, RabbitMQ) communicate via strict Port interfaces.
- **Stateless Workers**: Background processing workers pull fresh DB connections per message and gracefully route failed messages to Dead-Letter Queues (DLQs).
- **Idempotency**: All database inserts and updates handle concurrent retries safely.

---

## 🚀 The Pipeline Lifecycle

1. **Ingestion**: A user uploads an audio file via the Streamlit frontend. It is stored securely in **MinIO**, bypassing the FastAPI server to prevent memory bottlenecks.
2. **STT (Speech-To-Text)**: A background worker pulls the task from RabbitMQ, streams the audio from MinIO, and uses **Whisper AI** to generate a raw transcript.
3. **Repair**: A secondary worker uses an LLM to clean up the raw transcript grammar, remove filler words (umms/ahhs), and strictly diarize the speakers (Agent vs Customer).
4. **Analysis**: The clean transcript is passed to **GPT-4o Structured Outputs**. It is strictly graded against a Pydantic schema for metrics like *Empathy*, *Closing Effectiveness*, and *Compliance*.
5. **Report**: The final worker aggregates the transcript, call duration, talk-time metrics, and AI analysis into a single database `Report` entity.

---

## 🛠️ Technology Stack

- **Frontend**: Streamlit (Python)
- **API**: FastAPI, Uvicorn
- **Database**: PostgreSQL (via SQLAlchemy Core & asyncpg)
- **Messaging**: RabbitMQ (via aio-pika)
- **Storage**: MinIO (S3-Compatible Object Storage)
- **Caching & Pub/Sub**: Redis
- **AI Models**: OpenAI API (Whisper + GPT-4o)

---

## ⚙️ Getting Started

### 1. Prerequisites
Ensure you have the following installed and running via Docker or natively:
- PostgreSQL (port 5432)
- RabbitMQ (port 5672, UI on 15672)
- Redis (port 6379)
- MinIO (port 9000)

### 2. Setup Environment
1. Clone the repository.
2. Navigate into the `backend` directory.
3. Create a python virtual environment and activate it:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Or `venv\Scripts\activate` on Windows
   ```
4. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
5. Copy `.env.example` to `.env` and fill in your database credentials and `AI_PROVIDER_ORCHESTRATION_API_KEY`.

### 3. Run Migrations
Initialize your database schema:
```bash
python -m alembic upgrade head
```

### 4. Seed the Database
Create your initial Admin user (`admin@example.com` / `admin123`):
```bash
python scripts/seed_admin.py
```

---

## 🏃 Running the Platform

Because this is a distributed system, you need to run multiple components simultaneously.

### Terminal 1: The API
```bash
cd backend
python -m uvicorn src.presentation.api.app:create_app --factory --host 0.0.0.0 --port 8000 --reload
```

### Terminals 2-5: The AI Workers
In 4 separate terminals (with the `venv` activated), launch the specialized workers:
```bash
# Terminal 2
python src/worker_main.py stt

# Terminal 3
python src/worker_main.py repair

# Terminal 4
python src/worker_main.py analysis

# Terminal 5
python src/worker_main.py report
```

### Terminal 6: The Frontend Dashboard
Launch the Streamlit UI to interact with the pipeline:
```bash
python -m streamlit run frontend/app.py
```

---

## 🖥️ Using the Application
1. Open your browser to the Streamlit UI (typically `http://localhost:8501`).
2. Login using the admin credentials you seeded.
3. Drag and drop any `.mp3` or `.wav` sales call audio.
4. Watch the live progress bar as RabbitMQ passes the audio through all 4 AI worker stages.
5. Review the final generated **AI Coaching Dashboard**, Call Metrics, and Repaired Transcript!
