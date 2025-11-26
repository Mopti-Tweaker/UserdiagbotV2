import discord
from discord.ext import commands
import os
import re
import time
from dotenv import load_dotenv
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from bs4 import BeautifulSoup
import urllib.request # Nécessaire pour le self-ping

# --- 1. FAUX SERVEUR WEB (POUR RENDER) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is active and listening!")

def start_fake_server():
    # Récupère le port donné par Render ou utilise 8080 par défaut
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"🌍 Serveur Web actif sur le port {port}")
    server.serve_forever()

# --- NOUVEAU : SYSTÈME ANTI-SOMMEIL ---
def ping_self():
    while True:
        # On attend 5 minutes (300 secondes)
        time.sleep(290) 
        try:
            port = int(os.environ.get("PORT", 8080))
            # Le bot s'envoie une requête à lui-même
            url = f"http://127.0.0.1:{port}"
            with urllib.request.urlopen(url) as response:
                print(f"⏰ Auto-Ping envoyé ({response.status}) : Bot maintenu éveillé.")
        except Exception as e:
            print(f"⚠️ Erreur Auto-Ping : {e}")

# Lancement des tâches de fond (Serveur + Ping)
Thread(target=start_fake_server, daemon=True).start()
Thread(target=ping_self, daemon=True).start()

# --- 2. CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
try:
    ID_SALON = int(os.getenv("DISCORD_CHANNEL_ID"))
except:
    ID_SALON = 0

# LIEN DU TICKET
TICKET_LINK = "https://discord.com/channels/1316619303994396732/1355540389343531139/1355547355163660421"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- 3. MOTEUR D'ANALYSE HTML ---
async def analyze_html(attachment):
    try:
        file_bytes = await attachment.read()
        html_content = file_bytes.decode('utf-8', errors='ignore')
        soup = BeautifulSoup(html_content, "html.parser")
        
        # 1. Récupérer le texte complet pour la détection globale (Battery, Laptop...)
        full_text = soup.get_text(" ", strip=True).upper()
        
        # 2. Récupérer spécifiquement le résumé matériel (plus propre pour le CPU/GPU)
        meta_desc = soup.find("meta", property="og:description")
        if meta_desc:
            # On concatène le résumé précis avec le texte global
            # Le résumé sera utilisé pour l'analyse prioritaire
            summary = meta_desc["content"].upper()
            combined_text = f"SUMMARY_START {summary} SUMMARY_END {full_text}"
            return {"raw_text": combined_text}
            
        return {"raw_text": full_text}
    except Exception as e:
        return {"error": f"Lecture HTML impossible : {str(e)}"}

