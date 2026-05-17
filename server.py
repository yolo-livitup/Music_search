import os
import json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

# Load system prompt
with open("prompt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/search", methods=["POST"])
def search():
    data = request.get_json()
    if not data or "query" not in data:
        return jsonify({"error": "缺少查询参数"}), 400

    query = data["query"].strip()
    if not query:
        return jsonify({"error": "查询内容不能为空"}), 400

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0.7,
            max_tokens=4096,
        )
        result = response.choices[0].message.content
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": f"API 请求失败: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
