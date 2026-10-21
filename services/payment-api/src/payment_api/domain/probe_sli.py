"""SLI de la sonde : taux de réussite par minute. Pur, testable sans base.

payment-api ne voit que les virements réussis : un échec de sonde (jeton, clé, WAF, API
indisponible) n'écrit rien. Le dénominateur ne peut donc venir que de la cadence
nominale de la sonde, soit 60 / interval_s virements attendus par minute.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class MinutePoint:
    minute: datetime
    success_count: int
    expected_count: float
    success_pct: float


def minute_window(now: datetime, minutes: int) -> tuple[datetime, datetime]:
    """[début, fin) des `minutes` dernières minutes COMPLÈTES. La minute en cours est
    exclue : partielle, elle ferait plonger le taux à tort sur le dernier point."""
    end = now.replace(second=0, microsecond=0)
    return end - timedelta(minutes=minutes), end


def success_series(
    counts: dict[datetime, int], start: datetime, minutes: int, interval_s: float
) -> list[MinutePoint]:
    """Une entrée par minute à partir de `start`, minutes vides comprises : une sonde
    arrêtée n'écrit rien, et c'est justement ce 0 % qu'on veut voir.

    Plafonné à 100 % : la sonde ne tire pas pile sur les frontières de minute, une
    minute peut recevoir un virement de plus que la cadence (13 au lieu de 12) et la
    suivante un de moins. Le compte brut reste exposé tel quel."""
    expected = 60 / interval_s
    series = [start + timedelta(minutes=i) for i in range(minutes)]
    return [
        MinutePoint(
            minute=m,
            success_count=counts.get(m, 0),
            expected_count=round(expected, 2),
            success_pct=round(min(100.0, 100 * counts.get(m, 0) / expected), 1),
        )
        for m in series
    ]
