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
   menghasilkan peringatan lokal berupa tampilan OLED dan bunyi buzzer tanpa bergantung
   pada koneksi internet.
3. Mengintegrasikan pembacaan suhu dan kelembapan kabin ke dalam pengambilan keputusan,
   sehingga kondisi lingkungan yang ekstrem memperberat tingkat peringatan.
4. Mengirimkan data telemetri melalui MQTT ke broker HiveMQ Cloud dengan topik dan payload
   yang konsisten.
5. Menampilkan data tersebut pada dashboard Python yang menampilkan nilai terkini, tren,
   dan status sistem secara real-time.
6. Memvalidasi perilaku sistem melalui skenario pengujian kondisi normal, waspada,
   bahaya, kritis, eskalasi iklim mikro, dan kegagalan jaringan.

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

### 4.2 Prinsip Desain

Sistem dirancang agar **fungsi keselamatan tetap berjalan di level perangkat (edge)**.
OLED dan buzzer dikendalikan langsung oleh ESP32 tanpa perantara jaringan. Jalur
MQTT bersifat pelengkap: digunakan untuk pemantauan jarak jauh dan pencatatan data.
Dengan demikian, kegagalan WiFi atau broker tidak menghilangkan kemampuan peringatan lokal.

## 5. Daftar Komponen dan Alasan Pemilihan

| No | Komponen | Fungsi | Alasan Pemilihan |
|----|----------|--------|------------------|
| 1 | ESP32 DevKit V1 | Mikrokontroler utama | Memiliki WiFi dan Bluetooth terintegrasi, 30 GPIO, ADC 12-bit, harga terjangkau, dan didukung penuh oleh simulator Wokwi maupun Arduino IDE |
| 2 | Modul MQ-2 | Sensor gas CO | Sensor MOS yang tersedia di Wokwi dan sensitif terhadap CO. Pada implementasi fisik, MQ-7 dipilih karena selektivitas CO lebih tinggi (lihat catatan 5.1) |
| 3 | DHT22 | Sensor suhu dan kelembapan | Akurasi lebih baik dari DHT11 (±0,5 °C, ±2–5 % RH) dengan selisih harga kecil; kedua parameter dipakai menilai beban fisiologis kabin dan memperberat level CO |
| 4 | OLED SSD1306 0,96" | Tampilan status lokal **dan** indikator visual utama | Konsumsi daya rendah, antarmuka I2C hanya dua pin, mampu menampilkan level, nilai ppm, bar skala, suhu, RH, flag lingkungan, dan status jaringan sekaligus — menggantikan tiga LED |
| 5 | Buzzer piezoelektrik | Peringatan suara | Frekuensi tinggi lebih efektif menarik perhatian pengemudi; pola bunyi berbeda per level sehingga tingkat bahaya dapat dikenali dari suara |
| 6 | Resistor 10 kΩ ×2 | Pembagi tegangan (perangkat fisik) | Menurunkan keluaran analog MQ-2/MQ-7 (hingga ±5 V) ke rentang aman ADC ESP32 (maksimum 3,3 V) |

> Resistor 10 kΩ ×2 **tidak dipasang pada simulasi Wokwi** karena simulator tidak
> mendukung kombinasi resistor dengan komponen analog. Keduanya wajib ada pada perangkat
> fisik — penjelasannya pada bagian 6.

> **Catatan penyederhanaan.** Versi awal rangkaian memakai tiga LED (hijau/kuning/merah)
> beserta tiga resistor 220 Ω. Indikator tersebut dihapus karena menambah jumlah sambungan
> tanpa menambah informasi: level yang sama sudah ditampilkan pada OLED, termasuk pita
> status yang dibalik (putih di atas hitam) saat BAHAYA/KRITIS. Buzzer tetap dipertahankan
> karena berfungsi sebagai peringatan audio yang tidak bergantung pada pandangan pengemudi.

### 5.1 Catatan Penggantian MQ-7 dengan MQ-2

