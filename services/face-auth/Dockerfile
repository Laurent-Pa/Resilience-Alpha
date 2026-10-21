# Contexte de build = racine du dépôt :
#   docker build -f services/face-auth/Dockerfile .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app
# Modèles OpenCV Zoo (Apache 2.0), figés par empreinte : téléchargés au build, jamais au
# démarrage (la démo tourne sans Internet).
ADD --checksum=sha256:8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4 \
    https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx \
    models/face_detection_yunet_2023mar.onnx
ADD --checksum=sha256:0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79 \
    https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx \
    models/face_recognition_sface_2021dec.onnx

COPY pyproject.toml uv.lock ./
COPY libs/ libs/
COPY services/face-auth/ services/face-auth/
RUN uv sync --frozen --no-dev --package face-auth

RUN useradd -r app && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=2s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=1)"]

# Binaires du venv appelés directement (pas de `uv run` : cf. payment-api/Dockerfile).
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "--factory", "face_auth.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
