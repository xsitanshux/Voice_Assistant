from ctransformers import AutoModelForCausalLM

class LocalLLM:
    def __init__(self, model_path="C:/python/voice_assistant/models/llm/tinyllama-1.1b-chat-v1.0.Q4_0.gguf"):
        """
        Load the TinyLlama 1.1B Chat model (quantized Q4_0).
        """
        print("🧠 Loading TinyLlama model...")
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            model_type="llama",   # TinyLlama uses llama tokenizer & architecture
            max_new_tokens=150,
            temperature=0.7,
            repetition_penalty=1.1,
            context_length=512
        )
        print("✅ TinyLlama ready.")

    def generate_response(self, prompt):
        if not prompt.strip():
            return "Can you please repeat that?"
        return self.model(prompt).strip()
