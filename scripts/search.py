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


def fallback_chinese_description(name: str, description: str | None, language: str | None) -> str:
    original = sanitize_text(description)
    if original != "-":
        lowered = original.lower()
        if not re.search(r"[\u4e00-\u9fff]", original):
            if "agent" in lowered:
                return f"面向智能体与自动化场景的{sanitize_text(language) or '项目'}"
            if "framework" in lowered:
                return f"提供{sanitize_text(language) or '开发'}框架能力的项目"
            if "tool" in lowered:
                return f"实用的{sanitize_text(language) or '开发'}工具项目"
            if "trading" in lowered or "finance" in lowered or "quant" in lowered:
                return f"面向量化与金融分析的{sanitize_text(language) or '项目'}"
            if "api" in lowered:
                return f"提供接口与数据能力的{sanitize_text(language) or '项目'}"
            if "llm" in lowered or "model" in lowered:
                return f"围绕大模型与 AI 能力的{sanitize_text(language) or '项目'}"
            return f"{sanitize_text(language) or '开源'}项目"
        return original

    return f"{sanitize_text(language) or '开源'}项目"


def rewrite_description(name: str, description: str | None, language: str | None) -> str:
    original = sanitize_text(description)
    if original == "-":
        return "-"
    if os.getenv("ENABLE_AI_DESCRIPTION_REWRITE", "").lower() not in {"1", "true", "yes", "on"}:
        return fallback_chinese_description(name, original, language)
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return fallback_chinese_description(name, original, language)

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You rewrite GitHub repository descriptions for a README table. Keep it short, polished, and factual. Return only one concise sentence in Chinese.",
            },
            {
                "role": "user",
                "content": f"Repository: {name}\nLanguage: {sanitize_text(language)}\nOriginal description: {original}",
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
            return cleaned[:80] if cleaned else fallback_chinese_description(name, original, language)
    except Exception:
        return fallback_chinese_description(name, original, language)


def format_repo_row(repo: dict) -> str:
    name = repo.get("full_name") or "-"
    stars = repo.get("stargazers_count")
    description = rewrite_description(name, repo.get("description"), repo.get("language"))
    language = repo.get("language") or "-"
    updated_at = (repo.get("updated_at") or "").split("T")[0] if repo.get("updated_at") else "-"

    description = escape_markdown(description)[:80]
    language = escape_markdown(language)

    link = f"https://github.com/{name}"
    return f"| {stars if stars is not None else '-'} | [{name}]({link}) | {description} | {language} | {updated_at} |"


def render_section(label: str, query: str) -> str:
    lines = []
    lines.append(f"## {label}")
    lines.append("")
    lines.append("| ⭐ | 项目链接 | 描述 | 语言 | 更新 |")
    lines.append("|---|---:|---|---|---|")
    lines.append(f"<!-- DEBUG {label}: query={urllib.parse.quote_plus(query)} -->")

    result = fetch_search(query)
    if result.get("status") == 403 or isinstance(result.get("error"), str) and "rate limit" in str(result.get("error")).lower():
        lines.append("| - | ⚠️ API 限流 | 请稍后重试 | - | - |")
        lines.append("")
        return "\n".join(lines)

    if result.get("status") == 422 or isinstance(result.get("error"), str) and "Validation Failed" in str(result.get("error")).lower():
        message = str(result.get("error", ""))
        detail = message[:50]
        lines.append(f"| - | ⚠️ 查询语法错误 | {detail} | - | - |")
        lines.append("")
        return "\n".join(lines)

    if result.get("status") not in {200, None} and not result.get("items"):
        lines.append("| - | ⚠️ 请求失败 | 请检查网络或 GitHub API | - | - |")
        lines.append("")
        return "\n".join(lines)

    items = result.get("items") or []
    total_count = result.get("total_count", 0)
    if not items or total_count == 0:
        lines.append("| - | 暂无匹配结果 | 换个关键词试试 | - | - |")
        lines.append("")
        return "\n".join(lines)

    for repo in items[:5]:
        lines.append(format_repo_row(repo))

    lines.append("")
    return "\n".join(lines)


def build_report() -> str:
    today = now_shanghai()
    sections = [
        ("✅ 连通性测试", "stars:>1000 language:python"),
        ("🤖 AI 应用开发", f"ai agent language:python pushed:>{days_ago(30)} stars:>20"),
        ("🧠 LLM / Agent 框架", f"llm OR agent framework language:python pushed:>{days_ago(30)} stars:>50"),
        ("💹 量化交易 / 金融", f"trading OR finance OR quant language:python pushed:>{days_ago(60)} stars:>10"),
        ("🔧 CLI / 系统工具", f"cli OR tool language:python pushed:>{days_ago(30)} stars:>20"),
        ("🆕 本周新星", f"created:>{days_ago(7)}"),
        ("🔥 本月热门（中文）", f"pushed:>{days_ago(30)} stars:>20"),
    ]

    output = [
        "# 🔥 GitHub 热门项目日报",
        "",
        f"> 更新时间：{today} CST",
        "> 搜索维度：AI 应用 · 量化交易 · 系统工具 · 本周新星",
        "",
        "---",
        "",
    ]

    for label, query in sections:
        output.append(render_section(label, query))

    output.append("---")
    output.append("")
    output.append("> 🤖 由 [GitHub Actions](https://github.com/{}/actions) 每日自动更新".format(os.getenv("GITHUB_REPOSITORY", "your-org/your-repo")))
    output.append("> 📡 数据来源：[GitHub Search API](https://docs.github.com/en/rest/search)")
    return "\n".join(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", help="Optional output file path")
    args = parser.parse_args()

    report = build_report()
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(report)
            handle.write("\n")
    else:
        if hasattr(sys.stdout, "buffer"):
            sys.stdout.buffer.write(report.encode("utf-8"))
        else:
            sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
