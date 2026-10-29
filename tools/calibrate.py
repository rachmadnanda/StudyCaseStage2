#!/usr/bin/env python3
"""
Alat bantu kalibrasi dua titik untuk CO-Zero.

Dipakai SETELAH simulasi Wokwi berjalan dan Serial Monitor menampilkan
baris seperti:

    [  5210 ms] CO=  24.8 ppm (raw= 512 Vout=0.83V dout=1) | 29.1C 61% | WASPADA

Langkah:
  1. Geser slider ppm sensor ke 100, tunggu 2 detik, catat nilai Vout.
  2. Geser slider ppm sensor ke 500, tunggu 2 detik, catat nilai Vout.
  3. Jalankan:
        python tools/calibrate.py --p1 100 --v1 0.50 --p2 500 --v2 2.50
  4. Skrip mencetak dua nilai yang harus dimasukkan ke bagian KONFIGURASI sketch:
        PPM_PER_VOLT_DEFAULT  dan  BASELINE_VOLT_DEFAULT

Catatan: titik acuan sengaja dipilih di daerah linear ADC (100 dan 500 ppm).
Tanpa pembagi tegangan, ADC ESP32 jenuh di sekitar 3,1-3,3 V sehingga titik
acuan yang terlalu tinggi (mis. 900 ppm) menghasilkan kalibrasi yang salah.

Alternatif yang lebih cepat: kalibrasi langsung dari Serial Monitor dengan
perintah `c1 100` dan `c2 500` (lihat README bagian 7).
"""

import argparse


def main():
    ap = argparse.ArgumentParser(description="Kalibrasi dua titik sensor CO-Zero")
    ap.add_argument("--p1", type=float, required=True, help="ppm titik 1 (mis. 100)")
    ap.add_argument("--v1", type=float, required=True, help="Vout pada titik 1 (volt)")
    ap.add_argument("--p2", type=float, required=True, help="ppm titik 2 (mis. 500)")
    ap.add_argument("--v2", type=float, required=True, help="Vout pada titik 2 (volt)")
    args = ap.parse_args()

    if abs(args.v2 - args.v1) < 1e-6:
        raise SystemExit("Vout titik 1 dan 2 sama — geser slider lebih jauh.")

    k = (args.p2 - args.p1) / (args.v2 - args.v1)
    baseline = args.v1 - (args.p1 / k)

    print("\n=== Hasil kalibrasi ===")
    print(f"#define PPM_PER_VOLT_DEFAULT  {k:.2f}f")
    print(f"#define BASELINE_VOLT_DEFAULT {baseline:.4f}f")
    print("\nVerifikasi:")
    for ppm, v in ((args.p1, args.v1), (args.p2, args.v2)):
        back = (v - baseline) * k
        print(f"  Vout {v:.2f} V  ->  {back:6.1f} ppm  (target {ppm})")
    print("\nTempel ke sketch, lalu restart simulasi (slider kembali ke 5 ppm).")


if __name__ == "__main__":
    main()
