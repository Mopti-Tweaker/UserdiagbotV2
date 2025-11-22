# On part d'une version de Python légère
FROM python:3.9-slim

# 1. On installe les outils système, l'écran virtuel (xvfb) et de quoi télécharger
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    xvfb \
    libxi6 \
    libgconf-2-4 \
    default-jdk \
    && rm -rf /var/lib/apt/lists/*

# 2. On installe Google Chrome (La version stable officielle)
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# 3. On prépare le dossier du bot
WORKDIR /app

# 4. On copie tes fichiers dans le serveur
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 5. La commande de démarrage (avec l'écran virtuel activé)
CMD ["python", "main.py"]