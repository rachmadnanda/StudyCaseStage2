/*
 * ============================================================================
 *  CO-Zero v1.0
 *  Sistem Monitoring & Peringatan Dini Karbon Monoksida (CO) Kabin Mobil
 *  ---------------------------------------------------------------------------
 *  Samsung Innovation Campus Batch 8 - Stage 2 (IoT: Device & Hardware Discovery)
 *  Tim Iki jenenge wes wkwk - Politeknik Negeri Malang
 *  Platform : ESP32 DevKit V1 (Wokwi Simulator)
 *
 *  Alur sistem:
 *    MQ-2 (AOUT) --> ADC GPIO34 --> moving average --> klasifikasi level
 *        --> Buzzer + OLED (lokal, tetap jalan tanpa internet)
 *        --> WiFi --> MQTT (HiveMQ Cloud) --> Dashboard Python
 *
 *  CATATAN SIMULASI
 *    - Wokwi tidak menyediakan MQ-7. Digunakan modul MQ-2 yang juga sensitif
 *      terhadap CO. Keduanya sensor MOS berbasis heater dengan keluaran analog,
 *      sehingga logika sistem tidak berubah.
 *    - Nilai ppm sensor di Wokwi diatur melalui atribut "ppm" pada diagram.json
 *      dan dapat digeser saat simulasi berjalan (klik sensor).
 *    - Bila atribut "ppm" diabaikan simulator, slider digeser setelah simulasi
 *      berjalan. Kalibrasi dua titik (c1/c2) membuat skala ppm tetap akurat
 *      tanpa perubahan kode.
 *    - Keluaran sensor MQ-2 bersifat LOGARITMIK, bukan linear: setiap kenaikan
 *      satu dekade (10x) konsentrasi menaikkan Vout sekitar 0,68 V. Konversi
 *      ppm memakai powf(10, ...) - lihat readCoPpm().
 *    - Resistor pembagi tegangan tidak dapat dipakai di Wokwi; lihat bagian
 *      KONFIGURASI (DIVIDER_RATIO).
 * ============================================================================
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHTesp.h>

/* ==========================================================================
 *  1. KONFIGURASI  (ubah bagian ini saja)
 * ========================================================================== */

#define DEVICE_ID       "COZERO-01"

/* --- WiFi: Wokwi selalu memakai SSID ini --- */
#define WIFI_SSID       "Wokwi-GUEST"
#define WIFI_PASS       ""

/* --- HiveMQ Cloud (isi dengan kredensial cluster) --- */
#define MQTT_HOST       "xxxxxxxxxxxx.s1.eu.hivemq.cloud"
#define MQTT_PORT       8883
#define MQTT_USER       "ISI_USERNAME_HIVEMQ"
#define MQTT_PASS       "ISI_PASSWORD_HIVEMQ"

/* --- Topik MQTT --- */
#define TOPIC_BASE      "cozero/team"
#define TOPIC_TELEMETRY TOPIC_BASE "/telemetry"
#define TOPIC_ALERT     TOPIC_BASE "/alert"
#define TOPIC_STATUS    TOPIC_BASE "/status"

/* --- Pin GPIO (rincian pada tabel laporan) --- */
#define PIN_MQ_ADC      34   // ADC1_CH6, input-only
#define PIN_MQ_DOUT     32   // keluaran digital MQ-2 (redundan)
#define PIN_DHT         4
#define PIN_BUZZER      25
#define PIN_OLED_SDA    21
#define PIN_OLED_SCL    22

/*
 * Pin kosong yang dipakai sebagai acuan diagnostik. Pin ini tidak terhubung ke
 * komponen apa pun, sehingga perilakunya menunjukkan apakah simulator
 * menerapkan resistor pull-down internal.
 */
#define REF_PROBE_PIN   13

/* --- Ambang batas kadar CO (ppm) --- */
#define TH_WASPADA      20
#define TH_BAHAYA       35
#define TH_KRITIS       115
#define HISTERESIS      3.0f   // ppm, mencegah buzzer berkedip di batas

/*
 * Ambang batas iklim mikro kabin. Nilai ini tidak menentukan level secara
 * mandiri, melainkan memperberat level CO (lihat combineLevels()).
 *
 *   suhu >= 40 C      -> PANAS   : beban panas menambah risiko hipoksia
 *   RH   >= 75 %      -> LEMBAB  : penguapan keringat terhambat
 *   RH   <= 20 %      -> KERING  : iritasi saluran napas
 *
 * Deadband dipakai agar indikator tidak berkedip saat nilai berada tepat
 * di ambang.
 */
#define TH_TEMP_PANAS   40.0f
#define TH_RH_LEMBAB    75.0f
#define TH_RH_KERING    20.0f
#define ENV_HYST_TEMP   1.0f
#define ENV_HYST_RH     3.0f

/* --- Waktu (ms) --- */
#define SAMPLE_MS       500
#define PUBLISH_MS      2000
#define DHT_MS          2200    // DHT22 butuh jeda minimal 2000 ms antar pembacaan
#define OLED_MS         300
#define MQTT_RETRY_MS   5000
#define WIFI_RETRY_MS   5000
#define DHT_BOOT_TRIES  3       // jumlah percobaan pada uji awal saat boot

/* --- Konversi sensor --- */
#define ADC_MAX         4095.0f
#define ADC_VREF        3.3f

/*
 * CATATAN SIMULASI PENTING
 * Pada perangkat fisik, keluaran AOUT MQ-2/MQ-7 (hingga ±5 V) WAJIB diturunkan
 * lewat pembagi tegangan 10k:10k sebelum masuk ADC ESP32 (maksimum 3,3 V).
 * Wokwi tidak mendukung kombinasi resistor dengan komponen analog, sehingga
 * pada simulasi AOUT dihubungkan langsung ke GPIO34 dan DIVIDER_RATIO = 1.0.
 * Pada implementasi nyata, ubah nilai ini menjadi 2.0.
 */
#define DIVIDER_RATIO   1.0f
#define ADC_SAMPLES     8
#define AVG_WINDOW      5       // moving average

/*
 * Lompatan ppm dianggap perubahan nyata (misalnya slider sensor digeser) bila
 * melebihi FAST_TRACK_PPM atau lebih dari 30% nilai saat ini. Riwayat moving
 * average kemudian dibuang agar nilai terbaru langsung dipakai. Tanpa mekanisme
 * ini, nilai ppm tampak tidak menentu selama +-2,5 detik setiap kali slider
 * digeser karena rata-rata masih menyusul nilai lama.
 */
#define FAST_TRACK_PPM  40.0f

