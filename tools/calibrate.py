#!/usr/bin/env python3
"""
Alat bantu kalibrasi dua titik untuk CO-Zero.

Skrip ini dijalankan setelah simulasi Wokwi berjalan dan Serial Monitor
menampilkan baris seperti:

    [  5210 ms] CO= 24.80 i= 24.10 raw=2795 V=2.252 d=1 | 41.2C 62.0%RH PANAS  | WASPADA->BAHAYA

Prosedur:
  1. Slider ppm sensor digeser ke 10, ditunggu 2 detik, nilai Vout dicatat.
  2. Slider ppm sensor digeser ke 100, ditunggu 2 detik, nilai Vout dicatat.
  3. Skrip dijalankan:
        python tools/calibrate.py --p1 10 --v1 2.046 --p2 100 --v2 2.729
  4. Skrip mencetak dua nilai yang disalin ke bagian KONFIGURASI sketch:
        V_PER_DECADE_DEFAULT  dan  V_AT_1PPM_DEFAULT

Catatan: kurva sensor MQ-2/MQ-7 bersifat LOGARITMIK (V = a + b*log10(ppm)),
sehingga regresi di bawah dilakukan pada ruang log. Titik acuan dipilih 10 dan
100 ppm karena jaraknya tepat satu dekade dan keduanya jauh di bawah batas
jenuh ADC ESP32 (3,3 V setara +-682 ppm).

Alternatif yang lebih ringkas: kalibrasi langsung dari Serial Monitor dengan
perintah `c1 10` dan `c2 100` (lihat README bagian 7).
"""

import argparse
import math


def main():
    ap = argparse.ArgumentParser(description="Kalibrasi dua titik sensor CO-Zero (logaritmik)")
    ap.add_argument("--p1", type=float, required=True, help="ppm titik 1 (mis. 10)")
    ap.add_argument("--v1", type=float, required=True, help="Vout pada titik 1 (volt)")
    ap.add_argument("--p2", type=float, required=True, help="ppm titik 2 (mis. 100)")
    ap.add_argument("--v2", type=float, required=True, help="Vout pada titik 2 (volt)")
    args = ap.parse_args()

    if args.p1 <= 0 or args.p2 <= 0:
        raise SystemExit("Nilai ppm harus lebih besar dari 0.")
    if abs(args.v2 - args.v1) < 1e-6:
        raise SystemExit("Vout titik 1 dan 2 sama - geser slider lebih jauh.")

    dl = math.log10(args.p2) - math.log10(args.p1)
    if abs(dl) < 0.3:
        raise SystemExit(
            "Kedua titik acuan terlalu berdekatan (butuh minimal ~1 dekade, mis. 10 dan 100 ppm)."
        )

    per_decade = (args.v2 - args.v1) / dl
    at_1ppm = args.v1 - per_decade * math.log10(args.p1)

    def to_ppm(v):
        return 10 ** ((v - at_1ppm) / per_decade)

    print("\n=== Hasil kalibrasi (model logaritmik) ===")
    print(f"#define V_PER_DECADE_DEFAULT   {per_decade:.4f}f")
    print(f"#define V_AT_1PPM_DEFAULT      {at_1ppm:.4f}f")
    print("\nVerifikasi:")
    for ppm, v in ((args.p1, args.v1), (args.p2, args.v2)):
        back = to_ppm(v)
        err = abs(back - ppm) / ppm * 100
        print(f"  Vout {v:.3f} V  ->  {back:8.2f} ppm  (target {ppm:g}, galat {err:.1f}%)")

    print("\nBatas ADC (3,300 V) setara", f"{to_ppm(3.3):.0f} ppm")
    print("\nKedua nilai disalin ke bagian KONFIGURASI sketch, lalu simulasi dijalankan ulang.")
    print("README bagian 7 diperbarui bila nilainya berubah.")


if __name__ == "__main__":
    main()
