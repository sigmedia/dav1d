#!/usr/bin/env python3
"""
Reader and visualizer for dav1d inspection output files.

Reads the binary files produced by dav1d's --inspect-dir option:
  - frame_N_blocks.bin   : per-4x4 block metadata
  - frame_N_residual_Y.bin, _U.bin, _V.bin : signed residual planes

Usage:
    # Residual as RGB PNG via YCbCr-to-RGB (residual treated as YCbCr offset)
    python inspect_reader.py /path/to/inspect_dir --frame 0 --residual --png -c rgb

    # Residual magnitude heatmap (single RGB PNG, viridis-like)
    python inspect_reader.py /path/to/inspect_dir --frame 0 --residual --png -c heat

    # Signed grayscale per-plane PNGs (gray=0, dark=negative, bright=positive)
    python inspect_reader.py /path/to/inspect_dir --frame 0 --residual --png -c signed

    # Dump block metadata for a frame
    python inspect_reader.py /path/to/inspect_dir --frame 0 --blocks

    # Batch export all frames as RGB PNG
    python inspect_reader.py /path/to/inspect_dir --all --residual --png -c rgb

    # Print residual statistics
    python inspect_reader.py /path/to/inspect_dir --frame 0 --residual --stats
"""

import argparse
import struct
import sys
import os
import glob
import numpy as np

# ── Binary format definitions ──────────────────────────────────────────────

# Dav1dInspectBlock: 24 bytes, see src/inspect_data.h
#   int8_t  ref_type[2]    offset 0
#   uint8_t ref_poc[2]     offset 2
#   uint8_t is_intra       offset 4
#   (1 byte pad)
#   int16_t mv_x[2]        offset 6
#   int16_t mv_y[2]        offset 10
#   uint8_t block_size     offset 14
#   uint8_t skip           offset 15
#   uint8_t inter_mode     offset 16
#   uint8_t comp_type      offset 17
#   (2 bytes pad)
#   float   bits           offset 20
BLOCK_STRUCT = struct.Struct("<2b 2B B x 2h 2h 4B 2x f")
assert BLOCK_STRUCT.size == 24

BLOCK_FIELDS = [
    "ref_type_0", "ref_type_1",
    "ref_poc_0", "ref_poc_1",
    "is_intra",
    "mv_x_0", "mv_x_1",
    "mv_y_0", "mv_y_1",
    "block_size", "skip", "inter_mode", "comp_type",
    "bits",
]

BLOCK_DTYPE = np.dtype([
    ("ref_type",   np.int8,   (2,)),
    ("ref_poc",    np.uint8,  (2,)),
    ("is_intra",   np.uint8),
    ("_pad0",      np.uint8),
    ("mv_x",       np.int16,  (2,)),
    ("mv_y",       np.int16,  (2,)),
    ("block_size", np.uint8),
    ("skip",       np.uint8),
    ("inter_mode", np.uint8),
    ("comp_type",  np.uint8),
    ("_pad1",      np.uint8,  (2,)),
    ("bits",       np.float32),
])
assert BLOCK_DTYPE.itemsize == 24


# ── Readers ────────────────────────────────────────────────────────────────

def read_residual_plane(path):
    """Read a residual plane binary file.

    Returns (width, height, data) where data is a (height, width) int16 ndarray.
    """
    with open(path, "rb") as f:
        w, h = struct.unpack("<ii", f.read(8))
        data = np.frombuffer(f.read(w * h * 2), dtype=np.int16).reshape(h, w)
    return w, h, data


def read_blocks(path):
    """Read a blocks binary file.

    Returns (w4, h4, b4_stride, frame_offset, blocks) where blocks is
    a structured ndarray of shape (h4, b4_stride).
    """
    with open(path, "rb") as f:
        w4, h4, b4_stride, frame_offset = struct.unpack("<4I", f.read(16))
        nb = h4 * b4_stride
        raw = f.read(nb * BLOCK_DTYPE.itemsize)
        blocks = np.frombuffer(raw, dtype=BLOCK_DTYPE).reshape(h4, b4_stride)
    return w4, h4, b4_stride, frame_offset, blocks


