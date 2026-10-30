#!/usr/bin/env python3
"""
CO-Zero Dashboard - Monitoring CO Kabin Mobil
Samsung Innovation Campus Batch 8 - Stage 2
Tim Iki jenenge wes wkwk - Politeknik Negeri Malang

Menerima data telemetri dari ESP32 (Wokwi) melalui MQTT (broker publik
EMQX secara default), menampilkan grafik real-time (Matplotlib), dan
menyimpan log ke CSV.

Kedua panel grafik menampilkan kadar CO pada sumbu logaritmik beserta pita
ambang batas, dan suhu/kelembapan kabin pada sumbu 0-100 dengan penanda
kondisi ekstrem. Nilai iklim mikro yang tidak valid ditampilkan sebagai celah
pada grafik, bukan sebagai garis mendatar di nol.

Pemakaian:
    python cozero_dashboard.py
    python cozero_dashboard.py --host broker.hivemq.com --port 1883
    python cozero_dashboard.py --host abc123.s1.eu.hivemq.cloud \
                               --user cozero --password RAHASIA

Port 8883 otomatis memakai TLS, port 1883 tanpa TLS. Username/password hanya
dikirim bila --user diisi (broker publik tidak memerlukannya).

Dependensi:
    pip install -r requirements.txt
"""

import argparse
import csv
import json
import os
import ssl
import sys
from collections import deque
from datetime import datetime

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

import paho.mqtt.client as mqtt

# ----------------------------------------------------------------------------
# Konfigurasi default (dapat diubah melalui argumen CLI)
# ----------------------------------------------------------------------------
DEFAULT_HOST = "broker.emqx.io"
DEFAULT_PORT = 8883
DEFAULT_USER = ""
DEFAULT_PASS = ""
TOPIC_BASE = "cozero/sic8-wkwk7"
TOPIC_TELEMETRY = f"{TOPIC_BASE}/telemetry"
TOPIC_ALERT = f"{TOPIC_BASE}/alert"
TOPIC_STATUS = f"{TOPIC_BASE}/status"

# Ambang batas identik dengan firmware
TH_WASPADA = 20
TH_BAHAYA = 35
TH_KRITIS = 115

TH_TEMP_PANAS = 40.0      # celsius
TH_RH_LEMBAB = 75.0       # %RH
TH_RH_KERING = 20.0       # %RH

MAX_POINTS = 600          # ~20 menit pada interval publish 2 detik
WINDOW_SECONDS = 120      # jendela tampilan grafik

LEVEL_COLOR = {
    "AMAN": "#2e7d32",
    "WASPADA": "#f9a825",
    "BAHAYA": "#ef6c00",
    "KRITIS": "#c62828",
}

# ----------------------------------------------------------------------------
# Penyimpanan data
# ----------------------------------------------------------------------------
ts_buf = deque(maxlen=MAX_POINTS)
co_buf = deque(maxlen=MAX_POINTS)
temp_buf = deque(maxlen=MAX_POINTS)
rh_buf = deque(maxlen=MAX_POINTS)

state = {
    "level": "-",
    "co_level": "-",
    "env": "-",
    "dht_ok": True,
    "device": "-",
    "last_seen": None,
    "online": False,
    "alerts": deque(maxlen=5),
}

csv_file = None
csv_writer = None


def open_csv(path):
    global csv_file, csv_writer
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    csv_file = open(path, "a", newline="")
    csv_writer = csv.writer(csv_file)
    if csv_file.tell() == 0:
        csv_writer.writerow(
            [
                "timestamp", "device_id", "co_ppm", "temp_c", "rh",
                "level", "level_code", "co_level", "env", "dht_ok",
            ]
        )


def make_client():
    client_id = f"cozero-dashboard-{os.getpid()}"
    try:
        # paho-mqtt >= 2.0
        return mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )
    except (AttributeError, TypeError):
        # paho-mqtt 1.x
        return mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)


# ----------------------------------------------------------------------------
# Callback MQTT (kompatibel paho 1.x dan 2.x)
# ----------------------------------------------------------------------------
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0 or str(rc) == "Success":
        print(f"[MQTT] Terhubung ke broker. Subscribe: {TOPIC_TELEMETRY}, {TOPIC_ALERT}")
        client.subscribe(TOPIC_TELEMETRY, qos=1)
        client.subscribe(TOPIC_ALERT, qos=1)
    else:
        print(f"[MQTT] Gagal terhubung, rc={rc}")


def on_disconnect(client, userdata, *args):
    print("[MQTT] Koneksi terputus, mencoba ulang...")


