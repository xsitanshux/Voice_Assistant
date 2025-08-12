

import re
import queue
import threading
import sys
import numpy as np
import sounddevice as sd
from kittentts import KittenTTS

VOICE_ID = "expr-voice-3-f"           # pick any from tts.available_voices
MODEL_ID = "KittenML/kitten-tts-nano-0.1"
SAMPLERATE = 24_000                   # Kitten outputs 24 kHz PCM

tts = KittenTTS(MODEL_ID)             # downloads weights once
audio_q = queue.Queue(maxsize=8)      # back-pressure so synth ≈ play

# ---------- playback worker ----------------------------------------------
def audio_player():
    with sd.OutputStream(
            channels=1,
            samplerate=SAMPLERATE,
            dtype="float32") as stream:
        while True:
            chunk = audio_q.get()
            if chunk is None:                                            # poison pill => exit
                break
            stream.write(chunk.astype(np.float32))

player_th = threading.Thread(target=audio_player, daemon=True)
player_th.start()

# ---------- TTS producer --------------------------------------------------
def speak(text: str):
    """Chunk text, generate audio for each piece, enqueue for playback."""
    for piece in re.split(r"([.!?])", text):
        if not piece.strip():                        # skip empty splits
            continue
        wav = tts.generate(piece.strip(), voice=VOICE_ID, speed=1.0)
        audio_q.put(wav)                             # hand to audio thread

# ---------- CLI demo ------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python kitten_stream_tts.py \"Your text here.\"")
    speak(" ".join(sys.argv[1:]))
    audio_q.put(None)   # done
    player_th.join()
