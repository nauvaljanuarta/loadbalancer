import docker
import time
import os

# ── Konfigurasi ──────────────────────────────────────
CPU_THRESHOLD = float(os.getenv("CPU_THRESHOLD", 70))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 5))

# Urutan prioritas server
SERVER_PRIORITY = ["app1", "app2", "app3"]

client = docker.from_env()

def get_cpu_usage(container):
    """Hitung CPU usage (%) dari Docker stats API."""
    try:
        stats = container.stats(stream=False)
        cpu_delta = (
            stats["cpu_stats"]["cpu_usage"]["total_usage"]
            - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        )
        system_delta = (
            stats["cpu_stats"]["system_cpu_usage"]
            - stats["precpu_stats"]["system_cpu_usage"]
        )
        num_cpus = stats["cpu_stats"].get("online_cpus", 1)
        if system_delta > 0 and cpu_delta >= 0:
            return round((cpu_delta / system_delta) * num_cpus * 100.0, 2)
    except Exception as e:
        print(f"  [!] Error baca stats: {e}")
    return 0.0

def get_container_for_service(service_name):
    """Ambil container untuk service tertentu."""
    containers = client.containers.list(
        filters={"label": f"com.docker.compose.service={service_name}"}
    )
    return containers[0] if containers else None

def get_nginx_container():
    """Ambil container nginx loadbalancer."""
    containers = client.containers.list(
        filters={"label": "com.docker.compose.service=loadbalancer"}
    )
    return containers[0] if containers else None

def generate_nginx_conf(active_servers):
    """
    Generate nginx.conf — hanya server yang aktif yang menerima traffic.
    Server yang tidak aktif ditandai 'backup'.
    """
    upstream_lines = ""
    for svc in SERVER_PRIORITY:
        if svc in active_servers:
            upstream_lines += f"        server {svc}:5000;            # ✅ AKTIF\n"
        else:
            upstream_lines += f"        server {svc}:5000 backup;     # ⏳ STANDBY\n"

    conf = f"""events {{
    worker_connections 1024;
}}

http {{
    resolver 127.0.0.11 valid=5s;

    upstream flask_apps {{
{upstream_lines}    }}

    server {{
        listen 80;
        server_name localhost;

        location / {{
            proxy_pass http://flask_apps;

            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            proxy_connect_timeout 2s;
            proxy_read_timeout 10s;
        }}

        location /lb-health {{
            return 200 '{{"status": "load balancer healthy"}}';
            add_header Content-Type application/json;
        }}
    }}
}}
"""
    return conf

def reload_nginx(nginx_container, new_conf):
    """Tulis config baru ke nginx container dan reload."""
    try:
        import tarfile
        import io

        conf_bytes = new_conf.encode("utf-8")
        tar_stream = io.BytesIO()
        tar_info = tarfile.TarInfo(name="nginx.conf")
        tar_info.size = len(conf_bytes)
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            tar.addfile(tar_info, io.BytesIO(conf_bytes))
        tar_stream.seek(0)

        nginx_container.put_archive("/etc/nginx/", tar_stream)

        exit_code, output = nginx_container.exec_run("nginx -s reload")
        if exit_code == 0:
            print("  [✔] Nginx di-reload!")
        else:
            print(f"  [✘] Gagal reload nginx: {output.decode()}")
    except Exception as e:
        print(f"  [✘] Error reload nginx: {e}")

def monitor():
    """
    Loop utama — Scale Out / Scale In:
    - Mulai: hanya app1 aktif
    - Kalau ada server overload → TAMBAH server berikutnya ke pool
    - Kalau semua CPU rendah → kurangi kembali ke app1 saja
    """
    print("=" * 55)
    print("  🤖 AUTOSCALER AKTIF (Mode: Scale Out)")
    print(f"  CPU Threshold  : > {CPU_THRESHOLD}%")
    print(f"  Interval Cek   : {CHECK_INTERVAL} detik")
    print(f"  Prioritas      : {' → '.join(SERVER_PRIORITY)}")
    print("=" * 55)

    # Mulai hanya dengan app1
    active_servers = {"app1"}
    prev_active = set(active_servers)

    while True:
        print(f"\n[{time.strftime('%H:%M:%S')}] Server aktif: {', '.join(sorted(active_servers))}")

        # Cek CPU semua server
        cpu_data = {}
        any_overload = False
        all_low = True

        for svc in SERVER_PRIORITY:
            container = get_container_for_service(svc)
            if not container:
                print(f"  {svc}: tidak ada container")
                continue

            cpu = get_cpu_usage(container)
            cpu_data[svc] = cpu

            role = "⬅️  AKTIF" if svc in active_servers else "   STANDBY"
            status = "❌ OVERLOAD" if cpu > CPU_THRESHOLD else "✅ OK"
            print(f"  {svc}: CPU = {cpu:.1f}% → {status} {role}")

            if svc in active_servers and cpu > CPU_THRESHOLD:
                any_overload = True
            if svc in active_servers and cpu > 20:
                all_low = False

        # ── SCALE OUT: Ada server aktif yang overload → tambah server baru ──
        if any_overload:
            # Cari server berikutnya yang belum aktif
            added = False
            for svc in SERVER_PRIORITY:
                if svc not in active_servers:
                    active_servers.add(svc)
                    overloaded = [s for s in active_servers if cpu_data.get(s, 0) > CPU_THRESHOLD]
                    print(f"\n  ⚡ SCALE OUT! Server overload: {', '.join(overloaded)}")
                    print(f"  ➕ Tambah {svc} ke pool aktif")
                    print(f"  → Traffic sekarang ke: {', '.join(sorted(active_servers))}")
                    added = True
                    break

            if not added:
                print(f"\n  ⚠️  Semua server sudah aktif! Tidak bisa scale out lagi.")

        # ── SCALE IN: Semua server aktif CPU rendah & lebih dari 1 aktif → kurangi ──
        elif all_low and len(active_servers) > 1:
            # Hapus server terakhir yang ditambahkan (prioritas terbalik)
            for svc in reversed(SERVER_PRIORITY):
                if svc in active_servers and len(active_servers) > 1:
                    active_servers.remove(svc)
                    print(f"\n  📉 SCALE IN! Semua CPU rendah.")
                    print(f"  ➖ Hapus {svc} dari pool aktif")
                    print(f"  → Traffic sekarang ke: {', '.join(sorted(active_servers))}")
                    break

        # ── Update nginx jika ada perubahan ──
        if active_servers != prev_active:
            nginx = get_nginx_container()
            if nginx:
                new_conf = generate_nginx_conf(active_servers)
                reload_nginx(nginx, new_conf)
            prev_active = set(active_servers)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    print("Menunggu container siap...")
    time.sleep(5)
    monitor()
