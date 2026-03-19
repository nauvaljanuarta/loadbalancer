"""
Load Test Script — Kirim banyak request ke load balancer
Cara pakai: python stress_test.py [url] [jumlah_request] [jumlah_thread]

Contoh:
  python stress_test.py                                     → default: 50 request, 3 thread ke /stress
  python stress_test.py http://localhost/stress 50 3
"""
import requests
import threading
import time
import sys

# ── Konfigurasi Default (disesuaikan untuk Scale Out demo) ──
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost/stress"
TOTAL_REQUESTS = int(sys.argv[2]) if len(sys.argv) > 2 else 50
NUM_THREADS = int(sys.argv[3]) if len(sys.argv) > 3 else 3

# Counter
success = 0
failed = 0
lock = threading.Lock()

def send_requests(thread_id, count):
    global success, failed
    for i in range(count):
        try:
            r = requests.get(URL, timeout=60)
            with lock:
                success += 1
            print(f"  [Thread-{thread_id}] Request #{i+1} → {r.status_code}")
        except Exception as e:
            with lock:
                failed += 1
            print(f"  [Thread-{thread_id}] Request #{i+1} → GAGAL: {e}")
        time.sleep(0.05)  # Jeda 

def main():
    print("=" * 55)
    print("  🔥 LOAD TEST / STRESS TEST")
    print(f"  Target URL     : {URL}")
    print(f"  Total Request  : {TOTAL_REQUESTS}")
    print(f"  Jumlah Thread  : {NUM_THREADS}")
    print(f"  Request/Thread : {TOTAL_REQUESTS // NUM_THREADS}")
    print(f"  Jeda antar req : 1 detik")
    print("=" * 55)
    print()

    requests_per_thread = TOTAL_REQUESTS // NUM_THREADS
    threads = []

    start_time = time.time()

    for i in range(NUM_THREADS):
        t = threading.Thread(target=send_requests, args=(i+1, requests_per_thread))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    elapsed = time.time() - start_time

    print()
    print("=" * 55)
    print("  📊 HASIL")
    print(f"  Berhasil : {success}")
    print(f"  Gagal    : {failed}")
    print(f"  Waktu    : {elapsed:.2f} detik")
    print(f"  RPS      : {success / elapsed:.1f} request/detik")
    print("=" * 55)

if __name__ == "__main__":
    main()