/*
 * SKALA SENSOR: LOGARITMIK
 * ---------------------------------------------------------------------------
 * Keluaran MQ-2/MQ-7 tidak linear terhadap konsentrasi, melainkan logaritmik
 * (kurva Rs/R0 pada datasheet). Pengukuran langsung pada simulator Wokwi:
 *
 *     slider 0,1 ppm   -> Vout 0,679 V
 *     slider 3 ppm     -> Vout 1,689 V
 *     slider 100.000   -> Vout 3,257 V  (ADC mulai jenuh)
 *
 * Ketiga titik itu persis mengikuti  V = 1,3629 + 0,6836 x log10(ppm).
 * Hubungan ini menghasilkan satu dekade (10x) konsentrasi untuk setiap
 * 0,6836 V kenaikan tegangan, sehingga kadar CO dihitung dengan:
 *
 *     ppm = 10 ^ ((Vout - V_AT_1PPM) / V_PER_DECADE)
 *
 * Nilai default di bawah berasal dari regresi ketiga titik tersebut. Bila hasil
 * pembacaan belum sesuai dengan slider, dilakukan KALIBRASI DUA TITIK melalui
 * Serial Monitor (perintah c1/c2, lihat fungsi handleSerial()).
 *
 * Batas atas: ADC jenuh pada 3,300 V yang setara +-682 ppm, sehingga seluruh
 * skenario uji (termasuk 570 ppm = 3,247 V) masih terbaca sebelum jenuh.
 */
#define V_PER_DECADE_DEFAULT   0.6836f
#define V_AT_1PPM_DEFAULT      1.3629f

/*
 * Ambang komparator DOUT pada modul MQ-2 (atribut "threshold" di diagram.json).
 * Dipakai untuk memastikan DOUT hanya dipercaya bila tegangan AOUT memang sudah
 * melewatinya. Nilai 4,0 V berarti komparator baru aktif di atas kisaran uji.
 */
#define DOUT_THRESHOLD_V      4.0f

/* ==========================================================================
 *  2. OBJEK GLOBAL
 * ========================================================================== */

Adafruit_SSD1306 oled(128, 64, &Wire, -1);
DHTesp dht;
WiFiClientSecure net;
PubSubClient mqtt(net);

// ==LOGIC-TYPES-BEGIN==
enum Level { LV_AMAN = 0, LV_WASPADA = 1, LV_BAHAYA = 2, LV_KRITIS = 3 };
const char* LEVEL_NAME[4] = { "AMAN", "WASPADA", "BAHAYA", "KRITIS" };
const float LEVEL_TH[4]  = { -1.0f, TH_WASPADA, TH_BAHAYA, TH_KRITIS };

enum EnvFlag { ENV_NORMAL = 0, ENV_PANAS = 1, ENV_LEMBAB = 2, ENV_KERING = 3 };
const char* ENV_NAME[4] = { "NORMAL", "PANAS", "LEMBAB", "KERING" };
// ==LOGIC-TYPES-END==

/* state sensor */
float ppmRaw        = 0.0f;
float ppmAvg        = 0.0f;
float avgBuf[AVG_WINDOW];
int   avgIdx        = 0;
bool  avgFilled     = false;
int   lastRawAdc    = 0;
float lastVoltOut   = 0.0f;
bool  mqDoutLow     = false;

/* kalibrasi (dapat diubah saat runtime lewat Serial Monitor) */
float vPerDecade    = V_PER_DECADE_DEFAULT;
float vAt1ppm       = V_AT_1PPM_DEFAULT;

/* titik kalibrasi yang sedang menunggu pasangan (NaN = belum diisi) */
float calPpm[2]     = { NAN, NAN };
float calVolt[2]    = { NAN, NAN };

/* state iklim mikro */
float tempC         = 0.0f;
float humPct        = 0.0f;
bool  dhtOk         = false;
unsigned long dhtOkAt   = 0;      // waktu pembacaan DHT terakhir yang valid
unsigned int  dhtFail   = 0;      // jumlah kegagalan berurutan
const char*   dhtLastErr = "-";   // status pembacaan terakhir (OK/TIMEOUT/CHECKSUM)

/*
 * Pin tempat DHT22 benar-benar terbaca. Nilainya sama dengan PIN_DHT kecuali
 * pemindaian otomatis menemukan sensor pada pin lain, misalnya karena kanvas
 * Wokwi berbeda dari diagram.json yang seharusnya dipakai.
 */
uint8_t dhtActivePin = PIN_DHT;

/* state sistem */
Level   coLevel     = LV_AMAN;    // level dari kadar CO saja (dengan histeresis)
Level   level       = LV_AMAN;    // level akhir: CO + kondisi lingkungan
EnvFlag envFlag     = ENV_NORMAL;

/* timing */
unsigned long tSample = 0, tPublish = 0, tDht = 0, tOled = 0, tMqtt = 0, tWifi = 0;
unsigned long bootMillis = 0;

/* buzzer */
bool bzState = false;

/* MQTT hanya diaktifkan bila kredensial HiveMQ sudah diisi */
bool mqttConfigured = false;

/* ==========================================================================
 *  3. PEMBACAAN SENSOR
 * ========================================================================== */

/* Rata-rata ADC -> tegangan keluaran MQ-2 (setelah pembagi tegangan). */
float readVoltageOut() {
  long sum = 0;
  for (int i = 0; i < ADC_SAMPLES; i++) {
    sum += analogRead(PIN_MQ_ADC);
    delayMicroseconds(200);
  }
  float raw = (float)sum / (float)ADC_SAMPLES;
  float vAdc = raw * (ADC_VREF / ADC_MAX);
  lastRawAdc = (int)raw;
  lastVoltOut = vAdc * DIVIDER_RATIO;
  return lastVoltOut;
}

/*
 * Kalibrasi dua titik, dijalankan SAAT SIMULASI BERJALAN lewat Serial Monitor.
 *
 *  1. Geser slider ppm sensor ke nilai acuan pertama, misal 10.
 *  2. Ketik:  c1 10       -> firmware menyimpan pasangan (10 ppm, Vout saat ini)
 *  3. Geser slider ke nilai acuan kedua, misal 100.
 *  4. Ketik:  c2 100      -> firmware menghitung vPerDecade dan vAt1ppm
 *  5. Ketik:  ?           -> menampilkan hasil kalibrasi
 *  6. Ketik:  r           -> kembali ke nilai default
 *
 * Kalibrasi dilakukan di RUANG LOGARITMIK, bukan linear, karena kurva sensor
 * berbentuk  V = a + b x log10(ppm). Dua titik acuan menghasilkan:
 *     b (vPerDecade) = (V2 - V1) / (log10(ppm2) - log10(ppm1))
 *     a (vAt1ppm)    = V1 - b x log10(ppm1)
 *
 * PENTING: pilih titik acuan yang jaraknya minimal satu dekade (mis. 10 dan
 * 100 ppm) dan masih di bawah 682 ppm, karena di atas itu ADC ESP32 sudah
 * jenuh (3,3 V) sehingga titik acuan tidak lagi valid.
 *
 * Hasil kalibrasi hanya tersimpan di RAM (hilang saat restart), sesuai
 * kebutuhan simulasi. Untuk perangkat fisik, simpan nilainya sebagai
 * V_PER_DECADE_DEFAULT / V_AT_1PPM_DEFAULT di bagian KONFIGURASI.
 */