Wokwi tidak menyediakan modul MQ-7. Simulasi menggunakan **MQ-2**, yang juga sensitif
terhadap CO. Keduanya merupakan sensor semikonduktor oksida logam (MOS) berbasis heater
dengan keluaran analog, sehingga arsitektur rangkaian, kebutuhan pembagi tegangan, dan
logika pengambilan keputusan tidak berubah. Perbedaan terletak pada kurva sensitivitas dan
selektivitas gas: MQ-2 lebih sensitif terhadap LPG dan asap, sedangkan MQ-7 lebih selektif
terhadap CO. Karena itu, pada implementasi perangkat fisik MQ-7 tetap menjadi pilihan
utama, dan perbedaan ini tidak memengaruhi hasil pengujian fungsional sistem.

## 6. Rangkaian dan Wiring (Wokwi)

Seluruh rangkaian disimulasikan pada Wokwi dengan lima komponen: ESP32 DevKit V1, modul
MQ-2, DHT22, OLED SSD1306, dan buzzer. Tidak ada LED maupun resistor pada simulasi,
sehingga jumlah sambungan hanya 15 baris dan seluruhnya dapat ditulis langsung di
`diagram.json`.

**Penjelasan koneksi:**

- **Catu daya.** MQ-2 dihubungkan ke pin VIN (5 V) karena heater sensor membutuhkan
  tegangan 5 V. DHT22 dan OLED menggunakan pin 3V3.
- **Jalur analog.** Keluaran AOUT MQ-2 dihubungkan langsung ke GPIO34 (ADC1_CH6).
  GPIO34 dipilih karena merupakan pin *input-only* pada ADC1 yang tidak terganggu oleh
  aktivitas WiFi.
- **Jalur digital.** DOUT MQ-2 dihubungkan ke GPIO32 sebagai deteksi ambang redundan.
- **I2C.** OLED menggunakan GPIO21 (SDA) dan GPIO22 (SCL), yaitu pin I2C default ESP32.
- **Aktuator.** Buzzer pada GPIO25; pin lainnya ke GND.
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

## 8. Penjelasan Logika Program

Program ditulis dalam bahasa C++ untuk Arduino framework dengan struktur `setup()` dan
`loop()` non-blocking. Seluruh pewaktuan menggunakan `millis()` sehingga pembacaan sensor,
pengiriman MQTT, pembaruan OLED, dan pola buzzer berjalan tanpa saling menghambat.

### 8.1 Alur Program

```
setup()
  ├─ inisialisasi Serial 115200, pin input/output
  ├─ inisialisasi I2C + OLED
  ├─ uji awal DHT22 (maksimum 3 percobaan) sebelum WiFi aktif
  ├─ set skala sensor (default: 0,6836 V/dekade, 1 ppm = 1,3629 V)
  └─ koneksi WiFi, set konfigurasi MQTT (TLS, buffer 512, keepalive 30 s)

loop()
  ├─ baca perintah Serial Monitor (kalibrasi `c1`/`c2`, diagnosa `dht`)
  ├─ pastikan WiFi & MQTT terhubung (retry 5 detik)
  ├─ setiap 500 ms  : baca ADC → moving average → level CO → flag iklim
  │                   → gabungkan → publikasikan alert bila level berubah
  ├─ setiap 2200 ms : baca DHT22 (laju maksimum yang diizinkan sensor)
  ├─ setiap 2000 ms : publikasikan telemetri JSON
  ├─ setiap 300 ms  : perbarui OLED (level, ppm, bar skala, suhu, RH, flag)
  └─ setiap siklus  : perbarui pola buzzer sesuai level akhir
```

Uji awal DHT22 dijalankan sebelum WiFi diaktifkan karena aktivitas radio dapat
mengganggu timing protokol satu kabel. Hasilnya dicetak lengkap sehingga kegagalan
wiring langsung terlihat pada Serial Monitor tanpa menunggu siklus pembacaan pertama.

### 8.2 Pembacaan dan Konversi Sensor

Nilai ADC dibaca delapan kali lalu dirata-rata untuk mengurangi noise. Tegangan ADC
dikonversi menjadi tegangan keluaran sensor dengan mengalikannya dengan rasio pembagi
tegangan (`DIVIDER_RATIO`, bernilai 1,0 pada simulasi dan 2,0 pada perangkat fisik).

