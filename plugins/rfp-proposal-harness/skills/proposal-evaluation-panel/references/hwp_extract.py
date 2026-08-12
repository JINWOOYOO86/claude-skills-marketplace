import sys, olefile, zlib, struct, unicodedata

def extract_hwp_text(path):
    ole = olefile.OleFileIO(path)
    # FileHeader: check compression flag
    header = ole.openstream('FileHeader').read()
    compressed = bool(header[36] & 1)
    # collect BodyText sections
    secs = []
    for entry in ole.listdir():
        if entry[0]=='BodyText' and entry[-1].startswith('Section'):
            secs.append(entry)
    secs.sort(key=lambda e: int(e[-1].replace('Section','')))
    out=[]
    for e in secs:
        data = ole.openstream(e).read()
        if compressed:
            try: data = zlib.decompress(data, -15)
            except Exception: pass
        # parse HWP records: header = 4 bytes little-endian; tag_id=bits0-9, level 10-19, size 20-31
        i=0; n=len(data)
        while i+4<=n:
            hdr = struct.unpack('<I', data[i:i+4])[0]
            tag = hdr & 0x3ff
            size = (hdr>>20) & 0xfff
            i+=4
            if size==0xfff:
                if i+4>n: break
                size = struct.unpack('<I', data[i:i+4])[0]; i+=4
            payload = data[i:i+size]; i+=size
            if tag==67:  # HWPTAG_PARA_TEXT
                try:
                    text = payload.decode('utf-16le', errors='ignore')
                except Exception:
                    continue
                # filter control chars (inline objects use codes <32 except keep spacing)
                buf=[]
                for ch in text:
                    o=ord(ch)
                    if o>=32 or ch in '\n\t': buf.append(ch)
                    elif o in (13,): buf.append('\n')
                s=''.join(buf).strip()
                if s: out.append(s)
    ole.close()
    return '\n'.join(out)

if __name__=='__main__':
    t = extract_hwp_text(sys.argv[1])
    t = unicodedata.normalize('NFC', t)
    sys.stdout.write(t)
