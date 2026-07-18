redis: "C:\Program Files\Memurai\memurai.exe"
minio: "C:\tools\minio.exe" server "C:\minio-data" --console-address ":9001"
api: cd backend && python -m uvicorn src.presentation.api.app:create_app --factory --host 0.0.0.0 --port 8000
stt: cd backend && python src/worker_main.py stt
repair: cd backend && python src/worker_main.py repair
analysis: cd backend && python src/worker_main.py analysis
report: cd backend && python src/worker_main.py report
frontend: python -m streamlit run frontend/app.py
