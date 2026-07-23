from datetime import datetime
import os
import sqlite3
from flask import Flask, g, jsonify, request, send_file

app = Flask(__name__)
app.json.ensure_ascii = False
# Baza danych (na Renderze zap pisoana będzie w katalogu domyślnym, u Ciebie lokalnie)
DATABASE = "doniczka.db"


def get_db():
  db = getattr(g, "_database", None)
  if db is None:
    db = g._database = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
  return db


@app.teardown_appcontext
def close_connection(exception):
  db = getattr(g, "_database", None)
  if db is not None:
    db.close()


# Inicjalizacja tabel (tworzy je, jeśli nie istnieją)
def init_db():
  with app.app_context():
    db = get_db()
    db.execute("""
            CREATE TABLE IF NOT EXISTS Measurements_History (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                temperature REAL,
                moisture REAL,
                water_level_ok INTEGER,
                pump_status TEXT,
                plant_id INTEGER
            )
        """)
    db.commit()


init_db()


# 1. Endpoint do odbierania pomiarów z mikrokontrolera (POST)
@app.route("/log", methods=["POST"])
def log_measurement():
  data = request.json
  if not data:
    return jsonify({"error": "Brak danych JSON"}), 400

  plant_id = data.get("plant_id", 1)
  temperature = data.get("temperature")
  moisture = data.get("moisture")
  water_level_ok = 1 if data.get("water_level_ok") else 0
  pump_status = data.get("pump_status", "WYŁĄCZONA")

  # Pobranie aktualnego czasu serwera
  timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

  db = get_db()
  db.execute(
      """
        INSERT INTO Measurements_History (timestamp, temperature, moisture, water_level_ok, pump_status, plant_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
      (
          timestamp,
          temperature,
          moisture,
          water_level_ok,
          pump_status,
          plant_id,
      ),
  )
  db.commit()

  return jsonify({"status": "sukces", "zapisano_czas": timestamp}), 201


# 2. NOWOŚĆ: Endpoint do pobierania WSZYSTKICH pomiarów bez filtrowania po ID kwiatka
@app.route("/measurements", methods=["GET"])
def get_all_measurements():
  db = get_db()
  cursor = db.execute(
      "SELECT * FROM Measurements_History ORDER BY id DESC"
  )  # Najnowsze na górze
  rows = cursor.fetchall()

  result = []
  for row in rows:
    result.append({
        "id": row["id"],
        "timestamp": row["timestamp"],
        "temperature": row["temperature"],
        "moisture": row["moisture"],
        "water_level_ok": row["water_level_ok"],
        "pump_status": row["pump_status"],
        "plant_id": row["plant_id"],
    })

  return jsonify(result)


# 3. Stary endpoint z filtrowaniem po ID (zostawiamy, jakby był potrzebny)
@app.route("/measurements/<int:plant_id>", methods=["GET"])
def get_measurements_by_plant(plant_id):
  db = get_db()
  cursor = db.execute(
      "SELECT * FROM Measurements_History WHERE plant_id = ? ORDER BY id DESC",
      (plant_id,),
  )
  rows = cursor.fetchall()

  result = []
  for row in rows:
    result.append({
        "id": row["id"],
        "timestamp": row["timestamp"],
        "temperature": row["temperature"],
        "moisture": row["moisture"],
        "water_level_ok": row["water_level_ok"],
        "pump_status": row["pump_status"],
        "plant_id": row["plant_id"],
    })

  return jsonify(result)


# 4. NOWOŚĆ: Przycisk / funkcja do pobierania pliku bazy danych na Twój komputer!
@app.route("/download-db", methods=["GET"])
def download_database():
  if os.path.exists(DATABASE):
    return send_file(DATABASE, as_attachment=True)
  return "Baza danych jeszcze nie istnieje!", 404


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000, debug=True)
