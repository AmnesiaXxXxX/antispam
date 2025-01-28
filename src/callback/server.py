from flask import Flask, request, jsonify
from src.constants import waiting_for_payment
from src.utils.logger_config import setup_flask_logger

flask_log_file = "flask_logs.log"
flask_logger = setup_flask_logger(flask_log_file)

app = Flask(__name__)
app.logger.handlers = flask_logger.handlers
app.logger.setLevel(flask_logger.level)
# Ваше секретное слово из настроек ЮMoney
notification_secret = "test_OIWcw4fI5qLwRpYm9UVevAVSAS5rBEk-W2OXFishwNA"


@app.route("/yoomoney-notification", methods=["POST"])
def yoomoney_notification():
    data = request.get_json()  # Получаем JSON из тела запроса
    if not data:
        return jsonify({"error": "Empty body"}), 400

    # Проверяем событие
    if data.get("event") == "payment.succeeded":
        id = data["object"]["id"]
        if waiting_for_payment.get(id):
            if not waiting_for_payment[id]:
                waiting_for_payment[id] = True
            else:
                del waiting_for_payment[id]

    return "OK", 200
