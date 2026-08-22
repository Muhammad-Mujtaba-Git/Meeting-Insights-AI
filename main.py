import os
import site

# --- WINDOWS CUDA DLL FIX ---
# Yeh code pip se install hui nvidia DLLs ko Python ke path mein add karega
site_packages = site.getsitepackages()[0]
nvidia_dir = os.path.join(site_packages, "nvidia")
if os.path.exists(nvidia_dir):
    for lib_folder in os.listdir(nvidia_dir):
        bin_path = os.path.join(nvidia_dir, lib_folder, "bin")
        if os.path.exists(bin_path):
            os.add_dll_directory(bin_path)
# ----------------------------
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
import os
import logging
import uuid

from config import settings 
from schema.schema import ProcessRequest, QueryRequest

from utils.audio_processor import AudioProcessor
from core.transcribe import AudioTranscriber
from core.summarize import TranscriptSummarizer
from core.extractor import TranscriptPointsExtract
from core.vector_store import VectorStore
from core.rag_engine import RAGEngine

logging.basicConfig(level=logging.INFO)

class MeetingInsightsManager:
    """Class to manage the heavy models and orchestrate the pipeline."""
    
    def __init__(self):
        logging.info("Initializing Meeting Insights Manager and loading models...")
        self.audio_processor = AudioProcessor()
        self.transcriber = AudioTranscriber()
        self.summarizer = TranscriptSummarizer()
        self.extractor = TranscriptPointsExtract()
        
        # In-memory dictionary to store task statuses (Production mein Redis/DB use karenge)
        self.tasks_db = {} 
        logging.info("All base models loaded successfully!")

    def process_meeting_task(self, task_id: str, source: str):
        """Yeh function background mein chalega aur status update karega."""
        try:
            self.tasks_db[task_id] = {"status": "Processing", "data": None}
            
            chunk_paths = self.audio_processor.process_input(source)
            if not chunk_paths:
                raise ValueError("Failed to download or process audio.")

            full_transcript_parts = []
            for chunk_path in chunk_paths:
                text = self.transcriber.transcribe_chunks(chunk_path)
                full_transcript_parts.append(text)
                if os.path.exists(chunk_path):
                    os.remove(chunk_path) # Clean up chunks

            full_transcript = " ".join(full_transcript_parts)
            if not full_transcript.strip():
                raise ValueError("Transcription resulted in empty text.")

            self.tasks_db[task_id]["status"] = "Summarizing and Extracting..."
            
            summary = self.summarizer.summarize(full_transcript)
            title = self.summarizer.make_title(summary)
            action_items = self.extractor.extract_action_items(full_transcript)
            key_decisions = self.extractor.extract_key_decisions(full_transcript)
            questions = self.extractor.extract_questions(full_transcript)

            vs = VectorStore()
            vs.build_vector_store(full_transcript)

            # Final result save kar rahe hain
            self.tasks_db[task_id] = {
                "status": "Completed",
                "data": {
                    "title": title,
                    "summary": summary,
                    "action_items": action_items,
                    "key_decisions": key_decisions,
                    "questions": questions,
                }
            }
            logging.info(f"Task {task_id} completed successfully!")

        except Exception as e:
            self.tasks_db[task_id] = {"status": f"Failed: {str(e)}", "data": None}
            logging.error(f"Task {task_id} failed: {e}")

    def ask_question(self, question: str) -> str:
        """Handles the RAG querying."""
        if not os.path.exists("vector_db"):
            raise ValueError("No meeting has been processed yet. Call /process first.")

        rag = RAGEngine()
        chain = rag.build_rag_chain()
        return chain.invoke(question)


app = FastAPI(title="Meeting Insights AI API", version="1.0")

# Startup par ek hi baar model load hoga
pipeline_manager = MeetingInsightsManager()

def get_manager():
    """Dependency injection function."""
    return pipeline_manager


@app.post("/process", summary="Process audio and extract insights in background")
def process_endpoint(request: ProcessRequest, background_tasks: BackgroundTasks, manager: MeetingInsightsManager = Depends(get_manager)):
    """Yeh endpoint turant task_id return karega aur processing background mein hogi."""
    task_id = str(uuid.uuid4())
    logging.info(f"Starting background processing for source: {request.source} | Task ID: {task_id}")
    
    # Background task add karein
    background_tasks.add_task(manager.process_meeting_task, task_id, request.source)
    
    return {
        "message": "Meeting processing started in background!",
        "task_id": task_id,
        "status_check_url": f"/status/{task_id}"
    }

@app.get("/status/{task_id}", summary="Check the status of processing")
def status_endpoint(task_id: str, manager: MeetingInsightsManager = Depends(get_manager)):
    """User yahan check karega ke process complete hua ya nahi."""
    task = manager.tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task ID not found!")
    return task

@app.post("/ask", summary="Ask questions about the processed meeting (RAG)")
def ask_endpoint(request: QueryRequest, manager: MeetingInsightsManager = Depends(get_manager)):
    # RAG tab tak nahi chalega jab tak /process complete na ho
    try:
        logging.info(f"Querying RAG with: {request.question}")
        answer = manager.ask_question(request.question)
        return {"question": request.question, "answer": answer}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logging.error(f"Error querying RAG: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during RAG query.")