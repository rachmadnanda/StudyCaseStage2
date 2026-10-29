# CO-Zero — Monitoring & Peringatan Dini CO Kabin Mobil

**Samsung Innovation Campus Batch 8 — Stage 2 (IoT: Device & Hardware Discovery)**
Tim **Iki jenenge wes wkwk** · Politeknik Negeri Malang

> Detektor karbon monoksida (CO) kabin mobil berbasis ESP32: membaca kadar CO dan iklim
> mikro kabin, memberi peringatan lokal (LED + buzzer + OLED), mengirim data lewat MQTT
> ke HiveMQ Cloud, dan menampilkannya pada dashboard Python.

---

## 1. Isi Folder

```
StudyCaseStage2/
├── README.md                        ← file ini (mulai dari sini)
├── firmware/
│   ├── cozero_esp32.ino             ← sketch ESP32 lengkap (siap tempel ke Wokwi)
│   ├── diagram.json                 ← rangkaian Wokwi (import langsung)
│   └── libraries.txt                ← daftar library Wokwi
├── dashboard/
│   ├── cozero_dashboard.py          ← dashboard Matplotlib (lokal)
│   ├── cozero_dashboard_colab.ipynb ← dashboard Plotly (Google Colab)
│   └── requirements.txt
├── testing/
│   └── test-scenarios.md            ← 8 skenario uji + daftar screenshot
├── docs/
│   ├── laporan.md                   ← isi laporan lengkap (sumber)
│   ├── Laporan-CO-Zero-SIC8.docx    ← laporan siap kumpul
│   └── video-script.md              ← skrip + shot list video demo
└── tools/
    ├── build_laporan.py             ← generate .docx dari laporan.md
    ├── build_notebook.py            ← generate notebook Colab
    ├── calibrate.py                 ← hitung konstanta kalibrasi 2 titik
    └── test_logic.py                ← uji unit logika ambang batas (21 assertion)
```

---

## 2. Arsitektur Singkat

```
        ┌──────────┐   analog   ┌───────────────┐   I2C    ┌──────────┐
        │  MQ-2    │───────────▶│               │─────────▶│  OLED    │
        └──────────┘  GPIO34    │               │          └──────────┘
        ┌──────────┐            │     ESP32     │   GPIO   ┌──────────┐
        │  DHT22   │───────────▶│  rule-based   │─────────▶│ LED x3   │
        └──────────┘   GPIO4    │     logic     │          └──────────┘
                                 │               │   PWM    ┌──────────┐
                                 │               │─────────▶│  Buzzer  │
                                 └───────┬───────┘          └──────────┘
                                         │ WiFi + MQTT/TLS
                                         ▼
                                 ┌───────────────┐
                                 │ HiveMQ Cloud  │
                                 └───────┬───────┘
                                         │ subscribe
                                         ▼
                                 ┌────────────────┐
                                 │ Python + Plotly│
                                 └────────────────┘
```

---

## 3. Pin / GPIO

| Komponen | Pin komponen | Pin ESP32 | GPIO | Fungsi |
|---|---|---|---|---|
| MQ-2 | VCC | VIN | — | 5 V (heater sensor butuh 5 V) |
| MQ-2 | GND | GND.2 | — | Ground |
| MQ-2 | AOUT | D34 | GPIO34 | ADC1_CH6, input-only |
| MQ-2 | DOUT | D32 | GPIO32 | Deteksi ambang digital (redundan) |
| DHT22 | SDA | D4 | GPIO4 | Data one-wire |
| DHT22 | VCC / GND | 3V3 / GND.1 | — | Catu 3,3 V |
| OLED SSD1306 | SDA | D21 | GPIO21 | I2C SDA (default) |
| OLED SSD1306 | SCL | D22 | GPIO22 | I2C SCL (default) |
| Buzzer | 2 (+) | D25 | GPIO25 | Output tone |
| LED hijau | A (via 220 Ω) | D26 | GPIO26 | Indikator AMAN |
| LED kuning | A (via 220 Ω) | D27 | GPIO27 | Indikator WASPADA |
| LED merah | A (via 220 Ω) | D14 | GPIO14 | Indikator BAHAYA / KRITIS |

> **Catatan penting (pembagi tegangan).** Pada perangkat fisik, keluaran analog MQ-2/MQ-7
> dapat mencapai ±5 V sedangkan ADC ESP32 maksimum 3,3 V, sehingga **wajib** dipasang
> pembagi tegangan R1 = 10 kΩ (seri) dan R2 = 10 kΩ (ke GND) di jalur AOUT → GPIO34.
> Wokwi hanya mendukung simulasi analog sederhana dan **tidak bisa** mengombinasikan
> resistor dengan komponen analog, sehingga pada simulasi AOUT dihubungkan langsung ke
> GPIO34 dan `DIVIDER_RATIO` disetel **1.0**. Untuk implementasi nyata, ubah konstanta
> tersebut menjadi **2.0**.

---

