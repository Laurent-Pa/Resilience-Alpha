import base64
import binascii
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

MAX_IMAGE_BYTES = 2 * 1024 * 1024


class ImageIn(BaseModel):
    # JPEG ou PNG en base64, avec ou sans préfixe `data:image/...;base64,` (canvas.toDataURL).
    image: str = Field(max_length=MAX_IMAGE_BYTES * 4 // 3 + 64)

    @field_validator("image")
    @classmethod
    def _decodable(cls, value: str) -> str:
        cls.decode(value)
        return value

    @staticmethod
    def decode(value: str) -> bytes:
        if value.startswith("data:"):
            value = value.partition(",")[2]
        try:
            data = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("image : base64 invalide") from exc
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise ValueError("image : vide ou trop volumineuse")
        return data

    def raw(self) -> bytes:
        return self.decode(self.image)


class VerifyIn(ImageIn):
    username: str = Field(min_length=1, max_length=255)


class VerifyOut(BaseModel):
    match: bool
    outcome: str
    attempts_left: int
    locked_until: datetime | None


class StatusOut(BaseModel):
    locked_until: datetime | None
    attempts_left: int


class UserOut(BaseModel):
    username: str
    enrolled: bool
    enrolled_at: datetime | None
    enrolled_by: str | None
    failures: int
    locked_until: datetime | None


class AttemptOut(BaseModel):
    username: str
    at: datetime
    outcome: str
    score: float | None
