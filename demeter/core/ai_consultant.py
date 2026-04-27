import os
import json
import base64
from PIL import Image
from litellm import completion
from core.state import logger, LLM_BASE_MODEL, LLM_BASE_URL, API_KEY_LIST, LLM_API_KEY, global_brain

def consult_demeter(moisture, temp, current_img, prev_img):
    logger.info(f"[DEMETER] Analisa Komparatif dimulai...")
    
    persona_text = ""
    # The root directory is 2 levels up from core/ai_consultant.py
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    persona_md_path = os.path.join(current_dir, "persona_demeter.md")
    legacy_persona_path = os.path.join(current_dir, "prompt_persona.txt")

    try:
        if os.path.exists(persona_md_path):
            with open(persona_md_path, "r", encoding="utf-8") as f:
                persona_text = f.read()
        elif os.path.exists(legacy_persona_path):
             with open(legacy_persona_path, "r", encoding="utf-8") as f:
                persona_text = f.read()
    except Exception as e:
        logger.warning(f"[SYSTEM WARN] Gagal baca persona: {e}. Menggunakan default.")
        persona_text = "Bertindaklah sebagai asisten kebun. Analisa apakah tanaman butuh air berdasarkan foto dan sensor."

    if not current_img:
        logger.warning("[AI] Foto tidak ditemukan.")
        return {"action": "DIAM", "duration_sec": 0, "reason": "No Image"}

    prompt = f"""
    {persona_text}
    
    =========================================
    📊 DATA AKTUAL KEBUN:
    - Moisture Sensor: {moisture}%
    - Suhu Udara: {temp}°C
    =========================================
    
    ⚠️ INSTRUKSI SISTEM (JANGAN DIUBAH):
    Jawab HANYA dengan JSON valid. Tanpa markdown ```json.
    Format Wajib:
    {{
        "action": "SIRAM" atau "DIAM",
        "duration_sec": 5,
        "health_score": "Excellent" atau "Good" atau "Fair" atau "Poor",
        "estimated_height_cm": 15.5,
        "reason": "Paragraf analisa lengkap (3-4 kalimat) berdasarkan panduan visual di atas. Sertakan observasi daun dan tanah."
    }}
    """
    
    try:
        keys_to_try = API_KEY_LIST if API_KEY_LIST else [LLM_API_KEY]
        
        def encode_image(image_path):
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')

        last_error = None
        
        for attempt, api_key_val in enumerate(keys_to_try):
            try:
                messages = [
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt}
                    ]}
                ]
                
                if prev_img and os.path.exists(prev_img):
                    try:
                        b64 = encode_image(prev_img)
                        messages[0]["content"].append({
                            "type": "image_url", 
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                        })
                    except: pass
        
                if current_img and os.path.exists(current_img):
                    try:
                        b64 = encode_image(current_img)
                        messages[0]["content"].append({
                            "type": "image_url", 
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                        })
                    except: pass
        
                response = completion(
                    model=LLM_BASE_MODEL,
                    messages=messages,
                    response_format={"type": "json_object"},
                    api_key=api_key_val,
                    api_base=LLM_BASE_URL if LLM_BASE_URL else None
                )
                
                raw_response = response.choices[0].message.content
                ai_json = json.loads(raw_response)
                
                try:
                    reasoning_text = ai_json.get("reason", "No reasoning provided.")
                    mem_text = f"DEMETER STATUS REPORT: Action={ai_json.get('action')} | Condition: {reasoning_text}"
                    global_brain.record(text=mem_text, user_name="DemeterAI", source="demeter_ai_brain", tags="demeter, ai_consultation, decision")
                    logger.info("[MEMORY] AI Reasoning saved to Core.")
                except Exception as mem_err:
                    logger.error(f"[ERROR] AI Memory Save Failed: {mem_err}")

                return ai_json
                
            except Exception as e:
                logger.warning(f"⚠️ Attempt {attempt+1} failed: {e}")
                last_error = e
                import time; time.sleep(1)
        
        raise last_error if last_error else Exception("All keys exhausted.")

    except Exception as e:
        logger.error(f"⚠️ System Error: {str(e)}")
        return {"action": "DIAM", "duration_sec": 0, "reason": f"AI Failure: {str(e)}"}
