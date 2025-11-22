# Utilisation de Python 3.9 version légère
FROM python:3.9-slim

# 1. Installation des dépendances système indispensables
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    xvfb \
    libxi6 \
    default-jdk \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    fonts-liberation \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# 2. Installation de Google Chrome (Méthode Moderne sans apt-key)
RUN mkdir -p /etc/apt/keyrings \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | tee /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# 3. Configuration du dossier de travail
WORKDIR /app

# 4. Installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copie du code source
COPY . .

# 6. Commande de démarrage
CMD ["python", "main.py"]