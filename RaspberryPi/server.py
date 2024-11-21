from flask import Flask, jsonify, render_template, request
import os
import time
import requests
from threading import Thread

app = Flask(__name__)
RECIPE_FOLDER = "Rezepte"
ESP_IP = "192.168.2.236"  # IP-Adresse des ESP
ESP_PORT = 80

active_recipe = None  # Aktiver Rezeptname
is_running = False    # Status, ob ein Rezept läuft


def execute_recipe(recipe_file):
    """Führt ein Rezept aus der angegebenen Datei aus."""
    global active_recipe, is_running
    active_recipe = recipe_file
    is_running = True
    try:
        with open(os.path.join(RECIPE_FOLDER, recipe_file), "r") as file:
            for line in file:
                command = line.strip()
                if not command:
                    continue
                
                if command.startswith("start"):
                    print(f"Rezept '{recipe_file}' gestartet.")
                    continue

                elif command.startswith("move"):
                    position = int(command.split()[1])
                    print(f"Bewege Plattform zu {position} mm...")
                    response = requests.post(f"http://{ESP_IP}:{ESP_PORT}/move", json={"position": position})
                    if response.status_code == 200:
                        print(f"Plattform hat {position} mm erreicht.")
                    else:
                        print(f"Fehler beim Bewegen der Plattform: {response.text}")

                elif command.startswith("servo"):
                    delay = int(command.split()[1])
                    print(f"Bewege Servo mit Verzögerung von {delay} ms...")
                    response = requests.post(f"http://{ESP_IP}:{ESP_PORT}/servo", json={"delay": delay})
                    if response.status_code == 200:
                        print("Servo-Bewegung abgeschlossen.")
                    else:
                        print(f"Fehler bei der Servo-Bewegung: {response.text}")

                elif command.startswith("wait"):
                    duration = int(command.split()[1])
                    print(f"Warte {duration} ms...")
                    time.sleep(duration / 1000.0)

                elif command.startswith("done"):
                    print(f"Rezept '{recipe_file}' abgeschlossen.")
                    break

                else:
                    print(f"Unbekannter Befehl: {command}")

    except Exception as e:
        print(f"Fehler beim Ausführen des Rezepts: {e}")

    is_running = False
    active_recipe = None


@app.route("/")
def index():
    # Liste aller Rezepte anzeigen
    recipes = [f for f in os.listdir(RECIPE_FOLDER) if f.endswith(".txt")]
    return render_template("index.html", recipes=recipes, active_recipe=active_recipe, is_running=is_running)


@app.route("/run_recipe", methods=["POST"])
def run_recipe():
    # Rezept ausführen
    global is_running
    if is_running:
        return jsonify({"status": "error", "message": "Ein Rezept wird bereits ausgeführt."}), 400

    recipe_file = request.json.get("recipe")
    if not recipe_file or not os.path.exists(os.path.join(RECIPE_FOLDER, recipe_file)):
        return jsonify({"status": "error", "message": "Ungültiges Rezept."}), 400

    thread = Thread(target=execute_recipe, args=(recipe_file,))
    thread.start()
    return jsonify({"status": "success", "message": f"Rezept '{recipe_file}' gestartet."})


@app.route("/send_command", methods=["POST"])
def send_command():
    # Manuelle Befehle senden
    command_type = request.json.get("type")
    value = request.json.get("value")

    if not command_type or not isinstance(value, int):
        return jsonify({"status": "error", "message": "Ungültiger Befehl."}), 400

    try:
        if command_type == "move":
            print(f"Sende 'move' Befehl mit Ziel {value} mm...")
            response = requests.post(f"http://{ESP_IP}:{ESP_PORT}/move", json={"position": value})
        elif command_type == "servo":
            print(f"Sende 'servo' Befehl mit Verzögerung {value} ms...")
            response = requests.post(f"http://{ESP_IP}:{ESP_PORT}/servo", json={"delay": value})
        else:
            return jsonify({"status": "error", "message": "Unbekannter Befehlstyp."}), 400

        if response.status_code == 200:
            return jsonify({"status": "success", "message": f"Befehl '{command_type}' erfolgreich ausgeführt."})
        else:
            return jsonify({"status": "error", "message": "ESP antwortet nicht."}), 500

    except requests.exceptions.RequestException as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
