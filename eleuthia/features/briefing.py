"""
Morning Briefing Module
Generates daily morning reports with weather, calendar, and VIP inbox.
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

def get_weather(city: str = "Bekasi", timeout: int = 5) -> str:
    """
    Get weather information from wttr.in.
    
    Args:
        city: City name
        timeout: Request timeout in seconds
    
    Returns:
        Weather string or error message
    """
    try:
        url = f"https://wttr.in/{city}?format=%C+%t+%w"
        response = requests.get(url, timeout=timeout)
        
        if response.status_code == 200:
            weather = response.text.strip()
            logger.info(f"✅ Weather fetched: {weather}")
            return weather
        else:
            logger.warning(f"Weather API returned {response.status_code}")
            return "Weather Data Unavailable"
            
    except requests.Timeout:
        logger.error("Weather API timeout")
        return "Weather Data Unavailable (Timeout)"
    except Exception as e:
        logger.error(f"Weather fetch failed: {e}")
        return "Weather Data Unavailable"

def get_calendar_events(next_24h: bool = True) -> List[Dict]:
    """
    Get calendar events for the next 24 hours.
    
    Args:
        next_24h: If True, get events for next 24 hours
    
    Returns:
        List of event dicts with 'time' and 'title'
    """
    # TODO: Implement calendar integration
    # For now, return empty list
    logger.info("📅 Calendar integration not yet implemented")
    return []

def get_vip_inbox(vip_senders: List[str]) -> List[Dict]:
    """
    Get unread emails from VIP senders.
    
    Args:
        vip_senders: List of VIP email addresses
    
    Returns:
        List of email dicts with 'sender' and 'subject'
    """
    # TODO: Implement email filtering by sender
    # For now, return empty list
    logger.info("📧 VIP inbox check not yet implemented")
    return []

def generate_morning_report(
    city: str = "Bekasi",
    vip_emails: Optional[List[str]] = None,
    include_weather: bool = True,
    include_calendar: bool = True,
    include_vip_inbox: bool = True,
    include_memory: bool = True
) -> str:
    """
    Generate morning briefing report with RAG + LangChain.
    
    Args:
        city: City for weather
        vip_emails: List of VIP email addresses
        include_weather: Include weather section
        include_calendar: Include calendar section
        include_vip_inbox: Include VIP inbox section
        include_memory: Include semantic memory insights
    
    Returns:
        Formatted morning report string
    """
    if vip_emails is None:
        vip_emails = []
    
    # --- [RAG CORE SETUP] ---
    try:
        from eleuthia_memory_manager import EleuthiaBrain
        brain = EleuthiaBrain()
    except Exception as e:
        logger.error(f"Failed to initialize EleuthiaBrain for RAG: {e}")
        brain = None

    # Get current date
    now = datetime.now()
    date_str = now.strftime("%A, %d %B %Y")
    
    # Build report components
    sections = []
    
    # 1. Header
    sections.append(f"☀️ *Selamat Pagi, Boss.*\n📅 {date_str}")
    
    # 2. Weather section
    if include_weather:
        weather = get_weather(city)
        sections.append(f"🌤️ *Cuaca {city}*\n{weather}")
    
    # 3. Calendar section
    if include_calendar:
        events = get_calendar_events(next_24h=True)
        cal_text = "📅 *Jadwal Hari Ini*\n"
        if events:
            for event in events:
                time_str = event.get('time', 'N/A')
                title = event.get('title', 'Untitled')
                cal_text += f"• {time_str}: {title}\n"
        else:
            cal_text += "📅 Tidak ada jadwal hari ini. Enjoy!"
        sections.append(cal_text)
    
    # 4. VIP Inbox section
    if include_vip_inbox and vip_emails:
        vip_emails_list = get_vip_inbox(vip_emails)
        vip_text = "✉️ *Inbox VIP*\n"
        if vip_emails_list:
            for email in vip_emails_list:
                sender = email.get('sender', 'Unknown')
                subject = email.get('subject', 'No Subject')
                vip_text += f"• {sender}: {subject}\n"
        else:
            vip_text += "✉️ Inbox aman terkendali."
        sections.append(vip_text)

    # 5. RAG Memory Section
    memory_insights = ""
    if include_memory and brain:
        logger.info("🧠 Performing RAG search for morning briefing context...")
        # Search for context from the last 24 hours or general "urgent" history
        memories = brain.search_emails(
            query="urgent tasks pending items important reminders",
            n_results=3,
            classification_filter="urgent"
        )
        
        if memories:
            memory_insights = "🧠 *Catatan Penting (Neural Memory)*\n"
            for mem in memories:
                memory_insights += f"• {mem.get('subject', 'Memory')}: {mem.get('content', '')[:100]}...\n"
            sections.append(memory_insights)

    # --- [LLM POLISHING WITH RAG CONTEXT] ---
    raw_report = "\n\n".join(sections)
    
    if brain:
        try:
            from litellm import completion
            from config import LLMConfig
            
            # Load Unified Persona (Markdown)
            persona_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "persona_eleuthia.md")
            persona_text = "You are Eleuthia, a highly sophisticated Indonesian AI assistant."
            try:
                if os.path.exists(persona_path):
                    with open(persona_path, "r", encoding="utf-8") as f:
                        persona_text = f.read()
            except: pass

            logger.info("🤖 Polishing briefing with LLM...")
            
            polishing_prompt = f"""{persona_text}

CONTEXT: Take the following raw briefing data and polish it into a premium, professional, and helpful morning report for 'Boss'.

Raw Data:
{raw_report}

Instructions:
1. Maintain the Markdown formatting (bold, bullet points).
2. Keep the tone professional but warm/loyal Indonesian.
3. If there are VIP emails or urgent memories, highlight them as priorities.
4. Ensure the closing is "Siap menjalankan perintah."
5. Output ONLY the polished report text.
"""

            response = completion(
                model=LLMConfig.MODEL,
                messages=[{"role": "user", "content": polishing_prompt}],
                api_key=LLMConfig.API_KEY,
                base_url=LLMConfig.BASE_URL,
                temperature=0.3
            )
            
            polished_report = response.choices[0].message.content.strip()
            return polished_report
            
        except Exception as e:
            logger.error(f"LLM polishing failed: {e}")
            return raw_report + "\n\n🤖 Siap menjalankan perintah."

    return raw_report + "\n\n🤖 Siap menjalankan perintah."

if __name__ == "__main__":
    # Test briefing
    logging.basicConfig(level=logging.INFO)
    
    print("\n" + "="*60)
    print("MORNING BRIEFING TEST")
    print("="*60 + "\n")
    
    report = generate_morning_report(
        city="Bekasi",
        vip_emails=["boss@company.com", "bank@bca.co.id"],
        include_weather=True,
        include_calendar=True,
        include_vip_inbox=True
    )
    
    print(report)
    print("\n" + "="*60)
