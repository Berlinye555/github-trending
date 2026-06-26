#!/usr/bin/env python3
"""GitHub 热门项目日报 —— 增量追加模式。

数据存储在 scripts/repos.json，每次运行搜索新项目追加到已有列表，
避免覆盖历史数据。README.md 由 repos.json 渲染生成。
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

TOKEN = os.getenv("GITHUB_TOKEN", "")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "repos.json")


# ── 工具函数 ──

def now_shanghai() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")


def today_str() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def days_ago(days: int) -> str:
    return (datetime.now().date() - timedelta(days=days)).strftime("%Y-%m-%d")


def sanitize_text(value: str | None) -> str:
    if not value:
        return "-"
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)
    text = text.replace("�", "")
    return text.strip()


def escape_markdown(value: str | None) -> str:
    return sanitize_text(value).replace("|", "\\|")


def fetch_search(query: str) -> dict:
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://api.github.com/search/repositories?q={encoded_query}&sort=stars&order=desc&per_page=30"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "workflows-trending/1.0",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"error": body, "status": exc.code}
    except urllib.error.URLError as exc:
        return {"error": str(exc.reason), "status": None}


# ── 描述生成 ──

def fallback_chinese_description(full_name: str, description: str | None, language: str | None, topics: list[str] | None = None) -> str:
    original = sanitize_text(description)
    lang = sanitize_text(language)
    name_lower = (full_name or "").lower()
    topics_lower = [t.lower() for t in (topics or [])]

    def has_keyword(*words: str) -> bool:
        target = f"{original.lower()} {name_lower} {' '.join(topics_lower)}"
        return any(w in target for w in words)

    if original != "-" and re.search(r"[一-鿿]", original):
        return original

    if has_keyword("browser", "web automation", "playwright", "selenium", "puppeteer"):
        return f"浏览器自动化与 Web 交互{lang}工具"
    if has_keyword("trading agent", "tradingagent", "stock agent"):
        return f"LLM 驱动的智能交易 Agent ——{lang}项目"
    if has_keyword("langchain", "langgraph", "langflow"):
        return f"LLM 应用编排与工作流{lang}框架"
    if has_keyword("agent framework", "multi-agent", "agent orchestration"):
        return f"多智能体协作与编排{lang}框架"
    if has_keyword("ai agent", "agentic", "agent "):
        return f"AI 智能体自动化{lang}应用"
    if has_keyword("llm", "large language model", "gpt"):
        return f"大语言模型{lang}工具与框架"
    if has_keyword("rag", "retrieval augmented"):
        return f"RAG 检索增强生成{lang}方案"
    if has_keyword("transformers", "huggingface"):
        return f"预训练模型与{lang}深度学习框架"
    if has_keyword("inference", "vllm", "tgi", "triton"):
        return f"LLM 推理加速与部署{lang}工具"
    if has_keyword("fine-tune", "fine tune", "lora", "qlora"):
        return f"大模型微调与训练{lang}工具"
    if has_keyword("vector database", "embedding", "vector search"):
        return f"向量数据库与嵌入{lang}方案"
    if has_keyword("quantitative", "backtest", "backtrader", "vnpy", "zipline"):
        return f"量化交易回测与策略{lang}框架"
    if has_keyword("freqtrade", "ccxt", "binance", "crypto trading"):
        return f"加密货币自动化交易{lang}工具"
    if has_keyword("openbb", "financial data", "stock analysis", "market data"):
        return f"金融市场数据分析{lang}平台"
    if has_keyword("cli tool", "command line", "tui", "terminal"):
        return f"命令行终端{lang}效率工具"
    if has_keyword("dev tool", "developer tool", "developer experience"):
        return f"开发者{lang}效率工具"
    if has_keyword("package manager", "dependency", "build tool"):
        return f"{lang}包管理与构建工具"
    if has_keyword("monitor", "observability", "logging", "tracing"):
        return f"系统监控与可观测性{lang}工具"
    if has_keyword("api", "rest", "graphql", "openapi"):
        return f"API 开发与数据接口{lang}方案"
    if has_keyword("framework", "library"):
        return f"{lang}开发框架与库"
    if has_keyword("tool", "utility", "helper"):
        return f"{lang}实用工具"
    if has_keyword("awesome", "curated list", "awesome list"):
        return f"精选{lang}资源与学习清单"
    if has_keyword("book", "tutorial", "guide", "handbook", "course"):
        return f"{lang}学习教程与指南"
    if has_keyword("markdown"):
        return f"Markdown 文档与资源"
    if has_keyword("model", "deep learning", "neural", "machine learning"):
        return f"深度学习与{lang}模型项目"

    return f"{lang}项目"


def rewrite_description(full_name: str, description: str | None, language: str | None, topics: list[str] | None = None) -> str:
    original = sanitize_text(description)
    if original == "-":
        return "-"

    if os.getenv("ENABLE_AI_DESCRIPTION_REWRITE", "").lower() not in {"1", "true", "yes", "on"}:
        return fallback_chinese_description(full_name, original, language, topics)

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return fallback_chinese_description(full_name, original, language, topics)

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是 GitHub 项目描述编辑。用一句中文概括项目核心功能和独特价值。"
                    "要求：20字以内、具体突出项目特色、避免泛泛而谈。"
                    "不要用'围绕XX场景'这种套话，直接说清楚这个项目做什么。"
                ),
            },
            {
                "role": "user",
                "content": f"项目名：{full_name}\n语言：{sanitize_text(language)}\n原描述：{original}",
            },
        ],
        "temperature": 0.2,
    }

    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "workflows-trending/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            cleaned = sanitize_text(content)
            return cleaned[:80] if cleaned else fallback_chinese_description(full_name, original, language, topics)
    except Exception:
        return fallback_chinese_description(full_name, original, language, topics)


# ── 数据持久层 ──

def load_repos_db() -> dict:
    """加载 repos.json 数据库"""
    if not os.path.exists(DB_PATH):
        return {"updated": "", "categories": {}}
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"updated": "", "categories": {}}


def save_repos_db(data: dict) -> None:
    """保存 repos.json 数据库"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_existing_names(db: dict) -> set[str]:
    """从数据库中提取所有已收录的 full_name"""
    names: set[str] = set()
    for entries in db.get("categories", {}).values():
        for entry in entries:
            if isinstance(entry, dict) and entry.get("full_name"):
                names.add(entry["full_name"])
    return names