def on_message(client, userdata, msg):
    topic = msg.topic
    raw = msg.payload.decode("utf-8", errors="replace")

    if topic.endswith("/status"):
        state["online"] = "online" in raw
        print(f"[STATUS] {raw}")
        return

    if topic.endswith("/alert"):
        print(f"[ALERT ] {raw}")
        try:
            d = json.loads(raw)
            alasan = d.get("reason", "co")
            state["alerts"].append(
                f"{datetime.now():%H:%M:%S}  {d.get('prev','?')} -> {d.get('level','?')} "
                f"({d.get('co_ppm', 0):.2f} ppm, {alasan})"
            )
        except json.JSONDecodeError:
            pass
        return

    # telemetry
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[WARN] payload bukan JSON: {raw}")
        return

    now = datetime.now()
    dht_ok = bool(d.get("dht_ok", True))

    ts_buf.append(now)
    co_buf.append(float(d.get("co_ppm", 0.0)))
    # Nilai iklim mikro yang tidak valid dikirim sebagai NaN agar grafik
    # menampilkan celah, bukan garis mendatar di 0 C / 0 %RH.
    temp_buf.append(float(d.get("temp_c", 0.0)) if dht_ok else float("nan"))
    rh_buf.append(float(d.get("rh", 0.0)) if dht_ok else float("nan"))

    state["level"] = d.get("level", "-")
    state["co_level"] = d.get("co_level", "-")
    state["env"] = d.get("env", "NORMAL") if dht_ok else "-"
    state["dht_ok"] = dht_ok
    state["device"] = d.get("device_id", "-")
    state["last_seen"] = now

    if csv_writer:
        csv_writer.writerow(
            [
                now.isoformat(timespec="seconds"),
                d.get("device_id", ""),
                f"{d.get('co_ppm', 0):.2f}",
                f"{d.get('temp_c', 0):.1f}" if dht_ok else "",
                f"{d.get('rh', 0):.1f}" if dht_ok else "",
                d.get("level", ""),
                d.get("level_code", ""),
                d.get("co_level", ""),
                d.get("env", "") if dht_ok else "",
                "1" if dht_ok else "0",
            ]
        )
        csv_file.flush()


# ----------------------------------------------------------------------------
# Dashboard Matplotlib
# ----------------------------------------------------------------------------
def build_figure():
    fig, (ax_co, ax_env) = plt.subplots(
        2, 1, figsize=(11, 7), sharex=True,
        gridspec_kw={"height_ratios": [2.2, 1]},
    )
    fig.canvas.manager.set_window_title("CO-Zero Dashboard")

    ax_co.set_ylabel("CO (ppm, skala log)")
    ax_co.set_title("CO-Zero - Monitoring Kualitas Udara Kabin", fontsize=13, weight="bold")
    ax_co.grid(alpha=0.3, which="both")

    # Sumbu CO memakai skala logaritmik: keluaran sensor MQ-2 sendiri logaritmik,
    # dan rentang uji 0,1-570 ppm terlalu lebar untuk sumbu linear (pita AMAN
    # akan mengecil sampai tak terlihat). Batas 1000 ppm di atas titik jenuh ADC.
    CO_FLOOR, CO_CEIL = 0.1, 1000.0
    ax_co.set_yscale("log")
    ax_co.set_ylim(CO_FLOOR, CO_CEIL)

    # zona ambang batas
    ax_co.axhspan(CO_FLOOR, TH_WASPADA, color="#c8e6c9", alpha=0.55, label="AMAN (<20 ppm)")
    ax_co.axhspan(TH_WASPADA, TH_BAHAYA, color="#fff9c4", alpha=0.75, label="WASPADA (20-34)")
    ax_co.axhspan(TH_BAHAYA, TH_KRITIS, color="#ffe0b2", alpha=0.75, label="BAHAYA (35-114)")
    ax_co.axhspan(TH_KRITIS, CO_CEIL, color="#ffcdd2", alpha=0.75, label="KRITIS (>=115)")
    ax_co.legend(loc="upper left", fontsize=8, ncol=2)

    (line_co,) = ax_co.plot([], [], color="#c62828", linewidth=1.8, label="CO")

    ax_env.set_ylabel("Suhu (C) / RH (%)")
    ax_env.set_xlabel("Waktu")
    ax_env.grid(alpha=0.3)

    # Pita kondisi ekstrem. Suhu dan RH berbagi satu sumbu 0-100 agar kedua
    # ambang lingkungan langsung terlihat pada skala yang sama.
    ax_env.set_ylim(0, 100)
    ax_env.axhspan(TH_RH_LEMBAB, 100, color="#b3e5fc", alpha=0.55,
                   label=f"LEMBAB (>= {TH_RH_LEMBAB:.0f} %RH)")
    ax_env.axhspan(0, TH_RH_KERING, color="#d7ccc8", alpha=0.55,
                   label=f"KERING (<= {TH_RH_KERING:.0f} %RH)")
    ax_env.axhline(TH_TEMP_PANAS, color="#d84315", linestyle="--", linewidth=1.2,
                   label=f"PANAS (>= {TH_TEMP_PANAS:.0f} C)")

    (line_temp,) = ax_env.plot([], [], color="#1565c0", linewidth=1.4, label="Suhu (C)")
    (line_rh,) = ax_env.plot([], [], color="#00897b", linewidth=1.4, label="RH (%)")
    ax_env.legend(loc="upper left", fontsize=7, ncol=3)

    # format sumbu waktu
    locator = mdates.AutoDateLocator(minticks=4, maxticks=9)
    ax_env.xaxis.set_major_locator(locator)
    ax_env.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))

    fig.autofmt_xdate()
    fig.tight_layout(rect=(0, 0, 1, 0.94))

    status = fig.text(0.5, 0.965, "Menunggu data...", ha="center", fontsize=12, weight="bold")

    return fig, ax_co, ax_env, line_co, line_temp, line_rh, status


