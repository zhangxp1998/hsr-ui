"""Read-only SRAM/ENCR adapter. No target code is executed.

ENCR/mr0k logic is adapted from AnimeStudio (MIT); see THIRD_PARTY_NOTICES.md.
Unity object parsing, texture decoding and Sprite packing use UnityPy, not this
adapter. Upstream format tables are fetched explicitly, pinned and hash checked.
"""
from pathlib import Path
import hashlib
import re
import struct
import urllib.request

UPSTREAM = 'https://raw.githubusercontent.com/Escartem/AnimeStudio/76234e9f6f5a839504f41f9612719529fe2309a5/'
TABLES = {
    'AES.cs': ('AnimeStudio/Crypto/AES.cs', '0463e707511ede087799849d050ce658c9c1f0aa44099111e1b23bd06309fe8b'),
    'CryptoHelper.cs': ('AnimeStudio/Crypto/CryptoHelper.cs', '68d3169d9d0bce93c1a70b858ac0843136fb197a426cb040ab9e5f85f0b0688d'),
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def prepare_codec(directory):
    """Explicit network action; normal export never downloads executable code."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, (remote, expected) in TABLES.items():
        path = directory / name
        data = path.read_bytes() if path.is_file() else urllib.request.urlopen(UPSTREAM + remote, timeout=60).read()
        require(sha256(data) == expected, 'upstream table hash mismatch: ' + name)
        path.write_bytes(data)
    return {'files_verified': len(TABLES), 'upstream': UPSTREAM}


class SRAM:
    """Versioned resource index; IDs alone must never cross index hashes."""
    def __init__(self, data):
        require(data[:8] == b'SRAM\0\5\0\1', 'unsupported SRAM signature/version')
        require(len(data) >= 168, 'truncated SRAM header')
        require(struct.unpack_from('<IHH', data, 8) == (40, 8, 16), 'unsupported SRAM layout')
        self.data = data
        self.sha256 = sha256(data)
        self.sections = [struct.unpack_from('<4I', data, 40 + i * 16)[1:] for i in range(8)]
        for offset, count, stride in self.sections:
            require(offset + count * stride <= len(data), 'SRAM section outside input')
        require([self.sections[i][2] for i in (0, 1, 2)] == [24, 4, 32], 'unsupported SRAM strides')
        self.count = self.sections[2][1]

    def bundle(self, index):
        require(0 <= index < self.count, 'bundle index outside SRAM')
        row = struct.unpack_from('<8I', self.data, self.sections[2][0] + index * 32)
        require(row[0] == index and row[1] < self.sections[0][1], 'invalid bundle row')
        start = self.sections[0][0] + row[1] * 24
        raw = self.data[start:start + 16]
        name = b''.join(raw[i:i+4][::-1] for i in range(0, 16, 4)).hex() + '.block'
        _, size = struct.unpack_from('<II', self.data, start + 16)
        require(row[3] >= 25 and row[2] + row[3] <= size, 'bundle range outside block')
        count = row[7] & 0xffff
        require(row[6] + count <= self.sections[1][1], 'dependency range outside SRAM')
        deps = struct.unpack_from('<' + str(count) + 'I', self.data, self.sections[1][0] + row[6] * 4)
        require(all(x < self.count for x in deps), 'dependency ID outside SRAM')
        return dict(index=index, block=name, offset=row[2], length=row[3], dependencies=list(deps))


class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def unpack(self, fmt):
        size = struct.calcsize('>' + fmt)
        require(self.pos + size <= len(self.data), 'truncated ENCR table')
        result = struct.unpack_from('>' + fmt, self.data, self.pos)
        self.pos += size
        return result

    def string(self):
        end = self.data.find(b'\0', self.pos)
        require(self.pos <= end <= self.pos + 4096, 'invalid ENCR node name')
        result = self.data[self.pos:end].decode('utf-8')
        self.pos = end + 1
        require(result and '/' not in result and '\\' not in result and result not in ('.', '..'), 'unsafe ENCR node name')
        return result


class Codec:
    def __init__(self, directory, max_bytes=256 * 1024 * 1024):
        self.max_bytes = max_bytes
        sources = {}
        for name, (_, expected) in TABLES.items():
            data = (Path(directory) / name).read_bytes()
            require(sha256(data) == expected, 'upstream table hash mismatch: ' + name)
            sources[name] = data.decode('utf-8-sig')

        def table(source, name, size):
            match = re.search(r'\b' + name + r'\s*=.*?\{([^}]+)\}', sources[source], re.S)
            require(match is not None, 'missing upstream table: ' + name)
            result = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]+)', match[1]))
            require(len(result) == size, 'unexpected upstream table size: ' + name)
            return result

        self.ek = table('CryptoHelper.cs', 'Mr0kExpansionKey', 176)
        self.iv = table('CryptoHelper.cs', 'Mr0kInitVector', 16)
        # Length is pinned by the source digest, not an assumption about a key.
        match = re.search(r'\bMr0kBlockKey\s*=.*?\{([^}]+)\}', sources['CryptoHelper.cs'], re.S)
        self.bk = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]+)', match[1]))
        require(bool(self.bk), 'missing mr0k block table')
        self.sb = table('AES.cs', 'LookupSBoxInv', 256)
        self.sr = table('AES.cs', 'ShiftRowsTableInv', 16)
        self.gm = {n: table('AES.cs', 'LookupG' + str(n), 256) for n in (9, 11, 13, 14)}

    def decrypt16(self, block):
        require(len(block) == 16, 'invalid mr0k block')
        c = [a ^ b for a, b in zip(block, self.ek[:16])]
        g = self.gm
        for rnd in range(1, 11):
            c = [self.sb[c[i]] for i in self.sr]
            if rnd < 10:
                out = []
                for k in range(0, 16, 4):
                    a, b, d, e = c[k:k+4]
                    out += [g[14][a] ^ g[9][e] ^ g[13][d] ^ g[11][b],
                            g[14][b] ^ g[9][a] ^ g[13][e] ^ g[11][d],
                            g[14][d] ^ g[9][b] ^ g[13][a] ^ g[11][e],
                            g[14][e] ^ g[9][d] ^ g[13][b] ^ g[11][a]]
                c = out
            c = [v ^ self.ek[16*rnd+i] for i, v in enumerate(c)]
        return bytes(c)

    def decrypt(self, data):
        if not data.startswith(b'mr0k'):
            return data
        require(len(data) >= 0x94, 'truncated mr0k payload')
        b = bytearray(data)
        k1 = self.decrypt16(b[4:20])
        k2 = bytes(a ^ c for a, c in zip(b[0x74:0x84], self.iv))
        k3 = self.decrypt16(b[0x84:0x94])
        b[0x84:0x94] = bytes(a ^ c for a, c in zip(k1, k3))
        s1, s2 = int.from_bytes(k2[:8], 'little'), int.from_bytes(k3[:8], 'little')
        seed = (s2 ^ s1 ^ ((s1 + len(b) - 20) & ((1 << 64) - 1))).to_bytes(8, 'little')
        for i in range(min(16 * ((len(b) - 0x94) >> 7), 0x400)):
            b[0x94+i] ^= seed[i % 8] ^ self.bk[i % len(self.bk)]
        return bytes(b[20:])

    def decode(self, data, size, kind):
        require(0 <= size <= self.max_bytes, 'decoded block exceeds byte limit')
        if kind == 0:
            result = data
        elif kind in (2, 3, 5):
            import lz4.block
            result = lz4.block.decompress(self.decrypt(data) if kind == 5 else data, uncompressed_size=size)
        elif kind in (6, 7):
            import ooz
            result = ooz.decompress(self.decrypt(data) if kind == 7 else data, size)
        else:
            raise ValueError('unsupported ENCR compression: ' + str(kind))
        require(len(result) == size, 'decoded block length mismatch')
        return result

    def nodes(self, data):
        require(25 <= len(data) <= self.max_bytes and data[:5] == b'ENCR\0', 'invalid ENCR bundle')
        size, packed, unpacked, flags = struct.unpack_from('>QIII', data, 5)
        require(size == len(data) and 0 < packed <= size - 25, 'ENCR size mismatch')
        info_start = size - packed if flags & 0x80 else 25
        info = Reader(self.decode(data[info_start:info_start+packed], unpacked, flags & 0x3f))
        count, = info.unpack('I')
        require(count <= len(info.data) // 10, 'invalid ENCR block count')
        blocks = [info.unpack('IIH') for _ in range(count)]
        require(sum(x[0] for x in blocks) <= self.max_bytes, 'bundle exceeds decoded byte limit')
        count, = info.unpack('I')
        require(count <= len(info.data) // 21, 'invalid ENCR node count')
        entries = []
        for _ in range(count):
            offset, length, _ = info.unpack('QQI')
            entries.append((info.string(), offset, length))
        require(info.pos == len(info.data), 'trailing ENCR info bytes')
        cursor = 25 if flags & 0x80 else 25 + packed
        if flags & 0x200:
            cursor = (cursor + 15) // 16 * 16
        end = info_start if flags & 0x80 else size
        parts = []
        for unpacked, packed, block_flags in blocks:
            require(cursor + packed <= end, 'compressed block outside bundle')
            parts.append(self.decode(data[cursor:cursor+packed], unpacked, block_flags & 0x3f))
            cursor += packed
        require(cursor == end, 'trailing ENCR data bytes')
        raw = b''.join(parts)
        result = {}
        for name, offset, length in entries:
            require(offset + length <= len(raw) and name not in result, 'invalid or duplicate ENCR node')
            result[name] = raw[offset:offset+length]
        return result
