import os
import json
import time
import requests
from flask import Flask, jsonify, render_template, request
from threading import Thread

app = Flask(__name__)
RECIPE_FOLDER = "Rezepte"
CONFIG_FILE = "config.json"  # Konfigurationsdatei
ESP_IP = "192.168.2.236"  # IP-Adresse des ESP
ESP_PORT = 80

active_recipe = None  # Aktiver Rezeptname
is_running = False    # Status, ob ein Rezept läuft


def load_config():
    """Lädt die Konfiguration aus der JSON-Datei."""
    try:
        with open(CONFIG_FILE, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"Konfigurationsdatei '{CONFIG_FILE}' nicht gefunden! Erstelle eine neue.")
        return {}
    except json.JSONDecodeError as e:
        print(f"Fehler beim Lesen der Konfigurationsdatei: {e}")
        return {}


def save_config(config):
    """Speichert die Konfiguration in die JSON-Datei."""
    try:
        with open(CONFIG_FILE, "w") as file:
            json.dump(config, file, indent=4)
        print("Konfiguration erfolgreich gespeichert.")
    except Exception as e:
        print(f"Fehler beim Speichern der Konfigurationsdatei: {e}")


@app.route("/")
def index():
    """Startseite: Zeigt die Liste der Rezepte an."""
    recipes = []
    config = load_config()

    for filename in os.listdir(RECIPE_FOLDER):
        if filename.endswith(".txt"):
            recipe_path = os.path.join(RECIPE_FOLDER, filename)
            is_valid = True
            invalid_reasons = []
            with open(recipe_path, "r") as file:
                for line in file:
                    command = line.strip()
                    if command.startswith("move"):
                        args = command.split()
                        if len(args) != 2:
                            is_valid = False
                            invalid_reasons.append(f"Ungültiger move-Befehl: {command}")
                            continue
                        target = args[1]
                        if not target.isdigit() and target not in config:
                            is_valid = False
                            invalid_reasons.append(f"Kein Eintrag für '{target}' in der Konfiguration")
            recipes.append({"name": filename, "valid": is_valid, "reasons": invalid_reasons})

    return render_template("index.html", recipes=recipes, active_recipe=active_recipe, is_running=is_running)


@app.route("/config", methods=["GET", "POST"])
def manage_config():
    """Verwaltet die Konfiguration der Drinks."""
    if request.method == "GET":
        config = load_config()
        return render_template("config.html", config=config)

    elif request.method == "POST":
        # Aktualisiere die Konfiguration basierend auf den gesendeten Daten
        new_config = request.json.get("config")
        if not isinstance(new_config, dict):
            return jsonify({"status": "error", "message": "Ungültige Konfigurationsdaten"}), 400

        save_config(new_config)
        return jsonify({"status": "success", "message": "Konfiguration erfolgreich gespeichert"})


@app.route("/rezepte", methods=["GET", "POST", "DELETE"])
def manage_recipes():
    """Verwaltet die Rezepte (Erstellen, Bearbeiten, Löschen)."""
    if request.method == "GET":
        # Alle Rezepte aus dem Ordner anzeigen
        recipes = {}
        for filename in os.listdir(RECIPE_FOLDER):
            if filename.endswith(".txt"):
                with open(os.path.join(RECIPE_FOLDER, filename), "r") as file:
                    recipes[filename] = file.read()
        return render_template("rezepte.html", recipes=recipes)

    elif request.method == "POST":
        # Neues Rezept erstellen oder bestehendes Rezept bearbeiten
        data = request.json
        name = data.get("name")
        content = data.get("content")
        if not name or not content:
            return jsonify({"status": "error", "message": "Name oder Inhalt fehlt"}), 400

        if not name.endswith(".txt"):
            name += ".txt"

        with open(os.path.join(RECIPE_FOLDER, name), "w") as file:
            file.write(content)

        return jsonify({"status": "success", "message": f"Rezept '{name}' gespeichert."})

    elif request.method == "DELETE":
        # Rezept löschen
        data = request.json
        name = data.get("name")
        if not name or not name.endswith(".txt"):
            return jsonify({"status": "error", "message": "Ungültiger Rezeptname"}), 400

        filepath = os.path.join(RECIPE_FOLDER, name)
        if os.path.exists(filepath):
            os.remove(filepath)
            return jsonify({"status": "success", "message": f"Rezept '{name}' gelöscht."})
        else:
            return jsonify({"status": "error", "message": f"Rezept '{name}' nicht gefunden."}), 404


@app.route("/run_recipe", methods=["POST"])
def run_recipe():
    """Startet die Ausführung eines Rezepts."""
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
    """Manuelle Befehle mit Millimeterangaben oder Servo-Verzögerungen."""
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


def execute_recipe(recipe_file):
    """Führt ein Rezept aus der angegebenen Datei aus."""
    global active_recipe, is_running
    active_recipe = recipe_file
    is_running = True

    # Lade die Konfigurationsdaten
    config = load_config()

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
                    args = command.split()
                    target = args[1]
                    if target.isdigit():
                        position = int(target)
                    elif target in config:
                        position = config[target]
                    else:
                        print(f"Fehler: '{target}' ist kein gültiger Wert.")
                        break

                    response = requests.post(f"http://{ESP_IP}:{ESP_PORT}/move", json={"position": position})
                    if response.status_code != 200:
                        print("Fehler beim Bewegen der Plattform.")
                        break

                elif command.startswith("servo"):
                    delay = int(command.split()[1])
                    response = requests.post(f"http://{ESP_IP}:{ESP_PORT}/servo", json={"delay": delay})
                    if response.status_code != 200:
                        print("Fehler bei der Servo-Bewegung.")
                        break

                elif command.startswith("wait"):
                    duration = int(command.split()[1])
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
