#!/usr/bin/env bash
# GitHub Trending Repos Collector
# 根据 Alpha矿长 的兴趣方向定时搜索最新热门项目

set -euo pipefail

TODAY=$(TZ='Asia/Shanghai' date +'%Y-%m-%d %H:%M')
STARS_THRESHOLD=20
TOKEN="${GITHUB_TOKEN:-}"

cat <<EOF
# 🔥 GitHub 热门项目日报

> 更新时间：${TODAY} CST
> 搜索维度：AI 应用 · 量化交易 · 系统工具 · 本周新星

---

EOF

# ── 搜索函数（直接调 GitHub REST API） ──
search() {
  local label="$1"; shift
  local query="$*"

  echo "## ${label}"
  echo ""
  echo "| ⭐ | 项目 | 描述 | 语言 | 更新 |"
  echo "|---|---:|---|---|---|"

  # URL 编码空格和特殊字符
  local encoded
  encoded=$(echo "$query" | sed 's/ /%20/g;s/:/%3A/g;s/>/%3E/g;s/</%3C/g;s/(/%28/g;s/)/%29/g')

  local result
  result=$(curl -s -H "Authorization: Bearer ${TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/search/repositories?q=${encoded}&sort=stars&order=desc&per_page=5" 2>/dev/null)

  # DEBUG: 输出原始响应（仅首次调试用，后续可删除）
  echo "<!-- DEBUG ${label}: total=$(echo "$result" | grep -o '"total_count":[0-9]*' | head -1) -->"

  # 检查是否被限流
  if echo "$result" | grep -q '"message".*"API rate limit"'; then
    echo "| - | ⚠️ API 限流 | 请稍后重试 | - | - |"
    echo ""
    return
  fi

  # 检查是否有错误
  if echo "$result" | grep -q '"message":"Validation Failed"'; then
    echo "| - | ⚠️ 查询语法错误 | $(echo "$result" | grep -o '"message":"[^"]*"' | head -1 | sed 's/.*"message":"//;s/"//' | cut -c1-50) | - | - |"
    echo ""
    return
  fi

  # 解析 JSON 输出表格行（不依赖 jq）
  local count
  count=$(echo "$result" | grep -o '"total_count":[0-9]*' | head -1 | grep -o '[0-9]*')

  if [ -z "$count" ] || [ "$count" = "0" ]; then
    echo "| - | 暂无匹配结果 | 换个关键词试试 | - | - |"
    echo ""
    return
  fi

  # 提取每个 repo 的字段
  echo "$result" | grep -o '"full_name":"[^"]*"\|"stargazers_count":[0-9]*\|"description":"[^"]*"\|"language":"[^"]*"\|"updated_at":"[^"]*"\|"html_url":"[^"]*"' \
    | paste - - - - - - 2>/dev/null \
    | head -5 \
    | while IFS=$'\t' read -r full_name stars desc lang updated url; do
      local name star desc_text lang_text date_text link
      name=$(echo "$full_name" | sed 's/.*"full_name":"\([^"]*\)".*/\1/')
      star=$(echo "$stars" | grep -o '[0-9]*')
      desc_text=$(echo "$desc" | sed 's/.*"description":"\([^"]*\)".*/\1/' | sed 's/\\n/ /g' | cut -c1-60)
      lang_text=$(echo "$lang" | sed 's/.*"language":"\([^"]*\)".*/\1/')
      date_text=$(echo "$updated" | grep -o '[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}' | head -1)
      link=$(echo "$url" | sed 's/.*"html_url":"\([^"]*\)".*/\1/')
      [ -z "$desc_text" ] && desc_text="-"
      [ -z "$lang_text" ] && lang_text="-"
      echo "| ${star} | [${name}](${link}) | ${desc_text} | ${lang_text} | ${date_text} |"
    done

  echo ""
}

# ── 按用户兴趣维度搜索 ──

# 先用一个简单查询验证 API 工作正常
search "✅ 连通性测试" \
  "stars:>1000 language:python"

search "🤖 AI 应用开发" \
  "ai agent language:python pushed:>$(date -d '30 days ago' +%Y-%m-%d) stars:>${STARS_THRESHOLD}"

search "🧠 LLM / Agent 框架" \
  "llm OR agent framework language:python pushed:>$(date -d '30 days ago' +%Y-%m-%d) stars:>50"

search "💹 量化交易 / 金融" \
  "trading OR finance OR quant language:python pushed:>$(date -d '60 days ago' +%Y-%m-%d) stars:>10"

search "🔧 CLI / 系统工具" \
  "cli OR tool language:python pushed:>$(date -d '30 days ago' +%Y-%m-%d) stars:>${STARS_THRESHOLD}"

search "🆕 本周新星" \
  "created:>$(date -d '7 days ago' +%Y-%m-%d)"

search "🔥 本月热门（中文）" \
  "pushed:>$(date -d '30 days ago' +%Y-%m-%d) stars:>${STARS_THRESHOLD}"

cat <<EOF

---

> 🤖 由 [GitHub Actions](https://github.com/${GITHUB_REPOSITORY}/actions) 每日自动更新
> 📡 数据来源：[GitHub Search API](https://docs.github.com/en/rest/search)
EOF
