"""abc_inspect.py — ABC 块定位与结构探查

用途：
    AS3 字节码（ABC）可能分散在 SWF 的多个 DoABC tag 里。
    改字节码之前必须知道目标类在哪个块、块的边界在哪。

用法：
    python abc_inspect.py target.swf
    python abc_inspect.py target.swf merged     # 只看名字含 merged 的块

产出：
    每个 DoABC 的：tag 偏移、abc 起点、长度、版本号、包含的关键字符串

注意：
    ABC 头是 minor(2) 在前、major(2) 在后。
    常量池编码不统一：int 用变长 s32，uint 用 u30，double 定长 8 字节。
"""
import struct
import sys


def unwrap(data):
    sig = data[:3]
    if sig == b'FWS':
        return data
    import zlib
    if sig == b'CWS':
        raw = zlib.decompress(data[8:])
        return b'FWS' + bytes([data[3]]) + struct.pack('<I', len(raw) + 8) + raw
    raise ValueError('not a FWS/CWS SWF: %r' % sig)


def parse_header(fws):
    p = 8
    nbits = fws[p] >> 3
    nbytes = ((5 + nbits * 4) + 7) // 8
    p += nbytes
    p += 4                      # framerate + framecount
    return p


def iter_tags(data, off):
    while off < len(data) - 1:
        hdr = struct.unpack('<H', data[off:off + 2])[0]
        code = hdr >> 6
        length = hdr & 0x3F
        body = off + 2
        if length == 0x3F:
            length = struct.unpack('<I', data[off + 2:off + 6])[0]
            body = off + 6
        yield code, body, length, off
        if code == 0:
            return
        off = body + length


def u30(b, p):
    v = 0
    shift = 0
    while True:
        byte = b[p]
        p += 1
        v |= (byte & 0x7F) << shift
        shift += 7
        if not (byte & 0x80):
            return v, p


def s32_var(b, p):
    """AVM2 变长 s32，最多 5 字节，末字节符号扩展"""
    result = 0
    shift = 0
    for _ in range(5):
        byte = b[p]
        p += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not (byte & 0x80):
            break
    if shift and (result & (1 << (shift - 1))):
        result -= 1 << shift
    return result, p


def read_cpool_counts(abc):
    """读常量池 8 个计数字段"""
    p = 4                                  # 跳过 minor + major
    names = ['int', 'uint', 'double', 'string',
             'namespace', 'ns_set', 'multiname', 'method']
    out = {}
    for nm in names:
        v, p = u30(abc, p)
        out[nm] = v
    return out, p


def scan_doabc(data, name_filter=None):
    fws = unwrap(data)
    tags_start = parse_header(fws)
    results = []

    for code, body, length, tag_off in iter_tags(fws, tags_start):
        if code != 82:                     # DoABC
            continue
        flags = struct.unpack('<I', fws[body:body + 4])[0]
        nul = fws.index(b'\x00', body + 4)
        name = fws[body + 4:nul].decode('utf-8', 'replace')
        abc_start = nul + 1
        abc_len = (body + length) - abc_start

        if name_filter and name_filter not in name:
            continue

        abc = fws[abc_start:abc_start + abc_len]
        minor = struct.unpack('<H', abc[0:2])[0]
        major = struct.unpack('<H', abc[2:4])[0]

        counts = {}
        try:
            counts, _ = read_cpool_counts(abc)
        except Exception:
            pass

        results.append({
            'tag_off': tag_off,
            'flags': flags,
            'name': name,
            'abc_start': abc_start,
            'abc_len': abc_len,
            'minor': minor,
            'major': major,
            'counts': counts,
            'blob': abc,
        })

    return results


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    path = sys.argv[1]
    name_filter = sys.argv[2] if len(sys.argv) > 2 else None

    data = open(path, 'rb').read()
    print('file %s  %d bytes' % (path, len(data)))

    blocks = scan_doabc(data, name_filter)
    print('DoABC blocks: %d\n' % len(blocks))

    for i, b in enumerate(blocks):
        print('DoABC#%d' % i)
        print('  tag@%-12d body flags=0x%08x' % (b['tag_off'], b['flags']))
        print('  name          %r' % b['name'])
        print('  abcStart      %d' % b['abc_start'])
        print('  abcLen        %d' % b['abc_len'])
        print('  version       minor=%d major=%d' % (b['minor'], b['major']))
        if b['counts']:
            c = b['counts']
            print('  cpool         int=%d uint=%d double=%d string=%d'
                  % (c['int'], c['uint'], c['double'], c['string']))
            print('                ns=%d nsset=%d multiname=%d method=%d'
                  % (c['namespace'], c['ns_set'], c['multiname'], c['method']))
        # 关键字符串探测
        for probe in (b'AppModel', b'inPlatform', b'easy', b'AllowScriptAccess', b'allowScriptAccess'):
            idx = b['blob'].find(probe)
            if idx >= 0:
                print('  contains %-22s @%d' % (probe.decode(), idx))
        print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
