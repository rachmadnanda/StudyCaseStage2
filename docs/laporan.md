# CO-Zero: Sistem Monitoring dan Peringatan Dini Karbon Monoksida pada Kabin Mobil Berbasis ESP32 dan MQTT

**Tim Iki jenenge wes wkwk — Politeknik Negeri Malang**

Bagas Mirnanda Agung Narendra · Rachmad Febriananda · Syaiful Buchory

Samsung Innovation Campus Batch 8 — Stage 2: IoT (Device and Hardware Discovery)

---

## 1. Latar Belakang Masalah

Karbon monoksida (CO) adalah gas hasil pembakaran bahan bakar fosil yang tidak sempurna.
Sifatnya tidak berwarna, tidak berbau, dan tidak menimbulkan iritasi, sehingga korban tidak
menyadari bahwa dirinya sedang terpapar hingga muncul gejala berat seperti pusing, mual,
kebingungan, dan hilang kesadaran. Karena karakteristik inilah CO dijuluki *silent killer*.

Pada kendaraan bermotor, gas buang seharusnya dibuang ke udara terbuka melalui sistem
pembuangan. Namun korosi, retak halus, atau sambungan knalpot yang longgar dapat membuat
gas merembes masuk ke kabin, terutama ketika kendaraan berhenti lama dengan mesin dan AC
menyala dalam mode resirkulasi udara dalam. Volume kabin yang kecil serta tidak adanya
aliran udara membuat konsentrasi CO meningkat jauh lebih cepat dibandingkan di udara ambien.

Kasus di Indonesia menunjukkan hal ini bukan ancaman teoretis. Tragedi Brexit di Tol Brebes
Timur (2016) menyebabkan belasan pemudik meninggal akibat menghirup emisi gas buang saat
terjebak kemacetan. Pada Maret 2024, satu keluarga di Tol Indralaya–Prabumulih mengalami
keracunan dengan satu korban meninggal. Pada April 2025, sepasang suami istri ditemukan
tewas di Magelang dengan kadar CO dalam kabin mencapai 570 ppm — hampir lima kali ambang
batas aman 115 ppm. Kasus serupa kembali terjadi di Tol Pejagan–Pemalang pada Desember 2025
dan di Sleman pada April 2026.

Meskipun demikian, kendaraan penumpang kelas menengah di Indonesia umumnya tidak
dilengkapi indikator kualitas udara kabin. Fitur *air quality monitor* yang ada pada kendaraan
premium pun lebih berfokus pada partikel debu (PM2.5) untuk kebutuhan filtrasi AC, bukan
pada gas CO. Di sisi lain, solusi keselamatan pengemudi yang beredar saat ini didominasi
sistem *Driver Drowsiness Detection* berbasis kamera yang mahal, invasif terhadap privasi,
dan hanya bereaksi setelah gejala kantuk terlihat — padahal kantuk tersebut bisa jadi
merupakan akibat awal keracunan CO.

## 2. Problem Statement dan Tujuan

### 2.1 Problem Statement

Pengemudi dan penumpang tidak memiliki cara untuk mengetahui secara kuantitatif kualitas
udara kabin yang mereka tempati. Keputusan untuk membuka jendela, mematikan mesin, atau
menghentikan pendinginan sepenuhnya bergantung pada perasaan subjektif ("pengap" atau
"pusing") yang muncul setelah paparan berlangsung cukup lama. Diperlukan perangkat
berbiaya rendah yang mampu mengukur kadar CO secara berkelanjutan, memberi peringatan
segera di dalam kabin, dan mencatat data untuk evaluasi.

### 2.2 Tujuan

1. Membangun prototipe sistem monitoring CO kabin berbasis ESP32 yang membaca kadar CO,
   suhu, dan kelembapan secara berkala.
2. Menerapkan logika ambang batas berlapis (AMAN, WASPADA, BAHAYA, KRITIS) yang
   menghasilkan peringatan lokal berupa LED dan buzzer tanpa bergantung pada koneksi
   internet.
3. Mengirimkan data telemetri melalui MQTT ke broker HiveMQ Cloud dengan topik dan
   payload yang konsisten.
4. Menampilkan data tersebut pada dashboard Python yang menampilkan nilai terkini, tren,
   dan status sistem secara real-time.
