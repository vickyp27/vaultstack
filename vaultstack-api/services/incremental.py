"""
True incremental backup — block-level delta creation and application.

VSDT format (VaultStack Delta):
  Header : magic(4) + virtual_size(8) + chunk_size(4)  = 16 bytes
  Blocks : [offset(8) + data_size(4) + data(N)]  repeated for every changed chunk
"""
import os, struct, subprocess, json

MAGIC      = b'VSDT'
CHUNK_SIZE = 1024 * 1024  # 1 MB


def _img_info(path: str) -> dict:
    r = subprocess.run(
        ["qemu-img", "info", "--output=json", path],
        capture_output=True, text=True, timeout=30,
    )
    return json.loads(r.stdout) if r.returncode == 0 else {}


def normalize_to_raw(img_path: str, raw_path: str) -> None:
    """Convert any qemu-supported image to raw format."""
    info = _img_info(img_path)
    fmt  = info.get("format", "raw")
    if fmt == "raw" and img_path == raw_path:
        return
    subprocess.run(
        ["qemu-img", "convert", f"-f{fmt}", "-Oraw", img_path, raw_path],
        check=True, capture_output=True,
    )


def create_delta(new_path: str, base_path: str, delta_path: str) -> dict:
    """
    Compare new_path vs base_path (both raw) and write only changed 1 MB chunks
    to delta_path in VSDT format.
    Returns stats dict.
    """
    new_size  = os.path.getsize(new_path)
    base_size = os.path.getsize(base_path)
    total     = (max(new_size, base_size) + CHUNK_SIZE - 1) // CHUNK_SIZE
    changed   = 0

    with open(new_path,   'rb') as nf, \
         open(base_path,  'rb') as bf, \
         open(delta_path, 'wb') as df:

        df.write(MAGIC)
        df.write(struct.pack('<QI', new_size, CHUNK_SIZE))

        offset = 0
        while True:
            n_chunk = nf.read(CHUNK_SIZE)
            if not n_chunk:
                break
            b_chunk = bf.read(CHUNK_SIZE) or b''
            if len(b_chunk) < len(n_chunk):
                b_chunk += b'\x00' * (len(n_chunk) - len(b_chunk))

            if n_chunk != b_chunk:
                df.write(struct.pack('<QI', offset, len(n_chunk)))
                df.write(n_chunk)
                changed += 1

            offset += len(n_chunk)

    ratio = changed / max(total, 1)
    print(f"[incremental] {changed}/{total} blocks changed ({ratio*100:.1f}%)")
    return {"total_blocks": total, "changed_blocks": changed, "change_ratio": round(ratio, 4)}


def apply_delta(base_path: str, delta_path: str, output_path: str) -> None:
    """
    Reconstruct the full raw image at output_path by applying delta to base.
    """
    import shutil

    with open(delta_path, 'rb') as df:
        magic = df.read(4)
        if magic != MAGIC:
            raise ValueError(f"Not a VSDT delta (magic={magic!r})")
        vsize, chunk_size = struct.unpack('<QI', df.read(12))

        shutil.copy2(base_path, output_path)
        with open(output_path, 'r+b') as of:
            cur = os.path.getsize(output_path)
            if cur < vsize:
                of.seek(vsize - 1); of.write(b'\x00')
            elif cur > vsize:
                of.truncate(vsize)

            while True:
                hdr = df.read(12)
                if len(hdr) < 12:
                    break
                offset, size = struct.unpack('<QI', hdr)
                data = df.read(size)
                of.seek(offset)
                of.write(data)

    print(f"[incremental] Delta applied → {output_path} ({vsize:,} bytes)")
