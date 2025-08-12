# talk_with_ollama.py
import sys
import re
import httpx
import time
import queue
import threading
import argparse
import numpy as np
import sounddevice as sd
from kittentts import KittenTTS
from ollama import Client
# # from kitten_class import KittenVoiceStreamer


# class KittenVoiceStreamer:
#     """Non-blocking text-to-speech streamer (Kitten TTS + sounddevice)."""
#     def __init__(self,
#                  model_id="KittenML/kitten-tts-nano-0.1",
#                  voice_id="expr-voice-3-f",
#                  sr=24_000, qsize=8):
#         self.tts   = KittenTTS(model_id)
#         self.voice = voice_id
#         self.sr    = sr
#         self.q     = queue.Queue(maxsize=qsize)
#         self._stop = threading.Event()
#         self._player = threading.Thread(target=self._playback, daemon=True)
#         self._player.start()

#     def speak(self, text: str, speed: float = 1.0):
#         for piece in re.split(r"([.!?])", text):
#             if piece.strip():
#                 wav = self.tts.generate(piece.strip(),
#                                         voice=self.voice,
#                                         speed=speed)
#                 self.q.put(wav)

#     def close(self):
#         self.q.put(None)
#         self._stop.set()
#         self._player.join()

#     def _playback(self):
#         with sd.OutputStream(channels=1, samplerate=self.sr,
#                              dtype="float32") as s:
#             while not self._stop.is_set():
#                 chunk = self.q.get()
#                 if chunk is None:
#                     break
#                 s.write(chunk.astype(np.float32))

# def main():
#     ap = argparse.ArgumentParser(description="Ollama → Kitten TTS demo")
#     ap.add_argument("--host", default="http://54.242.243.62:11434",
#                     help="Ollama server URL")
#     ap.add_argument("--model", default="llama3.1:8b",
#                     help="Model name on the Ollama host")
#     ap.add_argument("--voice", default="expr-voice-3-f",
#                     help="Kitten TTS voice id")
#     ap.add_argument("--prompt", help="Initial prompt (otherwise ask interactively)")
#     args = ap.parse_args()

#     prompt = args.prompt or input("Your prompt ➜ ")
#     print(f"\n🗒  Prompt: {prompt}\n")

#     client = Client(host=args.host)
#     vox = KittenVoiceStreamer(voice_id=args.voice)

#     buffer, punct = [], re.compile(r"[.!?]")
#     try:
#         for tok in client.generate(
#         model=args.model,          # ← keyword args
#         prompt=prompt,
#         stream=True):
#             token = tok["response"]
#             print(token, end="", flush=True)          # ← live console print
#             buffer.append(token)
#             if punct.search(token):
#                 vox.speak("".join(buffer))            # speak the clause
#                 buffer.clear()

#         if buffer:                                    # tail fragment
#             vox.speak("".join(buffer))
#     finally:
#         vox.close()
#         print("\n\n✅ Finished\n")

# if __name__ == "__main__":
#     main()














# –  real-time LLM → cleaned speech





class KittenVoiceStreamer:
    """Non-blocking text-to-speech streamer (Kitten TTS + sounddevice)."""

    def __init__(
        self,
        model_id: str = "KittenML/kitten-tts-nano-0.1",
        voice_id: str = "expr-voice-3-m",
        sr: int = 24_000,
        qsize: int = 16,
    ):
        self.voice = voice_id
        self.sr = sr
        self.tts = KittenTTS(model_id)
        self.q: queue.Queue[np.ndarray] = queue.Queue(maxsize=qsize)
        self._stop = threading.Event()
        self._player = threading.Thread(target=self._playback, daemon=True)
        self._player.start()

    
    def speak(self, text: str, speed: float = 1.0) -> None:
        for piece in re.split(r"([.!?])", text):
            if piece.strip():
                wav = self.tts.generate(piece.strip(), voice=self.voice, speed=speed)
                self.q.put(wav)

    def close(self) -> None:
        self.q.put(None)
        self._stop.set()
        self._player.join()

   
    def _playback(self) -> None:
        with sd.OutputStream(
            channels=1, samplerate=self.sr, dtype="float32"
        ) as stream:
            while not self._stop.is_set():
                chunk = self.q.get()
                if chunk is None:
                    break
                stream.write(chunk.astype(np.float32))



NON_SPEECH = re.compile(r"[`*_•·\[\]\(\)<>]+|:[a-z_]+:")
MULTI_PUNC = re.compile(r"([.!?]){2,}")
WS_CLEAN = re.compile(r"\s{2,}")


def clean_for_voice(txt: str) -> str:
    txt = NON_SPEECH.sub(" ", txt)
    txt = MULTI_PUNC.sub(r"\1", txt)
    return WS_CLEAN.sub(" ", txt).strip()



def stream_ollama(client: Client, **kwargs):
    """Yield tokens with simple retry on transient network drop."""
    for attempt in range(1, 4):  # 3 retries
        try:
            yield from client.generate(stream=True, **kwargs)
            return
        except (httpx.ReadError, httpx.RemoteProtocolError, httpx.ConnectError) as e:
            if attempt == 3:
                raise
            print(f"\n⚠️  stream lost ({e}); retrying {attempt}/3…")
            time.sleep(2 * attempt)



def main() -> None:
    ap = argparse.ArgumentParser(description="Stream Ollama response to speech")
    ap.add_argument("--host", default="http://54.242.243.62:11434", help="Ollama URL")
    ap.add_argument("--model", default="llama3.1:8b", help="Model on Ollama host")
    ap.add_argument("--voice", default="expr-voice-3-f", help="Kitten voice id")
    ap.add_argument("--prompt", help="Prompt text (else ask interactively)")
    ap.add_argument("--max-words", type=int, default=120, help="Word budget")
    args = ap.parse_args()

    prompt = args.prompt or input("Your prompt ➜ ")
    print(f"\n🗒  Prompt: {prompt}\n")

    client = Client(host=args.host, timeout=httpx.Timeout(90.0, read=90.0))
    vox = KittenVoiceStreamer(voice_id=args.voice)

    buffer, word_count = [], 0
    punct = re.compile(r"[.!?]")

    try:
        for tok in stream_ollama(client, model=args.model, prompt=prompt):
            token = tok["response"]
            print(token, end="", flush=True)

            words = token.split()
            word_count += len(words)
            buffer.append(token)

            # flush when punctuation OR word budget reached
            flush = punct.search(token) or word_count >= args.max_words
            if flush:
                clause = clean_for_voice("".join(buffer))
                vox.speak(clause, speed=1.1)  # 10 % faster voice
                buffer.clear()

            if word_count >= args.max_words:
                print(" … [truncated]", flush=True)
                vox.speak(" … response truncated.")
                break

        if buffer:
            vox.speak(clean_for_voice("".join(buffer)))
    finally:
        vox.close()
        print("\n\n✅ Finished\n")


if __name__ == "__main__":
    main()
