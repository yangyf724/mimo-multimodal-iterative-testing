# Confirm Protocol（跨模态确认）

Detect 与 Confirm 视角分离。

## 证据等级

| 级 | 内容 | 可 Confirmed？ |
|----|------|----------------|
| L0 | VLM「感觉不好看」 | 否 → Deferred/Reject |
| L1 | 截图 + 描述 | 否，除非可复现 |
| L2 | 截图 + selector/bbox + 复现 | 视规则 |
| L3 | L2 + 机器规则命中 | **是** |
| L4 | L3 + 用户规范 | **是**（优先） |

## 确认清单（视觉）

1. 可定位：route/canvas item + selector 或坐标 + viewport  
2. 可陈述：期望 vs 实际（有数用数）  
3. 可证据：L3/L4；纯审美必须 L4  
4. 指纹未重复  
5. category ∈ DESIGN §1.4  

## 拒绝原因枚举

`false-positive` | `not-reproducible` | `intentional-design` | `animation-transient` | `auth-wall` | `subjective` | `duplicate`

## VLM 审图（仅候选）

- 同图独立 2 次（可不同侧重 prompt）；两次点名同一问题且位置一致 → Candidate。
- 与 `layout-geom` / `a11y-axe` 交叉：已报同类则合并升级，不重复计数。

## 代码向确认

- `static`：工具稳定退出码 + 可定位文件/行。
- `dynamic`：失败测试名 + 断言消息；flaky 需重跑 ≥3 次一致。
