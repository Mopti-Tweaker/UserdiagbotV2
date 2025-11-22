import discord
from discord.ext import commands
from seleniumbase import SB
from bs4 import BeautifulSoup
import asyncio
import time
import re

# --- CONFIGURATION ---
TOKEN = "MTQ0MTU2MjkzNDQzMzE1MzAyNg.GdVdhq.mEM_7aBe739jbkP6pLl2wLx_A6Kurw6TZaj_is"
ID_SALON = 1435004866823983154
# ---------------------

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- 1. SCRAPING ---
def scrape_userdiag(url):
    data = {}
    with SB(uc=True, headless=False) as sb:
        try:
            print(f"🔍 Analyse : {url}")
            sb.driver.uc_open_with_reconnect(url, 4)
            
            page_loaded = False
            for i in range(15):
                title = sb.get_title()
                if "UserDiag" in title and "Un instant" not in title:
                    page_loaded = True
                    break
                time.sleep(3)
            
            if not page_loaded: return {"error": "❌ Blocage Cloudflare."}
            time.sleep(2)

            html = sb.get_page_source()
            soup = BeautifulSoup(html, "html.parser")
            data["raw_text"] = soup.get_text(" ", strip=True).upper()
            
        except Exception as e:
            return {"error": f"Erreur : {str(e)}"}
    return data

# --- 2. LOGIQUE D'ANALYSE ---
def determine_offer(text):
    
    # =================================================================
    # 🛑 ÉTAPE 0 : DÉTECTION PC PORTABLE (PRIORITÉ ABSOLUE)
    # =================================================================
    
    # 1. Analyse des Suffixes CPU Mobiles
    # Intel : H, HK, HX, U, P, Y (ex: 13700H)
    # AMD : H, HS, HX, U (ex: 5800HS)
    # Regex : Cherche un nombre (ex: 12700) suivi immédiatement d'une lettre mobile
    # On exclut K, KF, KS qui sont desktop.
    mobile_cpu_regex = r'\d{4,5}(?:H|HK|HX|HS|HQ|U|P|Y)\b'
    has_mobile_cpu = bool(re.search(mobile_cpu_regex, text))
    
    # 2. Mots-clés explicites dans le rapport
    keywords_laptop = ["LAPTOP", "NOTEBOOK", "TOUCH", "BATTERY", "BATTERIE", "INTEGRATED GRAPHICS"]
    has_laptop_keyword = any(k in text for k in keywords_laptop)
    
    # 3. GPU Mobiles (ex: RTX 4060 Laptop GPU)
    has_mobile_gpu = "LAPTOP GPU" in text or "MOBILE" in text

    # SI C'EST UN LAPTOP -> ON ARRÊTE TOUT ICI
    if has_mobile_cpu or has_laptop_keyword or has_mobile_gpu:
        return {
            "name": "⛔ PC Portable détecté",
            "price": "Non pris en charge",
            "desc": "Nous ne réalisons aucune prestation d'overclocking sur les PC portables (Refroidissement insuffisant).",
            "is_laptop": True # Marqueur pour changer la couleur ou l'affichage si besoin
        }

    # =================================================================
    # ÉTAPE 1 : DÉTECTION DU MATÉRIEL (PC FIXE)
    # =================================================================
    
    is_intel = "INTEL" in text
    is_amd = "RYZEN" in text or "AMD" in text
    
    # CPU 'K' Check (ex: 13600K, 14900KS)
    is_intel_k = bool(re.search(r'\d{3,5}K[SF]?(?!\w)', text))
    
    # X3D Check
    is_x3d = "X3D" in text and ("7800" in text or "7900" in text or "7950" in text or "9800" in text)

    # Chipset Carte Mère (B550, Z790...)
    chipset_match = re.search(r'\b([BZXH])\d{3}[A-Z]?\b', text)
    chipset_prefix = chipset_match.group(1) if chipset_match else "UNKNOWN"
    
    is_intel_b_unlock = "B560" in text or "B660" in text or "B760" in text
    
    # GPU
    is_nvidia = "NVIDIA" in text or "GEFORCE" in text or "RTX" in text or "GTX" in text
    is_amd_gpu = ("RADEON" in text or "RX 6" in text or "RX 7" in text) and not "VEGA" in text
    is_intel_gpu = "INTEL ARC" in text or "IRIS" in text

    # DDR4 vs DDR5
    is_ddr5 = False
    freq_match = re.search(r'(\d{4})\s*(?:MHZ|MT/S)', text)
    if freq_match:
        if int(freq_match.group(1)) > 4400: is_ddr5 = True
    if "RYZEN" in text and ("7600" in text or "7700" in text or "7900" in text): is_ddr5 = True
    
    # =================================================================
    # ÉTAPE 2 : CALCUL ÉLIGIBILITÉ
    # =================================================================
    
    can_oc_cpu = False
    can_oc_ram = False
    can_oc_gpu = False

    # CPU
    if is_intel:
        if is_intel_k and chipset_prefix == "Z": can_oc_cpu = True
    elif is_amd:
        if "RYZEN" in text and (chipset_prefix == "B" or chipset_prefix == "X"): can_oc_cpu = True

    # RAM
    if is_intel:
        if chipset_prefix == "Z" or is_intel_b_unlock: can_oc_ram = True
    elif is_amd:
        if chipset_prefix == "B" or chipset_prefix == "X": can_oc_ram = True

    # GPU
    if (is_nvidia or is_amd_gpu) and not is_intel_gpu: can_oc_gpu = True

    # =================================================================
    # ÉTAPE 3 : SÉLECTION OFFRE
    # =================================================================

    if is_x3d:
        return {"name": "🔥 Spécial X3D AM5", "price": "95€", "desc": "Optimisation spécifique X3D (CPU + RAM + GPU)."}

    if is_ddr5:
        if can_oc_cpu and can_oc_ram and can_oc_gpu:
            return {"name": "🚀 Overclock CPU + RAM DDR5 + GPU", "price": "195€", "desc": "Pack complet ultime DDR5."}
        elif can_oc_ram and can_oc_gpu:
            return {"name": "⚡ Overclock RAM DDR5 + GPU", "price": "135€", "desc": "CPU non 'K' ou Carte B : Focus RAM/GPU."}
        elif can_oc_cpu and can_oc_ram:
             return {"name": "🧠 Overclock CPU + RAM DDR5", "price": "155€", "desc": "Pack CPU/RAM (Pas de GPU compatible détecté)."}
        elif can_oc_cpu:
            return {"name": "⚙️ Overclock CPU (DDR5)", "price": "40€", "desc": "Optimisation CPU uniquement."}
        
    else: # DDR4
        if can_oc_cpu and can_oc_ram and can_oc_gpu:
            return {"name": "💎 Overclock CPU + RAM + GPU (DDR4)", "price": "85€", "desc": "Pack complet performance DDR4."}
        elif can_oc_ram and can_oc_gpu:
            return {"name": "⚡ Overclock RAM + GPU (DDR4)", "price": "55€", "desc": "CPU non 'K' ou Carte B : Focus RAM/GPU."}
        elif can_oc_cpu and can_oc_ram:
             return {"name": "🧠 Overclock CPU + RAM", "price": "65€", "desc": "Pack CPU/RAM (Pas de GPU compatible détecté)."}
        elif can_oc_cpu:
            return {"name": "⚙️ Overclock CPU", "price": "20€", "desc": "Optimisation CPU uniquement."}

    return {
        "name": "🛠️ Optimisation Windows / Maintenance",
        "price": "Sur devis",
        "desc": "Matériel non éligible à l'Overclocking complet."
    }

