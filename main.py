from utils.stt_engine import SpeechRecognizer
from utils.llm_engine import LocalLLM
from utils.tts_engine import VoiceSynthesizer

def run_voice_assistant():
    print("🎙️ Voice Assistant started. Speak into the microphone...")

    # Initialize components
    recognizer = SpeechRecognizer()       # Vosk for speech-to-text
    llm = LocalLLM()                      # Local LLM via ctransformers
    tts = VoiceSynthesizer()             # Coqui TTS for voice output

    # Main loop: listen → process → speak
    for text in recognizer.listen_loop():
        if not text.strip():
            continue

        print(f"👤 You said: {text}")
        response = llm.generate_response(text)
        print(f"🤖 Assistant: {response}")
        tts.speak(response)

if __name__ == "__main__":
    run_voice_assistant()
