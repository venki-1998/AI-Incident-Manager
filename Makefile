.PHONY: build up down logs

build:
        docker compose build --pull

up:
        docker compose up -d

down:
        docker compose down

logs:
        docker compose logs -f