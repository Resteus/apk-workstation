import zipfile
import struct

with zipfile.ZipFile('templates/base.apk', 'r') as z:
    arsc = z.read('resources.arsc')

# 1. Parse Table Header
tbl_type, tbl_hsize, tbl_size, pkg_count = struct.unpack('<HHII', arsc[:12])
print(f"[*] ResTable: type=0x{tbl_type:04x}, headerSize={tbl_hsize}, size={tbl_size}")

# 2. Parse String Pool Header
sp_offset = tbl_hsize
sp_type, sp_hsize, sp_size, str_count, style_count, flags, str_start, style_start = struct.unpack(
    '<HHIIIIII', arsc[sp_offset:sp_offset+28]
)
is_utf8 = bool(flags & (1 << 8))
print(f"[*] StringPool: count={str_count}, is_utf8={is_utf8}, stringsStartOffset={str_start}")

# 3. Locate 'Smart WebView' occurrences
target = b'Smart WebView'
pos = 0
matches = []
while True:
    idx = arsc.find(target, pos)
    if idx == -1:
        break
    matches.append(idx)
    pos = idx + len(target)

print(f"[*] Found {len(matches)} occurrence(s) of '{target.decode()}' at binary offset(s): {matches}")
