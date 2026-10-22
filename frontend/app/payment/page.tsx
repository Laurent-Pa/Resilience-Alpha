"use client";

import { useEffect, useState, SyntheticEvent } from "react";
import { submitTransfer, extractErrorMessage } from "@/lib/payments";
import { getAccessToken, login } from "@/lib/auth";
import { Navbar } from "@/components/public/layout/Navbar";
import {
  maskIban,
  formatEuros,
  formatIbanInput,
} from "@/lib/format";
import type { TransferPayload } from "@/lib/crypto";

type SubmissionState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "success"; maskedIban: string; amount: string }
  | { status: "error"; message: string };

const INPUT_CLASSES =
  "mt-1 w-full rounded-2xl border border-[var(--ra-border-primary)] px-4 py-3 font-input text-base text-[var(--ra-foreground)] outline-none focus:border-[var(--ra-brand)]";

const PRIMARY_BUTTON_CLASSES =
  "mt-6 w-full rounded-2xl bg-[var(--ra-brand)] py-4 text-base font-semibold text-white transition hover:bg-[var(--ra-brand-hover)] disabled:cursor-not-allowed disabled:opacity-50";

export default function PaymentPage() {
  const [accountHolderName, setAccountHolderName] = useState("");
  const [iban, setIban] = useState("");
  const [bic, setBic] = useState("");
  const [amount, setAmount] = useState("");
  const [submission, setSubmission] = useState<SubmissionState>({
    status: "idle",
  });

  // null tant que la session n'a pas été vérifiée
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);

  useEffect(() => {
    getAccessToken().then((token) => setAuthenticated(token !== null));
  }, []);

  // Après un virement réussi, retour au formulaire vierge au bout de 5 s.
  useEffect(() => {
    if (submission.status !== "success") return;
    const timer = setTimeout(() => {
      setAccountHolderName("");
      setIban("");
      setBic("");
      setAmount("");
      setSubmission({ status: "idle" });
    }, 5000);
    return () => clearTimeout(timer);
  }, [submission.status]);

  const isSubmitting = submission.status === "submitting";

  if (authenticated === null) return null;

  if (!authenticated) {
    return (
      <>
        <Navbar />
        <main className="flex min-h-screen flex-col items-center justify-center p-6">
          <div className="w-full max-w-md rounded-2xl border border-[var(--ra-border-primary)] p-8 text-center">
            <h1 className="text-2xl font-bold">Accès refusé</h1>
            <p className="mt-4 text-[var(--ra-input-text)]">
              Vous devez être connecté pour effectuer un virement.
            </p>
            <button
              type="button"
              onClick={() => login()}
              className={PRIMARY_BUTTON_CLASSES}
            >
              Se connecter
            </button>
          </div>
        </main>
      </>
    );
  }

  async function handleSubmit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();

    const amountInEuros = parseFloat(amount);
    if (Number.isNaN(amountInEuros) || amountInEuros <= 0) {
      setSubmission({
        status: "error",
        message: "Le montant saisi n'est pas valide.",
      });
      return;
    }

    const payload: TransferPayload = {
      iban: iban.replace(/\s+/g, "").toUpperCase(),
      account_holder_name: accountHolderName,
      ...(bic.trim() ? { bic: bic.trim().toUpperCase() } : {}),
    };

    setSubmission({ status: "submitting" });

    try {
      const result = await submitTransfer(payload, amount);

      if (result.ok) {
        setSubmission({
          status: "success",
          maskedIban: maskIban(payload.iban),
          amount,
        });
      } else {
        const backendMessage = extractErrorMessage(result.body);
        setSubmission({
          status: "error",
          message:
            backendMessage ??
            "Le virement n'a pas pu être traité (code " +
              result.status +
              "). Merci de vérifier vos informations et réessayer.",
        });
      }
    } catch {
      setSubmission({
        status: "error",
        message:
          "Une erreur est survenue lors de la communication avec le serveur.",
      });
    }
  }

  if (submission.status === "success") {
    return (
      <>
        <Navbar />
        <main className="flex min-h-screen flex-col items-center justify-center p-6">
          <div className="w-full max-w-md rounded-2xl border border-[var(--ra-border-primary)] p-8 text-center">
            <h1 className="text-2xl font-bold">Virement initié</h1>
            <p className="mt-4 text-[var(--ra-input-text)]">
              Virement de {formatEuros(submission.amount)} vers{" "}
              {submission.maskedIban} enregistré avec succès.
            </p>
            <p className="mt-2 text-sm text-[var(--ra-input-text)]">
              Retour au formulaire dans 5 secondes...
            </p>
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <Navbar />
      <main className="flex min-h-screen flex-col items-center justify-center p-6">
        <form
          onSubmit={handleSubmit}
          className="w-full max-w-md rounded-2xl border border-[var(--ra-border-primary)] p-8"
        >
          <h1 className="text-2xl font-bold">Virement bancaire</h1>

          <div className="mt-6">
            <label
              htmlFor="accountHolderName"
              className="block text-sm text-[var(--ra-input-text)]"
            >
              Titulaire du compte
            </label>
            <input
              id="accountHolderName"
              type="text"
              required
              autoComplete="off"
              value={accountHolderName}
              onChange={(e) => setAccountHolderName(e.target.value)}
              className={INPUT_CLASSES}
              placeholder="Jean Dupont"
            />
          </div>

          <div className="mt-4">
            <label htmlFor="iban" className="block text-sm text-[var(--ra-input-text)]">
              IBAN
            </label>
            <input
              id="iban"
              type="text"
              required
              autoComplete="off"
              value={iban}
              onChange={(e) => setIban(formatIbanInput(e.target.value))}
              className={INPUT_CLASSES}
              placeholder="FR76 3000 6000 0112 3456 7890 189"
            />
          </div>

          <div className="mt-4">
            <label htmlFor="bic" className="block text-sm text-[var(--ra-input-text)]">
              BIC (optionnel)
            </label>
            <input
              id="bic"
              type="text"
              autoComplete="off"
              value={bic}
              onChange={(e) => setBic(e.target.value)}
              className={INPUT_CLASSES}
              placeholder="AGRIFRPP"
            />
          </div>

          <div className="mt-4">
            <label htmlFor="amount" className="block text-sm text-[var(--ra-input-text)]">
              Montant (€)
            </label>
            <input
              id="amount"
              type="number"
              step="0.01"
              min="0.01"
              required
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className={INPUT_CLASSES}
              placeholder="135.00"
            />
          </div>

          {submission.status === "error" && (
            <p className="mt-4 text-sm text-[var(--ra-status-alert-text)]">
              {submission.message}
            </p>
          )}

          <button type="submit" disabled={isSubmitting} className={PRIMARY_BUTTON_CLASSES}>
            {isSubmitting ? "Envoi en cours..." : "Effectuer le virement"}
          </button>
        </form>
      </main>
    </>
  );
}
