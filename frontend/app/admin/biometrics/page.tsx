"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { AuthGate } from "@/components/admin/auth/AuthGate";
import { useAdminAuth } from "@/app/admin/AdminAuthContext";
import { FaceCapture } from "@/components/admin/biometrics/FaceCapture";
import {
  BiometricsError,
  OUTCOME_LABELS,
  enrollFace,
  fetchBiometricAttempts,
  fetchBiometricUsers,
  revokeFace,
  unlockUser,
  type BiometricAttempt,
  type BiometricUser,
} from "@/lib/admin-biometrics";

const ROW_SHELL =
  "grid min-h-[48px] w-full items-center justify-items-center gap-4 rounded-[4px] border border-[var(--ra-border-primary)] px-4";
const USERS_GRID = "grid-cols-[1fr_1.4fr_1fr_1.6fr]";
const ATTEMPTS_GRID = "grid-cols-[1.2fr_1fr_1fr_80px]";
const BUTTON =
  "rounded-lg border border-[var(--ra-border-primary)] px-2.5 py-1 text-xs font-medium text-[var(--ra-foreground)] hover:bg-[var(--ra-background-secondary)] disabled:cursor-not-allowed disabled:opacity-50";

export default function AdminBiometricsPage() {
  return (
    <AuthGate>
      <AdminBiometricsContent />
    </AuthGate>
  );
}