# --- 4. LOGIQUE ET FORMATAGE ---
def determine_offer(text):
    
    # --- A. Détection PC Portable ---
    mobile_cpu = r'\d{4,5}(?:H|HK|HX|HS|HQ|U|P|Y)\b'
    # La présence de "INTEGRATED GRAPHICS" contribue à la détection de PC portable.
    is_laptop = bool(re.search(mobile_cpu, text)) or "BATTERY" in text or "LAPTOP" in text or "INTEGRATED GRAPHICS" in text
    
    if is_laptop:
        return {
            "price": "Non pris en charge",
            "caps": {"cpu": False, "ram": False, "gpu": False},
            "is_laptop": True,
            "pack_name": "PC Portable"
        }

    # --- B. Matériel ---
    # Recherche spécifique des marques CPU pour éviter la confusion avec les GPU Intel
    is_intel = "INTEL CORE" in text or "PENTIUM" in text or "CELERON" in text
    is_amd = "RYZEN" in text or "AMD" in text
    is_intel_k = bool(re.search(r'\d{3,5}K[SF]?(?!\w)', text))
    
    # Détection X3D (AM4 et AM5)
    is_x3d = "X3D" in text and any(x in text for x in ["5700", "5800", "7800", "7900", "7950", "9800", "9950"])
    
    chipset_match = re.search(r'\b([BZXH])\d{3}[A-Z]?\b', text)
    chipset_prefix = chipset_match.group(1) if chipset_match else "UNKNOWN"
    is_intel_b_unlock = any(c in text for c in ["B560", "B660", "B760"])
    
    is_nvidia = any(g in text for g in ["NVIDIA", "GEFORCE", "RTX", "GTX"])
    is_amd_gpu = ("RADEON" in text or "RX 6" in text or "RX 7" in text) and "VEGA" not in text
    
    # On maintient la détection des GPU Intel, mais elle sera utilisée différemment
    is_intel_gpu = "INTEL ARC" in text or "IRIS" in text or "INTEL UHD" in text

    # DDR5 Check
    is_ddr5 = False
    # Vérifie si la fréquence de RAM dépasse 4400 MHz (indicateur DDR5, car DDR4 est max 4400)
    freq_match = re.search(r'(\d{4})\s*(?:MHZ|MT/S)', text)
    if freq_match and int(freq_match.group(1)) > 4400: is_ddr5 = True
    # Vérifie si le CPU est un AM5 (qui est forcément DDR5)
    if "RYZEN" in text and any(c in text for c in ["7600", "7700", "7900", "9000"]): is_ddr5 = True

    # --- C. Eligibilité (Capacités) ---
    can_oc_cpu = False
    can_oc_ram = False
    can_oc_gpu = False

    # Logique CPU OC
    if is_intel:
        # OC CPU possible uniquement avec K et Chipset Z
        if is_intel_k and chipset_prefix == "Z": can_oc_cpu = True
    elif is_amd:
        # OC CPU possible avec chipset B ou X sur AMD (tous les processeurs modernes AMD sont "débloqués")
        if chipset_prefix in ["B", "X"]: can_oc_cpu = True

    # Logique RAM OC
    if is_intel:
        # OC RAM possible avec Chipset Z ou les B non-Z unlockables
        if chipset_prefix == "Z" or is_intel_b_unlock: can_oc_ram = True
    elif is_amd:
        # OC RAM possible avec chipset B ou X sur AMD
        if chipset_prefix in ["B", "X"]: can_oc_ram = True

    # Logique GPU OC (Corrigée pour ne pas bloquer si un iGPU Intel est présent avec une carte dédiée)
    # L'OC GPU est possible si une carte dédiée NVIDIA ou AMD est présente.
    if is_nvidia or is_amd_gpu:
        can_oc_gpu = True
    # Condition spéciale pour INTEL ARC: si c'est la seule carte détectée, l'OC est souvent possible aussi
    elif "INTEL ARC" in text and not (is_nvidia or is_amd_gpu):
        can_oc_gpu = True


    caps = {"cpu": can_oc_cpu, "ram": can_oc_ram, "gpu": can_oc_gpu}

    # --- D. Sélection du Prix (Priorisation X3D) ---
    
    # PRIORITÉ 1: Spécial X3D
    if is_x3d:
        # L'OC est possible sur tous les X3D (CPU via Curve Optimizer, RAM, GPU)
        return {"price": "95€", "caps": {"cpu": True, "ram": True, "gpu": True}, "is_laptop": False, "pack_name": "Spécial X3D"}

    # PRIORITÉ 2: Offres DDR5
    if is_ddr5:
        if can_oc_cpu and can_oc_ram and can_oc_gpu:
            return {"price": "195€", "caps": caps, "is_laptop": False, "pack_name": "Complet DDR5"}
        elif can_oc_ram and can_oc_gpu:
            return {"price": "135€", "caps": caps, "is_laptop": False, "pack_name": "RAM DDR5 + GPU"}
        elif can_oc_cpu and can_oc_ram:
             return {"price": "155€", "caps": caps, "is_laptop": False, "pack_name": "CPU + RAM DDR5"}
        elif can_oc_cpu:
            return {"price": "40€", "caps": caps, "is_laptop": False, "pack_name": "CPU Seul (DDR5)"}
    
    # PRIORITÉ 3: Offres DDR4
    else: # DDR4
        if can_oc_cpu and can_oc_ram and can_oc_gpu:
            return {"price": "85€", "caps": caps, "is_laptop": False, "pack_name": "Complet DDR4"}
        elif can_oc_ram and can_oc_gpu:
            return {"price": "55€", "caps": caps, "is_laptop": False, "pack_name": "RAM + GPU (DDR4)"}
        elif can_oc_cpu and can_oc_ram:
             return {"price": "65€", "caps": caps, "is_laptop": False, "pack_name": "CPU + RAM (DDR4)"}
        elif can_oc_cpu:
            return {"price": "20€", "caps": caps, "is_laptop": False, "pack_name": "CPU Seul"}

    # Cas de secours (si RAM et GPU sont les seuls possibles, et que la logique est passée à travers les packs DDR)
    if can_oc_ram and can_oc_gpu:
        if is_ddr5:
            # S'assurer qu'un setup RAM/GPU DDR5 non CPU OC a une offre
            return {"price": "135€", "caps": caps, "is_laptop": False, "pack_name": "RAM DDR5 + GPU"}
        else:
            # S'assurer qu'un setup RAM/GPU DDR4 non CPU OC a une offre
            return {"price": "55€", "caps": caps, "is_laptop": False, "pack_name": "RAM + GPU (DDR4)"}

    # PRIORITY 4: Optimisation Windows (si aucune OC n'est possible, ou seulement RAM ou seulement GPU)
    return {"price": "Sur devis", "caps": caps, "is_laptop": False, "pack_name": "Optimisation Windows"}


