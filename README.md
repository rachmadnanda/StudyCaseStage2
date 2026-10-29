# CO-Zero — Monitoring & Peringatan Dini CO Kabin Mobil

**Samsung Innovation Campus Batch 8 — Stage 2 (IoT: Device & Hardware Discovery)**
Tim **Iki jenenge wes wkwk** · Politeknik Negeri Malang

> Detektor karbon monoksida (CO) kabin mobil berbasis ESP32. Perangkat membaca kadar CO
> beserta suhu dan kelembapan kabin, memberi peringatan lokal melalui OLED dan buzzer,
> mengirim data melalui MQTT ke HiveMQ Cloud, dan menampilkannya pada dashboard Python.

---

## 1. Isi Folder

```
StudyCaseStage2/
├── README.md                        ← file ini (titik awal dokumentasi)
├── firmware/
│   ├── cozero_esp32.ino             ← sketch ESP32 lengkap (siap disalin ke Wokwi)
│   ├── diagram.json                 ← rangkaian Wokwi (import langsung)
│   └── libraries.txt                ← daftar library Wokwi
├── dashboard/
│   ├── cozero_dashboard.py          ← dashboard Matplotlib (lokal)
│   ├── cozero_dashboard_colab.ipynb ← dashboard Plotly (Google Colab)
│   └── requirements.txt
├── testing/
│   └── test-scenarios.md            ← 10 skenario uji + daftar tangkapan layar
├── docs/
│   ├── laporan.md                   ← isi laporan lengkap (sumber)
│   ├── Laporan-CO-Zero-SIC8.docx    ← laporan siap dikumpulkan
│   └── video-script.md              ← skrip + shot list video demo
└── tools/
    ├── build_laporan.py             ← menghasilkan .docx dari laporan.md
    ├── build_notebook.py            ← menghasilkan notebook Colab
    ├── calibrate.py                 ← menghitung konstanta kalibrasi dua titik
    └── test_logic.py                ← uji unit logika (60 assertion)
```

---

## 2. Arsitektur Singkat

```
INPUT / SENSING             PROCESSING / LOGIC              OUTPUT / ACTUATION
+----------------+          +--------------------+          +-------------------+
|  MQ-2 (CO)     |          |                    |          |  OLED SSD1306     |
|  AOUT -> GPIO34|--------->|                    |--I2C---->|  level, ppm, bar, |
|  DOUT -> GPIO32|          |  ESP32             |          |  suhu, RH, flag   |
+----------------+          |                    |          +-------------------+
+----------------+          |  - moving average  |          +-------------------+
|  DHT22 (T/RH)  |          |  - ambang CO       |          |  Buzzer           |
|  SDA  -> GPIO4 |--------->|  - ambang iklim    |--GPIO25->|  beep per level   |
+----------------+          |  - histeresis      |          +-------------------+
                            +---------+----------+
                                      |
                                      | Serial (debug)
                                      v
                           +---------------------+
                           |  Serial Monitor     |
                           +---------------------+
                                      |
                                      | WiFi + MQTT/TLS (8883)
                                      v
                           +---------------------+
                           |  HiveMQ Cloud       |
                           +---------------------+
                                      |
                                      | subscribe
                                      v
                           +---------------------+
                           |  Python Dashboard   |
                           |  paho-mqtt + Plotly |
                           +---------------------+
```

Keputusan sistem diambil pada dua lapis. **Lapis pertama** menilai kadar CO dan
menghasilkan level CO. **Lapis kedua** menilai suhu dan kelembapan kabin, lalu
memperberat level CO bila kondisi lingkungan ekstrem. Rincian aturan terdapat pada
bagian 4.

---

## 3. Pin / GPIO

| Komponen | Pin komponen | Pin ESP32 | GPIO | Fungsi |
|---|---|---|---|---|
| MQ-2 | VCC | VIN | — | 5 V (heater sensor membutuhkan 5 V) |
| MQ-2 | GND | GND.2 | — | Ground |
| MQ-2 | AOUT | D34 | GPIO34 | ADC1_CH6, input-only |
| MQ-2 | DOUT | D32 | GPIO32 | Deteksi ambang digital (redundan) |
| DHT22 | SDA | D4 | GPIO4 | Data satu kabel |
| DHT22 | VCC / GND | 3V3 / GND.1 | — | Catu 3,3 V |
| OLED SSD1306 | SDA | D21 | GPIO21 | I2C SDA (default) |
| OLED SSD1306 | SCL | D22 | GPIO22 | I2C SCL (default) |
| Buzzer | 2 (+) | D25 | GPIO25 | Output tone |

