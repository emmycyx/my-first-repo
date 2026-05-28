# 每日AI&DC新闻推送

每天早上 8:00 自动抓取全球 AI & 数据中心 TOP 新闻，通过微信推送给你。

## 工作原理

```
NewsAPI (全球新闻源) → 每日AI&DC新闻 → Server酱 → 微信推送
         ↑                          ↑
  GitHub Actions 定时触发     HTML 存档到仓库
```

## 技术栈

- **新闻源**: NewsAPI（覆盖中英文 9 组搜索词）
- **定时任务**: GitHub Actions（每天 0:00 UTC = 8:00 UTC+8）
- **推送**: Server酱
- **存档**: 自动生成 HTML 版本并提交到 `archive/` 目录

## 文件说明

| 文件 | 说明 |
|------|------|
| `daily_news.py` | 主脚本：抓取 → 去重 → 分类 → 推送 → 存档 |
| `.github/workflows/daily-news.yml` | GitHub Actions 定时工作流 |
| `archive/` | 每日 HTML 存档（自动生成） |
