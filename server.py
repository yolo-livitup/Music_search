import json
import os
import re
import uuid
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory, render_template_string
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
cc = OpenCC("t2s")
shared_results = {}
search_cache = {}
MAX_CACHE = 50


def is_chinese(text):
    chinese_chars = sum(1 for c in text if "一" <= c <= "鿿")
    return chinese_chars > len(text.replace(" ", "").replace("\n", "")) * 0.3


def classify_query(query):
    """Quick classification: song, artist, or album."""
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一个查询分类器。判断用户输入属于哪种类型，只回复一个英文单词：\n"
                        "song —— 用户想查某首歌的歌词\n"
                        "artist —— 用户输入的是音乐人/歌手/乐手/制作人的名字\n"
                        "album —— 用户明确想查某张专辑\n\n"
                        "核心规则（按优先级）：\n"
                        "1. 如果输入明显包含专辑关键词（Album/OST/Soundtrack/专辑），或用户明确说'某某专辑'，归类为 album\n"
                        "2. 如果输入是【纯粹单个人名】（如'张学友'、'周杰伦'、'Kendrick Lamar'、'坂本龙一'），"
                        "没有其他词，归类为 artist\n"
                        "3. 如果输入包含两个及以上部分（如'luther Kendrick Lamar'、'晴天 周杰伦'、"
                        "'Bohemian Rhapsody Queen'），说明用户给出了'歌名+歌手'，归类为 song\n"
                        "4. 不确定时默认归类为 song\n\n"
                        "关键区别：'Kendrick Lamar'（纯人名）→ artist；"
                        "'luther Kendrick Lamar'（歌名+人名）→ song；"
                        "'90210'（看起来像歌名）→ song"
                    ),
                },
                {"role": "user", "content": query},
            ],
            temperature=0,
            max_tokens=10,
        )
        result = resp.choices[0].message.content.strip().lower()
        if "album" in result:
            return "album"
        elif "artist" in result:
            return "artist"
        else:
            return "song"
    except Exception:
        return "song"


def identify_song_artist(query):
    """Use DeepSeek to identify the most likely track name and artist from a query."""
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一个音乐识别助手。用户输入了一个歌曲查询，"
                        "请识别出最可能对应的歌曲名和歌手名。"
                        "只返回JSON格式：{\"track\": \"歌曲名\", \"artist\": \"歌手名\"}。"
                        "如果无法确定歌手，artist字段返回空字符串。"
                        "不要返回任何其他内容。"
                    ),
                },
                {"role": "user", "content": query},
            ],
            temperature=0,
            max_tokens=100,
        )
        result = resp.choices[0].message.content.strip()
        if result.startswith("```"):
            result = result.split("\n", 2)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(result)
        return data.get("track", query), data.get("artist", "")
    except Exception:
        return query, ""


def fetch_lyrics(track_name, artist_name=""):
    """Fetch lyrics from LRCLIB with result scoring. Returns cleaned lyrics or None."""
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

        # Score each result to find the best match
        query_lower = track_name.lower()
        artist_lower = artist_name.lower()
        best = None
        best_score = -1

        for item in results:
            score = 0
            item_track = (item.get("trackName") or "").lower()
            item_artist = (item.get("artistName") or "").lower()

            if query_lower == item_track:
                score += 100
            elif query_lower in item_track or item_track in query_lower:
                score += 50

            if artist_lower and artist_lower in item_artist:
                score += 80
            elif artist_lower and item_artist in artist_lower:
                score += 40

            if item_track.startswith(query_lower):
                score += 30

            if item.get("syncedLyrics") or item.get("plainLyrics"):
                score += 10

            if score > best_score:
                best_score = score
                best = item

        if not best:
            best = results[0]

        lyrics = best.get("syncedLyrics") or best.get("plainLyrics") or ""
        if not lyrics:
            return None

        clean = re.sub(r"\[\d{2}:\d{2}\.\d{2}\]", "", lyrics)
        lines = [line.strip() for line in clean.split("\n") if line.strip()]
        lyrics = "\n".join(lines)

        if is_chinese(lyrics):
            lyrics = cc.convert(lyrics)
            lyrics = lyrics.replace("著", "着").replace("妳", "你").replace("復", "复")

        return lyrics
    except Exception:
        return None


def get_recommendations(query, qtype):
    """Get 3 recommended songs/artists/albums via DeepSeek."""
    try:
        hints = {
            "song": "推荐3首风格或主题相似的歌曲",
            "artist": "推荐3位风格相似的艺人（不要推荐该艺人自己的歌，推荐其他相似艺人）",
            "album": "推荐3张风格或主题相似的专辑",
        }
        hint = hints.get(qtype, hints["song"])
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"你是音乐推荐助手。基于用户的兴趣，{hint}。"
                        "只返回JSON数组，每个元素包含 track(歌名/专辑名/艺人名) 和 artist(艺人名，如适用，否则空字符串) 两个字段。"
                        "不要返回任何其他内容。示例：[{\"track\":\"Bohemian Rhapsody\",\"artist\":\"Queen\"}]"
                    ),
                },
                {"role": "user", "content": query},
            ],
            temperature=0.7,
            max_tokens=300,
        )
        text = resp.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 2)[-1].rsplit("```", 1)[0].strip()
        recs = json.loads(text)
        return recs[:3] if isinstance(recs, list) else []
    except Exception:
        return []


