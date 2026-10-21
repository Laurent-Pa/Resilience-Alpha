# Cibles de développement. Sous Windows sans `make`, lancer les commandes à la main.
UV ?= uv

.PHONY: sync test test-common test-payment test-prober lint fmt export-openapi check-openapi seed dev-up dev-down

sync:
	$(UV) sync --all-packages

test:
	$(UV) run pytest

test-common:
	$(UV) run pytest libs/common

test-payment:
	$(UV) run pytest services/payment-api

test-prober:
	$(UV) run pytest services/prober

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fmt:
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

export-openapi:
	$(UV) run --package payment-api python -m payment_api.export_openapi contracts/openapi-payment.json

# Utilisé par la CI : échoue si l'export diffère du fichier versionné.
check-openapi: export-openapi
	git diff --exit-code -- contracts/


seed:
	$(UV) run --package payment-api python -m payment_api.bootstrap

dev-up:
	docker compose -f compose.dev.yaml up -d --build

dev-down:
	docker compose -f compose.dev.yaml down
