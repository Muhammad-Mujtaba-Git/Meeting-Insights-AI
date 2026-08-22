import os
from groq import Groq
from config import settings

class AudioTranscriber:
    def __init__(self, model: str = "whisper-large-v3-turbo"):
        """
        Groq Audio Transcriber
        
        """
        self.model = model
        
        api_key = getattr(settings, "GROQ_API_KEY", None) or os.getenv("GROQ_API_KEY")
        
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in settings or environment variables.")
            
        self.client = Groq(api_key=api_key)
        print(f"Groq Transcriber initialized with model: '{self.model}'")

    def transcribe_chunks(self, audio_path: str, translate: bool = False, language: str = None) -> str:
        """
        Transcribes or translates an audio file via Groq API.
        
        :param audio_path: Path to the audio file.
        :param translate: If True, translates to English. If False, transcribes in original language.
        :param language: Language code (e.g., 'en', 'es', 'ur'). If None, auto-detects.
        :return: The full transcribed/translated text as a single string.
        """
        task = "translate" if translate else "transcribe"

        with open(audio_path, "rb") as file:
            if translate:
                
                response = self.client.audio.translations.create(
                    file=(os.path.basename(audio_path), file.read()),
                    model=self.model,
                    response_format="verbose_json",
                    temperature=0.0
                )
            else:
               
                response = self.client.audio.transcriptions.create(
                    file=(os.path.basename(audio_path), file.read()),
                    model=self.model,
                    response_format="verbose_json",
                    language=language,
                    temperature=0.0
                )

       
        if hasattr(response, "language") and response.language:
            print(f"Detected language: '{response.language}'")
        print(f"Task: {task.capitalize()}\n")

        
        print("--- Transcription Segments ---")
        full_text = []
        
       
        segments = getattr(response, "segments", []) or []
        for segment in segments:
            
            start = segment["start"] if isinstance(segment, dict) else segment.start
            end = segment["end"] if isinstance(segment, dict) else segment.end
            text = segment["text"].strip() if isinstance(segment, dict) else segment.text.strip()
            
            print(f"[{start:.2f}s -> {end:.2f}s] {text}")
            full_text.append(text)

        
        return " ".join(full_text) if full_text else getattr(response, "text", "")