## 4. Logika Ambang Batas

| Level | Kadar CO | LED | Buzzer |
|---|---|---|---|
| AMAN | < 20 ppm | hijau | mati |
| WASPADA | 20 – 34 ppm | kuning | beep 1 Hz (120 ms) |
| BAHAYA | 35 – 114 ppm | merah | beep 2,5 Hz (150 ms) |
| KRITIS | ≥ 115 ppm | merah | kontinu 2 kHz |

- **Moving average 5 sampel** → menstabilkan pembacaan ADC.
- **Histeresis 3 ppm** → level baru turun setelah nilai berada pada/ di bawah 3 ppm di
  bawah ambang, sehingga LED tidak berkedip saat nilai berada tepat di batas.
- **DOUT MQ-2** dipakai sebagai jalur redundan: bila keluaran digital aktif (LOW) **dan**
  pembacaan analog sudah mencapai WASPADA, level dinaikkan minimal ke BAHAYA. Di Wokwi
  `threshold` disetel 4,0 V sehingga komparator baru aktif di atas kisaran pengujian.

---

## 5. Langkah Menjalankan

### 5.1 Buat cluster HiveMQ Cloud (gratis, ±5 menit)

1. Buka <https://console.hivemq.cloud> → **Sign up** → buat cluster **Free**.
2. Catat **Cluster URL**, contoh: `abc123def.s1.eu.hivemq.cloud`.
3. Masuk tab **Access Management** → **Add credentials** → buat username & password
   (role *Publish & Subscribe*). Catat keduanya.
4. Port yang dipakai ESP32: **8883** (TLS).

### 5.2 Buat project Wokwi

1. Buka <https://wokwi.com/projects/new/esp32> → pilih **ESP32 DevKit V1**.
2. Tab **diagram.json** → ganti seluruh isinya dengan isi `firmware/diagram.json`.
3. Tab **sketch.ino** → ganti seluruh isinya dengan isi `firmware/cozero_esp32.ino`.
4. Tambahkan file **libraries.txt** (tombol `+` di panel file) → isi dengan isi
   `firmware/libraries.txt`.
5. Di `sketch.ino` bagian **KONFIGURASI**, isi:
   ```c
   #define MQTT_HOST  "abc123def.s1.eu.hivemq.cloud"
   #define MQTT_USER  "cozero"
   #define MQTT_PASS  "passwordmu"
   ```
6. Tekan ▶ **Start Simulation**. Buka **Serial Monitor** (baud 115200).

### 5.3 Verifikasi cepat

Serial Monitor akan menampilkan:

```
==============================================
  CO-Zero v1.0 | Tim Iki jenenge wes wkwk
  Monitoring CO Kabin Mobil - SIC Batch 8
==============================================
[CAL] Skala awal: 200.0 ppm/V, baseline 0.000 V
[CAL] Butuh kalibrasi? Geser slider lalu ketik: c1 <ppm>, c2 <ppm>, ?
[WiFi] Menghubungkan ke Wokwi-GUEST ...
[MQTT] Connect ke abc123def.s1.eu.hivemq.cloud:8883 ... OK
[  3210 ms] CO=   0.4 ppm (raw=   2 Vout=0.00V dout=1) | 29.0C 61% | AMAN
```

Jika `MQTT ... GAGAL`, cek username/password dan pastikan cluster aktif.
Jika angka CO tidak cocok dengan slider, lakukan **kalibrasi bagian 7** (30 detik).

### 5.4 Dashboard

**Opsi A — Google Colab (disarankan untuk screenshot):**
1. Buka <https://colab.research.google.com> → **Upload** →
   `dashboard/cozero_dashboard_colab.ipynb`.
2. Isi `MQTT_HOST`, `MQTT_USER`, `MQTT_PASS` pada cell *Konfigurasi*.
3. Jalankan semua cell berurutan.

**Opsi B — lokal:**
```bash
cd dashboard
pip install -r requirements.txt
python cozero_dashboard.py --host abc123def.s1.eu.hivemq.cloud \
                           --user cozero --password passwordmu
```
Log CSV otomatis tersimpan di `data/cozero_<tanggal>.csv`.

---

## 6. Topik & Payload MQTT

| Topik | Arah | Retain | Isi |
|---|---|---|---|
| `cozero/team/telemetry` | device → dashboard | tidak | data sensor tiap 2 detik |
| `cozero/team/alert` | device → dashboard | tidak | dikirim saat level berubah |
| `cozero/team/status` | device → dashboard | **ya** | `online` / `offline` (LWT) |

Contoh payload telemetri:

```json
{
  "device_id": "COZERO-01",
  "co_ppm": 18.5,
  "temp_c": 29.4,
  "rh": 61.2,
  "level": "AMAN",
  "level_code": 0,
  "raw": 77,
  "volt": 0.06,
  "dout": 1,
  "uptime_s": 42
}
```

---

## 7. Kalibrasi Skala ppm (30 detik, sekali saja)