> **Pembagi tegangan.** Pada perangkat fisik, keluaran analog MQ-2/MQ-7 dapat mencapai
> ±5 V sedangkan ADC ESP32 dibatasi 3,3 V, sehingga pembagi tegangan R1 = 10 kΩ (seri)
> dan R2 = 10 kΩ (ke GND) wajib dipasang pada jalur AOUT → GPIO34. Wokwi hanya
> mendukung simulasi analog sederhana dan tidak dapat mengombinasikan resistor dengan
> komponen analog, sehingga pada simulasi AOUT dihubungkan langsung ke GPIO34 dan
> `DIVIDER_RATIO` ditetapkan **1.0**. Untuk implementasi nyata, konstanta tersebut
> diubah menjadi **2.0**.

---

## 4. Logika Ambang Batas

### 4.1 Level dari kadar CO

| Level | Kadar CO | OLED | Buzzer |
|---|---|---|---|
| AMAN | < 20 ppm | `AMAN` (teks normal) | mati |
| WASPADA | 20 – 34 ppm | `WASPADA` (teks normal) | beep 1 Hz (120 ms) |
| BAHAYA | 35 – 114 ppm | `BAHAYA` (pita dibalik) | beep 2,5 Hz (150 ms) |
| KRITIS | ≥ 115 ppm | `KRITIS` (pita dibalik) | kontinu 2 kHz |

- **Moving average 5 sampel** menstabilkan pembacaan ADC.
- **Fast-track** membuang riwayat rata-rata bila nilai melompat lebih dari 40 ppm atau
  lebih dari 30% nilai saat ini, sehingga tampilan langsung mengikuti nilai terbaru.
- **Histeresis 3 ppm** menahan penurunan level sampai nilai berada pada atau di bawah
  3 ppm di bawah ambang, sehingga buzzer tidak berkedip saat nilai berada tepat di batas.
- **DOUT MQ-2** dipakai sebagai jalur redundan: level dinaikkan minimal ke BAHAYA hanya
  bila keluaran digital aktif (LOW) **dan** tegangan AOUT sudah melewati ambang
  komparator (`DOUT_THRESHOLD_V` = 4,0 V) **dan** pembacaan analog mencapai WASPADA.
  Syarat tegangan mencegah DOUT yang mengambang akibat kabel lepas memicu BAHAYA palsu.

### 4.2 Flag kondisi iklim mikro

Suhu dan kelembapan **tidak** menentukan level secara mandiri. Keduanya hanya
menghasilkan flag lingkungan:

| Flag | Kondisi | Alasan |
|---|---|---|
| `PANAS` | suhu ≥ 40,0 °C | Beban panas menambah risiko hipoksia |
| `LEMBAB` | RH ≥ 75 %RH | Penguapan keringat terhambat; lazim pada kabin tertutup |
| `KERING` | RH ≤ 20 %RH | Iritasi saluran napas |
| `NORMAL` | di luar semua kondisi di atas | — |

Bila suhu dan kelembapan sama-sama ekstrem, `PANAS` diprioritaskan. Deadband 1 °C dan
3 %RH diterapkan agar flag tidak berkedip di sekitar ambang. Jika DHT22 gagal dibaca,
flag dipaksa `NORMAL` sehingga kegagalan sensor tidak memicu eskalasi palsu.

### 4.3 Matriks eskalasi

| Level CO | Kondisi lingkungan | Level akhir |
|---|---|---|
| AMAN | NORMAL | AMAN |
| AMAN | ekstrem | WASPADA |
| WASPADA | NORMAL | WASPADA |
| WASPADA | ekstrem | **BAHAYA** |
| BAHAYA | NORMAL | BAHAYA |
| BAHAYA | ekstrem | **KRITIS** |
| KRITIS | apa pun | KRITIS |

Eskalasi dibatasi **satu tingkat** per keputusan. Kondisi lingkungan ekstrem sendirian
tidak pernah menghasilkan BAHAYA atau KRITIS; hanya kadar CO yang dapat mencapainya.
Dasar pertimbangannya: suhu tinggi menambah beban kardiovaskular sehingga tubuh lebih
cepat kekurangan oksigen, sedangkan kelembapan tinggi menghambat penguapan keringat dan
lazim menyertai kabin tertutup dengan sirkulasi resirkulasi.

---

## 5. Langkah Menjalankan

### 5.1 Membuat cluster HiveMQ Cloud (gratis, ±5 menit)

