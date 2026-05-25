#!/usr/bin/env python3
"""
Generate bit allocation heatmaps from dav1d inspection output.

Usage:
    python3 heatmap_bits.py inspect_dir/frame_0.json -o heatmap_frame0.png
    python3 heatmap_bits.py inspect_dir/ --all -o output_dir/
    python3 heatmap_bits.py inspect_dir/frame_0.json --colormap hot --scale log
"""

import argparse
import json
import sys
import os
import glob
import numpy as np
import matplotlib

matplotlib.use("Agg")  # Use non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, Normalize


def load_frame_data(json_path):
    """Load frame data from JSON file."""
    with open(json_path, "r") as f:
        data = json.load(f)

    if "bits" not in data:
        raise ValueError(
            f"No 'bits' field found in {json_path}. "
            "Make sure you're using dav1d with CONFIG_INSPECT enabled."
        )

    bits = np.array(data["bits"], dtype=np.float32)

    return {
        "bits": bits,
        "frame": data.get("frame", 0),
        "frame_type": data.get("frameType", 0),
        "shape": bits.shape,
    }


def create_heatmap(
    bits,
    output_path,
    colormap="viridis",
    scale="linear",
    title=None,
    dpi=150,
    interpolation="nearest",
    global_min=None,
    global_max=None,
    clean=False,
):
    """
    Create and save a heatmap visualization of bit allocation.

    Args:
        bits: 2D numpy array of bit costs per 4x4 block
        output_path: Output image path
        colormap: Matplotlib colormap name (viridis, hot, plasma, inferno, etc.)
        scale: 'linear' or 'log' scaling
        title: Optional plot title
        dpi: Output image DPI
        interpolation: Matplotlib interpolation method
        global_min: Global minimum value for normalization (optional)
        global_max: Global maximum value for normalization (optional)
        clean: If True, save as clean image without axes/colorbar/text (default: False)
    """
    h4, w4 = bits.shape

    # Determine min/max for normalization
    vmin = global_min if global_min is not None else bits.min()
    vmax = global_max if global_max is not None else bits.max()

    # Choose normalization
    if scale == "log":
        # Add small epsilon to avoid log(0)
        bits_viz = np.maximum(bits, 0.1)
        vmin = max(vmin, 0.1)
        norm = LogNorm(vmin=vmin, vmax=vmax)
    else:
        norm = Normalize(vmin=vmin, vmax=vmax)

    if clean:
        # Clean image mode: just the heatmap data as an image
        # Apply colormap to get RGB values
        cmap = plt.get_cmap(colormap)

        # Normalize data to [0, 1] range
        if scale == "log":
            import math

            # Manual log normalization
            log_vmin = math.log(vmin) if vmin > 0 else 0
            log_vmax = math.log(vmax) if vmax > 0 else 1
            bits_norm = np.zeros_like(bits, dtype=np.float32)
            mask = bits > 0
            bits_norm[mask] = (np.log(np.maximum(bits[mask], vmin)) - log_vmin) / (
                log_vmax - log_vmin
            )
            bits_norm = np.clip(bits_norm, 0, 1)
        else:
            bits_norm = (
                (bits - vmin) / (vmax - vmin)
                if (vmax - vmin) > 0
                else np.zeros_like(bits)
            )
            bits_norm = np.clip(bits_norm, 0, 1)

        # Apply colormap
        rgba = cmap(bits_norm)
        rgb = (rgba[:, :, :3] * 255).astype(np.uint8)

        # Save as image using PIL
        from PIL import Image

        img = Image.fromarray(rgb, mode="RGB")

        # Upscale to actual pixel resolution (each 4x4 block -> 4x4 pixels)
        target_width = w4 * 4
        target_height = h4 * 4

        # Use NEAREST for block-accurate visualization
        if interpolation == "nearest":
            resample = Image.NEAREST
        elif interpolation == "bilinear":
            resample = Image.BILINEAR
        elif interpolation == "bicubic":
            resample = Image.BICUBIC
        else:
            resample = None

        if resample is not None:
            img_upscaled = img.resize((target_width, target_height), resample=resample)
        else:
            img_upscaled = img

        img_upscaled.save(output_path, dpi=(dpi, dpi))

        print(f"Saved clean heatmap: {output_path}")
        print(f"  Resolution: {target_width}x{target_height} pixels ({w4}x{h4} blocks)")
        print(f"  Bits range: [{bits.min():.2f}, {bits.max():.2f}]")
        if global_min is not None or global_max is not None:
            print(f"  Norm range: [{vmin:.2f}, {vmax:.2f}]")

    else:
        # Graph mode: with colorbar, axes, and annotations
        # Create figure with appropriate aspect ratio
        fig_width = 12
        fig_height = fig_width * (h4 / w4)
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))

        # Create heatmap
        im = ax.imshow(
            bits, cmap=colormap, norm=norm, interpolation=interpolation, aspect="auto"
        )

        # Add colorbar
        cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("Bits per 4x4 block", rotation=270, labelpad=20)

        # Set title
        if title:
            ax.set_title(title, fontsize=14, pad=10)

        # Add grid dimensions as labels
        ax.set_xlabel(f"4x4 blocks (width: {w4}, {w4 * 4}px)", fontsize=10)
        ax.set_ylabel(f"4x4 blocks (height: {h4}, {h4 * 4}px)", fontsize=10)

        # Add statistics text box
        stats_text = (
            f"Min: {bits.min():.2f}\n"
            f"Max: {bits.max():.2f}\n"
            f"Mean: {bits.mean():.2f}\n"
            f"Total: {bits.sum():.0f}"
        )

        # Add normalization info if using global range
        if global_min is not None or global_max is not None:
            stats_text += f"\n\nNorm range:\n[{vmin:.2f}, {vmax:.2f}]"

        ax.text(
            0.02,
            0.98,
            stats_text,
            transform=ax.transAxes,
            fontsize=9,
            verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
        )

        # Tight layout and save
        plt.tight_layout()
        plt.savefig(output_path, dpi=dpi, bbox_inches="tight")
        plt.close()

        print(f"Saved heatmap: {output_path}")
        print(f"  Resolution: {w4}x{h4} blocks ({w4 * 4}x{h4 * 4} pixels)")
        print(f"  Bits range: [{bits.min():.2f}, {bits.max():.2f}]")
        if global_min is not None or global_max is not None:
            print(f"  Norm range: [{vmin:.2f}, {vmax:.2f}]")
        print(f"  Total bits: {bits.sum():.0f}")


