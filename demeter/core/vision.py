import os
import glob
import time
import cv2
from datetime import datetime
from core.state import logger, CAPTURE_DIR, RTSP_URL

def get_previous_image(current_img_path):
    """Mencari gambar satu langkah sebelum gambar saat ini"""
    try:
        if not os.path.exists(CAPTURE_DIR):
             os.makedirs(CAPTURE_DIR)

        list_files = sorted(glob.glob(os.path.join(CAPTURE_DIR, "*.jpg")))
        
        if len(list_files) < 2:
            return None
            
        current_name = os.path.basename(current_img_path)
        for i, f in enumerate(list_files):
            if os.path.basename(f) == current_name:
                if i > 0:
                    return list_files[i-1]
                else:
                    return None
        
        return list_files[-2]
    except Exception as e:
        logger.error(f"[VISION ERROR] Gagal mencari gambar sebelumnya: {e}")
        return None

def cleanup_vision_folder(max_days=3, max_files=1000):
    try:
        if not os.path.exists(CAPTURE_DIR): return

        now = time.time()
        cutoff = now - (max_days * 86400)
        
        files = glob.glob(os.path.join(CAPTURE_DIR, "*.jpg"))
        deleted = 0
        
        for f in files:
            if os.path.getmtime(f) < cutoff:
                try:
                    os.remove(f)
                    deleted += 1
                except: pass
        
        if deleted > 0:
            logger.info(f"[CLEANUP] Deleted {deleted} old images (> {max_days} days).")

        files = sorted(glob.glob(os.path.join(CAPTURE_DIR, "*.jpg")), key=os.path.getmtime)
        if len(files) > max_files:
            excess = len(files) - max_files
            for i in range(excess):
                try:
                    os.remove(files[i])
                except: pass
            logger.info(f"[CLEANUP] Deleted {excess} excess images (Limit: {max_files}).")
            
    except Exception as e:
        logger.error(f"[ERROR] Cleanup failed: {e}")

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

def capture_visual():
    logger.info("[VISION] Capture sequence started...")
    
    cap = None
    filepath = None
    
    try:
        if not os.path.exists(CAPTURE_DIR):
            os.makedirs(CAPTURE_DIR)
            
        if __import__("random").random() < 0.1:
            cleanup_vision_folder()

        cap = cv2.VideoCapture(RTSP_URL)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if not cap.isOpened():
            logger.error("[ERROR] RTSP Fail.")
            return None
        
        cap.read() 
        ret, frame = cap.read()
        
        if ret and frame is not None:
            timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"{timestamp_str}.jpg"
            filepath = os.path.join(CAPTURE_DIR, filename)
            cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            return filepath
        return None
        
    except Exception as e:
        logger.error(f"[ERROR] Vision Crash: {e}")
        return None
        
    finally:
        if cap:
            try:
                cap.release()
            except: pass
