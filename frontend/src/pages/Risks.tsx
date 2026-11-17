import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { LEVEL_STYLE, RecordForm, lines, orNull, toDraft, type Draft, type Field } from "../components/RecordForm";
import { Card, EmptyState, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks";
import { fmtDate, fmtNum } from "../i18n";

interface RiskRow {
  id: number;
  title: string;
  description: string;
  category: string;
  likelihood: number;
  impact: number;
  score: number;
  level: string;
  residual_likelihood: number | null;
  residual_impact: number | null;
  residual_score: number | null;
  residual_level: string | null;
  treatment: string;
  status: string;
  owner: string;
  requirement_ids: string[];
  controls: string;
  review_due: string | null;
  acceptance_expires_on: string | null;
  acceptance_expired: boolean;
  acceptance_note: string;
}

const band = (score: number) => (score >= 20 ? "critical" : score >= 10 ? "high" : score >= 5 ? "medium" : "low");
const CELL: Record<string, string> = { low: "bg-green-100", medium: "bg-amber-100", high: "bg-orange-200", critical: "bg-red-300" };

export function HeatMap({ rows, selected, onSelect, compact = false }: { rows: { likelihood: number; impact: number; status: string }[]; selected?: string | null; onSelect?: (key: string | null) => void; compact?: boolean }) {
  const { t } = useTranslation();
  const count = (l: number, i: number) => rows.filter((r) => r.status !== "closed" && r.likelihood === l && r.impact === i).length;
  const size = compact ? "h-7 w-7 text-[11px]" : "h-11 w-11 text-sm sm:h-12 sm:w-12";
  return (
    <div className="flex items-stretch gap-2" dir="ltr">
      <div className="flex items-center">
        <span className="text-xs text-slate-500 [writing-mode:vertical-rl] rotate-180">{t("risks.impact")}</span>
      </div>
      <div>
        <div className="grid grid-cols-5 gap-1" role="grid" aria-label={t("risks.heatMap")}>
          {[5, 4, 3, 2, 1].map((i) =>
            [1, 2, 3, 4, 5].map((l) => {
              const n = count(l, i);
              const key = `${l}-${i}`;
              const label = t("risks.cell", { count: fmtNum(n), l: fmtNum(l), i: fmtNum(i) });
              return (
                <button
                  key={key}
                  type="button"
                  role="gridcell"
                  aria-label={label}
                  title={label}
                  disabled={!onSelect || n === 0}
                  onClick={() => onSelect?.(selected === key ? null : key)}
                  className={`${size} flex items-center justify-center rounded-md font-semibold ${CELL[band(l * i)]} ${selected === key ? "ring-2 ring-brand-700" : ""} ${n ? "text-ink" : "text-transparent"}`}
                >
                  {n || "·"}
                </button>
              );
            }),
          )}
        </div>
        <div className="mt-1 text-center text-xs text-slate-500">{t("risks.likelihood")} →</div>
      </div>
    </div>
  );
}

function riskFields(t: (k: string) => string): Field[] {
  const scale = (prefix: string) => [1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: `${n} · ${t(`${prefix}.${n}`)}` }));
  const opt = (prefix: string, keys: string[]) => keys.map((k) => ({ value: k, label: t(`${prefix}.${k}`) }));
  return [
    { key: "title", label: t("risks.name"), required: true },
    { key: "description", label: t("risks.description"), type: "textarea" },
    { key: "category", label: t("risks.category"), half: true },
    { key: "owner", label: t("gov.owner"), half: true },
    { key: "likelihood", label: t("risks.likelihood"), type: "select", options: scale("risks.likelihoodScale"), half: true },
    { key: "impact", label: t("risks.impact"), type: "select", options: scale("risks.impactScale"), half: true },
    { key: "residual_likelihood", label: t("risks.residualLikelihood"), type: "select", options: [{ value: "", label: "—" }, ...scale("risks.likelihoodScale")], half: true },
    { key: "residual_impact", label: t("risks.residualImpact"), type: "select", options: [{ value: "", label: "—" }, ...scale("risks.impactScale")], half: true },
    { key: "treatment", label: t("risks.treatment"), type: "select", options: opt("risks.treatments", ["mitigate", "transfer", "avoid", "accept"]), half: true },
    { key: "status", label: t("gov.status"), type: "select", options: opt("risks.statuses", ["open", "treating", "closed"]), half: true },
    { key: "controls", label: t("risks.controls"), type: "textarea" },
    { key: "requirement_ids", label: t("gov.requirements"), type: "lines", dir: "ltr", half: true },
    { key: "review_due", label: t("gov.reviewDue"), type: "date", half: true },
  ];
}

const EMPTY: Draft = { title: "", description: "", category: "", owner: "", likelihood: "3", impact: "3", residual_likelihood: "", residual_impact: "", treatment: "mitigate", status: "open", controls: "", requirement_ids: "", review_due: "" };
const num = (v: string | boolean | undefined) => (v === "" || v === undefined ? null : Number(v));
const body = (d: Draft) => ({
  title: d.title, description: d.description, category: d.category, owner: d.owner, likelihood: Number(d.likelihood), impact: Number(d.impact),
  residual_likelihood: num(d.residual_likelihood), residual_impact: num(d.residual_impact), treatment: d.treatment,
  status: d.status === "accepted" ? "open" : d.status, controls: d.controls, requirement_ids: lines(d.requirement_ids), review_due: orNull(d.review_due),
});