5. Memvalidasi perilaku sistem melalui skenario pengujian kondisi normal, waspada,
   bahaya, kritis, dan kegagalan jaringan.

## 3. Target User dan Use Case

**Target user utama:** pengemudi mobil pribadi dan keluarga yang sering melakukan perjalanan
jauh (mudik, perjalanan antarkota), serta pengemudi yang beristirahat di dalam mobil dengan
mesin menyala.

**Use case yang dipilih:** *Smart Monitoring + Smart Alert*. Sistem memantau parameter
lingkungan kabin secara terus-menerus, memberikan peringatan bertingkat ketika kadar CO
meningkat, dan mengirimkan data ke dashboard untuk pemantauan serta pencatatan riwayat.

**Batasan lingkup Stage 2:** implementasi dilakukan sepenuhnya sebagai simulasi di Wokwi.
Aplikasi mobile berbasis Flutter dan komunikasi BLE yang terdapat pada proposal awal
KMIPN tidak diimplementasikan pada tahap ini, melainkan diposisikan sebagai pengembangan
lanjutan. Sebagai gantinya, jalur komunikasi IoT menggunakan MQTT dan divisualisasikan
melalui dashboard Python, sesuai kebutuhan Stage 2.

## 4. Arsitektur Sistem

### 4.1 Block Diagram

```
 INPUT / SENSING            PROCESSING / LOGIC              OUTPUT / ACTUATION
 ┌──────────────┐           ┌────────────────────┐          ┌──────────────┐
 │  MQ-2 (CO)   │──analog──▶│                    │──GPIO────▶│ LED H/K/M    │
 └──────────────┘  GPIO34   │      ESP32         │          └──────────────┘
 ┌──────────────┐           │  • moving average  │──PWM─────▶┌──────────────┐
 │ DHT22 (T/RH) │──GPIO4───▶│  • ambang batas    │           │   Buzzer     │
 └──────────────┘           │  • histeresis      │          └──────────────┘
                            │  • state machine   │──I2C─────▶┌──────────────┐
                            └─────────┬──────────┘           │ OLED SSD1306 │
                                      │                      └──────────────┘
                                      │ Serial (debug)
                                      ▼
                            ┌────────────────────┐
                            │  Serial Monitor    │
                            └────────────────────┘
                                      │ WiFi + MQTT/TLS (8883)
                                      ▼
                            ┌────────────────────┐
                            │   HiveMQ Cloud     │
                            └─────────┬──────────┘
                                      │ subscribe
                                      ▼
                            ┌────────────────────┐
                            │ Python Dashboard   │
                            │  paho-mqtt+Plotly  │
                            └────────────────────┘
```

### 4.2 Prinsip Desain

Sistem dirancang agar **fungsi keselamatan tetap berjalan di level perangkat (edge)**.
LED, buzzer, dan OLED dikendalikan langsung oleh ESP32 tanpa perantara jaringan. Jalur
MQTT bersifat pelengkap: digunakan untuk pemantauan jarak jauh dan pencatatan data.
Dengan demikian, kegagalan WiFi atau broker tidak menghilangkan kemampuan peringatan lokal.

## 5. Daftar Komponen dan Alasan Pemilihan

| No | Komponen | Fungsi | Alasan Pemilihan |
|----|----------|--------|------------------|
| 1 | ESP32 DevKit V1 | Mikrokontroler utama | Memiliki WiFi dan Bluetooth terintegrasi, 30 GPIO, ADC 12-bit, harga terjangkau, dan didukung penuh oleh simulator Wokwi maupun Arduino IDE |
| 2 | Modul MQ-2 | Sensor gas CO | Sensor MOS yang tersedia di Wokwi dan sensitif terhadap CO. Pada implementasi fisik, MQ-7 dipilih karena selektivitas CO lebih tinggi (lihat catatan 5.1) |
| 3 | DHT22 | Sensor suhu dan kelembapan | Akurasi lebih baik dari DHT11 (±0,5 °C, ±2–5 % RH) dengan selisih harga kecil; kelembapan penting untuk menilai kenyamanan dan sirkulasi kabin |
| 4 | OLED SSD1306 0,96" | Tampilan status lokal | Konsumsi daya rendah, antarmuka I2C hanya dua pin, mampu menampilkan nilai ppm, suhu, RH, dan status jaringan sekaligus |
| 5 | Buzzer piezoelektrik | Peringatan suara | Frekuensi tinggi lebih efektif menarik perhatian pengemudi; pola bunyi berbeda per level sehingga tingkat bahaya dapat dikenali dari suara |
| 6 | LED hijau/kuning/merah | Indikator visual | Memberi informasi status seketika pada jarak pandang jauh, redundan terhadap buzzer (misalnya bagi pengguna dengan gangguan pendengaran) |
| 7 | Resistor 10 kΩ ×2 | Pembagi tegangan (perangkat fisik) | Menurunkan keluaran analog MQ-2/MQ-7 (hingga ±5 V) ke rentang aman ADC ESP32 (maksimum 3,3 V) |
| 8 | Resistor 220 Ω ×3 | Pembatas arus LED | Mencegah kerusakan LED dan menjaga arus di bawah batas pin GPIO ESP32 |

