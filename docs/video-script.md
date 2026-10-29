# Skrip Video Demo — CO-Zero

**Durasi target: 4 menit** · Format: rekaman layar (Wokwi + Colab) dengan narasi voice-over
Resolusi 1080p, kursor disorot, tanpa kamera wajah.

---

## Persiapan sebelum perekaman (10 menit)

1. Wokwi: simulasi sudah berjalan dan Serial Monitor terbuka.
2. **Kalibrasi 30 detik**: slider digeser ke 10 lalu `c1 10` diketik; slider digeser ke 100
   lalu `c2 100` diketik; perintah `?` dijalankan untuk memastikan `vPerDecade` ≈ 0,68
   V/dekade.
3. Slider dikembalikan ke **5 ppm** (kondisi awal AMAN).
4. Colab: cell konfigurasi dan koneksi sudah dijalankan, status `connected`.
5. HiveMQ Web Client terbuka pada tab lain dan sudah berlangganan `cozero/team/#`.
6. Tab dan notifikasi lain ditutup. Perbesaran peramban 110% agar teks terbaca.
7. Perekaman menggunakan OBS atau GNOME Screencast, dengan **audio terpisah** agar narasi
   dapat direkam ulang tanpa mengulang rekaman layar.

---

## Shot list

| # | Waktu | Visual | Narasi (inti) |
|---|---|---|---|
| 1 | 0:00–0:25 | Slide judul: CO-Zero, tim, institusi | "Karbon monoksida tidak berwarna dan tidak berbau. Setiap tahun terdapat keluarga yang meninggal di dalam mobil karena kadar CO di kabin meningkat tanpa disadari. CO-Zero adalah sistem peringatan dini berbasis ESP32." |
| 2 | 0:25–0:55 | Foto atau ilustrasi kasus (Brexit 2016, Magelang 2025) | "Pada 2025, dua orang ditemukan meninggal di Magelang dengan kadar CO 570 ppm, lima kali ambang aman. Mobil kelas menengah umumnya tidak memiliki detektor CO." |
| 3 | 0:55–1:20 | Block diagram pada laporan | "Alurnya: sensor MQ-2 membaca CO, DHT22 membaca suhu dan kelembapan. ESP32 mengolah kedua masukan tersebut, menampilkan status di OLED, membunyikan buzzer, dan mengirim data ke HiveMQ melalui MQTT." |
| 4 | 1:20–1:50 | Rangkaian Wokwi, sorot setiap komponen | "Seluruh komponen disimulasikan di Wokwi: ESP32, MQ-2, DHT22, OLED, dan buzzer. Lima komponen tanpa LED agar rangkaian mudah diperiksa. Pada perangkat fisik ditambahkan pembagi tegangan 10 kilo-ohm karena keluaran MQ-2 dapat mencapai 5 volt sedangkan ADC ESP32 dibatasi 3,3 volt." |
| 5 | 1:50–2:20 | OLED dan Serial Monitor kondisi AMAN | "Saat simulasi dimulai, sistem membaca kadar CO di bawah 20 ppm. Statusnya AMAN dan buzzer diam. Skala sensor dikalibrasi dua titik melalui Serial Monitor sehingga angka ppm sesuai dengan nilai acuan." |
| 6 | 2:20–2:50 | Slider digeser ke 25 lalu 60 | "Ketika kadar naik ke 25 ppm, status berubah menjadi WASPADA dan buzzer berbunyi satu kali per detik. Pada 60 ppm status menjadi BAHAYA: pita status di OLED berubah menjadi putih, bar skala memanjang, dan buzzer berbunyi lebih cepat." |
| 7 | 2:50–3:10 | Slider digeser ke 570, sorot OLED | "Pada 570 ppm, angka yang sama dengan kasus Magelang, status menjadi KRITIS dengan bar skala penuh dan buzzer berbunyi terus." |
| 8 | 3:10–3:35 | Slider suhu DHT22 digeser ke 41 °C | "Sistem juga memperhitungkan kondisi kabin. Pada kadar CO yang hanya 5 ppm, suhu kabin 41 derajat Celsius mengeskalasi status menjadi WASPADA. Flag PANAS tampil di OLED, dan payload menyertakan alasan eskalasi." |
| 9 | 3:35–3:55 | Tab HiveMQ Web Client | "Bersamaan dengan itu, ESP32 mempublikasikan JSON ke HiveMQ setiap dua detik melalui topik telemetry, alert saat status berubah, dan status dengan Last Will and Testament." |
| 10 | 3:55–4:15 | Dashboard Colab | "Dashboard Python menampilkan tren CO pada skala logaritmik lengkap dengan pita ambang batas, serta panel suhu dan kelembapan dengan penanda kondisi ekstrem. Data juga disimpan ke CSV untuk analisis lanjutan." |
| 11 | 4:15–4:35 | Putus WiFi (SSID diubah) | "Ketika koneksi internet diputus, alarm lokal tetap bekerja sehingga keselamatan tidak bergantung pada jaringan. Dashboard menandai perangkat offline, dan sistem menyambung ulang secara otomatis." |
| 12 | 4:35–4:55 | Slide penutup: hasil uji dan pengembangan | "Sepuluh skenario pengujian dan enam puluh assertion unit lulus. Pengembangan berikutnya mencakup sensor MQ-7 pada perangkat fisik, kalibrasi Rs/R0, dan notifikasi ke aplikasi mobile." |

---

## Catatan produksi

- Rekaman suara buzzer dibatasi 3–5 detik per level agar tidak mengganggu narasi.
- Pada setiap perpindahan level, tahan gambar selama 2 detik agar penonton sempat membaca
  status.
- Nomor test case (TC-01, TC-02, dan seterusnya) ditampilkan sebagai overlay saat demo untuk
  memenuhi kriteria *Testing* dan *Video Demo* (10%).
- Teks berikut ditampilkan di bawah layar minimal 8 detik: *"Simulasi menggunakan MQ-2
  karena MQ-7 tidak tersedia di Wokwi; keduanya sensor MOS dengan keluaran analog."*
- Ekspor: MP4 H.264, 1080p, bitrate 6–8 Mbps. Nama berkas:
  `Video-Demo-CO-Zero-Iki-Jenenge-Wes-Wkwk.mp4`.