void captureCalPoint(int idx, float ppmRef) {
  calPpm[idx]  = ppmRef;
  calVolt[idx] = lastVoltOut;
  Serial.printf("[CAL] Titik %d disimpan: %.1f ppm = %.4f V\n",
                idx + 1, ppmRef, lastVoltOut);

  if (isnan(calPpm[0]) || isnan(calPpm[1])) return;

  float dl = log10f(calPpm[1]) - log10f(calPpm[0]);
  if (fabs(dl) < 0.3f) {   // butuh jarak minimal ~2x antar titik acuan
    Serial.println(F("[CAL] Titik acuan terlalu berdekatan. Gunakan mis. 10 dan 100 ppm."));
    return;
  }

  vPerDecade = (calVolt[1] - calVolt[0]) / dl;
  vAt1ppm    = calVolt[0] - vPerDecade * log10f(calPpm[0]);

  Serial.printf("[CAL] Selesai -> vPerDecade = %.4f | vAt1ppm = %.4f V\n",
                vPerDecade, vAt1ppm);
  Serial.println(F("[CAL] Kedua nilai disalin ke bagian KONFIGURASI sketch."));
}

void printCalState() {
  Serial.println(F("---- Status kalibrasi ----"));
  Serial.printf("  vPerDecade = %.4f V/dekade\n", vPerDecade);
  Serial.printf("  vAt1ppm    = %.4f V\n", vAt1ppm);
  Serial.printf("  Vout kini  = %.4f V -> %.1f ppm\n",
                lastVoltOut, ppmAvg);
  Serial.println(F("  Perintah: c1 <ppm> | c2 <ppm> | dht | scan | r | ?"));
}

/*
 * Ringkasan keadaan sensor iklim mikro dan hasil klasifikasinya. Berguna untuk
 * memastikan apakah kegagalan berasal dari sensor (dhtOk = false) atau dari
 * nilai yang memang berada di luar ambang.
 */
void printDhtState() {
  Serial.println(F("---- Status iklim mikro ----"));
  Serial.printf("  DHT22      : %s (GPIO%d)\n",
                dhtOk ? "terbaca" : "TIDAK TERBACA", dhtActivePin);
  Serial.printf("  Status baca: %s (%u kegagalan berurutan)\n",
                dhtLastErr, dhtFail);
  if (dhtOk) {
    Serial.printf("  Suhu       : %.1f C  (ambang panas >= %.1f C)\n",
                  tempC, TH_TEMP_PANAS);
    Serial.printf("  Kelembapan : %.1f %%RH (lembab >= %.0f, kering <= %.0f)\n",
                  humPct, TH_RH_LEMBAB, TH_RH_KERING);
    Serial.printf("  Umur data  : %lu ms sejak pembacaan valid terakhir\n",
                  millis() - dhtOkAt);
  } else {
    dhtProbe();
  }
  Serial.printf("  Flag       : %s\n",
                dhtOk ? ENV_NAME[envFlag] : "NORMAL (dilewati)");
  Serial.printf("  Level CO   : %s\n", LEVEL_NAME[coLevel]);
  Serial.printf("  Level akhir: %s\n", LEVEL_NAME[level]);
}

/*
 * Konversi tegangan -> ppm memakai hubungan logaritmik sensor MOS.
 * Dibuat sebagai fungsi murni (tanpa variabel global) agar dapat diuji
 * terpisah oleh tools/test_logic.py.
 *
 *   Vout 0,679 V -> 0,10 ppm
 *   Vout 1,689 V -> 3,00 ppm
 *   Vout 3,257 V -> 589 ppm  (ADC mulai jenuh)
 */
// ==LOGIC-SCALE-BEGIN==
float voltsToPpm(float v, float perDecade, float at1ppm) {
  if (perDecade <= 0.0f) return 0.0f;           // kalibrasi tidak valid
  float ppm = powf(10.0f, (v - at1ppm) / perDecade);
  if (ppm < 0.0f)     ppm = 0.0f;
  if (ppm > 10000.0f) ppm = 10000.0f;           // batas atas wajar
  return ppm;
}
// ==LOGIC-SCALE-END==

float readCoPpm() {
  return voltsToPpm(readVoltageOut(), vPerDecade, vAt1ppm);
}

/* Moving average sederhana untuk menstabilkan pembacaan.
 * Bila nilai baru melompat jauh (slider digeser atau kondisi berubah cepat),
 * buffer dikosongkan agar tampilan langsung mengikuti nilai terbaru.
 * Ambang lompatan memakai nilai absolut atau relatif, karena pada skala
 * logaritmik selisih 40 ppm bermakna sangat berbeda pada 0,1 ppm dan 500 ppm. */
float pushAverage(float v) {
  float ref   = (ppmAvg > 1.0f) ? ppmAvg : 1.0f;
  float delta = fabs(v - ppmAvg);

  if (delta > FAST_TRACK_PPM || delta > 0.3f * ref) {
    for (int i = 0; i < AVG_WINDOW; i++) avgBuf[i] = v;
    avgFilled = true;
    return v;
  }

  avgBuf[avgIdx] = v;
  avgIdx = (avgIdx + 1) % AVG_WINDOW;
  if (avgIdx == 0) avgFilled = true;

  int n = avgFilled ? AVG_WINDOW : avgIdx;
  if (n == 0) return v;

  float s = 0.0f;
  for (int i = 0; i < n; i++) s += avgBuf[i];
  return s / (float)n;
}

/*
 * Klasifikasi level dengan histeresis:
 * naik langsung mengikuti ambang, turun harus melewati ambang - HISTERESIS.
 */
