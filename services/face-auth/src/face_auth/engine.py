"""Moteur de reconnaissance faciale : YuNet (détection) + SFace (empreinte 128 floats).

Deux modèles ONNX de l'OpenCV Zoo (Apache 2.0, ~39 Mo au total), exécutés par OpenCV sur
CPU : pas de GPU, pas de dépendance lourde, quelques dizaines de ms par image.

Aucune image n'est conservée : seule l'empreinte normalisée sort de ce module.
"""

import threading
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

DETECTOR_MODEL = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_MODEL = "face_recognition_sface_2021dec.onnx"
MAX_SIDE = 1280  # au-delà, l'image est réduite avant détection


class FaceError(Exception):
    """`code` : invalid_image | no_face | multiple_faces."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Engine(Protocol):
    def embed(self, image: bytes, *, single: bool = False) -> np.ndarray: ...


class FaceEngine:
    def __init__(self, models_dir: str | Path, detect_threshold: float = 0.9) -> None:
        models = Path(models_dir)
        self._detector = cv2.FaceDetectorYN.create(
            str(models / DETECTOR_MODEL), "", (320, 320), detect_threshold
        )
        self._recognizer = cv2.FaceRecognizerSF.create(str(models / RECOGNIZER_MODEL), "")
        # setInputSize modifie le détecteur : un appel à la fois (threadpool de FastAPI).
        self._lock = threading.Lock()

    def embed(self, image: bytes, *, single: bool = False) -> np.ndarray:
        """Empreinte L2-normalisée du visage le plus grand.

        `single=True` (enrôlement) refuse une image à plusieurs visages : la référence
        doit être sans ambiguïté. À la connexion, le plus grand visage (le plus proche
        de la caméra) est retenu.
        """
        img = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise FaceError("invalid_image")
        h, w = img.shape[:2]
        if max(h, w) > MAX_SIDE:
            ratio = MAX_SIDE / max(h, w)
            img = cv2.resize(img, (int(w * ratio), int(h * ratio)))
            h, w = img.shape[:2]
        with self._lock:
            self._detector.setInputSize((w, h))
            _, faces = self._detector.detect(img)
            if faces is None or len(faces) == 0:
                raise FaceError("no_face")
            if single and len(faces) > 1:
                raise FaceError("multiple_faces")
            face = max(faces, key=lambda f: f[2] * f[3])
            aligned = self._recognizer.alignCrop(img, face)
            feature = self._recognizer.feature(aligned).flatten()
        return feature / np.linalg.norm(feature)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosinus entre deux empreintes normalisées (même mesure que FR_COSINE d'OpenCV)."""
    return float(np.dot(a, b))