Firmware memakai pemetaan linear:

```
ppm = (Vout - baseline) × ppmPerVolt        (default: 200 ppm/V, baseline 0 V)
```

Kalibrasi dilakukan **saat simulasi berjalan**, langsung dari Serial Monitor — tidak perlu
mengubah kode:

1. Geser slider ppm sensor MQ-2 ke **100**, tunggu 2 detik.
2. Ketik di Serial Monitor: `c1 100` → Enter.
3. Geser slider ke **500**, tunggu 2 detik.
4. Ketik: `c2 500` → Enter. Firmware mencetak hasilnya:
   ```
   [CAL] Selesai -> ppmPerVolt = 200.00 | baseline = 0.0000 V
   ```
5. Ketik `?` untuk melihat status, `r` untuk kembali ke default.

Nilai tersebut hanya tersimpan di RAM (hilang saat simulasi di-restart). Kalau ingin
permanen, salin ke bagian KONFIGURASI:

```c
#define PPM_PER_VOLT_DEFAULT  200.00f
#define BASELINE_VOLT_DEFAULT 0.0000f
```

Alternatif: hitung di luar simulasi dengan `python tools/calibrate.py` bila kamu sudah
mencatat dua pasangan ppm–volt.

> Kalau kamu tidak melakukan kalibrasi, sistem tetap berfungsi: level akan tetap naik
> bertahap AMAN → WASPADA → BAHAYA → KRITIS mengikuti slider, hanya angka ppm-nya yang
> bisa berbeda dari nilai slider.
>
> **Batas ADC.** Tanpa pembagi tegangan, ADC ESP32 jenuh di sekitar 3,1–3,3 V. Karena itu
> titik kalibrasi dipilih **100 dan 500 ppm**, bukan 900, agar kedua pengukuran masih di
> dalam rentang linear. Untuk pengujian di atas ±600 ppm (mis. TC-04 pada 570 ppm), nilai
> masih terbaca; di atas itu barulah ADC mulai jenuh.
>
> Kalibrasi ini murni kompensasi simulator. Pada hardware asli, MQ-7/MQ-2 memakai kurva
> logaritmik Rs/R0 sesuai datasheet (lihat bagian *Pengembangan Lanjutan* di laporan).

---

## 8. Troubleshooting

| Gejala | Penyebab umum | Solusi |
|---|---|---|
| `MQTT GAGAL (rc=-2)` | host/port salah atau TLS gagal | pastikan port **8883**, host tanpa `https://` |
| `MQTT GAGAL (rc=4/5)` | username/password salah | buat ulang credential di HiveMQ |
| OLED blank | alamat I2C beda | ganti `0x3C` → `0x3D` pada `oled.begin()` |
| `DHT gagal baca` | library salah | gunakan **DHT sensor library for ESPx**, bukan DHT.h biasa |
| ppm selalu 0 | baseline terlalu besar / skala terlalu kecil | lakukan kalibrasi `c1` / `c2` (bagian 7) |
| Level tidak pernah KRITIS | skala ppm terlalu kecil | kalibrasi, atau cek slider sudah di 570 |
| Angka ppm tidak sama dengan slider | skala belum dikalibrasi | jalankan `c1` / `c2` sekali, lalu salin hasilnya ke sketch |
| Buzzer tidak bunyi | volume 0 | atribut `volume` pada `diagram.json` sudah 0.1 → naikkan ke 1.0 |
| Compile error `tone()` | core ESP32 sangat lama | gunakan core 3.x (default Wokwi) |

---

## 9. Catatan MQ-2 sebagai Pengganti MQ-7

Wokwi tidak menyediakan MQ-7. Simulasi memakai **MQ-2** yang juga sensitif terhadap CO.
Keduanya merupakan sensor semikonduktor oksida logam (MOS) berbasis heater dengan
keluaran analog, sehingga:

- arsitektur sistem, logika ambang batas, dan kebutuhan pembagi tegangan **tidak berubah**;
- yang berbeda hanya kurva sensitivitas dan selektivitas gas.

Pada implementasi fisik, **MQ-7** tetap menjadi pilihan utama karena selektivitas CO lebih
tinggi (MQ-2 lebih sensitif ke LPG/asap). Pernyataan ini wajib dicantumkan pada laporan
dan narasi video.

---

## 10. Checklist Sebelum Submit

- [ ] Wokwi project berjalan tanpa error, Serial Monitor menampilkan data
- [ ] Payload MQTT terverifikasi di HiveMQ Web Client
- [ ] Dashboard menampilkan grafik (screenshot)
- [ ] Minimal 3 skenario uji terisi di `testing/test-scenarios.md`
- [ ] Screenshot `SS-01` … `SS-08` tersimpan di `docs/img/`
- [ ] Laporan `.docx` sudah diisi nama tim & anggota
- [ ] Video demo `.mp4` sudah direkam
- [ ] Link Wokwi di-set **public/unlisted** lalu disalin ke laporan
