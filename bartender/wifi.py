from flask import Flask, request
import subprocess

app = Flask(__name__)

wifi_device = "wlan0"

@app.route('/', methods=['GET', 'POST'])
def index():
    message = ""
    success = False

    if request.method == 'POST':
        ssid = request.form.get('ssid', '').strip()
        password = request.form.get('password', '').strip()

        if not ssid:
            message = "Fehler: SSID wurde nicht ausgewählt."
        elif not password:
            message = "Fehler: Passwort wurde nicht eingegeben."
        else:
            connection_command = [
                "nmcli", "--colors", "no", "device", "wifi", "connect",
                ssid, "ifname", wifi_device
            ]
            if password:
                connection_command += ["password", password]

            try:
                result = subprocess.run(connection_command, capture_output=True, text=True, check=True)
                # Optional: Neustart des Servers nach erfolgreicher Verbindung
                subprocess.run(['sudo', 'python', 'restart.py'], check=True)
                print("server.py wurde erfolgreich neu gestartet.")
                message = f"Erfolg: {result.stdout}"
                success = True
            except subprocess.CalledProcessError as e:
                error_message = e.stderr or e.stdout
                message = f"Fehler: Verbindung zum WiFi-Netzwerk fehlgeschlagen: <i>{error_message}</i>"

    try:
        result = subprocess.check_output([
            "nmcli", "--colors", "no", "-m", "multiline",
            "--get-value", "SSID", "dev", "wifi", "list",
            "ifname", wifi_device
        ])
        ssids_list = result.decode().split('\n')
        ssids = [ssid.removeprefix("SSID:").strip() for ssid in ssids_list if ssid.startswith("SSID:") and ssid.removeprefix("SSID:").strip()]
    except subprocess.CalledProcessError:
        ssids = []

    # Erstelle das HTML mit reinem Python
    dropdowndisplay = f"""
    <!DOCTYPE html>
    <html lang="de">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
        <title>WiFi Steuerung</title>
        <!-- Bootstrap CSS -->
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
        <div class="container mt-5">
            <h1 class="mb-4 text-center">WiFi Steuerung</h1>
            <div class="row justify-content-center">
                <div class="col-md-6">
                    <form action="/" method="post" class="needs-validation" novalidate>
                        <div class="mb-3">
                            <label for="ssid" class="form-label">Wähle ein WiFi-Netzwerk:</label>
                            <select name="ssid" id="ssid" class="form-select" required>
                                <option value="" disabled selected>Bitte auswählen</option>
    """
    for ssid in ssids:
        dropdowndisplay += f"""
                                <option value="{ssid}">{ssid}</option>
        """

    dropdowndisplay += """
                            </select>
                            <div class="invalid-feedback">
                                Bitte wähle ein WiFi-Netzwerk aus.
                            </div>
                        </div>
                        <div class="mb-3">
                            <label for="password" class="form-label">Passwort:</label>
                            <input type="password" class="form-control" id="password" name="password" required>
                            <div class="invalid-feedback">
                                Bitte gib das Passwort ein.
                            </div>
                        </div>
                        <button type="submit" class="btn btn-primary w-100">Verbinden</button>
                    </form>
                </div>
            </div>
    """

    # Füge die Nachricht hinzu, wenn vorhanden
    if message:
        alert_type = "success" if success else "danger"
        dropdowndisplay += f"""
            <div class="row justify-content-center mt-4">
                <div class="col-md-6">
                    <div class="alert alert-{alert_type}" role="alert">
                        {message}
                    </div>
                </div>
            </div>
        """

    # Beende das HTML
    dropdowndisplay += """
        </div>

        <!-- Bootstrap JS und Abhängigkeiten -->
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            // Beispiel für Formularvalidierung
            (function () {
                'use strict'
                var forms = document.querySelectorAll('.needs-validation')
                Array.prototype.slice.call(forms)
                    .forEach(function (form) {
                        form.addEventListener('submit', function (event) {
                            if (!form.checkValidity()) {
                                event.preventDefault()
                                event.stopPropagation()
                            }
                            form.classList.add('was-validated')
                        }, false)
                    })
            })()
        </script>
    </body>
    </html>
    """

    return dropdowndisplay


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)
