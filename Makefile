.PHONY: setup backend frontend migrate recalculate admin check db-up db-stop

PYTHON := backend/.venv/bin/python

setup:
	bash scripts/setup.sh

backend:
	$(PYTHON) backend/manage.py runserver 127.0.0.1:8000

frontend:
	npm --prefix frontend run dev

migrate:
	$(PYTHON) backend/manage.py migrate

recalculate:
	$(PYTHON) backend/manage.py recalculate_reports

admin:
	$(PYTHON) backend/manage.py createsuperuser

check:
	$(PYTHON) backend/manage.py check
	$(PYTHON) backend/manage.py makemigrations --check --dry-run
	cd backend && .venv/bin/python manage.py test
	npm --prefix frontend run lint
	npm --prefix frontend test
	npm --prefix frontend run build

db-up:
	docker compose up -d --wait db

db-stop:
	docker compose stop db
