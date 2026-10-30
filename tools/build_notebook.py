#!/usr/bin/env python3
"""
Membangun notebook Colab CO-Zero (dashboard/cozero_dashboard_colab.ipynb).

Notebook ini adalah sumber tunggal tampilan dashboard berbasis Plotly. Berkas
.ipynb dihasilkan ulang dari skrip ini agar isinya selalu konsisten dan dapat
ditinjau sebagai teks biasa. Setelah mengubah isi sel di bawah, jalankan:

    python tools/build_notebook.py
"""
import json
import os

CELLS = []


def md(text):
    CELLS.append({"cell_type": "markdown", "metadata": {},
                  "source": text.strip("\n").splitlines(True)})


def code(text):
    CELLS.append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.strip("\n").splitlines(True),
    })


md(r"""
# CO-Zero — Dashboard Monitoring CO Kabin Mobil

**Samsung Innovation Campus Batch 8 — Stage 2 (IoT)**
Tim Iki jenenge wes wkwk · Politeknik Negeri Malang

Notebook ini berlangganan (subscribe) ke topik MQTT yang dipublikasikan oleh
ESP32 (Wokwi) melalui **broker publik EMQX** (gratis, tanpa akun), lalu
menampilkan dashboard real-time dengan **Plotly**.

### Alur data
`MQ-2 → ESP32 → WiFi → broker MQTT → notebook ini → grafik`

### Langkah
1. Jalankan cell **Instalasi**.
2. Periksa cell **Konfigurasi** — `MQTT_HOST`, `MQTT_PORT`, dan `TOPIC_BASE`
   harus sama persis dengan `firmware/cozero_esp32.ino`.
3. Jalankan cell **Koneksi** — tunggu sampai muncul `[MQTT] connected`.
4. Jalankan cell **Dashboard live** dan nyalakan simulasi Wokwi.

> Broker publik bersifat terbuka. Pastikan `TOPIC_BASE` memakai kode unik tim
> (contoh: `cozero/sic8-wkwk7`) agar data tidak bercampur dengan pengguna lain.
""")

code(r"""
!pip install -q paho-mqtt
print("paho-mqtt terpasang")
""")

code(r"""
import json, ssl, threading, time
from collections import deque
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from IPython.display import clear_output

import paho.mqtt.client as mqtt

# ============================================================
#  KONFIGURASI — samakan dengan firmware/config di Wokwi
# ============================================================
MQTT_HOST = "broker.emqx.io"   # broker publik gratis (EMQX)
MQTT_PORT = 8883               # 8883 = TLS, 1883 = tanpa TLS
MQTT_USER = ""                 # broker publik: kosongkan
MQTT_PASS = ""                 # broker publik: kosongkan

# Opsional (disarankan bila notebook dibagikan): simpan kredensial di
# Colab Secrets (ikon kunci di sidebar kiri), bukan di dalam file .ipynb.
# from google.colab import userdata
# MQTT_USER = userdata.get("MQTT_USER") or ""
# MQTT_PASS = userdata.get("MQTT_PASS") or ""

TOPIC_BASE      = "cozero/sic8-wkwk7"
TOPIC_TELEMETRY = TOPIC_BASE + "/telemetry"
TOPIC_ALERT     = TOPIC_BASE + "/alert"
TOPIC_STATUS    = TOPIC_BASE + "/status"

TH_WASPADA, TH_BAHAYA, TH_KRITIS = 20, 35, 115

# Ambang iklim mikro, identik dengan firmware
TH_TEMP_PANAS = 40.0      # celsius
TH_RH_LEMBAB  = 75.0      # %RH
TH_RH_KERING  = 20.0      # %RH

LEVEL_COLOR = {"AMAN": "#2e7d32", "WASPADA": "#f9a825",
               "BAHAYA": "#ef6c00", "KRITIS": "#c62828"}

assert MQTT_HOST and "xxxx" not in MQTT_HOST, "MQTT_HOST belum diisi"
print(f"Konfigurasi OK -> {MQTT_HOST}:{MQTT_PORT}  topik={TOPIC_BASE}")
""")

