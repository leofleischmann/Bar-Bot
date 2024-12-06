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
current_progress = 0  # Globaler Fortschritt


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


def check_esp_connection():
    """Prüft, ob der ESP erreichbar ist."""
    try:
        response = requests.get(f"http://{ESP_IP}:{ESP_PORT}/status", timeout=2)
        if response.status_code == 200:
            data = response.json()
            return data.get("status") == "online"
        else:
            print(f"ESP antwortet mit Statuscode: {response.status_code}")
            return False
    except requests.exceptions.ConnectTimeout:
        print("Fehler: Verbindung zum ESP abgelaufen.")
        return False
    except requests.exceptions.ConnectionError:
        print("Fehler: Keine Verbindung zum ESP möglich.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"Allgemeiner Fehler beim Prüfen des ESP-Status: {e}")
        return False


@app.route("/")
def index():
    """Startseite: Zeigt die Liste der Rezepte und den ESP-Status an."""
    recipes = []
    config = load_config()

    # Getränke aus Pumpen hinzufügen, mit deren spezifischen Positionen
    for i in range(1, 5):  # pump1 bis pump4
        pump_drink = config.get(f"pump{i}")
        if pump_drink:
            pump_pos = config.get(f"pump{i}_position", 250)
            config[pump_drink] = pump_pos

    for filename in os.listdir(RECIPE_FOLDER):
        if filename.endswith(".txt"):
            recipe_path = os.path.join(RECIPE_FOLDER, filename)
            is_valid = True
            invalid_reasons = []
            with open(recipe_path, "r") as file:
                for line in file:
                    command = line.strip()
                    if not command:
                        continue
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
                    elif command.startswith("servo"):
                        args = command.split()
                        if len(args) >= 3:
                            mode = args[1]
                            value = args[2]
                            if mode == "ms":
                                if not value.isdigit():
                                    is_valid = False
                                    invalid_reasons.append(f"Ungültiger servo ms-Wert: {command}")
                            elif mode == "cl":
                                try:
                                    float(value)
                                    if "pour_time" not in config:
                                        is_valid = False
                                        invalid_reasons.append("Kein 'pour_time' in der Konfiguration für 'servo cl'")
                                except ValueError:
                                    is_valid = False
                                    invalid_reasons.append(f"Ungültiger servo cl-Wert: {command}")
                            else:
                                is_valid = False
                                invalid_reasons.append(f"Unbekannter servo Modus: {mode}")
                        else:
                            is_valid = False
                            invalid_reasons.append(f"Ungültiger servo-Befehl: {command}")
            recipes.append({
                "name": filename,
                "valid": is_valid,
                "reasons": invalid_reasons
            })

    esp_connected = check_esp_connection()
    return render_template("index.html", recipes=recipes, esp_connected=esp_connected, active_recipe=active_recipe, is_running=is_running)


@app.route("/esp_status")
def esp_status():
    """Prüft, ob der ESP erreichbar ist."""
    esp_connected = check_esp_connection()
    return jsonify({"connected": esp_connected})


@app.route("/config", methods=["GET", "POST"])
def manage_config():
    """Verwaltet die Konfiguration der Drinks und Pumpen."""
    if request.method == "GET":
        config = load_config()
        return render_template("config.html", config=config)
    elif request.method == "POST":
        new_config = request.json.get("config")
        if not isinstance(new_config, dict):
            return jsonify({"status": "error", "message": "Ungültige Konfigurationsdaten"}), 400
        save_config(new_config)
        return jsonify({"status": "success", "message": "Konfiguration erfolgreich gespeichert"})


@app.route("/rezepte", methods=["GET", "POST", "DELETE"])
def manage_recipes():
    if request.method == "GET":
        recipes = {}
        for filename in os.listdir(RECIPE_FOLDER):
            if filename.endswith(".txt"):
                with open(os.path.join(RECIPE_FOLDER, filename), "r") as file:
                    recipes[filename] = file.read()

        config = load_config()
        drinks = [
            key for key in config.keys()
            if not key.startswith("pump") and key not in ["pour_time"]
        ]

        # Getränke aus Pumpen hinzufügen
        for i in range(1, 5):
            pump_drink = config.get(f"pump{i}")
            if pump_drink and pump_drink not in drinks:
                drinks.append(pump_drink)

        return render_template("rezepte.html", recipes=recipes, configured_alcohols=drinks)

    elif request.method == "POST":
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
    global is_running
    if is_running:
        return jsonify({"status": "error", "message": "Ein Rezept wird bereits ausgeführt."}), 400

    if not check_esp_connection():
        return jsonify({"status": "error", "message": "ESP ist nicht verbunden."}), 400

    recipe_file = request.json.get("recipe")
    if not recipe_file or not os.path.exists(os.path.join(RECIPE_FOLDER, recipe_file)):
        return jsonify({"status": "error", "message": "Ungültiges Rezept."}), 400

    thread = Thread(target=execute_recipe, args=(recipe_file,))
    thread.start()
    return jsonify({"status": "success", "message": f"Rezept '{recipe_file}' gestartet."})


def activate_pump_thread(pump_number, duration):
    try:
        print(f"Aktiviere Pumpe {pump_number} für {duration} ms...")
        response = requests.post(f"http://{ESP_IP}:{ESP_PORT}/pump", json={"pump": pump_number, "duration": duration})
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                print(f"Pumpe {pump_number} erfolgreich aktiviert.")
            else:
                print(f"Fehler beim Aktivieren der Pumpe {pump_number}: {result.get('message', 'Unbekannter Fehler')}")
        else:
            print(f"Fehler: ESP-Server antwortet mit {response.status_code}")
    except requests.ConnectionError:
        print(f"Fehler: Keine Verbindung zum ESP für Pumpe {pump_number}.")
    except requests.Timeout:
        print(f"Fehler: Zeitüberschreitung bei der Verbindung zur Pumpe {pump_number}.")
    except requests.RequestException as e:
        print(f"Fehler bei der Pumpenkommunikation für Pumpe {pump_number}: {e}")


def activate_pump(pump_number, duration):
    thread = Thread(target=activate_pump_thread, args=(pump_number, duration))
    thread.start()


def calculate_pump_duration(cl, pump_time):
    return int(cl * pump_time)


@app.route("/get_recipe_content", methods=["GET"])
def get_recipe_content():
    recipe_name = request.args.get("name")
    if not recipe_name:
        return "Rezeptname fehlt.", 400

    recipe_path = os.path.join(RECIPE_FOLDER, recipe_name)
    if not os.path.exists(recipe_path):
        return "Rezeptdatei nicht gefunden.", 404

    try:
        with open(recipe_path, "r") as file:
            content = file.read()
        if not content.strip():
            return "Rezeptdatei ist leer.", 400
        return content
    except Exception as e:
        return f"Fehler beim Lesen der Datei: {str(e)}", 500


@app.route("/send_command", methods=["POST"])
def send_command():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "Keine Daten gesendet."}), 400

        command_type = data.get("type")
        value = data.get("value")
        pump = data.get("pump")

        if not command_type or not isinstance(value, int):
            return jsonify({"status": "error", "message": "Ungültiger Befehlstyp oder Wert."}), 400

        if command_type == "move":
            # Move command
            print(f"Sending 'move' command to ESP with position {value} mm.")
            response = requests.post(f"http://{ESP_IP}:{ESP_PORT}/move", json={"position": value})
            if response.status_code == 200:
                return jsonify({"status": "success", "message": f"Plattform zu {value} mm bewegt."})
            else:
                return jsonify({"status": "error", "message": "ESP hat nicht auf 'move' reagiert."}), 500

        elif command_type == "servo":
            # Servo command
            print(f"Sending 'servo' command to ESP with delay {value} ms.")
            response = requests.post(f"http://{ESP_IP}:{ESP_PORT}/servo", json={"delay": value})
            if response.status_code == 200:
                return jsonify({"status": "success", "message": f"Servo mit {value} ms Verzögerung bewegt."})
            else:
                return jsonify({"status": "error", "message": "ESP hat nicht auf 'servo' reagiert."}), 500

        elif command_type == "pump":
            if not pump or not isinstance(pump, int):
                return jsonify({"status": "error", "message": "Pumpennummer fehlt oder ist ungültig."}), 400

            print(f"Sending 'pump' command to ESP: Pump {pump}, Duration {value} ms.")
            response = requests.post(f"http://{ESP_IP}:{ESP_PORT}/pump", json={"pump": pump, "duration": value})
            if response.status_code == 200:
                return jsonify({"status": "success", "message": f"Pumpe {pump} für {value} ms aktiviert."})
            else:
                return jsonify({"status": "error", "message": "ESP hat nicht auf 'pump' reagiert."}), 500

        else:
            return jsonify({"status": "error", "message": f"Unbekannter Befehlstyp: {command_type}."}), 400

    except Exception as e:
        print(f"Error in send_command: {e}")
        return jsonify({"status": "error", "message": "Serverfehler beim Verarbeiten des Befehls."}), 500