1. Buka <https://console.hivemq.cloud> → **Sign up** → buat cluster **Free**.
2. Catat **Cluster URL**, contoh: `abc123def.s1.eu.hivemq.cloud`.
3. Masuk tab **Access Management** → **Add credentials** → buat username dan password
   dengan role *Publish & Subscribe*. Catat keduanya.
4. Port yang dipakai ESP32 adalah **8883** (TLS).

### 5.2 Membuat project Wokwi

1. Buka <https://wokwi.com/projects/new/esp32> → pilih **ESP32 DevKit V1**.
2. Tab **diagram.json** → **Ctrl+A**, **Delete**, lalu tempelkan seluruh isi
   `firmware/diagram.json` → **Save**.
   Rangkaian hanya berisi **5 komponen**: ESP32, MQ-2, DHT22, OLED SSD1306, dan buzzer,
   tanpa LED dan tanpa resistor agar wiring seminimal mungkin.
3. Tab **sketch.ino** → ganti seluruh isinya dengan isi `firmware/cozero_esp32.ino`.
4. Tambahkan file **libraries.txt** (tombol `+` pada panel file) → isi dengan isi
   `firmware/libraries.txt`.
5. Pada `sketch.ino` bagian **KONFIGURASI**, isi kredensial:
   ```c
   #define MQTT_HOST  "abc123def.s1.eu.hivemq.cloud"
   #define MQTT_USER  "cozero"
   #define MQTT_PASS  "password_cluster"
   ```
6. Tekan ▶ **Start Simulation**, lalu buka **Serial Monitor** (baud 115200).

> **Penyambungan kabel dilakukan melalui `diagram.json`, bukan dengan drag pada kanvas.**
> Sambungan yang dibuat dengan drag terlepas saat tombol mouse dilepas, dan setiap pin
> hanya menerima satu kabel.

### 5.3 Verifikasi cepat

Serial Monitor akan menampilkan:

```
==============================================
  CO-Zero v1.0 | Tim Iki jenenge wes wkwk
  Monitoring CO Kabin Mobil - SIC Batch 8
==============================================
[DHT] Uji awal sensor (maksimum 3 percobaan)...
[DHT] Percobaan 1/3: OK -> 29.0 C, 61.0 %RH
[CAL] Skala log: 0.6836 V/dekade, 1 ppm = 1.3629 V
[CAL] Kalibrasi: c1 <ppm>, c2 <ppm>, ? | Diagnosa: dht
[INFO] Kolom: CO=ppm i=instan raw=ADC V=volt d=DOUT
[INFO] Contoh: ... | 29.0C 61.0%RH NORMAL | AMAN->AMAN
[WiFi] Menghubungkan ke Wokwi-GUEST ...
[MQTT] Connect ke abc123def.s1.eu.hivemq.cloud:8883 ... OK
[  3210 ms] CO=  0.10 i=  0.10 raw= 843 V=0.679 d=1 | 29.0C 61.0%RH NORMAL | AMAN->AMAN
```

Baris terakhir memuat seluruh informasi keputusan: nilai ppm hasil pengolahan (`CO`),
nilai sesaat sebelum dirata-rata (`i`), ADC mentah (`raw`), tegangan sensor (`V`), status
DOUT (`d`), suhu dan kelembapan beserta flag lingkungan, lalu level CO dan level akhir
yang dipisahkan tanda `->`.

Jika muncul `MQTT ... GAGAL`, periksa username dan password serta pastikan cluster aktif.
Jika angka CO tidak sesuai dengan slider, lakukan kalibrasi pada bagian 7.

### 5.4 Dashboard

**Opsi A — Google Colab (disarankan untuk tangkapan layar):**
1. Buka <https://colab.research.google.com> → **Upload** →
   `dashboard/cozero_dashboard_colab.ipynb`.
2. Isi `MQTT_HOST`, `MQTT_USER`, dan `MQTT_PASS` pada cell *Konfigurasi*.
3. Jalankan seluruh cell secara berurutan.

**Opsi B — lokal:**
```bash
cd dashboard
pip install -r requirements.txt
python cozero_dashboard.py --host abc123def.s1.eu.hivemq.cloud \
                           --user cozero --password password_cluster
```
Log CSV tersimpan otomatis di `data/cozero_<tanggal>.csv`.