code(r"""
# ============================================================
#  Buffer data & callback
# ============================================================
rows = deque(maxlen=3000)      # seluruh riwayat sesi
alerts = deque(maxlen=20)
status = {"online": False, "last": None}

_lock = threading.Lock()

def on_connect(client, userdata, flags, rc, properties=None):
    print("[MQTT] connected, rc =", rc)
    client.subscribe(TOPIC_TELEMETRY, qos=1)
    client.subscribe(TOPIC_ALERT, qos=1)
    client.subscribe(TOPIC_STATUS, qos=1)

def on_disconnect(client, userdata, *args):
    print("[MQTT] terputus:", args[-1] if args else "-")

def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8", errors="replace")

    if msg.topic.endswith("/status"):
        status["online"] = "online" in payload
        return

    if msg.topic.endswith("/alert"):
        print("[ALERT]", payload)
        try:
            d = json.loads(payload)
            alerts.append(f"{datetime.now():%H:%M:%S}  {d.get('prev')} -> "
                          f"{d.get('level')} ({d.get('co_ppm', 0):.2f} ppm, "
                          f"{d.get('reason', 'co')})")
        except Exception:
            pass
        return

    try:
        d = json.loads(payload)
    except json.JSONDecodeError:
        return

    dht_ok = bool(d.get("dht_ok", True))
    with _lock:
        rows.append({
            "waktu": datetime.now(),
            "device": d.get("device_id", "-"),
            "co_ppm": float(d.get("co_ppm", 0)),
            # Nilai iklim mikro tidak valid dikirim sebagai NaN agar grafik
            # menampilkan celah, bukan garis mendatar di 0 C / 0 %RH.
            "temp_c": float(d.get("temp_c", 0)) if dht_ok else float("nan"),
            "rh": float(d.get("rh", 0)) if dht_ok else float("nan"),
            "level": d.get("level", "-"),
            "level_code": int(d.get("level_code", 0)),
            "co_level": d.get("co_level", "-"),
            "env": d.get("env", "NORMAL") if dht_ok else "-",
            "dht_ok": dht_ok,
        })
        status["last"] = datetime.now()

def make_client():
    cid = f"cozero-colab-{int(time.time())}"
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid,
                           protocol=mqtt.MQTTv311)
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=cid, protocol=mqtt.MQTTv311)

client = make_client()
if MQTT_USER:
    client.username_pw_set(MQTT_USER, MQTT_PASS)
if MQTT_PORT == 8883:
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect
client.reconnect_delay_set(min_delay=1, max_delay=5)

client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
client.loop_start()
time.sleep(2)
if client.is_connected():
    print("Status: terhubung ke broker.")
else:
    print("Status: TIDAK terhubung. Periksa MQTT_HOST/MQTT_PORT, atau coba")
    print("        broker.hivemq.com:8883 sebagai alternatif.")
print("Menunggu data... (simulasi Wokwi dijalankan pada tahap ini)")
""")