> Resistor 10 kΩ ×2 **tidak dipasang pada simulasi Wokwi** karena simulator tidak
> mendukung kombinasi resistor dengan komponen analog. Keduanya wajib ada pada perangkat
> fisik — penjelasannya pada bagian 6.

### 5.1 Catatan Penggantian MQ-7 dengan MQ-2

Wokwi tidak menyediakan modul MQ-7. Simulasi menggunakan **MQ-2**, yang juga sensitif
terhadap CO. Keduanya merupakan sensor semikonduktor oksida logam (MOS) berbasis heater
dengan keluaran analog, sehingga arsitektur rangkaian, kebutuhan pembagi tegangan, dan
logika pengambilan keputusan tidak berubah. Perbedaan terletak pada kurva sensitivitas dan
selektivitas gas: MQ-2 lebih sensitif terhadap LPG dan asap, sedangkan MQ-7 lebih selektif
terhadap CO. Karena itu, pada implementasi perangkat fisik MQ-7 tetap menjadi pilihan
utama, dan perbedaan ini tidak memengaruhi hasil pengujian fungsional sistem.

## 6. Rangkaian dan Wiring (Wokwi)

Seluruh rangkaian disimulasikan pada Wokwi dengan komponen: ESP32 DevKit V1, modul
MQ-2, DHT22, OLED SSD1306, buzzer, tiga LED, dan tiga resistor 220 Ω.

**Penjelasan koneksi:**

- **Catu daya.** MQ-2 dihubungkan ke pin VIN (5 V) karena heater sensor membutuhkan
  tegangan 5 V. DHT22 dan OLED menggunakan pin 3V3.
- **Jalur analog.** Keluaran AOUT MQ-2 dihubungkan langsung ke GPIO34 (ADC1_CH6).
  GPIO34 dipilih karena merupakan pin *input-only* pada ADC1 yang tidak terganggu oleh
  aktivitas WiFi.
- **Jalur digital.** DOUT MQ-2 dihubungkan ke GPIO32 sebagai deteksi ambang redundan.
- **I2C.** OLED menggunakan GPIO21 (SDA) dan GPIO22 (SCL), yaitu pin I2C default ESP32.
- **Aktuator.** Buzzer pada GPIO25, LED hijau pada GPIO26, LED kuning pada GPIO27, dan
  LED merah pada GPIO14, masing-masing melalui resistor 220 Ω ke GND.
- **Ground.** Seluruh komponen berbagi ground dengan ESP32 agar referensi tegangan sama.

**Perbedaan dengan implementasi fisik (pembagi tegangan).** Keluaran analog MQ-2/MQ-7
dapat mencapai ±5 V, sedangkan ADC ESP32 hanya menerima maksimum 3,3 V. Pada perangkat
nyata jalur AOUT harus melewati pembagi tegangan R1 = 10 kΩ (seri) dan R2 = 10 kΩ
(ke GND), sehingga tegangan di GPIO34 menjadi setengahnya, dan firmware perlu diubah
dengan `DIVIDER_RATIO = 2.0`. Pembagi ini tidak dapat disimulasikan karena Wokwi hanya
mendukung rangkaian analog sederhana dan tidak mengombinasikan resistor dengan komponen
analog; karena itu pada simulasi AOUT dihubungkan langsung dan `DIVIDER_RATIO = 1.0`.
Perbedaan ini tidak memengaruhi logika sistem karena keduanya hanya memengaruhi skala
pembacaan, yang dikompensasi melalui kalibrasi dua titik.