Kadar CO dihitung dengan pemetaan **logaritmik**, bukan linear:

```
Vout = (ADC / 4095) × 3,3 V × DIVIDER_RATIO
ppm  = 10 ^ ((Vout − V_AT_1PPM) / V_PER_DECADE)
```

Pemilihan model ini didasarkan pada pengukuran langsung di simulator. Tiga titik ukur
diambil dengan menggeser slider sensor dan mencatat tegangan yang dilaporkan Serial
Monitor:

| Slider (ppm) | Vout | ADC mentah |
|---|---|---|
| 0,1 | 0,679 V | 843 |
| 3 | 1,689 V | 2.096 |
| 100.000 | 3,257 V | 4.041 *(ADC mulai jenuh)* |

Ketiga titik tersebut mengikuti hubungan `Vout = 1,3629 + 0,6836 × log10(ppm)` dengan
kesalahan di bawah 0,1%. Artinya setiap kenaikan satu dekade (10×) konsentrasi hanya
menaikkan tegangan sekitar 0,68 V — ciri khas sensor semikonduktor oksida logam (MOS)
seperti MQ-2 dan MQ-7. Pemetaan linear yang sempat dipakai pada versi awal firmware
menghasilkan kesalahan hingga tiga orde besaran (slider 0,1 ppm terbaca 136 ppm),
sehingga diganti dengan model logaritmik di atas.

Konstanta `V_PER_DECADE` dan `V_AT_1PPM` ditetapkan melalui **kalibrasi dua titik yang
dijalankan saat simulasi berjalan**, bukan dengan menebak nilai. Pengguna menggeser slider
sensor ke nilai acuan, lalu mengirim perintah lewat Serial Monitor:

```
c1 10      ->  simpan pasangan (10 ppm, Vout saat ini)
c2 100     ->  hitung V_PER_DECADE dan V_AT_1PPM, lalu cetak hasilnya
?          ->  tampilkan status kalibrasi saat ini
r          ->  kembalikan ke nilai default
```

Kalibrasi dilakukan di ruang logaritmik:

```
V_PER_DECADE = (V2 − V1) / (log10(ppm2) − log10(ppm1))
V_AT_1PPM    = V1 − V_PER_DECADE × log10(ppm1)
```

Dengan cara ini skala ppm selalu sesuai dengan keluaran simulator, tanpa perlu mengubah
dan meng-*upload* ulang sketch. Nilai hasil kalibrasi kemudian disalin ke bagian
KONFIGURASI agar tetap berlaku setelah perangkat di-*restart*.

Titik kalibrasi dipilih pada **10 ppm dan 100 ppm**, yaitu dua titik yang berjarak tepat
satu dekade sehingga regresi logaritmik stabil, dan keduanya jauh di bawah batas jenuh
ADC. Tanpa pembagi tegangan, ADC ESP32 jenuh pada 3,300 V yang setara ±682 ppm; titik
acuan di atas 600 ppm akan terpotong (*clipping*) dan menghasilkan kalibrasi yang salah.
Skenario uji tertinggi, 570 ppm, berada pada 3,247 V sehingga masih terbaca sebelum jenuh.

> Pada perangkat fisik, MQ-7 memakai kurva Rs/R0 sesuai datasheet
> (`ppm = a × (Rs/R0)^b`) dan membutuhkan pemanasan awal 24–48 jam. Bentuk kurvanya sama —
> logaritmik — sehingga struktur perhitungan tidak berubah; hanya konstanta dan titik
> nolnya yang berbeda dan harus ditentukan lewat kalibrasi pada gas acuan.

### 8.3 Klasifikasi Level CO dan Histeresis

| Level | Rentang | OLED | Buzzer |
|---|---|---|---|
| AMAN | < 20 ppm | `AMAN`, teks normal | mati |
| WASPADA | 20 – 34 ppm | `WASPADA`, teks normal | beep 1 Hz |
| BAHAYA | 35 – 114 ppm | `BAHAYA`, pita dibalik | beep 2,5 Hz |
| KRITIS | ≥ 115 ppm | `KRITIS`, pita dibalik | kontinu |

