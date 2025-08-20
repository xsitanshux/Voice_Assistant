// src/useChatAudio.tsx
import { useEffect, useRef, useState } from 'react';

export function useChatAudio(prompt: string) {
  const [text, setText] = useState('');
  const ctx = useRef<AudioContext | null>(null);
  const node = useRef<AudioWorkletNode | null>(null);
  const primed = useRef(false);

  // Buffers that arrive before the worklet is ready
  const pending = useRef<ArrayBuffer[]>([]);

  // Prime AudioContext + Worklet once, on first user gesture (fastest first sound)
  useEffect(() => {
    const prime = async () => {
      if (primed.current) return;
      primed.current = true;

      ctx.current = new AudioContext({ latencyHint: 'interactive' });
      await ctx.current.audioWorklet.addModule('/pcm-worklet.js');

      node.current = new AudioWorkletNode(ctx.current, 'pcm-player');
      node.current.connect(ctx.current.destination);

      // iOS / Safari sometimes suspend; resume on gesture
      if (ctx.current.state === 'suspended') {
        await ctx.current.resume();
      }

      // Flush anything queued while loading
      for (const buf of pending.current) {
        node.current.port.postMessage(buf, [buf]);
      }
      pending.current.length = 0;
    };

    const once = () => void prime();
    window.addEventListener('pointerdown', once, { once: true });
    window.addEventListener('keydown', once, { once: true });
    return () => {
      window.removeEventListener('pointerdown', once);
      window.removeEventListener('keydown', once);
    };
  }, []);

  useEffect(() => {
    if (!prompt) return;

    const ws = new WebSocket('ws://127.0.0.1:8000/chat');
    ws.binaryType = 'arraybuffer';

    let headerSR: number | null = null;

    ws.onopen = () => {
      ws.send(JSON.stringify({ prompt }));
    };

    ws.onmessage = async (ev) => {
      // JSON control messages
      if (typeof ev.data === 'string') {
        const msg = JSON.parse(ev.data);

        // Header from backend: { sr, fmt, frame_ms }
        if (typeof msg.sr === 'number') {
          headerSR = msg.sr;

          // Ensure audio path is ready; if user never interacted, prime now
          if (!ctx.current) {
            // As a fallback (Chrome allows), create context now
            ctx.current = new AudioContext({ sampleRate: headerSR, latencyHint: 'interactive' });
            await ctx.current.audioWorklet.addModule('/pcm-worklet.js');
            node.current = new AudioWorkletNode(ctx.current, 'pcm-player');
            node.current.connect(ctx.current.destination);
            await ctx.current.resume();
            primed.current = true;
          }

          // Tell worklet the input sample rate (and optionally frame size)
          node.current?.port.postMessage({ type: 'cfg', inSR: headerSR, frame_ms: msg.frame_ms ?? undefined });
          return;
        }

        // Live tokens for UI
        if (typeof msg.tok === 'string') {
          setText((t) => t + msg.tok);
          return;
        }
        return;
      }

      // Binary PCM chunk
      if (!node.current) {
        // Worklet not ready yet — queue buffer (will be flushed on prime)
        pending.current.push(ev.data as ArrayBuffer);
      } else {
        node.current.port.postMessage(ev.data as ArrayBuffer, [ev.data as ArrayBuffer]); // zero-copy
      }
    };

    return () => {
      try { ws.close(); } catch {}
    };
  }, [prompt]);

  return text;
}