**Tautan proyek Wokwi:** `https://wokwi.com/projects/________` *(isi setelah project dibuat)*

## 7. Pin dan Fungsi GPIO

| Komponen | Pin Komponen | Pin ESP32 | GPIO | Mode | Keterangan |
|---|---|---|---|---|---|
| MQ-2 | VCC | VIN | — | Power | 5 V untuk heater |
| MQ-2 | GND | GND.2 | — | Power | Ground |
| MQ-2 | AOUT | D34 | GPIO34 | Analog input | ADC1_CH6, resolusi 12-bit |
| MQ-2 | DOUT | D32 | GPIO32 | Digital input | LOW saat melewati ambang |
| DHT22 | SDA | D4 | GPIO4 | Digital I/O | Protokol one-wire |
| DHT22 | VCC/GND | 3V3 / GND.1 | — | Power | 3,3 V |
| OLED | SDA | D21 | GPIO21 | I2C SDA | Default I2C ESP32 |
| OLED | SCL | D22 | GPIO22 | I2C SCL | Default I2C ESP32 |
| Buzzer | Pin 2 (+) | D25 | GPIO25 | Digital output | `tone()` 2 kHz |
| LED hijau | Anoda | D26 | GPIO26 | Digital output | AMAN |
| LED kuning | Anoda | D27 | GPIO27 | Digital output | WASPADA |
| LED merah | Anoda | D14 | GPIO14 | Digital output | BAHAYA / KRITIS |

## 8. Penjelasan Logika Program

Program ditulis dalam bahasa C++ untuk Arduino framework dengan struktur `setup()` dan
`loop()` non-blocking. Seluruh pewaktuan menggunakan `millis()` sehingga pembacaan sensor,
pengiriman MQTT, pembaruan OLED, dan pola buzzer berjalan tanpa saling menghambat.

### 8.1 Alur Program

```
setup()
  ├─ inisialisasi Serial 115200, pin input/output
  ├─ inisialisasi I2C + OLED
  ├─ inisialisasi DHT22
  ├─ set skala sensor (default: 200 ppm/V, baseline 0 V)
  └─ koneksi WiFi, set konfigurasi MQTT (TLS, buffer 512, keepalive 30 s)

loop()
  ├─ baca perintah Serial Monitor (kalibrasi/diagnosa)
  ├─ pastikan WiFi & MQTT terhubung (retry 5 detik)
  ├─ setiap 500 ms  : baca ADC → moving average → klasifikasi level → LED
  ├─ setiap 2500 ms : baca DHT22
  ├─ setiap 2000 ms : publikasikan telemetri JSON
  ├─ setiap 300 ms  : perbarui OLED
  └─ setiap siklus  : perbarui pola buzzer sesuai level
```

### 8.2 Pembacaan dan Konversi Sensor

Nilai ADC dibaca delapan kali lalu dirata-rata untuk mengurangi noise. Tegangan ADC
dikonversi menjadi tegangan keluaran sensor dengan mengalikannya dengan rasio pembagi
tegangan (`DIVIDER_RATIO`, bernilai 1,0 pada simulasi dan 2,0 pada perangkat fisik).
Kadar CO dihitung dengan pemetaan linear:

```
Vout  = (ADC / 4095) × 3,3 V × DIVIDER_RATIO
ppm   = (Vout − baseline) × ppmPerVolt
```

Nilai `ppmPerVolt` dan `baseline` ditetapkan melalui **kalibrasi dua titik yang dijalankan
saat simulasi berjalan**, bukan dengan menebak konstanta. Pengguna menggeser slider ppm
sensor ke nilai acuan, lalu mengirim perintah lewat Serial Monitor:

```
c1 100     ->  simpan pasangan (100 ppm, Vout saat ini)
c2 500     ->  hitung ppmPerVolt dan baseline, lalu cetak hasilnya
?          ->  tampilkan status kalibrasi saat ini
r          ->  kembalikan ke nilai default
```

Dengan cara ini skala ppm selalu sesuai dengan keluaran simulator, tanpa perlu mengubah
dan meng-*upload* ulang sketch. Nilai hasil kalibrasi kemudian disalin ke bagian
KONFIGURASI agar tetap berlaku setelah perangkat di-*restart*.

