#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoOTA.h>
#include <AccelStepper.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>

// Pin Definitions
#define DIR_PIN 15
#define STEP_PIN 2
#define LIMIT_SWITCH1_PIN 27
#define LIMIT_SWITCH2_PIN 26
#define SLEEP_PIN 4
#define SERVO_PIN 25

// Servo Steps definition (all active for 1/16)
#define MS1 13
#define MS2 12
#define MS3 14

#define PUMP1_PIN 21
#define PUMP2_PIN 19
#define PUMP3_PIN 18
#define PUMP4_PIN 5

struct Pump {
    uint8_t pin;
    bool active;
    unsigned long start;
    unsigned long duration;
};

Pump pumps[4] = {
    {PUMP1_PIN, false, 0, 0},
    {PUMP2_PIN, false, 0, 0},
    {PUMP3_PIN, false, 0, 0},
    {PUMP4_PIN, false, 0, 0}
};

AccelStepper stepper(AccelStepper::DRIVER, STEP_PIN, DIR_PIN);
Servo myServo;
int servoDelay = 1000;

const char* ssid = "ssid";
const char* password = "pass";

IPAddress local_IP(192, 168, 2, 236);
IPAddress gateway(192, 168, 2, 1);
IPAddress subnet(255, 255, 255, 0);
IPAddress dns(192, 168, 2, 40);

const int moveMaxSpeed = 6000;
const int moveAcceleration = 1200;
const int calibMaxSpeed = 2600;
const int maxMillimeters = 1200;

long maxSteps = 0;
long currentPosition = 0;

void createJsonResponse(const char* status, const char* message, String &response) {
    StaticJsonDocument<200> doc;
    doc["status"] = status;
    doc["message"] = message;
    serializeJson(doc, response);
}

void setup() {
    Serial.begin(115200);
    Serial.println("DEBUG: ESP32 Initialisierung gestartet");

    pinMode(LIMIT_SWITCH1_PIN, INPUT);
    pinMode(LIMIT_SWITCH2_PIN, INPUT);
    pinMode(SLEEP_PIN, OUTPUT);
    digitalWrite(SLEEP_PIN, LOW);

    pinMode(MS1, OUTPUT);
    pinMode(MS2, OUTPUT);
    pinMode(MS3, OUTPUT);
    digitalWrite(MS1, HIGH);
    digitalWrite(MS2, HIGH);
    digitalWrite(MS3, HIGH);

    for (int i = 0; i < 4; i++) {
        pinMode(pumps[i].pin, OUTPUT);
        digitalWrite(pumps[i].pin, HIGH);
        pumps[i].active = false;
    }

    stepper.setMaxSpeed(moveMaxSpeed);
    stepper.setAcceleration(moveAcceleration);

    myServo.attach(SERVO_PIN);
    myServo.write(90);

    connectToWiFi();
    setupOTA();

    calibratePlatform();
    moveToMM(maxMillimeters / 2);

    Serial.println("DEBUG: Setup abgeschlossen.");
}

void loop() {
    ArduinoOTA.handle();
    handlePumpDurations();
    handleSerialCommands();
}

void handlePumpDurations() {
    unsigned long currentMillis = millis();
    for (int i = 0; i < 4; i++) {
        if (pumps[i].active && (currentMillis - pumps[i].start >= pumps[i].duration)) {
            // Pumpe automatisch deaktivieren
            pumps[i].active = false;
            digitalWrite(pumps[i].pin, HIGH);
            Serial.printf("DEBUG: Pumpe %d deaktiviert.\n", i + 1);
        }
    }
}

void handleSerialCommands() {
    static String inputString = "";
    while (Serial.available() > 0) {
        char c = (char)Serial.read();
        if (c == '\n') {
            if (inputString.length() > 0) {
                processSerialCommand(inputString);
                inputString = "";
            }
        } else {
            inputString += c;
        }
    }
}

