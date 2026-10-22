"use client";

import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { usePathname } from "next/navigation";
import { useAdminAuth } from "@/app/admin/AdminAuthContext";
import {
  AssistantError,
  MAX_QUESTION_LENGTH,
  askAssistant,
  sourceLabel,
  type AssistantSource,
} from "@/lib/admin-assistant";

/** Pages du back-office où l'assistant est proposé. */
const ASSISTANT_PATHS = ["/admin/payments", "/admin/monitoring"];

const SUGGESTIONS = [
  "Que faire en cas de flood HTTP sur payment-api ?",
  "Que signifie un incident ESCALATED ?",
  "Comment débloquer une IP bloquée par erreur ?",
];

type Message =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "assistant"; text: string; sources: AssistantSource[] }
  | { id: number; role: "error"; text: string; question: string }
  | { id: number; role: "notice"; text: string };

/** Un message avant attribution de son identifiant (Omit appliqué à chaque variante). */
type NewMessage = Message extends infer M ? (M extends Message ? Omit<M, "id"> : never) : never;

/**
 * Assistant documentaire (RAG) du back-office, réservé au rôle ops.
 *
 * Monté une seule fois dans le layout /admin : la conversation survit à la navigation
 * entre Paiements et Monitoring (un layout garde son état). Fenêtre non modale : la page
 * reste consultable pendant l'échange. L'assistant n'expose aucun bouton d'action sur la
 * plateforme : il explique et cite docs/exploitation/.
 */