Dashboard menampilkan dua panel. Panel atas berisi tren CO pada sumbu logaritmik beserta
pita ambang AMAN, WASPADA, BAHAYA, dan KRITIS. Panel bawah berisi suhu dan kelembapan
pada sumbu 0–100, lengkap dengan pita `LEMBAB`/`KERING` dan garis putus-putus `PANAS`
sehingga hubungan antara kondisi kabin dan kenaikan level dapat dibaca langsung.

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
  "co_ppm": 25.40,
  "temp_c": 41.2,
  "rh": 62.0,
  "dht_ok": true,
  "level": "BAHAYA",
  "level_code": 2,
  "co_level": "WASPADA",
  "env": "PANAS",
  "env_extreme": true,
  "raw": 2795,
  "volt": 2.252,
  "dout": 1,
  "uptime_s": 42
}
```

Pada contoh tersebut kadar CO 25,4 ppm sebenarnya hanya menghasilkan level WASPADA, tetapi
suhu kabin 41,2 °C mengeskalasi level akhir menjadi BAHAYA. Field `co_level` dan `env`
memungkinkan penerima menelusuri asal keputusan.

Contoh payload alert, yang menyertakan alasan transisi pada field `reason`
(`co`, `env`, atau `dout`):

```json
{
  "device_id": "COZERO-01",
  "prev": "WASPADA",
  "level": "BAHAYA",
  "reason": "env",
  "co_ppm": 25.40,
  "co_level": "WASPADA",
  "env": "PANAS",
  "uptime_s": 42
}
```

---

## 7. Kalibrasi Skala ppm (30 detik, sekali saja)

Keluaran sensor MQ-2 bersifat **logaritmik**, bukan linear: setiap kenaikan satu dekade
(10×) konsentrasi menaikkan Vout sekitar 0,68 V. Firmware memakai hubungan:

```
ppm = 10 ^ ((Vout − V_AT_1PPM) / V_PER_DECADE)
```

Nilai default berasal dari regresi tiga titik pengukuran langsung pada simulator:

| Slider | Vout | raw ADC |
|---|---|---|
| 0,1 ppm | 0,679 V | 843 |
| 3 ppm | 1,689 V | 2096 |
| 100.000 ppm | 3,257 V | 4041 *(ADC jenuh)* |

Hasil regresi: `V_PER_DECADE = 0,6836` dan `V_AT_1PPM = 1,3629`.

Kalibrasi dilakukan **saat simulasi berjalan** melalui Serial Monitor, tanpa mengubah
kode:

1. Slider ppm sensor MQ-2 digeser ke **10**, tunggu 2 detik.
2. Ketik `c1 10` → Enter.
3. Slider digeser ke **100**, tunggu 2 detik.
4. Ketik `c2 100` → Enter. Firmware mencetak hasilnya:
   ```
   [CAL] Selesai -> vPerDecade = 0.6836 | vAt1ppm = 1.3629 V
   ```
5. Ketik `?` untuk melihat status kalibrasi, atau `r` untuk kembali ke nilai default.

> Kedua titik acuan harus berjarak minimal satu dekade, misalnya 10 dan 100 ppm. Bila
> terlalu berdekatan, firmware menolak pasangan tersebut dan meminta titik yang lebih jauh.

Nilai hasil kalibrasi hanya tersimpan di RAM dan hilang saat simulasi dimulai ulang. Agar
berlaku permanen, kedua nilai disalin ke bagian KONFIGURASI:

```c
#define V_PER_DECADE_DEFAULT   0.6836f
#define V_AT_1PPM_DEFAULT      1.3629f
```

Alternatif lain adalah menghitung konstanta di luar simulasi dengan
`python tools/calibrate.py` berdasarkan dua pasangan ppm–volt yang telah dicatat.

> **Tanpa kalibrasi** sistem tetap berfungsi: level akan naik bertahap
> AMAN → WASPADA → BAHAYA → KRITIS mengikuti slider, sedangkan angka ppm dapat berbeda
> dari nilai slider.
>
> **Batas ADC.** Tanpa pembagi tegangan, ADC ESP32 jenuh pada 3,300 V yang setara ±682 ppm.
> Karena itu titik kalibrasi dipilih **10 dan 100 ppm**, jauh di bawah batas jenuh.
> Skenario TC-04 (570 ppm) berada pada 3,247 V sehingga masih terbaca sebelum jenuh.
>
> Kalibrasi ini murni kompensasi karakteristik simulator. Pada perangkat keras asli,
> MQ-7/MQ-2 memakai kurva Rs/R0 sesuai datasheet; bentuk logaritmiknya sama, hanya
> konstanta dan titik nolnya berbeda (lihat bagian *Pengembangan Lanjutan* pada laporan).

---

## 8. Troubleshooting

| Gejala | Penyebab umum | Solusi |
|---|---|---|
| `MQTT GAGAL (rc=-2)` | host/port salah atau TLS gagal | pastikan port **8883** dan host tanpa awalan `https://` |
| `MQTT GAGAL (rc=4/5)` | username/password salah | buat ulang credential pada HiveMQ |
| OLED blank | alamat I2C berbeda | ganti `0x3C` menjadi `0x3D` pada `oled.begin()` |
| `[DHT] Percobaan 1/3: TIMEOUT` | jalur data DHT22 tidak merespons | periksa ketiga kabel pada `diagram.json`: `VCC→3V3`, `SDA→D4`, `GND→GND.1`; pastikan SDA tidak terpasang pada pad `NC` |
| `[DHT] Gagal baca: CHECKSUM` | data terbalik saat transmisi | firmware mengulang otomatis setiap 2,2 detik; bila berlanjut, pindahkan `PIN_DHT` ke GPIO15 |
| OLED menampilkan `--.-C  --%RH  NO DHT` | DHT22 tidak terbaca | klasifikasi iklim dilewati; periksa wiring lalu ketik `dht` untuk diagnostik |
| Angka ppm berubah cepat lalu diam | moving average sedang menyusul nilai lama | sudah ditangani `FAST_TRACK_PPM`; kolom `i=` pada Serial menunjukkan nilai sesaat |
| Angka ppm beku (raw identik) padahal slider digeser | AOUT MQ-2 tidak tersambung ke GPIO34 | tempelkan ulang `diagram.json`, pastikan terdapat baris `[ "mq2:AOUT", "esp:D34", "green", [] ]`, lalu **Stop → Start Simulation** |
| MQTT nonaktif tanpa pesan `GAGAL` | `MQTT_HOST` masih placeholder `xxxx…` | isi kredensial HiveMQ; firmware mengaktifkan MQTT secara otomatis |
| ppm selalu 0 | ADC terbaca 0 V (kabel AOUT lepas) | pastikan `mq2:AOUT → D34` tersambung dan periksa kolom `V=` |
| Angka ppm jauh dari slider | skala log belum dikalibrasi | jalankan `c1 10` lalu `c2 100` (bagian 7) |
| Level tidak pernah KRITIS | skala ppm terlalu kecil | lakukan kalibrasi (bagian 7), lalu geser slider ke 570 ppm |
| Level naik tanpa kenaikan CO | flag iklim mikro aktif | periksa flag lingkungan pada baris Serial atau ketik `dht`; suhu ≥ 40 °C atau RH di luar 20–75 %RH akan mengeskalasi level |
| Buzzer tidak berbunyi | volume terlalu kecil | atribut `volume` pada `diagram.json` bernilai 0.1; naikkan menjadi 1.0 |
| Compile error pada `tone()` | core ESP32 sangat lama | gunakan core 3.x (default Wokwi) |

