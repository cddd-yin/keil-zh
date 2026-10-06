# Keil µVision 5.x 简体中文补丁（keil-zh）

**原地汉化**你的 Keil µVision：运行一次，之后**双击桌面那个 Keil 图标就是中文**，
不需要额外的启动器，也不需要改名。

- **一键汉化 / 一键还原**：首次执行先自动备份 `UV4.exe.bak`（英文原版），随时可还原；
- **只改界面资源**：仅替换 PE 资源段中的字符串表、菜单、对话框文本，
  `.text / .rdata / .data` 与备份原版**逐字节一致**（写入前自动校验，不过则放弃）；
- **指纹匹配、绝不误改**：词典按 **资源身份 + 英文原文 SHA-256** 双重匹配，
  完全对不上的条目一律保持英文；
- **3000+ 界面条目**：主菜单、右键菜单、工具栏提示、状态栏、绝大多数对话框；
- 可选 `--copy`：只生成旁边的 `UV4_zh-CN.exe`、完全不动原版的非破坏式模式。

![主界面](截图/01-主界面.png)

## 效果

| 主界面 | 器件数据库 | 关于 |
|---|---|---|
| ![主界面](截图/01-主界面.png) | ![器件数据库](截图/02-器件数据库.png) | ![关于](截图/03-关于.png) |

实测环境：**Keil µVision 5.40.0.0**（Windows，中文系统）。

## 工作原理（一句话）

µVision 的界面文字全部保存在 `UV4.exe` 的 Win32 资源里（字符串表 `RT_STRING`、
菜单 `RT_MENU`、对话框 `RT_DIALOG`）。本补丁用官方 Windows 资源 API
把 `1033`（英文）资源中的文本**精确替换**为简体中文，并就地写回 `UV4.exe`。

安全设计：

1. 首次执行先备份 `UV4.exe.bak`（原版英文），之后每次都以这份备份为源做匹配；
2. 每条词典的键是“**资源身份**（字符串 ID / 菜单路径 / 对话框控件序号）+
   **英文原文的 SHA-256 指纹**”，只有二者同时命中才会替换；
3. 写入在临时文件上进行，写完后逐段比对：`.text/.rdata/.data` 必须与原版完全一致，
   只有 `.rsrc` 允许变化；校验不过就放弃写入，`UV4.exe` 保持原样。

> 只改资源、不碰代码与数据：即使某个词条翻错，也只影响显示，
> 不会影响编译器、调试器、Pack、工程文件或许可证逻辑。

## 环境要求

- Windows 10 / 11；
- 已合法安装 Keil µVision 5.x（自带 `UV4\UV4.exe`）；
- **Python 3.8+**（仅标准库，无需 pip 安装任何包）。

> ⚠️ 注意：Windows 自带/商店里的 `python.exe` 往往是**占位程序**（运行后没有任何输出）。
> 请安装真正的 Python，或使用便携版并在仓库根目录创建 `python-path.txt`
> 填入 `python.exe` 的完整路径（脚本会优先使用它）。

## 使用流程

### 1. 汉化

1. 下载本仓库并解压到任意目录；
2. **完全退出 Keil µVision**；
3. 双击 **`工具\生成中文版.cmd`**，看到 `[OK]` 即完成；
4. 之后照旧双击桌面/开始菜单里的 Keil 图标 —— 界面就是中文了。

> `UV4.exe.bak`（英文原版）会保留在 `UV4.exe` 旁边。脚本会自动在注册表与常见路径中
> 查找 `UV4.exe`；找不到时可用 `工具\生成中文版.cmd --target "D:\Keil_v5\UV4\UV4.exe"`。
> 运行日志在 `build\build.log`。

### 2. 还原英文

双击 **`工具\还原英文.cmd`**：从 `UV4.exe.bak` 还原原版 `UV4.exe` 并删除备份；
桌面图标随即恢复英文。

### 3. 只预览、不写入

双击 **`工具\预览匹配.cmd`**，查看词典与本地 `UV4.exe` 的匹配率与未命中项（不改任何文件）。

### 4. 高级用法（命令行）

```powershell
python build_patch.py                       # 原地汉化（默认；自动备份 UV4.exe.bak）
python build_patch.py --dry-run             # 只统计，不写文件
python build_patch.py --target "<...>\UV4.exe"
python build_patch.py --copy                # 非破坏式：只生成旁边的 UV4_zh-CN.exe
python build_patch.py --min-coverage 0.85   # 其它版本提高兼容模式阈值
python build_patch.py --exact-only          # 只接受完整验证过的版本哈希
python tools\verify_pe_sections.py "<原版备份>" "<UV4.exe>"   # 校验仅资源段被改动
python tools\validate_formats.py "<UV4.exe>"                 # 校验菜单/对话框可无损解析
```

## 覆盖情况

以 µVision **5.40.0.0** 为例（见 `build/patch-report.json`）：

| 资源 | 命中 / 总数 |
| --- | --- |
| 字符串表（RT_STRING） | 828 / 955 |
| 菜单（RT_MENU） | 265 / 318 |
| 对话框（RT_DIALOG） | 2043 / 2294 |
| **合计（按出现次数）** | **3136 条** |

词典在这些条目上的匹配率为 **100%**（`coverage.ratio = 1.0`）。
未命中的多为数字、寄存器名、器件型号、URL、脚本关键字等**本就不该翻译**的内容。