def find_frames(inspect_dir):
    """Discover all frame indices present in the output directory."""
    pattern = os.path.join(inspect_dir, "frame_*.json")
    frames = set()
    for p in glob.glob(pattern):
        base = os.path.basename(p)
        # frame_N_blocks.bin
        parts = base.split("_")
        if len(parts) >= 2:
            try:
                frames.add(int(parts[1].split(".")[0]))
            except ValueError:
                pass
    return sorted(frames)


# ── Visualization ──────────────────────────────────────────────────────────

def _upscale_chroma(chroma, target_h, target_w):
    """Upscale a chroma plane to luma resolution.

    Uses numpy repeat for exact 2x integer upscale (common 4:2:0 case),
    falls back to PIL bilinear for non-integer ratios.
    """
    ch, cw = chroma.shape
    h_ratio = target_h / ch
    w_ratio = target_w / cw

    # Fast path: exact 2x integer upscale (4:2:0)
    if h_ratio == int(h_ratio) and w_ratio == int(w_ratio):
        hr, wr = int(h_ratio), int(w_ratio)
        result = chroma.astype(np.float32)
        if hr > 1:
            result = np.repeat(result, hr, axis=0)
        if wr > 1:
            result = np.repeat(result, wr, axis=1)
        # Trim if chroma * ratio > target (due to rounding)
        return result[:target_h, :target_w]

    # Slow path: bilinear resize via PIL
    from PIL import Image
    img = Image.fromarray(chroma.astype(np.float32), mode="F")
    img = img.resize((target_w, target_h), Image.Resampling.BILINEAR)
    return np.array(img, dtype=np.float32)


def residual_to_rgb(y_data, u_data, v_data):
    """Convert signed YCbCr residual planes to an RGB image.

    The residual is centered at zero. We treat it as a YCbCr offset:
      Y  residual  -> mapped to [16, 235]  (128 = zero)
      Cb residual  -> mapped to [16, 240]  (128 = zero)
      Cr residual  -> mapped to [16, 240]  (128 = zero)
    Then standard BT.601 YCbCr-to-RGB conversion is applied.

    Chroma planes are upscaled to luma resolution before conversion.
    Returns an (H, W, 3) uint8 RGB array.
    """
    h, w = y_data.shape

    # Upscale chroma to luma resolution
    u_full = _upscale_chroma(u_data, h, w)
    v_full = _upscale_chroma(v_data, h, w)

    # Normalize each channel: map [-max_abs, +max_abs] -> [0, 255], zero=128
    def normalize_signed(arr):
        ma = max(abs(arr.min()), abs(arr.max()), 1)
        return arr * (127.0 / ma) + 128.0

    y_norm = normalize_signed(y_data.astype(np.float32))
    cb_norm = normalize_signed(u_full)
    cr_norm = normalize_signed(v_full)

    # BT.601 YCbCr to RGB (full-range):
    cb_off = cb_norm - 128.0
    cr_off = cr_norm - 128.0
    r = y_norm + 1.402 * cr_off
    g = y_norm - 0.344136 * cb_off - 0.714136 * cr_off
    b = y_norm + 1.772 * cb_off

    rgb = np.stack([r, g, b], axis=-1)
    return rgb.clip(0, 255).astype(np.uint8)


def residual_to_heatmap(y_data, u_data, v_data):
    """Convert residual planes to an RGB magnitude heatmap.

    Computes per-pixel energy as sqrt(Y^2 + U^2 + V^2) (chroma upscaled),
    then maps to a blue -> cyan -> green -> yellow -> red colormap.
    Returns an (H, W, 3) uint8 RGB array.
    """
    h, w = y_data.shape

    y_f = y_data.astype(np.float32)
    u_full = _upscale_chroma(u_data, h, w)
    v_full = _upscale_chroma(v_data, h, w)

    # Per-pixel energy (RMS of Y, U, V)
    energy = np.sqrt(y_f**2 + u_full**2 + v_full**2)
    max_e = energy.max()
    if max_e == 0:
        return np.zeros((h, w, 3), dtype=np.uint8)
    norm = energy / max_e  # [0, 1]

    # 5-stop colormap via np.interp (vectorized, no boolean masks):
    # black -> blue -> cyan -> yellow -> red
    xp = [0.0, 0.25, 0.50, 0.75, 1.0]
    r = np.interp(norm, xp, [0, 0, 0, 255, 255])
    g = np.interp(norm, xp, [0, 0, 255, 255, 0])
    b = np.interp(norm, xp, [0, 255, 255, 0, 0])

    rgb = np.stack([r, g, b], axis=-1)
    return rgb.astype(np.uint8)


