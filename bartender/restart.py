import os
import subprocess

# Service-Name
SERVICE_NAME = "server.service"

def run_command(command):
    """Führt einen Shell-Befehl aus und gibt die Ausgabe zurück."""
    try:
        subprocess.run(command, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[OK] {command}")
    except subprocess.CalledProcessError:
        print(f"[ERROR] {command}")

def get_service_status():
    """Prüft den Status des Services und gibt 'Running' oder 'Failed' aus."""
    try:
        result = subprocess.check_output(f"sudo systemctl is-active {SERVICE_NAME}", shell=True, text=True).strip()
        if result == "active":
            print(f"Status: Running")
        else:
            print(f"Status: Failed")
    except subprocess.CalledProcessError:
        print(f"Status: Failed")

def reload_and_restart_service():
    """Lädt systemd neu und startet den Service."""
    print("Lade systemd-Daemon neu...")
    run_command("sudo systemctl daemon-reload")
    
    print(f"Starte den Service '{SERVICE_NAME}' neu...")
    run_command(f"sudo systemctl restart {SERVICE_NAME}")
    
    print(f"Prüfe den Status des Services '{SERVICE_NAME}'...")
    get_service_status()

if __name__ == "__main__":
    print("Starte die Schritte nach Änderung von server.py...")
    reload_and_restart_service()
    print("Fertig!")