@app.route("/generate_recipe", methods=["POST"])
def generate_recipe():
    try:
        data = request.json
        recipe_name = data.get("name", "").strip()
        alcohol_data = data.get("alcoholData", [])

        if not recipe_name:
            return jsonify({"status": "error", "message": "Rezeptname fehlt."}), 400
        if not alcohol_data or not isinstance(alcohol_data, list):
            return jsonify({"status": "error", "message": "Ungültige Zutatenliste."}), 400

        if not recipe_name.endswith(".txt"):
            recipe_name += ".txt"
        recipe_path = os.path.join(RECIPE_FOLDER, recipe_name)

        config = load_config()
        pour_time = config.get("pour_time", 2000)

        commands = ["start"]
        for item in alcohol_data:
            alcohol = item.get("alcohol")
            amount_cl = float(item.get("amount", 0))
            if not alcohol:
                return jsonify({"status": "error", "message": "Getränkename fehlt."}), 400
            if amount_cl <= 0:
                return jsonify({"status": "error", "message": "Menge muss größer als 0 sein."}), 400

            move_command = f"move {alcohol}"
            is_valid, error = validate_recipe_command(move_command, config)
            if not is_valid:
                return jsonify({"status": "error", "message": error}), 400
            commands.append(move_command)
            commands.append("wait 500")

            remaining_cl = amount_cl
            while remaining_cl > 2:
                servo_command = "servo cl 2"
                is_valid, error = validate_recipe_command(servo_command, config)
                if not is_valid:
                    return jsonify({"status": "error", "message": error}), 400
                commands.append(servo_command)
                commands.append("wait 5000")
                remaining_cl -= 2

            if remaining_cl > 0:
                servo_command = f"servo cl {remaining_cl}"
                is_valid, error = validate_recipe_command(servo_command, config)
                if not is_valid:
                    return jsonify({"status": "error", "message": error}), 400
                commands.append(servo_command)
                commands.append("wait 1000")

        commands.append("move 10")
        commands.append("done")

        with open(recipe_path, "w") as file:
            file.write("\n".join(commands))

        return jsonify({"status": "success", "message": f"Rezept '{recipe_name}' wurde erfolgreich generiert."})
    except Exception as e:
        print(f"Fehler beim Generieren des Rezepts: {e}")
        return jsonify({"status": "error", "message": "Fehler beim Generieren des Rezepts."}), 500