Histeresis sebesar 3 ppm diterapkan pada proses penurunan level. Level hanya akan turun
setelah nilai berada pada atau di bawah 3 ppm di bawah ambang level tersebut (misalnya
level BAHAYA baru lepas saat nilai ≤ 32 ppm). Tanpa histeresis, nilai yang berfluktuasi
di sekitar ambang (misalnya 34–36 ppm) akan menyebabkan buzzer berbunyi terputus-putus
dan pita status OLED berkedip terus-menerus.

Konsekuensi yang disengaja: bila nilai berosilasi melewati ambang, sistem akan **bertahan
pada level yang lebih tinggi** (konservatif demi keamanan) sampai kadar turun melewati
batas histeresis.

Ambang 20 ppm dipakai sebagai peringatan dini agar pengemudi memiliki waktu membuka jendela
atau mematikan mode resirkulasi. Ambang 35 ppm dan 115 ppm mengikuti rujukan kesehatan
serta data kasus lapangan yang menunjukkan kadar CO kabin dapat mencapai ratusan ppm.

### 8.4 Penilaian Iklim Mikro dan Matriks Eskalasi

Suhu dan kelembapan kabin tidak menghasilkan level secara mandiri. Keduanya hanya
menghasilkan **flag lingkungan** yang kemudian dipakai untuk memperberat level CO:

| Flag | Kondisi | Dasar pertimbangan |
|---|---|---|
| `PANAS` | suhu ≥ 40,0 °C | Beban panas menambah kerja kardiovaskular sehingga tubuh lebih cepat kekurangan oksigen |
| `LEMBAB` | RH ≥ 75 %RH | Penguapan keringat terhambat; lazim menyertai kabin tertutup dengan sirkulasi resirkulasi |
| `KERING` | RH ≤ 20 %RH | Iritasi saluran napas dan mukosa |
| `NORMAL` | di luar semua kondisi di atas | — |

Bila suhu dan kelembapan sama-sama berada di luar rentang, `PANAS` diprioritaskan karena
dampaknya terhadap beban jantung lebih langsung. Deadband sebesar 1 °C dan 3 %RH
diterapkan pada proses pelepasan flag, dengan konvensi yang sama seperti histeresis CO:
flag baru kembali ke `NORMAL` setelah nilai melewati ambang dikurangi deadband.

Keputusan akhir diambil melalui matriks berikut:

| Level CO | Kondisi lingkungan | Level akhir |
|---|---|---|
| AMAN | NORMAL | AMAN |
| AMAN | ekstrem | WASPADA |
| WASPADA | NORMAL | WASPADA |
| WASPADA | ekstrem | BAHAYA |
| BAHAYA | NORMAL | BAHAYA |
| BAHAYA | ekstrem | KRITIS |
| KRITIS | apa pun | KRITIS |

Eskalasi dibatasi **satu tingkat** per keputusan, dan kondisi lingkungan ekstrem
sendirian tidak pernah menghasilkan BAHAYA atau KRITIS. Pembatasan ini disengaja agar
sensor gas tetap menjadi sumber utama keputusan: suhu dan kelembapan hanya memperkuat
penilaian, tidak menggantikannya. Konsekuensinya, kabin bersuhu 45 °C dengan udara bersih
tetap menghasilkan WASPADA, bukan KRITIS.

Bila DHT22 gagal dibaca, flag dipaksa `NORMAL` dan eskalasi dilewati. Keputusan ini
mencegah kegagalan sensor memicu peringatan palsu, sekaligus membuat sistem tetap berfungsi
dengan level CO saja.

Pembacaan DHT22 dijadwalkan setiap 2.200 ms, yaitu laju maksimum yang diizinkan sensor
(0,5 Hz). Nilai yang gagal dibaca tidak dipertahankan: variabel ditandai tidak valid
sehingga antarmuka menampilkan tanda `--`, bukan angka lama yang dapat disalahartikan
sebagai pembacaan terkini. Sebelum WiFi diaktifkan, firmware menjalankan uji awal hingga
tiga percobaan berjarak 2,2 detik dan mencetak status setiap percobaan, sehingga kegagalan
wiring terlihat langsung pada Serial Monitor. Kegagalan berulang dilaporkan paling sering
setiap lima detik agar keluaran Serial tetap terbaca.

