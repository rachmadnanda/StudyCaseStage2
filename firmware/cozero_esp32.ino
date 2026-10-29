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
 *        --> LED + Buzzer + OLED (lokal, tetap jalan tanpa internet)
 *        --> WiFi --> MQTT (HiveMQ Cloud) --> Dashboard Python
 *
 *  CATATAN SIMULASI
 *    - Wokwi tidak menyediakan MQ-7. Digunakan modul MQ-2 yang juga sensitif
 *      terhadap CO. Keduanya sensor MOS berbasis heater dengan keluaran analog,
 *      sehingga logika sistem tidak berubah.
 *    - Nilai ppm sensor di Wokwi diatur lewat atribut "ppm" pada diagram.json
 *      dan bisa digeser saat simulasi berjalan (klik sensor).
 *    - Kalau atribut "ppm" diabaikan simulator, cukup geser slider setelah
 *      simulasi berjalan. Kalibrasi dua titik (c1/c2) membuat skala ppm tetap
 *      akurat tanpa mengubah kode.
 *    - Resistor pembagi tegangan tidak bisa dipakai di Wokwi; lihat bagian
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

/* --- HiveMQ Cloud (ganti dengan kredensial cluster kamu) --- */
#define MQTT_HOST       "xxxxxxxxxxxx.s1.eu.hivemq.cloud"
#define MQTT_PORT       8883
#define MQTT_USER       "ISI_USERNAME_HIVEMQ"
#define MQTT_PASS       "ISI_PASSWORD_HIVEMQ"

/* --- Topik MQTT --- */
#define TOPIC_BASE      "cozero/team"
#define TOPIC_TELEMETRY TOPIC_BASE "/telemetry"
#define TOPIC_ALERT     TOPIC_BASE "/alert"
#define TOPIC_STATUS    TOPIC_BASE "/status"

/* --- Pin GPIO (lihat tabel di laporan) --- */
#define PIN_MQ_ADC      34   // ADC1_CH6, input-only
#define PIN_MQ_DOUT     32   // keluaran digital MQ-2 (redundan)
#define PIN_DHT         4
#define PIN_BUZZER      25
#define PIN_LED_G       26
#define PIN_LED_Y       27
#define PIN_LED_R       14
#define PIN_OLED_SDA    21
#define PIN_OLED_SCL    22

/* --- Ambang batas (ppm) --- */
#define TH_WASPADA      20
#define TH_BAHAYA       35
#define TH_KRITIS       115
#define HISTERESIS      3.0f   // ppm, mencegah LED berkedip di batas

/* --- Waktu (ms) --- */
#define SAMPLE_MS       500
#define PUBLISH_MS      2000
#define DHT_MS          2500
#define OLED_MS         300
#define MQTT_RETRY_MS   5000
#define WIFI_RETRY_MS   5000

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
 * Skala awal: diasumsikan keluaran MQ-2 Wokwi linier 0..5 V untuk 0..1000 ppm,
 * sehingga 1 V = 200 ppm. Dengan VCC 5 V dan ADC 12-bit (3,3 V), pembacaan
 * masih linear sampai sekitar 660 ppm - cukup untuk seluruh skenario uji.
 * Jika angka ppm di Serial tidak cocok dengan slider sensor, lakukan
 * KALIBRASI DUA TITIK lewat Serial Monitor (lihat fungsi handleSerial()).
 */
#define PPM_PER_VOLT_DEFAULT  200.0f
#define BASELINE_VOLT_DEFAULT 0.0f

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
float ppmPerVolt    = PPM_PER_VOLT_DEFAULT;
float baselineVolt  = BASELINE_VOLT_DEFAULT;

/* titik kalibrasi yang sedang menunggu pasangan (NaN = belum diisi) */
float calPpm[2]     = { NAN, NAN };
float calVolt[2]    = { NAN, NAN };

/* state iklim mikro */
float tempC         = 0.0f;
float humPct        = 0.0f;
bool  dhtOk         = false;

/* state sistem */
Level level         = LV_AMAN;

/* timing */
unsigned long tSample = 0, tPublish = 0, tDht = 0, tOled = 0, tMqtt = 0, tWifi = 0;
unsigned long bootMillis = 0;