function AdminBiometricsContent() {
  const { accessToken } = useAdminAuth();
  const [users, setUsers] = useState<BiometricUser[] | null>(null);
  const [attempts, setAttempts] = useState<BiometricAttempt[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [busy, setBusy] = useState<string | null>(null); // identifiant en cours d'action

  const load = useCallback(
    async (cancelledRef: { current: boolean }) => {
      try {
        const [nextUsers, nextAttempts] = await Promise.all([
          fetchBiometricUsers(accessToken),
          fetchBiometricAttempts(accessToken),
        ]);
        if (cancelledRef.current) return;
        setUsers(nextUsers);
        setAttempts(nextAttempts);
        setLoadError(false);
      } catch {
        if (!cancelledRef.current) setLoadError(true);
      }
    },
    [accessToken]
  );

  const refresh = useCallback(() => load({ current: false }), [load]);

  useEffect(() => {
    const cancelledRef = { current: false };
    // Fetch réseau au montage, pas un "miroir" de props (faux positif documenté de la règle).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load(cancelledRef);
    return () => {
      cancelledRef.current = true;
    };
  }, [load]);

  async function act(username: string, action: () => Promise<void>) {
    setBusy(username);
    try {
      await action();
    } finally {
      setBusy(null);
      await refresh();
    }
  }

  return (
    <main className="flex-1 p-8">
      <h1 className="text-2xl font-semibold text-[var(--ra-foreground)]">Biométrie</h1>
      <p className="mt-1 max-w-[820px] text-sm text-[var(--ra-input-text)]">
        Habilitations de la reconnaissance faciale. Les comptes du rôle « ops » doivent être
        reconnus par la caméra du PC Hôte entre la saisie de l&apos;identifiant et celle du mot
        de passe. Seule une empreinte chiffrée est conservée, jamais la photo.
      </p>

      <div className="mt-8 flex w-full max-w-[820px] flex-col gap-10">
        <EnrollPanel accessToken={accessToken} onEnrolled={refresh} />

        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold text-[var(--ra-foreground)]">Utilisateurs</h2>
          {users === null ? (
            <p className="py-6 text-center text-sm text-[var(--ra-input-text)]">
              {loadError ? "Impossible de charger les habilitations." : "Chargement..."}
            </p>
          ) : users.length === 0 ? (
            <p className="py-6 text-center text-sm text-[var(--ra-input-text)]">
              Aucun utilisateur enrôlé.
            </p>
          ) : (
            <>
              <div
                className={`${ROW_SHELL} ${USERS_GRID} bg-[var(--ra-background-secondary)] text-xs font-medium text-[var(--ra-input-text)]`}
              >
                <span>Identifiant</span>
                <span>Enrôlement</span>
                <span>État</span>
                <span>Actions</span>
              </div>
              {users.map((u) => (
                <div key={u.username} className={`${ROW_SHELL} ${USERS_GRID} bg-[var(--ra-background)]`}>
                  <span className="text-sm font-medium text-[var(--ra-foreground)]">{u.username}</span>
                  <span className="text-center text-xs text-[var(--ra-input-text)]">
                    {u.enrolled_at
                      ? `${formatDate(u.enrolled_at)} par ${u.enrolled_by}`
                      : "non enrôlé"}
                  </span>
                  <StateBadge user={u} />
                  <span className="flex flex-wrap justify-center gap-2">
                    {(u.locked_until || u.failures > 0) && (
                      <button
                        type="button"
                        className={BUTTON}
                        disabled={busy === u.username}
                        onClick={() => act(u.username, () => unlockUser(u.username, accessToken))}
                      >
                        Déverrouiller
                      </button>
                    )}
                    {u.enrolled && (
                      <button
                        type="button"
                        className={`${BUTTON} text-[var(--ra-status-alert-text)]`}
                        disabled={busy === u.username}
                        onClick={() => {
                          if (window.confirm(`Révoquer le visage de ${u.username} ? Il ne pourra plus se connecter au back-office.`)) {
                            act(u.username, () => revokeFace(u.username, accessToken));
                          }
                        }}
                      >
                        Révoquer
                      </button>
                    )}
                  </span>
                </div>
              ))}
            </>
          )}
        </section>

        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold text-[var(--ra-foreground)]">
            Dernières tentatives
          </h2>
          {attempts.length === 0 ? (
            <p className="py-6 text-center text-sm text-[var(--ra-input-text)]">
              Aucune tentative enregistrée.
            </p>
          ) : (
            <>
              <div
                className={`${ROW_SHELL} ${ATTEMPTS_GRID} bg-[var(--ra-background-secondary)] text-xs font-medium text-[var(--ra-input-text)]`}
              >
                <span>Date</span>
                <span>Identifiant</span>
                <span>Résultat</span>
                <span>Score</span>
              </div>
              {attempts.map((a, i) => (
                <div key={`${a.at}-${i}`} className={`${ROW_SHELL} ${ATTEMPTS_GRID} bg-[var(--ra-background)]`}>
                  <span className="text-sm text-[var(--ra-foreground)]">{formatDate(a.at)}</span>
                  <span className="text-sm text-[var(--ra-foreground)]">{a.username}</span>
                  <OutcomeBadge attempt={a} />
                  <span className="font-mono text-xs text-[var(--ra-input-text)]">
                    {a.score === null ? "—" : a.score.toFixed(2)}
                  </span>
                </div>
              ))}
            </>
          )}
        </section>
      </div>
    </main>
  );
}

function EnrollPanel({
  accessToken,
  onEnrolled,
}: {
  accessToken: string | null;
  onEnrolled: () => Promise<void>;
}) {
  const [username, setUsername] = useState("");
  const [capturing, setCapturing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  function start(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    setCapturing(true);
  }

  async function handleCapture(image: string) {
    setCapturing(false);
    setSaving(true);
    try {
      await enrollFace(username.trim(), image, accessToken);
      setMessage({ ok: true, text: `Visage de ${username.trim()} enregistré.` });
      setUsername("");
      await onEnrolled();
    } catch (err) {
      const text =
        err instanceof BiometricsError && err.code
          ? err.message
          : "Échec de l'enregistrement. Réessayez.";
      setMessage({ ok: false, text });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="flex flex-col gap-4 rounded-[4px] border border-[var(--ra-border-primary)] p-4">
      <div>
        <h2 className="text-lg font-semibold text-[var(--ra-foreground)]">Enrôler un visage</h2>
        <p className="mt-1 text-xs text-[var(--ra-input-text)]">
          Identifiant Keycloak de la personne, présente devant la caméra, seule et de face.
          Un nouvel enrôlement remplace le précédent.
        </p>
      </div>
      <form onSubmit={start} className="flex flex-wrap items-center gap-3">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="identifiant (ex. operator)"
          required
          pattern="[A-Za-z0-9._@\-]{1,255}"
          disabled={capturing || saving}
          className="h-9 w-64 rounded-lg border border-[var(--ra-border-primary)] px-3 text-sm text-[var(--ra-foreground)]"
        />
        {capturing ? (
          <button type="button" className={BUTTON} onClick={() => setCapturing(false)}>
            Annuler
          </button>
        ) : (
          <button type="submit" className={BUTTON} disabled={saving || !username.trim()}>
            {saving ? "Enregistrement..." : "Ouvrir la caméra"}
          </button>
        )}
      </form>
      {capturing && <FaceCapture onCapture={handleCapture} />}
      {message && (
        <p
          role={message.ok ? "status" : "alert"}
          className={`text-sm ${message.ok ? "text-[var(--ra-status-ok-text)]" : "text-[var(--ra-status-alert-text)]"}`}
        >
          {message.text}
        </p>
      )}
    </section>
  );
}

function StateBadge({ user }: { user: BiometricUser }) {
  if (user.locked_until) {
    return (
      <Badge tone="alert">
        bloqué jusqu&apos;à {new Date(user.locked_until).toLocaleTimeString("fr-FR")}
      </Badge>
    );
  }
  if (user.failures > 0) return <Badge tone="warning">{user.failures} échec(s)</Badge>;
  return user.enrolled ? <Badge tone="ok">actif</Badge> : <Badge tone="neutral">—</Badge>;
}

function OutcomeBadge({ attempt }: { attempt: BiometricAttempt }) {
  const tone =
    attempt.outcome === "match"
      ? "ok"
      : attempt.outcome === "no_face" || attempt.outcome === "invalid_image"
        ? "neutral"
        : "alert";
  return <Badge tone={tone}>{OUTCOME_LABELS[attempt.outcome] ?? attempt.outcome}</Badge>;
}

const TONES = {
  ok: "text-[var(--ra-status-ok-text)] bg-[var(--ra-status-ok-bg)]",
  warning: "text-[var(--ra-status-warning-text)] bg-[var(--ra-status-warning-bg)]",
  alert: "text-[var(--ra-status-alert-text)] bg-[var(--ra-status-alert-bg)]",
  neutral: "text-[var(--ra-input-text)] bg-[var(--ra-background-secondary)]",
};

function Badge({ tone, children }: { tone: keyof typeof TONES; children: React.ReactNode }) {
  return (
    <span
      className={`inline-flex min-h-8 items-center justify-center rounded-full px-3 text-center text-xs font-medium ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}
