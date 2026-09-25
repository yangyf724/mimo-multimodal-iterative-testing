# MiMo Multimodal Iterative Testing

**简称：** MMIT（MiMo Multimodal Iterative Testing）— 对话与文档中可用 MMIT 指代本项目。

MiMoCode skill 源码仓，现含两套 skill：

1. **MMIT Hunter** `mmit-hunter/` — 全模态迭代抓 BUG（code + Web 视觉 + 画布），quiet 四条件收敛
2. **MMIT Test** `mmit-test/` — 全模态迭代测试 / 发布就绪裁决（Profile→Matrix→RC Loop→Allow/Deny/Escalate）

<!-- github-sync:begin -->
**Version:** 3.0.0  
**Last sync:** 2026-09-25
<!-- github-sync:end -->

## 仓库定位

- `DESIGN.md` — MMIT 设计真源（全模态 taxonomy、策略库、收敛与 Fix Gate）
- `docs/skill-refactor-mmit-test.md` — MMIT Test 设计真源（MIT-DESIGN-001）
- `mmit-hunter/` — MMIT skill 本体；视觉/布局抓 BUG 唯一真源
- `mmit-test/` — MMIT Test skill 本体（SKILL.md + scripts + references + locales）；发布就绪测试真源
- `examples/acceptance-demo/` / `examples/second-project/` — MMIT 验收 demo
- `examples/mit-demo-webapi/` / `examples/mit-demo-media/` — MMIT Test 双 demo（web+api / media+canvas+3d）
- `tests/` — 单元测试（MMIT phase* + MIT `test_mit_core`）
- `docs/ACCEPTANCE.md` / `docs/METRICS.md` / `docs/BLUEPRINTS.md` — 观测与索引
- `docs/compose/spec/mmit-test.md` — MMIT Test 重构 compose spec

## 快速开始

```powershell
# 单元测试（两套 skill）
$env:MIMO_PYTHON -m unittest discover -s tests -v

# MMIT Test：对项目生成画像与冻结矩阵
& $env:MIMO_PYTHON mmit-test/scripts/profile_scan.py --root <project>
& $env:MIMO_PYTHON mmit-test/scripts/matrix_build.py --root <project> --freeze

# MMIT：在目标项目初始化状态
& $env:MIMO_PYTHON mmit-hunter/scripts/init_state.py --root <project> --routes / /about
```

# Phase 1：采集 + 单轮 hunt（需 Playwright；否则用 MCP 采集后 --skip-capture）
& $env:MIMO_PYTHON ../../mmit-hunter/scripts/capture_web.py --root . --run-id run-1
& $env:MIMO_PYTHON ../../mmit-hunter/scripts/hunt_round.py --root . --run-id run-1 --skip-capture --dynamic-cmd "npm test"

# Phase 2：分片采集 / ux flows / canvas
& $env:MIMO_PYTHON ../../mmit-hunter/scripts/capture_web.py --root . --run-id run-1 --shard 0/2
& $env:MIMO_PYTHON ../../mmit-hunter/scripts/hunt_round.py --root . --run-id run-2 --skip-capture `
  --flows .bug-hunter/flows --canvas-items canvas/poster.scene.json

# Phase 3：路由发现 / FP 白名单 / 导出 / CI
& $env:MIMO_PYTHON ../../mmit-hunter/scripts/discover_routes.py --root . --seed / --html public/index.html --write
& $env:MIMO_PYTHON ../../mmit-hunter/scripts/export_report.py --root .
& $env:MIMO_PYTHON ../../mmit-hunter/scripts/ci_gate.py --root ../..
```

## 安装为 MiMo Desktop skill（可选）

将 `mmit-hunter/` 复制到：

- 全局：`~/.config/mimocode/skills/mmit-hunter/`
- 项目：`<project>/.mimocode/skills/mmit-hunter/`

新开对话后生效。

## License

MIT
