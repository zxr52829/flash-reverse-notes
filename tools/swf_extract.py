"""swf_extract.py — SWF 三层嵌套提取器

从 4399 的壳 SWF 里把内嵌的真本体解出来。
适用于所有使用 4399 "Flash Barrel (FB)" 通用壳的游戏。

用法：
    python swf_extract.py main.swf out_dir

产出：
    out_dir/13_L4399Main_gamefile.bin   内嵌载荷（DefineBinaryData）
    out_dir/game_inner.swf              解压后的真本体（FWS）

原理：
    1. 遍历 SWF tag，找 DefineBinaryData (code=87)，取 chid 13
       —— 对应壳里 [Embed] 的 L4399Main_gamefile 类
    2. 载荷头部是 CWS/CFS/ZWS 时按 SWF 压缩格式解包
    3. 4399 壳里的 Decryption.as 做逐字节 XOR，但 game_key 为空字符串时
       等于没加密，所以载荷直接就是标准 CWS
"""
import os
import struct
import sys
import zlib


def unwrap(data):
    """把 CWS/ZWS/FWS 统一成 FWS"""
    sig = data[:3]
    if sig not in (b'FWS', b'CWS', b'ZWS'):
        raise ValueError('not a SWF: %r' % sig)
    if sig == b'FWS':
        return data

    ver = data[3]
    declared = struct.unpack('<I', data[4:8])[0]

    if sig == b'CWS':
        raw = zlib.decompress(data[8:])
    elif sig == b'ZWS':
        import lzma
        # 前 12 字节：sig(3) + ver(1) + len(4) + zi(4)
        raw = lzma.decompress(data[12:], format=lzma.FORMAT_ALONE)
    else:
        raise ValueError('unknown signature %r' % sig)

    if len(raw) + 8 != declared:
        print('  [warn] declared %d, actual %d' % (declared, len(raw) + 8))

    return b'FWS' + bytes([ver]) + struct.pack('<I', len(raw) + 8) + raw


def parse_header(fws):
    """返回 (tags_start, stage_w, stage_h, fps, frames)"""
    p = 8
    nbits = fws[p] >> 3
    total_bits = 5 + nbits * 4
    nbytes = (total_bits + 7) // 8

    bits = ''
    for byte in fws[p:p + nbytes]:
        bits += format(byte, '08b')
    vals = bits[5:]
    rect = [int(vals[i * nbits:(i + 1) * nbits], 2) for i in range(4)]

    twips = 1.0 / 20.0
    w = (rect[2] - rect[0]) * twips
    h = (rect[3] - rect[1]) * twips

    p += nbytes
    fps = struct.unpack('<H', fws[p:p + 2])[0] / 256.0
    frames = struct.unpack('<H', fws[p + 2:p + 4])[0]

    return p + 4, w, h, fps, frames


def iter_tags(data, off):
    """遍历 tag，产出 (code, body_start, length)"""
    while off < len(data) - 1:
        hdr = struct.unpack('<H', data[off:off + 2])[0]
        code = hdr >> 6
        length = hdr & 0x3F
        body = off + 2

        if length == 0x3F:                      # 长格式
            length = struct.unpack('<I', data[off + 2:off + 6])[0]
            body = off + 6

        yield code, body, length

        if code == 0:                           # End
            return
        off = body + length


def find_binary_data(fws, want_chid):
    """找指定 chid 的 DefineBinaryData (code=87)"""
    tags_start, w, h, fps, frames = parse_header(fws)
    print('  stage %.0fx%.0f  %.1f fps  %d frames' % (w, h, fps, frames))

    for code, body, length in iter_tags(fws, tags_start):
        if code != 87:
            continue
        chid = struct.unpack('<H', fws[body:body + 2])[0]
        payload = fws[body + 6:body + length]   # 跳过 CharacterId(u16) + Reserved(u32)
        print('  DefineBinaryData chid=%-5d len=%d' % (chid, len(payload)))
        if chid == want_chid:
            return payload
    return None


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    src, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)

    raw = open(src, 'rb').read()
    print('[1] %s  %d bytes' % (src, len(raw)))

    fws = unwrap(raw)
    print('[2] unwrapped  %d bytes' % len(fws))

    # L4399Main_gamefile 的 chid 在 4399 壳里固定为 13
    payload = find_binary_data(fws, want_chid=13)
    if payload is None:
        print('[x] chid=13 not found — is this a 4399 FB shell?')
        return 2

    bin_path = os.path.join(outdir, '13_L4399Main_gamefile.bin')
    open(bin_path, 'wb').write(payload)
    print('[3] payload  %s  %d bytes' % (bin_path, len(payload)))

    inner = unwrap(payload)
    inner_path = os.path.join(outdir, 'game_inner.swf')
    open(inner_path, 'wb').write(inner)
    print('[4] binary   %s  %d bytes' % (inner_path, len(inner)))

    _, w, h, fps, frames = parse_header(inner)
    print('    stage %.0fx%.0f  %.1f fps  %d frames' % (w, h, fps, frames))
    return 0


if __name__ == '__main__':
    sys.exit(main())
