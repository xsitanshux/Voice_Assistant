import { useState } from 'react';
import { useChatAudio } from './useChatAudio';

export default function Chat() {
  const [inp, setInp] = useState('');
  const [prompt, setPrompt] = useState('');
  const text = useChatAudio(prompt);

  return (
    <div style={{ padding: 30, fontFamily: 'sans-serif' }}>
      <h3>Ask the model & hear the reply</h3>
      <input
        style={{ width: 480, padding: 6 }}
        value={inp}
        placeholder="Type your question..."
        onChange={(e) => setInp(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && setPrompt(inp)}
      />
      <button onClick={() => setPrompt(inp)}>Send & Speak</button>
      <pre style={{ whiteSpace: 'pre-wrap', marginTop: 24 }}>{text}</pre>
    </div>
  );
}
