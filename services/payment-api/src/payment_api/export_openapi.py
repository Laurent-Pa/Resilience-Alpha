"""Exporte le contrat OpenAPI.

python -m payment_api.export_openapi contracts/openapi-payment.json
"""

import json
import sys
from pathlib import Path

from payment_api.main import create_app
from payment_api.settings import Settings


def main() -> None:
    # Clé factice : l'export ne touche ni la base ni aucune donnée.
    spec = create_app(Settings(iban_hmac_key="export-only-not-a-secret")).openapi()
    out = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(out, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
