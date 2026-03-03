.PHONY: up down build logs

up:
	docker compose up --build -d
	@echo ""
	@echo "Swagger UI: http://localhost:8000/docs"
	@echo ""

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f