@app.route("/recipe_progress", methods=["GET"])
def recipe_progress():
    global current_progress
    return jsonify({"progress": current_progress})


def validate_recipe_command(command, config):
    command = command.strip()
    if not command:
        return False, "Leerer Befehl."

    parts = command.split()
    if parts[0] == "move":
        if len(parts) != 2:
            return False, f"Ungültiger move-Befehl: {command}"
        target = parts[1]
        if not target.isdigit() and target not in config:
            is_pump = any(config.get(f"pump{i}") == target for i in range(1,5))
            if not is_pump:
                return False, f"'{target}' ist nicht in der Konfiguration vorhanden."
    elif parts[0] == "servo":
        if len(parts) < 3:
            return False, f"Ungültiger servo-Befehl: {command}"
        mode, value = parts[1], parts[2]
        if mode == "ms" and not value.isdigit():
            return False, f"Ungültiger servo ms-Wert: {command}"
        elif mode == "cl":
            try:
                float(value)
                if "pour_time" not in config:
                    return False, "Kein 'pour_time' in der Konfiguration für 'servo cl'."
            except ValueError:
                return False, f"Ungültiger servo cl-Wert: {command}"
        else:
            if mode not in ["ms", "cl"]:
                return False, f"Unbekannter servo Modus: {mode}"
    elif parts[0] == "wait":
        if len(parts) != 2 or not parts[1].isdigit():
            return False, f"Ungültiger wait-Befehl: {command}"
    elif parts[0] == "done":
        if len(parts) != 1:
            return False, f"Ungültiger done-Befehl: {command}"
    elif parts[0] == "start":
        if len(parts) != 1:
            return False, f"Ungültiger start-Befehl: {command}"
    else:
        return False, f"Unbekannter Befehl: {command}"

    return True, None


