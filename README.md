# UltraGiga Monitor Bot

Production-ready Telegram bot for monitoring TCP services with alerting capabilities.

## Features

- 🔍 TCP port monitoring with configurable intervals
- ⚡ Asynchronous checks with concurrent execution limits
- 🔔 Intelligent alerting with failure thresholds
- 📊 Historical logging and audit trails
- 🔄 Retry logic with exponential backoff
- 🚦 Rate limiting to respect Telegram API limits
- 🐳 Docker support with non-root user
- 🧪 Comprehensive test suite
- 🔒 Admin-only subscription model (no auto-subscribe)

## Requirements

- Python 3.12+
- SQLite 3 (or PostgreSQL for production)
- Telegram Bot Token

## Quick Start

### 1. Clone and Setup
```bash
git clone <repository>
cd monitor-bot-v2
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
make install