import { useEffect, useRef, useState } from 'react';

export function useChatAudio(prompt: string) {
  const [text, setText] = useState('');
  const ctx = useRef<AudioContext | null>(null);
  const node = useRef<AudioWorkletNode | null>(null);

  useEffect(() => {
    if (!prompt) return;
    const ws = new WebSocket('ws://127.0.0.1:8000/chat');
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => ws.send(JSON.stringify({ prompt }));
    const pending: ArrayBuffer[] = [];          // <-- add outside onmessage

    ws.onmessage = async (ev) => {
    if (typeof ev.data === 'string') {
        const msg = JSON.parse(ev.data);
        if (msg.tok) setText(t => t + msg.tok);
        return;
    }

    if (!ctx.current) {
        ctx.current = new AudioContext({ sampleRate: 24_000 });
        await ctx.current.audioWorklet.addModule('/pcm-worklet.js');
        node.current = new AudioWorkletNode(ctx.current, 'pcm-player');
        node.current.connect(ctx.current.destination);
        await ctx.current.resume();

        // flush anything that arrived while we were loading
        pending.forEach(buf => node.current!.port.postMessage(buf, [buf]));
        pending.length = 0;
    }

    if (!node.current) {
        pending.push(ev.data);                 // queue until worklet ready
    } else {
        node.current.port.postMessage(ev.data, [ev.data]);
    }
    };
    return () => ws.close();
  }, [prompt]);

  return text;
}
