// src/useChatAudio.tsx
import { useEffect, useRef, useState } from 'react';

export function useChatAudio(prompt: string) {
  const [text, setText] = useState('');
  const ctx = useRef<AudioContext | null>(null);
  const node = useRef<AudioWorkletNode | null>(null);

  useEffect(() => {
    if (!prompt) return;
    const ws = new WebSocket('ws://127.0.0.1:8000/chat');
    ws.binaryType = 'arraybuffer';

    let headerSR: number | null = null;
    const pending: ArrayBuffer[] = [];

    ws.onopen = () => ws.send(JSON.stringify({ prompt }));

    ws.onmessage = async (ev) => {
      if (typeof ev.data === 'string') {
        const msg = JSON.parse(ev.data);

        // 1) header from backend
        if (typeof msg.sr === 'number') {
          headerSR = msg.sr;
          console.log('[WS] Backend SR:', headerSR);
          return;
        }

        // 2) live tokens
        if (msg.tok) {
          setText((t) => t + msg.tok);
          return;
        }
        return;
      }

      // 3) first PCM chunk → build audio path
      if (!ctx.current) {
        const desired = headerSR ?? 44100;
        ctx.current = new AudioContext({
          sampleRate: desired,
          latencyHint: 'interactive',
        });
        await ctx.current.audioWorklet.addModule('/pcm-worklet.js');
        node.current = new AudioWorkletNode(ctx.current, 'pcm-player');
        node.current.connect(ctx.current.destination);
        await ctx.current.resume();
        node.current.port.postMessage({ type: 'cfg', inSR: headerSR || 44100 });

        // tell worklet the input sample rate (important for resampling)
        node.current.port.postMessage({ type: 'cfg', inSR: desired });

        console.log('[Audio] AudioContext.sampleRate:', ctx.current.sampleRate);

        // flush anything that arrived while loading
        for (const buf of pending) {
          node.current.port.postMessage(buf, [buf]);
        }
        pending.length = 0;
      }

      // 
      if (!node.current) {
        pending.push(ev.data);
      } else {
        node.current.port.postMessage(ev.data, [ev.data]); // transfer ArrayBuffer
      }
    };

    return () => ws.close();
  }, [prompt]);

  return text;
}
