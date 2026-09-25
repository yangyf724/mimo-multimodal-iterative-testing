# 项目画像 Profile Schema

画像来源：仓库、清单（package.json / pyproject / go.mod / Cargo.toml 等）、CI 配置、README、媒体/设备目录、运行时探测。产物：`.mmit/profile.json`。由 `scripts/profile_scan.py` 生成。

## unknown-not-invent 规则（硬约束）

1. 缺字段一律写 `unknown`，**不得臆造**默认值或猜测内容。
2. 线索不充分 → 字段保持 `unknown`，并在矩阵中标为盲区候选，不得当「已覆盖」。
3. 用户可显式补全字段；补全来源记入 `profile.json` 的 `sources`，仍禁止无来源填充。
4. `unknown` 字段对应的模态在矩阵中：能证明未命中 → `n/a`；不能证明 → `optional` + Blind Spot，不得标 `required` 通过。
5. Profile Scan **静默完成**（S1），不向用户反复确认；冲突线索取更保守解释并记录。

## 字段定义

| 字段 | 类型 | 示例 | 说明 |
|------|------|------|------|
| `app_types` | string[] | `web,api,cli,mobile,desktop,xr,plugin` | 主交付形态；驱动模态命中 |
| `runtime` | string | `node@20` | 构建/运行时；E1 版本锁定依据 |
| `topology` | string | `api+worker+postgres+redis` | 依赖形状；E1 对齐生产拓扑 |
| `devices` | string[] | `ios-sim,android-emu,quest3` | 设备面；E3 真机/仿真来源 |
| `data_classes` | string[] | `pii,payment,media` | 数据等级；脱敏硬门输入 |
| `plugins` | string[] | `vscode-ext` | 插件宿主；M13 命中 |
| `release_artifact` | string | `oci-image,dmg,msix,npm,apk` | RC 形态；构建与安装验证对象 |
| `contract_apis` | string[] | `openapi.yaml,proto/` | 对外契约源；M2 契约 diff 输入 |
| `prod_access` | enum | `none,readonly,shadow,canary` | 生产测试授权；默认须用户确认 |

## 字段语义与取值约定

### app_types

- 与 13 模态目录对齐的形态标签：`web` `api` `cli` `mobile` `desktop` `xr` `plugin`，以及 `db` `infra` `av` `canvas` `3d` 等表面线索形态。
- 多形态项目全部列出；漏列会导致矩阵漏测（G1）。

### runtime

- 单值字符串，格式 `name@version` 或发行版锁定标识。
- 禁止写 `latest`；E1 版本锁定依赖此字段。

### topology

- 用 `+` 连接的依赖形状，例：`api+worker+postgres+redis`。
- E1 生产等价要求拓扑一致；偏差写入 `topology_delta`（见 `env-layers.md`）。

### devices

- 每项为设备/仿真面标识：真机型号、模拟器/仿真器（`*-sim` / `*-emu`）、HMD 等。
- 仿真必须可识别为仿真（后缀或备注），E3 统计时单独计覆盖率。

### data_classes

- 数据等级标签，至少覆盖设计示例：`pii` `payment` `media`；可含项目自有等级。
- 直接决定 `data-masking.md` 硬门扫描规则集；识别错误按硬门失败处理。

### plugins

- 插件宿主标识（如 `vscode-ext`、浏览器扩展宿主）。
- 命中则 M13 `plugin` 进入矩阵。

### release_artifact

- RC 制品形态：`oci-image` `dmg` `msix` `npm` `apk` 等。
- 决定 B3 构建与安装/加载验证方式；与 `build_rc.py` 输出 `RC-*.meta.json` 对应。

### contract_apis

- 对外契约源路径或标识（`openapi.yaml`、`proto/` 等）。
- 命中则 M2 `api` 做 contract diff；无契约源时 M2 降级为黑盒接口探针并记盲区。

### prod_access

- 枚举四值：`none` | `readonly` | `shadow` | `canary`。
- 默认 **须用户确认**（Scope 表）；未确认不得自行升权。
- 语义与允许动作见 `prod-test.md`。

## 与矩阵的关系

```text
profile.json  →  S2 Surface Map（线索→surface→modality）  →  S3 Matrix Freeze
```

- `app_types` / `plugins` / `devices` / `contract_apis` 主要驱动模态命中。
- `data_classes` / `prod_access` 驱动环境与数据门，不直接取消模态。
- `unknown` 不等于 `n/a`：`n/a` 需画像线索证明未命中。

## 校验清单

- [ ] 九字段齐全（值可为 `unknown`，键不可缺）
- [ ] 无臆造值；`unknown` 均有原因（缺线索/冲突未决）
- [ ] `prod_access` 已获用户确认
- [ ] `data_classes` 非空或显式 `unknown`（`unknown` 时脱敏按最严规则）
- [ ] `profile.json` 可被 `matrix_build.py` 消费
