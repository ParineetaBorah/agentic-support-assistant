.PHONY: up down logs reset clean ps

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

reset:
	docker compose down -v
	docker compose up -d

clean:
	docker compose down -v
	docker system prune -f

ps:
	docker compose ps