// ==LOGIC-CLASSIFY-BEGIN==
Level classify(float ppm, Level prev) {
  Level lv = LV_AMAN;
  if (ppm >= TH_KRITIS)      lv = LV_KRITIS;
  else if (ppm >= TH_BAHAYA) lv = LV_BAHAYA;
  else if (ppm >= TH_WASPADA) lv = LV_WASPADA;

  if (lv < prev && ppm > (LEVEL_TH[prev] - HISTERESIS)) {
    lv = prev;   // tahan penurunan agar indikator tidak berkedip
  }
  return lv;
}
// ==LOGIC-CLASSIFY-END==

/*
 * Penilaian iklim mikro kabin.
 *
 * Suhu dan kelembapan TIDAK menentukan level secara mandiri. Keduanya hanya
 * menghasilkan flag lingkungan yang kemudian dipakai untuk memperberat level
 * CO (lihat combineLevels()). Dengan cara ini sensor gas tetap menjadi sumber
 * utama keputusan, sementara kondisi kabin yang memperburuk risiko ikut
 * diperhitungkan.
 *
 * Parameter "valid" bernilai false bila sensor DHT22 tidak terbaca. Pada
 * kondisi itu fungsi mengembalikan ENV_NORMAL agar kegagalan sensor tidak
 * memicu eskalasi level palsu.
 */
// ==LOGIC-ENV-BEGIN==
EnvFlag envCheck(float t, float rh, bool valid, EnvFlag prev) {
  if (!valid) return ENV_NORMAL;

  EnvFlag lv = ENV_NORMAL;
  if      (t  >= TH_TEMP_PANAS) lv = ENV_PANAS;   // suhu diprioritaskan
  else if (rh >= TH_RH_LEMBAB)  lv = ENV_LEMBAB;
  else if (rh <= TH_RH_KERING)  lv = ENV_KERING;

  /*
   * Deadband: bila nilai sudah kembali ke rentang normal tetapi masih berada
   * di dalam pita deadband, flag sebelumnya dipertahankan agar indikator
   * tidak berkedip di sekitar ambang.
   */
  if (lv == ENV_NORMAL && prev != ENV_NORMAL) {
    bool panas  = (prev == ENV_PANAS)  && (t  > TH_TEMP_PANAS - ENV_HYST_TEMP);
    bool lembab = (prev == ENV_LEMBAB) && (rh > TH_RH_LEMBAB  - ENV_HYST_RH);
    bool kering = (prev == ENV_KERING) && (rh < TH_RH_KERING  + ENV_HYST_RH);
    if (panas || lembab || kering) lv = prev;
  }
  return lv;
}

/*
 * Menggabungkan level CO dengan flag lingkungan.
 *
 * Aturan eskalasi (satu tingkat, tidak pernah melompat):
 *
 *   CO              lingkungan        level akhir
 *   AMAN            NORMAL            AMAN
 *   AMAN            ekstrem           WASPADA
 *   WASPADA         NORMAL            WASPADA
 *   WASPADA         ekstrem           BAHAYA
 *   BAHAYA          NORMAL            BAHAYA
 *   BAHAYA          ekstrem           KRITIS
 *   KRITIS          apa pun           KRITIS
 *
 * Dasar pertimbangan: suhu tinggi menambah beban kardiovaskular sehingga
 * tubuh lebih cepat kekurangan oksigen, sedangkan kelembapan tinggi
 * menghambat penguapan keringat dan lazim menyertai kabin tertutup dengan
 * sirkulasi resirkulasi. Keduanya memperberat dampak kadar CO yang sama.
 * Lingkungan ekstrem sendirian tidak pernah menghasilkan BAHAYA atau KRITIS.
 */
Level combineLevels(Level co, EnvFlag env) {
  if (env == ENV_NORMAL) return co;
  if (co == LV_AMAN)     return LV_WASPADA;
  if (co >= LV_KRITIS)   return LV_KRITIS;
  return (Level)((int)co + 1);
}
// ==LOGIC-ENV-END==

/* ==========================================================================
 *  4. OUTPUT LOKAL
 * ========================================================================== */

void updateBuzzer(unsigned long now) {
  unsigned long period = 0, onMs = 0;

  switch (level) {
    case LV_AMAN:    period = 0;    break;   // senyap
    case LV_WASPADA: period = 1000; onMs = 120; break;  // beep 1 Hz
    case LV_BAHAYA:  period = 400;  onMs = 150; break;  // beep 2.5 Hz
    case LV_KRITIS:  period = 0;    onMs = 0;   break;  // kontinu
  }

  if (level == LV_AMAN) {
    if (bzState) { noTone(PIN_BUZZER); bzState = false; }
    return;
  }

  if (level == LV_KRITIS) {
    if (!bzState) { tone(PIN_BUZZER, 2000); bzState = true; }
    return;
  }

  bool on = (now % period) < onMs;
  if (on && !bzState)      { tone(PIN_BUZZER, 2000); bzState = true; }
  else if (!on && bzState) { noTone(PIN_BUZZER);     bzState = false; }
}

/*
 * OLED adalah satu-satunya indikator visual, sehingga tata letaknya dibuat
 * mengikuti panel instrumen. Layar 128x64 piksel, font bawaan 6x8 px per
 * karakter (size 1) dan 12x16 px (size 2):
 *
 *   y  0.. 7 : judul "CO-Zero" + status W:OK M:OK
 *   y  8..27 : pita status, teks size 2 (dibalik untuk BAHAYA/KRITIS)
 *   y 29..37 : kadar CO dalam ppm
 *   y 40..47 : bar skala relatif terhadap ambang KRITIS
 *   y 50..58 : suhu, kelembapan, dan flag lingkungan (rata kanan)
 */
void drawOled() {
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);

  /* --- judul + status jaringan (maks 7 + 9 karakter x 6 px = 96 px) --- */
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.print(F("CO-Zero"));
  oled.setCursor(66, 0);
  oled.printf("W:%s M:%s",
               WiFi.status() == WL_CONNECTED ? "OK" : "--",
               mqtt.connected() ? "OK" : "--");

  /* --- pita status: teks dibalik (putih di atas hitam) saat berbahaya --- */
  bool alertStyle = (level >= LV_BAHAYA);
  oled.fillRect(0, 8, 128, 20, alertStyle ? SSD1306_WHITE : SSD1306_BLACK);
  oled.setTextColor(alertStyle ? SSD1306_BLACK : SSD1306_WHITE);
  oled.setTextSize(2);
  oled.setCursor(2, 10);
  oled.print(LEVEL_NAME[level]);
  oled.setTextColor(SSD1306_WHITE);

  /* --- kadar CO --- */
  oled.setTextSize(1);
  oled.setCursor(0, 29);
  oled.printf("CO: %6.2f ppm", ppmAvg);

  /* --- bar skala 0..TH_KRITIS --- */
  int barW = (int)((ppmAvg / (float)TH_KRITIS) * 126.0f);
  if (barW < 0)   barW = 0;
  if (barW > 126) barW = 126;
  oled.drawRect(0, 40, 128, 8, SSD1306_WHITE);
  if (barW > 0) oled.fillRect(1, 41, barW, 6, SSD1306_WHITE);

  /*
   * --- suhu, kelembapan, dan flag lingkungan ---
   * Flag dicetak rata kanan agar perubahan kondisi kabin langsung terlihat
   * sebagai penyebab kenaikan level. Bila sensor gagal dibaca, nilai diganti
   * tanda "--" dan flag menjadi "NO DHT"; klasifikasi lingkungan otomatis
   * dilewati sehingga tidak terjadi eskalasi palsu.
   */
  oled.setCursor(0, 50);
  if (dhtOk) oled.printf("%.1fC %.0f%%RH", tempC, humPct);
  else       oled.print(F("--.-C  --%RH"));

  const char* flag = dhtOk ? ENV_NAME[envFlag] : "NO DHT";
  oled.setCursor(128 - (int)strlen(flag) * 6, 50);
  oled.print(flag);

  oled.display();
}