code(r'''
# ============================================================
#  Dashboard live (Plotly) — dijalankan selama demo / perekaman video
# ============================================================
from plotly.subplots import make_subplots

def _band(fig, yref, y0, y1, warna, opacity=0.55):
    """Pita horizontal pada subplot tertentu (kompatibel plotly 5 dan 7)."""
    fig.add_shape(type="rect", xref="paper", x0=0, x1=1, yref=yref,
                  y0=y0, y1=y1, fillcolor=warna, opacity=opacity,
                  line_width=0, layer="below")

def render(df):
    last = df.iloc[-1]
    warna = LEVEL_COLOR.get(last["level"], "gray")

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.65, 0.35], vertical_spacing=0.10,
        subplot_titles=("Kadar CO kabin", "Iklim mikro kabin"),
    )

    # --- panel CO: pita ambang batas, sumbu logaritmik ---
    CO_FLOOR, CO_CEIL = 0.1, 1000.0
    _band(fig, "y", CO_FLOOR, TH_WASPADA, "#c8e6c9", 0.45)
    _band(fig, "y", TH_WASPADA, TH_BAHAYA, "#fff9c4", 0.60)
    _band(fig, "y", TH_BAHAYA, TH_KRITIS, "#ffe0b2", 0.60)
    _band(fig, "y", TH_KRITIS, CO_CEIL, "#ffcdd2", 0.60)

    fig.add_trace(go.Scatter(x=df.waktu, y=df.co_ppm, mode="lines+markers",
                             name="CO (ppm)", line=dict(color="#c62828", width=2)),
                  row=1, col=1)

    # --- panel iklim mikro: pita LEMBAB / KERING + garis PANAS ---
    _band(fig, "y2", TH_RH_LEMBAB, 100, "#b3e5fc")
    _band(fig, "y2", 0, TH_RH_KERING, "#d7ccc8")
    fig.add_shape(type="line", xref="paper", x0=0, x1=1, yref="y2",
                  y0=TH_TEMP_PANAS, y1=TH_TEMP_PANAS,
                  line=dict(color="#d84315", width=1.5, dash="dash"))

    fig.add_trace(go.Scatter(x=df.waktu, y=df.temp_c, mode="lines",
                             name="Suhu (°C)", line=dict(color="#1565c0", width=1.6)),
                  row=2, col=1)
    fig.add_trace(go.Scatter(x=df.waktu, y=df.rh, mode="lines",
                             name="RH (%)", line=dict(color="#00897b", width=1.6)),
                  row=2, col=1)

    if last["dht_ok"]:
        iklim = f"{last['temp_c']:.1f} °C / {last['rh']:.0f} %RH ({last['env']})"
    else:
        iklim = "DHT22 tidak terbaca"

    fig.update_layout(
        title=dict(
            text=(f"<b>CO-Zero Dashboard</b> — status <span style='color:{warna}'>"
                  f"<b>{last['level']}</b></span> | CO {last['co_ppm']:.2f} ppm "
                  f"(level CO: {last['co_level']}) | iklim: {iklim}"),
            x=0.5, xanchor="center"),
        template="plotly_white",
        height=680,
        margin=dict(l=60, r=30, t=90, b=50),
        legend=dict(orientation="h", y=1.04),
        showlegend=True,
    )
    fig.update_yaxes(title_text="CO (ppm, skala log)", type="log",
                     range=[-1, 3], row=1, col=1)
    fig.update_yaxes(title_text="Suhu (°C) / RH (%)", range=[0, 100], row=2, col=1)
    fig.update_xaxes(title_text="Waktu", row=2, col=1)

    fig.add_annotation(x=df.waktu.iloc[-1], y=last["co_ppm"],
                       text=f"{last['co_ppm']:.2f} ppm", showarrow=True,
                       arrowhead=2, ay=-30, row=1, col=1)
    return fig

DURASI = 600     # 10 menit; hentikan manual (tombol stop) bila rekaman selesai
for i in range(DURASI):
    with _lock:
        data = list(rows)

    if len(data) < 2:
        clear_output(wait=True)
        print(f"Menunggu data MQTT... ({i}/{DURASI})  online={status['online']}  "
              f"data={len(data)}  konek={client.is_connected()}")
        if i == 20 and not data:
            print("\nBelum ada data masuk. Pastikan simulasi Wokwi sedang berjalan,")
            print("tab Wokwi tidak diminimize, dan TOPIC_BASE sama dengan firmware.")
        time.sleep(1)
        continue

    df = pd.DataFrame(data).tail(120)
    clear_output(wait=True)
    render(df).show()
    if alerts:
        print("Riwayat peringatan:")
        for a in list(alerts)[-5:]:
            print("  •", a)
    time.sleep(1)
''')

code(r"""
# ============================================================
#  Ekspor hasil sesi (untuk lampiran laporan)
# ============================================================
df_all = pd.DataFrame(list(rows))
print(f"Total sampel: {len(df_all)}")

if len(df_all):
    nama = f"cozero_log_{datetime.now():%Y%m%d_%H%M%S}.csv"
    df_all.to_csv(nama, index=False)

    ringkas = df_all.groupby("level").agg(
        jumlah=("co_ppm", "size"),
        co_min=("co_ppm", "min"),
        co_maks=("co_ppm", "max"),
    ).round(1)
    print("\nRingkasan per level:")
    display(ringkas)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_all.waktu, y=df_all.co_ppm, mode="lines", name="CO"))
    fig.add_trace(go.Scatter(x=df_all.waktu, y=df_all.temp_c, mode="lines",
                             name="Suhu (°C)", yaxis="y2"))
    fig.update_layout(template="plotly_white", height=420,
                      title="Rekap sesi pengujian",
                      yaxis=dict(title="CO (ppm)"),
                      yaxis2=dict(title="Suhu (°C)", overlaying="y", side="right"))
    fig.show()

    from google.colab import files
    files.download(nama)
else:
    print("Belum ada data.")
""")

nb = {
    "cells": CELLS,
    "metadata": {
        "colab": {"provenance": [], "toc_visible": True},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 0,
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.join(ROOT, "dashboard", "cozero_dashboard_colab.ipynb")
with open(out, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
    f.write("\n")
print("Notebook dibuat:", out)
