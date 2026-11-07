# Flash / Unity-Flash 反编译实战笔记

从 4399 小游戏《急速变色龙》拆出来的经验沉淀。不谈理论，只记实际踩过的东西：怎么判断引擎、从哪下手、哪些坑值得绕开、用哪些工具。

**案例对象**：一个 27 MB 的 SWF，反编译出 1,324 个 ActionScript 文件，发现它是 **Unity 导出的 Flash**——627 个游戏业务类，15 个关卡，36 个 Unity 序列化容器。

---

## 目录

- [快速判断：先定引擎](#快速判断先定引擎)
- [入口：类名就是文档](#入口类名就是文档)
- [配置表：序列化字段](#配置表序列化字段)
- [核心：只读 Update()](#核心只读-update)
- [筛选：框架代码 vs 游戏代码](#筛选框架代码-vs-游戏代码)
- [空函数体也是信息](#空函数体也是信息)
- [平台壳与游戏本体](#平台壳与游戏本体)
- [字节码层面的边界](#字节码层面的边界)
- [验证可复现性](#验证可复现性)
- [工具清单](#工具清单)
- [完整案例：急速变色龙](#完整案例急速变色龙)

---

## 快速判断：先定引擎

拿到一个 SWF，**不要直接啃字节码**。先把类名列出来，一眼就能定引擎：

| 包路径 | 引擎 |
|---|---|
| `com.unity.UnityNative` | **Unity 导出 Flash** |
| `UnityEngine.*` | Unity API 映射层 |
| `mx.*` | Flex 框架 |
| `flash.display.*` | 原生 AS3 |
| `org.bytearray.gif.*` | 第三方库（GIF 解码） |
| `global.*` | 业务代码（Unity 导出常见） |

案例里的第一印象：

```
com.unity.UnityNative          98 MB     Unity Flash 运行时
UnityEngine.*                          物理/动画/渲染 API
global.*                        627 个类  游戏业务
NGUIText / UIPanel / UIDrawCall         UI 框架
```

**判错引擎的代价极高。** 按普通 Flash 游戏去找逐帧逻辑，会在几十 MB 的运行时镜像里耗尽时间。认清它是 Unity 产物后，思路立刻变成：运行时 + 资源容器，游戏逻辑在 `global/` 里。

### 判断命令

```bash
# 导出脚本后立刻看目录结构
java -jar ffdec.jar -onerror ignore -export script,symbolClass out/ target.swf

ls out/scripts/
du -sh out/scripts/*/ | sort -h | tail -10
```

大目录几乎必然是运行时，小目录里才藏着业务逻辑。

---

## 入口：类名就是文档

中文/拼音命名的项目有天然优势——**类名直接说明用途**：

| 类名 | 含义 |
|---|---|
| `Player_SenTiYanSe` | 身体颜色 |
| `ErDuanTiaoBianSe` | 二段跳变色 |
| `TuoWeiBianSe` | 拖尾变色 |
| `Player_KongZhi` | 玩家控制 |
| `Player_FaShe` | 玩家发射 |
| `ChuanTouCengJi` | 穿透层（下跳平台） |
| `GuanKaXiaoChuangKou` | 关卡小窗口 |
| `BossJiHuoDian` | BOSS 激活点 |
| `BOSS_XueRenGuai` | 血刃怪 BOSS |
| `ChiLunXunLu` | 齿轮巡逻 |
| `ChuanSongDai` | 传送带 |
| `ChuFaJianSu` | 触发减速 |

### 筛选命令

```bash
cd out/scripts/global

# 找和「颜色/变色」相关的
ls | grep -E "变|色|color|Color"

# 找玩家控制相关
ls | grep -iE "player|wanjia|kongzhi|control"

# 找 BOSS
ls | grep -iE "boss"
```

比读任何一个文件都快。**命名混乱的项目没这条捷径，但值得先试一次。**

---

## 配置表：序列化字段

Unity 导出后，MonoBehaviour 的 Inspector 字段全部变成 `public var`：

```actionscript
public var Player_KongZhi$移动速度$:Number = 0;
public var Player_KongZhi$最高移动速度$:Number = 0;
public var Player_KongZhi$额外速度$:Number = 0;
public var Player_KongZhi$阻力$:Number = 0;
public var Player_KongZhi$地面阻力$:Number = 0;
public var Player_KongZhi$空中阻力$:Number = 0;
public var Player_KongZhi$加速度$:Number = 0;
public var Player_KongZhi$地面加速度$:Number = 0;
public var Player_KongZhi$空中加速度$:Number = 0;
public var Player_KongZhi$在地板上$:Boolean;
public var Player_KongZhi$在底层平台$:Boolean;
public var Player_KongZhi$跳跃高度$:Number = 0;
public var Player_KongZhi$空中跳力量$:int;
public var Player_KongZhi$默认空中跳跃力量$:int;
public var Player_KongZhi$地板恢复跳跃力量真空期$:Number = 0;
public var Player_KongZhi$最大重力速度$:Number = 0;
public var Player_KongZhi$最大跳起的时间$:Number = 0;
public var Player_KongZhi$踩踏间隔$:Number = 0;
public var Player_KongZhi$踩踏限制器$:Number = 0;
```

**光看字段列表就能反推整套动作系统**：

- 速度三层叠加（基础 / 上限 / 额外）
- 空中地面两套独立手感（加速度、阻力各两份）
- 跳跃有「额度」概念（`空中跳力量` = 剩余次数）
- 落地后有回充冷却（`地板恢复跳跃力量真空期`）
- 重力有封顶（`最大重力速度`）
- 踩踏有节奏限制（`踩踏间隔` + `踩踏限制器`）

### 命令

```bash
# 提取所有字段
sed -n '/public class Player_KongZhi/,/public function Player_KongZhi()/p' \
    Player_KongZhi.as | grep "public var"
```

**真正的数值不在这里。** 它们存在 Unity 序列化容器里（`ProjectSerializedFileContainer_*.bin`），需要额外解析。但如果目标是**理解机制**，字段名 + `Update()` 逻辑就够；要复刻手感才需要去挖 bin。

---

## 核心：只读 Update()

Unity 的生命周期方法里，`Update()` 每帧执行。业务类的 `Update()` 往往极短：

```actionscript
public function ErDuanTiaoBianSe_Update() : void
{
   if(Player_KongZhi(...).Player_KongZhi$空中跳力量$ == 0)
   {
      SpriteRenderer(...).color = this.ErDuanTiaoBianSe$无力量颜色$;
   }
   else
   {
      SpriteRenderer(...).color = this.ErDuanTiaoBianSe$原始颜色$;
   }
}
```

**整个变色机制就这五行。**

而且这里藏着设计洞察——**变色不是美术效果，是二段跳剩余次数的状态指示器**。玩家靠颜色判断还能跳几次。这种信息源码是唯一出口，玩一百遍也未必想明白。

### 另一个例子

`Player_KongZhi_Update()` 十行交代完整帧流程：

```actionscript
public function Player_KongZhi_Update() : void
{
   this.Player_KongZhi$地板恢复跳跃力量真空期$ -= Time.deltaTime;

   if(在地板上 && 真空期 < 0)
      this.Player_KongZhi$空中跳力量$ = this.Player_KongZhi$默认空中跳跃力量$;   // 回充额度

   this.Player_KongZhi_反转();
   this.Player_KongZhi_模拟世界物理();

   switch(this.Player_KongZhi$m_角色类型$)
   {
      case 玩家1: 非物理键盘控制(); 同步到状态机(); break;
      case 玩家2: 非物理键盘控制(); 同步到状态机(); break;
      case AI:    挂载AI移动状态选择器(); 非物理键盘控制(); 同步到状态机();
   }

   if(在底层平台) this.Player_KongZhi_取消跳下作用();
}
```

### 规律

```
业务类的 Update()     短小、直白 ← 优先读
框架类的 Update()     冗长、嵌套 ← 跳过
```

**做法**：先 `grep -n "function.*_Update"` 定位所有 Update，从 `global/` 下的开始读。

---

## 筛选：框架代码 vs 游戏代码

1,324 个文件里真正值得看的不超过 30 个。

### 不需要看

```
com/unity/UnityNative.as          98 MB    Unity 运行时镜像
UnityEngine/*.as                          API 映射（Camera, Physics, Animator...）
global/NGUI*.as, UI*.as                   UI 框架
global/Bloom*.as, Blur*.as                后处理特效
ConvertedDotNetCodeClassIndex.as          .NET 类型索引表
```

### 需要看

```
global/ 下名字是中文/拼音的类（排除上面的）   游戏逻辑
com/frames/FB.as                          平台壳（拦截点在这里）
```

### 筛选方法

**按大小排序，中间段落最可疑。**

```bash
find . -name "*.as" -not -path "*/mx/*" -printf "%s\t%p\n" \
  | sort -rn | head -40
```

结果分布：

| 大小 | 类型 |
|---|---|
| 98 MB | `UnityNative` —— 运行时 |
| 1-5 KB | `Bloom_*.as` 特效小类 |
| **100-200 KB** | **`Player_KongZhi`、`GuanKaXiaoChuangKou` 等业务类** ← 目标 |
| 60-100 KB | 框架类（`UILabel`、`UIWidget`） |

业务类往往几百到几千行，刚好落中间。

---

## 空函数体也是信息

```actionscript
public function Player_KongZhi_长按加力跳_KeyCode($按键:KeyCode) : void
{
}
```

**函数体空的，但函数名保留着。**

这说明「长按蓄力跳」这个功能规划过、接口留了、最终没实现。

反编译时遇到空实现**不要直接跳过**：

- 它告诉你这个版本的完成度
- 能解释为什么某些操作「看起来应该有用但没反应」
- 是版本差异的重要线索（对比不同版本时，空实现变有实现，就是新增功能）

---

## 平台壳与游戏本体

4399 的 `FB.as`（Flash Barrel）是通用平台层，跟游戏逻辑无关，但**决定游戏能不能跑**：

```actionscript
if (RE.isBrowser && JS.enable) {
    // 比对 allowScriptAccess 等参数，不一致就 reload
}
else if (!appModel.easy) {
    showError(getLabel("allowScriptAccess"), null);
    return;
}
```

追这条链到最底层：

```
AppModel.easy
  └─ Platform.inPlatform(name)
       └─ m_types.indexOf(name) > -1
          || URL.checkDomain(GreenGlobal.domain, name)
               └─ JS.topDomain
                    └─ ExternalInterface.call("top.location.hostname.toString")
```

### 如何区分

看 import：

```actionscript
// 业务类
import UnityEngine.Color;
import UnityEngine.MonoBehaviour;
import UnityEngine.SpriteRenderer;

// 平台壳
import flash.events.Event;
import com.green.method.JS;
```

两类代码混在同一个 ABC 块里，但逻辑边界清楚。

---

## 字节码层面的边界

我尝试直接改 ABC 让 `AppModel.easy` 恒返回 `true`，**没做成，过程值得记录**。

### 坑 1：SWF 可能有多块 ABC

```python
# 遍历 tag 找 DoABC (code=82)
hdr = struct.unpack('<H', data[off:off+2])[0]
code, length = hdr >> 6, hdr & 0x3F
body = off + 2
if length == 0x3F:                                  # 长格式
    length = struct.unpack('<I', data[off+2:off+6])[0]
    body = off + 6
```

这个包有 **5 个 DoABC**，主逻辑在 `frame2`（19.6 MB）：

```
DoABC#0  merged    abcStart=754        len=7,482
DoABC#1  merged    abcStart=8,280      len=56,138
DoABC#2  merged    abcStart=168,168    len=7,917
DoABC#3  frame1    abcStart=274,750    len=31,257
DoABC#4  frame2    abcStart=7,523,026  len=19,604,114   ← 主逻辑
```

**找错块 = 白找。**

### 坑 2：ABC 头 minor 在前

```python
minor = struct.unpack('<H', abc[0:2])[0]     # 16
major = struct.unpack('<H', abc[2:4])[0]     # 46
```

我一开始读反了，看成 `major=46` 觉得异常。

### 坑 3：常量池编码不统一

```
int 初始值   变长 s32（5 位符号扩展）
uint 初始值  u30
double      定长 8 字节
```

混用会导致后续**全部解析错位**。我在这里连续撞了十几次。

```python
def u30(b, p):
    v = 0; shift = 0
    while True:
        byte = b[p]; p += 1
        v |= (byte & 0x7F) << shift
        shift += 7
        if not (byte & 0x80):
            return v, p

def s32_var(b, p):
    result = 0; shift = 0
    for _ in range(5):
        byte = b[p]; p += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not (byte & 0x80):
            break
    if result & (1 << (shift - 1)):        # 符号扩展
        result -= 1 << shift
    return result, p
```

### 结论

**改一个 getter 需要：重定位、重编常量池、重写方法体、重算所有长度字段。** 投入产出比极差。

**优先级应该是：**

1. 查壳逻辑，找开关变量（`game_key = ""` 这种）
2. 换运行环境（桌面版播放器跳过浏览器检查）
3. 实在不行才动 ABC

---

## 验证可复现性

反编译产物必须能重建。**验证方法：重新提取一遍，对比哈希。**

```
原始: 2439CD1DA41B124D5EBACEEE18B73642D27195E9F8FA10325B37158050C533BD
重提: 2439CD1DA41B124D5EBACEEE18B73642D27195E9F8FA10325B37158050C533BD
```

**一致 = 提取链路无偏差**，出问题一定是后续某个具体环节，不用怀疑整条链。

这对排查「跑不起来」特别有用：先证明原料是对的，再往下查。

---

## 工具清单

### 核心

| 工具 | 版本 | 作用 | 地址 |
|---|---|---|---|
| **FFDec** (JPEXS) | 22.0.1 | AVM2 反编译，导出 script/binaryData/image/sound | [jindrapetrik/jpexs-decompiler](https://github.com/jindrapetrik/jpexs-decompiler) |
| **Ruffle** | 0.7.1 | Flash 模拟器（**必须桌面版**） | [ruffle-rs/ruffle](https://github.com/ruffle-rs/ruffle/releases) |
| **Java** | 21 | FFDec 运行环境 | 任意 JDK 21 |
| **Python** | 3.10+ | 解包脚本，仅用标准库 | — |

### FFDec 常用命令

```bash
# 导出脚本（最重要）
java -jar ffdec.jar -onerror ignore -export script,symbolClass out/ target.swf

# 导出内嵌二进制（Unity 资源容器在这里）
java -jar ffdec.jar -onerror ignore -export binaryData out/ target.swf

# 导出图片音效
java -jar ffdec.jar -onerror ignore -export image,sound out/ target.swf

# 全部一起
java -jar ffdec.jar -onerror ignore -export script,image,sound,binaryData,symbolClass out/ target.swf
```

耗时参考（27 MB SWF）：`script` 约 **135 秒**，`binaryData` 约 **4 秒**。

### symbolClass.csv 别忽略

它是**符号 ID ↔ 类名映射表**，告诉你每个库元件的用途：

```csv
13,L4399Main_gamefile
2236,ProjectSerializedFileContainer_level8
```

看到 `ProjectSerializedFileContainer` 就知道有 Unity 序列化资源，看到 `level*` 就知道关卡在二进制里而不是代码里。

### Ruffle：桌面版 vs 浏览器版

| | 桌面版 | 浏览器版 |
|---|---|---|
| `Capabilities.playerType` | `StandAlone` | `PlugIn` / `ActiveX` |
| 平台自检 | **跳过** | **拦截** |
| `allowScriptAccess` | 无需 | 默认 false，且 `ExternalInterface` 不通 |

**遇到平台壳拦截时，先换桌面版试试。** 比较省事。

---

## 完整案例：急速变色龙

### 目标

4399 小游戏《急速变色龙》，页面 `4399.com/flash/188739.htm`。

### 第一步：找真实资源

**页面站不托管 SWF。** 这是最容易踩的坑：

```js
// /js/server8.js
var webServer = "//flashs1.4399.com/4399swf";        // ← 真实资源域名

// 页面内联
var _strGamePath = "/upload_swf/ftp22/tangyongfeng/20170613/5/jifen3d_https.htm";
```

拼起来：

```
https://flashs1.4399.com/4399swf/upload_swf/ftp22/tangyongfeng/20170613/5/jifen3d_https.htm
https://flashs1.4399.com/4399swf/upload_swf/ftp22/tangyongfeng/20170613/5/main.swf
```

**验证锚点**：页面标注「10.39 MB」，实际 `main.swf` 是 10,392,883 字节 —— 吻合。

### 第二步：三层嵌套解包

```
容器 htm  (1,690 B)     只有 <object> 指向 main.swf
 └─ main.swf (10.39 MB)  CWS · Flash v19 · 800×500 · 60fps · 2 帧
     └─ DefineBinaryData #13 (10.28 MB)
         └─ zlib inflate → game_inner.swf (27.13 MB)   ← 真本体
```

**壳的 AS3 代码里指明了 chid：**

```actionscript
[Embed(source="/_assets/13_L4399Main_gamefile.bin", mimeType="application/octet-stream")]
public class L4399Main_gamefile extends ByteArrayAsset { }
```

`DefineBinaryData` 结构：

```
CharacterId   u16
Reserved      u32
Data          ...     ← 载荷
```

### 第三步：识别「假加密」

壳里有完整的 `Decryption.as`：分块读字节 → 逐字节 XOR 循环密钥 → `loadBytes()`。看着是正经保护。

**但一行配置说明它没生效：**

```actionscript
private var game_key:String = "";
```

空密钥。载荷头部直接是 `43 57 53`（`CWS`），标准 zlib 压缩 SWF，直接解就行。

> **教训：先读常量，再写解密器。** 这一眼省了三小时。

### 第四步：反编译定型

```bash
java -jar ffdec.jar -onerror ignore -export script,symbolClass out/ game_inner.swf
```

结果：

| 项目 | 数量 |
|---|---|
| `.as` 文件 | 1,324 |
| 业务类（`global/`） | 627 |
| 反编译耗时 | 135 秒 |
| 《UnityNative.as》 | 98 MB（运行时，排除） |

看到 `com.unity.UnityNative` + `UnityEngine.*` + NGUI，**确认是 Unity 导出的 Flash**。

### 第五步：读核心逻辑

```bash
ls global/ | grep -E "变|色"
# Player_SenTiYanSe.as   身体颜色
# ErDuanTiaoBianSe.as    二段跳变色
# TuoWeiBianSe.as        拖尾变色
```

读出来三件事：

**1. 角色是 13 部件骨骼精灵**

```actionscript
躯干 · 头
右上臂 · 右下臂 · 右手 · 右肘
左上臂 · 左下臂 · 左手
枪械 · 身体所有部件[]
```

每帧把自身 `color` 广播给全身 —— 所以是整只龙同步换色。

**2. 变色 = 二段跳额度指示器**

```actionscript
if (空中跳力量 == 0) color = 无力量颜色;
else                color = 原始颜色;
```

**3. 长按蓄力跳没实现**（空函数体）

### 第六步：跑起来

浏览器 Ruffle 会弹出 `allowScriptAccess` 错误，卡在 `FB.as` 的平台自检。

桌面版 Ruffle `Capabilities.playerType` 返回 `StandAlone`，`RE.isBrowser` 为 false，**整个检查被跳过**：

```
ruffle.exe game_inner.swf
```

实机验证：角色起跳后从白色变橙黄，拖尾转红黄 —— 正是 `ErDuanTiaoBianSe` + `TuoWeiBianSe` 的表现。**源码推理和实机行为对上了。**

### 物料清单

| 项目 | 说明 |
|---|---|
| 壳 | 10,392,883 B · CWS · Flash v19 |
| 本体 | 27,128,915 B · SHA256 `2439CD1D...533BD` |
| 关卡 | 15 个（`level0`–`level14`） |
| 序列化容器 | 36 个 Unity `ProjectSerializedFileContainer` |
| 运行时 | Ruffle 0.7.1 桌面版 |

---

## 一页速查

```
1. 抓页面 → 搜 webServer / _strGamePath → 拿到真实资源域名
2. 核对页面标注的体积，验证抓对文件
3. 查载荷头部：CWS/FWS/ZWS → 没加密就直接 zlib
4. FFDec 先导 script，看类名判断引擎
5. 按大小排序，中间段落找业务类
6. grep 类名（中文/拼音项目优先）→ 锁定核心类
7. 只读 Update() 和 public var 字段
8. 空函数体记下来（功能未完成/版本差异）
9. 跑不起来先看平台壳（FB.as 之类），再考虑换运行环境
10. 字节码修改是最后手段
11. 重提一遍对比哈希，验证链路无偏差
```

---

## 声明

本文档记录的是对**已停止运营的 2017 年网页游戏**的技术研究与保存工作，目标游戏著作权归原作者及 4399 所有。

内容仅用于 AVM2 逆向工程、SWF 容器结构分析、Unity-to-Flash 运行时研究等学习目的。不包含任何游戏本体文件、反编译源码或资源。

请勿用于商业用途或二次分发。