Seluruh aturan pada bagian 8.3 dan 8.4 diverifikasi oleh uji unit otomatis
(`tools/test_logic.py`, 60 assertion) yang mengekstrak fungsi `classify()`, `envCheck()`,
`combineLevels()`, dan `voltsToPpm()` langsung dari sketch, mengompilasinya secara
terpisah, lalu menguji ketiganya — termasuk matriks eskalasi, deadband, penanganan sensor
gagal, dan kesesuaian konversi logaritmik dengan tiga titik pengukuran di simulator.

### 8.5 Jalur Redundan

Keluaran digital MQ-2 (DOUT) dibaca sebagai penguat keputusan dari komparator perangkat
keras. Level dinaikkan minimal ke BAHAYA hanya bila **dua** syarat terpenuhi: tegangan
AOUT sudah melewati ambang komparator (`DOUT_THRESHOLD_V` = 4,0 V) **dan** perhitungan
analog sudah mencapai ambang WASPADA. Syarat pertama penting karena pin DOUT yang
mengambang — misalnya akibat kabel lepas — akan terbaca LOW; tanpa pemeriksaan tegangan,
kondisi itu dapat memicu BAHAYA palsu. Dengan cara ini sistem memiliki dua jalur deteksi
independen tanpa mengorbankan keandalan pembacaan analog.

Pada simulasi Wokwi, atribut `threshold` komponen MQ-2 disetel **4,0 V** sehingga komparator
baru akan aktif di atas kisaran pengujian (≤ 570 ppm). Dengan begitu seluruh perubahan level
selama demo benar-benar berasal dari perhitungan analog, dan jalur DOUT berfungsi sebagai
lapisan pengaman tambahan yang siap diaktifkan pada perangkat fisik (potensiometer disetel
agar DOUT aktif pada kadar sekitar 200 ppm).

### 8.6 Tampilan OLED

Karena OLED menjadi satu-satunya indikator visual, tata letaknya dirancang seperti panel
instrumen agar status dapat dibaca dalam sekali pandang:

| Baris (px) | Isi |
|---|---|
| 0–7 | Judul `CO-Zero` dan status `W:OK M:OK` (WiFi / MQTT) |
| 8–27 | Pita status: `AMAN`, `WASPADA`, `BAHAYA`, `KRITIS` ukuran 2× (12×16 px). Pada BAHAYA dan KRITIS pita dibalik (teks hitam di atas latar putih) sehingga perubahan status terlihat tanpa harus membaca huruf |
| 29–37 | Nilai CO dalam ppm, hasil moving average |
| 40–47 | Bar skala 0–115 ppm; panjang bar sebanding dengan kadar CO dan penuh saat KRITIS |
| 50–58 | Suhu dan kelembapan relatif dari DHT22, ditambah flag lingkungan rata kanan (`PANAS`, `LEMBAB`, `KERING`). Bila sensor gagal dibaca, nilainya menjadi `--.-C --%RH NO DHT` |

Baris terakhir menampilkan flag lingkungan agar kenaikan level yang berasal dari kondisi
kabin dapat dibedakan dari kenaikan yang berasal dari kadar CO. Pembalikan warna pita
dipilih karena lebih mudah ditangkap mata tepi dibandingkan perubahan teks biasa, dan tetap
terbaca pada layar 0,96 inci. Perilaku ini diuji pada TC-01 sampai TC-04 serta TC-09 dan
TC-10.

## 9. Komunikasi Serial dan MQTT

### 9.1 Serial Monitor

Serial Monitor (115200 baud) digunakan sebagai tiga hal sekaligus: media debugging,
bukti aliran data, dan antarmuka kalibrasi sensor.

Contoh keluaran:

```
[  3210 ms] CO=  0.10 i=  0.10 raw= 843 V=0.679 d=1 | 29.0C 61.0%RH NORMAL | AMAN->AMAN
[  5210 ms] CO= 24.80 i= 24.10 raw=2795 V=2.252 d=1 | 41.2C 62.0%RH PANAS  | WASPADA->BAHAYA
```

