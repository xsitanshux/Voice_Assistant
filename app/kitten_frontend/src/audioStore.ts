import { create } from 'zustand';

interface AudioState {
  pcm: Int16Array[];                 // FIFO of raw PCM frames
  push: (buf: ArrayBuffer) => void;  // binary → queue
  shift: () => Int16Array | undefined;
}

export const useAudioStore = create<AudioState>((set, get) => ({
  pcm: [],
  push: (buf) =>
    set((s) => ({ pcm: [...s.pcm, new Int16Array(buf)] })),
  shift: () => {
    const [head, ...rest] = get().pcm;
    set({ pcm: rest });
    return head;
  },
}));