export function AssistantPanel() {
  const { user, accessToken } = useAdminAuth();
  const pathname = usePathname();

  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [isPending, setIsPending] = useState(false);
  const [elapsedS, setElapsedS] = useState(0);
  const [hasUnread, setHasUnread] = useState(false);

  const nextId = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const isOpenRef = useRef(isOpen);
  const listRef = useRef<HTMLOListElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const restoreFocusRef = useRef(false);
  const titleId = useId();

  useEffect(() => {
    isOpenRef.current = isOpen;
    // À la fermeture, le focus revient au bouton « Assistant » (rendu à la place du
    // panneau, donc seulement après ce rendu).
    if (!isOpen && restoreFocusRef.current) {
      restoreFocusRef.current = false;
      launcherRef.current?.focus();
    }
  }, [isOpen]);

  // Chronomètre de la question en cours (une réponse prend ~1 min sur CPU).
  useEffect(() => {
    if (!isPending) return;
    const timer = window.setInterval(() => setElapsedS((s) => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, [isPending]);

  // Défilement : une nouvelle réponse s'affiche à partir de son début (elle dépasse souvent
  // la hauteur de la fenêtre compacte) ; sinon, on suit le bas de la conversation.
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const last = messages[messages.length - 1];
    if (!isPending && last?.role === "assistant") {
      const item = list.querySelector<HTMLElement>(`[data-message-id="${last.id}"]`);
      if (item) {
        list.scrollTop = item.offsetTop - list.offsetTop - 12;
        return;
      }
    }
    list.scrollTop = list.scrollHeight;
  }, [messages, isPending, isOpen]);

  useEffect(() => {
    if (isOpen) inputRef.current?.focus();
  }, [isOpen]);

  // Déconnexion (démontage du layout) : la question en cours est abandonnée.
  useEffect(() => () => controllerRef.current?.abort(), []);

  const isVisible =
    user !== null &&
    ASSISTANT_PATHS.some((p) => pathname === p || pathname?.startsWith(`${p}/`));
  if (!isVisible) {
    return null; // masqué, mais l'état (conversation) est conservé
  }

  function push(message: NewMessage) {
    const id = nextId.current++;
    setMessages((current) => [...current, { ...message, id } as Message]);
  }

  async function send(question: string) {
    const q = question.trim();
    if (!q || q.length > MAX_QUESTION_LENGTH || controllerRef.current) return;

    const controller = new AbortController();
    controllerRef.current = controller;
    setElapsedS(0);
    setIsPending(true);
    push({ role: "user", text: q });
    setDraft("");

    try {
      const { answer, sources } = await askAssistant(q, accessToken, controller.signal);
      push({ role: "assistant", text: answer, sources });
      if (!isOpenRef.current) setHasUnread(true);
    } catch (e) {
      if (controller.signal.aborted) {
        push({ role: "notice", text: "Question annulée." });
      } else {
        const text =
          e instanceof AssistantError ? e.message : "Erreur inattendue. Réessayez dans un instant.";
        push({ role: "error", text, question: q });
      }
    } finally {
      controllerRef.current = null;
      setIsPending(false);
    }
  }

  function open() {
    setIsOpen(true);
    setHasUnread(false);
  }

  function close() {
    restoreFocusRef.current = true;
    setIsOpen(false);
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void send(draft);
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Entrée envoie, Maj+Entrée va à la ligne.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send(draft);
    }
  }

  function handlePanelKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") close();
  }

  if (!isOpen) {
    return (
      <button
        ref={launcherRef}
        type="button"
        onClick={open}
        className="fixed bottom-6 right-6 z-30 flex items-center gap-2 rounded-full bg-[var(--ra-foreground)] px-4 py-3 text-sm font-medium text-white shadow-lg hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ra-brand)]"
      >
        <ChatIcon />
        Assistant
        {(hasUnread || isPending) && (
          <span
            className={`h-2 w-2 rounded-full bg-[var(--ra-brand)] ${isPending ? "animate-pulse" : ""}`}
            aria-hidden="true"
          />
        )}
        <span className="sr-only">
          {isPending ? " (réponse en préparation)" : hasUnread ? " (nouvelle réponse)" : ""}
        </span>
      </button>
    );
  }

  const remaining = MAX_QUESTION_LENGTH - draft.trim().length;
  const canSend = !isPending && draft.trim().length > 0 && remaining >= 0;

  return (
    <section
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      onKeyDown={handlePanelKeyDown}
      className={`fixed z-30 flex flex-col border border-[var(--ra-border-primary)] bg-[var(--ra-background)] shadow-xl ${
        isExpanded
          ? "bottom-0 right-0 top-[var(--ra-navbar-height)] w-[min(640px,50vw)] rounded-none border-y-0 border-r-0"
          : "bottom-6 right-6 h-[min(560px,calc(100vh-var(--ra-navbar-height)-3rem))] w-[380px] rounded-lg"
      }`}
    >
      <header className="flex items-start gap-2 border-b border-[var(--ra-border-primary)] px-4 py-3">
        <div className="min-w-0 flex-1">
          <h2 id={titleId} className="text-sm font-semibold text-[var(--ra-foreground)]">
            Assistant documentaire
          </h2>
          <p className="text-xs text-[var(--ra-input-text)]">
            Réponses tirées de la documentation d&apos;exploitation
          </p>
        </div>
        {messages.length > 0 && !isPending && (
          <HeaderButton label="Effacer la conversation" onClick={() => setMessages([])}>
            <TrashIcon />
          </HeaderButton>
        )}
        <HeaderButton
          label={isExpanded ? "Réduire la fenêtre" : "Agrandir la fenêtre"}
          onClick={() => setIsExpanded((v) => !v)}
        >
          {isExpanded ? <CollapseIcon /> : <ExpandIcon />}
        </HeaderButton>
        <HeaderButton label="Fermer l'assistant" onClick={close}>
          <CloseIcon />
        </HeaderButton>
      </header>

      <ol
        ref={listRef}
        aria-live="polite"
        aria-busy={isPending}
        className="flex flex-1 flex-col gap-3 overflow-y-auto px-4 py-4"
      >
        {messages.length === 0 && !isPending && (
          <li className="flex flex-col gap-3 text-sm text-[var(--ra-input-text)]">
            <p>
              Posez une question sur un incident, un message d&apos;erreur ou une procédure.
              L&apos;assistant répond à partir des runbooks et de la documentation, et cite ses
              sources.
            </p>
            <div className="flex flex-col items-start gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => void send(s)}
                  className="rounded-full border border-[var(--ra-border-primary)] px-3 py-1.5 text-left text-xs text-[var(--ra-foreground)] hover:bg-[var(--ra-background-secondary)]"
                >
                  {s}
                </button>
              ))}
            </div>
          </li>
        )}

        {messages.map((m) => (
          <MessageItem key={m.id} message={m} onRetry={isPending ? undefined : send} />
        ))}

        {isPending && (
          <li className="flex flex-col items-start gap-2 self-start rounded-lg bg-[var(--ra-background-secondary)] px-3 py-2 text-sm text-[var(--ra-input-text)]">
            <span>
              Recherche dans la documentation… <span className="tabular-nums">{elapsedS} s</span>
            </span>
            <span className="text-xs">Comptez environ une minute sur ce poste.</span>
            <button
              type="button"
              onClick={() => controllerRef.current?.abort()}
              className="text-xs font-medium text-[var(--ra-foreground)] underline underline-offset-2"
            >
              Annuler
            </button>
          </li>
        )}
      </ol>

      <form onSubmit={handleSubmit} className="border-t border-[var(--ra-border-primary)] px-4 py-3">
        <label htmlFor={`${titleId}-input`} className="sr-only">
          Votre question
        </label>
        <textarea
          ref={inputRef}
          id={`${titleId}-input`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleInputKeyDown}
          rows={isExpanded ? 3 : 2}
          placeholder="Votre question (Entrée pour envoyer, Maj+Entrée pour aller à la ligne)"
          className="font-input w-full resize-none rounded-[4px] border border-[var(--ra-border-primary)] px-3 py-2 text-sm text-[var(--ra-foreground)] placeholder:text-[var(--ra-input-text)] focus:border-[var(--ra-brand)] focus:outline-none"
        />
        <div className="mt-2 flex items-center justify-between gap-3">
          <p className="text-xs text-[var(--ra-input-text)]">
            {remaining < 200 ? (
              <span className={remaining < 0 ? "text-[var(--ra-status-alert-text)]" : ""}>
                {remaining} caractères restants
              </span>
            ) : (
              "N'exécute aucune action sur la plateforme."
            )}
          </p>
          <button
            type="submit"
            disabled={!canSend}
            className="rounded-[4px] bg-[var(--ra-brand)] px-4 py-1.5 text-sm font-medium text-white hover:bg-[var(--ra-brand-hover)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Envoyer
          </button>
        </div>
      </form>
    </section>
  );
}

