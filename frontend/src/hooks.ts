import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";

export interface Loadable<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

/** GET a JSON endpoint; re-fetches when `url` changes or reload() is called. */
export function useApi<T>(url: string | null): Loadable<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(!!url);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!url) return;
    let alive = true;
    setLoading(true);
    api
      .get<T>(url)
      .then((d) => {
        if (alive) {
          setData(d);
          setError(null);
        }
      })
      .catch((e) => alive && setError(e instanceof ApiError ? e : new ApiError(0, "network")))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [url, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

/** Re-render every `ms` milliseconds (for live countdowns). */
export function useNow(ms = 1000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}
