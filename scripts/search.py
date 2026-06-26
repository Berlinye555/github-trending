#!/usr/bin/env python3
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


def now_shanghai() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")


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
    text = sanitize_text(value)
    return text.replace("|", "\\|")


def fetch_search(query: str) -> dict:
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://api.github.com/search/repositories?q={encoded_query}&sort=stars&order=desc&per_page=5"
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


# ── 描述生成（更精准的 fallback 规则） ──

def fallback_chinese_description(full_name: str, description: str | None, language: str | None, topics: list[str] | None = None) -> str:
    """根据仓库元数据生成中文描述，规则更细化"""
    original = sanitize_text(description)
    lang = sanitize_text(language)
    name_lower = (full_name or "").lower()
    topics_lower = [t.lower() for t in (topics or [])]

    def has_keyword(*words: str) -> bool:
        target = f"{original.lower()} {name_lower} {' '.join(topics_lower)}"
        return any(w in target for w in words)

    # 有中文描述直接复用
    if original != "-" and re.search(r"[一-鿿]", original):
        return original

    # 按优先级匹配
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
    """AI 改写描述（优化 prompt，要求更具体）"""
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


def format_repo_row(repo: dict) -> str:
    name = repo.get("full_name") or "-"
    stars = repo.get("stargazers_count")
    description = rewrite_description(
        name,
        repo.get("description"),
        repo.get("language"),
        repo.get("topics"),
    )
    language = repo.get("language") or "-"
    updated_at = (repo.get("updated_at") or "").split("T")[0] if repo.get("updated_at") else "-"

    description = escape_markdown(description)[:80]
    language = escape_markdown(language)

    link = f"https://github.com/{name}"
    return f"| {stars if stars is not None else '-'} | [{name}]({link}) | {description} | {language} | {updated_at} |"


def render_section(label: str, query: str, seen: set[str] | None = None) -> tuple[str, int, int]:
    """返回 (markdown文本, 显示项目数, 搜索结果总数)"""
    lines = []
    lines.append(f"### {label}")
    lines.append("")
    lines.append("| ⭐ | 项目链接 | 描述 | 语言 | 更新 |")
    lines.append("|---:|---|---|---|---|")

    result = fetch_search(query)
    total_count = result.get("total_count", 0)

    if result.get("status") == 403 or (isinstance(result.get("error"), str) and "rate limit" in str(result.get("error")).lower()):
        lines.append("| - | ⚠️ API 限流 | 请稍后重试，保留上期数据 | - | - |")
        lines.append("")
        return "\n".join(lines), 0, total_count

    if result.get("status") == 422 or (isinstance(result.get("error"), str) and "Validation Failed" in str(result.get("error")).lower()):
        message = str(result.get("error", ""))
        detail = sanitize_text(message)[:50]
        lines.append(f"| - | ⚠️ 查询语法错误 | {detail} | - | - |")
        lines.append("")
        return "\n".join(lines), 0, total_count

    if result.get("status") not in {200, None} and not result.get("items"):
        lines.append("| - | ⚠️ 请求失败 | 请检查网络或 GitHub API 状态 | - | - |")
        lines.append("")
        return "\n".join(lines), 0, total_count

    items = result.get("items") or []
    if not items or total_count == 0:
        lines.append("| - | 暂无匹配结果 | 尝试放宽搜索条件 | - | - |")
        lines.append("")
        return "\n".join(lines), 0, total_count

    displayed = 0
    for repo in items[:5]:
        name = repo.get("full_name")
        if name and seen is not None:
            if name in seen:
                continue
            seen.add(name)

        lines.append(format_repo_row(repo))
        displayed += 1

    if displayed == 0:
        lines.append("| - | 全部与前面重复 | 已在上方分类展示 | - | - |")

    lines.append("")
    return "\n".join(lines), displayed, total_count