## 兼容性

| 版本 | 状态 |
| --- | --- |
| µVision 5.40.0.0 | ✅ 实机验证（本仓库开发环境，`exact-tested`） |
| 其它 µVision 5.x（MDK / C51） | ✅ 同机制；按“资源身份 + 原文指纹”精确匹配，未命中项保持英文；默认匹配率 < 70% 时**拒绝写入**，建议先 `--dry-run` |
| µVision 4.x / 非 µVision | ❌ 拒绝（只接受主版本号为 5 的文件） |

词典按**原文指纹**（而非版本号）匹配，因此大版本升级后大部分词条仍然有效。
**升级 / 重装 Keil 后**：`UV4.exe` 会被官方文件覆盖，重打一次 `工具\生成中文版.cmd` 即可。

## 已知限制

以下内容存在于**程序代码/数据**而非资源中，无法通过资源方式翻译，保持英文：

- 「关于 µVision」对话框中的版权/许可正文（硬编码在 `.data`）；
- 少数属性表框架按钮（如「器件数据库」窗口底部的 *Close / Help*）；
- 由代码在运行时拼接或设置的个别文本，如窗格标题（*Project*、*Build Output*）、
  *Recent Files*、部分窗口标题等。

另外：资源被改动会导致 Arm 的**数字签名失效**（任何资源汉化都无法避免）；
若安全软件因此报警，请放行或改用 `--copy` 模式。

## 目录结构

```
build_patch.py            补丁生成器入口（默认原地汉化 + 自动备份 + 写入前校验）
tools/
  pe_resources.py         PE 资源读写（Windows 资源 API）+ 字符串表编解码
  resource_formats.py     菜单 / 对话框资源格式解析与序列化
  make_catalog.py         由 translations/src/*.json + 官方 UV4.exe 生成指纹词典
  extract.py              导出界面资源（供维护词典）
  validate_formats.py     校验菜单/对话框可无损往返解析
  verify_pe_sections.py   校验仅资源段被改动（代码段逐字节一致）
  export_translation_catalog.py  由“原版/汉化版”对照导出指纹词典
  restore.py              还原英文（从 UV4.exe.bak）
translations/
  zh_CN.json              编译好的指纹词典（补丁实际使用）
  src/*.json              词典源文件（便于审校与维护）
工具/                     一键脚本（生成中文版 / 预览匹配 / 还原英文）
截图/                     效果截图
docs/                     原理、兼容性与开发验证记录
```

## 维护与二次开发

- 修正某个词条：编辑 `translations/src/*.json` 中对应的“英文原文 → 中文”，
  运行 `python tools\make_catalog.py`（会自动定位官方 `UV4.exe`）重新生成词典；
- 补翻新版本新增文案：`python tools\extract.py "<...>\UV4.exe"` 导出资源，
  在 `translations/src/*.json` 补全后重新运行 `make_catalog.py`；
- 词典按“**资源身份 + 原文指纹**”生成，因此同一原文在不同位置的上下文差异可被区分。

## 常见问题

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| 双击「生成中文版.cmd」只闪过一行、没有生效 | 系统里的 `python` 是微软商店的**占位程序**（不执行 Python） | 安装真正的 Python 3.8+；或在仓库根目录新建 `python-path.txt`，写入某个 `python.exe` 的完整路径。脚本现已逐个探测候选解释器并把输出写入 `build\build.log` |
| 提示 `No working Python 3 found` | 同上，或 Python 未加入 PATH | 同上 |
| 汉化后仍然是英文 | 有 Keil 进程未完全退出，写入被跳过；或看的是旧窗口 | 完全退出 Keil 后重跑；确认 `UV4.exe` 大小/时间已变化，或看 `build\build.log` 里的 `output_sha256` |
| 写入时报「请先完全退出正在运行的 Keil」 | `UV4.exe` 正被占用 | 关闭 Keil 后重试（脚本会给出中文提示，不再打印堆栈） |
| 提示找不到 `UV4.exe` | 安装位置特殊或注册表无记录 | 用 `工具\生成中文版.cmd --target "D:\Keil_v5\UV4\UV4.exe"` 手动指定 |
| 提示 `Compatibility check failed` / 退出码 2 | 其它版本命中率低于 `--min-coverage`，或使用了 `--exact-only` | 先 `--dry-run` 看报告；确认文件确为官方 µVision 5.x；不要盲目调低阈值 |
| 提示 `Device Database`/属性表底部按钮仍是英文 | 这些文本硬编码在程序里，不在资源中 | 已知限制，见上文 |
| 想彻底还原 / 升级 Keil 后 | — | 双击 `工具\还原英文.cmd`；备份 `UV4.exe.bak` 与 `UV4.exe` 同目录 |

## 版权与免责声明

- 本仓库**不提供** Keil 软件本体、`UV4.exe`、编译器、Pack、许可证或注册机；
  补丁在**使用者自己的机器**上由官方文件现场生成，仓库内不含任何厂商二进制。
- Keil、µVision、MDK、ARM 是 Arm Limited / Keil 的商标；请通过官方渠道获取并使用正版软件。
- 本项目为第三方非官方汉化，与 Arm / Keil 无任何关联。
- 工具与词典：MIT（见 `LICENSE`）；使用本项目产生的一切后果由使用者自行承担。
