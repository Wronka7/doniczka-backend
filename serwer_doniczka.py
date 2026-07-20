import os
import sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Zezwala na połączenia z aplikacji mobilnej / PWA

DATABASE = 'doniczka.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ==========================================
# INICJALIZACJA BAZY DANYCH
# ==========================================
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabela z konfiguracją roślin
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Plants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            species TEXT,
            planted_date TEXT,
            moisture_start REAL DEFAULT 25.0,
            moisture_stop REAL DEFAULT 40.0,
            notes TEXT
        )
    ''')
    
    # Tabela z historią pomiarów
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Measurements_History (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plant_id INTEGER DEFAULT 1,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            temperature REAL,
            moisture REAL,
            water_level_ok BOOLEAN,
            pump_status TEXT,
            FOREIGN KEY (plant_id) REFERENCES Plants (id)
        )
    ''')
    
    # Domyślny wiersz dla pierwszej rośliny (jeśli baza jest pusta)
    cursor.execute("SELECT COUNT(*) FROM Plants")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO Plants (id, name, species, planted_date, moisture_start, moisture_stop, notes)
            VALUES (1, 'Moja Pierwsza Roślina', 'Monstera', '2026-05-01', 25.0, 40.0, 'Roślina w salonie')
        ''')
    
    conn.commit()
    conn.close()

init_db()

# ==========================================
# ENDPOINTY DLA ARDUINO / ESP
# ==========================================

# 1. Zapis pojedynczego pomiaru na żywo
@app.route('/log', methods=['POST'])
def log_measurement():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Brak danych JSON"}), 400

    plant_id = data.get('plant_id', 1)
    temp = data.get('temperature')
    moisture = data.get('moisture')
    water_ok = data.get('water_level_ok')
    pump_status = data.get('pump_status', 'NIEZNANY')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO Measurements_History (plant_id, temperature, moisture, water_level_ok, pump_status)
        VALUES (?, ?, ?, ?, ?)
    ''', (plant_id, temp, moisture, water_ok, pump_status))
    conn.commit()
    conn.close()

    print(f"[LIVE] Roślina ID={plant_id} | Temp: {temp}°C | Wilgotność: {moisture}% | Woda OK: {water_ok} | Pompa: {pump_status}")
    return jsonify({"status": "success", "message": "Pomiar zapisany"}), 201


# 2. Zbiórka danych z karty MicroSD (tryb offline/sync)
@app.route('/bulk_log', methods=['POST'])
def bulk_log():
    data = request.get_json()
    if not data or 'logs' not in data:
        return jsonify({"status": "error", "message": "Wymagane pole 'logs'"}), 400

    logs = data['logs']
    conn = get_db_connection()
    cursor = conn.cursor()

    count = 0
    for log in logs:
        plant_id = log.get('plant_id', 1)
        timestamp = log.get('timestamp')
        temp = log.get('temperature')
        moisture = log.get('moisture')
        water_ok = log.get('water_level_ok')
        pump_status = log.get('pump_status', 'NIEZNANY')

        cursor.execute('''
            INSERT INTO Measurements_History (plant_id, timestamp, temperature, moisture, water_level_ok, pump_status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (plant_id, timestamp, temp, moisture, water_ok, pump_status))
        count += 1

    conn.commit()
    conn.close()

    print(f"[SD-SYNC] Zsynchronizowano {count} zaległych pomiarów z karty SD!")
    return jsonify({"status": "success", "message": f"Pomyślnie zsynchronizowano {count} wpisów"}), 201


# 3. Pobieranie konfiguracji progów podawania wody dla Arduino (POPRAWIONE)
@app.route('/plant/<int:plant_id>/config', methods=['GET'])
def get_plant_config(plant_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    plant = cursor.execute("SELECT id, moisture_start, moisture_stop FROM Plants WHERE id = ?", (plant_id,)).fetchone()
    conn.close()

    if plant is None:
        return jsonify({"status": "error", "message": "Nie znaleziono rośliny"}), 404

    return jsonify({
        "status": "success",
        "plant_id": plant['id'],
        "moisture_start": plant['moisture_start'],
        "moisture_stop": plant['moisture_stop']
    }), 200


# ==========================================
# ENDPOINTY DLA APLIKACJI MOBILNEJ / TELEFONU
# ==========================================

# 4. Pobranie listy wszystkich roślin
@app.route('/plants', methods=['GET'])
def get_plants():
    conn = get_db_connection()
    cursor = conn.cursor()
    plants = cursor.execute("SELECT * FROM Plants").fetchall()
    conn.close()
    return jsonify([dict(p) for p in plants]), 200


# 5. Pobranie historii pomiarów dla danej rośliny (np. ostatnie 20)
@app.route('/measurements/<int:plant_id>', methods=['GET'])
def get_measurements(plant_id):
    limit = request.args.get('limit', 20)
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute('''
        SELECT * FROM Measurements_History
        WHERE plant_id = ?
        ORDER BY timestamp DESC LIMIT ?
    ''', (plant_id, limit)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200


# 6. Edycja/Ustawienie nowej rośliny lub zmiany progów wilgotności z telefonu
@app.route('/plant/settings', methods=['POST'])
def update_plant_settings():
    data = request.get_json()
    if not data or 'plant_id' not in data:
        return jsonify({"status": "error", "message": "Wymagane 'plant_id'"}), 400

    plant_id = data['plant_id']
    moisture_start = data.get('moisture_start')
    moisture_stop = data.get('moisture_stop')
    name = data.get('name')
    species = data.get('species')
    planted_date = data.get('planted_date')

    conn = get_db_connection()
    cursor = conn.cursor()

    if moisture_start is not None:
        cursor.execute("UPDATE Plants SET moisture_start = ? WHERE id = ?", (moisture_start, plant_id))
    if moisture_stop is not None:
        cursor.execute("UPDATE Plants SET moisture_stop = ? WHERE id = ?", (moisture_stop, plant_id))
    if name is not None:
        cursor.execute("UPDATE Plants SET name = ? WHERE id = ?", (name, plant_id))
    if species is not None:
        cursor.execute("UPDATE Plants SET species = ? WHERE id = ?", (species, plant_id))
    if planted_date is not None:
        cursor.execute("UPDATE Plants SET planted_date = ? WHERE id = ?", (planted_date, plant_id))

    conn.commit()
    conn.close()

    print(f"[API MOBILNE] Zaktualizowano ustawienia dla rośliny ID={plant_id}")
    return jsonify({"status": "success", "message": "Ustawienia zaktualizowane"}), 200


# ==========================================
# URUCHOMIENIE SERWERA
# ==========================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("==========================================")
    print(f"SERWER WI-FI / CLOUD DLA DONICZKI NA PORTU {port}")
    print("==========================================")
    app.run(host='0.0.0.0', port=port, debug=True)
