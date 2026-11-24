import struct

def encode_utf8_len(val):
    if val <= 0x7F:
        return bytes([val])
    return bytes([((val >> 8) & 0x7F) | 0x80, val & 0xFF])

def patch_arsc_app_name(arsc_bytes, new_name):
    # 1. ResTable Header (12 bytes)
    tbl_type, tbl_hsize, tbl_size, pkg_count = struct.unpack('<HHII', arsc_bytes[:12])
    
    # 2. StringPool Header (28 bytes at offset tbl_hsize)
    sp_offset = tbl_hsize
    sp_type, sp_hsize, sp_size, str_count, style_count, flags, strings_start, styles_start = struct.unpack(
        '<HHIIIIII', arsc_bytes[sp_offset:sp_offset + 28]
    )

    # 3. Read String Offset Table
    indices_start = sp_offset + sp_hsize
    indices = list(struct.unpack(f'<{str_count}I', arsc_bytes[indices_start:indices_start + str_count * 4]))

    # 4. Locate 'Smart WebView' index
    target_bytes = b'Smart WebView'
    pool_data_start = sp_offset + strings_start
    target_idx = None

    for i, rel_off in enumerate(indices):
        abs_pos = pool_data_start + rel_off
        # Length prefixes: uleb128 char length, uleb128 byte length
        c_len = arsc_bytes[abs_pos]
        c_shift = 1 if c_len < 0x80 else 2
        b_len = arsc_bytes[abs_pos + c_shift]
        b_shift = 1 if b_len < 0x80 else 2
        str_start = abs_pos + c_shift + b_shift
        
        if arsc_bytes[str_start:str_start + len(target_bytes)] == target_bytes:
            target_idx = i
            old_entry_len = (c_shift + b_shift) + b_len + 1  # includes trailing null
            break

    if target_idx is None:
        raise ValueError("Target label 'Smart WebView' not located in ARSC string pool.")

    # 5. Build New String Entry
    new_name_bytes = new_name.encode('utf-8')
    new_char_len = encode_utf8_len(len(new_name))
    new_byte_len = encode_utf8_len(len(new_name_bytes))
    new_entry = new_char_len + new_byte_len + new_name_bytes + b'\x00'

    raw_delta = len(new_entry) - old_entry_len

    # 6. Adjust offsets for all strings following the target
    new_indices = []
    for i, off in enumerate(indices):
        if i <= target_idx:
            new_indices.append(off)
        else:
            new_indices.append(off + raw_delta)

    # 7. 4-byte padding alignment for the StringPool chunk
    pad_needed = (4 - ((sp_size + raw_delta) % 4)) % 4
    total_delta = raw_delta + pad_needed

    new_sp_size = sp_size + total_delta
    new_tbl_size = tbl_size + total_delta

    # 8. Reassemble the binary ARSC buffer
    target_abs_pos = pool_data_start + indices[target_idx]
    
    # Split string pool data before and after target entry
    before_str = arsc_bytes[pool_data_start:target_abs_pos]
    after_str = arsc_bytes[target_abs_pos + old_entry_len:sp_offset + sp_size]

    # Reconstruct headers and tables
    new_tbl_header = struct.pack('<HHII', tbl_type, tbl_hsize, new_tbl_size, pkg_count)
    new_sp_header = struct.pack(
        '<HHIIIIII', sp_type, sp_hsize, new_sp_size, str_count, style_count, flags, strings_start, styles_start
    )
    new_indices_bytes = struct.pack(f'<{str_count}I', *new_indices)

    remainder = arsc_bytes[sp_offset + sp_size:]  # Package chunks, types, specs

    patched_arsc = (
        new_tbl_header +
        new_sp_header +
        new_indices_bytes +
        before_str +
        new_entry +
        after_str +
        (b'\x00' * pad_needed) +
        remainder
    )

    return patched_arsc

if __name__ == '__main__':
    import zipfile
    with zipfile.ZipFile('templates/base.apk', 'r') as z:
        raw_arsc = z.read('resources.arsc')
    
    test_patched = patch_arsc_app_name(raw_arsc, "Store Manager")
    with open('test_patched.arsc', 'wb') as f:
        f.write(test_patched)
    print(f"[+] Patched ARSC generated successfully ({len(raw_arsc)} -> {len(test_patched)} bytes).")
