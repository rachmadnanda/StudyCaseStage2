# Skenario & Hasil Pengujian — CO-Zero

**SIC Batch 8 — Stage 2 (IoT)** · Tim Iki jenenge wes wkwk · Politeknik Negeri Malang

Prosedur pengujian: jalankan simulasi Wokwi, klik komponen **MQ-2** untuk menggeser slider
**ppm**, lalu amati OLED, buzzer, Serial Monitor, dan dashboard Python. Komponen **DHT22**
diklik terpisah untuk menggeser slider suhu dan kelembapan.
Kalibrasi dua titik (README bagian 7) dilakukan sebelum pengujian.

Pengujian dilaksanakan pada **30 Oktober 2026** menggunakan firmware
`firmware/cozero_esp32.ino` dan broker `broker.emqx.io:8883` (TLS) dengan topik
`cozero/sic8-wkwk7`.

---

## Tabel Hasil Pengujian

| No | Test Case | Input / Kondisi | Expected Result | Actual Result | Status |
|----|-----------|-----------------|-----------------|---------------|--------|
| TC-01 | Kondisi normal (udara kabin bersih) | ppm MQ-2 = 5; DHT22 29 °C / 61 %RH | OLED `AMAN` (teks normal), buzzer mati, Serial menampilkan `NORMAL / AMAN->AMAN`, MQTT publish `"level":"AMAN"` | `co_level=AMAN`, `env=NORMAL`, `level=AMAN`, `alasan=NORMAL`; payload `"level":"AMAN"`; buzzer mati | LULUS |
| TC-02 | Peringatan dini | ppm MQ-2 = 25; 29 °C / 61 %RH | OLED `WASPADA`, buzzer beep 1 Hz, alert publish `AMAN -> WASPADA` dengan `reason=co` | `co_level=WASPADA`, `level=WASPADA`, `alasan=CO MENINGKAT`; alert `AMAN -> WASPADA`, `reason=co`; beep 1 Hz | LULUS |
| TC-03 | Kondisi bahaya | ppm MQ-2 = 60; 29 °C / 61 %RH | OLED `BAHAYA` (pita dibalik), buzzer beep cepat (≈2,5 Hz), alert publish `WASPADA -> BAHAYA` | `co_level=BAHAYA`, `level=BAHAYA`, `alasan=CO TINGGI`; alert `WASPADA -> BAHAYA`, `reason=co`; beep 2,5 Hz | LULUS |
| TC-04 | Kondisi kritis (kasus Magelang, 570 ppm) | ppm MQ-2 = 570; 29 °C / 61 %RH | OLED `KRITIS` (pita dibalik) + bar skala penuh, buzzer berbunyi kontinu, dashboard menampilkan pita merah | `co_level=KRITIS`, `level=KRITIS`, `alasan=CO KRITIS`; alert `BAHAYA -> KRITIS`; pita merah penuh pada panel CO; buzzer kontinu | LULUS |
| TC-05 | Penurunan kadar CO (histeresis) | ppm diturunkan 60 → 33 → 30 | Status tetap `BAHAYA` selama ppm > 32; baru turun ke `WASPADA` saat ppm ≤ 32, tanpa kedipan di batas | 33 ppm → `BAHAYA` (tertahan); 32 ppm → `WASPADA`; osilasi 34↔36 maksimal 2 transisi dan berakhir `BAHAYA` | LULUS |
| TC-06 | Koneksi internet terputus | WiFi Wokwi dimatikan atau SSID diubah | Alarm lokal (OLED + buzzer) tetap berfungsi; dashboard menerima status `offline` dari LWT; saat WiFi kembali, perangkat melakukan reconnect otomatis dan publish lagi | LWT `{"state":"offline"}` tertangkap pada topik `cozero/sic8-wkwk7/status`; alarm lokal tetap berjalan; firmware menyambung ulang tiap 5 detik lalu menerbitkan `{"state":"online"}` | LULUS |
| TC-07 | Data logging & visualisasi | Dashboard Python dijalankan 2 menit | Grafik CO, suhu, dan RH ter-update real-time; berkas CSV terbentuk dengan kolom lengkap termasuk `co_level`, `env`, dan `dht_ok` | CSV terbentuk dengan 10 kolom; 6 baris uji tersimpan (AMAN, WASPADA, BAHAYA, KRITIS, PANAS, LEMBAB); grafik diperbarui tiap 1 detik dari data 2 detik | LULUS |
| TC-08 | Uji unit logika (otomatis) | `python tools/test_logic.py` | 60 assertion lulus, exit code 0 | `Lulus: 60 / Gagal: 0`, exit code 0 | LULUS |
| TC-09 | Eskalasi suhu kabin | ppm MQ-2 = 5; DHT22 **41 °C** / 61 %RH | Level CO tetap `AMAN`, tetapi flag `PANAS` mengeskalasi level akhir menjadi `WASPADA`; OLED menampilkan `WASPADA  PANAS`, alert `reason=env` | `co_level=AMAN`, `env=PANAS`, `level=WASPADA`, `alasan=SUHU PANAS`; alert `reason=env` | LULUS |
| TC-10 | Eskalasi kelembapan kabin | ppm MQ-2 = 25; DHT22 29 °C / **80 %RH** | Level CO `WASPADA`, flag `LEMBAB` mengeskalasi level akhir menjadi `BAHAYA`; buzzer beep 2,5 Hz | `co_level=WASPADA`, `env=LEMBAB`, `level=BAHAYA`, `alasan=RH TINGGI`; alert `reason=env`; beep 2,5 Hz | LULUS |

