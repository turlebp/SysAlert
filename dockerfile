FROM python:3.12-slim

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Set working directory
WORKDIR /home/appuser/app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install dependencies as root
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set ownership
RUN chown -R appuser:appuser /home/appuser/app

# Switch to non-root user
USER appuser

# Create data directory
RUN mkdir -p /home/appuser/app/data

# Expose health check port (optional)
EXPOSE 8080

# Set environment
ENV PYTHONUNBUFFERED=1
ENV PATH="/home/appuser/.local/bin:${PATH}"

# Run the bot
CMD ["python", "bot.py"]