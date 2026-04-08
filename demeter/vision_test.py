import cv2
import time
import os

# --- KONFIGURASI KAMERA ---
# GANTI INI sesuai kamera kamu!
# Jangan lupa encode password jika ada karakter aneh (misal @ diganti %40)
RTSP_URL = "rtsp://admin:L2164818@192.168.168.31/cam/realmonitor?channel=1&subtype=0" 

def ambil_snapshot():
    print(f"[KAMERA] Mencoba terhubung ke: {RTSP_URL}")
    
    # Buka koneksi ke stream
    cap = cv2.VideoCapture(RTSP_URL)
    
    # Cek apakah berhasil dibuka
    if not cap.isOpened():
        print("[ERROR] Gagal membuka stream RTSP. Cek URL/Password/Jaringan.")
        return
    
    # Biarkan buffer kamera "panas" dulu (skip beberapa frame awal biar gambar jelas)
    for i in range(10):
        cap.read()
        
    # Ambil 1 Frame Bersih
    ret, frame = cap.read()
    
    if ret:
        filename = "capture_test.jpg"
        cv2.imwrite(filename, frame)
        print(f"[SUKSES] Gambar berhasil disimpan: {filename}")
        print("Cek file tersebut. Apakah gambarnya jelas?")
    else:
        print("[ERROR] Gagal membaca frame (Stream putus/timeout).")
        
    # Tutup koneksi
    cap.release()

if __name__ == "__main__":
    ambil_snapshot()
