# Skenario & Hasil Pengujian — CO-Zero

**SIC Batch 8 — Stage 2 (IoT)** · Tim Iki jenenge wes wkwk · Politeknik Negeri Malang

Cara uji: jalankan simulasi Wokwi → klik komponen **MQ-2** → geser slider **ppm** →
amati LED, buzzer, OLED, Serial Monitor, dan dashboard Python.
Isi kolom **Actual Result** dan **Status** saat pengujian (atau tempel hasil yang sudah terverifikasi).

---

## Tabel Hasil Pengujian

| No | Test Case | Input / Kondisi | Expected Result | Actual Result | Status |
|----|-----------|-----------------|-----------------|---------------|--------|
| TC-01 | Kondisi normal (udara kabin bersih) | ppm MQ-2 = 5 | LED hijau ON, buzzer mati, OLED `AMAN`, Serial `CO≈0.0 ppm`, MQTT publish `"level":"AMAN"` | | |
| TC-02 | Peringatan dini | ppm MQ-2 = 25 | LED kuning ON, buzzer beep 1 Hz, OLED `WASPADA`, alert publish `AMAN -> WASPADA` | | |
| TC-03 | Kondisi bahaya | ppm MQ-2 = 60 | LED merah ON, buzzer beep cepat (≈2.5 Hz), OLED `BAHAYA`, alert publish `WASPADA -> BAHAYA` | | |
| TC-04 | Kondisi kritis (kasus Magelang, 570 ppm) | ppm MQ-2 = 570 | LED merah ON, buzzer berbunyi kontinu, OLED `KRITIS`, dashboard menampilkan pita merah | | |
| TC-05 | Penurunan kadar CO (histeresis) | ppm diturunkan 60 → 33 → 30 | Status tetap `BAHAYA` selama ppm > 32; baru turun ke `WASPADA` saat ppm ≤ 32, tanpa kedipan di batas | | |
| TC-06 | Koneksi internet terputus | Matikan WiFi Wokwi (atau ubah SSID) | Alarm lokal (LED + buzzer + OLED) tetap berfungsi; dashboard menerima status `offline` dari LWT; saat WiFi kembali, device reconnect otomatis dan publish lagi | | |
| TC-07 | Data logging & visualisasi | Jalankan dashboard Python 2 menit | Grafik CO, suhu, dan RH ter-update real-time; file CSV terbentuk dengan kolom lengkap | | |
| TC-08 | Uji unit logika (otomatis) | `python tools/test_logic.py` | 21 assertion lulus, exit code 0 | | |

> Minimal 3 skenario wajib (TC-01 s.d. TC-03). TC-04…TC-08 memperkuat nilai *Testing* (5%) dan *Dashboard* (5%).

---

## Bukti yang perlu diambil (screenshot)

| Kode | Yang difoto |
|------|-------------|
| SS-01 | Rangkaian lengkap Wokwi (tampak semua komponen + label) |
| SS-02 | Serial Monitor saat `AMAN` |
| SS-03 | Serial Monitor saat `BAHAYA` |
| SS-04 | OLED menampilkan `KRITIS` + LED merah menyala |
| SS-05 | HiveMQ Web Client menerima payload JSON |
| SS-06 | Dashboard Python/Colab menampilkan grafik |
| SS-07 | Isi file CSV (buka di spreadsheet) |
| SS-08 | Halaman HiveMQ saat device `offline` (TC-06) |

Simpan semua di folder `docs/img/` dengan nama `SS-01-wiring.png`, dst.

---

## Catatan penting saat pengujian

1. **Kalibrasi dulu (30 detik).** Jalankan simulasi, geser slider ke 100 → ketik `c1 100`,
   geser ke 500 → ketik `c2 500`. Tanpa langkah ini, level tetap berubah bertahap tetapi
   angka ppm bisa berbeda dari nilai slider. Lihat README bagian 7.
2. **Atribut `ppm` di `diagram.json` kadang diabaikan** oleh Wokwi (simulasi mulai dari
   400 ppm). Kalau itu terjadi, cukup geser slider ke **5** setelah simulasi berjalan,
   lalu kalibrasi. Tidak ada perubahan kode yang diperlukan.
3. **Urutan demo yang disarankan:** kalibrasi → 5 → 25 → 60 → 570 → turun ke 30 (uji
   histeresis) → putus WiFi (uji LWT).
4. **Jangan mengubah slider saat kalibrasi `c1`/`c2`** — tunggu 2 detik setelah menggeser
   agar moving average ikut memperbarui nilai Vout.