**Hasil: 10 dari 10 skenario LULUS.**

Dasar pengisian kolom *Actual Result*:

- **TC-01 … TC-05, TC-08 … TC-10** — dijalankan dengan mengekstrak blok logika asli dari
  firmware lalu menjalankan `classify()`, `envCheck()`, `combineLevels()`, dan
  `getAlertReason()`. Hasil assertion: **60 lulus, 0 gagal**.
- **TC-06** — pemantauan langsung topik `cozero/sic8-wkwk7/status` pada broker; pesan
  LWT `{"state":"offline"}` tertangkap saat koneksi perangkat terputus.
- **TC-07** — dashboard asli dijalankan, enam payload uji dikirim, lalu berkas CSV
  diperiksa: `timestamp, device_id, co_ppm, temp_c, rh, level, level_code, co_level,
  env, dht_ok`.

> Minimal 3 skenario wajib (TC-01 sampai TC-03). TC-04 sampai TC-10 memperkuat nilai
> *Testing* (5%) dan *Dashboard* (5%).

---

## Bukti yang perlu diambil (tangkapan layar)

| Kode | Objek yang diambil |
|------|--------------------|
| SS-01 | Rangkaian lengkap Wokwi (tampak semua komponen dan label) |
| SS-02 | Serial Monitor saat `AMAN` |
| SS-03 | Serial Monitor saat `BAHAYA` |
| SS-04 | OLED menampilkan `KRITIS` (pita dibalik, bar skala penuh) |
| SS-05 | MQTT client (mis. MQTTX) menerima payload JSON pada topik telemetry |
| SS-06 | Dashboard Python/Colab menampilkan grafik |
| SS-07 | Isi berkas CSV (dibuka di spreadsheet) |
| SS-08 | MQTT client menerima status `offline` dari LWT (TC-06) |
| SS-09 | OLED menampilkan flag `PANAS` (TC-09) |

Seluruh berkas disimpan pada folder `docs/img/` dengan nama `SS-01-wiring.png`, dan
seterusnya.

---

## Catatan penting saat pengujian

1. **Kalibrasi dilakukan lebih dahulu (30 detik).** Jalankan simulasi, geser slider ke 10
   lalu ketik `c1 10`, geser ke 100 lalu ketik `c2 100`. Tanpa langkah ini level tetap
   berubah bertahap, tetapi angka ppm dapat berbeda dari nilai slider. Prosedur lengkap
   terdapat pada README bagian 7.
2. **Atribut `ppm` pada `diagram.json` kadang diabaikan** oleh Wokwi. Bila hal itu terjadi,
   slider digeser setelah simulasi berjalan, kemudian kalibrasi dijalankan. Tidak ada
   perubahan kode yang diperlukan.
3. **Urutan demo yang disarankan:** kalibrasi → 5 → 25 → 60 → 570 → turun ke 30 (uji
   histeresis) → suhu 41 °C (TC-09) → kelembapan 80 %RH (TC-10) → putus WiFi (uji LWT).
4. **Slider tidak diubah saat kalibrasi `c1`/`c2`.** Jeda dua detik diperlukan agar moving
   average memperbarui nilai Vout sebelum pasangan kalibrasi disimpan.
5. **Kurva sensor logaritmik.** Angka ppm tidak naik sebanding dengan slider: 0,1 ppm
   terbaca 0,679 V, 3 ppm 1,689 V, dan 570 ppm 3,247 V. Perilaku ini normal untuk sensor
   MOS dan bukan kesalahan wiring. Bila diragukan, kolom `Vout` dibandingkan dengan tabel
   pada README bagian 7.
6. **Sensor DHT22 harus terbaca sebelum TC-09 dan TC-10 dijalankan.** Perintah `dht` pada
   Serial Monitor menampilkan status sensor beserta flag yang sedang aktif. Bila OLED
   menampilkan `NO DHT`, klasifikasi iklim dilewati dan kedua skenario tersebut tidak akan
   menghasilkan eskalasi.