Titik kalibrasi dipilih pada **100 ppm dan 500 ppm**. Pemilihan ini penting karena tanpa
pembagi tegangan, ADC ESP32 jenuh di sekitar 3,1–3,3 V; bila titik kedua diambil pada
900 ppm, pembacaan bisa terpotong (*clipping*) dan hasil kalibrasi menjadi salah. Dengan
rentang 100–500 ppm, kedua titik berada di daerah linear, sementara nilai uji di atasnya
(termasuk skenario 570 ppm) masih terbaca sebelum ADC jenuh.

> Pada perangkat fisik, MQ-7 memakai kurva logaritmik Rs/R0 sesuai datasheet
> (`ppm = a × (Rs/R0)^b`) dan membutuhkan pemanasan awal 24–48 jam. Pemetaan linear
> dipilih pada simulasi karena keluaran simulator sudah proporsional terhadap konsentrasi;
> prosedur kalibrasi dua titik di atas menjaga agar angka yang ditampilkan tetap terverifikasi.

### 8.3 Klasifikasi Level dan Histeresis

| Level | Rentang | LED | Buzzer |
|---|---|---|---|
| AMAN | < 20 ppm | hijau | mati |
| WASPADA | 20 – 34 ppm | kuning | beep 1 Hz |
| BAHAYA | 35 – 114 ppm | merah | beep 2,5 Hz |
| KRITIS | ≥ 115 ppm | merah | kontinu |

Histeresis sebesar 3 ppm diterapkan pada proses penurunan level. Level hanya akan turun
setelah nilai berada pada atau di bawah 3 ppm di bawah ambang level tersebut (misalnya
level BAHAYA baru lepas saat nilai ≤ 32 ppm). Tanpa histeresis, nilai yang berfluktuasi
di sekitar ambang (misalnya 34–36 ppm) akan menyebabkan LED dan buzzer berkedip
terus-menerus.

Konsekuensi yang disengaja: bila nilai berosilasi melewati ambang, sistem akan **bertahan
pada level yang lebih tinggi** (konservatif demi keamanan) sampai kadar turun melewati
batas histeresis. Perilaku ini diverifikasi oleh uji unit otomatis
(`tools/test_logic.py`, 21 assertion) yang mengekstrak fungsi `classify()` langsung dari
sketch dan mengompilasinya secara terpisah.

Ambang 20 ppm dipakai sebagai peringatan dini agar pengemudi punya waktu membuka jendela
atau mematikan mode resirkulasi. Ambang 35 ppm dan 115 ppm mengikuti rujukan kesehatan
serta data kasus lapangan yang menunjukkan kadar CO kabin dapat mencapai ratusan ppm.

### 8.4 Jalur Redundan

Keluaran digital MQ-2 (DOUT) dibaca sebagai penguat keputusan dari komparator perangkat
keras. Jika DOUT aktif (LOW) **dan** perhitungan analog sudah mencapai ambang WASPADA,
level sistem dinaikkan minimal ke BAHAYA. Syarat kedua tersebut penting: bila DOUT
"nyangkut" LOW karena potensiometer disetel terlalu sensitif, sistem tidak akan melaporkan
bahaya palsu saat udara kabin masih bersih. Dengan cara ini sistem memiliki dua jalur
deteksi independen tanpa mengorbankan keandalan pembacaan analog.

Pada simulasi Wokwi, atribut `threshold` komponen MQ-2 disetel **4,0 V** sehingga komparator
baru akan aktif di atas kisaran pengujian (≤ 570 ppm). Dengan begitu seluruh perubahan level
selama demo benar-benar berasal dari perhitungan analog, dan jalur DOUT berfungsi sebagai
lapisan pengaman tambahan yang siap diaktifkan pada perangkat fisik (potensiometer disetel
agar DOUT aktif pada kadar sekitar 200 ppm).

## 9. Komunikasi Serial dan MQTT

### 9.1 Serial Monitor

Serial Monitor (115200 baud) digunakan sebagai tiga hal sekaligus: media debugging,
bukti aliran data, dan antarmuka kalibrasi sensor.

Contoh keluaran:

