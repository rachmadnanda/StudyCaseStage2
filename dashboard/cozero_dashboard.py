#!/usr/bin/env python3
"""
CO-Zero Dashboard - Monitoring CO Kabin Mobil
Samsung Innovation Campus Batch 8 - Stage 2
Tim Iki jenenge wes wkwk - Politeknik Negeri Malang

Menerima data telemetri dari ESP32 (Wokwi) melalui MQTT HiveMQ Cloud,
menampilkan grafik real-time (Matplotlib), dan menyimpan log ke CSV.

Jalankan:
    python cozero_dashboard.py --host xxxx.s1.eu.hivemq.cloud \
                               --user cozero --password RAHASIA

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
# Konfigurasi default (boleh diubah lewat argumen CLI)
# ----------------------------------------------------------------------------
DEFAULT_HOST = "xxxxxxxxxxxx.s1.eu.hivemq.cloud"
DEFAULT_PORT = 8883
DEFAULT_USER = "ISI_USERNAME_HIVEMQ"
DEFAULT_PASS = "ISI_PASSWORD_HIVEMQ"
TOPIC_BASE = "cozero/team"
TOPIC_TELEMETRY = f"{TOPIC_BASE}/telemetry"
TOPIC_ALERT = f"{TOPIC_BASE}/alert"
TOPIC_STATUS = f"{TOPIC_BASE}/status"

# Ambang batas identik dengan firmware
TH_WASPADA = 20
TH_BAHAYA = 35
TH_KRITIS = 115

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
            ["timestamp", "device_id", "co_ppm", "temp_c", "rh", "level", "level_code"]
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
            state["alerts"].append(
                f"{datetime.now():%H:%M:%S}  {d.get('prev','?')} -> {d.get('level','?')} "
                f"({d.get('co_ppm', 0):.1f} ppm)"
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
    ts_buf.append(now)
    co_buf.append(float(d.get("co_ppm", 0.0)))
    temp_buf.append(float(d.get("temp_c", 0.0)))
    rh_buf.append(float(d.get("rh", 0.0)))

    state["level"] = d.get("level", "-")
    state["device"] = d.get("device_id", "-")
    state["last_seen"] = now

    if csv_writer:
        csv_writer.writerow(
            [
                now.isoformat(timespec="seconds"),
                d.get("device_id", ""),
                f"{d.get('co_ppm', 0):.1f}",
                f"{d.get('temp_c', 0):.1f}",
                f"{d.get('rh', 0):.1f}",
                d.get("level", ""),
                d.get("level_code", ""),
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

    ax_co.set_ylabel("CO (ppm)")
    ax_co.set_title("CO-Zero - Monitoring Kualitas Udara Kabin", fontsize=13, weight="bold")
    ax_co.grid(alpha=0.3)

    # zona ambang batas
    ax_co.axhspan(0, TH_WASPADA, color="#c8e6c9", alpha=0.55, label="AMAN (<20 ppm)")
    ax_co.axhspan(TH_WASPADA, TH_BAHAYA, color="#fff9c4", alpha=0.75, label="WASPADA (20-34)")
    ax_co.axhspan(TH_BAHAYA, TH_KRITIS, color="#ffe0b2", alpha=0.75, label="BAHAYA (35-114)")
    ax_co.axhspan(TH_KRITIS, 400, color="#ffcdd2", alpha=0.75, label="KRITIS (>=115)")
    ax_co.set_ylim(0, 200)
    ax_co.legend(loc="upper left", fontsize=8, ncol=2)

    (line_co,) = ax_co.plot([], [], color="#c62828", linewidth=1.8, label="CO")

    ax_env.set_ylabel("Suhu (C) / RH (%)")
    ax_env.set_xlabel("Waktu")
    ax_env.grid(alpha=0.3)
    (line_temp,) = ax_env.plot([], [], color="#1565c0", linewidth=1.4, label="Suhu (C)")
    (line_rh,) = ax_env.plot([], [], color="#00897b", linewidth=1.4, label="RH (%)")
    ax_env.legend(loc="upper left", fontsize=8, ncol=2)

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
    ax_env.relim()
    ax_env.autoscale_view(scalex=False, scaley=True)

    # geser jendela waktu
    last = x[-1]
    from datetime import timedelta

    ax_co.set_xlim(last - timedelta(seconds=WINDOW_SECONDS), last)
    ax_co.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))

    lvl = state["level"]
    status.set_text(f"Status: {lvl}   |   CO: {co_buf[-1]:.1f} ppm   |   Device: {state['device']}")
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

    if "xxxx" in args.host:
        print("!! Isi dulu --host / --user / --password dengan kredensial HiveMQ Cloud kamu.")
        print("   Contoh: python cozero_dashboard.py --host abc123.s1.eu.hivemq.cloud "
              "--user cozero --password Rahasia123")
        sys.exit(1)

    csv_path = args.csv or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data",
        f"cozero_{datetime.now():%Y%m%d_%H%M%S}.csv",
    )
    open_csv(csv_path)
    print(f"[CSV  ] Log disimpan ke: {os.path.abspath(csv_path)}")

    client = make_client()
    client.username_pw_set(args.user, args.password)
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