def execute_recipe(recipe_file):
    global active_recipe, is_running, current_progress
    active_recipe = recipe_file
    is_running = True
    current_progress = 0

    config = load_config()
    pour_time = config.get("pour_time", 2000)

    current_target = None
    aggregated_pump_duration = 0
    pump_in_progress = False
    abtropfzeit = 0

    try:
        with open(os.path.join(RECIPE_FOLDER, recipe_file), "r") as file:
            commands = file.readlines()
            total_commands = len(commands)

            for idx, command in enumerate(commands):
                command = command.strip()
                if not command:
                    continue

                current_progress = int((idx + 1) / total_commands * 100)

                if command.startswith("start"):
                    print(f"Rezept '{recipe_file}' gestartet.")
                    continue

                elif command.startswith("move"):
                    target = command.split()[1]

                    if pump_in_progress:
                        pump_number = next((i for i in range(1, 5) if config.get(f"pump{i}") == current_target), None)
                        if pump_number:
                            print(f"Aktiviere Pumpe {pump_number} für {aggregated_pump_duration} ms.")
                            requests.post(f"http://{ESP_IP}:{ESP_PORT}/pump", json={"pump": pump_number, "duration": aggregated_pump_duration})
                        print(f"Pumpenlauf abgeschlossen, warte Abtropfzeit: {abtropfzeit} ms.")
                        time.sleep(abtropfzeit / 1000.0)
                        abtropfzeit = 0
                        aggregated_pump_duration = 0
                        pump_in_progress = False

                    if target.isdigit():
                        position = int(target)
                        current_target = None
                    elif target in config:
                        position = config[target]
                        current_target = target
                    elif any(config.get(f"pump{i}") == target for i in range(1, 5)):
                        pump_number = next(i for i in range(1, 5) if config.get(f"pump{i}") == target)
                        position = config.get(f"pump{pump_number}_position", 250)
                        current_target = target
                    else:
                        print(f"Fehler: Ziel '{target}' ist nicht in der Konfiguration vorhanden.")
                        continue

                    print(f"Bewege Plattform zu {position} mm für '{target}'...")
                    requests.post(f"http://{ESP_IP}:{ESP_PORT}/move", json={"position": position})

                elif command.startswith("servo"):
                    if not current_target:
                        print("Fehler: Kein gültiges Ziel für 'servo' vorhanden.")
                        continue

                    mode, value = command.split()[1], command.split()[2]
                    if mode == "cl":
                        cl = float(value)
                        pump_number = next((i for i in range(1, 5) if config.get(f"pump{i}") == current_target), None)
                        if pump_number:
                            pump_time_for_current = config.get(f"pump{pump_number}_time", 1000)
                            aggregated_pump_duration += calculate_pump_duration(cl, pump_time_for_current)
                            pump_in_progress = True
                        else:
                            delay = int((cl / 2) * pour_time)
                            print(f"Bewege Servo für {cl} cl mit Verzögerung {delay} ms...")
                            requests.post(f"http://{ESP_IP}:{ESP_PORT}/servo", json={"delay": delay})
                    elif mode == "ms":
                        delay = int(value)
                        print(f"Bewege Servo mit {delay} ms Verzögerung...")
                        requests.post(f"http://{ESP_IP}:{ESP_PORT}/servo", json={"delay": delay})

                elif command.startswith("wait"):
                    duration = int(command.split()[1])
                    if pump_in_progress:
                        abtropfzeit = duration
                        print(f"Setze Abtropfzeit auf {abtropfzeit} ms.")
                    else:
                        print(f"Warte {duration} ms...")
                        time.sleep(duration / 1000.0)

                elif command.startswith("done"):
                    if pump_in_progress:
                        pump_number = next((i for i in range(1, 5) if config.get(f"pump{i}") == current_target), None)
                        if pump_number:
                            print(f"Aktiviere Pumpe {pump_number} für {aggregated_pump_duration} ms.")
                            requests.post(f"http://{ESP_IP}:{ESP_PORT}/pump", json={"pump": pump_number, "duration": aggregated_pump_duration})
                        print(f"Pumpenlauf abgeschlossen, warte Abtropfzeit: {abtropfzeit} ms.")
                        time.sleep(abtropfzeit / 1000.0)
                        abtropfzeit = 0
                        aggregated_pump_duration = 0
                        pump_in_progress = False

                    print(f"Rezept '{recipe_file}' abgeschlossen.")
                    break

        current_progress = 100

    except Exception as e:
        print(f"Fehler beim Ausführen des Rezepts: {e}")

    is_running = False
    active_recipe = None


