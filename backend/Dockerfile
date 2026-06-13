FROM python:3.11-slim

# Install LibreOffice + fonts (runs as root inside Docker - no sudo needed).
#
# The slim base ships with almost no fonts and zero Microsoft fonts. Our DOCX
# templates use Times New Roman / Arial / Calibri / etc.; without matching
# fonts LibreOffice substitutes a default with different metrics, so text
# renders larger and bullets/line-wraps drift vs. the Windows-authored docs.
# These metric-compatible fonts have identical metrics to the MS fonts, so the
# PDF layout matches what we see locally:
#   Times New Roman / Arial  -> fonts-liberation (Liberation Serif/Sans)
#   Calibri                  -> fonts-crosextra-carlito (Carlito)
#   Cambria                  -> fonts-crosextra-caladea (Caladea)
#   Mangal (Devanagari)      -> fonts-indic
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    fonts-liberation \
    fonts-crosextra-carlito \
    fonts-crosextra-caladea \
    fonts-indic \
    && fc-cache -f \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