void processSerialCommand(String commandStr) {
    StaticJsonDocument<200> doc;
    DeserializationError error = deserializeJson(doc, commandStr);
    if (error) {
        Serial.println("DEBUG: Ungültiges JSON ignoriert.");
        return;
    }

    const char* cmd = doc["command"];
    if (!cmd) return;

    String response;

    if (strcmp(cmd, "move") == 0) {
        int targetMM = doc["position"];
        Serial.printf("DEBUG: Bewegung zu %d mm angefordert.\n", targetMM);
        moveToMM(targetMM);

        // Jetzt nur JSON, keine weiteren Ausgaben danach
        createJsonResponse("success", "Bewegung abgeschlossen", response);
        Serial.println(response);

    } else if (strcmp(cmd, "servo") == 0) {
        int delayTime = doc["delay"];
        if (delayTime < 0) {
            createJsonResponse("error", "Ungültige Verzögerung", response);
            Serial.println(response);
            return; 
        }

        Serial.printf("DEBUG: Servo bewegen (180 Grad), warte %d ms, zurück zu 90 Grad.\n", delayTime);
        servoDelay = delayTime;
        myServo.write(180);
        delay(180);
        delay(servoDelay);
        myServo.write(90);
        delay(180);

        createJsonResponse("success", "Servo-Bewegung abgeschlossen", response);
        Serial.println(response);

    } else if (strcmp(cmd, "pump") == 0) {
        int pumpNumber = doc["pump"];
        int duration = doc["duration"];
        if (pumpNumber < 1 || pumpNumber > 4 || duration <= 0) {
            createJsonResponse("error", "Ungültige Pumpennummer oder Dauer", response);
            Serial.println(response);
            return;
        }

        // Debug vor JSON
        Serial.printf("DEBUG: Pumpe %d wird für %d ms aktiviert.\n", pumpNumber, duration);

        // Pumpe aktivieren ohne späteres delay oder Ausgabe
        Pump &pump = pumps[pumpNumber - 1];
        if (pump.active) {
            Serial.println("DEBUG: Pumpe ist bereits aktiv, ignoriere Aktivierung.");
            createJsonResponse("error", "Pumpe bereits aktiv", response);
            Serial.println(response);
            return;
        }

        pump.active = true;
        pump.start = millis();
        pump.duration = duration;
        digitalWrite(pump.pin, LOW);

        // Jetzt JSON ausgeben, danach keine Ausgaben mehr
        createJsonResponse("success", "Pumpe aktiviert", response);
        Serial.println(response);

        // KEINE weitere Ausgabe nach JSON!

    } else if (strcmp(cmd, "status") == 0) {
        // Keine Debug-Ausgabe, direkt JSON
        StaticJsonDocument<256> statusDoc;
        statusDoc["status"] = "online";
        JsonArray pumpStatuses = statusDoc.createNestedArray("pumps");
        for (int i = 0; i < 4; i++) {
            JsonObject pumpObj = pumpStatuses.createNestedObject();
            pumpObj["pumpNumber"] = i + 1;
            pumpObj["active"] = pumps[i].active;
            pumpObj["remainingTime"] = pumps[i].active ? (pumps[i].duration - (millis() - pumps[i].start)) : 0;
        }
        serializeJson(statusDoc, response);
        Serial.println(response);

        // Keine weitere Ausgabe nach JSON!
    }
}

void connectToWiFi() {
  Serial.println("DEBUG: Statische IP konfigurieren...");
  if (!WiFi.config(local_IP, gateway, subnet, dns)) {
    Serial.println("DEBUG: Fehler: Statische IP konnte nicht konfiguriert werden!");
  } else {
    Serial.println("DEBUG: Statische IP erfolgreich konfiguriert.");
  }

  Serial.printf("DEBUG: Verbinde mit WLAN '%s'...\n", ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
  }
  Serial.printf("DEBUG: WLAN verbunden! IP-Adresse: %s\n", WiFi.localIP().toString().c_str());
}

