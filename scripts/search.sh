#!/usr/bin/env bash
# GitHub Trending Repos Collector
# 根据 Alpha矿长 的兴趣方向定时搜索最新热门项目

set -euo pipefail

TODAY=$(TZ='Asia/Shanghai' date +'%Y-%m-%d %H:%M')
STARS_THRESHOLD=20

cat <<EOF
# 🔥 GitHub 热门项目日报

> 更新时间：${TODAY} CST
> 搜索维度：AI 应用 · 量化交易 · 系统工具 · 本周新星

---

EOF

# ── 搜索函数 ──
search() {
  local label="$1"; shift
  local query="$*"

  echo "## ${label}"
  echo ""
  echo "| ⭐ | 项目 | 描述 | 语言 | 更新 |"
  echo "|---|---:|---|---|---|"

  gh search repos "${query}" \
    --sort stars \
    --limit 5 \
    --json name,fullName,description,language,stargazersCount,updatedAt,htmlUrl \
    --jq '.[] | "| \(.stargazersCount) | [\(.fullName)](\(.htmlUrl)) | \(.description // "-" | .[0:80]) | \(.language // "-") | \(.updatedAt[0:10]) |"' \
    2>/dev/null || echo "| - | 搜索失败 | 请检查 token 权限 | - | - |"

  echo ""
}

# ── 按用户兴趣维度搜索 ──

search "🤖 AI 应用开发" \
  "topic:machine-learning+language:python+pushed:>$(date -d '30 days ago' +%Y-%m-%d)+stars:>${STARS_THRESHOLD}"

search "🧠 LLM / Agent 框架" \
  "llm agent framework language:python+pushed:>$(date -d '30 days ago' +%Y-%m-%d)+stars:>${STARS_THRESHOLD}"

search "💹 量化交易 / 金融" \
  "topic:trading OR topic:finance language:python+pushed:>$(date -d '60 days ago' +%Y-%m-%d)+stars:>${STARS_THRESHOLD}"

search "🔧 CLI / 系统工具" \
  "topic:cli+topic:tool+pushed:>$(date -d '30 days ago' +%Y-%m-%d)+stars:>${STARS_THRESHOLD}"

search "🆕 本周新星（<7天）" \
  "created:>$(date -d '7 days ago' +%Y-%m-%d)+stars:>10"

search "🔥 本月热门（中文）" \
  "language:chinese+pushed:>$(date -d '30 days ago' +%Y-%m-%d)+stars:>${STARS_THRESHOLD}"

cat <<EOF

---

> 🤖 由 [GitHub Actions](https://github.com/${GITHUB_REPOSITORY}/actions) 每日自动更新
> 📡 数据来源：[GitHub Search API](https://docs.github.com/en/rest/search)
EOF
