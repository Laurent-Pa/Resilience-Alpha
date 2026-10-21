"use client";

import { useCallback, useEffect, useState } from "react";
import { AuthGate } from "@/components/admin/auth/AuthGate";
import { useAdminAuth } from "@/app/admin/AdminAuthContext";
import { ProberSuccessChart } from "@/components/admin/monitoring/ProberSuccessChart";
import { StatTile } from "@/components/admin/ui/StatTile";
import {
  fetchProberSuccessRate,
  formatMinute,
  formatPct,
  summarize,
  type ProberSuccessRate,
} from "@/lib/admin-prober";

// Les points sont des minutes complètes : rafraîchir plus souvent n'apporterait rien.
const REFRESH_MS = 30_000;

export default function AdminMonitoringPage() {
  return (
    <AuthGate>
      <AdminMonitoringContent />
    </AuthGate>
  );
}

function AdminMonitoringContent() {
  const { accessToken } = useAdminAuth();
  const [data, setData] = useState<ProberSuccessRate | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [refreshFailed, setRefreshFailed] = useState(false);

  const load = useCallback(
    async (cancelledRef: { current: boolean }) => {
      try {
        const next = await fetchProberSuccessRate(accessToken);
        if (cancelledRef.current) return;
        setData(next);
        setUpdatedAt(new Date());
        setRefreshFailed(false);
      } catch {
        // On garde le dernier affichage : un trou réseau ne doit pas effacer le graphique.
        if (!cancelledRef.current) setRefreshFailed(true);
      }
    },
    [accessToken]
  );

  useEffect(() => {
    const cancelledRef = { current: false };
    // Onglet masqué : inutile d'interroger l'API pour un graphique que personne ne voit.
    const refreshIfVisible = () => {
      if (document.visibilityState === "visible") load(cancelledRef);
    };
    // Fetch réseau au montage puis à intervalle, pas un "miroir" de props :
    // cas explicitement documenté par la règle comme faux positif légitime.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load(cancelledRef);
    const timer = window.setInterval(refreshIfVisible, REFRESH_MS);
    document.addEventListener("visibilitychange", refreshIfVisible);
    return () => {
      cancelledRef.current = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refreshIfVisible);
    };
  }, [load]);

  return (
    <main className="flex-1 p-8">
      <h1 className="text-2xl font-semibold text-[var(--ra-foreground)]">Monitoring</h1>
      <p className="mt-1 text-sm text-[var(--ra-input-text)]">
        Taux de réussite de la sonde de supervision, minute par minute, sur la dernière heure.
      </p>

      <div className="mt-8 flex w-full max-w-[820px] flex-col gap-6">
        {data === null ? (
          refreshFailed ? (
            <p role="alert" className="py-8 text-center text-sm text-[var(--ra-status-alert-text)]">
              Impossible de charger le taux de réussite. Nouvel essai dans un instant.
            </p>
          ) : (
            <p className="py-8 text-center text-sm text-[var(--ra-input-text)]">Chargement...</p>
          )
        ) : (
          <ProberPanel data={data} updatedAt={updatedAt} refreshFailed={refreshFailed} />
        )}
      </div>
    </main>
  );
}

interface ProberPanelProps {
  data: ProberSuccessRate;
  updatedAt: Date | null;
  refreshFailed: boolean;
}

function ProberPanel({ data, updatedAt, refreshFailed }: ProberPanelProps) {
  const { windowPct, last, minutesWithoutSuccess } = summarize(data.points);
  const perMinute = Math.round((60 / data.interval_s) * 100) / 100;

  return (
    <>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatTile label="Réussite sur l'heure" value={formatPct(windowPct)} />
        <StatTile
          label="Dernière minute complète"
          value={last ? formatPct(last.success_pct) : "—"}
          hint={
            last
              ? `${formatMinute(last.minute)} · ${last.success_count} / ${last.expected_count} virements`
              : undefined
          }
        />
        <StatTile
          label="Minutes sans réussite"
          value={String(minutesWithoutSuccess)}
          hint={`sur ${data.points.length}`}
        />
      </div>

      <div className="rounded-[4px] border border-[var(--ra-border-primary)] p-4">
        <ProberSuccessChart points={data.points} />
      </div>


      <p className="text-xs text-[var(--ra-input-text)]">
        Hypothèse de calcul : une sonde toutes les {data.interval_s} s, soit {perMinute} virements
        attendus par minute. Une sonde arrêtée n&apos;écrit rien : ses minutes ressortent à 0 %.
        {updatedAt && ` Mis à jour à ${updatedAt.toLocaleTimeString("fr-FR")}.`}
        {refreshFailed && (
          <span role="status" className="text-[var(--ra-status-alert-text)]">
            {" "}
            Dernière actualisation échouée : données précédentes affichées.
          </span>
        )}
      </p>
    </>
  );
}
