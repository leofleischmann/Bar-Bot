#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import cv2
from pyzbar.pyzbar import decode
import socket
import time
import os
import subprocess

########################################
# Hilfsfunktionen
########################################

def is_connected():
    """
    Einfache Prüfung, ob eine Internetverbindung (TCP-Port 80 zu Google) besteht.
    Gibt True zurück, wenn online, sonst False.
    """
    try:
        socket.create_connection(("www.google.com", 80), timeout=5)
        return True
    except OSError:
        return False

def parse_wifi_qr(qr_string):
    """
    Erwartet einen QR-Inhalt etwa im Format:
       WIFI:S:<SSID>;T:<WPA|WPA2|WEP|nopass>;P:<PASSWORD>;H:<true|false>;;
    Gibt ein Dict zurück mit Schlüsseln:
      {
        'ssid': str,
        'password': str,
        'encryption': str,  # 'WPA', 'WPA2', 'WEP', 'nopass', etc.
        'hidden': bool
      }
    oder None, wenn nicht erkennbar.
    """
    if not qr_string.startswith("WIFI:"):
        return None

    # "WIFI:" entfernen, rest splitten
    content = qr_string[5:]
    segments = content.split(";")
    wifi_data = {
        "ssid": "",
        "password": "",
        "encryption": "nopass",
        "hidden": False
    }
    for seg in segments:
        seg = seg.strip()
        if seg.startswith("S:"):
            wifi_data["ssid"] = seg[2:]
        elif seg.startswith("P:"):
            wifi_data["password"] = seg[2:]
        elif seg.startswith("T:"):
            wifi_data["encryption"] = seg[2:].upper()  # z.B. "WPA", "WPA2", ...
        elif seg.startswith("H:"):
            val = seg[2:].lower()
            wifi_data["hidden"] = (val == "true")

    # Gültig, wenn zumindest SSID und Passwort vorhanden oder "nopass" (je nach Fall).
    # Wir gehen hier davon aus, dass wir min. SSID + Passwort brauchen.
    # Falls "nopass", könntest du 'password' leer lassen.
    if wifi_data["ssid"] and wifi_data["password"]:
        return wifi_data
    return None

def write_wpa_supplicant_conf(wifi_info):
    """
    Erstellt /etc/wpa_supplicant/wpa_supplicant.conf entsprechend wifi_info-Dict.
    wifi_info = {
       'ssid': str,
       'password': str,
       'encryption': 'WPA' | 'WPA2' | 'WEP' | 'nopass',
       'hidden': bool
    }
    """
    ssid = wifi_info["ssid"]
    password = wifi_info["password"]
    encryption = wifi_info["encryption"]
    hidden = wifi_info["hidden"]

    # Standardwerte
    proto_line = "proto=RSN"            # RSN für WPA2
    key_mgmt_line = "key_mgmt=WPA-PSK"
    pairwise_line = "pairwise=CCMP"
    auth_alg_line = "auth_alg=OPEN"
    hidden_line = ""

    # Falls Hidden-Netz, setze scan_ssid=1
    if hidden:
        hidden_line = "    scan_ssid=1\n"

    # Einfacher Beispiel-Umgang mit encryption:
    # - WPA oder WPA2 -> RSN, WPA-PSK
    # - WEP -> key_mgmt=NONE; (hier müsstest du eigentlich WEP-Parameter hinterlegen)
    # - nopass -> key_mgmt=NONE
    if encryption in ("WPA", "WPA2"):
        # Standard bleibt RSN / WPA-PSK
        pass
    elif encryption == "WEP":
        proto_line = ""
        key_mgmt_line = "key_mgmt=NONE"
        pairwise_line = ""
        auth_alg_line = "auth_alg=SHARED"  # z. B. WEP
        # -> Achtung: in wpa_supplicant ist WEP etwas tricky
    elif encryption == "NOPASS":
        proto_line = ""
        key_mgmt_line = "key_mgmt=NONE"
        pairwise_line = ""
        auth_alg_line = ""

    content = f"""\
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=DE

network={{
    ssid="{ssid}"
    psk="{password}"
    {proto_line}
    {key_mgmt_line}
    {pairwise_line}
    {auth_alg_line}
{hidden_line}}}
"""

    conf_path = "/etc/wpa_supplicant/wpa_supplicant.conf"
    try:
        with open(conf_path, "w") as f:
            f.write(content.strip() + "\n")
        print(f"[INFO] wpa_supplicant.conf für SSID='{ssid}' erstellt.")
        return conf_path
    except Exception as e:
        print(f"[ERROR] Konnte wpa_supplicant.conf nicht schreiben: {e}")
        return None