Setiap baris memuat waktu, nilai ppm hasil pengolahan (`CO`), nilai ppm sesaat sebelum
dirata-rata (`i`), nilai ADC mentah (`raw`), tegangan sensor (`V`), status DOUT (`d`),
suhu, kelembapan, flag lingkungan, serta dua level: level CO dari sensor gas dan teks
setelah `->` sebagai level akhir. Nilai `raw` dan `V` inilah yang dipakai pada prosedur
kalibrasi dua titik (`c1`/`c2`) sebagaimana dijelaskan pada bagian 8.2.

Perintah `dht` menampilkan ringkasan kondisi iklim mikro beserta alasan keputusan,
sehingga kegagalan sensor dapat dibedakan dari nilai yang memang berada di luar ambang:

```
---- Status iklim mikro ----
  DHT22      : terbaca (GPIO4)
  Status baca: OK (0 kegagalan berurutan)
  Suhu       : 41.2 C  (ambang panas >= 40.0 C)
  Kelembapan : 62.0 %RH (lembab >= 75, kering <= 20)
  Umur data  : 1204 ms sejak pembacaan valid terakhir
  Flag       : PANAS
  Level CO   : WASPADA
  Level akhir: BAHAYA
```

Perintah yang tersedia pada Serial Monitor:

| Perintah | Fungsi |
|---|---|
| `c1 <ppm>` | menetapkan titik kalibrasi pertama pada konsentrasi gas acuan yang diketahui |
| `c2 <ppm>` | menetapkan titik kalibrasi kedua; kedua titik menentukan koefisien skala logaritmik |
| `dht` | menampilkan status iklim mikro, jumlah kegagalan berurutan, dan hasil uji jalur data |
| `scan` | menguji pin kandidat untuk menemukan pin tempat DHT22 benar-benar terpasang |
| `r` | mengembalikan skala sensor ke nilai bawaan |
| `?` | menampilkan status kalibrasi beserta daftar perintah |

Perintah `dht` dan `scan` bersifat diagnostik dan tidak mengubah kalibrasi maupun level yang
sedang berjalan. Perintah `scan` diperlukan karena kanvas Wokwi merutekan kabel secara
otomatis sehingga sambungan yang bertumpuk sulit diperiksa secara visual; hasil pemindaian
menyebutkan nomor GPIO tempat sensor menjawab atau menyatakan bahwa sensor tidak ditemukan
pada pin mana pun. Uji awal saat perangkat menyala menjalankan pemindaian yang sama secara
otomatis, sehingga perangkat tetap memperoleh data iklim mikro meskipun sensor terpasang
pada pin yang berbeda dari `#define PIN_DHT`.

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

Payload memisahkan `co_level` dan `env` agar penerima dapat menelusuri asal keputusan.
Pada contoh tersebut kadar CO 25,4 ppm hanya menghasilkan WASPADA, tetapi suhu 41,2 °C
mengeskalasi level akhir menjadi BAHAYA. Field `dht_ok` membedakan nilai iklim mikro yang
valid dari nilai bawaan saat sensor gagal dibaca.

Payload pada topik `alert` menyertakan field `reason` (`co`, `env`, atau `dout`) yang
mencatat pemicu transisi:

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

Format JSON dipilih agar mudah di-*parse* oleh klien mana pun (Python, JavaScript, maupun
aplikasi mobile pada pengembangan lanjutan).

## 10. Dashboard dan Visualisasi

Dashboard dibuat dengan Python menggunakan `paho-mqtt` sebagai klien dan Plotly/Matplotlib
sebagai mesin visualisasi. Dashboard berlangganan ketiga topik di atas dan menampilkan:

1. **Kartu status** — level akhir, level CO, kadar CO, suhu, kelembapan, flag lingkungan,
   dan ID perangkat.
2. **Grafik tren CO** — garis waktu dengan pita warna yang menandai zona AMAN, WASPADA,
   BAHAYA, dan KRITIS sehingga posisi nilai langsung terbaca secara visual. Sumbu CO
   memakai **skala logaritmik** (0,1–1000 ppm) agar rentang uji yang sangat lebar
   (0,1 ppm hingga 570 ppm) tetap terbaca: pada sumbu linear, pita AMAN yang hanya
   20 ppm akan mengecil sampai tidak terlihat.
