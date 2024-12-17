import subprocess

SERVICE_NAME = "server.service"

def show_logs_in_real_time():
    """Zeigt die Logs des Services in Echtzeit an."""
    print(f"Zeige Logs für '{SERVICE_NAME}' in Echtzeit (Drücke STRG+C zum Beenden)...\n")
    try:
        # Startet journalctl mit Echtzeit-Logs
        subprocess.run(f"sudo journalctl -u {SERVICE_NAME} -f", shell=True)
    except KeyboardInterrupt:
        print("\nLog-Anzeige beendet.")

if __name__ == "__main__":
    show_logs_in_real_time()
