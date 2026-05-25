#ifndef DAV1D_SRC_INSPECT_DATA_H
#define DAV1D_SRC_INSPECT_DATA_H

#include <stdint.h>
#include <stddef.h>

/* Per-4x4 block metadata (splatted from coding block to all covered 4x4 units) */
typedef struct Dav1dInspectBlock {
    int8_t  ref_type[2];   /* reference index 0-6, -1 if unused/intra */
    uint8_t ref_poc[2];    /* frame_offset of referenced frame */
    uint8_t is_intra;      /* 1=intra, 0=inter */

    int16_t mv_x[2];       /* horizontal MV (1/8-pel units) */
    int16_t mv_y[2];       /* vertical MV (1/8-pel units) */

    uint8_t block_size;    /* enum BlockSize (dav1d numbering) */
    uint8_t skip;
    uint8_t inter_mode;
    uint8_t comp_type;

    float bits;            /* approximate bit cost for this 4x4 unit */
} Dav1dInspectBlock;

/*
 * Mapping from dav1d enum BlockSize to libaom/aomanalyzer block size index.
 *
 * dav1d (levels.h):                        libaom (aomanalyzer):
 *   BS_128x128 = 0                           BLOCK_4X4    = 0
 *   BS_128x64  = 1                           BLOCK_4X8    = 1
 *   BS_64x128  = 2                           BLOCK_8X4    = 2
 *   BS_64x64   = 3                           BLOCK_8X8    = 3
 *   BS_64x32   = 4                           BLOCK_8X16   = 4
 *   BS_64x16   = 5                           BLOCK_16X8   = 5
 *   BS_32x64   = 6                           BLOCK_16X16  = 6
 *   BS_32x32   = 7                           BLOCK_16X32  = 7
 *   BS_32x16   = 8                           BLOCK_32X16  = 8
 *   BS_32x8    = 9                           BLOCK_32X32  = 9
 *   BS_16x64   = 10                          BLOCK_32X64  = 10
 *   BS_16x32   = 11                          BLOCK_64X32  = 11
 *   BS_16x16   = 12                          BLOCK_64X64  = 12
 *   BS_16x8    = 13                          BLOCK_64X128 = 13
 *   BS_16x4    = 14                          BLOCK_128X64 = 14
 *   BS_8x32    = 15                          BLOCK_128X128= 15
 *   BS_8x16    = 16                          BLOCK_4X16   = 16
 *   BS_8x8     = 17                          BLOCK_16X4   = 17
 *   BS_8x4     = 18                          BLOCK_8X32   = 18
 *   BS_4x16    = 19                          BLOCK_32X8   = 19
 *   BS_4x8     = 20                          BLOCK_16X64  = 20
 *   BS_4x4     = 21                          BLOCK_64X16  = 21
 */
static const uint8_t dav1d_bs_to_aom_bs[22] = {
    /* BS_128x128 = 0  -> BLOCK_128X128 = 15 */  15,
    /* BS_128x64  = 1  -> BLOCK_128X64  = 14 */  14,
    /* BS_64x128  = 2  -> BLOCK_64X128  = 13 */  13,
    /* BS_64x64   = 3  -> BLOCK_64X64   = 12 */  12,
    /* BS_64x32   = 4  -> BLOCK_64X32   = 11 */  11,
    /* BS_64x16   = 5  -> BLOCK_64X16   = 21 */  21,
    /* BS_32x64   = 6  -> BLOCK_32X64   = 10 */  10,
    /* BS_32x32   = 7  -> BLOCK_32X32   = 9  */   9,
    /* BS_32x16   = 8  -> BLOCK_32X16   = 8  */   8,
    /* BS_32x8    = 9  -> BLOCK_32X8    = 19 */  19,
    /* BS_16x64   = 10 -> BLOCK_16X64   = 20 */  20,
    /* BS_16x32   = 11 -> BLOCK_16X32   = 7  */   7,
    /* BS_16x16   = 12 -> BLOCK_16X16   = 6  */   6,
    /* BS_16x8    = 13 -> BLOCK_16X8    = 5  */   5,
    /* BS_16x4    = 14 -> BLOCK_16X4    = 17 */  17,
    /* BS_8x32    = 15 -> BLOCK_8X32    = 18 */  18,
    /* BS_8x16    = 16 -> BLOCK_8X16    = 4  */   4,
    /* BS_8x8     = 17 -> BLOCK_8X8     = 3  */   3,
    /* BS_8x4     = 18 -> BLOCK_8X4     = 2  */   2,
    /* BS_4x16    = 19 -> BLOCK_4X16    = 16 */  16,
    /* BS_4x8     = 20 -> BLOCK_4X8     = 1  */   1,
    /* BS_4x4     = 21 -> BLOCK_4X4     = 0  */   0,
};

typedef struct Dav1dInspectFrameCtx {
    int w4, h4;                /* frame dimensions in 4x4 units */
    ptrdiff_t b4_stride;       /* stride for 2D indexing */

    Dav1dInspectBlock *blocks; /* per-4x4 metadata array (h4 * b4_stride) */

    /* spatial-domain residual: full-resolution pixel planes (signed int16) */
    int16_t *residual[3];      /* Y, U, V residual planes */
    int res_w, res_h;          /* luma frame dimensions in pixels */
    int res_cw, res_ch;        /* chroma frame dimensions in pixels */
    int ss_hor, ss_ver;        /* chroma subsampling factors */

    /* frame info */
    unsigned decode_idx;       /* monotonic decode counter (for file naming) */
    uint8_t frame_offset;
    uint8_t frame_type;
    uint8_t show_frame;
    uint8_t base_q_idx;
    uint8_t delta_q_present;
    uint8_t delta_q_res;
    uint8_t refpoc[7];

    /* feature flags */
    uint8_t enable_residual;   /* 1 = capture residual, 0 = skip */
    uint8_t use_rle;           /* 1 = RLE-compressed JSON, 0 = flat JSON */

    /* output directory (owned) */
    char *out_dir;
} Dav1dInspectFrameCtx;

#endif /* DAV1D_SRC_INSPECT_DATA_H */