# --- 3. BOT EVENTS ---
@bot.event
async def on_ready():
    print(f"✅ Bot connecté. Salon : {ID_SALON}")

@bot.event
async def on_message(message):
    if message.author == bot.user or message.channel.id != ID_SALON: return

    if "userdiag.com" in message.content:
        words = message.content.split()
        url = next((w for w in words if "userdiag.com" in w), None)
        if not url: return

        msg = await message.channel.send(f"👀 **Analyse en cours...**")
        
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, scrape_userdiag, url)

        if "error" in data:
            await msg.edit(content=f"❌ {data['error']}")
            return

        offer = determine_offer(data["raw_text"])

        # Affichage Différent si Laptop
        if offer.get("is_laptop"):
            embed_text = f"**🚫 Analyse pour :** {message.author.mention}\n"
            embed_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            embed_text += f"❌ **{offer['name']}**\n"
            embed_text += f"📝 *{offer['desc']}*\n"
            embed_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━"
        else:
            embed_text = f"**📊 Analyse pour :** {message.author.mention}\n"
            embed_text += f"🔗 *{url}*\n"
            embed_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            embed_text += f"🎯 **SERVICE RECOMMANDÉ : {offer['name']}**\n"
            embed_text += f"💰 **Prix : {offer['price']}**\n\n"
            embed_text += f"📝 *{offer['desc']}*\n"
            embed_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            embed_text += "**💎 Avantages inclus :**\n• 📈 Gain FPS\n• 🛡️ SAV à vie\n• ☁️ Backup Cloud"
        
        await msg.edit(content=embed_text)

    await bot.process_commands(message)

bot.run(TOKEN)