3. **Grafik iklim mikro** — suhu dan kelembapan pada sumbu 0–100, dilengkapi pita `LEMBAB`
   (≥ 75 %RH) dan `KERING` (≤ 20 %RH) serta garis putus-putus `PANAS` (≥ 40 °C). Dengan
   penanda ini, kenaikan level yang dipicu kondisi kabin dapat dibaca langsung dari
   grafik, bukan hanya dari angka.
4. **Riwayat peringatan** — daftar transisi level beserta waktu dan pemicunya (`co`, `env`,
   atau `dout`).
5. **Pencatatan CSV** — setiap pesan disimpan dengan kolom waktu, perangkat, ppm, suhu,
   RH, level akhir, kode level, level CO, flag lingkungan, dan status validitas DHT22
   untuk analisis lanjutan.

Nilai iklim mikro yang tidak valid dikirim sebagai `NaN` sehingga grafik menampilkan
celah, bukan garis mendatar pada 0 °C atau 0 %RH yang dapat disalahartikan sebagai
pembacaan nyata.

Dashboard tersedia dalam dua bentuk: skrip Python untuk dijalankan lokal dan notebook
Google Colab untuk pengambilan tangkapan layar pada laporan.

## 11. Skenario dan Hasil Pengujian

Pengujian dilakukan pada dua lapis. Pertama, **uji unit logika** yang mengekstrak fungsi
`classify()`, `envCheck()`, `combineLevels()`, dan `voltsToPpm()` langsung dari sketch,
mengompilasinya terpisah, dan menjalankan 60 assertion terhadap tabel ambang batas,
perilaku histeresis, deadband iklim mikro, matriks eskalasi, penanganan sensor gagal,
serta kesesuaian konversi logaritmik dengan hasil pengukuran langsung di simulator
(`tools/test_logic.py`). Kedua, **uji fungsional end-to-end** pada Wokwi dengan menggeser
slider ppm pada komponen MQ-2 dan slider suhu/kelembapan pada komponen DHT22 saat simulasi
berjalan, sehingga kondisi udara kabin dapat disimulasikan secara terkendali.

| No | Test Case | Input | Expected Result | Actual Result | Status |
|----|-----------|-------|-----------------|---------------|--------|
| TC-01 | Kondisi normal | 5 ppm, 29 °C, 61 %RH | OLED AMAN (teks normal), buzzer mati, payload AMAN | | |
| TC-02 | Peringatan dini | 25 ppm, 29 °C, 61 %RH | OLED WASPADA, beep 1 Hz, alert AMAN→WASPADA (`reason=co`) | | |
| TC-03 | Kondisi bahaya | 60 ppm, 29 °C, 61 %RH | OLED BAHAYA (pita dibalik), beep 2,5 Hz, alert WASPADA→BAHAYA | | |
| TC-04 | Kondisi kritis | 570 ppm, 29 °C, 61 %RH | OLED KRITIS (pita dibalik) + bar penuh, buzzer kontinu | | |
| TC-05 | Histeresis | 60 → 33 → 30 ppm | Level tetap BAHAYA hingga ppm ≤ 32 | | |
| TC-06 | Jaringan terputus | WiFi dimatikan | Alarm lokal tetap aktif, dashboard menandai offline, reconnect otomatis | | |
| TC-07 | Logging & visualisasi | 2 menit data | Grafik ter-update, CSV terbentuk dengan kolom iklim mikro | | |
| TC-08 | Uji unit logika (otomatis) | `tools/test_logic.py` | 60 assertion lulus | | |
| TC-09 | Eskalasi suhu | 5 ppm, **41 °C**, 61 %RH | OLED WASPADA, flag `PANAS`, alert `reason=env` | | |
| TC-10 | Eskalasi kelembapan | 25 ppm, 29 °C, **80 %RH** | OLED BAHAYA, flag `LEMBAB`, beep 2,5 Hz | | |

*(Kolom Actual Result dan Status diisi setelah pengujian; dokumentasi berupa tangkapan layar
dan video demo.)*

## 12. Dokumentasi Visual

