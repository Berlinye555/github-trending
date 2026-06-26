#!/usr/bin/env bash
# GitHub Trending Repos Collector
# 根据 Alpha矿长 的兴趣方向定时搜索最新热门项目

set -eu
set -o pipefail

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
    "https://api.github.com/search/repositories?q=${encoded}&sort=stars&order=desc&per_page=5" 2>/dev/null) || true

  # DEBUG: 输出原始响应（仅首次调试用，后续可删除）
  echo "<!-- DEBUG ${label}: query=${encoded} -->"

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
  count=$(echo "$result" | grep -o '"total_count": *[0-9]*' | head -1 | grep -o '[0-9]*')

  if [ -z "$count" ] || [ "$count" = "0" ]; then
    echo "| - | 暂无匹配结果 | 换个关键词试试 | - | - |"
    echo ""
    return
  fi

  # 先整体清理：移掉所有 owner 嵌套对象（避免其 html_url 干扰匹配）
  local clean
  clean=$(echo "$result" | sed 's/"owner":{[^}]*},//g')

  # 逐 repo 按索引提取（每个 repo 的字段在全局中按相同顺序排列）
  local i=1
  while [ "$i" -le 5 ]; do
    local name star desc_text lang_text date_text link

    name=$(echo "$clean" | grep -o '"full_name": *"[^"]*"' | sed -n "${i}p" | sed 's/.*"full_name": *"//;s/"$//')
    [ -z "$name" ] && break

    star=$(echo "$clean" | grep -o '"stargazers_count": *[0-9]*' | sed -n "${i}p" | grep -o '[0-9]*')

    # description（可能是 "... " 或 null）
    desc_text=$(echo "$clean" | grep -o '"description": *\(null\|"[^"]*"\)' | sed -n "${i}p")
    if echo "$desc_text" | grep -q 'null'; then
      desc_text="-"
    else
      desc_text=$(echo "$desc_text" | sed 's/.*"description": *"//;s/"$//' | sed 's/\\n/ /g' | cut -c1-60)
    fi

    # language（可能是 "... " 或 null）
    lang_text=$(echo "$clean" | grep -o '"language": *\(null\|"[^"]*"\)' | sed -n "${i}p")
    if echo "$lang_text" | grep -q 'null'; then
      lang_text="-"
    else
      lang_text=$(echo "$lang_text" | sed 's/.*"language": *"//;s/"$//')
    fi

    date_text=$(echo "$clean" | grep -o '"updated_at": *"[^"]*"' | sed -n "${i}p" | grep -o '[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}' | head -1)
    link=$(echo "$clean" | grep -o '"html_url": *"[^"]*"' | sed -n "${i}p" | sed 's/.*"html_url": *"//;s/"$//')

    [ -z "$star" ] && star="-"
    [ -z "$desc_text" ] && desc_text="-"
    [ -z "$lang_text" ] && lang_text="-"
    [ -z "$date_text" ] && date_text="-"
    echo "| ${star} | [${name}](${link}) | ${desc_text} | ${lang_text} | ${date_text} |"

    i=$((i + 1))
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
