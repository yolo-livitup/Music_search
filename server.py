import os
import re
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI
from opencc import OpenCC

load_dotenv()

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

with open("prompt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
cc = OpenCC("t2s")  # Traditional → Simplified Chinese


def is_chinese(text):
    """Check if text is predominantly Chinese."""
    chinese_chars = sum(1 for c in text if "一" <= c <= "鿿" or "㐀" <= c <= "䶿")
    return chinese_chars > len(text.replace(" ", "").replace("\n", "")) * 0.3


def fetch_lyrics(track_name, artist_name=""):
    """Fetch lyrics from LRCLIB. Returns cleaned lyrics string or None."""
    try:
        query = f"{track_name} {artist_name}".strip()
        resp = requests.get(
            "https://lrclib.net/api/search",
            params={"q": query},
            timeout=12,
        )
        if resp.status_code != 200:
            return None

        results = resp.json()
        if not results:
            return None

        # Search results already include lyrics fields
        data = results[0]
        lyrics = data.get("syncedLyrics") or data.get("plainLyrics") or ""
        if not lyrics:
            return None

        # Remove LRC timestamps like [00:12.34]
        clean = re.sub(r"\[\d{2}:\d{2}\.\d{2}\]", "", lyrics)
        lines = [line.strip() for line in clean.split("\n") if line.strip()]
        lyrics = "\n".join(lines)

        # Convert Traditional → Simplified for Chinese lyrics
        if is_chinese(lyrics):
            lyrics = cc.convert(lyrics)
            # Additional fixes OpenCC t2s misses in lyrics context
            lyrics = lyrics.replace("著", "着")
            lyrics = lyrics.replace("妳", "你")
            lyrics = lyrics.replace("復", "复")

        return lyrics
    except Exception:
        return None


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

    user_message = query
    has_lyrics = False

    # Attempt to fetch real lyrics
    parts = query.rsplit(" ", 1)
    lyrics = None

    # Try "song artist" split
    if len(parts) == 2:
        lyrics = fetch_lyrics(parts[0], parts[1])

    # Fallback: try whole query as track name
    if not lyrics:
        lyrics = fetch_lyrics(query, "")

    if lyrics:
        has_lyrics = True
        if is_chinese(lyrics):
            instruction = "以下是这首歌的**准确歌词**。这是中文歌，无需翻译，请直接呈现歌词并进行解析分析："
        else:
            instruction = "以下是这首歌的**准确歌词**，请基于此逐行翻译和分析："
        user_message = f"{instruction}\n\n{lyrics}\n\n用户查询：{query}"

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=4096,
        )
        result = response.choices[0].message.content
        return jsonify({"result": result, "hasLyrics": has_lyrics})
    except Exception as e:
        return jsonify({"error": f"API 请求失败: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
