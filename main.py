from fastapi import FastAPI, HTTPException
import logging
import os
import re

from config import settings 
from schema.schema import ProcessRequest, QueryRequest
from fastapi.middleware.cors import CORSMiddleware
from utils.audio_processor import AudioProcessor
from core.transcribe import AudioTranscriber
from core.summarize import TranscriptSummarizer
from core.extractor import TranscriptPointsExtract
from core.vector_store import VectorStore
from core.rag_engine import RAGEngine
from datetime import datetime

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Meeting Insights AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

audio_processor = AudioProcessor()
transcriber = AudioTranscriber()
summarizer = TranscriptSummarizer()
extractor = TranscriptPointsExtract()


@app.get("/health", summary="Health check", tags=["System"])
def health_check():
    return {
        "status": "ok",
        "service": "meeting-insights-ai",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

@app.post("/process", summary="Process audio and return insights")
def process_meeting(request: ProcessRequest):
    try:
        logging.info(f"Processing audio: {request.source}")

        chunk_paths = audio_processor.process_input(request.source)
        if not chunk_paths:
            raise ValueError("Failed to download or process audio.")

        transcript_parts = []
        for chunk in chunk_paths:
            transcript_parts.append(transcriber.transcribe_chunks(chunk))
            if os.path.exists(chunk):
                os.remove(chunk)

        full_transcript = " ".join(transcript_parts).strip()
        if not full_transcript:
            raise ValueError("Transcription resulted in empty text.")

        summary = summarizer.summarize(full_transcript)
        title = summarizer.make_title(summary)
        action_items = extractor.extract_action_items(full_transcript)
        key_decisions = extractor.extract_key_decisions(full_transcript)
        questions = extractor.extract_questions(full_transcript)

        VectorStore().build_vector_store(transcript=full_transcript, meeting_id="default_meeting")

        return {
            "title": title,
            "summary": summary,
            "action_items": action_items,
            "key_decisions": key_decisions,
            "questions": questions,
        }

    except Exception:
        logging.exception("Processing failed")
        raise


@app.post("/ask", summary="Ask a question about the meeting")
def ask_question(request: QueryRequest):
    try:
        chain = RAGEngine(meeting_id="default_meeting").build_rag_chain()
        raw_answer = str(chain.invoke(request.question))

        clean_answer = re.sub(r"<think>.*?</think>", "", raw_answer, flags=re.DOTALL).strip()

        return {
            "question": request.question,
            "answer": clean_answer
        }
    except Exception as e:
        logging.error(f"RAG query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))