void setupOTA() {
  ArduinoOTA.setHostname("ESP32-Stepper");

  ArduinoOTA.onStart([]() {
    String type = (ArduinoOTA.getCommand() == U_FLASH) ? "Sketch" : "SPIFFS";
    Serial.printf("DEBUG: OTA-Update gestartet: %s\n", type.c_str());
  });
  ArduinoOTA.onEnd([]() {
    Serial.println("DEBUG: OTA-Update abgeschlossen.");
  });
  ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
    Serial.printf("DEBUG: OTA-Fortschritt: %u%%\r", (progress / (total / 100)));
  });
  ArduinoOTA.onError([](ota_error_t error) {
    Serial.printf("DEBUG: OTA-Fehler [%u]: ", error);
    if (error == OTA_AUTH_ERROR) Serial.println("DEBUG: Authentifizierungsfehler");
    else if (error == OTA_BEGIN_ERROR) Serial.println("DEBUG: Beginn-Fehler");
    else if (error == OTA_CONNECT_ERROR) Serial.println("DEBUG: Verbindungsfehler");
    else if (error == OTA_RECEIVE_ERROR) Serial.println("DEBUG: Empfangsfehler");
    else if (error == OTA_END_ERROR) Serial.println("DEBUG: Ende-Fehler");
  });

  ArduinoOTA.begin();
  Serial.println("DEBUG: OTA eingerichtet.");
}

void enableDriver() {
  Serial.println("DEBUG: Treiber aktivieren...");
  digitalWrite(SLEEP_PIN, HIGH);
}

void disableDriver() {
  Serial.println("DEBUG: Treiber deaktivieren...");
  digitalWrite(SLEEP_PIN, LOW);
}

void calibratePlatform() {
    Serial.println("DEBUG: Kalibrierung: Bewege zu Endschalter 1...");
    enableDriver();

    stepper.setSpeed(-calibMaxSpeed);

    // Starte die Kalibrierungsfahrt in Richtung Endschalter 1
    while (true) {
        // So lange der Schalter NICHT gedrückt ist (LOW), weiterfahren
        if (digitalRead(LIMIT_SWITCH1_PIN) == LOW) {
            stepper.runSpeed();
        } else {
            // Sobald der Pin HIGH meldet, kurz warten, um Prellen zu vermeiden
            delay(50); 
            // Jetzt erneut prüfen, ob der Schalter immer noch HIGH ist
            if (digitalRead(LIMIT_SWITCH1_PIN) == HIGH) {
                // Debounce-Bestätigung: Schalter wirklich ausgelöst
                break;
            }
        }
    }

    // Schritt-Motor anhalten
    stepper.stop();
    // Bezugsposition auf 0 setzen
    stepper.setCurrentPosition(0);
    Serial.println("DEBUG: Kalibrierung: Endschalter 1 erreicht. Position auf 0 gesetzt.");

    Serial.println("DEBUG: Kalibrierung: Bewege zu Endschalter 2...");
    stepper.setSpeed(calibMaxSpeed);

    // Fahre in die andere Richtung bis Endschalter 2
    while (true) {
        if (digitalRead(LIMIT_SWITCH2_PIN) == LOW) {
            stepper.runSpeed();
        } else {
            delay(50);
            if (digitalRead(LIMIT_SWITCH2_PIN) == HIGH) {
                break;
            }
        }
    }

    stepper.stop();
    // Maximale Schritte speichern
    maxSteps = stepper.currentPosition();
    Serial.printf("DEBUG: Kalibrierung abgeschlossen. Maximale Schritte: %ld\n", maxSteps);

    disableDriver();
}


void moveToMM(int targetMM) {
  if (targetMM < 0 || targetMM > maxMillimeters) {
    Serial.printf("DEBUG: Ungültige Position: %d mm (Erlaubt: 0-%d mm)\n", targetMM, maxMillimeters);
    return;
  }

  long steps = map(targetMM, 0, maxMillimeters, 0, maxSteps);
  Serial.printf("DEBUG: Bewege Plattform zu %d mm (%ld Schritte)...\n", targetMM, steps);

  enableDriver();
  stepper.moveTo(steps);

  while (stepper.distanceToGo() != 0) {
    stepper.run();
  }

  currentPosition = stepper.currentPosition();
  Serial.printf("DEBUG: Position erreicht: %d mm (%ld Schritte).\n", targetMM, currentPosition);

  disableDriver();
}

void activatePump(int pumpNumber, int duration) {
    // Diese Funktion aktiviert die Pumpe sofort und vertraut darauf,
    // dass handlePumpDurations() sie später automatisch ausschaltet.
    Pump &pump = pumps[pumpNumber - 1];
    pump.active = true;
    pump.start = millis();
    pump.duration = duration;
    digitalWrite(pump.pin, LOW);
    // Keine weiteren Ausgaben nach der JSON-Antwort!
}
