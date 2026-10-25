FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/agentguard
COPY requirements-deploy.txt ./
RUN python -m pip install --no-cache-dir -r requirements-deploy.txt
COPY pyproject.toml README.md ./
COPY app/*.py ./app/
COPY guard/*.py ./guard/
COPY index.html checkout.html confirmation.html app.js checkout.js styles.css ./
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