SHARE_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0b0b10">
<title>Music Search - 分享结果</title>
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
body{font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",-apple-system,BlinkMacSystemFont,sans-serif;background:#0b0b10;color:#d0d0d8;min-height:100vh;line-height:1.75}
.container{max-width:860px;margin:0 auto;padding:60px 24px}
header{text-align:center;margin-bottom:32px}
h1{font-size:1.3rem;font-weight:700;color:#e0d0b0;letter-spacing:.06em}
.badge{display:inline-block;padding:3px 12px;font-size:.76rem;border-radius:14px;background:rgba(196,164,108,.12);border:1px solid rgba(196,164,108,.25);color:#c4a46c;margin-top:8px}
.content{background:rgba(22,22,29,.85);border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:32px 36px;font-size:.925rem;color:#c4c4d0;backdrop-filter:blur(16px);box-shadow:0 4px 32px rgba(0,0,0,.2)}
.content h1{font-size:1.2rem;margin-bottom:.6em;padding-bottom:.45em;border-bottom:1px solid rgba(255,255,255,.06)}
.content h2{font-size:1rem;font-weight:600;color:#c4a46c;margin:1.5em 0 .5em}
.content h3{font-size:.92rem;color:#ccc0a8;margin:1.2em 0 .35em}
.content p{margin:.5em 0}
.content strong{color:#e0d4bc}
.content ul,.content ol{padding-left:1.3em;margin:.5em 0}
.content li::marker{color:#c4a46c}
.content blockquote{border-left:2px solid #c4a46c;margin:.75em 0;padding:.3em 0 .3em 1em;color:#8b8b9e;font-style:italic}
.content hr{border:none;height:1px;background:rgba(255,255,255,.06);margin:1.5em 0}
.content code{background:rgba(255,255,255,.05);padding:1px 6px;border-radius:3px;font-size:.92em;color:#c8b898}
.content a{color:#c4a46c}
.lt{color:#9b8c6f;display:block;padding-left:1em;font-style:italic}
footer{text-align:center;margin-top:24px;font-size:.78rem;color:#58586b}
footer a{color:#8b8b9e;text-decoration:none}
@media(max-width:600px){.content{padding:20px 18px;font-size:.88rem}}
</style>
</head>
<body>
<div class="container">
<header><h1>Music Search</h1><div class="badge">{{ qtype_label }}</div></header>
<div class="content">{{ content | safe }}</div>
<footer>由 <a href="/">Music Search</a> 生成</footer>
</div>
</body>
</html>"""


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

    cache_key = query.strip().lower()
    if cache_key in search_cache:
        return jsonify(search_cache[cache_key])

    # Step 1: classify the query
    qtype = classify_query(query)

    # Step 2: fetch lyrics only for song queries
    user_message = query
    has_lyrics = False

    if qtype == "song":
        # Step 2a: identify the most likely track + artist via DeepSeek
        track, artist = identify_song_artist(query)
        lyrics = fetch_lyrics(track, artist)
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
        recs = get_recommendations(query, qtype)
        response_data = {
            "result": result,
            "recommendations": recs,
            "hasLyrics": has_lyrics,
            "type": qtype,
        }
        if len(search_cache) >= MAX_CACHE:
            search_cache.pop(next(iter(search_cache)))
        search_cache[cache_key] = response_data
        return jsonify(response_data)
    except Exception as e:
        return jsonify({"error": f"API 请求失败: {str(e)}"}), 500


@app.route("/api/share", methods=["POST"])
def share():
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效请求"}), 400
    sid = uuid.uuid4().hex[:8]
    shared_results[sid] = {
        "content": data.get("content", ""),
        "qtype": data.get("type", "song"),
    }
    return jsonify({"id": sid, "url": f"/s/{sid}"})


@app.route("/s/<sid>")
def view_share(sid):
    item = shared_results.get(sid)
    if not item:
        return "分享不存在或已过期", 404
    labels = {"song": "歌词解析", "album": "专辑档案", "artist": "人物志"}
    content_html = item["content"]
    content_html = content_html.replace("<!-- split -->", "")
    content_html = "\n".join(
        '<span class="lt">' + line[2:] + "</span>" if line.lstrip().startswith("^ ") else line
        for line in content_html.split("\n")
    )
    # basic markdown conversion
    import re as _re
    content_html = _re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', content_html)
    content_html = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content_html)
    content_html = _re.sub(r"^#{1,2} (.+)$", r"<h2>\1</h2>", content_html, flags=_re.MULTILINE)
    content_html = _re.sub(r"^#{3} (.+)$", r"<h3>\1</h3>", content_html, flags=_re.MULTILINE)
    content_html = _re.sub(r"^- (.+)$", r"<li>\1</li>", content_html, flags=_re.MULTILINE)
    content_html = _re.sub(r"^---$", r"<hr>", content_html, flags=_re.MULTILINE)
    content_html = content_html.replace("\n", "<br>" if len(content_html) < 5000 else "\n")
    return render_template_string(
        SHARE_PAGE,
        content=content_html,
        qtype_label=labels.get(item["qtype"], "查询结果"),
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
