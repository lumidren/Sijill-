import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "./api";

export interface Org {
  id: number;
  name: string;
  archived: boolean;
  created_at: string;
}

interface OrgState {
  orgs: Org[];
  current: number | null;
  currentOrg: Org | undefined;
  /** Switch to another organisation; every page below the shell reloads its data. */
  select: (id: number, to?: string) => Promise<void>;
  reload: () => void;
}

const FALLBACK: OrgState = { orgs: [], current: null, currentOrg: undefined, select: async () => {}, reload: () => {} };
const Ctx = createContext<OrgState>(FALLBACK);

export function OrgProvider({ children }: { children: ReactNode }) {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [current, setCurrent] = useState<number | null>(null);
  const [tick, setTick] = useState(0);
  const navigate = useNavigate();
  const { pathname } = useLocation();

  useEffect(() => {
    api
      .get<{ current: number; items: Org[] }>("/api/orgs")
      .then((r) => {
        setOrgs(r.items);
        setCurrent(r.current);
      })
      .catch(() => {});
  }, [tick]);

  const select = useCallback(
    async (id: number, to?: string) => {
      await api.post("/api/orgs/select", { id });
      setCurrent(id);
      // A record page (/incidents/7) belongs to the old organisation; go to its list instead.
      const next = to ?? pathname.replace(/\/\d+$/, "");
      navigate(next || "/");
    },
    [navigate, pathname],
  );

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return <Ctx.Provider value={{ orgs, current, currentOrg: orgs.find((o) => o.id === current), select, reload }}>{children}</Ctx.Provider>;
}

export const useOrg = () => useContext(Ctx);
