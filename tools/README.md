# 工具

两个 Python 脚本，仅用标准库，无需安装依赖。

---

## swf_extract.py

SWF 三层嵌套提取器。从 4399 的壳 SWF 里解出内嵌的真本体。

```bash
python swf_extract.py main.swf out/
```

产出：

```
out/13_L4399Main_gamefile.bin     内嵌载荷（DefineBinaryData, chid=13）
out/game_inner.swf                解压后的真本体（FWS）
```

### 原理

4399 的壳结构固定：

```
容器 htm → main.swf(壳) → DefineBinaryData#13 → 真本体
```

壳的 AS3 代码里指明了 chid：

```actionscript
[Embed(source="/_assets/13_L4399Main_gamefile.bin", mimeType="application/octet-stream")]
public class L4399Main_gamefile extends ByteArrayAsset { }
```

**关键点：那个 XOR 解密是幌子。**

壳里有完整的 `Decryption.as`，但：

```actionscript
private var game_key:String = "";     // 空密钥
```

载荷头部直接是 `CWS`，标准 zlib 压缩，解就行。

### DefineBinaryData 结构

```
CharacterId   u16
Reserved      u32
Data          ...       ← 载荷
```

### tag 遍历的两种长度格式

```python
hdr = struct.unpack('<H', data[off:off+2])[0]
code = hdr >> 6
length = hdr & 0x3F
body = off + 2

if length == 0x3F:                        # 0x3F = 长格式标志
    length = struct.unpack('<I', data[off+2:off+6])[0]
    body = off + 6
```

---

## abc_inspect.py

ABC 块定位器。改字节码之前必须先知道目标在哪个块。

```bash
python abc_inspect.py target.swf
python abc_inspect.py target.swf merged    # 只看名字含 merged 的块
```

输出示例：

```
DoABC#4
  tag@7523009      flags=0x00000001
  name          'frame2'
  abcStart      7523026
  abcLen        19604114
  version       minor=16 major=46
  cpool         int=7326 uint=0 double=4294967295 string=100
  contains inPlatform             @12847
```

### 三个必须知道的坑

**1. SWF 可能有多块 ABC**

一个包里有 5 个 `DoABC` 是常态。主逻辑往往在最后那个（`frame2`，19.6 MB）。找错块等于白找。

**2. ABC 头 minor 在前**

```python
minor = struct.unpack('<H', abc[0:2])[0]    # 16
major = struct.unpack('<H', abc[2:4])[0]    # 46
```

读反了会以为版本号异常。

**3. 常量池编码不统一**

```
int 初始值     变长 s32（5 位符号扩展）
uint 初始值    u30
double        定长 8 字节
string         u30 长度 + UTF-8 字节
```

混用会导致后续全部解析错位。脚本里的 `u30()` 和 `s32_var()` 就是干这个的。

### 关于改字节码

脚本只做**探查**，不做修改。

真要改一个 getter，需要：重定位 → 重编常量池 → 重写方法体 → 重算所有长度字段。投入产出比很差。

**优先级建议：**

1. 查壳逻辑，找开关变量（`game_key = ""` 这种）
2. 换运行环境（桌面版播放器跳过浏览器检查）
3. 实在不行才动 ABC

---

## 配套工具

| 工具 | 用途 | 来源 |
|---|---|---|
| **FFDec** | AVM2 反编译 | [jindrapetrik/jpexs-decompiler](https://github.com/jindrapetrik/jpexs-decompiler) |
| **Ruffle** 桌面版 | 运行时（浏览器版过不了平台自检） | [ruffle-rs/ruffle](https://github.com/ruffle-rs/ruffle/releases) |

### FFDec 常用命令

```bash
# 导出脚本 + 符号表（最重要）
java -jar ffdec.jar -onerror ignore -export script,symbolClass out/ target.swf

# 导出内嵌二进制（Unity 资源容器在这里）
java -jar ffdec.jar -onerror ignore -export binaryData out/ target.swf

# 导出图片音效
java -jar ffdec.jar -onerror ignore -export image,sound out/ target.swf
```

耗时参考（27 MB SWF）：`script` 约 135 秒，`binaryData` 约 4 秒。
