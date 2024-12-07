import os
import json
import time
import requests
from flask import Flask, jsonify, render_template, request
from threading import Thread

app = Flask(__name__)

RECIPE_FOLDER = "Rezepte"
CONFIG_FILE = "config.json"
ESP_IP = "192.168.2.236"
ESP_PORT = 80

active_recipe = None
is_running = False
current_progress = 0


def load_config():
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
    try:
        with open(CONFIG_FILE, "w") as file:
            json.dump(config, file, indent=4)
        print("Konfiguration erfolgreich gespeichert.")
    except Exception as e:
        print(f"Fehler beim Speichern der Konfigurationsdatei: {e}")


def check_esp_connection():
    try:
        response = requests.get(f"http://{ESP_IP}:{ESP_PORT}/status", timeout=2)
        if response.status_code == 200:
            data = response.json()
            return data.get("status") == "online"
        else:
            print(f"ESP antwortet mit Statuscode: {response.status_code}")
            return False
    except:
        return False


@app.route("/")
def index():
    recipes = []
    config = load_config()

    # Pumpengetränke in config integrieren
    for i in range(1, 5):
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
            recipes.append({"name": filename, "valid": is_valid, "reasons": invalid_reasons})

    esp_connected = check_esp_connection()
    return render_template("index.html", recipes=recipes, esp_connected=esp_connected, active_recipe=active_recipe, is_running=is_running)


@app.route("/esp_status")
def esp_status():
    esp_connected = check_esp_connection()
    return jsonify({"connected": esp_connected})


@app.route("/config", methods=["GET", "POST"])
def manage_config():
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
            if not key.startswith("pump") and key not in ["pour_time", "move_wait", "drip_wait", "refill_wait"]
        ]

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
            response = requests.post(f"http://{ESP_IP}:{ESP_PORT}/move", json={"position": value})
            if response.status_code == 200:
                return jsonify({"status": "success", "message": f"Plattform zu {value} mm bewegt."})
            else:
                return jsonify({"status": "error", "message": "ESP hat nicht auf 'move' reagiert."}), 500

        elif command_type == "servo":
            response = requests.post(f"http://{ESP_IP}:{ESP_PORT}/servo", json={"delay": value})
            if response.status_code == 200:
                return jsonify({"status": "success", "message": f"Servo mit {value} ms Verzögerung bewegt."})
            else:
                return jsonify({"status": "error", "message": "ESP hat nicht auf 'servo' reagiert."}), 500

        elif command_type == "pump":
            if not pump or not isinstance(pump, int):
                return jsonify({"status": "error", "message": "Pumpennummer fehlt oder ist ungültig."}), 400

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
        # Wir verwenden Platzhalter anstatt fixer Werte:
        move_wait_placeholder = "move_wait"
        drip_wait_placeholder = "drip_wait"
        refill_wait_placeholder = "refill_wait"

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
            commands.append(f"wait {move_wait_placeholder}")

            remaining_cl = amount_cl
            while remaining_cl > 2:
                servo_command = "servo cl 2"
                is_valid, error = validate_recipe_command(servo_command, config)
                if not is_valid:
                    return jsonify({"status": "error", "message": error}), 400
                commands.append(servo_command)
                commands.append(f"wait {refill_wait_placeholder}")
                remaining_cl -= 2

            if remaining_cl > 0:
                servo_command = f"servo cl {remaining_cl}"
                is_valid, error = validate_recipe_command(servo_command, config)
                if not is_valid:
                    return jsonify({"status": "error", "message": error}), 400
                commands.append(servo_command)
                commands.append(f"wait {drip_wait_placeholder}")

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

    elif parts[0] == "wait":
        # wait-Befehle dürfen jetzt auch Platzhalter enthalten, daher nur Grundcheck:
        if len(parts) != 2:
            return False, f"Ungültiger wait-Befehl: {command}"
        # Keine weitere Validierung hier, da Platzhalter erlaubt sind
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
    move_wait = config.get("move_wait", 500)
    drip_wait = config.get("drip_wait", 1000)
    refill_wait = config.get("refill_wait", 5000)
    pour_time = config.get("pour_time", 2000)

    pump_in_progress = False
    aggregated_pump_duration = 0
    abtropfzeit = 0
    current_target = None

    try:
        with open(os.path.join(RECIPE_FOLDER, recipe_file), "r") as file:
            commands = file.readlines()
            total_commands = len(commands)

            for idx, command in enumerate(commands):
                command = command.strip()
                if not command:
                    continue
                current_progress = int((idx+1)/total_commands*100)

                if command.startswith("start"):
                    print(f"Rezept '{recipe_file}' gestartet.")
                    continue
                elif command.startswith("move"):
                    # Hier ihre Move-Logik einfügen
                    parts = command.split()
                    if len(parts) == 2:
                        target = parts[1]
                        # Ermitteln der Position, Pumpenlogik etc. wie in Ihrem ursprünglichen Code
                        # Für Darstellung ausgelassen
                    else:
                        print(f"Ungültiger move-Befehl: {command}")

                elif command.startswith("servo"):
                    # Servo-Logik einfügen
                    parts = command.split()
                    if len(parts) >= 3:
                        mode = parts[1]
                        value = parts[2]
                        if mode == "cl":
                            cl = float(value)
                            # Pumpen oder Servo aktivieren etc.
                            # Aggregation pump_in_progress etc.
                        elif mode == "ms":
                            delay = int(value)
                            # Servo per ms bewegen
                        else:
                            print(f"Unbekannter servo Modus: {mode}")
                    else:
                        print(f"Ungültiger servo-Befehl: {command}")

                elif command.startswith("wait"):
                    parts = command.split()
                    if len(parts) == 2:
                        wait_value = parts[1]
                        if wait_value.isdigit():
                            duration = int(wait_value)
                        else:
                            # Platzhalter interpretieren
                            if wait_value == "move_wait":
                                duration = move_wait
                            elif wait_value == "drip_wait":
                                duration = drip_wait
                            elif wait_value == "refill_wait":
                                duration = refill_wait
                            else:
                                print(f"Unbekannter wait-Platzhalter: {wait_value}, Standard 500ms.")
                                duration = 500

                        if pump_in_progress:
                            abtropfzeit = duration
                            print(f"Setze Abtropfzeit auf {abtropfzeit} ms (Platzhalter: {wait_value}).")
                        else:
                            print(f"Warte {duration} ms (Platzhalter: {wait_value}).")
                            time.sleep(duration/1000.0)
                    else:
                        print(f"Ungültiger wait-Befehl: {command}")

                elif command.startswith("done"):
                    # Abschließende Logik, Pumpen stoppen usw.
                    print(f"Rezept '{recipe_file}' abgeschlossen.")
                    break

        current_progress = 100
    except Exception as e:
        print(f"Fehler beim Ausführen des Rezepts: {e}")

    is_running = False
    active_recipe = None