/* buzzer */
bool bzState = false;

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
 *  1. Geser slider ppm sensor ke nilai acuan pertama, misal 100.
 *  2. Ketik:  c1 100      -> firmware menyimpan pasangan (100 ppm, Vout saat ini)
 *  3. Geser slider ke nilai acuan kedua, misal 500.
 *  4. Ketik:  c2 500      -> firmware menghitung ppmPerVolt dan baselineVolt
 *
 * PENTING: pilih titik acuan di daerah linear ADC (disarankan 100 dan 500 ppm).
 * Tanpa pembagi tegangan, ADC ESP32 jenuh di sekitar 3,1-3,3 V sehingga titik
 * acuan yang terlalu tinggi (mis. 900 ppm) akan menghasilkan kalibrasi salah.
 *  5. Ketik:  ?           -> menampilkan hasil kalibrasi
 *  6. Ketik:  r           -> kembali ke nilai default
 *
 * Hasil kalibrasi hanya tersimpan di RAM (hilang saat restart), sesuai
 * kebutuhan simulasi. Untuk perangkat fisik, simpan nilainya sebagai
 * PPM_PER_VOLT_DEFAULT / BASELINE_VOLT_DEFAULT di bagian KONFIGURASI.
 */
void captureCalPoint(int idx, float ppmRef) {
  calPpm[idx]  = ppmRef;
  calVolt[idx] = lastVoltOut;
  Serial.printf("[CAL] Titik %d disimpan: %.1f ppm = %.4f V\n",
                idx + 1, ppmRef, lastVoltOut);

  if (!isnan(calPpm[0]) && !isnan(calPpm[1]) && fabs(calVolt[1] - calVolt[0]) > 0.01f) {
    ppmPerVolt = (calPpm[1] - calPpm[0]) / (calVolt[1] - calVolt[0]);
    baselineVolt = calVolt[0] - (calPpm[0] / ppmPerVolt);
    Serial.printf("[CAL] Selesai -> ppmPerVolt = %.2f | baseline = %.4f V\n",
                  ppmPerVolt, baselineVolt);
    Serial.println(F("[CAL] Salin kedua nilai ini ke bagian KONFIGURASI sketch."));
  }
}

void printCalState() {
  Serial.println(F("---- Status kalibrasi ----"));
  Serial.printf("  ppmPerVolt = %.2f\n", ppmPerVolt);
  Serial.printf("  baseline   = %.4f V\n", baselineVolt);
  Serial.printf("  Vout kini  = %.4f V -> %.1f ppm\n",
                lastVoltOut, ppmAvg);
  Serial.println(F("  Perintah: c1 <ppm> | c2 <ppm> | r | ?"));
}

float readCoPpm() {
  float v = readVoltageOut();
  float ppm = (v - baselineVolt) * ppmPerVolt;
  if (ppm < 0.0f) ppm = 0.0f;
  return ppm;
}

/* Moving average sederhana untuk menstabilkan pembacaan. */
float pushAverage(float v) {
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

/* ==========================================================================
 *  4. OUTPUT LOKAL
 * ========================================================================== */

void applyLeds(Level lv) {
  digitalWrite(PIN_LED_G, lv == LV_AMAN);
  digitalWrite(PIN_LED_Y, lv == LV_WASPADA);
  digitalWrite(PIN_LED_R, lv == LV_BAHAYA || lv == LV_KRITIS);
}

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

void drawOled() {
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);

  /* baris 1: judul + level */
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.print(F("CO-Zero | Kabin"));

  oled.setTextSize(2);
  oled.setCursor(0, 10);
  oled.print(LEVEL_NAME[level]);

  /* baris 2: kadar CO */
  oled.setTextSize(1);
  oled.setCursor(0, 30);
  oled.printf("CO  : %6.1f ppm", ppmAvg);

  /* baris 3: suhu & kelembapan */
  oled.setCursor(0, 40);
  if (dhtOk) oled.printf("Suhu: %4.1f C  RH: %2.0f%%", tempC, humPct);
  else       oled.print(F("Suhu: --      RH: --"));

  /* baris 4: status jaringan */
  oled.setCursor(0, 50);
  oled.printf("WiFi:%s MQTT:%s",
               WiFi.status() == WL_CONNECTED ? "OK" : "--",
               mqtt.connected() ? "OK" : "--");

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

  char payload[240];
  snprintf(payload, sizeof(payload),
           "{\"device_id\":\"%s\",\"co_ppm\":%.1f,\"temp_c\":%.1f,\"rh\":%.1f,"
           "\"level\":\"%s\",\"level_code\":%d,\"raw\":%d,\"volt\":%.2f,"
           "\"dout\":%d,\"uptime_s\":%lu}",
           DEVICE_ID, ppmAvg, tempC, humPct,
           LEVEL_NAME[level], (int)level, lastRawAdc, lastVoltOut,
           mqDoutLow ? 0 : 1, (millis() - bootMillis) / 1000UL);

  mqtt.publish(TOPIC_TELEMETRY, payload);
}