@app.route("/calibrate", methods=["GET", "POST"])
def calibrate():
    """
    Seite zum Kalibrieren einzelner Getränke oder Pumpen.
    GET: Zeigt die Kalibrierungsoberfläche
    POST: Speichert geänderte Konfiguration
    """
    config = load_config()
    if request.method == "GET":
        item = request.args.get("item", "")
        if not item:
            return "Kein Item angegeben.", 400

        # Prüfen, ob es eine Pumpe oder ein Getränk ist
        is_pump = False
        pump_number = None
        if item.startswith("pump") and item[-1].isdigit():
            # z.B. pump1
            is_pump = True
            pump_number = int(item[-1])
        # Falls kein Pumpeneintrag, dann ist es ein Getränk oder pour_time Parameter
        # Wenn es ein normaler Drink ist, erwarten wir einen position-Wert
        # Prüfen ob Item in config ist (außer pump Keys)
        drink_position = config.get(item) if (item in config and not item.startswith("pump")) else None
        pour_time = config.get("pour_time", 2000)

        # Falls es eine Pumpe ist: wir holen pump{i}, pump{i}_time, pump{i}_position
        pump_drink = None
        pump_time_val = None
        pump_pos_val = None
        if is_pump and pump_number:
            pump_drink = config.get(f"pump{pump_number}", "")
            pump_time_val = config.get(f"pump{pump_number}_time", 1000)
            pump_pos_val = config.get(f"pump{pump_number}_position", 250)

        return render_template("calibrate.html",
                               item=item,
                               is_pump=is_pump,
                               pump_number=pump_number,
                               pump_drink=pump_drink,
                               pump_time_val=pump_time_val,
                               pump_pos_val=pump_pos_val,
                               drink_position=drink_position,
                               pour_time=pour_time)

    elif request.method == "POST":
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "Keine Daten gesendet."}), 400

        item = data.get("item")
        if not item:
            return jsonify({"status": "error", "message": "Kein Item angegeben"}), 400

        config = load_config()

        # Aktualisiere die Konfiguration mit den gesendeten Werten
        if item.startswith("pump") and item[-1].isdigit():
            # Pumpenwerte aktualisieren
            pump_number = int(item[-1])
            pump_drink_new = data.get("pump_drink", "").strip()
            pump_time_new = int(data.get("pump_time", 1000))
            pump_pos_new = int(data.get("pump_position", 250))

            if pump_drink_new:
                config[f"pump{pump_number}"] = pump_drink_new
            config[f"pump{pump_number}_time"] = pump_time_new
            config[f"pump{pump_number}_position"] = pump_pos_new

        else:
            # Getränk oder pour_time
            if "pour_time" in data:
                config["pour_time"] = int(data["pour_time"])
            if "drink_position" in data and item in config:
                config[item] = int(data["drink_position"])

        save_config(config)
        return jsonify({"status": "success", "message": "Kalibrierte Werte erfolgreich gespeichert."})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
