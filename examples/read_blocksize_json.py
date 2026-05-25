#!/usr/bin/env python3
"""
Example: Read and visualize block sizes from dav1d inspection JSON output.

Usage:
    python3 read_blocksize_json.py frame_0000.json
"""

import json
import sys
from collections import Counter

# Block size lookup table: index -> (width_px, height_px, name)
BLOCK_INFO = {
    0: (4, 4, "BLOCK_4X4"),
    1: (4, 8, "BLOCK_4X8"),
    2: (8, 4, "BLOCK_8X4"),
    3: (8, 8, "BLOCK_8X8"),
    4: (8, 16, "BLOCK_8X16"),
    5: (16, 8, "BLOCK_16X8"),
    6: (16, 16, "BLOCK_16X16"),
    7: (16, 32, "BLOCK_16X32"),
    8: (32, 16, "BLOCK_32X16"),
    9: (32, 32, "BLOCK_32X32"),
    10: (32, 64, "BLOCK_32X64"),
    11: (64, 32, "BLOCK_64X32"),
    12: (64, 64, "BLOCK_64X64"),
    13: (64, 128, "BLOCK_64X128"),
    14: (128, 64, "BLOCK_128X64"),
    15: (128, 128, "BLOCK_128X128"),
    16: (4, 16, "BLOCK_4X16"),
    17: (16, 4, "BLOCK_16X4"),
    18: (8, 32, "BLOCK_8X32"),
    19: (32, 8, "BLOCK_32X8"),
    20: (16, 64, "BLOCK_16X64"),
    21: (64, 16, "BLOCK_64X16"),
}


def parse_rle_array(rle_row):
    """
    Parse RLE-encoded row: [value, value,[count], value, ...]
    Returns flat list of values.
    """
    result = []
    i = 0
    while i < len(rle_row):
        value = rle_row[i]
        if i + 1 < len(rle_row) and isinstance(rle_row[i + 1], list):
            # RLE: value,[count] means repeat value (count+1) times
            count = rle_row[i + 1][0]
            result.extend([value] * (count + 1))
            i += 2
        else:
            # Single value
            result.append(value)
            i += 1
    return result


def read_block_sizes(json_path):
    """
    Read block size map from JSON inspection file.
    Returns: (width_4x4, height_4x4, block_sizes_2d)
    where block_sizes_2d[row][col] = block_size_index
    """
    with open(json_path, 'r') as f:
        frame = json.load(f)
    
    block_sizes_rle = frame.get('blockSize', [])
    
    # Detect if RLE or flat format by checking if any element is a list
    is_rle = any(isinstance(elem, list) for row in block_sizes_rle for elem in row)
    
    if is_rle:
        # Parse RLE format
        block_sizes_2d = [parse_rle_array(row) for row in block_sizes_rle]
    else:
        # Already flat
        block_sizes_2d = block_sizes_rle
    
    height_4x4 = len(block_sizes_2d)
    width_4x4 = len(block_sizes_2d[0]) if height_4x4 > 0 else 0
    
    return width_4x4, height_4x4, block_sizes_2d


def analyze_block_sizes(block_sizes_2d):
    """
    Analyze block size distribution.
    Returns dict: {block_size_index: count_of_4x4_units}
    """
    flat = [bs for row in block_sizes_2d for bs in row]
    return Counter(flat)


def print_block_map(block_sizes_2d, max_rows=20, max_cols=40):
    """
    Print ASCII visualization of block size map.
    """
    height = min(len(block_sizes_2d), max_rows)
    width = min(len(block_sizes_2d[0]), max_cols) if height > 0 else 0
    
    print(f"\nBlock Size Map (showing top-left {height}×{width} 4x4 units):")
    print("  " + "".join(f"{c%10}" for c in range(width)))
    
    for r in range(height):
        row_str = "".join(f"{block_sizes_2d[r][c]:X}" for c in range(width))
        print(f"{r:2} {row_str}")
    
    print("\nLegend:")
    print("  0=4x4, 1=4x8, 2=8x4, 3=8x8, 4=8x16, 5=16x8, 6=16x16, 7=16x32")
    print("  8=32x16, 9=32x32, A=32x64, B=64x32, C=64x64, D=64x128, E=128x64, F=128x128")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <frame_XXXX.json>", file=sys.stderr)
        print("\nExample: python3 read_blocksize_json.py frame_0000.json")
        sys.exit(1)
    
    json_path = sys.argv[1]
    
    # Read block sizes
    width_4x4, height_4x4, block_sizes_2d = read_block_sizes(json_path)
    width_px = width_4x4 * 4
    height_px = height_4x4 * 4
    
    print(f"Frame dimensions: {width_px}×{height_px} pixels ({width_4x4}×{height_4x4} in 4x4 units)")
    
    # Analyze distribution
    distribution = analyze_block_sizes(block_sizes_2d)
    
    print("\nBlock Size Distribution (in 4x4 units):")
    print(f"{'Block Size':<20} {'Count':>8} {'Percentage':>10}")
    print("-" * 40)
    
    total_4x4 = width_4x4 * height_4x4
    for bs_idx in sorted(distribution.keys()):
        count = distribution[bs_idx]
        percentage = (count / total_4x4) * 100
        w, h, name = BLOCK_INFO.get(bs_idx, (0, 0, f"UNKNOWN_{bs_idx}"))
        print(f"{name:<20} {count:>8} {percentage:>9.2f}%")
    
    # Print visual map
    print_block_map(block_sizes_2d)
    
    # Example: Access specific block
    if height_4x4 > 10 and width_4x4 > 20:
        row, col = 10, 20
        bs_idx = block_sizes_2d[row][col]
        w, h, name = BLOCK_INFO[bs_idx]
        print(f"\nExample access: Block at 4x4 position ({row}, {col}) = pixel position ({row*4}, {col*4})")
        print(f"  Block size: {name} ({w}×{h} pixels)")


if __name__ == '__main__':
    main()
