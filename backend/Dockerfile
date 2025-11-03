# backend/Dockerfile
FROM python:3.11-slim
WORKDIR /app

# (Optional) WeasyPrint deps for Linux container; remove if not needed yet
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi8 \
#     fonts-liberation && rm -rf /var/lib/apt/lists/*


# install python deps
COPY app/requirements.txt /app/app/requirements.txt
RUN pip install --no-cache-dir -r /app/app/requirements.txt

# copy the whole backend/app package into /app/app
COPY app /app/app

# expose the package on PYTHONPATH
ENV PYTHONPATH=/app

# run uvicorn using the package path
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

