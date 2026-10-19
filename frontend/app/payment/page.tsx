"use client";

import { useState, SyntheticEvent } from "react";
import { submitTransfer } from "@/lib/payments";
import {
  maskIban,
  eurosToCents,
  formatCentsAsEuros,
  formatIbanInput,
} from "@/lib/format";
import type { TransferPayload } from "@/lib/crypto";

type SubmissionState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "success"; maskedIban: string; amountCents: number }
  | { status: "error"; message: string };

export default function PaymentPage() {
  const [accountHolderName, setAccountHolderName] = useState("");
  const [iban, setIban] = useState("");
  const [bic, setBic] = useState("");
  const [amount, setAmount] = useState("");
  const [submission, setSubmission] = useState<SubmissionState>({
    status: "idle",
  });

  const isSubmitting = submission.status === "submitting";

  async function handleSubmit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();

    const amountInEuros = Number.parseFloat(amount);
    if (Number.isNaN(amountInEuros) || amountInEuros <= 0) {
      setSubmission({
        status: "error",
        message: "Le montant saisi n'est pas valide.",
      });
      return;
    }

    const amountCents = eurosToCents(amountInEuros);

    const payload: TransferPayload = {
      iban: iban.replace(/\s+/g, "").toUpperCase(),
      account_holder_name: accountHolderName,
      ...(bic.trim() ? { bic: bic.trim().toUpperCase() } : {}),
    };

    setSubmission({ status: "submitting" });

    try {
      const result = await submitTransfer(payload, amountCents);

      if (result.ok) {
        setSubmission({
          status: "success",
          maskedIban: maskIban(payload.iban),
          amountCents,
        });
      } else {
        // TODO: affiner une fois le schéma d'erreur confirmé via Swagger
        setSubmission({
          status: "error",
          message:
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
      <main className="flex min-h-screen flex-col items-center justify-center p-6">
        <div className="w-full max-w-md rounded-2xl border border-gray-200 p-8 text-center">
          <h1 className="text-2xl font-bold">Virement initié</h1>
          <p className="mt-4 text-gray-600">
            Virement de {formatCentsAsEuros(submission.amountCents)} vers{" "}
            {submission.maskedIban} enregistré avec succès.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-6">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-2xl border border-gray-200 p-8"
      >
        <h1 className="text-2xl font-bold">Virement bancaire</h1>

        <div className="mt-6">
          <label
            htmlFor="accountHolderName"
            className="block text-sm text-gray-500"
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
            className="mt-1 w-full rounded-lg border border-gray-300 px-4 py-3 text-base outline-none focus:border-blue-500"
            placeholder="Jean Dupont"
          />
        </div>

        <div className="mt-4">
          <label htmlFor="iban" className="block text-sm text-gray-500">
            IBAN
          </label>
          <input
            id="iban"
            type="text"
            required
            autoComplete="off"
            value={iban}
            onChange={(e) => setIban(formatIbanInput(e.target.value))}
            className="mt-1 w-full rounded-lg border border-gray-300 px-4 py-3 text-base outline-none focus:border-blue-500"
            placeholder="FR76 3000 6000 0112 3456 7890 189"
          />
        </div>

        <div className="mt-4">
          <label htmlFor="bic" className="block text-sm text-gray-500">
            BIC (optionnel)
          </label>
          <input
            id="bic"
            type="text"
            autoComplete="off"
            value={bic}
            onChange={(e) => setBic(e.target.value)}
            className="mt-1 w-full rounded-lg border border-gray-300 px-4 py-3 text-base outline-none focus:border-blue-500"
            placeholder="AGRIFRPP"
          />
        </div>

        <div className="mt-4">
          <label htmlFor="amount" className="block text-sm text-gray-500">
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
            className="mt-1 w-full rounded-lg border border-gray-300 px-4 py-3 text-base outline-none focus:border-blue-500"
            placeholder="135.00"
          />
        </div>

        {submission.status === "error" && (
          <p className="mt-4 text-sm text-red-600">{submission.message}</p>
        )}

        <button
          type="submit"
          disabled={isSubmitting}
          className="mt-6 w-full rounded-lg bg-blue-600 py-4 text-base font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
        >
          {isSubmitting ? "Envoi en cours..." : "Effectuer le virement"}
        </button>
      </form>
    </main>
  );
}
