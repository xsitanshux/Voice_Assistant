from TTS.api import TTS
from utils.audio_io import play_audio
import numpy as np
import soundfile as sf
import re

class VoiceSynthesizer:
    def __init__(self):
        print("🗣️ Loading TTS model from local path...")

        # Use forward slashes in model paths for cross-platform consistency
        self.tts = TTS(
            model_name="tts_models/en/ljspeech/tacotron2-DDC",
            model_path="C:/Users/NutanSitanshuBoyini/AppData/Local/tts/tts_models--en--ljspeech--tacotron2-DDC/model_file.pth",
            config_path="C:/Users/NutanSitanshuBoyini/AppData/Local/tts/tts_models--en--ljspeech--tacotron2-DDC/config.json",
            vocoder_path="C:/Users/NutanSitanshuBoyini/AppData/Local/tts/vocoder_models--en--ljspeech--hifigan_v2/model_file.pth",
            vocoder_config_path="C:/Users/NutanSitanshuBoyini/AppData/Local/tts/vocoder_models--en--ljspeech--hifigan_v2/config.json",
            progress_bar=False,
            gpu=False
        )

        print("✅ TTS model ready.")

    def clean_sentence(self, text):
        text = re.sub(r"http\S+", "", text)
        text = re.sub(r"[^a-zA-Z0-9 ,.'?]+", "", text)
        text = re.sub(r"\s{2,}", " ", text)
        return text.strip()

    def speak(self, text):
        if not text.strip():
            print("⚠️ [TTS] Empty input.")
            return

        print("🔈 Speaking...")
        try:
            raw_sentences = re.split(r"[.?!]", text)
            clean_sentences = [self.clean_sentence(s) for s in raw_sentences if s.strip()]
            
            audio_chunks = []
            for sentence in clean_sentences:
                audio = self.tts.tts(sentence)
                if isinstance(audio, list):
                    audio_chunks += [a for a in audio if isinstance(a, np.ndarray) and a.size > 0]
                elif isinstance(audio, np.ndarray) and audio.size > 0:
                    audio_chunks.append(audio)

            if not audio_chunks:
                print("⚠️ [TTS] No valid audio chunks to play.")
                return

            audio_array = np.concatenate(audio_chunks, axis=0)
            audio_array *= 1.5
            audio_array = np.clip(audio_array, -1.0, 1.0)

            sf.write("test_output.wav", audio_array, 22050)
            play_audio(audio_array, sample_rate=22050)
            print("✅ [TTS] Playback done.")

        except Exception as e:
            print(f"❌ [TTS] Error during synthesis: {e}")
