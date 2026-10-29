#!/usr/bin/env python3
"""
Uji unit logika klasifikasi level CO-Zero.

Skrip ini mengekstrak blok logika yang ditandai penanda `// ==LOGIC-...-BEGIN==`
hingga `// ==LOGIC-...-END==` dari firmware/cozero_esp32.ino, mengompilasinya
bersama program uji C++, lalu menjalankan assertion. Tujuannya memastikan
fungsi classify(), envCheck(), combineLevels(), dan voltsToPpm() yang dipakai
di Wokwi benar-benar berperilaku sesuai tabel ambang batas, histeresis, dan
matriks eskalasi lingkungan - bukan hanya "terlihat benar".

Pemakaian:
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

/* Bandingkan ppm hasil konversi dengan toleransi relatif. */
void cekPpm(const char* nama, float volt, float harap, float tolPersen) {
    float dapat = voltsToPpm(volt, V_PER_DECADE_DEFAULT, V_AT_1PPM_DEFAULT);
    float err = (harap > 0.0f) ? fabsf(dapat - harap) / harap * 100.0f : fabsf(dapat);
    if (err <= tolPersen) {
        lulus++;
    } else {
        gagal++;
        printf("  GAGAL  %-42s V=%.4f dapat=%.2f ppm harap=%.2f (err %.1f%%)\n",
               nama, volt, dapat, harap, err);
    }
}

void cekEnv(const char* nama, float t, float rh, bool valid,
            EnvFlag prev, EnvFlag harap) {
    EnvFlag dapat = envCheck(t, rh, valid, prev);
    if (dapat == harap) {
        lulus++;
    } else {
        gagal++;
        printf("  GAGAL  %-42s dapat=%-7s harap=%s\n",
               nama, ENV_NAME[dapat], ENV_NAME[harap]);
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

    /* 6. Konversi logaritmik terhadap pengukuran langsung di Wokwi.
     *    raw 843  = 0,679 V -> slider 0,1 ppm
     *    raw 2096 = 1,689 V -> slider 3 ppm
     *    raw 4041 = 3,257 V -> slider 100.000 ppm (ADC jenuh, bukan 589 ppm) */
    cekPpm("0,679 V -> 0,1 ppm",  0.679f,    0.1f,   12.0f);
    cekPpm("1,689 V -> 3 ppm",    1.689f,    3.0f,    2.0f);
    cekPpm("2,252 V -> 20 ppm",   2.2524f,  20.0f,    2.0f);
    cekPpm("2,419 V -> 35 ppm",   2.4185f,  35.0f,    2.0f);
    cekPpm("2,772 V -> 115 ppm",  2.7717f, 115.0f,    2.0f);
    cekPpm("3,247 V -> 570 ppm",  3.2470f, 570.0f,    2.0f);

    /* 7. Sifat monoton: tegangan naik -> ppm tidak pernah turun */
    {
        float prev = -1.0f;
        int naik = 0;
        for (float v = 0.0f; v <= 3.30f; v += 0.05f) {
            float p = voltsToPpm(v, V_PER_DECADE_DEFAULT, V_AT_1PPM_DEFAULT);
            if (p >= prev) naik++;
            prev = p;
        }
        cek("konversi monoton naik", (Level)(naik == 67 ? 0 : 1), LV_AMAN);
    }

    /* 8. Batas ADC: 3,300 V setara ~682 ppm, masih di atas 570 ppm */
    cekPpm("3,300 V (jenuh) -> ~682 ppm", 3.300f, 682.0f, 2.0f);

    /* 9. Ambang lingkungan: suhu */
    cekEnv("39,9 C -> NORMAL",       39.9f, 55.0f, true,  ENV_NORMAL, ENV_NORMAL);
    cekEnv("40,0 C -> PANAS",        40.0f, 55.0f, true,  ENV_NORMAL, ENV_PANAS);
    cekEnv("45,0 C -> PANAS",        45.0f, 55.0f, true,  ENV_NORMAL, ENV_PANAS);

    /* 10. Ambang lingkungan: kelembapan */
    cekEnv("74,9 %RH -> NORMAL",     29.0f, 74.9f, true,  ENV_NORMAL, ENV_NORMAL);
    cekEnv("75,0 %RH -> LEMBAB",     29.0f, 75.0f, true,  ENV_NORMAL, ENV_LEMBAB);
    cekEnv("20,1 %RH -> NORMAL",     29.0f, 20.1f, true,  ENV_NORMAL, ENV_NORMAL);
    cekEnv("20,0 %RH -> KERING",     29.0f, 20.0f, true,  ENV_NORMAL, ENV_KERING);

    /* 11. Suhu diprioritaskan bila keduanya ekstrem */
    cekEnv("42 C + 80 %RH -> PANAS", 42.0f, 80.0f, true,  ENV_NORMAL, ENV_PANAS);

    /* 12. Deadband: flag sebelumnya dipertahankan di dalam pita.
     * Konvensi sama dengan histeresis CO: flag lepas TEPAT pada
     * ambang - deadband (batas bawah inklusif ke arah pelepasan). */
    cekEnv("39,5 C dari PANAS -> PANAS",  39.5f, 55.0f, true, ENV_PANAS,  ENV_PANAS);
    cekEnv("39,1 C dari PANAS -> PANAS",  39.1f, 55.0f, true, ENV_PANAS,  ENV_PANAS);
    cekEnv("39,0 C dari PANAS -> NORMAL", 39.0f, 55.0f, true, ENV_PANAS,  ENV_NORMAL);
    cekEnv("38,9 C dari PANAS -> NORMAL", 38.9f, 55.0f, true, ENV_PANAS,  ENV_NORMAL);
    cekEnv("72,1 %RH dari LEMBAB -> LEMBAB", 29.0f, 72.1f, true, ENV_LEMBAB, ENV_LEMBAB);
    cekEnv("72,0 %RH dari LEMBAB -> NORMAL", 29.0f, 72.0f, true, ENV_LEMBAB, ENV_NORMAL);
    cekEnv("71,9 %RH dari LEMBAB -> NORMAL", 29.0f, 71.9f, true, ENV_LEMBAB, ENV_NORMAL);
    cekEnv("22,9 %RH dari KERING -> KERING", 29.0f, 22.9f, true, ENV_KERING, ENV_KERING);
    cekEnv("23,0 %RH dari KERING -> NORMAL", 29.0f, 23.0f, true, ENV_KERING, ENV_NORMAL);
    cekEnv("23,1 %RH dari KERING -> NORMAL", 29.0f, 23.1f, true, ENV_KERING, ENV_NORMAL);

    /* 13. Sensor gagal tidak boleh memicu eskalasi palsu */
    cekEnv("DHT gagal, 50 C -> NORMAL", 50.0f, 90.0f, false, ENV_NORMAL, ENV_NORMAL);
    cekEnv("DHT gagal, flag PANAS -> NORMAL", 50.0f, 90.0f, false, ENV_PANAS, ENV_NORMAL);

    /* 14. Matriks eskalasi combineLevels() */
    cek("AMAN + NORMAL -> AMAN",       combineLevels(LV_AMAN,    ENV_NORMAL), LV_AMAN);
    cek("AMAN + PANAS -> WASPADA",     combineLevels(LV_AMAN,    ENV_PANAS),  LV_WASPADA);
    cek("WASPADA + NORMAL -> WASPADA", combineLevels(LV_WASPADA, ENV_NORMAL), LV_WASPADA);
    cek("WASPADA + PANAS -> BAHAYA",   combineLevels(LV_WASPADA, ENV_PANAS),  LV_BAHAYA);
    cek("BAHAYA + NORMAL -> BAHAYA",   combineLevels(LV_BAHAYA,  ENV_NORMAL), LV_BAHAYA);
    cek("BAHAYA + LEMBAB -> KRITIS",   combineLevels(LV_BAHAYA,  ENV_LEMBAB), LV_KRITIS);
    cek("KRITIS + NORMAL -> KRITIS",   combineLevels(LV_KRITIS,  ENV_NORMAL), LV_KRITIS);
    cek("KRITIS + KERING -> KRITIS",   combineLevels(LV_KRITIS,  ENV_KERING), LV_KRITIS);

    /* 15. Eskalasi tidak pernah melompati satu tingkat */
    {
        int lompat = 0;
        for (int c = LV_AMAN; c <= LV_KRITIS; c++) {
            for (int e = ENV_NORMAL; e <= ENV_KERING; e++) {
                Level hasil = combineLevels((Level)c, (EnvFlag)e);
                if (hasil < (Level)c || hasil > (Level)(c + 1)) lompat++;
            }
        }
        cek("eskalasi maksimal satu tingkat", (Level)(lompat == 0 ? 0 : 1), LV_AMAN);
    }

    /* 16. Rantai penuh: CO 25 ppm + suhu 41 C -> BAHAYA */
    {
        Level co = classify(25.0f, LV_AMAN);
        EnvFlag env = envCheck(41.0f, 60.0f, true, ENV_NORMAL);
        cek("CO 25 ppm + 41 C -> BAHAYA", combineLevels(co, env), LV_BAHAYA);
    }

    /* 17. Rantai penuh: CO 5 ppm + RH 80 % -> WASPADA (bukan lebih) */
    {
        Level co = classify(5.0f, LV_AMAN);
        EnvFlag env = envCheck(29.0f, 80.0f, true, ENV_NORMAL);
        cek("CO 5 ppm + 80 %RH -> WASPADA", combineLevels(co, env), LV_WASPADA);
    }

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

    env = re.search(r"// ==LOGIC-ENV-BEGIN==(.*?)// ==LOGIC-ENV-END==", src, re.S)
    if not env:
        sys.exit("Penanda blok logika lingkungan tidak ditemukan di sketch.")
    logic += "\n" + env.group(1)

    scale = re.search(r"// ==LOGIC-SCALE-BEGIN==(.*?)// ==LOGIC-SCALE-END==", src, re.S)
    if not scale:
        sys.exit("Penanda blok skala logaritmik tidak ditemukan di sketch.")
    logic += "\n" + scale.group(1)

    # ambil konstanta ambang batas + skala sensor dari bagian KONFIGURASI
    defines = "\n".join(
        line for line in src.splitlines()
        if re.match(
            r"#define\s+(TH_WASPADA|TH_BAHAYA|TH_KRITIS|HISTERESIS"
            r"|TH_TEMP_PANAS|TH_RH_LEMBAB|TH_RH_KERING"
            r"|ENV_HYST_TEMP|ENV_HYST_RH"
            r"|V_PER_DECADE_DEFAULT|V_AT_1PPM_DEFAULT)\s", line)
    )
    if not defines:
        sys.exit("Konstanta ambang batas / skala sensor tidak ditemukan.")

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
