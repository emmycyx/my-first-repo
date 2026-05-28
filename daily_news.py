#!/usr/bin/env python3
"""
每日AI&DC新闻 — 自动抓取、整理并推送到微信（Server酱）
支持 GitHub Actions 定时运行

用法:
  python daily_news.py --newsapi-key KEY --sendkey KEY
  python daily_news.py --newsapi-key KEY --sendkey KEY --date 2026-05-27
  python daily_news.py --newsapi-key KEY --sendkey KEY --dry-run   # 只生成不发送
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Any

# ─── 配置 ────────────────────────────────────────────────────────────────

NEWSAPI_URL = "https://newsapi.org/v2/everything"
SERVERCHAN_URL = "https://sctapi.ftqq.com/{sendkey}.send"
UTC8 = timezone(timedelta(hours=8))

SEARCH_QUERIES = [
    ("AI data center infrastructure investment", "en"),
    ("AI chip NVIDIA AMD semiconductor", "en"),
    ("large language model GPT Claude Gemini", "en"),
    ("AI startup funding investment", "en"),
    ("artificial intelligence regulation policy", "en"),
    ("AI enterprise application", "en"),
    ("AI 数据中心 算力 基础设施", "zh"),
    ("AI 芯片 大模型 人工智能", "zh"),
    ("AI 融资 投资 startup", "zh"),
]

ARTICLES_PER_QUERY = 15
MAX_RESULTS = 20
ARCHIVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archive")


# ─── 日志 ────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    ts = datetime.now(UTC8).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stderr)


# ─── 新闻抓取 ────────────────────────────────────────────────────────────

def fetch_newsapi(api_key: str, query: str, lang: str, date_from: str) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({
        "q": query,
        "from": date_from,
        "sortBy": "publishedAt",
        "pageSize": ARTICLES_PER_QUERY,
        "language": lang,
        "apiKey": api_key,
    })
    url = f"{NEWSAPI_URL}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DailyAI/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") != "ok":
            log(f"  ⚠ API异常: {data.get('message', 'unknown')}")
            return []
        return data.get("articles", [])
    except urllib.error.HTTPError as e:
        log(f"  ⚠ HTTP {e.code}: {e.reason}")
        return []
    except Exception as e:
        log(f"  ⚠ 请求失败: {e}")
        return []


# ─── 去重 ────────────────────────────────────────────────────────────────

def dedup(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for a in articles:
        t = (a.get("title") or "").strip().lower()
        if not t:
            continue
        h = hashlib.md5(t.encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            result.append(a)
    return result


# ─── 分类 & 地区 ─────────────────────────────────────────────────────────

def classify(title: str, desc: str) -> str:
    text = f"{title} {desc or ''}".lower()
    rules = [
        ("AI基建投资", ["data center", "数据中心", "capex", "infrastructure", "服务器", "算力",
                        "hyperscaler", "cloud"]),
        ("AI芯片/算力", ["chip", "semiconductor", "nvidia", "amd", "tsmc", "芯片", "半导体",
                       "gpu", "hbm"]),
        ("大模型竞赛", ["llm", "gpt", "claude", "gemini", "openai", "anthropic", "大模型",
                     "transformer", "deepseek"]),
        ("投融资", ["funding", "startup", "融资", "投资", "估值", "round", "venture"]),
        ("政策监管", ["regulation", "policy", "governance", "监管", "政策", "法案", "合规"]),
        ("AI行业应用", ["enterprise", "application", "adopt", "industry", "应用", "落地",
                      "robot", "agent", "医疗", "金融", "制造"]),
    ]
    for category, keywords in rules:
        if any(k in text for k in keywords):
            return category
    return "AI行业动态"


def region_tag(title: str, desc: str) -> str:
    text = f"{title} {desc or ''}"
    cn = ["中国", "北京", "上海", "深圳", "华为", "百度", "阿里", "腾讯", "字节",
          "运营商", "工信部", "国家", "国内", "小米"]
    return "🇨🇳 国内" if any(k in text for k in cn) else "🌍 海外"


def truncate(text: str, max_len: int = 150) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] + "…" if len(text) > max_len else text


def safe_text(val: Any) -> str:
    return (val or "").strip()


# ─── 格式化器 ────────────────────────────────────────────────────────────

def build_markdown(articles: list[dict[str, Any]], date_str: str) -> str:
    lines = [f"# 📡 每日AI&DC新闻 · {date_str}\n"]
    current_cat = None
    order = ["AI基建投资", "AI芯片/算力", "大模型竞赛", "AI行业应用", "投融资", "政策监管", "AI行业动态"]

    def cat_sort_key(a: dict) -> int:
        try:
            return order.index(a["_category"])
        except ValueError:
            return 99

    sorted_articles = sorted(articles, key=cat_sort_key)

    for i, a in enumerate(sorted_articles, 1):
        cat = a.get("_category", "AI行业动态")
        region = a.get("_region", "")
        title = safe_text(a.get("title"))
        desc = truncate(safe_text(a.get("description")), 150)
        url = safe_text(a.get("url"))

        if cat != current_cat:
            current_cat = cat
            lines.append(f"\n---\n### {cat}\n")

        line_parts = [f"**{i}. {title}**"]
        if region:
            line_parts.append(f"  *{region}*")
        if desc:
            line_parts.append(f"  > {desc}")
        if url:
            line_parts.append(f"  [🔗 阅读原文]({url})")
        lines.append("  \n".join(line_parts) + "\n")

    lines.append(f"\n---\n*⏱ {datetime.now(UTC8).strftime('%H:%M')} 自动生成 | 来源: NewsAPI*")
    return "\n".join(lines)


# ─── 存档 ────────────────────────────────────────────────────────────────

def build_html(articles: list[dict[str, Any]], date_str: str) -> str:
    cards = []
    order = ["AI基建投资", "AI芯片/算力", "大模型竞赛", "AI行业应用", "投融资", "政策监管", "AI行业动态"]

    def cat_sort_key(a):
        try:
            return order.index(a["_category"])
        except ValueError:
            return 99

    sorted_articles = sorted(articles, key=cat_sort_key)

    for i, a in enumerate(sorted_articles, 1):
        title = html.escape(safe_text(a.get("title")))
        desc = html.escape(truncate(safe_text(a.get("description")), 150))
        url = html.escape(safe_text(a.get("url")))
        source = html.escape(safe_text(a.get("source", {}).get("name", "")))
        cat = a.get("_category", "AI行业动态")
        region = a.get("_region", "")
        cards.append(f"""    <div class="card">
      <div class="meta">
        <span class="tag">{cat}</span>
        <span class="region">{region}</span>
        <span class="source">{source}</span>
      </div>
      <h3><a href="{url}" target="_blank">{title}</a></h3>
      <p>{desc}</p>
    </div>""")

    cards_html = "\n".join(cards)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>每日AI&DC新闻 · {date_str}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #f5f0e8; font-family: -apple-system, "Noto Sans SC", sans-serif; padding: 40px 20px; }}
  .container {{ max-width: 900px; margin: 0 auto; }}
  h1 {{ font-size: 1.6em; color: #333; margin-bottom: 8px; text-align: center; }}
  .sub {{ color: #888; text-align: center; font-size: 0.85em; margin-bottom: 30px; }}
  .card {{ background: #fff; border-radius: 10px; padding: 18px 22px; margin-bottom: 16px;
           box-shadow: 0 2px 8px rgba(0,0,0,0.06); transition: box-shadow .2s; }}
  .card:hover {{ box-shadow: 0 4px 16px rgba(0,0,0,0.1); }}
  .meta {{ display: flex; gap: 10px; align-items: center; margin-bottom: 8px; font-size: 0.78em; }}
  .tag {{ background: #e8d5b5; color: #5a4a2a; padding: 2px 10px; border-radius: 4px; font-weight: 600; }}
  .region {{ color: #666; }}
  .source {{ color: #999; margin-left: auto; }}
  h3 {{ font-size: 1em; margin-bottom: 6px; }}
  h3 a {{ color: #222; text-decoration: none; }}
  h3 a:hover {{ color: #c0392b; text-decoration: underline; }}
  p {{ font-size: 0.88em; color: #555; line-height: 1.6; }}
  .footer {{ text-align: center; color: #aaa; font-size: 0.8em; margin-top: 30px; }}
</style>
</head>
<body>
<div class="container">
  <h1>📡 每日AI&DC新闻</h1>
  <div class="sub">{date_str}</div>
{cards_html}
  <div class="footer">⏱ {datetime.now(UTC8).strftime('%H:%M')} 自动生成 · 来源: NewsAPI</div>
</div>
</body>
</html>"""