function MessageItem({
  message,
  onRetry,
}: {
  message: Message;
  onRetry?: (question: string) => void;
}) {
  switch (message.role) {
    case "user":
      return (
        <li className="max-w-[85%] self-end whitespace-pre-wrap rounded-lg border border-[var(--ra-border-primary)] px-3 py-2 text-sm text-[var(--ra-foreground)]">
          {message.text}
        </li>
      );
    case "assistant":
      return (
        <li
          data-message-id={message.id}
          className="flex max-w-[95%] flex-col gap-2 self-start rounded-lg bg-[var(--ra-background-secondary)] px-3 py-2 text-sm text-[var(--ra-foreground)]"
        >
          <p className="whitespace-pre-wrap">{message.text}</p>
          {message.sources.length > 0 && (
            <div className="border-t border-[var(--ra-border-primary)] pt-2">
              <p className="text-xs font-medium text-[var(--ra-input-text)]">Sources</p>
              <ul className="mt-1 flex flex-col gap-1">
                {message.sources.map((s) => {
                  const { title, section } = sourceLabel(s);
                  return (
                    <li
                      key={`${s.file}#${s.section}`}
                      title={`docs/exploitation/${s.file} — ${s.section}`}
                      className="text-xs text-[var(--ra-input-text)]"
                    >
                      <span className="text-[var(--ra-foreground)]">{title}</span>
                      {section && <> › {section}</>}
                      <span className="block font-mono text-[11px]">{s.file}</span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </li>
      );
    case "error":
      return (
        <li
          role="alert"
          className="flex max-w-[95%] flex-col items-start gap-1 self-start rounded-lg bg-[var(--ra-status-alert-bg)] px-3 py-2 text-sm text-[var(--ra-status-alert-text)]"
        >
          <span>{message.text}</span>
          {onRetry && (
            <button
              type="button"
              onClick={() => onRetry(message.question)}
              className="text-xs font-medium underline underline-offset-2"
            >
              Réessayer
            </button>
          )}
        </li>
      );
    case "notice":
      return (
        <li className="self-center text-xs text-[var(--ra-input-text)]">{message.text}</li>
      );
  }
}

function HeaderButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="rounded-[4px] p-1.5 text-[var(--ra-input-text)] hover:bg-[var(--ra-background-secondary)] hover:text-[var(--ra-foreground)]"
    >
      {children}
    </button>
  );
}

function Icon({ children }: { children: React.ReactNode }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

function ChatIcon() {
  return (
    <Icon>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </Icon>
  );
}

function ExpandIcon() {
  return (
    <Icon>
      <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
    </Icon>
  );
}

function CollapseIcon() {
  return (
    <Icon>
      <path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7" />
    </Icon>
  );
}

function CloseIcon() {
  return (
    <Icon>
      <path d="M18 6 6 18M6 6l12 12" />
    </Icon>
  );
}

function TrashIcon() {
  return (
    <Icon>
      <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" />
    </Icon>
  );
}
