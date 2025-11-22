import discord
from discord.ext import commands
import os
import re
from dotenv import load_dotenv
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from bs4 import BeautifulSoup

# --- 1. FAUX SERVEUR WEB (POUR RENDER) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot HTML is running!")

def start_fake_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"🌍 Serveur actif sur le port {port}")
    server.serve_forever()

Thread(target=start_fake_server, daemon=True).start()

# --- 2. CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
try:
    ID_SALON = int(os.getenv("DISCORD_CHANNEL_ID"))
except:
    ID_SALON = 0

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- 3. MOTEUR D'ANALYSE HTML ---
async def analyze_html(attachment):
    try:
        # Lecture du fichier en mémoire
        file_bytes = await attachment.read()
        
        # Conversion des octets en texte (UTF-8)
        # errors='ignore' permet d'éviter le crash si un caractère est bizarre
        html_content = file_bytes.decode('utf-8', errors='ignore')
        
        # Nettoyage avec BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Extraction de tout le texte visible, en majuscules
        text = soup.get_text(" ", strip=True).upper()
        
        return {"raw_text": text}
    except Exception as e:
        return {"error": f"Lecture HTML impossible : {str(e)}"}

# --- 4. LOGIQUE COMMERCIALE (OFFRES) ---
def determine_offer(text):
    
    # --- A. Détection PC Portable ---
    mobile_cpu = r'\d{4,5}(?:H|HK|HX|HS|HQ|U|P|Y)\b'
    is_laptop = bool(re.search(mobile_cpu, text)) or "BATTERY" in text or "LAPTOP" in text or "INTEGRATED GRAPHICS" in text
    
    if is_laptop:
        return {
            "name": "⛔ PC Portable détecté",
            "price": "Non pris en charge",
            "desc": "Pas d'overclocking sur PC portable.",
            "is_laptop": True
        }

    # --- B. Matériel ---
    is_intel = "INTEL" in text
    is_amd = "RYZEN" in text or "AMD" in text
    is_intel_k = bool(re.search(r'\d{3,5}K[SF]?(?!\w)', text))
    is_x3d = "X3D" in text and any(x in text for x in ["7800", "7900", "7950", "9800"])
    
    chipset_match = re.search(r'\b([BZXH])\d{3}[A-Z]?\b', text)
    chipset_prefix = chipset_match.group(1) if chipset_match else "UNKNOWN"
    is_intel_b_unlock = any(c in text for c in ["B560", "B660", "B760"])
    
    is_nvidia = any(g in text for g in ["NVIDIA", "GEFORCE", "RTX", "GTX"])
    is_amd_gpu = ("RADEON" in text or "RX 6" in text or "RX 7" in text) and "VEGA" not in text
    is_intel_gpu = "INTEL ARC" in text or "IRIS" in text

    # DDR5 Check
    is_ddr5 = False
    freq_match = re.search(r'(\d{4})\s*(?:MHZ|MT/S)', text)
    if freq_match and int(freq_match.group(1)) > 4400: is_ddr5 = True
    if "RYZEN" in text and any(c in text for c in ["7600", "7700", "7900", "9000"]): is_ddr5 = True

    # --- C. Eligibilité ---
    can_oc_cpu = (is_intel and is_intel_k and chipset_prefix == "Z") or \
                 (is_amd and chipset_prefix in ["B", "X"])

    can_oc_ram = (is_intel and (chipset_prefix == "Z" or is_intel_b_unlock)) or \
                 (is_amd and chipset_prefix in ["B", "X"])

    can_oc_gpu = (is_nvidia or is_amd_gpu) and not is_intel_gpu

    # --- D. Sélection Offre ---
    if is_x3d: return {"name": "🔥 Spécial X3D AM5", "price": "95€", "desc": "Optimisation X3D."}

    if is_ddr5:
        if can_oc_cpu and can_oc_ram and can_oc_gpu: return {"name": "🚀 Pack Complet DDR5", "price": "195€", "desc": "Full OC DDR5"}
        if can_oc_ram and can_oc_gpu: return {"name": "⚡ RAM DDR5 + GPU", "price": "135€", "desc": "Focus RAM/GPU"}
        if can_oc_cpu and can_oc_ram: return {"name": "🧠 CPU + RAM DDR5", "price": "155€", "desc": "Focus CPU/RAM"}
        if can_oc_cpu: return {"name": "⚙️ CPU Seul (DDR5)", "price": "40€", "desc": "CPU Only"}
    else:
        if can_oc_cpu and can_oc_ram and can_oc_gpu: return {"name": "💎 Pack Complet DDR4", "price": "85€", "desc": "Full OC DDR4"}
        if can_oc_ram and can_oc_gpu: return {"name": "⚡ RAM + GPU (DDR4)", "price": "55€", "desc": "Focus RAM/GPU"}
        if can_oc_cpu and can_oc_ram: return {"name": "🧠 CPU + RAM (DDR4)", "price": "65€", "desc": "Focus CPU/RAM"}
        if can_oc_cpu: return {"name": "⚙️ CPU Seul", "price": "20€", "desc": "CPU Only"}

    return {"name": "🛠️ Optimisation Windows", "price": "Sur devis", "desc": "Matériel non éligible OC complet."}

# --- 5. EVENTS ---
@bot.event
async def on_ready():
    print(f"✅ Bot HTML connecté : {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    if ID_SALON != 0 and message.channel.id != ID_SALON: return

    # Détection fichier HTML
    if message.attachments:
        for attachment in message.attachments:
            if attachment.filename.lower().endswith(('.html', '.htm')):
                
                msg = await message.channel.send(f"🌐 **Fichier HTML reçu !** Analyse en cours...")
                data = await analyze_html(attachment)
                
                if "error" in data:
                    await msg.edit(content=f"❌ {data['error']}")
                    return

                offer = determine_offer(data["raw_text"])
                
                # Affichage
                emoji = "⛔" if offer.get("is_laptop") else "✅"
                embed = f"**📊 Rapport {message.author.mention}**\n━━━━━━━━━━━━━━━━\n"
                embed += f"{emoji} **{offer['name']}**\n💰 **{offer['price']}**\n📝 *{offer['desc']}*\n━━━━━━━━━━━━━━━━"
                if not offer.get("is_laptop"):
                    embed += "\n**💎 Inclus :** Gains FPS • SAV à vie • Backup Cloud"

                await msg.edit(content=embed)
                return

    # Message d'aide
    if "userdiag.com" in message.content:
        await message.channel.send(f"ℹ️ {message.author.mention}, merci d'envoyer le rapport en fichier HTML.\n**(CTRL + S sur la page > Enregistrer > Glisser le fichier ici)**", delete_after=20)

    await bot.process_commands(message)

if TOKEN:
    bot.run(TOKEN)