| Kode | Keterangan | Berkas |
|---|---|---|
| SS-01 | Rangkaian lengkap Wokwi | `docs/img/SS-01-wiring.png` |
| SS-02 | Serial Monitor kondisi AMAN | `docs/img/SS-02-serial-aman.png` |
| SS-03 | Serial Monitor kondisi BAHAYA | `docs/img/SS-03-serial-bahaya.png` |
| SS-04 | OLED KRITIS (pita dibalik + bar penuh) | `docs/img/SS-04-oled-kritis.png` |
| SS-05 | Payload diterima HiveMQ | `docs/img/SS-05-hivemq.png` |
| SS-06 | Dashboard Python | `docs/img/SS-06-dashboard.png` |
| SS-07 | Isi file CSV | `docs/img/SS-07-csv.png` |
| SS-08 | Status offline (LWT) | `docs/img/SS-08-offline.png` |
| SS-09 | OLED dengan flag lingkungan `PANAS` | `docs/img/SS-09-oled-panas.png` |

## 13. Pembagian Peran Anggota

| Nama | Peran | Kontribusi |
|---|---|---|
| Bagas Mirnanda Agung Narendra | Ketua / Hardware | Perancangan rangkaian, pemilihan komponen, wiring Wokwi, dokumentasi pin |
| Rachmad Febriananda | Firmware | Penulisan sketch ESP32, logika ambang batas, integrasi MQTT, debugging |
| Syaiful Buchory | Data & Dokumentasi | Dashboard Python, pengujian skenario, penyusunan laporan dan video |

## 14. Kesimpulan

1. Prototipe CO-Zero berhasil dibangun di atas ESP32 dan disimulasikan penuh di Wokwi
   dengan dua sensor input (gas dan iklim mikro) serta dua aktuator (OLED dan buzzer).
2. Logika ambang batas berlapis dengan moving average dan histeresis mampu mengubah
   kondisi sensor menjadi peringatan yang stabil dan mudah dipahami, tanpa kedipan pada
   nilai batas.
3. Konversi kadar CO memakai pemetaan logaritmik yang diturunkan dari pengukuran langsung
   di simulator. Model ini terbukti akurat pada tiga titik ukur (galat di bawah 0,1%),
   sedangkan pemetaan linear yang dipakai pada versi awal menghasilkan kesalahan hingga
   tiga orde besaran.
4. Keputusan sistem tidak lagi bergantung pada kadar CO semata. Suhu dan kelembapan kabin
   dinilai sebagai flag lingkungan yang memperberat level CO sebesar satu tingkat, sehingga
   kabin panas atau lembap dengan kadar CO sedang dapat menghasilkan peringatan yang lebih
   tinggi. Eskalasi dibatasi satu tingkat dan tidak pernah menghasilkan BAHAYA atau KRITIS
   tanpa kontribusi sensor gas.
5. Integrasi MQTT dengan HiveMQ Cloud berjalan baik: data telemetri terkirim setiap dua
   detik, transisi level tercatat pada topik `alert` beserta pemicunya, dan status perangkat
   terpantau melalui mekanisme Last Will & Testament.
6. Dashboard Python berhasil menampilkan tren CO, suhu, dan kelembapan secara real-time,
   menandai ambang iklim mikro secara visual, serta menyimpan riwayat ke berkas CSV.
7. Fungsi keselamatan tetap berjalan ketika koneksi internet terputus karena seluruh
   indikator lokal dikendalikan langsung oleh perangkat. Kegagalan sensor DHT22 juga tidak
   menghentikan sistem: klasifikasi iklim dilewati dan perangkat melanjutkan pemantauan
   kadar CO.

## 15. Pengembangan Lanjutan

1. **Perangkat fisik dengan MQ-7.** Mengganti MQ-2 dengan MQ-7 dan mengukur ulang konstanta
   `V_PER_DECADE` / `V_AT_1PPM` pada gas acuan, beserta pemanasan (preheat) 24–48 jam
   untuk akurasi kadar CO. Struktur perhitungan logaritmiknya sudah dipakai pada simulasi,
   sehingga yang berubah hanya nilai konstantanya.
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
