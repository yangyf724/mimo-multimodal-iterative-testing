# MiMo Multimodal Iterative Testing

**简称：** MMIT（MiMo Multimodal Iterative Testing）— 对话与文档中可用 MMIT 指代本项目。

MiMoCode skill 源码仓，现为**单一 skill**：

- **MMIT** `mmit/` — 全模态质量门流水线：抓 BUG 至 quiet 收敛 + 发布就绪 RC 裁决，出口统一 **Allow / Deny / Escalate**

> 历史：`mmit-hunter/`（抓 BUG）与 `mmit-test/`（发布就绪）已合并进 `mmit/`，旧包删除。legacy 状态目录 `.bug-hunter/`、`.mit/` 可用 `mmit/scripts/migrate_state.py` 迁入 `.mmit/`。

<!-- github-sync:begin -->
**Version:** 3.1.0  
**Last sync:** 2026-09-25
<!-- github-sync:end -->

## 仓库定位

- `mmit/` — 唯一 skill 包（SKILL.md + scripts + references + locales）
- `DESIGN.md` — 设计真源（全模态 taxonomy、策略库、收敛与 Fix Gate）；文末附统一流水线说明
- `docs/compose/spec/mmit-unified.md` — 本次合并的 compose spec / 交付契约
- `docs/skill-refactor-mmit-test.md` / `docs/compose/spec/mmit-test.md` — 历史真源（已 superseded）
- `examples/acceptance-demo/` / `examples/second-project/` — 抓 BUG 验收 demo
- `examples/mit-demo-webapi/` / `examples/mit-demo-media/` — 发布就绪双 demo
- `tests/` — 单元测试（hunt phase* + release `test_mit_core`）
- `docs/ACCEPTANCE.md` / `docs/METRICS.md` / `docs/BLUEPRINTS.md` — 观测与索引

## 深度（depth）

| depth | 何时用 | 出口 |
|-------|--------|------|
| `hunt` | 抓 BUG / design QA / 修到没有 | quiet 收敛 → 三态 |
| `release` | 发布就绪 / go-no-go / RC 验收 | SIG+RPT+EVD+PRD → 三态 |

## 快速开始

```powershell
# 单元测试
$env:MIMO_PYTHON -m unittest discover -s tests -v

# hunt 深度：初始化并跑一轮
& $env:MIMO_PYTHON mmit/scripts/init_state.py --root <project> --depth hunt --routes / /about
& $env:MIMO_PYTHON mmit/scripts/capture_web.py --root <project> --run-id run-1
& $env:MIMO_PYTHON mmit/scripts/hunt_round.py --root <project> --run-id run-1 --skip-capture

# release 深度：画像 → 冻结矩阵 → 报告
& $env:MIMO_PYTHON mmit/scripts/init_state.py --root <project> --depth release
& $env:MIMO_PYTHON mmit/scripts/profile_scan.py --root <project>
& $env:MIMO_PYTHON mmit/scripts/matrix_build.py --root <project> --freeze
& $env:MIMO_PYTHON mmit/scripts/assemble_report.py --root <project>

# legacy 状态迁移
& $env:MIMO_PYTHON mmit/scripts/migrate_state.py --root <project>
```

## 安装为 MiMo Desktop skill

将 `mmit/` 复制到：

- 全局：`~/.config/mimocode/skills/mmit/`
- 项目：`<project>/.mimocode/skills/mmit/`

新开对话后生效。若本机仍装有 `mmit-hunter` / `mmit-test`，确认无其它会话依赖后可删除旧目录。

## License

MIT