def residual_to_image(data, colormap="signed"):
    """Convert a signed int16 residual array to an 8-bit grayscale image.

    colormap options:
      "signed"   - map [-max_abs, +max_abs] -> [0, 255], zero = 128
      "abs"      - map absolute value [0, max_abs] -> [0, 255]
    """
    if data.size == 0:
        return np.zeros(data.shape, dtype=np.uint8)

    if colormap == "abs":
        abs_data = np.abs(data.astype(np.float32))
        max_val = abs_data.max()
        if max_val == 0:
            return np.zeros(data.shape, dtype=np.uint8)
        return (abs_data / max_val * 255).clip(0, 255).astype(np.uint8)

    elif colormap == "signed":
        fdata = data.astype(np.float32)
        max_abs = max(abs(fdata.min()), abs(fdata.max()), 1)
        return ((fdata / max_abs) * 127 + 128).clip(0, 255).astype(np.uint8)

    else:
        raise ValueError(f"Unknown colormap: {colormap}")


def _load_residual_planes(inspect_dir, frame_idx):
    """Load Y, U, V residual planes from binary files.

    Returns dict of {name: (w, h, data)} for planes that exist.
    """
    planes = {}
    for name in ("Y", "U", "V"):
        path = os.path.join(inspect_dir, f"frame_{frame_idx}_residual_{name}.bin")
        if os.path.exists(path):
            w, h, data = read_residual_plane(path)
            planes[name] = (w, h, data)
    return planes


def save_residual_png(inspect_dir, frame_idx, output_path=None, colormap="rgb"):
    """Save residual planes as PNG image(s).

    colormap:
      "rgb"    - single RGB PNG via YCbCr-to-RGB conversion (default)
      "heat"   - single RGB PNG magnitude heatmap
      "signed" - separate grayscale PNGs per plane (gray=0)
      "abs"    - separate grayscale PNGs per plane (black=0)
    """
    from PIL import Image

    planes = _load_residual_planes(inspect_dir, frame_idx)
    if not planes:
        print(f"No residual files found for frame {frame_idx}", file=sys.stderr)
        return

    # RGB modes: produce a single combined RGB image
    if colormap in ("rgb", "heat") and "Y" in planes:
        yw, yh, ydata = planes["Y"]
        # Get chroma, default to zeros if missing (monochrome)
        if "U" in planes:
            _, _, udata = planes["U"]
        else:
            udata = np.zeros_like(ydata)
        if "V" in planes:
            _, _, vdata = planes["V"]
        else:
            vdata = np.zeros_like(ydata)

        if colormap == "rgb":
            rgb = residual_to_rgb(ydata, udata, vdata)
        else:
            rgb = residual_to_heatmap(ydata, udata, vdata)

        out = output_path or os.path.join(
            inspect_dir, f"frame_{frame_idx}_residual.png")
        Image.fromarray(rgb).save(out)
        print(f"Saved {colormap} residual: {out} ({yw}x{yh})")

    else:
        # Per-plane grayscale
        for name, (w, h, data) in planes.items():
            img_data = residual_to_image(data, colormap)
            out = output_path
            if out is None or len(planes) > 1:
                out = os.path.join(inspect_dir,
                                   f"frame_{frame_idx}_residual_{name}.png")
            Image.fromarray(img_data).save(out)
            print(f"Saved {name} residual: {out} ({w}x{h})")


def print_residual_stats(inspect_dir, frame_idx):
    """Print statistics about residual planes."""
    for name in ("Y", "U", "V"):
        path = os.path.join(inspect_dir, f"frame_{frame_idx}_residual_{name}.bin")
        if not os.path.exists(path):
            continue
        w, h, data = read_residual_plane(path)
        total = data.size
        nonzero = np.count_nonzero(data)
        print(f"  {name} plane: {w}x{h}")
        print(f"    range:   [{data.min()}, {data.max()}]")
        print(f"    mean:    {data.mean():.2f}")
        print(f"    std:     {data.std():.2f}")
        print(f"    nonzero: {nonzero}/{total} ({100*nonzero/total:.1f}%)")
        print(f"    mean|r|: {np.abs(data.astype(np.float32)).mean():.2f}")


