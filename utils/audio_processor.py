import os
import yt_dlp
from pydub import AudioSegment
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

class AudioProcessor:
    def __init__(self, download_dir: str = "download", chunks_dir: str = "chunks"):
        self.download_dir = download_dir
        self.chunks_dir = chunks_dir
        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.chunks_dir, exist_ok=True)

    def download_youtube_audio(self, url: str) -> str:
        """Downloads audio from a URL and converts it to WAV using yt-dlp."""
        logging.info(f"Downloading audio from: {url}")
        
        output_path = os.path.join(self.download_dir, "%(title)s.%(ext)s")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_path,
            "extractor_args": {"youtube": {"player_client": ["android"]}},
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                   
                }
            ],
            "quiet": True,
            "no_warnings": True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                base_filename = os.path.splitext(ydl.prepare_filename(info))[0]
                final_wav_path = base_filename + ".wav"
                
            if not os.path.exists(final_wav_path):
                raise FileNotFoundError(f"Expected downloaded file not found: {final_wav_path}")
                
            logging.info(f"Download complete: {final_wav_path}")
            return final_wav_path
            
        except Exception as e:
            logging.error(f"Failed to download YouTube audio: {e}")
            raise

    def convert_to_wav(self, input_path: str) -> str:
        """Converts any local audio/video file to 16kHz Mono WAV."""
        logging.info(f"Converting local file to WAV: {input_path}")
        
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(self.download_dir, f"{base_name}_converted.wav")
        
        try:
            audio = AudioSegment.from_file(input_path)
            # Whisper performs best with 16kHz mono
            audio = audio.set_channels(1).set_frame_rate(16000)
            audio.export(output_path, format="wav")
            logging.info(f"Conversion complete: {output_path}")
            return output_path
        except Exception as e:
            logging.error(f"Failed to convert {input_path} to WAV. Ensure FFmpeg is installed. Error: {e}")
            raise

    def chunk_audio(self, wav_path: str, chunk_min: int = 10, cleanup: bool = True) -> list:
        """Splits a WAV file into smaller chunks of `chunk_min` minutes."""
        logging.info(f"Chunking audio into {chunk_min}-minute segments...")
        
        audio = AudioSegment.from_wav(wav_path)
        chunk_ms = chunk_min * 60 * 1000
        base_name = os.path.splitext(os.path.basename(wav_path))[0]
        
        chunk_paths = []
        for i, start in enumerate(range(0, len(audio), chunk_ms)):
            chunk = audio[start: start + chunk_ms]
            chunk_path = os.path.join(self.chunks_dir, f"{base_name}_chunk_{i}.wav")
            chunk.export(chunk_path, format="wav")
            chunk_paths.append(chunk_path)
            
        logging.info(f"Created {len(chunk_paths)} chunks in '{self.chunks_dir}' directory.")
        
        #Delete the full audio file to save disk space
        if cleanup:
            try:
                os.remove(wav_path)
                logging.info(f"Cleaned up original file: {wav_path}")
            except OSError as e:
                logging.warning(f"Could not delete {wav_path}: {e}")
                
        return chunk_paths

    def process_input(self, source: str, chunk_min: int = 10) -> list:
        """
        Main pipeline: Detects if input is URL or local file, 
        converts to WAV, and chunks it.
        """
        try:
            if source.startswith(("http://", "https://")):
                wav_path = self.download_youtube_audio(source)
            else:
                if not os.path.exists(source):
                    raise FileNotFoundError(f"Local file not found: {source}")
                wav_path = self.convert_to_wav(source)
                
            chunks = self.chunk_audio(wav_path, chunk_min=chunk_min, cleanup=True)
            return chunks
            
        except Exception as e:
            logging.error(f"Processing failed: {e}")
            return []