def create_overlay_heatmap(
    bits, video_frame_path, output_path, colormap="hot", alpha=0.6, scale="linear"
):
    """
    Create a heatmap overlaid on the actual video frame.

    Args:
        bits: 2D numpy array of bit costs per 4x4 block
        video_frame_path: Path to decoded frame image (YUV or PNG)
        output_path: Output image path
        colormap: Matplotlib colormap name
        alpha: Transparency of heatmap overlay (0=transparent, 1=opaque)
        scale: 'linear' or 'log' scaling
    """
    from PIL import Image

    # Load video frame
    try:
        frame_img = Image.open(video_frame_path).convert("RGB")
    except Exception as e:
        print(f"Warning: Could not load video frame: {e}")
        return

    h4, w4 = bits.shape
    frame_w, frame_h = frame_img.size

    # Upscale bits to frame resolution (each 4x4 block -> 4x4 pixels)
    bits_upscaled = np.repeat(np.repeat(bits, 4, axis=0), 4, axis=1)

    # Ensure sizes match
    if bits_upscaled.shape[:2] != (frame_h, frame_w):
        from scipy.ndimage import zoom

        scale_y = frame_h / bits_upscaled.shape[0]
        scale_x = frame_w / bits_upscaled.shape[1]
        bits_upscaled = zoom(bits_upscaled, (scale_y, scale_x), order=1)

    # Create figure
    fig, ax = plt.subplots(figsize=(12, 12 * frame_h / frame_w))

    # Display original frame
    ax.imshow(frame_img)

    # Overlay heatmap
    if scale == "log":
        bits_viz = np.maximum(bits_upscaled, 0.1)
        norm = LogNorm(vmin=bits_viz.min(), vmax=bits_viz.max())
    else:
        norm = Normalize(vmin=bits_upscaled.min(), vmax=bits_upscaled.max())

    im = ax.imshow(
        bits_upscaled, cmap=colormap, alpha=alpha, norm=norm, interpolation="bilinear"
    )

    # Add colorbar
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Bits per 4x4 block", rotation=270, labelpad=20)

    ax.set_title("Bit Allocation Heatmap Overlay", fontsize=14, pad=10)
    ax.axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    print(f"Saved overlay heatmap: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate bit allocation heatmaps from dav1d inspection output."
    )
    parser.add_argument(
        "input", help="Input JSON file or directory with inspection output"
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output image path (or directory if processing multiple frames)",
    )
    parser.add_argument(
        "--all", action="store_true", help="Process all frames in directory"
    )
    parser.add_argument(
        "--colormap",
        default="viridis",
        choices=[
            "viridis",
            "plasma",
            "inferno",
            "magma",
            "hot",
            "cool",
            "jet",
            "turbo",
        ],
        help="Colormap to use (default: viridis)",
    )
    parser.add_argument(
        "--scale",
        default="linear",
        choices=["linear", "log"],
        help="Color scale (default: linear)",
    )
    parser.add_argument(
        "--dpi", type=int, default=150, help="Output image DPI (default: 150)"
    )
    parser.add_argument(
        "--interpolation",
        default="None",
        choices=["nearest", "bilinear", "bicubic"],
        help="Interpolation method (default: nearest)",
    )
    parser.add_argument(
        "--overlay", help="Path to decoded video frame for overlay visualization"
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="Normalize all frames to global min/max (max=1.0) across directory",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Save as clean image without colorbar, axes, or statistics (just the heatmap)",
    )

    args = parser.parse_args()

    # Determine if input is file or directory
    if os.path.isfile(args.input):
        # Single file mode
        json_files = [args.input]
        if args.all:
            print("Warning: --all flag ignored for single file input")
        if args.normalize:
            print("Warning: --normalize requires directory input, ignored")
            args.normalize = False
    elif os.path.isdir(args.input):
        # Directory mode
        pattern = os.path.join(args.input, "frame_*.json")
        json_files = sorted(glob.glob(pattern))
        if not json_files:
            print(f"Error: No frame_*.json files found in {args.input}")
            sys.exit(1)
        if not args.all:
            json_files = json_files[:1]  # Process only first frame
            print(f"Processing first frame only. Use --all to process all frames.")
            if args.normalize:
                print("Warning: --normalize requires --all flag, ignored")
                args.normalize = False
    else:
        print(f"Error: {args.input} is neither a file nor directory")
        sys.exit(1)

    # If processing multiple files, output must be a directory
    if len(json_files) > 1:
        if not os.path.isdir(args.output):
            os.makedirs(args.output, exist_ok=True)
            print(f"Created output directory: {args.output}")

    # If normalization requested, scan all files to find global min/max
    global_min = None
    global_max = None
    if args.normalize:
        print(f"Scanning {len(json_files)} frames for global min/max...")
        all_mins = []
        all_maxs = []
        for json_path in json_files:
            try:
                frame_data = load_frame_data(json_path)
                bits = frame_data["bits"]
                all_mins.append(bits.min())
                all_maxs.append(bits.max())
            except Exception as e:
                print(f"Warning: Could not load {json_path}: {e}")
                continue

        if all_mins and all_maxs:
            global_min = min(all_mins)
            global_max = max(all_maxs)
            print(f"Global range: [{global_min:.2f}, {global_max:.2f}]")
            print(f"Normalizing: max value ({global_max:.2f}) will map to 1.0")
            # Normalize to [0, 1] range
            # We'll pass global_min and global_max, but display will be in normalized units
        else:
            print("Warning: Could not determine global range, normalization disabled")
            args.normalize = False

    # Process each frame
    for json_path in json_files:
        try:
            # Load data
            frame_data = load_frame_data(json_path)
            bits = frame_data["bits"]
            frame_num = frame_data["frame"]

            # Apply normalization if requested
            if args.normalize and global_max is not None:
                # Normalize to [0, 1] range
                bits_normalized = (bits - global_min) / (global_max - global_min)
                bits_display = bits_normalized
                norm_min = 0.0
                norm_max = 1.0
            else:
                bits_display = bits
                norm_min = None
                norm_max = None

            # Determine output path
            if len(json_files) > 1:
                base_name = f"heatmap_frame_{frame_num:04d}.png"
                output_path = os.path.join(args.output, base_name)
            else:
                output_path = args.output

            # Create title
            frame_type_names = {0: "KEY", 1: "INTER", 2: "INTRA_ONLY", 3: "SWITCH"}
            frame_type_str = frame_type_names.get(frame_data["frame_type"], "UNKNOWN")
            title = f"Frame {frame_num} - {frame_type_str} - Bit Allocation Heatmap"
            if args.normalize:
                title += " (Normalized)"

            # Generate heatmap
            if args.overlay:
                create_overlay_heatmap(
                    bits_display,
                    args.overlay,
                    output_path,
                    colormap=args.colormap,
                    scale=args.scale,
                )
            else:
                create_heatmap(
                    bits_display,
                    output_path,
                    colormap=args.colormap,
                    scale=args.scale,
                    title=title,
                    dpi=args.dpi,
                    interpolation=args.interpolation,
                    global_min=norm_min,
                    global_max=norm_max,
                    clean=args.clean,
                )

        except Exception as e:
            print(f"Error processing {json_path}: {e}", file=sys.stderr)
            continue

    print(f"\nProcessed {len(json_files)} frame(s)")


if __name__ == "__main__":
    main()