---

## 9. Catatan MQ-2 sebagai Pengganti MQ-7

Wokwi tidak menyediakan MQ-7. Simulasi memakai **MQ-2** yang juga sensitif terhadap CO.
Keduanya merupakan sensor semikonduktor oksida logam (MOS) berbasis heater dengan
keluaran analog, sehingga:

- arsitektur sistem, logika ambang batas, dan kebutuhan pembagi tegangan tidak berubah;
- yang berbeda hanya kurva sensitivitas dan selektivitas gas.

Pada implementasi fisik, **MQ-7** tetap menjadi pilihan utama karena selektivitas CO lebih
tinggi, sedangkan MQ-2 lebih sensitif terhadap LPG dan asap. Pernyataan ini dicantumkan
pada laporan dan narasi video.

---

## 10. Checklist Sebelum Submit

- [ ] Project Wokwi berjalan tanpa error dan Serial Monitor menampilkan data
- [ ] Payload MQTT terverifikasi pada HiveMQ Web Client
- [ ] Dashboard menampilkan grafik (tangkapan layar)
- [ ] Minimal 3 skenario uji terisi pada `testing/test-scenarios.md`
- [ ] Tangkapan layar `SS-01` … `SS-09` tersimpan di `docs/img/`
- [ ] Laporan `.docx` sudah memuat nama tim dan anggota
- [ ] Video demo `.mp4` sudah direkam
- [ ] Tautan Wokwi diatur **public/unlisted** lalu disalin ke laporan
