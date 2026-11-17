import { useTranslation } from "react-i18next";
import { EmptyState, PageHeader } from "../components/ui";

export default function Dashboard() {
  const { t } = useTranslation();
  return (
    <>
      <PageHeader title={t("dashboard.title")} subtitle={t("dashboard.scoreCaption")} />
      <EmptyState title={t("dashboard.noRuns")} hint={t("dashboard.noRunsHint")} />
    </>
  );
}