export default function Risks() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi<RiskRow[]>("/api/risks");
  const [editing, setEditing] = useState<{ id: number | null; draft: Draft } | null>(null);
  const [accepting, setAccepting] = useState<RiskRow | null>(null);
  const [cell, setCell] = useState<string | null>(null);
  const rows = (data ?? []).filter((r) => !cell || `${r.likelihood}-${r.impact}` === cell);

  return (
    <>
      <PageHeader
        title={t("risks.title")}
        subtitle={t("risks.subtitle")}
        actions={can("governance.write") && <button className="btn-primary" onClick={() => setEditing({ id: null, draft: EMPTY })}>+ {t("gov.add")}</button>}
      />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? (
        <Spinner />
      ) : (
        <div className="grid gap-5 xl:grid-cols-[auto_1fr]">
          <Card title={t("risks.heatMap")}>
            <HeatMap rows={data ?? []} selected={cell} onSelect={setCell} />
            <p className="mt-3 max-w-xs text-xs text-slate-500">{t("risks.bands")}</p>
          </Card>
          <Card>
            {!rows.length ? (
              <EmptyState title={t("gov.empty")} />
            ) : (
              <div className="overflow-x-auto">
                <table className="table-base">
                  <thead>
                    <tr>
                      <th>{t("risks.name")}</th>
                      <th>{t("risks.inherent")}</th>
                      <th>{t("risks.residual")}</th>
                      <th>{t("risks.treatment")}</th>
                      <th>{t("gov.status")}</th>
                      <th>
                        <span className="sr-only">{t("common.actions")}</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.id} className={r.status === "closed" ? "opacity-60" : ""}>
                        <td>
                          <div className="font-medium">{r.title}</div>
                          <div className="mt-0.5 flex flex-wrap gap-2 text-xs text-slate-500">
                            {r.category && <span>{r.category}</span>}
                            {r.owner && <span>· {r.owner}</span>}
                            {r.requirement_ids.map((id) => (
                              <Link key={id} to={`/requirements/${id}`} className="text-brand-700 hover:underline" dir="ltr">
                                {id.toUpperCase().replace("-", ".")}
                              </Link>
                            ))}
                          </div>
                        </td>
                        <td>
                          <span className={`chip ${LEVEL_STYLE[r.level]}`}>
                            {fmtNum(r.score)} · {t(`risks.levels.${r.level}`)}
                          </span>
                        </td>
                        <td>{r.residual_score ? <span className={`chip ${LEVEL_STYLE[r.residual_level!]}`}>{fmtNum(r.residual_score)} · {t(`risks.levels.${r.residual_level}`)}</span> : "—"}</td>
                        <td className="text-sm">{t(`risks.treatments.${r.treatment}`)}</td>
                        <td className="text-sm">
                          <div>{t(`risks.statuses.${r.status}`)}</div>
                          {r.status === "accepted" && r.acceptance_expires_on && (
                            <div className={`text-xs ${r.acceptance_expired ? "font-semibold text-red-700" : "text-slate-500"}`}>
                              {r.acceptance_expired ? t("risks.acceptanceExpired") : t("risks.acceptedUntil", { when: fmtDate(r.acceptance_expires_on) })}
                            </div>
                          )}
                        </td>
                        <td className="whitespace-nowrap text-end">
                          {can("governance.write") && (
                            <button
                              className="btn-ghost text-xs"
                              onClick={() =>
                                setEditing({
                                  id: r.id,
                                  draft: { ...EMPTY, ...toDraft(r), likelihood: String(r.likelihood), impact: String(r.impact), residual_likelihood: r.residual_likelihood ? String(r.residual_likelihood) : "", residual_impact: r.residual_impact ? String(r.residual_impact) : "", requirement_ids: r.requirement_ids.join("\n"), review_due: r.review_due ?? "" },
                                })
                              }
                            >
                              {t("common.edit")}
                            </button>
                          )}
                          {can("risks.accept") && r.status !== "accepted" && r.status !== "closed" && (
                            <button className="btn-ghost text-xs" onClick={() => setAccepting(r)}>
                              {t("risks.accept")}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}
      {editing && (
        <RecordForm
          title={editing.id ? t("gov.edit") : t("gov.add")}
          fields={riskFields(t)}
          initial={editing.draft}
          onClose={() => setEditing(null)}
          onSubmit={async (d) => {
            if (editing.id) await api.put(`/api/risks/${editing.id}`, body(d));
            else await api.post("/api/risks", body(d));
            reload();
          }}
        />
      )}
      {accepting && (
        <RecordForm
          title={`${t("risks.acceptTitle")}: ${accepting.title}`}
          fields={[
            { key: "note", label: t("risks.acceptNote"), type: "textarea", required: true },
            { key: "expires_on", label: t("risks.acceptExpires"), type: "date", required: true },
          ]}
          initial={{ note: "", expires_on: "" }}
          onClose={() => setAccepting(null)}
          onSubmit={async (d) => {
            await api.post(`/api/risks/${accepting.id}/accept`, { note: d.note, expires_on: d.expires_on });
            reload();
          }}
        />
      )}
    </>
  );
}