/* ==========================================================================
 *  5. JARINGAN & MQTT
 * ========================================================================== */

void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  unsigned long now = millis();
  if (now - tWifi < WIFI_RETRY_MS) return;
  tWifi = now;

  Serial.printf("[WiFi] Menghubungkan ke %s ...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

void ensureMqtt() {
  if (!mqttConfigured) return;          // kredensial masih placeholder
  if (WiFi.status() != WL_CONNECTED || mqtt.connected()) return;

  unsigned long now = millis();
  if (now - tMqtt < MQTT_RETRY_MS) return;
  tMqtt = now;

  char clientId[32];
  snprintf(clientId, sizeof(clientId), "%s-%04X", DEVICE_ID,
           (unsigned)(ESP.getEfuseMac() & 0xFFFF));

  Serial.printf("[MQTT] Connect ke %s:%d ... ", MQTT_HOST, MQTT_PORT);

  /* Last Will & Testament: broker menandai device offline bila koneksi putus */
  bool ok = mqtt.connect(clientId, MQTT_USER, MQTT_PASS,
                         TOPIC_STATUS, 0, true, "{\"state\":\"offline\"}");

  if (ok) {
    Serial.println(F("OK"));
    mqtt.publish(TOPIC_STATUS, "{\"state\":\"online\"}", true);
  } else {
    Serial.printf("GAGAL (rc=%d)\n", mqtt.state());
  }
}

void publishTelemetry() {
  if (!mqtt.connected()) return;

  char payload[320];
  snprintf(payload, sizeof(payload),
           "{\"device_id\":\"%s\",\"co_ppm\":%.2f,\"temp_c\":%.1f,\"rh\":%.1f,"
           "\"dht_ok\":%s,\"level\":\"%s\",\"level_code\":%d,"
           "\"co_level\":\"%s\",\"env\":\"%s\",\"env_extreme\":%s,"
           "\"raw\":%d,\"volt\":%.3f,\"dout\":%d,\"uptime_s\":%lu}",
           DEVICE_ID, ppmAvg, tempC, humPct,
           dhtOk ? "true" : "false",
           LEVEL_NAME[level], (int)level,
           LEVEL_NAME[coLevel],
           dhtOk ? ENV_NAME[envFlag] : "NORMAL",
           (dhtOk && envFlag != ENV_NORMAL) ? "true" : "false",
           lastRawAdc, lastVoltOut,
           mqDoutLow ? 0 : 1, (millis() - bootMillis) / 1000UL);

  mqtt.publish(TOPIC_TELEMETRY, payload);
}

/*
 * Alasan transisi dicatat agar penerima dapat membedakan apakah kenaikan level
 * dipicu oleh kadar CO, kondisi lingkungan, atau keluaran digital sensor.
 */
void publishAlert(Level prev, const char* reason) {
  if (!mqtt.connected()) return;

  char payload[220];
  snprintf(payload, sizeof(payload),
           "{\"device_id\":\"%s\",\"prev\":\"%s\",\"level\":\"%s\","
           "\"reason\":\"%s\",\"co_ppm\":%.2f,\"co_level\":\"%s\","
           "\"env\":\"%s\",\"uptime_s\":%lu}",
           DEVICE_ID, LEVEL_NAME[prev], LEVEL_NAME[level], reason,
           ppmAvg, LEVEL_NAME[coLevel],
           dhtOk ? ENV_NAME[envFlag] : "NORMAL",
           (millis() - bootMillis) / 1000UL);

  mqtt.publish(TOPIC_ALERT, payload);
  Serial.printf("[ALERT] %s -> %s (%s, %.2f ppm, %s)\n",
                LEVEL_NAME[prev], LEVEL_NAME[level], reason,
                ppmAvg, dhtOk ? ENV_NAME[envFlag] : "NO-DHT");
}

/* ==========================================================================
 *  6. PERINTAH SERIAL MONITOR (kalibrasi & diagnosa)
 * ========================================================================== */

void handleSerial() {
  static char buf[48];
  static uint8_t len = 0;

  while (Serial.available()) {
    char c = (char)Serial.read();

    if (c == '\r' || c == '\n') {
      if (len == 0) continue;
      buf[len] = '\0';
      len = 0;

      String cmd(buf);
      cmd.trim();
      if (cmd.length() == 0) continue;

      if (cmd == "?") {
        printCalState();
      } else if (cmd == "dht") {
        printDhtState();
      } else if (cmd == "scan") {
        dhtScan(false);
      } else if (cmd == "r" || cmd == "reset") {
        vPerDecade = V_PER_DECADE_DEFAULT;
        vAt1ppm    = V_AT_1PPM_DEFAULT;
        calPpm[0] = calPpm[1] = NAN;
        calVolt[0] = calVolt[1] = NAN;
        Serial.println(F("[CAL] Dikembalikan ke nilai default."));
      } else {
        int sep = cmd.indexOf(' ');
        bool ok = false;
        if (sep > 0) {
          String key = cmd.substring(0, sep);
          float val = cmd.substring(sep + 1).toFloat();
          if ((key == "c1" || key == "c2") && val > 0.0f) {
            captureCalPoint(key == "c1" ? 0 : 1, val);
            ok = true;
          }
        }
        if (!ok) {
          Serial.println(F("[CMD] Tidak dikenal. Gunakan: c1 <ppm> | c2 <ppm> "
                           "| dht | scan | r | ?"));
        }
      }
      continue;
    }

    if (len < sizeof(buf) - 1) {
      buf[len++] = c;
    } else {
      len = 0;   // buang baris yang terlalu panjang
    }
  }
}

/* ==========================================================================
 *  7. SIKLUS UTAMA
 * ========================================================================== */

void sampleSensors() {
  ppmRaw = readCoPpm();
  ppmAvg = pushAverage(ppmRaw);

  /* redundansi: keluaran digital MQ-2 (LOW = melewati ambang potensiometer) */
  mqDoutLow = (digitalRead(PIN_MQ_DOUT) == LOW);

  Level   coPrev  = coLevel;
  EnvFlag envPrev = envFlag;

  coLevel = classify(ppmAvg, coLevel);
  envFlag = envCheck(tempC, humPct, dhtOk, envFlag);

  Level prev = level;
  level = combineLevels(coLevel, envFlag);

  /*
   * DOUT sebagai penguat keputusan (hardware comparator).
   *
   * Dua syarat harus terpenuhi sebelum DOUT boleh menaikkan level:
   *   1. tegangan AOUT sudah melewati ambang komparator (DOUT_THRESHOLD_V),
   *      sehingga DOUT yang tertahan LOW karena kabel lepas tidak memicu
   *      BAHAYA palsu;
   *   2. pembacaan analog sudah mencapai WASPADA.
   * Keduanya membuat DOUT hanya memperkuat keputusan, tidak pernah
   * bertentangan dengan jalur analog.
   */
  if (mqDoutLow && lastVoltOut >= DOUT_THRESHOLD_V
      && ppmAvg >= TH_WASPADA && level < LV_BAHAYA) {
    level = LV_BAHAYA;
  }

  if (level != prev) {
    const char* reason = (coLevel != coPrev) ? "co"
                       : (envFlag != envPrev) ? "env"
                       : "dout";
    publishAlert(prev, reason);
  }

  /*
   * Serial Monitor: jendela debugging. Kolom "i" adalah nilai sesaat sebelum
   * dirata-rata, "raw" nilai ADC mentah, dan "V" tegangan keluaran sensor.
   * Bagian setelah tanda "|" memuat suhu, kelembapan, flag lingkungan, lalu
   * level CO dan level akhir. Panjang baris dijaga di bawah 94 karakter agar
   * tidak terpotong pada Serial Monitor maupun pada dokumen laporan.
   */
  char envBuf[24];
  if (dhtOk) {
    snprintf(envBuf, sizeof(envBuf), "%4.1fC %4.1f%%RH %-6s",
             tempC, humPct, ENV_NAME[envFlag]);
  } else {
    snprintf(envBuf, sizeof(envBuf), "DHT TIDAK TERBACA    ");
  }

  Serial.printf("[%6lu ms] CO=%6.2f i=%6.2f raw=%4d V=%.3f d=%d | %s | %s->%s\n",
                millis(), ppmAvg, ppmRaw, lastRawAdc, lastVoltOut,
                mqDoutLow ? 0 : 1, envBuf,
                LEVEL_NAME[coLevel], LEVEL_NAME[level]);
}

/*
 * Pembacaan DHT22.
 *
 * Catatan penting mengenai library DHTesp:
 *   - readSensor() menolak pembacaan yang berjarak kurang dari 1999 ms dan
 *     langsung kembali TANPA memperbarui status. Karena itu percobaan ulang
 *     berjarak dekat tidak berguna; satu percobaan per siklus DHT_MS (2200 ms)
 *     sudah merupakan laju maksimum yang diizinkan sensor.
 *   - getStatus() hanya mengembalikan ERROR_NONE, ERROR_TIMEOUT, atau
 *     ERROR_CHECKSUM. TIMEOUT berarti jalur data tidak merespons sama sekali
 *     (indikasi wiring), sedangkan CHECKSUM berarti sensor merespons tetapi
 *     data rusak.
 *
 * Nilai yang gagal dibaca TIDAK dipertahankan. Variabel ditandai tidak valid
 * (dhtOk = false) agar antarmuka menampilkan tanda "--" dan bukan angka lama
 * yang menyesatkan.
 */
void readDht() {
  TempAndHumidity th = dht.getTempAndHumidity();

  if (dht.getStatus() == DHTesp::ERROR_NONE) {
    tempC   = th.temperature;
    humPct  = th.humidity;
    dhtOkAt = millis();
    dhtLastErr = "OK";

    if (!dhtOk) {
      if (dhtFail > 0) {
        Serial.printf("[DHT] Terbaca kembali setelah %u kegagalan.\n", dhtFail);
      }
      Serial.printf("[DHT] OK: %.1f C, %.1f %%RH\n", tempC, humPct);
      dhtFail = 0;
    }
    dhtOk = true;
    return;
  }

  dhtOk = false;
  dhtFail++;
  dhtLastErr = dht.getStatusString();

  /* Laporan dibatasi 5 detik sekali agar Serial Monitor tidak dipenuhi. */
  static unsigned long lastWarn = 0;
  if (millis() - lastWarn < 5000UL) return;
  lastWarn = millis();

  Serial.printf("[DHT] Gagal baca #%u: %s\n", dhtFail, dht.getStatusString());
  if (strcmp(dht.getStatusString(), "TIMEOUT") == 0) {
    Serial.printf("[DHT] Jalur data tidak merespons. Periksa tiga kabel: "
                  "VCC->3V3, SDA->D%d, GND->GND.\n", dhtActivePin);
    Serial.println(F("[DHT] Pastikan SDA tidak terpasang pada pad NC."));
  } else {
    Serial.println(F("[DHT] Data rusak (checksum). Pembacaan akan diulang otomatis."));
  }
}

/*
 * Uji awal sensor saat boot, dijalankan SEBELUM WiFi aktif agar pembacaan
 * tidak terganggu aktivitas radio. Hasilnya dicetak lengkap sehingga
 * kegagalan wiring langsung terlihat pada Serial Monitor.
 */
void dhtSelfTest() {
  Serial.printf("[DHT] Uji awal sensor pada GPIO%d (maksimum %d percobaan)...\n",
                dhtActivePin, DHT_BOOT_TRIES);

  for (int i = 1; i <= DHT_BOOT_TRIES; i++) {
    delay(2200);
    TempAndHumidity th = dht.getTempAndHumidity();

    if (dht.getStatus() == DHTesp::ERROR_NONE) {
      tempC   = th.temperature;
      humPct  = th.humidity;
      dhtOk   = true;
      dhtOkAt = millis();
      dhtLastErr = "OK";
      Serial.printf("[DHT] Percobaan %d/%d: OK -> %.1f C, %.1f %%RH\n",
                    i, DHT_BOOT_TRIES, tempC, humPct);
      return;
    }
    dhtLastErr = dht.getStatusString();
    Serial.printf("[DHT] Percobaan %d/%d: %s\n",
                  i, DHT_BOOT_TRIES, dhtLastErr);
  }

  dhtOk = false;
  Serial.printf("[DHT] GPIO%d tidak merespons. Mencari pin lain...\n", dhtActivePin);
  dhtProbe();

  /*
   * Pemindaian otomatis: kanvas Wokwi dapat berbeda dari diagram.json yang
   * seharusnya dipakai, sehingga sensor mungkin terpasang pada pin lain.
   * Bila ditemukan, pin tersebut langsung dipakai agar sistem tetap
   * memperoleh data iklim mikro tanpa perubahan kode.
   */
  int pin = dhtScan(true);
  if (pin >= 0) {
    Serial.printf("[DHT] Sensor ditemukan pada GPIO%d dan dipakai.\n", pin);
    Serial.printf("[DHT] Ubah \"#define PIN_DHT %d\" agar sesuai wiring.\n", pin);
    return;
  }

  Serial.println(F("[DHT] Sensor tidak ditemukan. Sistem tetap berjalan dengan "
                   "level CO saja."));
  Serial.printf("[DHT] Periksa wiring: VCC->3V3, SDA->D%d, GND->GND "
                "(pad ketiga bertanda NC tidak terpakai).\n", dhtActivePin);
}

/*
 * Uji tingkat tegangan sebuah pin.
 *
 * Pin dikonfigurasi sebagai INPUT_PULLUP lalu INPUT_PULLDOWN, dan level pada
 * kedua kondisi dicatat. Perbandingan kedua nilai menunjukkan apakah jalur
 * ditahan oleh komponen luar atau hanya mengikuti resistor internal.
 */
void probePin(uint8_t pin, int &hi, int &lo) {
  pinMode(pin, INPUT_PULLUP);
  delay(5);
  hi = digitalRead(pin);

  pinMode(pin, INPUT_PULLDOWN);
  delay(5);
  lo = digitalRead(pin);

  pinMode(pin, INPUT);
}

/*
 * Diagnostik jalur data DHT22.
 *
 * Kanvas Wokwi merutekan kabel secara otomatis sehingga sambungan yang
 * bertumpuk sulit diperiksa secara visual. Fungsi ini membandingkan pin data
 * dengan pin yang sengaja dikosongkan (REF_PROBE_PIN). Pin kosong menjadi
 * acuan: bila pin kosong dan pin data memberi pola yang sama, jalur data
 * kemungkinan besar juga kosong; bila berbeda, ada komponen yang menahan pin
 * data dan kesalahannya ada pada urutan kabel.
 */
void dhtProbe() {
  int hi, lo;
  probePin(dhtActivePin, hi, lo);

  int refHi, refLo;
  probePin(REF_PROBE_PIN, refHi, refLo);

  Serial.printf("[DHT] Probe GPIO%d: pull-up=%d pull-down=%d | "
                "acuan GPIO%d: pull-up=%d pull-down=%d\n",
                dhtActivePin, hi, lo, REF_PROBE_PIN, refHi, refLo);

  bool refFloats = (refHi == 1 && refLo == 0);

  if (!refFloats) {
    Serial.println(F("[DHT] Pin acuan tidak berperilaku mengambang; simulator "
                     "tidak menerapkan INPUT_PULLDOWN."));
    Serial.println(F("[DHT] Hasil probe tidak dapat dipakai. Gunakan perintah "
                     "\"scan\" untuk mencari pin tempat sensor terpasang."));
    return;
  }

  if (hi == 1 && lo == 0) {
    Serial.println(F("[DHT] GPIO data MENGAMBANG: tidak ada komponen terpasang."));
    Serial.printf("[DHT] Sambungan \"dht1:SDA\" -> \"esp:D%d\" belum ada.\n",
                  dhtActivePin);
  } else if (hi == 0 && lo == 0) {
    Serial.println(F("[DHT] GPIO data tertahan LOW: kabel data tertukar dengan GND."));
  } else {
    Serial.println(F("[DHT] GPIO data ditahan HIGH oleh komponen luar."));
    Serial.println(F("[DHT] Dua kemungkinan: (a) SDA benar dan sensor siaga, atau"));
    Serial.println(F("[DHT] (b) SDA tertukar dengan VCC sehingga menempel ke 3V3."));
    Serial.println(F("[DHT] Urutan pad DHT22 kiri ke kanan: VCC, SDA, NC, GND."));
    Serial.println(F("[DHT] Jalankan perintah \"scan\" untuk memastikan."));
  }
}

/*
 * Mencoba membaca DHT22 pada satu pin.
 *
 * setup() memberi tahu library pin mana yang dipakai dan mengatur ulang
 * penghitung waktu, sehingga pembacaan berikutnya langsung dijalankan tanpa
 * menunggu jeda 2 detik.
 */
bool dhtTryPin(uint8_t pin, float &t, float &h) {
  dht.setup(pin, DHTesp::DHT22);
  delay(10);

  TempAndHumidity th = dht.getTempAndHumidity();
  if (dht.getStatus() != DHTesp::ERROR_NONE) return false;

  t = th.temperature;
  h = th.humidity;
  return true;
}

/*
 * Mencari pin tempat DHT22 benar-benar terpasang.
 *
 * Setiap kandidat dicoba satu kali. Pin yang berhasil dibaca berarti di situlah
 * jalur data sensor berada, sehingga kesalahan wiring dapat diketahui tanpa
 * membaca kanvas. Pin yang dipakai komponen lain (OLED pada 21/22, buzzer pada
 * 25, ADC dan DOUT MQ-2 pada 34/32) sengaja dilewati agar tidak mengganggu I2C
 * maupun pembacaan sensor gas.
 *
 * Parameter adopt menentukan apakah pin hasil temuan langsung dipakai. Pada
 * mode manual (perintah "scan") hasilnya hanya dilaporkan agar konfigurasi
 * tidak berubah tanpa sepengetahuan pengguna.
 */
int dhtScan(bool adopt) {
  const uint8_t kandidat[] = { 4, 2, 5, 12, 13, 14, 15, 18, 19, 23, 26, 27, 33 };
  const uint8_t jumlah = sizeof(kandidat) / sizeof(kandidat[0]);

  if (!adopt) Serial.println(F("[DHT] Mencari sensor pada pin kandidat..."));

  /*
   * Pola pin acuan dicatat lebih dahulu. Bila pin kosong pun terbaca HIGH pada
   * kedua konfigurasi, simulator tidak menerapkan resistor pull-down dan pola
   * (1,1) pada pin lain tidak dapat dianggap bukti adanya komponen.
   */
  int refHi, refLo;
  probePin(REF_PROBE_PIN, refHi, refLo);
  bool pulldownValid = (refHi == 1 && refLo == 0);

  int ketemu = -1;
  int ditahanHigh = -1;

  for (uint8_t i = 0; i < jumlah; i++) {
    uint8_t p = kandidat[i];
    float t, h;

    int hi, lo;
    probePin(p, hi, lo);

    if (dhtTryPin(p, t, h)) {
      if (!adopt) {
        Serial.printf("  GPIO%-2d : OK -> %.1f C, %.1f %%RH\n", p, t, h);
      }
      if (ketemu < 0) ketemu = p;
    } else if (!adopt) {
      Serial.printf("  GPIO%-2d : %-8s (pu=%d pd=%d)\n",
                    p, dht.getStatusString(), hi, lo);
      if (pulldownValid && hi == 1 && lo == 1 && ditahanHigh < 0) {
        ditahanHigh = p;
      }
    }
  }

  if (ketemu >= 0 && adopt) {
    dhtActivePin = (uint8_t)ketemu;
    float t, h;
    if (dhtTryPin(dhtActivePin, t, h)) {
      tempC   = t;
      humPct  = h;
      dhtOk   = true;
      dhtOkAt = millis();
      dhtFail = 0;
      dhtLastErr = "OK";
    }
  } else if (ketemu < 0) {
    /* Tidak ada yang berhasil: kembalikan library ke pin semula. */
    dht.setup(dhtActivePin, DHTesp::DHT22);
    dhtOk = false;
  }

  if (!adopt) {
    Serial.println(F("[DHT] ----------------------------------------"));
    if (ketemu < 0) {
      Serial.println(F("[DHT] Sensor tidak ditemukan pada pin mana pun."));
      if (ditahanHigh >= 0) {
        Serial.printf("[DHT] GPIO%d ditahan HIGH padahal pin acuan tidak, "
                      "sehingga jalur data\n", ditahanHigh);
        Serial.println(F("[DHT] kemungkinan menempel pada rel 3V3, bukan pada "
                         "pin GPIO."));
      }
      Serial.printf("[DHT] Periksa tiga kabel DHT22: VCC->3V3, SDA->D%d, GND->GND.\n",
                    PIN_DHT);
      Serial.println(F("[DHT] Pad ketiga bertanda NC tidak boleh dipakai."));
    } else if (ketemu == dhtActivePin) {
      Serial.printf("[DHT] Sensor terpasang pada GPIO%d, sesuai sketch.\n", ketemu);
      Serial.println(F("[DHT] Pembacaan gagal karena sebab lain; periksa VCC dan GND."));
    } else {
      Serial.printf("[DHT] Sensor terpasang pada GPIO%d, bukan GPIO%d.\n",
                    ketemu, dhtActivePin);
      Serial.printf("[DHT] Ubah \"#define PIN_DHT %d\" atau pindahkan kabel SDA "
                    "ke esp:D%d.\n", ketemu, dhtActivePin);
    }
  }

  return ketemu;
}

void setup() {
  Serial.begin(115200);
  delay(200);
  bootMillis = millis();

  Serial.println();
  Serial.println(F("=============================================="));
  Serial.println(F("  CO-Zero v1.0 | Tim Iki jenenge wes wkwk"));
  Serial.println(F("  Monitoring CO Kabin Mobil - SIC Batch 8"));
  Serial.println(F("=============================================="));

  /* output */
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);

  /* input */
  pinMode(PIN_MQ_DOUT, INPUT);
  analogSetPinAttenuation(PIN_MQ_ADC, ADC_11db);

  /* OLED */
  Wire.begin(PIN_OLED_SDA, PIN_OLED_SCL);
  if (!oled.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("[OLED] inisialisasi gagal"));
  } else {
    oled.clearDisplay();
    oled.setTextColor(SSD1306_WHITE);
    oled.setTextSize(1);
    oled.setCursor(0, 0);
    oled.print(F("CO-Zero booting..."));
    oled.display();
  }

  /* DHT22: uji awal dijalankan sebelum WiFi agar tidak terganggu aktivitas radio */
  dhtActivePin = PIN_DHT;
  dht.setup(dhtActivePin, DHTesp::DHT22);
  dhtSelfTest();

  /* Skala sensor: nilai default, dapat dikalibrasi lewat Serial Monitor */
  vPerDecade = V_PER_DECADE_DEFAULT;
  vAt1ppm    = V_AT_1PPM_DEFAULT;
  Serial.printf("[CAL] Skala log: %.4f V/dekade, 1 ppm = %.4f V\n",
                vPerDecade, vAt1ppm);
  Serial.println(F("[CAL] Kalibrasi: c1 <ppm>, c2 <ppm>, ? | Diagnosa: dht, scan"));
  Serial.println(F("[INFO] Kolom: CO=ppm i=instan raw=ADC V=volt d=DOUT"));
  Serial.println(F("[INFO] Contoh: ... | 29.0C 61.0%RH NORMAL | AMAN->AMAN"));

  /* Jaringan */
  ensureWifi();
  net.setInsecure();                 // penyederhanaan simulasi, lihat catatan laporan
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);
  mqtt.setKeepAlive(30);

  /*
   * Bila MQTT_HOST masih berupa placeholder "xxxxxxxxxxxx...", MQTT dimatikan
   * agar Serial Monitor tidak dipenuhi pesan "GAGAL (rc=5)". Seluruh fitur
   * lokal (sensor, OLED, buzzer) tetap berjalan normal.
   */
  mqttConfigured = (strncmp(MQTT_HOST, "xxxx", 4) != 0);
  if (mqttConfigured) {
    Serial.printf("[MQTT] Broker: %s:%d\n", MQTT_HOST, MQTT_PORT);
  } else {
    Serial.println(F("[MQTT] Kredensial HiveMQ belum diisi -> MQTT nonaktif."));
    Serial.println(F("[MQTT] Fitur lokal (OLED/buzzer) tetap berjalan."));
  }
}

void loop() {
  unsigned long now = millis();

  handleSerial();
  ensureWifi();
  ensureMqtt();
  mqtt.loop();

  if (now - tSample >= SAMPLE_MS) {
    tSample = now;
    sampleSensors();
  }

  if (now - tDht >= DHT_MS) {
    tDht = now;
    readDht();
  }

  if (now - tPublish >= PUBLISH_MS) {
    tPublish = now;
    publishTelemetry();
  }

  if (now - tOled >= OLED_MS) {
    tOled = now;
    drawOled();
  }

  updateBuzzer(now);
}