# ── 相关性过滤 ──

def is_relevant(label: str, full_name: str, description: str | None, topics: list[str] | None) -> bool:
    """检查项目是否与分类相关，过滤 GitHub 搜索的噪音结果"""
    text = f"{full_name or ''} {description or ''} {' '.join(topics or [])}".lower()

    if "AI / Agent" in label:
        strong = ["llm", "langchain", "autogen", "chatgpt", "rag",
                  "copilot", "chatbot", "crewai", "haystack",
                  "agentic", "multi-agent", "openai", "gpt-",
                  "ai-", "ai.", "gpt "]
        weak = ["ai ", "agent"]
        has_strong = any(w in text for w in strong)
        has_weak = sum(1 for w in weak if w in text)
        return has_strong or has_weak >= 2
    if "量化" in label:
        strong = ["trading", "backtest", "freqtrade", "openbb",
                  "crypto trading", "cryptocurrency", "exchange",
                  "binance", "stock market", "broker", "quantitative",
                  "algorithmic trading", "fintech"]
        weak = ["quant", "finance", "stock", "trade", "crypto",
                "invest", "market", "option"]
        has_strong = any(w in text for w in strong)
        has_weak = sum(1 for w in weak if w in text)
        return has_strong or has_weak >= 2
    if "开发者工具" in label:
        strong = ["cli ", "cli/", "-cli", "devtool", "terminal", "tui",
                  "command-line", "command line", "debug", "workflow",
                  "pipeline", "warp ", "curl", "zsh", "bash"]
        weak = ["tool", "dev ", "utility", "automation", "plugin"]
        has_strong = any(w in text for w in strong)
        has_weak = sum(1 for w in weak if w in text)
        return has_strong or has_weak >= 2
    if "中文" in label:
        return bool(re.search(r"[一-鿿]", text))

    return True


def repo_to_entry(repo: dict) -> dict:
    """将 API 返回的 repo 对象转为存储条目"""
    name = repo.get("full_name") or "-"
    return {
        "full_name": name,
        "stars": repo.get("stargazers_count", 0) or 0,
        "description": rewrite_description(
            name, repo.get("description"), repo.get("language"), repo.get("topics"),
        ),
        "language": repo.get("language") or "-",
        "updated_at": (repo.get("updated_at") or "").split("T")[0] if repo.get("updated_at") else "-",
        "added": today_str(),
    }


# ── 搜索与增量更新 ──

SECTION_DEFS = [
    (
        "\U0001f916 AI / Agent 项目",
        "ai agent OR llm framework",
        ">10",
        "不限",
    ),
    (
        "\U0001f30f 中文项目热点",
        "人工智能 OR 开源项目 OR 大模型 OR 智能",
        ">5",
        "不限",
    ),
    (
        "\U0001f4f9 量化交易与金融",
        "trading OR finance OR quant",
        ">5",
        "不限",
    ),
    (
        "\U0001f6e0️ 开发者工具",
        "cli OR dev tool",
        ">10",
        "不限",
    ),
]


