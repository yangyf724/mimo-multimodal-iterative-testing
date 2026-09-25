# Subagent 并行采集（Phase 2）

单写者契约（DESIGN §5.2b）不变：**只有 main agent** 写 `state.json` / `fingerprints.json` / `bugs/**`。

## Subagent 允许写

- `runs/run-N/captures/shard-{i}/`
- `runs/run-N/findings/raw/`

## 分片采集

矩阵 cell 按 `(index) % n` 划分：

```powershell
# 每个 subagent
capture_web.py --root <project> --run-id run-N --shard 0/2
capture_web.py --root <project> --run-id run-N --shard 1/2

# main agent 汇总（不写 state）
capture_web.py merge --root <project> --run-id run-N
# 或
capture_web.py merge --captures <project>/.mmit/runs/run-N/captures
```

产物：

```
captures/
  shard-0/MANIFEST.shard-0.json + 截图/elements
  shard-1/MANIFEST.shard-1.json + …
  MANIFEST.json          # merge 后
```

## merge 语义

- 合并所有 `MANIFEST.shard-*.json`；
- 同 route×viewport 冲突：status=ok 优先，再比 elements mtime；
- 制品**复制**到 captures 根（不依赖 symlink）；
- 写 `merged_from` / `conflicts`；
- **不**更新 state / fingerprints——由 main agent 在锁内继续 hunt_round。

## Spawn 模板（参考）

```
任务：分片采集 shard {i}/{n}
工作目录：{project_root}
命令：& $env:MIMO_PYTHON {skill}/scripts/capture_web.py --root . --run-id run-N --shard {i}/{n}
禁止：写 .mmit/state.json、fingerprints.json、bugs/**
完成后回报：MANIFEST 路径 + ok/error cell 数
```