def update(frame, ax_co, ax_env, line_co, line_temp, line_rh, status):
    if not ts_buf:
        status.set_text("Menunggu data MQTT...")
        status.set_color("gray")
        return line_co, line_temp, line_rh, status

    x = list(ts_buf)

    line_co.set_data(x, list(co_buf))
    line_temp.set_data(x, list(temp_buf))
    line_rh.set_data(x, list(rh_buf))

    ax_co.relim()
    ax_co.autoscale_view(scalex=False, scaley=False)
    # Sumbu lingkungan dikunci 0-100 agar pita ambang tetap terbaca.

    # geser jendela waktu
    last = x[-1]
    from datetime import timedelta

    ax_co.set_xlim(last - timedelta(seconds=WINDOW_SECONDS), last)
    ax_co.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))

    lvl = state["level"]
    co_lvl = state["co_level"]
    env = state["env"]
    if state["dht_ok"]:
        status.set_text(
            f"Status: {lvl}   |   CO: {co_buf[-1]:.2f} ppm ({co_lvl})"
            f"   |   Iklim: {env}   |   Device: {state['device']}"
        )
    else:
        status.set_text(
            f"Status: {lvl}   |   CO: {co_buf[-1]:.2f} ppm ({co_lvl})"
            f"   |   Iklim: DHT22 tidak terbaca   |   Device: {state['device']}"
        )
    status.set_color(LEVEL_COLOR.get(lvl, "black"))

    if state["alerts"]:
        ax_co.set_xlabel("Alert terakhir: " + state["alerts"][-1], fontsize=8, color="#c62828")
    else:
        ax_co.set_xlabel("")

    return line_co, line_temp, line_rh, status


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="CO-Zero MQTT Dashboard")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASS)
    parser.add_argument("--csv", default=None, help="path file log CSV")
    parser.add_argument("--no-plot", action="store_true", help="hanya log ke terminal/CSV")
    args = parser.parse_args()

    if not args.host or "xxxx" in args.host:
        print("!! Argumen --host belum diisi.")
        print("   Broker publik: python cozero_dashboard.py --host broker.emqx.io --port 8883")
        print("   HiveMQ Cloud : tambahkan --user <user> --password <pass>")
        sys.exit(1)

    csv_path = args.csv or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data",
        f"cozero_{datetime.now():%Y%m%d_%H%M%S}.csv",
    )
    open_csv(csv_path)
    print(f"[CSV  ] Log disimpan ke: {os.path.abspath(csv_path)}")

    client = make_client()
    if args.user:
        client.username_pw_set(args.user, args.password)
    if args.port == 8883:
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    print(f"[MQTT ] Menghubungkan ke {args.host}:{args.port} ...")
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()

    if args.no_plot:
        try:
            while True:
                import time

                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        fig, ax_co, ax_env, lc, lt, lr, st = build_figure()
        ani = FuncAnimation(
            fig, update, fargs=(ax_co, ax_env, lc, lt, lr, st),
            interval=1000, blit=False, cache_frame_data=False,
        )
        plt.show()

    client.loop_stop()
    client.disconnect()
    if csv_file:
        csv_file.close()
    print("[DONE ] Dashboard ditutup.")


if __name__ == "__main__":
    main()
