"use client";
import { useCallback, useEffect, useState } from "react";
import { newsroom } from "./api";

export function useRemote<T>(path: string, pollMs = 0, isFinished?: (data: T) => boolean) {
  const [generation, setGeneration] = useState(0);
  const [state, setState] = useState<{ path: string; data: T | null; error: string | null }>({ path: "", data: null, error: null });
  const refresh = useCallback(() => setGeneration(value => value + 1), []);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setInterval> | null = null;
    const load = () => newsroom<T>(path).then(data => {
      if (active) setState({ path, data, error: null });
      if (isFinished?.(data) && timer) clearInterval(timer);
    }).catch(error => {
      if (active) setState(previous => ({ path, data: previous.path === path ? previous.data : null, error: error.message }));
    });
    void load();
    timer = pollMs ? setInterval(load, pollMs) : null;
    return () => { active = false; if (timer) clearInterval(timer); };
  }, [path, generation, pollMs, isFinished]);
  return { data: state.path === path ? state.data : null, error: state.path === path ? state.error : null, refresh };
}