def build_report(manual_params: dict | None = None) -> tuple[str, dict]:
    """生成完整日报，返回 (markdown, 统计摘要)"""
    today = now_shanghai()
    seven_days = days_ago(7)
    thirty_days = days_ago(30)
    sixty_days = days_ago(60)

    sections = [
        (
            "🤖 AI / Agent 项目",
            f"ai agent OR llm framework language:python pushed:>{thirty_days} stars:>50",
            "ai agent OR llm framework",
            ">50",
            "30天",
        ),
        (
            "💹 量化交易与金融",
            f"trading OR finance OR quant language:python NOT awesome pushed:>{sixty_days} stars:>10",
            "trading OR finance OR quant",
            ">10",
            "60天",
        ),
        (
            "🛠️ 开发者工具",
            f"cli OR dev tool language:python NOT awesome pushed:>{thirty_days} stars:>20",
            "cli OR dev tool",
            ">20",
            "30天",
        ),
        (
            "🆕 本月新星",
            f"created:>{thirty_days} stars:>3",
            "created:>30d",
            ">3",
            "30天",
        ),
        (
            "🌏 中文项目热点",
            f"人工智能 OR 开源项目 OR 大模型 pushed:>{thirty_days} stars:>20",
            "人工智能 OR 开源项目 OR 大模型",
            ">20",
            "30天",
        ),
    ]

    # 支持手动指定分类覆盖
    if manual_params:
        override_sections = []
        for label, query, _, _, _ in sections:
            if manual_params.get("category") and manual_params["category"] != label:
                override_sections.append((label, query, query, "-", "-"))
            else:
                new_query = manual_params.get("query", query)
                override_sections.append((label, new_query, new_query, "-", "-"))
        sections = override_sections

    output = [
        "# 🔥 GitHub 热门项目日报",
        "",
        f"> 更新时间：{today} CST",
        "> 关注方向：AI / Agent · 量化交易 · 开发者工具 · 本月新星 · 中文热点",
        f"> 时间范围：{seven_days} ~ {today}",
        "",
        "## 📋 项目总览",
        "",
        "| 分类 | 说明 | 搜索关键词 | Stars | 时间 |",
        "|------|------|-----------|-------|------|",
        "| 🤖 AI / Agent 项目 | AI 应用与 LLM 框架全覆盖 | ai agent OR llm framework | >50 | 30天 |",
        "| 💹 量化交易与金融 | 量化策略、金融数据、回测 | trading OR finance OR quant | >10 | 60天 |",
        "| 🛠️ 开发者工具 | CLI、效率工具、开发辅助 | cli OR dev tool | >20 | 30天 |",
        "| 🆕 本月新星 | 30天内新创建的高潜项目 | created:>30d | >3 | 30天 |",
        "| 🌏 中文项目热点 | 中文社区高热项目 | 人工智能 OR 开源项目 OR 大模型 | >20 | 30天 |",
        "",
        "---",
        "",
    ]

    stats = {"categories": {}, "total_projects": 0}
    seen: set[str] = set()

    for label, query, _, _, _ in sections:
        md, displayed, total = render_section(label, query, seen)
        output.append(md)
        stats["categories"][label] = {"displayed": displayed, "totalResults": total}
        stats["total_projects"] += displayed

    repo_full = os.getenv("GITHUB_REPOSITORY", "your-org/your-repo")
    output.append("---")
    output.append("")
    output.append(f"> 🤖 由 [GitHub Actions](https://github.com/{repo_full}/actions) 每日自动更新")
    output.append("> 📡 数据来源：[GitHub Search API](https://docs.github.com/en/rest/search)")

    return "\n".join(output), stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", help="Optional output file path")
    parser.add_argument("--category", help="指定更新某个分类")
    parser.add_argument("--query", help="自定义搜索关键词")
    parser.add_argument("--changeset", help="输出变更摘要文件路径")
    args = parser.parse_args()

    manual = None
    if args.category or args.query:
        manual = {"category": args.category, "query": args.query}

    report, stats = build_report(manual)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(report)
            handle.write("\n")
    else:
        if hasattr(sys.stdout, "buffer"):
            sys.stdout.buffer.write(report.encode("utf-8"))
        else:
            sys.stdout.write(report)

    # 写入变更摘要供 workflow commit message 使用
    summary_path = args.changeset or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".changeset.json"
    )
    try:
        os.makedirs(os.path.dirname(summary_path), exist_ok=True)
        summary = {
            "total": stats["total_projects"],
            "categories": {
                k: v["displayed"] for k, v in stats["categories"].items()
            },
            "timestamp": now_shanghai(),
        }
        with open(summary_path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 摘要写入失败不影响主流程

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
