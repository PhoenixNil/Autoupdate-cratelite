# Crates Index Generator

从 crates.io 数据库 dump 生成按下载量排序的 crate 名称索引文件。

## 输出格式

`crates-index.txt` — 纯文本文件，每行一个 crate 名称，按下载量降序排列：

```
serde
rand
tokio
reqwest
clap
...
```

第 1 行 = 下载量最高的 crate，第 N 行 = 第 N 热门的 crate。行号即排名。

## 本地运行

```bash
python generate.py
```

首次运行会下载约 300MB 的数据库 dump，之后会复用已下载的文件。

## 自动更新

项目包含 GitHub Actions 配置（`.github/workflows/update-crates-index.yml`），
每天 UTC 06:00 自动运行，生成新的索引文件并发布到 GitHub Releases。

你的 VSCode 扩展可以从 `latest` release 下载文件：

```
https://github.com/<你的用户名>/crates-index/releases/download/latest/crates-index.txt.gz
```

## 在 VSCode 扩展中使用

```typescript
// 扩展启动时加载索引
const lines = indexText.split('\n').filter(Boolean);
// lines[0] = 最热门的 crate
// lines[1] = 第二热门
// ...

// 建立前缀索引用于快速查询
const trieOrMap = buildPrefixIndex(lines);

// 用户输入 "se" 时
const matches = searchByPrefix(trieOrMap, "se");
// matches 已经按 rank（行号）排好序
```
