from flask import Flask, jsonify, request
import socket
import time
import threading
import redis
import json
import hashlib
import os
import random

app = Flask(__name__)

# ── Koneksi Redis (Caching Layer) ──────────────────────
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
CACHE_TTL  = int(os.getenv("CACHE_TTL", 30))  # TTL default 30 detik

def get_redis():
    """Buat koneksi Redis dengan retry."""
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0,
                        decode_responses=True, socket_timeout=2)
        r.ping()
        return r
    except Exception:
        return None

# ── Helper: Simulasi "heavy computation" ──────────────
def heavy_computation(complexity=1):
    """Simulasi proses berat (database query / API call)."""
    time.sleep(0.5 * complexity)  # Simulasi latency
    result = sum(i * i for i in range(50000 * complexity))
    return result

# ── Endpoint: Home ────────────────────────────────────
@app.route("/")
def home():
    hostname = socket.gethostname()
    return f"""
    <h1>Hello from Server 3</h1>
    <hr>
    <p><b>Server:</b> app3</p>
    <p><b>Hostname:</b> {hostname}</p>
    <p><b>IP Address:</b> {socket.gethostbyname(hostname)}</p>
    <hr>
    """

# ── Endpoint: Data dengan Caching ─────────────────────
@app.route("/data")
def get_data():
    """
    Endpoint yang mensimulasikan pengambilan data berat.
    Menggunakan Redis sebagai caching layer.
    """
    category = request.args.get("category", "general")
    nocache  = request.args.get("nocache", "0") == "1"
    cache_key = f"data:app3:{category}"
    hostname  = socket.gethostname()

    start_time = time.time()

    r = get_redis()

    # ── Cek cache (jika tidak bypass) ──
    if r and not nocache:
        try:
            cached = r.get(cache_key)
            if cached:
                elapsed = (time.time() - start_time) * 1000
                data = json.loads(cached)
                data["cache_status"]   = "HIT"
                data["response_time"]  = f"{elapsed:.2f} ms"
                data["served_by"]      = f"app3 ({hostname})"
                data["cache_ttl_left"] = r.ttl(cache_key)
                return jsonify(data)
        except Exception:
            pass

    # ── Cache MISS → Proses berat ──
    complexity = random.randint(1, 3)
    result = heavy_computation(complexity)
    elapsed = (time.time() - start_time) * 1000

    data = {
        "category":       category,
        "result":         result,
        "complexity":     complexity,
        "cache_status":   "MISS",
        "response_time":  f"{elapsed:.2f} ms",
        "served_by":      f"app3 ({hostname})",
        "timestamp":      time.strftime("%Y-%m-%d %H:%M:%S"),
        "cache_ttl_left": CACHE_TTL,
    }

    # ── Simpan ke cache ──
    if r:
        try:
            r.setex(cache_key, CACHE_TTL, json.dumps(data))
        except Exception:
            pass

    return jsonify(data)

# ── Endpoint: Cache Stats ─────────────────────────────
@app.route("/cache-stats")
def cache_stats():
    """Lihat statistik Redis cache."""
    r = get_redis()
    if not r:
        return jsonify({"error": "Redis tidak tersedia"}), 503

    try:
        info = r.info("stats")
        memory = r.info("memory")
        keyspace = r.info("keyspace")

        return jsonify({
            "server":          "app3",
            "redis_connected": True,
            "hits":            info.get("keyspace_hits", 0),
            "misses":          info.get("keyspace_misses", 0),
            "hit_rate":        round(
                info.get("keyspace_hits", 0) /
                max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1) * 100, 2
            ),
            "used_memory":     memory.get("used_memory_human", "N/A"),
            "max_memory":      memory.get("maxmemory_human", "N/A"),
            "total_keys":      sum(
                v.get("keys", 0) for v in keyspace.values() if isinstance(v, dict)
            ),
            "evicted_keys":    info.get("evicted_keys", 0),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Endpoint: Flush Cache ─────────────────────────────
@app.route("/cache-flush", methods=["POST"])
def cache_flush():
    """Hapus semua cache (untuk demo)."""
    r = get_redis()
    if not r:
        return jsonify({"error": "Redis tidak tersedia"}), 503
    try:
        keys_before = r.dbsize()
        r.flushdb()
        return jsonify({
            "status":       "flushed",
            "keys_deleted": keys_before,
            "server":       "app3"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Endpoint: CDN Simulated Static Asset ──────────────
@app.route("/static-asset")
def static_asset():
    """Simulasi pengambilan static asset — di-cache oleh Nginx (CDN edge)."""
    hostname = socket.gethostname()
    time.sleep(0.3)
    payload = {
        "asset_type":    "simulated_image_data",
        "size_kb":       256,
        "origin_server": f"app3 ({hostname})",
        "generated_at":  time.strftime("%Y-%m-%d %H:%M:%S"),
        "data":          "x" * 1024,
    }
    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "public, max-age=60"
    resp.headers["X-Origin-Server"] = f"app3"
    return resp

# ── Endpoint: Stress Test ─────────────────────────────
def cpu_burn(duration=5):
    """Bakar CPU ringan — pakai ~30% CPU per thread selama N detik."""
    end = time.time() + duration
    while time.time() < end:
        _ = sum(i * i for i in range(5000))
        time.sleep(0.05)

@app.route("/stress")
def stress():
    """Endpoint stress — 1 thread, 5 detik, ringan."""
    t = threading.Thread(target=cpu_burn, args=(5,))
    t.daemon = True
    t.start()
    hostname = socket.gethostname()
    return f"""
    <h1>Stress Test Dimulai - Server 3</h1>
    <hr>
    <p><b>Server:</b> app3</p>
    <p><b>Hostname:</b> {hostname}</p>
    <p><b>Durasi:</b> 5 detik</p>
    <hr>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0")