# ─── Server酱 推送 ───────────────────────────────────────────────────────

def push_wechat(sendkey: str, title: str, content_md: str) -> bool:
    url = SERVERCHAN_URL.format(sendkey=sendkey)
    payload = json.dumps({"title": title, "desp": content_md}).encode("utf-8")
    try:
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if result.get("code") == 0 or result.get("errno") == 0:
            log("  ✅ Server酱 推送成功")
            return True
        else:
            log(f"  ❌ Server酱 推送失败: {result.get('message', result.get('info', 'unknown'))}")
            return False
    except Exception as e:
        log(f"  ❌ Server酱 请求异常: {e}")
        return False


# ─── 主流程 ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="每日AI&DC新闻 — 抓取并推送到微信")
    parser.add_argument("--newsapi-key", default=os.getenv("NEWSAPI_KEY"), help="NewsAPI Key")
    parser.add_argument("--sendkey", default=os.getenv("SENDKEY"), help="Server酱 SendKey")
    parser.add_argument("--date", help="新闻日期 (YYYY-MM-DD)，默认为今天")
    parser.add_argument("--dry-run", action="store_true", help="仅生成，不推送")
    args = parser.parse_args()

    if not args.newsapi_key:
        log("❌ 需要 --newsapi-key 或环境变量 NEWSAPI_KEY")
        sys.exit(1)
    if not args.sendkey and not args.dry_run:
        log("❌ 需要 --sendkey 或环境变量 SENDKEY")
        sys.exit(1)

    # 日期
    if args.date:
        date_obj = datetime.strptime(args.date, "%Y-%m-%d").date()
        date_str = args.date
    else:
        date_obj = datetime.now(UTC8).date()
        date_str = date_obj.strftime("%Y-%m-%d")

    date_from = date_str  # NewsAPI 的 from 参数
    log(f"📡 开始抓取 {date_str} 的AI&DC新闻")

    # Step 1: 多轮搜索
    all_articles: list[dict[str, Any]] = []
    total_queries = len(SEARCH_QUERIES)
    for idx, (query, lang) in enumerate(SEARCH_QUERIES, 1):
        log(f"  [{idx}/{total_queries}] 搜索: {query[:35]}")
        articles = fetch_newsapi(args.newsapi_key, query, lang, date_from)
        log(f"    → 获取 {len(articles)} 条")
        all_articles.extend(articles)

    log(f"📦 合计 {len(all_articles)} 条（去重前）")

    # Step 2: 去重
    all_articles = dedup(all_articles)
    log(f"🔍 去重后 {len(all_articles)} 条")

    # Step 3: 分类 + 地区标记
    for a in all_articles:
        title = safe_text(a.get("title"))
        desc = safe_text(a.get("description"))
        a["_category"] = classify(title, desc)
        a["_region"] = region_tag(title, desc)

    # Step 4: 取前 N 条
    articles = all_articles[:MAX_RESULTS]
    log(f"📋 精选 TOP {len(articles)} 条")

    # Step 5: 生成 Markdown
    md = build_markdown(articles, date_str)
    title = f"📡 每日AI&DC新闻 · {date_str}"

    # Step 6: 生成 HTML 存档
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    html_path = os.path.join(ARCHIVE_DIR, f"{date_str}.html")
    html_content = build_html(articles, date_str)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    log(f"💾 存档: {html_path}")

    # Step 7: 推送到微信
    if args.dry_run:
        log("🏁 Dry-run 模式，不推送")
        print("\n" + md)
        return

    log("📤 推送到微信...")
    success = push_wechat(args.sendkey, title, md)

    if not success:
        sys.exit(1)

    log("🎉 完成!")


if __name__ == "__main__":
    main()
