# Math Buddy workbench. The models are NOT trained here: run `python webapp/export_models.py`
# first (needs the FSDD folder and the MNIST cache), then build.
FROM python:3.14.5-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NUMBA_CACHE_DIR=/tmp/numba \
    MPLCONFIGDIR=/tmp/matplotlib

# libsndfile is needed by soundfile on some platforms (the wheel usually bundles it)
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py lesson.py ./
COPY templates ./templates
COPY static ./static
COPY models ./models

RUN useradd --create-home buddy
USER buddy

EXPOSE 8000
# One worker keeps one copy of the models in memory (~600 MB); threads serve parallel requests
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--timeout", "120", "app:app"]
