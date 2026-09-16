FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime AS runtime

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/src \
    HF_HOME=/models/huggingface

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY studio ./studio
COPY src ./src
COPY static ./static

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS test
COPY dataset/requirements.txt ./dataset-requirements.txt
RUN pip install --no-cache-dir pytest -r dataset-requirements.txt
ENV PYTHONPATH=/app:/app/src
COPY models/registry.json models/character_profiles.json ./models/
RUN mkdir -p ./models/loras && touch ./models/loras/ixy_style.safetensors
COPY dataset ./dataset
COPY colab ./colab
COPY kaggle ./kaggle
COPY tests ./tests
CMD ["pytest", "-q"]

FROM runtime AS development
COPY pyproject.toml README.md ./
COPY dataset/requirements.txt ./dataset-requirements.txt
COPY src ./src
RUN pip install --no-cache-dir -e ".[dev]" -r dataset-requirements.txt
CMD ["python", "-m", "pytest"]

FROM runtime AS production
