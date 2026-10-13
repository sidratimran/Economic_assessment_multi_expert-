FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=7860

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# live market cache is written at runtime
RUN mkdir -p data/live && chmod -R a+rw data

EXPOSE 7860
CMD ["python", "run.py"]
