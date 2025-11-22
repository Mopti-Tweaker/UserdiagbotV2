import discord
from discord.ext import commands
from seleniumbase import SB
from bs4 import BeautifulSoup
import asyncio
import time
import re
import os
from dotenv import load_dotenv
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- 1. LE FAUX SERVEUR WEB (POUR RENDER) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running and happy!")

def start_fake_server():
    # Render donne le port via la variable d'environnement PORT
    port = int(os.environ.get("PORT", 8080)) 
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"🌍 Faux serveur web lancé sur le port {port}")
    server.serve_forever()

# Lancement du serveur dans un thread séparé pour ne pas bloquer le bot
Thread(target=start_fake_server, daemon=True).start()

# --- 2. CONFIGURATION DU BOT ---
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
try:
    ID_SALON = int(os.getenv("DISCORD_CHANNEL_ID"))
except (TypeError, ValueError):
    # Fallback pour éviter le crash si l'env n'est pas encore mis
    print("⚠️ Attention: ID_SALON non trouvé ou invalide.")
    ID_SALON = 0 

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- 3. SCRAPING (Optimisé pour Serveur) ---
def scrape_userdiag(url):
    data = {}
    # xvfb=True est CRUCIAL sur Render (car pas d'écran réel)
    with SB(uc=True, headless=False, xvfb=True) as sb:
        try:
            print(f"🔍 Analyse : {url}")
            sb.driver.uc_open_with_reconnect(url, 5) # Reconnexion agressive pour Cloudflare
            
            page_loaded = False
            # On augmente un peu l'attente car les serveurs gratuits sont lents
            for i in range(20): 
                try:
                    title = sb.get_title()
                    print(f"   ⏳ Titre page : {title}") # Log pour voir ce qui bloque
                    if "UserDiag" in title and "Un instant" not in title and "Just a moment" not in title:
                        page_loaded = True
                        break
                except:
                    pass
                time.sleep(3)
            
            if not page_loaded: 
                # On essaie de capturer une erreur si possible
                return {"error": "❌ Délai dépassé : Cloudflare bloque l'accès au serveur Render."}

            time.sleep(2) # Stabilisation

            html = sb.get_page_source()
            soup = BeautifulSoup(html, "html.parser")
            data["raw_text"] = soup.get_text(" ", strip=True).upper()
            
        except Exception as e:
            print(f"Erreur scraping : {e}")
            return {"error": f"Erreur technique : {str(e)}"}
    return data

