/* ====== Service Worker ====== */
if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js");
}

/* ====== Animated Background Canvas ====== */
const canvas = document.getElementById("bgCanvas");
const ctx = canvas.getContext("2d");

let w, h;
const particles = [];
const NOTES = ["♩", "♪", "♫", "♬", "♭", "♯", "𝄞", "𝄢"];
const NOTE_COLORS = [
    "rgba(196,164,108,0.18)",
    "rgba(196,164,108,0.12)",
    "rgba(180,150,100,0.10)",
    "rgba(200,180,140,0.14)",
];

function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
}
window.addEventListener("resize", resize);
resize();

class Particle {
    constructor() {
        this.reset(true);
    }

    reset(init) {
        this.x = Math.random() * w;
        this.y = init ? Math.random() * h : h + 40;
        this.size = 14 + Math.random() * 22;
        this.speed = 0.3 + Math.random() * 0.7;
        this.wobble = Math.random() * Math.PI * 2;
        this.wobbleSpeed = 0.003 + Math.random() * 0.008;
        this.opacity = 0.06 + Math.random() * 0.14;
        this.note = NOTES[Math.floor(Math.random() * NOTES.length)];
        this.color = NOTE_COLORS[Math.floor(Math.random() * NOTE_COLORS.length)];
        this.driftX = 0;
        this.driftSpeed = (Math.random() - 0.5) * 0.3;
    }

    update() {
        this.y -= this.speed;
        this.wobble += this.wobbleSpeed;
        this.driftX += this.driftSpeed;
        if (this.driftX > 1 || this.driftX < -1) this.driftSpeed *= -1;
        this.x += this.driftX * 0.3;
        if (this.y < -60) this.reset(false);
    }

    draw() {
        ctx.save();
        ctx.globalAlpha = this.opacity;
        ctx.fillStyle = this.color.replace(/[\d.]+\)$/, "1)");
        ctx.font = `${this.size}px serif`;
        ctx.textAlign = "center";
        ctx.fillText(this.note, this.x + Math.sin(this.wobble) * 20, this.y);
        ctx.restore();
    }
}

// Create particles
for (let i = 0; i < 35; i++) {
    particles.push(new Particle());
}

// Gradient orb
let orbAngle = 0;

function drawBackground() {
    // Subtle gradient base
    const grad = ctx.createRadialGradient(w * 0.7, h * 0.3, 0, w * 0.5, h * 0.5, Math.max(w, h));
    grad.addColorStop(0, "rgba(196,164,108,0.03)");
    grad.addColorStop(0.4, "rgba(180,140,90,0.02)");
    grad.addColorStop(1, "rgba(13,13,17,0)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);

    // Slow-moving orb
    orbAngle += 0.002;
    const ox = w * 0.5 + Math.cos(orbAngle) * w * 0.3;
    const oy = h * 0.4 + Math.sin(orbAngle * 0.7) * h * 0.2;
    const orb = ctx.createRadialGradient(ox, oy, 0, ox, oy, 300);
    orb.addColorStop(0, "rgba(196,164,108,0.04)");
    orb.addColorStop(1, "rgba(13,13,17,0)");
    ctx.fillStyle = orb;
    ctx.fillRect(0, 0, w, h);
}

function animate() {
    ctx.clearRect(0, 0, w, h);
    drawBackground();

    for (const p of particles) {
        p.update();
        p.draw();
    }
    requestAnimationFrame(animate);
}

animate();

/* ====== Search History ====== */
const history = document.getElementById("history");
const historyList = document.getElementById("historyList");
const clearHistoryBtn = document.getElementById("clearHistoryBtn");
const STORAGE_KEY = "music_search_history";
const MAX_HISTORY = 10;

function loadHistory() {
    try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
    } catch {
        return [];
    }
}

function saveHistory(items) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

function addHistory(query) {
    const items = loadHistory();
    const idx = items.indexOf(query);
    if (idx > -1) items.splice(idx, 1);
    items.unshift(query);
    if (items.length > MAX_HISTORY) items.pop();
    saveHistory(items);
    renderHistory();
}

function renderHistory() {
    const items = loadHistory();
    if (items.length === 0) {
        history.classList.add("hidden");
        return;
    }
    history.classList.remove("hidden");
    historyList.innerHTML = items
        .map((q) => `<span class="history-item" data-query="${q.replace(/"/g, "&quot;")}">${escapeHtml(q)}</span>`)
        .join("");

    historyList.querySelectorAll(".history-item").forEach((el) => {
        el.addEventListener("click", () => {
            input.value = el.dataset.query;
            search();
        });
    });
}

