# Skenario & Hasil Pengujian — CO-Zero

**SIC Batch 8 — Stage 2 (IoT)** · Tim Iki jenenge wes wkwk · Politeknik Negeri Malang

Prosedur pengujian: jalankan simulasi Wokwi, klik komponen **MQ-2** untuk menggeser slider
**ppm**, lalu amati OLED, buzzer, Serial Monitor, dan dashboard Python. Komponen **DHT22**
diklik terpisah untuk menggeser slider suhu dan kelembapan.
Kolom **Actual Result** dan **Status** diisi setelah pengujian dilakukan.

---

## Tabel Hasil Pengujian

| No | Test Case | Input / Kondisi | Expected Result | Actual Result | Status |
|----|-----------|-----------------|-----------------|---------------|--------|
| TC-01 | Kondisi normal (udara kabin bersih) | ppm MQ-2 = 5; DHT22 29 °C / 61 %RH | OLED `AMAN` (teks normal), buzzer mati, Serial menampilkan `NORMAL | AMAN->AMAN`, MQTT publish `"level":"AMAN"` | | |
| TC-02 | Peringatan dini | ppm MQ-2 = 25; 29 °C / 61 %RH | OLED `WASPADA`, buzzer beep 1 Hz, alert publish `AMAN -> WASPADA` dengan `reason=co` | | |
| TC-03 | Kondisi bahaya | ppm MQ-2 = 60; 29 °C / 61 %RH | OLED `BAHAYA` (pita dibalik), buzzer beep cepat (≈2,5 Hz), alert publish `WASPADA -> BAHAYA` | | |
| TC-04 | Kondisi kritis (kasus Magelang, 570 ppm) | ppm MQ-2 = 570; 29 °C / 61 %RH | OLED `KRITIS` (pita dibalik) + bar skala penuh, buzzer berbunyi kontinu, dashboard menampilkan pita merah | | |
| TC-05 | Penurunan kadar CO (histeresis) | ppm diturunkan 60 → 33 → 30 | Status tetap `BAHAYA` selama ppm > 32; baru turun ke `WASPADA` saat ppm ≤ 32, tanpa kedipan di batas | | |
| TC-06 | Koneksi internet terputus | WiFi Wokwi dimatikan atau SSID diubah | Alarm lokal (OLED + buzzer) tetap berfungsi; dashboard menerima status `offline` dari LWT; saat WiFi kembali, perangkat melakukan reconnect otomatis dan publish lagi | | |
| TC-07 | Data logging & visualisasi | Dashboard Python dijalankan 2 menit | Grafik CO, suhu, dan RH ter-update real-time; berkas CSV terbentuk dengan kolom lengkap termasuk `co_level`, `env`, dan `dht_ok` | | |
| TC-08 | Uji unit logika (otomatis) | `python tools/test_logic.py` | 60 assertion lulus, exit code 0 | | |
| TC-09 | Eskalasi suhu kabin | ppm MQ-2 = 5; DHT22 **41 °C** / 61 %RH | Level CO tetap `AMAN`, tetapi flag `PANAS` mengeskalasi level akhir menjadi `WASPADA`; OLED menampilkan `WASPADA  PANAS`, alert `reason=env` | | |
| TC-10 | Eskalasi kelembapan kabin | ppm MQ-2 = 25; DHT22 29 °C / **80 %RH** | Level CO `WASPADA`, flag `LEMBAB` mengeskalasi level akhir menjadi `BAHAYA`; buzzer beep 2,5 Hz | | |

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
| SS-05 | HiveMQ Web Client menerima payload JSON |
| SS-06 | Dashboard Python/Colab menampilkan grafik |
| SS-07 | Isi berkas CSV (dibuka di spreadsheet) |
| SS-08 | Halaman HiveMQ saat perangkat `offline` (TC-06) |
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
