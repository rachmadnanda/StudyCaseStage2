# Skrip Video Demo — CO-Zero

**Durasi target: 4 menit** · Format: rekaman layar (Wokwi + Colab) + narasi voice-over
Resolusi 1080p, cursor disorot, tidak perlu kamera wajah.

---

## Persiapan sebelum merekam (10 menit)

1. Wokwi: project sudah jalan, Serial Monitor terbuka.
2. **Kalibrasi 30 detik**: slider ke 100 → ketik `c1 100`; slider ke 500 → ketik `c2 500`;
   ketik `?` dan pastikan `ppmPerVolt` sudah masuk akal.
3. Geser slider kembali ke **5 ppm** (kondisi awal AMAN).
4. Colab: cell konfigurasi & koneksi sudah dijalankan, status `connected`.
5. HiveMQ Web Client terbuka di tab lain, sudah subscribe `cozero/team/#`.
6. Tutup tab/notifikasi lain. Zoom browser 110% agar teks terbaca.
7. Rekam dengan OBS (atau GNOME Screencast), **audio terpisah** agar bisa re-take narasi.

---

## Shot list

| # | Waktu | Visual | Narasi (inti) |
|---|---|---|---|
| 1 | 0:00–0:25 | Slide judul: CO-Zero, tim, institusi | "Karbon monoksida tidak berwarna dan tidak berbau. Setiap tahun ada keluarga yang meninggal di dalam mobil karena kadar CO di kabin meningkat tanpa disadari. Kami membuat CO-Zero, sistem peringatan dini berbasis ESP32." |
| 2 | 0:25–0:55 | Foto/ilustrasi kasus (Brexit 2016, Magelang 2025) | "Pada 2025, dua orang ditemukan meninggal di Magelang dengan kadar CO 570 ppm — lima kali ambang aman. Mobil kelas menengah tidak punya detektor CO." |
| 3 | 0:55–1:15 | Block diagram di laporan | "Alurnya: sensor MQ-2 membaca CO, DHT22 membaca suhu dan kelembapan. ESP32 mengolah dengan logika ambang batas, lalu menyalakan LED dan buzzer, dan mengirim data ke HiveMQ lewat MQTT." |
| 4 | 1:15–1:45 | Rangkaian Wokwi, sorot tiap komponen | "Semua komponen disimulasikan di Wokwi. Perhatikan pembagi tegangan 10 kilo-ohm: keluaran MQ-2 bisa mencapai 5 volt, sedangkan ADC ESP32 hanya 3,3 volt." |
| 5 | 1:45–2:15 | Serial Monitor kondisi AMAN | "Saat simulasi dimulai, sistem membaca kadar CO di bawah 20 ppm. Statusnya AMAN, LED hijau menyala. Skala sensor dikalibrasi dua titik lewat Serial Monitor, jadi angka ppm yang tampil sesuai dengan acuan." |
| 6 | 2:15–2:45 | Geser slider ke 25 → 60 | "Ketika kadar naik ke 25 ppm, status berubah WASPADA, buzzer berbunyi satu kali per detik. Di 60 ppm, status BAHAYA, buzzer makin cepat, LED merah menyala." |
| 7 | 2:45–3:05 | Geser ke 570, sorot OLED | "Pada 570 ppm — angka yang sama dengan kasus Magelang — status KRITIS dan buzzer berbunyi terus. Ini peringatan yang tidak bisa diabaikan pengemudi." |
| 8 | 3:05–3:30 | Tab HiveMQ Web Client | "Bersamaan dengan itu, ESP32 mempublikasikan JSON ke HiveMQ setiap dua detik. Ada topik telemetry, alert saat status berubah, dan status dengan Last Will Testament." |
| 9 | 3:30–3:55 | Dashboard Colab | "Dashboard Python menampilkan tren CO real-time lengkap dengan pita ambang batas. Data juga disimpan ke CSV untuk analisis lanjutan." |
| 10 | 3:55–4:15 | Putus WiFi (ubah SSID) | "Ketika koneksi internet diputus, alarm lokal tetap bekerja — keselamatan tidak bergantung pada jaringan. Dashboard menandai perangkat offline, dan sistem menyambung ulang otomatis." |
| 11 | 4:15–4:35 | Slide penutup: hasil uji + pengembangan | "Tujuh skenario pengujian lulus. Pengembangan berikutnya: sensor MQ-7 pada perangkat fisik, kurva kalibrasi Rs/R0, dan notifikasi ke aplikasi mobile." |

---

## Tips

- **Jangan** merekam suara simulasi buzzer terlalu lama — cukup 3–5 detik per level.
- Setiap perpindahan level, **berhenti 2 detik** agar penonton sempat membaca status.
- Tampilkan **nomor test case** (TC-01, TC-02, …) sebagai overlay saat demo — ini
  langsung memenuhi kriteria *Testing* dan *Video Demo* (10%).
- Tambahkan teks di bawah layar: *"Simulasi menggunakan MQ-2 karena MQ-7 tidak tersedia
  di Wokwi; keduanya sensor MOS dengan keluaran analog."* Munculkan minimal 8 detik.
- Export: MP4 H.264, 1080p, bitrate 6–8 Mbps. Nama file:
  `Video-Demo-CO-Zero-Iki-Jenenge-Wes-Wkwk.mp4`.