```
[  3210 ms] CO=   0.4 ppm (raw=   2 Vout=0.00V dout=1) | 29.0C 61% | AMAN
[  5210 ms] CO=  24.8 ppm (raw= 103 Vout=0.08V dout=1) | 29.1C 61% | WASPADA
```

Setiap baris memuat waktu, nilai ppm hasil pengolahan, nilai ADC mentah, tegangan sensor,
status DOUT, suhu, kelembapan, dan level. Nilai mentah inilah yang dipakai pada prosedur
kalibrasi dua titik (`c1`/`c2`) sebagaimana dijelaskan pada bagian 8.2.

### 9.2 Topik MQTT

| Topik | QoS | Retain | Isi |
|---|---|---|---|
| `cozero/team/telemetry` | 0 | tidak | data sensor setiap 2 detik |
| `cozero/team/alert` | 0 | tidak | dikirim saat level berubah |
| `cozero/team/status` | 0 | ya | `online` / `offline` (Last Will & Testament) |

Koneksi menggunakan TLS pada port 8883. Fitur *Last Will & Testament* dipakai agar broker
otomatis menandai perangkat `offline` bila koneksi terputus tanpa salam penutup, sehingga
dashboard dapat membedakan "kabin aman" dari "data tidak masuk".

### 9.3 Struktur Payload

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

Format JSON dipilih agar mudah di-*parse* oleh klien mana pun (Python, JavaScript, maupun
aplikasi mobile pada pengembangan lanjutan).

## 10. Dashboard dan Visualisasi

Dashboard dibuat dengan Python menggunakan `paho-mqtt` sebagai klien dan Plotly/Matplotlib
sebagai mesin visualisasi. Dashboard berlangganan ketiga topik di atas dan menampilkan:

1. **Kartu status** — level terkini, kadar CO, suhu, kelembapan, dan ID perangkat.
2. **Grafik tren CO** — garis waktu dengan pita warna yang menandai zona AMAN, WASPADA,
   BAHAYA, dan KRITIS sehingga posisi nilai langsung terbaca secara visual.
3. **Grafik iklim mikro** — suhu dan kelembapan dalam satu sumbu waktu.
4. **Riwayat peringatan** — daftar transisi level beserta waktunya.
5. **Pencatatan CSV** — setiap pesan disimpan dengan kolom waktu, perangkat, ppm, suhu,
   RH, level, dan kode level untuk analisis lanjutan.

Dashboard tersedia dalam dua bentuk: skrip Python untuk dijalankan lokal dan notebook
Google Colab untuk pengambilan tangkapan layar pada laporan.

## 11. Skenario dan Hasil Pengujian

Pengujian dilakukan pada dua lapis. Pertama, **uji unit logika** yang mengekstrak fungsi
`classify()` langsung dari sketch, mengompilasinya terpisah, dan menjalankan 21 assertion
terhadap tabel ambang batas serta perilaku histeresis (`tools/test_logic.py`). Kedua,
**uji fungsional end-to-end** pada Wokwi dengan mengubah atribut `ppm` pada komponen MQ-2
saat simulasi berjalan, sehingga kondisi udara kabin dapat disimulasikan secara terkendali.

| No | Test Case | Input | Expected Result | Actual Result | Status |
|----|-----------|-------|-----------------|---------------|--------|
| TC-01 | Kondisi normal | 5 ppm | LED hijau, buzzer mati, OLED AMAN, payload AMAN | | |
| TC-02 | Peringatan dini | 25 ppm | LED kuning, beep 1 Hz, alert AMAN→WASPADA | | |
| TC-03 | Kondisi bahaya | 60 ppm | LED merah, beep 2,5 Hz, alert WASPADA→BAHAYA | | |
| TC-04 | Kondisi kritis | 570 ppm | LED merah, buzzer kontinu, OLED KRITIS | | |
| TC-05 | Histeresis | 60 → 33 → 30 ppm | Level tetap BAHAYA hingga ppm ≤ 32 | | |
| TC-06 | Jaringan terputus | WiFi dimatikan | Alarm lokal tetap aktif, dashboard menandai offline, reconnect otomatis | | |
| TC-07 | Logging & visualisasi | 2 menit data | Grafik ter-update, CSV terbentuk | | |
| TC-08 | Uji unit logika (otomatis) | `tools/test_logic.py` | 21 assertion lulus | | |