def print_block_summary(inspect_dir, frame_idx):
    """Print summary of block metadata."""
    path = os.path.join(inspect_dir, f"frame_{frame_idx}_blocks.bin")
    if not os.path.exists(path):
        print(f"No blocks file for frame {frame_idx}", file=sys.stderr)
        return

    w4, h4, b4_stride, frame_offset, blocks = read_blocks(path)
    # Only look at the valid region (w4 columns)
    valid = blocks[:h4, :w4] if w4 <= b4_stride else blocks[:h4]
    total = valid.size

    intra_count = np.sum(valid["is_intra"] == 1)
    inter_count = np.sum(valid["is_intra"] == 0)
    skip_count = np.sum(valid["skip"] == 1)

    print(f"  Frame offset: {frame_offset}")
    print(f"  Grid: {w4}x{h4} (4x4 blocks), stride={b4_stride}")
    print(f"  Total 4x4 units: {total}")
    print(f"  Intra: {intra_count} ({100*intra_count/total:.1f}%)")
    print(f"  Inter: {inter_count} ({100*inter_count/total:.1f}%)")
    print(f"  Skip:  {skip_count} ({100*skip_count/total:.1f}%)")

    if inter_count > 0:
        inter_mask = valid["is_intra"] == 0
        mvx0 = valid["mv_x"][inter_mask, 0]
        mvy0 = valid["mv_y"][inter_mask, 0]
        print(f"  MV[0] range: x=[{mvx0.min()}, {mvx0.max()}], "
              f"y=[{mvy0.min()}, {mvy0.max()}] (1/8-pel)")

    # Bit cost statistics
    bits = valid["bits"].flatten()
    total_bits = bits.sum()
    if total_bits > 0:
        nonzero_bits = bits[bits > 0]
        print(f"  Bits: total={total_bits:.0f}, mean/b4={bits.mean():.2f}, "
              f"max/b4={bits.max():.2f}, nonzero={len(nonzero_bits)}/{len(bits)}")


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Read and visualize dav1d inspection output files.")
    parser.add_argument("inspect_dir", help="Directory containing inspection output")
    parser.add_argument("--frame", "-f", type=int, default=None,
                        help="Frame index to process (default: list available)")
    parser.add_argument("--all", "-a", action="store_true",
                        help="Process all frames")
    parser.add_argument("--residual", "-r", action="store_true",
                        help="Process residual planes")
    parser.add_argument("--blocks", "-b", action="store_true",
                        help="Process block metadata")
    parser.add_argument("--png", action="store_true",
                        help="Save residual as PNG image(s)")
    parser.add_argument("--colormap", "-c", default="rgb",
                        choices=["rgb", "heat", "signed", "abs"],
                        help="Colormap for PNG: rgb (YCbCr->RGB, default), "
                             "heat (magnitude heatmap), signed (grayscale per-plane), "
                             "abs (absolute grayscale per-plane)")
    parser.add_argument("--stats", "-s", action="store_true",
                        help="Print statistics")
    parser.add_argument("--output", "-o", default=None,
                        help="Output path (for single-frame PNG)")
    args = parser.parse_args()

    if not os.path.isdir(args.inspect_dir):
        print(f"Error: {args.inspect_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    frames = find_frames(args.inspect_dir)
    if not frames:
        print(f"No inspection files found in {args.inspect_dir}", file=sys.stderr)
        sys.exit(1)

    # Default: list available frames
    if args.frame is None and not args.all:
        print(f"Available frames: {frames}")
        print(f"Use --frame N or --all to select frames.")
        return

    target_frames = frames if args.all else [args.frame]

    for fidx in target_frames:
        print(f"Frame {fidx}:")

        if args.blocks or args.stats:
            print_block_summary(args.inspect_dir, fidx)

        if args.residual:
            if args.stats:
                print_residual_stats(args.inspect_dir, fidx)
            if args.png:
                save_residual_png(args.inspect_dir, fidx,
                                  output_path=args.output,
                                  colormap=args.colormap)

        if not args.blocks and not args.residual:
            print("  Specify --residual and/or --blocks")

        print()


if __name__ == "__main__":
    main()
