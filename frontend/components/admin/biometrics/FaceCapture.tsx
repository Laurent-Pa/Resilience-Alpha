"use client";

import { useEffect, useRef, useState } from "react";

interface FaceCaptureProps {
  /** Reçoit l'image capturée (data URL JPEG). La caméra est coupée juste après. */
  onCapture: (image: string) => void;
  disabled?: boolean;
}

// Même format que l'étape caméra de Keycloak : la référence et les captures de connexion
// se ressemblent, ce qui stabilise la similarité.
const WIDTH = 480;
const HEIGHT = 360;

/**
 * Aperçu webcam + bouton de capture. La caméra n'est allumée que pendant que ce composant
 * est monté et en attente de capture ; l'image n'est ni stockée ni journalisée ici.
 */
export function FaceCapture({ onCapture, disabled = false }: FaceCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!navigator.mediaDevices?.getUserMedia) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setError("Caméra indisponible : ouvrir le back-office en HTTPS (ou sur localhost).");
      return;
    }
    navigator.mediaDevices
      .getUserMedia({ video: { width: 640, height: 480, facingMode: "user" }, audio: false })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
        setReady(true);
      })
      .catch(() => {
        if (!cancelled) setError("Accès à la caméra refusé ou aucune caméra branchée.");
      });
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, []);

  function capture() {
    const video = videoRef.current;
    if (!video) return;
    const canvas = document.createElement("canvas");
    canvas.width = WIDTH;
    canvas.height = HEIGHT;
    canvas.getContext("2d")?.drawImage(video, 0, 0, WIDTH, HEIGHT);
    const image = canvas.toDataURL("image/jpeg", 0.8);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setReady(false);
    onCapture(image);
  }

  return (
    <div className="flex flex-col gap-3">
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className="aspect-[4/3] w-full max-w-[400px] -scale-x-100 rounded-[4px] bg-black object-cover"
      />
      {error && (
        <p role="alert" className="text-sm text-[var(--ra-status-alert-text)]">
          {error}
        </p>
      )}
      <button
        type="button"
        onClick={capture}
        disabled={!ready || disabled}
        className="w-fit rounded-lg bg-[var(--ra-brand)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--ra-brand-hover)] disabled:cursor-not-allowed disabled:opacity-50"
      >
        Capturer et enregistrer
      </button>
    </div>
  );
}
