.PHONY: help install test run clean docker-build docker-run lint format

help:
	@echo "Available commands:"
	@echo "  make install      - Install dependencies"
	@echo "  make test         - Run tests"
	@echo "  make run          - Run bot locally"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-run   - Run via Docker Compose"
	@echo "  make clean        - Clean temporary files"
	@echo "  make lint         - Run linters"
	@echo "  make format       - Format code with black"

install:
	pip install --upgrade pip
	pip install -r requirements.txt

test:
	pytest -v

run:
	python bot.py

docker-build:
	docker-compose build

docker-run:
	docker-compose up -d

docker-logs:
	docker-compose logs -f bot

docker-stop:
	docker-compose down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	find . -type d -name '.pytest_cache' -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '.mypy_cache' -exec rm -rf {} + 2>/dev/null || true
	rm -f *.log

lint:
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

format:
	black --line-length 100 *.py services/*.py tests/*.py scripts/*.py