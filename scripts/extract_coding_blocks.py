#!/usr/bin/env python3
"""Extract coding-block map from dav1d inspect binaries.

Usage examples:
  python3 scripts/extract_coding_blocks.py --run --ivf 0018.ivf --outdir dav1d_inspect_out --frames 0 1 --format json
  python3 scripts/extract_coding_blocks.py --outdir dav1d_inspect_out --frames 0 --format csv
"""
import os
import sys
import argparse
import subprocess
import struct
import json
import csv

ENTRY_FMT = '<bbBBBxhhhhBBBBxxf'  # matches Dav1dInspectBlock on this host
ENTRY_SZ = struct.calcsize(ENTRY_FMT)

# block_size enum -> (width_px, height_px)
BS_PIXELS = [
    (128,128),(128,64),(64,128),(64,64),(64,32),(64,16),
    (32,64),(32,32),(32,16),(32,8),(16,64),(16,32),
    (16,16),(16,8),(16,4),(8,32),(8,16),(8,8),(8,4),
    (4,16),(4,8),(4,4),
]

def run_dav1d(inspect_dir, ivf, limit):
    os.makedirs(inspect_dir, exist_ok=True)
    cmd = ['tools/dav1d', '--inspect-dir', inspect_dir, '-i', ivf, '-o', '/dev/null', '--limit', str(limit)]
    print('Running:', ' '.join(cmd))
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        print('dav1d failed:', r.returncode, file=sys.stderr)
        print(r.stdout.decode(), file=sys.stderr)
        print(r.stderr.decode(), file=sys.stderr)
        sys.exit(1)

def read_blocks_bin(path):
    with open(path, 'rb') as f:
        hdr = f.read(16)
        if len(hdr) < 16:
            raise ValueError('header too small')
        w4,h4,stride,frame = struct.unpack('<4I', hdr)
        nb = h4 * stride
        data = f.read(nb * ENTRY_SZ)
        if len(data) < nb * ENTRY_SZ:
            raise ValueError('block data too small')
    blocks = []
    off = 0
    for i in range(nb):
        chunk = data[off:off+ENTRY_SZ]
        (rt0, rt1, rp0, rp1, is_intra,
         mvx0, mvx1, mvy0, mvy1,
         bsize, skip, imod, ctype,
         bits) = struct.unpack(ENTRY_FMT, chunk)
        blocks.append({
            'block_size': int(bsize),
            'is_intra': int(is_intra),
            'ref_type': (int(rt0), int(rt1)),
            'mv0': (int(mvx0), int(mvy0)),
            'mv1': (int(mvx1), int(mvy1)),
            'skip': int(skip),
            'inter_mode': int(imod),
            'bits': float(bits),
        })
        off += ENTRY_SZ
    return w4,h4,stride,frame,blocks

def group_to_coding_blocks(w4,h4,stride,blocks):
    visited = [False] * (w4*h4)
    coding = []
    for y in range(h4):
        for x in range(stride):
            idx = y*stride + x
            if visited[idx]:
                continue
            b = blocks[idx]
            bs = b['block_size']
            if 0 <= bs < len(BS_PIXELS):
                pw, ph = BS_PIXELS[bs]
                mi_w = pw // 4
                mi_h = ph // 4
            else:
                mi_w = mi_h = 1
            mi_w = min(mi_w, stride - x)
            mi_h = min(mi_h, h4 - y)
            for yy in range(y, y + mi_h):
                for xx in range(x, x + mi_w):
                    visited[yy*stride + xx] = True
            coding.append({
                'mi_x': x, 'mi_y': y,
                'px_x': x*4, 'px_y': y*4,
                'mi_w': mi_w, 'mi_h': mi_h,
                'w_px': mi_w*4, 'h_px': mi_h*4,
                'block_size_enum': bs,
                'is_intra': b['is_intra'],
                'ref_type': b['ref_type'],
                'mv0': b['mv0'],
                'mv1': b['mv1'],
                'skip': b['skip'],
                'inter_mode': b['inter_mode'],
                'bits': b['bits'],
            })
    return coding

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ivf', default='0018.ivf', help='input ivf file (used to run dav1d)')
    ap.add_argument('--outdir', default='dav1d_inspect_out', help='inspect output dir (where frame_*.bin are/will be)')
    ap.add_argument('--frames', nargs='+', type=int, required=True, help='frame numbers to extract (space separated)')
    ap.add_argument('--format', choices=['json','csv'], default='json', help='output format')
    ap.add_argument('--run', action='store_true', help='run dav1d to generate inspect files before extracting')
    args = ap.parse_args()

    if args.run:
        limit = max(args.frames) + 1
        run_dav1d(args.outdir, args.ivf, limit=limit)

    results = {}
    for fno in args.frames:
        path = os.path.join(args.outdir, f'frame_{fno}_blocks.bin')
        if not os.path.exists(path):
            print('Missing:', path, file=sys.stderr)
            continue
        w4,h4,stride,frame,blocks = read_blocks_bin(path)
        coding = group_to_coding_blocks(w4,h4,stride,blocks)
        results[fno] = {
            'header': {'w4': w4, 'h4': h4, 'stride': stride, 'frame': frame},
            'coding_blocks': coding
        }

    outbase = os.path.abspath(args.outdir)
    if args.format == 'json':
        outpath = os.path.join(outbase, 'coding_blocks.json')
        with open(outpath,'w') as f:
            json.dump(results, f, indent=2)
        print('Wrote', outpath)
    else:
        for fno, info in results.items():
            outpath = os.path.join(outbase, f'frame_{fno}_coding_blocks.csv')
            with open(outpath, 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(['mi_x','mi_y','px_x','px_y','mi_w','mi_h','w_px','h_px','bs_enum','is_intra','ref0','ref1','mv0_x','mv0_y','mv1_x','mv1_y','skip','inter_mode','bits'])
                for cb in info['coding_blocks']:
                    r0,r1 = cb['ref_type']
                    mv0x,mv0y = cb['mv0']
                    mv1x,mv1y = cb['mv1']
                    w.writerow([cb['mi_x'],cb['mi_y'],cb['px_x'],cb['px_y'],cb['mi_w'],cb['mi_h'],cb['w_px'],cb['h_px'],cb['block_size_enum'],cb['is_intra'],r0,r1,mv0x,mv0y,mv1x,mv1y,cb['skip'],cb['inter_mode'],cb['bits']])
            print('Wrote', outpath)

if __name__ == '__main__':
    main()
