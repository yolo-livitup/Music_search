const input = document.getElementById("queryInput");
const searchBtn = document.getElementById("searchBtn");
const loading = document.getElementById("loading");
const result = document.getElementById("result");
const resultContent = document.getElementById("resultContent");
const error = document.getElementById("error");
const copyBtn = document.getElementById("copyBtn");

function showLoading() {
    loading.classList.remove("hidden");
    result.classList.add("hidden");
    error.classList.add("hidden");
}

function showResult(text) {
    loading.classList.add("hidden");
    error.classList.add("hidden");
    result.classList.remove("hidden");
    resultContent.textContent = text;
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

        showResult(data.result);
    } catch (err) {
        showError(`网络错误: ${err.message}`);
    }
}

searchBtn.addEventListener("click", search);
input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") search();
});

copyBtn.addEventListener("click", async () => {
    try {
        await navigator.clipboard.writeText(resultContent.textContent);
        copyBtn.textContent = "已复制";
        setTimeout(() => (copyBtn.textContent = "复制"), 1500);
    } catch {
        copyBtn.textContent = "复制失败";
    }
});