function clearHistory() {
    localStorage.removeItem(STORAGE_KEY);
    renderHistory();
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

clearHistoryBtn.addEventListener("click", clearHistory);
renderHistory();

/* ====== Search Logic ====== */
const input = document.getElementById("queryInput");
const searchBtn = document.getElementById("searchBtn");
const loading = document.getElementById("loading");
const result = document.getElementById("result");
const resultContent = document.getElementById("resultContent");
const error = document.getElementById("error");
const copyBtn = document.getElementById("copyBtn");
const modeBadge = document.getElementById("modeBadge");

const MODE_LABELS = {
    song: { text: "歌词解析", icon: "♫" },
    album: { text: "专辑档案", icon: "💿" },
    artist: { text: "人物志", icon: "🎵" },
};

function showLoading() {
    loading.classList.remove("hidden");
    result.classList.add("hidden");
    error.classList.add("hidden");
}

function processLines(text) {
    return text
        .split("\n")
        .map((line) => {
            const trimmed = line.trimStart();
            if (trimmed.startsWith("^ ")) {
                const indent = line.length - trimmed.length;
                return " ".repeat(indent) + '<span class="lyric-tr">' + trimmed.slice(2) + "</span>";
            }
            return line;
        })
        .join("\n");
}

const recommendations = document.getElementById("recommendations");
const recList = document.getElementById("recList");
const shareBar = document.getElementById("shareBar");
const shareUrl = document.getElementById("shareUrl");
const shareCopyBtn = document.getElementById("shareCopyBtn");
const shareGenBtn = document.getElementById("shareGenBtn");
let lastResult = null;

function showResult(text, qtype) {
    loading.classList.add("hidden");
    error.classList.add("hidden");
    result.classList.remove("hidden");
    lastResult = { text, qtype };

    const splitIdx = text.indexOf("<!-- split -->");
    if (splitIdx > -1) {
        const lyricsMd = text.slice(0, splitIdx).trim();
        const analysisMd = text.slice(splitIdx + "<!-- split -->".length).trim();
        resultContent.innerHTML =
            '<div class="result-inner">' +
            '<div class="lyrics-card">' + marked.parse(processLines(lyricsMd)) + '</div>' +
            '<div class="analysis-section">' + marked.parse(processLines(analysisMd)) + '</div>' +
            '</div>';
    } else {
        resultContent.innerHTML = '<div class="result-inner">' + marked.parse(processLines(text)) + '</div>';
    }

    const info = MODE_LABELS[qtype] || { text: "查询", icon: "" };
    modeBadge.textContent = info.icon + " " + info.text;
    modeBadge.classList.remove("hidden");

    // Reset share bar for new search
    shareUrl.value = "";
    shareBar.classList.remove("hidden");
    shareCopyBtn.textContent = "复制链接";
    shareCopyBtn.style.display = "none";
    shareGenBtn.style.display = "";

    result.scrollIntoView({ behavior: "smooth", block: "start" });
}

function showRecommendations(recs) {
    if (!recs || recs.length === 0) {
        recommendations.classList.add("hidden");
        return;
    }
    recommendations.classList.remove("hidden");
    recList.innerHTML = recs
        .map((r) => {
            const label = r.artist ? `${r.track} <span class="rec-item-artist">${escapeHtml(r.artist)}</span>` : escapeHtml(r.track);
            return `<span class="rec-item" data-query="${escapeHtml(r.track + (r.artist ? ' ' + r.artist : ''))}">${label}</span>`;
        })
        .join("");

    recList.querySelectorAll(".rec-item").forEach((el) => {
        el.addEventListener("click", () => {
            input.value = el.dataset.query;
            search();
        });
    });
}

function showError(msg) {
    loading.classList.add("hidden");
    result.classList.add("hidden");
    error.classList.remove("hidden");
    error.textContent = msg;
}

async function search() {
    const query = input.value.trim();
    if (!query) return;

    showLoading();

    try {
        const res = await fetch("/api/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query }),
        });

        const data = await res.json();

        if (!res.ok) {
            showError(data.error || "请求失败");
            return;
        }

        showResult(data.result, data.type);
        showRecommendations(data.recommendations);
        addHistory(query);
    } catch (err) {
        showError(`网络错误: ${err.message}`);
    }
}

searchBtn.addEventListener("click", search);
input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") search();
    if (e.key === "Escape") {
        input.value = "";
        input.blur();
    }
});

// Global keyboard shortcuts
document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        input.focus();
        input.select();
    }
    if (e.key === "Escape" && document.activeElement === input) {
        input.value = "";
        input.blur();
    }
});

copyBtn.addEventListener("click", async () => {
    try {
        const text = resultContent.textContent;
        await navigator.clipboard.writeText(text);
        copyBtn.textContent = "已复制";
        setTimeout(() => (copyBtn.textContent = "复制"), 1500);
    } catch {
        copyBtn.textContent = "复制失败";
    }
});

// Share button
shareGenBtn.addEventListener("click", async () => {
    if (!lastResult) return;
    shareGenBtn.textContent = "生成中...";
    shareGenBtn.disabled = true;
    try {
        const res = await fetch("/api/share", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: lastResult.text, type: lastResult.qtype }),
        });
        const data = await res.json();
        if (data.url) {
            const full = window.location.origin + data.url;
            shareUrl.value = full;
            shareCopyBtn.style.display = "";
            shareGenBtn.style.display = "none";
            shareUrl.select();
        }
    } catch (err) {
        shareGenBtn.textContent = "生成失败";
    } finally {
        shareGenBtn.disabled = false;
        if (shareGenBtn.textContent === "生成中...") shareGenBtn.textContent = "生成分享链接";
    }
});

shareCopyBtn.addEventListener("click", async () => {
    try {
        await navigator.clipboard.writeText(shareUrl.value);
        shareCopyBtn.textContent = "已复制";
        setTimeout(() => (shareCopyBtn.textContent = "复制链接"), 1500);
    } catch {
        shareCopyBtn.textContent = "复制失败";
    }
});
