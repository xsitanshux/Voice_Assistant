import sounddevice as sd
import queue
from vosk import Model, KaldiRecognizer
import json

class SpeechRecognizer:
    def __init__(self, model_path="C:/python/voice_assistant/models/vosk/vosk-model-small-en-us-0.15", sample_rate=16000):
        """
        Initialize the Vosk STT engine with the given model and sampling rate.
        """
        self.sample_rate = sample_rate
        self.q = queue.Queue()

        print("🧠 Loading Vosk model...")
        self.model = Model(model_path)
        self.recognizer = KaldiRecognizer(self.model, self.sample_rate)

        # Set up microphone stream
        self.stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=8000,
            dtype='int16',
            channels=1,
            callback=self._callback
        )

    def _callback(self, indata, frames, time, status):
        """
        Callback function for sounddevice to push mic data into queue.
        """
        if status:
            print(f"Mic Status: {status}")
        self.q.put(bytes(indata))

    def listen_loop(self):
        """
        Generator function that yields transcribed text from live mic input.
        """
        with self.stream:
            print("🎤 Listening...")
            while True:
                data = self.q.get()
                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    yield result.get("text", "")
                else:
                    partial = json.loads(self.recognizer.PartialResult())
                    if partial.get("partial"):
                        yield partial["partial"]
