# voice_streamer.py
import re
import queue
import threading
import numpy as np
import sounddevice as sd
from kittentts import KittenTTS
from  ollama import Client


class KittenVoiceStreamer:
    """Non-blocking text-to-speech streamer built on Kitten TTS + sounddevice."""
    def __init__(
        self,
        model_id="KittenML/kitten-tts-nano-0.1",
        voice_id="expr-voice-3-f",
        sr=24_000,
        qsize=8,
    ):
        self.tts   = KittenTTS(model_id)
        self.voice = voice_id
        self.sr    = sr
        self.q     = queue.Queue(maxsize=qsize)
        self._stop = threading.Event()
        threading.Thread(target=self._playback, daemon=True).start()

    def speak(self, text: str):
        for piece in re.split(r"([.!?])", text):
            if piece.strip():
                wav = self.tts.generate(piece.strip(), voice=self.voice)
                self.q.put(wav)

    def close(self):
        self.q.put(None)
        self._stop.set()

    def _playback(self):
        with sd.OutputStream(channels=1, samplerate=self.sr, dtype="float32") as s:
            while not self._stop.is_set():
                chunk = self.q.get()
                if chunk is None:
                    break
                s.write(chunk.astype(np.float32))



# prompt = "Write a short summary about the city of Hyderabad."
# vox = KittenVoiceStreamer()          # starts the audio thread

# buffer, punct = [], re.compile(r"[.!?]")
# client = Client(host="http://54.242.243.62:11434")
# try:
#     for tok in client.generate(
#         model="llama3.1:8b",
#         prompt=prompt,
#         stream=True                  # <-- enables token streaming
#     ):
#         token = tok["response"]
#         buffer.append(token)
#         if punct.search(token):      # full clause reached
#             vox.speak("".join(buffer))
#             buffer.clear()

#     # speak any tail without punctuation
#     if buffer:
#         vox.speak("".join(buffer))
# finally:
#     vox.close()