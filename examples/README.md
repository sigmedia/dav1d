# dav1d Inspection Examples

This directory contains example scripts for working with dav1d inspection output.

## read_blocksize_json.py

Reads and analyzes block size maps from JSON inspection files.

### Usage

```bash
# Generate inspection JSON files
./dav1d -i input.ivf --inspect-dir output_dir

# Analyze block sizes
python3 examples/read_blocksize_json.py output_dir/frame_0000.json
```

### Output

The script provides:
- Frame dimensions (in pixels and 4x4 units)
- Block size distribution statistics
- ASCII visualization of the block size map
- Example of accessing individual blocks

### Example Output

```
Frame dimensions: 1920×1080 pixels (480×270 in 4x4 units)

Block Size Distribution (in 4x4 units):
Block Size           Count  Percentage
----------------------------------------
BLOCK_16X16          45600      35.19%
BLOCK_32X32          28800      22.22%
BLOCK_64X64          32400      25.00%
...

Block Size Map (showing top-left 20×40 4x4 units):
  0123456789012345678901234567890123456789
 0 CCCCCCCCCCCC999999999999666666666666666
 1 CCCCCCCCCCCC999999999999666666666666666
 2 CCCCCCCCCCCC999999999999666666666666666
...

Legend:
  0=4x4, 1=4x8, 2=8x4, 3=8x8, 4=8x16, 5=16x8, 6=16x16, 7=16x32
  8=32x16, 9=32x32, A=32x64, B=64x32, C=64x64, D=64x128, E=128x64, F=128x128

Example access: Block at 4x4 position (10, 20) = pixel position (40, 80)
  Block size: BLOCK_16X16 (16×16 pixels)
```

## Block Size Reference

| Index | Name | Width (px) | Height (px) |
|-------|------|-----------|------------|
| 0 | BLOCK_4X4 | 4 | 4 |
| 1 | BLOCK_4X8 | 4 | 8 |
| 2 | BLOCK_8X4 | 8 | 4 |
| 3 | BLOCK_8X8 | 8 | 8 |
| 4 | BLOCK_8X16 | 8 | 16 |
| 5 | BLOCK_16X8 | 16 | 8 |
| 6 | BLOCK_16X16 | 16 | 16 |
| 7 | BLOCK_16X32 | 16 | 32 |
| 8 | BLOCK_32X16 | 32 | 16 |
| 9 | BLOCK_32X32 | 32 | 32 |
| 10 | BLOCK_32X64 | 32 | 64 |
| 11 | BLOCK_64X32 | 64 | 32 |
| 12 | BLOCK_64X64 | 64 | 64 |
| 13 | BLOCK_64X128 | 64 | 128 |
| 14 | BLOCK_128X64 | 128 | 64 |
| 15 | BLOCK_128X128 | 128 | 128 |
| 16 | BLOCK_4X16 | 4 | 16 |
| 17 | BLOCK_16X4 | 16 | 4 |
| 18 | BLOCK_8X32 | 8 | 32 |
| 19 | BLOCK_32X8 | 32 | 8 |
| 20 | BLOCK_16X64 | 16 | 64 |
| 21 | BLOCK_64X16 | 64 | 16 |

## JSON Output Formats

dav1d can output inspection data in two JSON formats:

### Flat Format (default)

Uncompressed 2D arrays:
```json
{
  "blockSize": [
    [12, 12, 12, 9, 9, 9, ...],
    [12, 12, 12, 9, 9, 9, ...],
    ...
  ],
  ...
}
```

### RLE Compressed Format (--inspect-compress)

Run-length encoded format where `value,[count]` means repeat `value` a total of `count+1` times:
```json
{
  "blockSize": [
    [12,[2], 9,[5], 6,[8]],  // 3× 12, 6× 9, 9× 6
    ...
  ],
  ...
}
```

Enable with: `./dav1d -i input.ivf --inspect-dir output_dir --inspect-compress`

## Performance: JSON vs Binary

For maximum speed, use **binary format** instead of JSON:

| Format | Write Speed | Read Speed | File Size |
|--------|------------|-----------|-----------|
| Binary | ~50 MB/s | ~500 MB/s | 24 bytes/block |
| JSON (flat) | ~2 MB/s | ~10 MB/s | ~150 bytes/block |
| JSON (RLE) | ~1 MB/s | ~5 MB/s | ~50-100 bytes/block |

Binary files are **10-50× faster** to read/write and use much less disk space.

See `tools/inspect_reader.py` for reading binary inspection files.
