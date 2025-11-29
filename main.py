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

# --- NOUVEAU : Dictionnaire de Prix Black Friday ---
# Contient: (Nouveau Prix, Ancien Prix, Remise, Mention Paiement, Date fin promo)
PACK_PRICES = {
    "Spécial X3D": ("75€", "95€", "-20€", "", "30 Novembre"),
    
    # DDR5
    "Complet DDR5": ("155€", "195€", "-40€", "(Paiement en plusieurs fois possible)", "30 Novembre"),
    "RAM DDR5 + GPU": ("115€", "135€", "-20€", "(Paiement en plusieurs fois possible)", "30 Novembre"),
    "CPU + RAM DDR5": ("135€", "155€", "-20€", "(Paiement en plusieurs fois possible)", "30 Novembre"),
    "CPU Seul (DDR5)": ("30€", "40€", "-10€", "", "30 Novembre"),
    
    # DDR4
    "Complet DDR4": ("65€", "85€", "-20€", "", "30 Novembre"),
    "RAM + GPU (DDR4)": ("45€", "55€", "-10€", "", "30 Novembre"),
    "CPU + RAM (DDR4)": ("55€", "65€", "-10€", "", "30 Novembre"),
    "CPU Seul": ("20€", "20€", "0€", "", "30 Novembre"), # Le prix reste 20€

    # Autres
    "PC Portable": ("Non pris en charge", "", "", "", ""),
    "Optimisation Windows": ("Sur devis", "", "", "", ""),
}


# --- 3. MOTEUR D'ANALYSE HTML ---
async def analyze_html(attachment):
    try:
        file_bytes = await attachment.read()
        html_content = file_bytes.decode('utf-8', errors='ignore')
        soup = BeautifulSoup(html_content, "html.parser")
        
        full_text = soup.get_text(" ", strip=True).upper()
        
        meta_desc = soup.find("meta", property="og:description")
        if meta_desc:
            summary = meta_desc["content"].upper()
            combined_text = f"SUMMARY_START {summary} SUMMARY_END {full_text}"
            return {"raw_text": combined_text}
            
        return {"raw_text": full_text}
    except Exception as e:
        return {"error": f"Lecture HTML impossible : {str(e)}"}

# --- 4. LOGIQUE ET FORMATAGE ---
def determine_offer(text):
    
    # --- A. Détection PC Portable ---
    mobile_cpu = r'\b\d{4,5}(?:H|HK|HX|HS|HQ|U|P|Y)\b'
    # Correction : On retire "INTEGRATED GRAPHICS" pour éviter les faux positifs sur les desktops.
    is_laptop = bool(re.search(mobile_cpu, text)) or "BATTERY" in text or "LAPTOP" in text or "NOTEBOOK" in text
    
    if is_laptop:
        return {
            "pack_name": "PC Portable",
            "caps": {"cpu": False, "ram": False, "gpu": False},
            "is_laptop": True
        }

    # --- B. Matériel ---
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
    
    # DDR5 Check
    is_ddr5 = False
    freq_match = re.search(r'(\d{4})\s*(?:MHZ|MT/S)', text)
    if freq_match and int(freq_match.group(1)) > 4400: is_ddr5 = True
    if "RYZEN" in text and any(c in text for c in ["7600", "7700", "7900", "9000"]): is_ddr5 = True

    # --- C. Eligibilité (Capacités) ---
    can_oc_cpu = False
    can_oc_ram = False
    can_oc_gpu = False

    if is_intel:
        if is_intel_k and chipset_prefix == "Z": can_oc_cpu = True
    elif is_amd:
        if chipset_prefix in ["B", "X"]: can_oc_cpu = True

    if is_intel:
        if chipset_prefix == "Z" or is_intel_b_unlock: can_oc_ram = True
    elif is_amd:
        if chipset_prefix in ["B", "X"]: can_oc_ram = True

    if is_nvidia or is_amd_gpu:
        can_oc_gpu = True
    elif "INTEL ARC" in text and not (is_nvidia or is_amd_gpu):
        can_oc_gpu = True

    caps = {"cpu": can_oc_cpu, "ram": can_oc_ram, "gpu": can_oc_gpu}

    # --- D. Sélection du Prix ---
    
    pack_name = "Optimisation Windows" # Default

    # PRIORITÉ 1: Spécial X3D
    if is_x3d:
        pack_name = "Spécial X3D"
        # X3D a toujours tous les OC cochés.
        caps = {"cpu": True, "ram": True, "gpu": True}
    
    # PRIORITÉ 2: Offres DDR5
    elif is_ddr5:
        if can_oc_cpu and can_oc_ram and can_oc_gpu:
            pack_name = "Complet DDR5"
        elif can_oc_ram and can_oc_gpu:
            pack_name = "RAM DDR5 + GPU"
        elif can_oc_cpu and can_oc_ram:
             pack_name = "CPU + RAM DDR5"
        elif can_oc_cpu:
            pack_name = "CPU Seul (DDR5)"
    
    # PRIORITÉ 3: Offres DDR4
    else: # DDR4
        if can_oc_cpu and can_oc_ram and can_oc_gpu:
            pack_name = "Complet DDR4"
        elif can_oc_ram and can_oc_gpu:
            pack_name = "RAM + GPU (DDR4)"
        elif can_oc_cpu and can_oc_ram:
             pack_name = "CPU + RAM (DDR4)"
        elif can_oc_cpu:
            pack_name = "CPU Seul"
        elif can_oc_ram and can_oc_gpu: # Cas de secours DDR4 (doit être couvert par les packs ci-dessus, mais pour sécurité)
             pack_name = "RAM + GPU (DDR4)"
    
    return {"pack_name": pack_name, "caps": caps, "is_laptop": False}


# --- 5. EVENTS ---
@bot.event
async def on_ready():
    print(f"✅ Bot HTML connecté : {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user: return
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
                
                # Récupération des données du pack à partir du dictionnaire
                pack_data = PACK_PRICES.get(res['pack_name'], ("Sur devis", "", "", "", ""))
                new_price, old_price, discount, mention, end_date = pack_data

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
                    
                    # FORMATAGE SPÉCIAL BLACK FRIDAY
                    if old_price and old_price != new_price:
                         # Utilisation de la syntaxe Discord pour le texte barré (~~)
                        price_display = f"~~{old_price}~~ **{new_price}** ({discount}) {mention}"
                        response += f"⚠️ **PROMO BLACK FRIDAY JUSQU'AU {end_date.upper()}** ⚠️\n"
                        response += f"C'est la prestation **{res['pack_name']}** au prix promo de : {price_display}\n\n"
                    else:
                        # Si ce n'est pas une promo (comme "Optimisation Windows" ou "CPU Seul")
                        response += f"C'est la prestation **{res['pack_name']}** à **{new_price}**\n\n"


                # Phrase de fin
                response += f"Si tu es interessé crée ton ticket ici 👉 {TICKET_LINK}"

                await msg.edit(content=response)
                return

    if "userdiag.com" in message.content:
        await message.channel.send(f"ℹ️ {message.author.mention}, merci d'envoyer le rapport en fichier HTML.\n**(CTRL + S sur la page > Enregistrer > Glisser le fichier ici)**", delete_after=20)

    await bot.process_commands(message)

# --- 6. DÉMARRAGE ---
if TOKEN:
    print("🚀 Lancement du bot...")
    bot.run(TOKEN)
else:
    print("❌ ERREUR: DISCORD_TOKEN non trouvé dans le .env")
