FROM python:3.12-slim

# System deps — changes almost never
RUN apt-get update && apt-get install -y --no-install-recommends iputils-ping && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps — changes only when requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code — changes less often than static assets
COPY pinginator/ pinginator/

# Static assets — changes most frequently (UI iterations)
COPY static/ static/

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')" || exit 1
CMD ["python", "-m", "pinginator"]
