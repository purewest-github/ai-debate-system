.PHONY: up down test logs build

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

test:
	cd backend && python test_mock.py

logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

ps:
	docker compose ps