def search_and_append(db: dict) -> dict:
    """搜索 API 并将新项目追加到数据库，返回新增统计"""
    stats: dict[str, int] = {}
    existing = get_existing_names(db)

    for label, base_query, stars_threshold, _time_label in SECTION_DEFS:
        query = f"{base_query} stars:{stars_threshold}"

        result = fetch_search(query)
        items = result.get("items") or []
        if not items:
            stats[label] = 0
            continue

        # 确保分类存在
        if label not in db.setdefault("categories", {}):
            db["categories"][label] = []

        category_list: list = db["categories"][label]
        new_count = 0

        for repo in items:
            name = repo.get("full_name")
            if not name:
                continue
            if name in existing:
                continue
            # 同一分类内避免重复
            if any(e.get("full_name") == name for e in category_list):
                continue

            # 相关性过滤：剔除搜索噪音
            if not is_relevant(label, name, repo.get("description"), repo.get("topics")):
                continue

            entry = repo_to_entry(repo)
            category_list.append(entry)
            existing.add(name)
            new_count += 1

        stats[label] = new_count

    db["updated"] = now_shanghai()
    return stats


# ── README 渲染 ──

def format_row(entry: dict) -> str:
    stars = entry.get("stars", "-")
    name = entry.get("full_name", "-")
    desc = escape_markdown(entry.get("description", "-"))[:80]
    lang = escape_markdown(entry.get("language", "-"))
    updated = entry.get("updated_at") or (entry.get("added", ""))
    link = f"https://github.com/{name}"
    return f"| {stars} | [{name}]({link}) | {desc} | {lang} | {updated} |"


def render_readme(db: dict) -> str:
    """从数据库渲染完整 README.md"""
    today = now_shanghai()
    cats = db.get("categories", {})

    # 预定义各分类名称（避免 f-string 内反斜杠问题）
    L_AI = "\U0001f916 AI / Agent 项目"
    L_ZH = "\U0001f30f 中文项目热点"
    L_TRADE = "\U0001f4f9 量化交易与金融"
    L_TOOL = "\U0001f6e0️ 开发者工具"

    lines = [
        "# \U0001f525 GitHub 热门项目日报",
        "",
        f"> \U0001f552 更新：{today} CST  |  AI / Agent · 中文热点 · 量化交易 · 开发者工具  |  按 Stars 排序",
        "",
        "## \U0001f4cb 项目总览",
        "",
        "| 分类 | 说明 | 搜索关键词 | Stars | 时间 | 已收录 |",
        "|------|------|-----------|-------|------|------|",
        f"| {L_AI} | AI 应用与 LLM 框架全覆盖 | ai agent OR llm framework | >10 | 不限 | {len(cats.get(L_AI, []))} |",
        f"| {L_ZH} | 中文社区高热项目 | 人工智能 OR 开源项目 OR 大模型 OR 智能 | >5 | 不限 | {len(cats.get(L_ZH, []))} |",
        f"| {L_TRADE} | 量化策略、金融数据、回测 | trading OR finance OR quant | >5 | 不限 | {len(cats.get(L_TRADE, []))} |",
        f"| {L_TOOL} | CLI、效率工具、开发辅助 | cli OR dev tool | >10 | 不限 | {len(cats.get(L_TOOL, []))} |",
        "",
        "---",
        "",
    ]

    for label, _query, _stars, _time in SECTION_DEFS:
        lines.append(f"### {label}")
        lines.append("")
        lines.append("| ⭐ | 项目链接 | 描述 | 语言 | 更新 |")
        lines.append("|---:|---|---|---|---|")

        entries = db.get("categories", {}).get(label, [])
        if not entries:
            lines.append("| - | 暂无 | 等待下次更新 | - | - |")
        else:
            for entry in entries:
                lines.append(format_row(entry))

        lines.append("")

    repo_full = os.getenv("GITHUB_REPOSITORY", "your-org/your-repo")
    lines.append("---")
    lines.append("")
    lines.append(f"> \U0001f916 每日自动更新 · 数据来源 [GitHub Search API](https://docs.github.com/en/rest/search)")

    return "\n".join(lines)


# ── 主入口 ──

def main() -> int:
    parser = argparse.ArgumentParser(description="GitHub 热门项目日报 —— 增量追加模式")
    parser.add_argument("output", nargs="?", help="输出文件路径（默认 README.md）")
    parser.add_argument("--changeset", help="变更摘要文件路径")
    args = parser.parse_args()

    # 1) 加载数据库
    db = load_repos_db()

    # 2) 搜索并增量追加
    stats = search_and_append(db)

    # 3) 保存数据库
    save_repos_db(db)

    # 4) 渲染 README
    report = render_readme(db)

    output_path = args.output or "README.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
        f.write("\n")

    # 5) 变更摘要
    total_new = sum(stats.values())
    summary_path = args.changeset or os.path.join(SCRIPT_DIR, ".changeset.json")
    try:
        summary = {
            "new_total": total_new,
            "categories": stats,
            "db_total": sum(
                len(v) for v in db.get("categories", {}).values()
            ),
            "timestamp": now_shanghai(),
        }
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    print(f"[OK] {total_new} new repos added, {summary.get('db_total', 0)} total in database")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