@app.route("/get_recipe_ingredients")
def get_recipe_ingredients():
    recipe_name = request.args.get("recipe")
    if not recipe_name:
        return jsonify({"status":"error","message":"Kein Rezept angegeben"}),400
    recipe_path = os.path.join(RECIPE_FOLDER, recipe_name)
    if not os.path.exists(recipe_path):
        return jsonify({"status":"error","message":"Rezept nicht gefunden"}),404

    try:
        with open(recipe_path,"r") as f:
            lines = f.readlines()

        config = load_config()
        ingredientAmounts = {}
        currentIngredient = None
        for line in lines:
            line=line.strip()
            if line.startswith("move"):
                args=line.split()
                if len(args)==2:
                    currentIngredient=args[1]
            elif line.startswith("servo cl") and currentIngredient:
                val=float(line.split()[2])
                if currentIngredient not in ingredientAmounts:
                    ingredientAmounts[currentIngredient]=0.0
                ingredientAmounts[currentIngredient]+=val

        ing_list = []
        for ing,amt in ingredientAmounts.items():
            ing_list.append({"name":ing,"amount":amt})

        return jsonify({"status":"success","ingredients":ing_list})
    except Exception as e:
        print(e)
        return jsonify({"status":"error","message":"Fehler beim Lesen des Rezepts"}),500


@app.route("/run_custom_recipe", methods=["POST"])
def run_custom_recipe():
    global is_running
    if is_running:
        return jsonify({"status":"error","message":"Ein Rezept wird bereits ausgeführt."}),400
    if not check_esp_connection():
        return jsonify({"status":"error","message":"ESP ist nicht verbunden."}),400

    data=request.json
    recipe_name=data.get("recipe","")
    ingredients=data.get("ingredients",[])
    if not recipe_name or not ingredients:
        return jsonify({"status":"error","message":"Rezeptname oder Zutaten fehlen"}),400

    recipe_path = os.path.join(RECIPE_FOLDER, recipe_name)
    if not os.path.exists(recipe_path):
        return jsonify({"status":"error","message":"Rezept nicht gefunden"}),404

    try:
        with open(recipe_path,"r") as f:
            original_lines=f.readlines()

        ing_map={ing["name"]:ing["amount"] for ing in ingredients}
        config=load_config()

        currentIngredient=None
        new_commands=[]
        for line in original_lines:
            line=line.strip()
            if line.startswith("move"):
                args=line.split()
                if len(args)==2:
                    currentIngredient=args[1]
                new_commands.append(line)
            elif line.startswith("servo cl") and currentIngredient:
                parts=line.split()
                original_val=float(parts[2])
                new_val=ing_map.get(currentIngredient,original_val)
                parts[2]=str(new_val)
                new_commands.append(" ".join(parts))
            else:
                new_commands.append(line)

        thread=Thread(target=execute_custom_recipe, args=(new_commands,recipe_name,))
        thread.start()
        return jsonify({"status":"success","message":"Angepasstes Rezept gestartet."})
    except Exception as e:
        print(e)
        return jsonify({"status":"error","message":"Fehler beim Anpassen des Rezepts."}),500