def apply_wpa_conf(conf_path):
    """
    Startet wpa_supplicant mit der gegebenen Konfig.
    Anschließend bekommt wlan0 eine neue DHCP-Lease.
    """
    if not os.path.isfile(conf_path):
        print(f"[ERROR] Datei {conf_path} existiert nicht oder ist nicht lesbar.")
        return

    # 1) Alte wpa_supplicant-Instanzen stoppen
    subprocess.call(["sudo", "killall", "wpa_supplicant"])
    time.sleep(1)
    # 2) DHCP-Client beenden
    subprocess.call(["sudo", "dhclient", "-r", "wlan0"])
    time.sleep(1)
    # 3) wlan0 hochfahren
    subprocess.call(["sudo", "ifconfig", "wlan0", "up"])
    time.sleep(1)
    # 4) wpa_supplicant starten
    subprocess.call(["sudo", "wpa_supplicant", "-B", "-i", "wlan0", "-c", conf_path])
    time.sleep(2)
    # 5) DHCP neu beziehen
    subprocess.call(["sudo", "dhclient", "-v", "wlan0"])
    time.sleep(5)
    print("[INFO] WLAN-Konfiguration angewendet.")


########################################
# Hauptprogramm
########################################

def main():
    """
    1) Prüft, ob WLAN bereits verbunden.
    2) Falls nicht, startet Kamera und sucht nach WLAN-QR-Codes.
    3) Sobald ein gültiger (WIFI:) Code gefunden, wpa_supplicant.conf erzeugen & aktivieren.
    4) Beenden, wenn erfolgreich verbunden.
    """

    print("[INFO] Starte find_wifi.py...")

    # Prüfen, ob bereits Internet/WLAN aktiv ist
    if is_connected():
        print("[INFO] WLAN bereits verbunden oder Internetzugang vorhanden. Breche ab.")
        return

    # Kamera initialisieren
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Kamera konnte nicht geöffnet werden!")
        return

    print("[INFO] Kamera geöffnet. Suche nach WLAN-QR-Codes... (Strg+C zum Abbrechen)")

    last_apply_time = 0
    try:
        while True:
            # Ist evtl. inzwischen WLAN da?
            if is_connected():
                print("[INFO] Erfolgreich verbunden! Beende find_wifi.py.")
                break

            ret, frame = cap.read()
            if not ret:
                time.sleep(0.5)
                continue

            # Optional: In Graustufen wandeln (manchmal bessere Erkennungsrate)
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # QR-Codes analysieren
            decoded_objs = decode(gray_frame)
            if decoded_objs:
                for obj in decoded_objs:
                    if obj.type == "QRCODE":
                        qr_data = obj.data.decode("utf-8")
                        wifi_info = parse_wifi_qr(qr_data)
                        if wifi_info:
                            now = time.time()
                            # Warte 10s, damit wir nicht in einer Schleife permanent neu schreiben
                            if now - last_apply_time > 10:
                                print(f"[INFO] WLAN-QR-Code gefunden!")
                                print(f"      SSID   = '{wifi_info['ssid']}'")
                                print(f"      PASS   = '{wifi_info['password']}'")
                                print(f"      ENC    = '{wifi_info['encryption']}'")
                                print(f"      HIDDEN = {wifi_info['hidden']}")

                                conf_path = write_wpa_supplicant_conf(wifi_info)
                                if conf_path:
                                    apply_wpa_conf(conf_path)
                                last_apply_time = now
                            else:
                                print("[INFO] WLAN-QR-Code erneut erkannt, warte kurz...")
                        else:
                            print("[INFO] QR-Code erkannt, aber kein gültiges WLAN-Format.")
                    else:
                        print(f"[INFO] Barcode gefunden (Typ={obj.type}), kein QR-CODE.")
            else:
                print("[INFO] Kein QR-Code im Bild...")

            # OPTIONAL: Live-Bild anzeigen:
            # cv2.imshow("WLAN QR Code Scanner", gray_frame)
            # if cv2.waitKey(1) & 0xFF == ord('q'):
            #     break

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[INFO] Manuell abgebrochen.")

    finally:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