void publishAlert(Level prev) {
  if (!mqtt.connected()) return;

  char payload[180];
  snprintf(payload, sizeof(payload),
           "{\"device_id\":\"%s\",\"prev\":\"%s\",\"level\":\"%s\","
           "\"co_ppm\":%.1f,\"uptime_s\":%lu}",
           DEVICE_ID, LEVEL_NAME[prev], LEVEL_NAME[level],
           ppmAvg, (millis() - bootMillis) / 1000UL);

  mqtt.publish(TOPIC_ALERT, payload);
  Serial.printf("[ALERT] %s -> %s (%.1f ppm)\n",
                LEVEL_NAME[prev], LEVEL_NAME[level], ppmAvg);
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
      } else if (cmd == "r" || cmd == "reset") {
        ppmPerVolt = PPM_PER_VOLT_DEFAULT;
        baselineVolt = BASELINE_VOLT_DEFAULT;
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
          Serial.println(F("[CMD] Tidak dikenal. Gunakan: c1 <ppm> | c2 <ppm> | r | ?"));
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

  Level prev = level;
  level = classify(ppmAvg, level);

  /*
   * DOUT sebagai penguat keputusan (hardware comparator).
   * Hanya boleh MENAIKKAN level, dan hanya jika pembacaan analog sudah
   * menunjukkan peningkatan. Ini mencegah DOUT yang "nyangkut" LOW
   * memaksa status BAHAYA saat udara kabin masih bersih.
   */
  if (mqDoutLow && ppmAvg >= TH_WASPADA && level < LV_BAHAYA) {
    level = LV_BAHAYA;
  }

  if (level != prev) {
    publishAlert(prev);
  }

  applyLeds(level);

  /* Serial Monitor: jendela debugging */
  Serial.printf("[%6lu ms] CO=%6.1f ppm (raw=%4d Vout=%.2fV dout=%d) | "
                "%4.1fC %2.0f%% | %s\n",
                millis(), ppmAvg, lastRawAdc, lastVoltOut, mqDoutLow ? 0 : 1,
                tempC, humPct, LEVEL_NAME[level]);}

void readDht() {
  TempAndHumidity th = dht.getTempAndHumidity();
  if (dht.getStatus() == DHTesp::ERROR_NONE) {
    tempC = th.temperature;
    humPct = th.humidity;
    dhtOk = true;
  } else {
    dhtOk = false;
    Serial.printf("[DHT] gagal baca: %s\n", dht.getStatusString());
  }
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
  pinMode(PIN_LED_G, OUTPUT);
  pinMode(PIN_LED_Y, OUTPUT);
  pinMode(PIN_LED_R, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_LED_G, HIGH);   // boot: hijau
  digitalWrite(PIN_LED_Y, LOW);
  digitalWrite(PIN_LED_R, LOW);

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

  /* DHT22 */
  dht.setup(PIN_DHT, DHTesp::DHT22);

  /* Skala sensor: nilai default, dapat dikalibrasi lewat Serial Monitor */
  ppmPerVolt = PPM_PER_VOLT_DEFAULT;
  baselineVolt = BASELINE_VOLT_DEFAULT;
  Serial.printf("[CAL] Skala awal: %.1f ppm/V, baseline %.3f V\n",
                ppmPerVolt, baselineVolt);
  Serial.println(F("[CAL] Butuh kalibrasi? Geser slider lalu ketik: c1 <ppm>, c2 <ppm>, ?"));

  /* Jaringan */
  ensureWifi();
  net.setInsecure();                 // simplifikasi simulasi, lihat catatan laporan
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);
  mqtt.setKeepAlive(30);
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