def execute_custom_recipe(commands, recipe_name):
    global active_recipe, is_running, current_progress
    active_recipe = recipe_name
    is_running = True
    current_progress = 0

    config = load_config()
    move_wait = config.get("move_wait", 500)
    drip_wait = config.get("drip_wait", 1000)
    refill_wait = config.get("refill_wait", 5000)
    pour_time = config.get("pour_time", 2000)

    pump_in_progress=False
    aggregated_pump_duration=0
    abtropfzeit=0
    current_target=None

    total_commands=len(commands)
    try:
        for idx,command in enumerate(commands):
            command=command.strip()
            if not command:
                continue
            current_progress=int((idx+1)/total_commands*100)
            if command.startswith("start"):
                print(f"Custom Rezept '{recipe_name}' gestartet.")
                continue
            elif command.startswith("move"):
                # Move-Logik wie bei execute_recipe
                parts=command.split()
                if len(parts)==2:
                    target=parts[1]
                else:
                    print(f"Ungültiger move-Befehl: {command}")
            elif command.startswith("servo"):
                parts=command.split()
                if len(parts)>=3:
                    mode=parts[1]
                    value=parts[2]
                    # Servo-Logik analog zu execute_recipe
                else:
                    print(f"Ungültiger servo-Befehl: {command}")
            elif command.startswith("wait"):
                parts=command.split()
                if len(parts)==2:
                    wait_value=parts[1]
                    if wait_value.isdigit():
                        duration=int(wait_value)
                    else:
                        if wait_value=="move_wait":
                            duration=move_wait
                        elif wait_value=="drip_wait":
                            duration=drip_wait
                        elif wait_value=="refill_wait":
                            duration=refill_wait
                        else:
                            print(f"Unbekannter wait-Platzhalter: {wait_value}, Standard 500ms.")
                            duration=500
                    if pump_in_progress:
                        abtropfzeit=duration
                        print(f"Setze Abtropfzeit auf {abtropfzeit} ms (Platzhalter: {wait_value}).")
                    else:
                        print(f"Warte {duration} ms (Platzhalter: {wait_value}).")
                        time.sleep(duration/1000.0)
                else:
                    print(f"Ungültiger wait-Befehl: {command}")
            elif command.startswith("done"):
                print(f"Custom Rezept '{recipe_name}' abgeschlossen.")
                break
        current_progress=100
    except Exception as e:
        print(f"Fehler beim Ausführen des Custom Rezepts: {e}")

    is_running=False
    active_recipe=None


@app.route("/calibrate", methods=["GET", "POST"])
def calibrate():
    config = load_config()
    if request.method == "GET":
        item = request.args.get("item", "")
        if not item:
            return "Kein Item angegeben.", 400

        is_pump = False
        pump_number = None
        if item.startswith("pump") and item[-1].isdigit():
            is_pump = True
            pump_number = int(item[-1])

        drink_position = config.get(item) if (item in config and not item.startswith("pump")) else None
        pour_time = config.get("pour_time", 2000)

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

        if item.startswith("pump") and item[-1].isdigit():
            pump_number = int(item[-1])
            pump_drink_new = data.get("pump_drink", "").strip()
            pump_time_new = int(data.get("pump_time", 1000))
            pump_pos_new = int(data.get("pump_position", 250))

            if pump_drink_new:
                config[f"pump{pump_number}"] = pump_drink_new
            config[f"pump{pump_number}_time"] = pump_time_new
            config[f"pump{pump_number}_position"] = pump_pos_new

        else:
            if "pour_time" in data:
                config["pour_time"] = int(data["pour_time"])
            if "drink_position" in data and item in config:
                config[item] = int(data["drink_position"])

        save_config(config)
        return jsonify({"status": "success", "message": "Kalibrierte Werte erfolgreich gespeichert."})


if __name__ == "__main__":
    # Stellen Sie sicher, dass:
    # - Ein Ordner "Rezepte" existiert
    # - Die templates config.html, rezepte.html, calibrate.html, index.html vorhanden sind
    # - config.json mit pour_time, move_wait, drip_wait, refill_wait etc. existiert
    app.run(host="0.0.0.0", port=5001, debug=True)