# --- 4. LOGIQUE D'ANALYSE ---
def determine_offer(text):
    # (Copie exactement ta logique précédente ici, je la remets pour être sûr)
    
    # 0. Laptop Check
    mobile_cpu_regex = r'\d{4,5}(?:H|HK|HX|HS|HQ|U|P|Y)\b'
    has_mobile_cpu = bool(re.search(mobile_cpu_regex, text))
    keywords_laptop = ["LAPTOP", "NOTEBOOK", "TOUCH", "BATTERY", "BATTERIE", "INTEGRATED GRAPHICS"]
    has_laptop = any(k in text for k in keywords_laptop) or "LAPTOP GPU" in text

    if has_mobile_cpu or has_laptop:
        return {"name": "⛔ PC Portable détecté", "price": "Non pris en charge", "desc": "Pas d'overclocking sur PC portable.", "is_laptop": True}

    # 1. Matériel
    is_intel = "INTEL" in text
    is_amd = "RYZEN" in text or "AMD" in text
    is_intel_k = bool(re.search(r'\d{3,5}K[SF]?(?!\w)', text))
    is_x3d = "X3D" in text and ("7800" in text or "7900" in text or "7950" in text or "9800" in text)
    
    chipset_match = re.search(r'\b([BZXH])\d{3}[A-Z]?\b', text)
    chipset_prefix = chipset_match.group(1) if chipset_match else "UNKNOWN"
    is_intel_b_unlock = any(x in text for x in ["B560", "B660", "B760"])
    
    is_nvidia = any(x in text for x in ["NVIDIA", "GEFORCE", "RTX", "GTX"])
    is_amd_gpu = ("RADEON" in text or "RX 6" in text or "RX 7" in text) and "VEGA" not in text
    is_intel_gpu = "INTEL ARC" in text or "IRIS" in text

    is_ddr5 = False
    freq_match = re.search(r'(\d{4})\s*(?:MHZ|MT/S)', text)
    if freq_match and int(freq_match.group(1)) > 4400: is_ddr5 = True
    if "RYZEN" in text and any(x in text for x in ["7600", "7700", "7900"]): is_ddr5 = True

    # 2. Éligibilité
    can_oc_cpu = (is_intel and is_intel_k and chipset_prefix == "Z") or \
                 (is_amd and "RYZEN" in text and chipset_prefix in ["B", "X"])

    can_oc_ram = (is_intel and (chipset_prefix == "Z" or is_intel_b_unlock)) or \
                 (is_amd and chipset_prefix in ["B", "X"])

    can_oc_gpu = (is_nvidia or is_amd_gpu) and not is_intel_gpu

    # 3. Offres
    if is_x3d:
        return {"name": "🔥 Spécial X3D AM5", "price": "95€", "desc": "Optimisation X3D."}

    if is_ddr5:
        if can_oc_cpu and can_oc_ram and can_oc_gpu: return {"name": "🚀 Pack Complet DDR5", "price": "195€", "desc": "CPU + RAM + GPU"}
        if can_oc_ram and can_oc_gpu: return {"name": "⚡ RAM DDR5 + GPU", "price": "135€", "desc": "Focus RAM/GPU"}
        if can_oc_cpu and can_oc_ram: return {"name": "🧠 CPU + RAM DDR5", "price": "155€", "desc": "Focus CPU/RAM"}
        if can_oc_cpu: return {"name": "⚙️ CPU Seul (DDR5)", "price": "40€", "desc": "CPU uniquement"}
    else:
        if can_oc_cpu and can_oc_ram and can_oc_gpu: return {"name": "💎 Pack Complet DDR4", "price": "85€", "desc": "CPU + RAM + GPU"}
        if can_oc_ram and can_oc_gpu: return {"name": "⚡ RAM + GPU (DDR4)", "price": "55€", "desc": "Focus RAM/GPU"}
        if can_oc_cpu and can_oc_ram: return {"name": "🧠 CPU + RAM (DDR4)", "price": "65€", "desc": "Focus CPU/RAM"}
        if can_oc_cpu: return {"name": "⚙️ CPU Seul", "price": "20€", "desc": "CPU uniquement"}

    return {"name": "🛠️ Optimisation Windows", "price": "Sur devis", "desc": "Matériel non éligible OC."}


# --- 5. EVENTS DISCORD ---
@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    
    # On vérifie le salon uniquement si l'ID est valide
    if ID_SALON != 0 and message.channel.id != ID_SALON: return

    if "userdiag.com" in message.content:
        words = message.content.split()
        url = next((w for w in words if "userdiag.com" in w), None)
        if not url: return

        msg = await message.channel.send(f"👀 **Analyse en cours...** (Cela peut prendre ~30s)")
        
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, scrape_userdiag, url)

        if "error" in data:
            await msg.edit(content=f"❌ {data['error']}")
            return

        offer = determine_offer(data["raw_text"])

        # Formatage réponse
        color = 0xFF0000 if offer.get("is_laptop") else 0x00FF00
        embed_desc = f"🔗 *{url}*\n\n🎯 **{offer['name']}**\n💰 **{offer['price']}**\n📝 *{offer['desc']}*"
        
        # Simple message texte propre
        final_msg = f"**📊 Rapport pour {message.author.mention}**\n{embed_desc}\n\n"
        if not offer.get("is_laptop"):
            final_msg += "**💎 Inclus :** Gain FPS, SAV à vie, Backup Cloud."
        
        await msg.edit(content=final_msg)

    await bot.process_commands(message)

if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ ERREUR: Token Discord manquant.")