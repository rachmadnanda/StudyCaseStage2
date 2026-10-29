#!/usr/bin/env python3
"""Membangun notebook Colab CO-Zero (cozero_dashboard_colab.ipynb)."""
import json
import os

CELLS = []


def md(text):
    CELLS.append({"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(True)})


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

Notebook ini berlangganan (subscribe) ke topik MQTT HiveMQ Cloud yang dipublikasikan
oleh ESP32 (Wokwi), lalu menampilkan dashboard real-time dengan **Plotly**.

### Alur data
`MQ-2 → ESP32 → WiFi → HiveMQ Cloud → notebook ini → grafik`

### Langkah
1. Jalankan cell **Instalasi**.
2. Isi kredensial HiveMQ Cloud pada cell **Konfigurasi**.
3. Jalankan cell **Koneksi** — tunggu sampai muncul `[MQTT] connected`.
4. Jalankan cell **Dashboard live** dan nyalakan simulasi Wokwi.
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
MQTT_HOST = "xxxxxxxxxxxx.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "ISI_USERNAME_HIVEMQ"
MQTT_PASS = "ISI_PASSWORD_HIVEMQ"

TOPIC_BASE      = "cozero/team"
TOPIC_TELEMETRY = TOPIC_BASE + "/telemetry"
TOPIC_ALERT     = TOPIC_BASE + "/alert"
TOPIC_STATUS    = TOPIC_BASE + "/status"

TH_WASPADA, TH_BAHAYA, TH_KRITIS = 20, 35, 115
LEVEL_COLOR = {"AMAN": "#2e7d32", "WASPADA": "#f9a825",
               "BAHAYA": "#ef6c00", "KRITIS": "#c62828"}

assert "xxxx" not in MQTT_HOST, "Isi dulu MQTT_HOST / MQTT_USER / MQTT_PASS"
print("Konfigurasi OK ->", MQTT_HOST)
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
                          f"{d.get('level')} ({d.get('co_ppm', 0):.1f} ppm)")
        except Exception:
            pass
        return

    try:
        d = json.loads(payload)
    except json.JSONDecodeError:
        return

    with _lock:
        rows.append({
            "waktu": datetime.now(),
            "device": d.get("device_id", "-"),
            "co_ppm": float(d.get("co_ppm", 0)),
            "temp_c": float(d.get("temp_c", 0)),
            "rh": float(d.get("rh", 0)),
            "level": d.get("level", "-"),
            "level_code": int(d.get("level_code", 0)),
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
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.tls_set(cert_reqs=ssl.CERT_NONE)
client.tls_insecure_set(True)
client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
client.loop_start()
time.sleep(2)
print("Menunggu data... (nyalakan simulasi Wokwi sekarang)")
""")

code(r"""
# ============================================================
#  Dashboard live (Plotly) — jalankan selama demo / rekam video
# ============================================================
def render(df):
    last = df.iloc[-1]
    warna = LEVEL_COLOR.get(last["level"], "gray")

    fig = go.Figure()

    # pita ambang batas
    fig.add_hrect(y0=0, y1=TH_WASPADA, fillcolor="#c8e6c9", opacity=0.45, line_width=0)
    fig.add_hrect(y0=TH_WASPADA, y1=TH_BAHAYA, fillcolor="#fff9c4", opacity=0.60, line_width=0)
    fig.add_hrect(y0=TH_BAHAYA, y1=TH_KRITIS, fillcolor="#ffe0b2", opacity=0.60, line_width=0)
    fig.add_hrect(y0=TH_KRITIS, y1=max(200, df.co_ppm.max() * 1.2),
                  fillcolor="#ffcdd2", opacity=0.60, line_width=0)

    fig.add_trace(go.Scatter(x=df.waktu, y=df.co_ppm, mode="lines+markers",
                             name="CO (ppm)", line=dict(color="#c62828", width=2)))

    fig.update_layout(
        title=dict(
            text=(f"<b>CO-Zero Dashboard</b> — status <span style='color:{warna}'>"
                  f"<b>{last['level']}</b></span> | {last['co_ppm']:.1f} ppm | "
                  f"{last['temp_c']:.1f} °C | {last['rh']:.0f} % RH"),
            x=0.5, xanchor="center"),
        xaxis_title="Waktu",
        yaxis_title="Konsentrasi CO (ppm)",
        yaxis=dict(range=[0, max(120, df.co_ppm.max() * 1.25)]),
        template="plotly_white",
        height=460,
        margin=dict(l=60, r=30, t=80, b=50),
        legend=dict(orientation="h", y=1.08),
    )
    fig.add_annotation(x=df.waktu.iloc[-1], y=last["co_ppm"],
                       text=f"{last['co_ppm']:.1f} ppm", showarrow=True,
                       arrowhead=2, ay=-30)
    return fig


DURASI = 90      # detik; ubah sesuai kebutuhan
for i in range(DURASI):
    with _lock:
        data = list(rows)

    if len(data) < 2:
        clear_output(wait=True)
        print(f"Menunggu data MQTT... ({i}/{DURASI})  online={status['online']}")
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
""")

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
print("Notebook dibuat:", out)