# --- 5. EVENTS ---
@bot.event
async def on_ready():
    print(f"✅ Bot HTML connecté : {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    # Si ID_SALON est 0, écoute tous les salons. Sinon, filtre.
    if ID_SALON != 0 and message.channel.id != ID_SALON: return

    if message.attachments:
        for attachment in message.attachments:
            if attachment.filename.lower().endswith(('.html', '.htm')):
                
                msg = await message.channel.send(f"🌐 **Fichier HTML reçu !** Analyse en cours...")
                data = await analyze_html(attachment)
                
                if "error" in data:
                    await msg.edit(content=f"❌ {data['error']}")
                    return

                res = determine_offer(data["raw_text"])
                
                if res["is_laptop"]:
                        response = f"⛔ **PC Portable détecté**\n"
                        response += "Nous ne réalisons pas de prestations sur les PC portables."
                else:
                    c_cpu = "✅" if res["caps"]["cpu"] else "❌"
                    c_ram = "✅" if res["caps"]["ram"] else "❌"
                    c_gpu = "✅" if res["caps"]["gpu"] else "❌"

                    response = f"**Ton PC permet de faire :**\n"
                    response += f"- Un Overclock CPU {c_cpu}\n"
                    response += f"- Un Overclock RAM {c_ram}\n"
                    response += f"- Un Overclock GPU {c_gpu}\n\n"
                    response += f"Mopti peut faire les Overclocks à ta place pour **{res['price']}**\n"
                    response += f"Si tu es interessé crée ton ticket ici 👉 {TICKET_LINK}"

                await msg.edit(content=response)
                return # Analyse un seul fichier HTML par message

    if "userdiag.com" in message.content:
        await message.channel.send(f"ℹ️ {message.author.mention}, merci d'envoyer le rapport en fichier HTML.\n**(CTRL + S sur la page > Enregistrer > Glisser le fichier ici)**", delete_after=20)

    # Nécessaire si vous avez d'autres commandes !
    await bot.process_commands(message)

# --- 6. DÉMARRAGE ---
if TOKEN:
    print("🚀 Lancement du bot...")
    bot.run(TOKEN)
else:
    print("❌ ERREUR: DISCORD_TOKEN non trouvé dans le .env")
