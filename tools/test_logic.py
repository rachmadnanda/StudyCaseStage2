#!/usr/bin/env python3
"""
Uji unit logika klasifikasi level CO-Zero.

Skrip ini mengekstrak blok logika yang ditandai `// ==LOGIC-BEGIN==` ..
`// ==LOGIC-END==` dari firmware/cozero_esp32.ino, mengompilasinya bersama
program uji C++, lalu menjalankan assertion. Tujuannya memastikan fungsi
classify() yang dipakai di Wokwi benar-benar berperilaku sesuai tabel
ambang batas + histeresis, bukan hanya "terlihat benar".

Pakai:
    python tools/test_logic.py
"""

import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKETCH = os.path.join(ROOT, "firmware", "cozero_esp32.ino")

HARNESS = r"""
#include <cstdio>
#include <cmath>

__LOGIC__

static int gagal = 0;
static int lulus = 0;

void cek(const char* nama, Level dapat, Level harap) {
    if (dapat == harap) {
        lulus++;
    } else {
        gagal++;
        printf("  GAGAL  %-42s dapat=%-8s harap=%s\n",
               nama, LEVEL_NAME[dapat], LEVEL_NAME[harap]);
    }
}

int main() {
    printf("=== Uji logika klasifikasi CO-Zero ===\n");

    /* 1. Pemetaan ambang batas dasar */
    cek("5 ppm dari AMAN",        classify(5.0f,    LV_AMAN),    LV_AMAN);
    cek("19.9 ppm dari AMAN",     classify(19.9f,   LV_AMAN),    LV_AMAN);
    cek("20 ppm dari AMAN",       classify(20.0f,   LV_AMAN),    LV_WASPADA);
    cek("34.9 ppm dari WASPADA",  classify(34.9f,   LV_WASPADA), LV_WASPADA);
    cek("35 ppm dari WASPADA",    classify(35.0f,   LV_WASPADA), LV_BAHAYA);
    cek("114.9 ppm dari BAHAYA",  classify(114.9f,  LV_BAHAYA),  LV_BAHAYA);
    cek("115 ppm dari BAHAYA",    classify(115.0f,  LV_BAHAYA),  LV_KRITIS);
    cek("570 ppm (kasus Magelang)", classify(570.0f, LV_BAHAYA), LV_KRITIS);

    /* 2. Naik langsung, tanpa ditahan */
    cek("lompat 5 -> 60",   classify(60.0f,  LV_AMAN),    LV_BAHAYA);
    cek("lompat 5 -> 570",  classify(570.0f, LV_AMAN),    LV_KRITIS);

    /* 3. Histeresis pada penurunan */
    cek("BAHAYA turun ke 33 (tahan)", classify(33.0f, LV_BAHAYA), LV_BAHAYA);
    cek("BAHAYA turun ke 32 (lepas)", classify(32.0f, LV_BAHAYA), LV_WASPADA);
    cek("KRITIS turun ke 113 (tahan)", classify(113.0f, LV_KRITIS), LV_KRITIS);
    cek("KRITIS turun ke 112 (lepas)", classify(112.0f, LV_KRITIS), LV_BAHAYA);
    cek("WASPADA turun ke 18 (tahan)", classify(18.0f, LV_WASPADA), LV_WASPADA);
    cek("WASPADA turun ke 17 (lepas)", classify(17.0f, LV_WASPADA), LV_AMAN);

    /* 4. Tidak ada kedipan di sekitar ambang.
     * Osilasi 34 <-> 36 melewati ambang 35. Dengan histeresis 3 ppm, level
     * boleh naik ke BAHAYA lalu TERTAHAN di sana (konservatif demi keamanan),
     * dan tidak boleh kembali turun selama nilai masih di atas 32 ppm. */
    Level lv = LV_AMAN;
    int transisi = 0;
    for (int i = 0; i < 20; i++) {
        float ppm = (i % 2 == 0) ? 34.0f : 36.0f;
        Level baru = classify(ppm, lv);
        if (baru != lv) transisi++;
        lv = baru;
    }
    cek("osilasi 34<->36 maksimal 2 transisi", (Level)(transisi <= 2 ? 0 : 1), LV_AMAN);
    cek("osilasi 34<->36 berakhir BAHAYA", lv, LV_BAHAYA);

    /* 4b. Osilasi di dalam satu pita: hanya satu transisi, tidak berkedip */
    lv = LV_AMAN;
    transisi = 0;
    for (int i = 0; i < 20; i++) {
        float ppm = (i % 2 == 0) ? 22.0f : 24.0f;
        Level baru = classify(ppm, lv);
        if (baru != lv) transisi++;
        lv = baru;
    }
    cek("osilasi 22<->24 hanya 1 transisi", (Level)(transisi == 1 ? 0 : 1), LV_AMAN);
    cek("osilasi 22<->24 tetap WASPADA", lv, LV_WASPADA);

    /* 5. Level tidak pernah turun lebih dari satu langkah per sampel */
    cek("KRITIS -> 20 ppm", classify(20.0f, LV_KRITIS), LV_WASPADA);

    printf("---------------------------------------\n");
    printf("Lulus: %d | Gagal: %d\n", lulus, gagal);
    return gagal == 0 ? 0 : 1;
}
"""


def main():
    src = open(SKETCH, encoding="utf-8").read()

    types = re.search(r"// ==LOGIC-TYPES-BEGIN==(.*?)// ==LOGIC-TYPES-END==", src, re.S)
    func = re.search(r"// ==LOGIC-CLASSIFY-BEGIN==(.*?)// ==LOGIC-CLASSIFY-END==", src, re.S)
    if not types or not func:
        sys.exit("Penanda blok logika tidak ditemukan di sketch.")

    logic = types.group(1) + "\n" + func.group(1)

    # ambil konstanta ambang batas dari bagian KONFIGURASI
    defines = "\n".join(
        line for line in src.splitlines()
        if re.match(r"#define\s+(TH_WASPADA|TH_BAHAYA|TH_KRITIS|HISTERESIS)\s", line)
    )
    if not defines:
        sys.exit("Konstanta TH_* / HISTERESIS tidak ditemukan.")

    program = HARNESS.replace("__LOGIC__", defines + "\n" + logic)

    with tempfile.TemporaryDirectory() as tmp:
        cpp = os.path.join(tmp, "test_logic.cpp")
        exe = os.path.join(tmp, "test_logic")
        with open(cpp, "w", encoding="utf-8") as f:
            f.write(program)

        comp = subprocess.run(
            ["g++", "-std=c++17", "-Wall", "-Wextra", "-O1", cpp, "-o", exe],
            capture_output=True, text=True,
        )
        if comp.returncode != 0:
            print(comp.stderr)
            sys.exit("Kompilasi program uji gagal.")

        run = subprocess.run([exe], capture_output=True, text=True)
        print(run.stdout.rstrip())
        if run.stderr.strip():
            print(run.stderr.rstrip())
        sys.exit(run.returncode)


if __name__ == "__main__":
    main()
