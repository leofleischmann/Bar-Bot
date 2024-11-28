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
    """Prüft, ob der ESP erreichbar ist und gibt eine detaillierte Fehlerdiagnose."""
    try:
        response = requests.get(f"http://{ESP_IP}:{ESP_PORT}/status", timeout=2)
        if response.status_code == 200:
            data = response.json()
            return data.get("status") == "online"
        else:
            print(f"ESP antwortet, aber mit unerwartetem Statuscode: {response.status_code}")
            return False
    except requests.exceptions.ConnectTimeout:
        print("Fehler: Verbindung zum ESP abgelaufen. Möglicherweise ist der ESP offline oder die IP falsch.")
        return False
    except requests.exceptions.ConnectionError:
        print("Fehler: Keine Verbindung zum ESP möglich. Prüfe die Netzwerkverbindung.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"Allgemeiner Fehler beim Prüfen des ESP-Status: {e}")
        return False



@app.route("/")
def index():
    """Startseite: Zeigt die Liste der Rezepte und den ESP-Status an."""
    recipes = []
    config = load_config()

    # Getränke aus Pumpen hinzufügen
    for i in range(1, 5):  # pump1 bis pump4
        pump_drink = config.get(f"pump{i}")
        if pump_drink:
            config[pump_drink] = config.get("pumpen", 250)

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

    esp_connected = check_esp_connection()  # Prüfen, ob der ESP verbunden ist
    return render_template("index.html", recipes=recipes, esp_connected=esp_connected, active_recipe=active_recipe, is_running=is_running)

@app.route("/esp_status")
def esp_status():
    """Prüft, ob der ESP erreichbar ist und gibt den Status zurück."""
    esp_connected = check_esp_connection()
    return jsonify({"connected": esp_connected})


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

        # Lade die Konfigurationsdaten
        config = load_config()

        # Extrahiere Getränke aus der Konfiguration
        drinks = [
            key for key in config.keys()
            if not key.startswith("pump") and key not in ["pour_time", "pump_time", "pumpen"]
        ]

        # Füge die Getränke aus den Pumpenparametern hinzu
        for i in range(1, 5):  # pump1 bis pump4
            pump_drink = config.get(f"pump{i}")
            if pump_drink and pump_drink not in drinks:
                drinks.append(pump_drink)

        # Übergabe der Rezepte und Getränke an das Frontend
        return render_template("rezepte.html", recipes=recipes, configured_alcohols=drinks)

    elif request.method == "POST":
        # Rezept hinzufügen oder bearbeiten
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
    global is_running
    if is_running:
        return jsonify({"status": "error", "message": "Ein Rezept wird bereits ausgeführt."}), 400

    if not check_esp_connection():  # ESP-Status prüfen
        return jsonify({"status": "error", "message": "ESP ist nicht verbunden."}), 400

    recipe_file = request.json.get("recipe")
    if not recipe_file or not os.path.exists(os.path.join(RECIPE_FOLDER, recipe_file)):
        return jsonify({"status": "error", "message": "Ungültiges Rezept."}), 400

    thread = Thread(target=execute_recipe, args=(recipe_file,))
    thread.start()
    return jsonify({"status": "success", "message": f"Rezept '{recipe_file}' gestartet."})

def activate_pump_thread(pump_number, duration):
    """Führt die Pumpenaktivierung in einem separaten Thread aus."""
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
        
def handle_pump_activation(target, cl, config, pump_flow_rate):
    """Aktiviert relevante Pumpen für ein Ziel und eine Menge."""
    active_pumps = []
    for i in range(1, 5):  # pump1 bis pump4
        if config.get(f"pump{i}") == target:
            duration = calculate_pump_duration(cl, pump_flow_rate)
            active_pumps.append((i, duration))

    if active_pumps:
        for pump_number, duration in active_pumps:
            activate_pump(pump_number, duration)
        return True  # Indikator, dass Pumpen genutzt wurden
    return False



def activate_pump(pump_number, duration):
    """Startet die Pumpenaktivierung in einem neuen Thread."""
    thread = Thread(target=activate_pump_thread, args=(pump_number, duration))
    thread.start()
    
def calculate_pump_duration(cl, pump_flow_rate):
    """
    Berechnet die Dauer, die eine Pumpe für eine bestimmte Menge benötigt.
    :param cl: Menge in cl.
    :param pump_flow_rate: Flussrate der Pumpe in cl/ms.
    :return: Dauer in ms.
    """
    return int(cl / pump_flow_rate)

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

@app.route("/generate_recipe", methods=["POST"])
def generate_recipe():
    """Generiert ein neues Rezept basierend auf den angegebenen Zutaten und Mengen."""
    try:
        # Lade die Anfragedaten
        data = request.json
        recipe_name = data.get("name", "").strip()
        alcohol_data = data.get("alcoholData", [])

        # Validierung der Eingabedaten
        if not recipe_name:
            return jsonify({"status": "error", "message": "Rezeptname fehlt."}), 400
        if not alcohol_data or not isinstance(alcohol_data, list):
            return jsonify({"status": "error", "message": "Ungültige Zutatenliste."}), 400

        # Pfad des neuen Rezepts
        if not recipe_name.endswith(".txt"):
            recipe_name += ".txt"
        recipe_path = os.path.join(RECIPE_FOLDER, recipe_name)

        # Lade die Konfigurationsdaten
        config = load_config()
        pour_time = config.get("pour_time", 2000)  # Standard-Pour-Time in ms für 2 cl

        # Rezept generieren
        commands = ["start"]
        for item in alcohol_data:
            alcohol = item.get("alcohol")
            amount_cl = float(item.get("amount", 0))
            if not alcohol:
                return jsonify({"status": "error", "message": "Getränkename fehlt."}), 400
            if amount_cl <= 0:
                return jsonify({"status": "error", "message": "Menge muss größer als 0 sein."}), 400

            # Validierung des move-Befehls
            move_command = f"move {alcohol}"
            is_valid, error = validate_recipe_command(move_command, config)
            if not is_valid:
                return jsonify({"status": "error", "message": error}), 400
            commands.append(move_command)
            commands.append("wait 500")  # Wartezeit, um sicherzustellen, dass die Plattform still steht

            # Servo-Befehle hinzufügen
            remaining_cl = amount_cl
            while remaining_cl > 2:
                servo_command = "servo cl 2"
                is_valid, error = validate_recipe_command(servo_command, config)
                if not is_valid:
                    return jsonify({"status": "error", "message": error}), 400
                commands.append(servo_command)
                commands.append("wait 5000")  # Wartezeit, um die Plattform aufzufüllen
                remaining_cl -= 2

            # Letzter Servo-Befehl für Restmenge
            if remaining_cl > 0:
                servo_command = f"servo cl {remaining_cl}"
                is_valid, error = validate_recipe_command(servo_command, config)
                if not is_valid:
                    return jsonify({"status": "error", "message": error}), 400
                commands.append(servo_command)
                commands.append("wait 1000")  # Wartezeit zum Abtropfen

        # Abschluss des Rezepts
        commands.append("move 10")  # Bewegt die Plattform zur Entnahme des Glases
        commands.append("done")

        # Rezept speichern
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

def get_position(drink, config):
    """Ermittelt die Position eines Getränks oder Pumpengetränks."""
    # Prüfen, ob das Getränk ein normales Getränk ist
    if drink in config and not drink.startswith("pump"):
        return config[drink]

    # Prüfen, ob das Getränk in einer Pumpe konfiguriert ist
    for i in range(1, 5):  # pump1 bis pump4
        pump_key = f"pump{i}"
        if config.get(pump_key) == drink:
            return config.get("pumpen", None)  # Rückgabe der Pumpenposition

    # Wenn das Getränk nicht gefunden wurde
    print(f"Fehler: '{drink}' ist nicht in der Konfiguration vorhanden.")
    return None

def validate_recipe_command(command, config):
    """
    Validiert einen einzelnen Rezeptbefehl.
    :param command: Der Rezeptbefehl als String.
    :param config: Die aktuelle Konfiguration als Dictionary.
    :return: Tuple (is_valid, error_message)
    """
    command = command.strip()
    if not command:
        return False, "Leerer Befehl."

    parts = command.split()
    if parts[0] == "move":
        if len(parts) != 2:
            return False, f"Ungültiger move-Befehl: {command}"
        target = parts[1]
        if not target.isdigit() and target not in config:
            # Überprüfen, ob das Ziel ein Pumpenzuordnung ist
            is_pump = any(config.get(f"pump{i}") == target for i in range(1, 5))
            if not is_pump:
                return False, f"'{target}' ist nicht in der Konfiguration oder Pumpenzuordnung vorhanden."
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
    """Führt ein Rezept aus, einschließlich optimierter Bewegungs- und Pumpenlogik."""
    global active_recipe, is_running, current_progress
    active_recipe = recipe_file
    is_running = True
    current_progress = 0

    config = load_config()
    pump_time = config.get("pump_time", 1000)  # Zeit pro cl in ms für Pumpen
    pour_time = config.get("pour_time", 2000)  # Zeit pro 2 cl für den Servo
    pump_position = config.get("pumpen", 250)  # Position aller Pumpen
    current_pump = None  # Aktuelle Pumpe, für Aggregation
    aggregated_cl = 0  # Aggregierte Menge für die aktuelle Pumpe

    try:
        with open(os.path.join(RECIPE_FOLDER, recipe_file), "r") as file:
            commands = file.readlines()
            total_commands = len(commands)

            for idx, command in enumerate(commands):
                command = command.strip()
                if not command:
                    continue

                # Fortschritt aktualisieren
                current_progress = int((idx + 1) / total_commands * 100)

                if command.startswith("start"):
                    print(f"Rezept '{recipe_file}' gestartet.")
                    continue

                elif command.startswith("move"):
                    target = command.split()[1]

                    # Vorherige Pumpenoperation abschließen, falls vorhanden
                    if current_pump and aggregated_cl > 0:
                        duration = int(aggregated_cl * pump_time)
                        print(f"Aktiviere Pumpe {current_pump} für {duration} ms...")
                        requests.post(f"http://{ESP_IP}:{ESP_PORT}/pump", json={"pump": current_pump, "duration": duration})
                        current_pump = None
                        aggregated_cl = 0

                    # Bestimme Position für das Ziel
                    if target in config:
                        position = config[target]
                    elif any(config.get(f"pump{i}") == target for i in range(1, 5)):
                        position = pump_position
                    else:
                        position = None

                    if position is not None:
                        print(f"Bewege Plattform zu {position} mm für '{target}'...")
                        requests.post(f"http://{ESP_IP}:{ESP_PORT}/move", json={"position": position})
                    else:
                        print(f"Ungültiger move-Befehl: {command}")
                        continue

                elif command.startswith("servo"):
                    mode, value = command.split()[1], command.split()[2]
                    if mode == "cl":
                        cl = float(value)

                        # Prüfen, ob das Ziel mit einer Pumpe verbunden ist
                        target = commands[idx - 2].split()[1]  # Ziel aus vorherigem `move`-Befehl
                        pump_number = next(
                            (i for i in range(1, 5) if config.get(f"pump{i}") == target),
                            None
                        )

                        if pump_number:
                            # Aggregiere Pumpenbefehle
                            if current_pump == pump_number:
                                aggregated_cl += cl
                            else:
                                # Vorherige Pumpe abschließen
                                if current_pump and aggregated_cl > 0:
                                    duration = int(aggregated_cl * pump_time)
                                    print(f"Aktiviere Pumpe {current_pump} für {duration} ms...")
                                    requests.post(f"http://{ESP_IP}:{ESP_PORT}/pump", json={"pump": current_pump, "duration": duration})

                                # Neue Pumpe setzen
                                current_pump = pump_number
                                aggregated_cl = cl
                        else:
                            # Servo aktivieren, wenn keine Pumpe vorhanden
                            delay = int((cl / 2) * pour_time)
                            print(f"Bewege Servo für {cl} cl mit Verzögerung {delay} ms...")
                            requests.post(f"http://{ESP_IP}:{ESP_PORT}/servo", json={"delay": delay})

                elif command.startswith("wait"):
                    # Wartezeit überspringen, falls Pumpen aggregiert werden
                    if current_pump and aggregated_cl > 0:
                        continue

                    duration = int(command.split()[1])
                    print(f"Warte {duration} ms...")
                    time.sleep(duration / 1000.0)

                elif command.startswith("done"):
                    # Abschließen aller offenen Pumpenaufträge
                    if current_pump and aggregated_cl > 0:
                        duration = int(aggregated_cl * pump_time)
                        print(f"Aktiviere Pumpe {current_pump} für {duration} ms...")
                        requests.post(f"http://{ESP_IP}:{ESP_PORT}/pump", json={"pump": current_pump, "duration": duration})
                        current_pump = None
                        aggregated_cl = 0

                    print(f"Rezept '{recipe_file}' abgeschlossen.")
                    break

        current_progress = 100  # Fortschritt auf 100% setzen

    except Exception as e:
        print(f"Fehler beim Ausführen des Rezepts: {e}")

    is_running = False
    active_recipe = None

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