*(Kolom Actual Result dan Status diisi setelah pengujian; dokumentasi berupa tangkapan layar
dan video demo.)*

## 12. Dokumentasi Visual

| Kode | Keterangan | Berkas |
|---|---|---|
| SS-01 | Rangkaian lengkap Wokwi | `docs/img/SS-01-wiring.png` |
| SS-02 | Serial Monitor kondisi AMAN | `docs/img/SS-02-serial-aman.png` |
| SS-03 | Serial Monitor kondisi BAHAYA | `docs/img/SS-03-serial-bahaya.png` |
| SS-04 | OLED KRITIS + LED merah | `docs/img/SS-04-oled-kritis.png` |
| SS-05 | Payload diterima HiveMQ | `docs/img/SS-05-hivemq.png` |
| SS-06 | Dashboard Python | `docs/img/SS-06-dashboard.png` |
| SS-07 | Isi file CSV | `docs/img/SS-07-csv.png` |
| SS-08 | Status offline (LWT) | `docs/img/SS-08-offline.png` |

## 13. Pembagian Peran Anggota

| Nama | Peran | Kontribusi |
|---|---|---|
| Bagas Mirnanda Agung Narendra | Ketua / Hardware | Perancangan rangkaian, pemilihan komponen, wiring Wokwi, dokumentasi pin |
| Rachmad Febriananda | Firmware | Penulisan sketch ESP32, logika ambang batas, integrasi MQTT, debugging |
| Syaiful Buchory | Data & Dokumentasi | Dashboard Python, pengujian skenario, penyusunan laporan dan video |

## 14. Kesimpulan

1. Prototipe CO-Zero berhasil dibangun di atas ESP32 dan disimulasikan penuh di Wokwi
   dengan satu sensor input gas, satu sensor iklim mikro, serta tiga jenis aktuator
   (LED, buzzer, OLED).
2. Logika ambang batas berlapis dengan moving average dan histeresis mampu mengubah
   kondisi sensor menjadi peringatan yang stabil dan mudah dipahami, tanpa kedipan pada
   nilai batas.
3. Integrasi MQTT dengan HiveMQ Cloud berjalan baik: data telemetri terkirim setiap dua
   detik, transisi level tercatat pada topik `alert`, dan status perangkat terpantau
   melalui mekanisme Last Will & Testament.
4. Dashboard Python berhasil menampilkan tren CO, suhu, dan kelembapan secara real-time
   serta menyimpan riwayat ke berkas CSV.
5. Fungsi keselamatan tetap berjalan ketika koneksi internet terputus karena seluruh
   indikator lokal dikendalikan langsung oleh perangkat.

## 15. Pengembangan Lanjutan

1. **Perangkat fisik dengan MQ-7.** Mengganti MQ-2 dengan MQ-7 dan menerapkan kurva
   logaritmik Rs/R0 beserta pemanasan (preheat) 24–48 jam untuk akurasi kadar CO.
2. **Aplikasi mobile dan BLE.** Mengimplementasikan aplikasi Flutter dengan komunikasi
   Bluetooth Low Energy dan basis data SQLite lokal sebagaimana dirancang pada proposal
   KMIPN, sebagai pelengkap jalur MQTT.
3. **Notifikasi jarak jauh.** Menambahkan integrasi Telegram atau push notification agar
   peringatan KRITIS diterima anggota keluarga.
4. **Aktuasi otomatis.** Menambahkan relay atau servo untuk membuka jendela dan
   menghentikan mode resirkulasi AC secara otomatis saat level BAHAYA tercapai.
5. **Analitik prediktif.** Memanfaatkan data historis CO, suhu, dan kelembapan untuk
   mendeteksi indikasi kebocoran sistem pembuangan sebelum mencapai kadar berbahaya.

## 16. Lampiran

- **Proyek Wokwi:** `https://wokwi.com/projects/________`
- **Kode sumber:** `firmware/cozero_esp32.ino`
- **Rangkaian:** `firmware/diagram.json`
- **Dashboard:** `dashboard/cozero_dashboard.py`, `dashboard/cozero_dashboard_colab.ipynb`
- **Hasil pengujian:** `testing/test-scenarios.md`
- **Video demo:** `Video-Demo-CO-Zero-Iki-Jenenge-Wes-Wkwk.mp4`
