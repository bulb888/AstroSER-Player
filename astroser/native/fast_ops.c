/*
 * fast_ops.c - High-performance native operations for AstroSER Player
 *
 * Compiled to DLL, called via Python ctypes.
 * Replaces Python hot loops for:
 *   1. Centroid detection (search window tracking)
 *   2. Frame export loop (read SER + crop + pipe to ffmpeg)
 *
 * Build: gcc -O3 -shared -o fast_ops.dll fast_ops.c -mavx2 -mfma
 */

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdio.h>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

/* ========== Centroid Detection ========== */

/*
 * Detect brightness-weighted centroid in a grayscale region.
 * Returns (cx, cy) via output pointers.
 *
 * data: grayscale pixel data (uint8 or uint16)
 * width, height: region dimensions
 * stride: bytes per row
 * bpp: bytes per pixel (1 for uint8, 2 for uint16)
 * threshold_pct: percentile threshold (0-100), pixels below are ignored
 * out_cx, out_cy: output centroid coordinates
 */
EXPORT void centroid_region(
    const uint8_t *data, int width, int height, int stride, int bpp,
    float threshold_pct, float *out_cx, float *out_cy
) {
    /* Build histogram to find percentile threshold */
    int hist[65536] = {0};
    int total_pixels = width * height;
    int max_val = (bpp == 2) ? 65535 : 255;

    for (int y = 0; y < height; y++) {
        const uint8_t *row = data + y * stride;
        if (bpp == 2) {
            const uint16_t *row16 = (const uint16_t *)row;
            for (int x = 0; x < width; x++)
                hist[row16[x]]++;
        } else {
            for (int x = 0; x < width; x++)
                hist[row[x]]++;
        }
    }

    /* Find threshold value at given percentile */
    int target = (int)(total_pixels * threshold_pct / 100.0f);
    int cumsum = 0;
    int thresh = 0;
    for (int i = 0; i <= max_val; i++) {
        cumsum += hist[i];
        if (cumsum >= target) {
            thresh = i;
            break;
        }
    }

    /* Compute weighted centroid */
    double sum_x = 0, sum_y = 0, sum_w = 0;

    for (int y = 0; y < height; y++) {
        const uint8_t *row = data + y * stride;
        if (bpp == 2) {
            const uint16_t *row16 = (const uint16_t *)row;
            for (int x = 0; x < width; x++) {
                uint16_t v = row16[x];
                if (v >= thresh) {
                    double w = (double)v;
                    sum_x += x * w;
                    sum_y += y * w;
                    sum_w += w;
                }
            }
        } else {
            for (int x = 0; x < width; x++) {
                uint8_t v = row[x];
                if (v >= thresh) {
                    double w = (double)v;
                    sum_x += x * w;
                    sum_y += y * w;
                    sum_w += w;
                }
            }
        }
    }

    if (sum_w > 0) {
        *out_cx = (float)(sum_x / sum_w);
        *out_cy = (float)(sum_y / sum_w);
    } else {
        *out_cx = width / 2.0f;
        *out_cy = height / 2.0f;
    }
}

/*
 * Detect centroids for multiple frames with search window tracking.
 * First frame: full image. Subsequent frames: search around last position.
 *
 * frames: array of pointers to frame data (grayscale)
 * num_frames: number of frames
 * width, height: frame dimensions
 * stride: bytes per row
 * bpp: bytes per pixel
 * threshold_pct: detection threshold
 * search_radius: search window half-size (0 = auto 20% of frame)
 * out_cx, out_cy: output arrays (num_frames floats each)
 *
 * Returns 0 on success.
 */
EXPORT int detect_centroids_batch(
    const uint8_t **frames, int num_frames,
    int width, int height, int stride, int bpp,
    float threshold_pct, int search_radius,
    float *out_cx, float *out_cy
) {
    if (search_radius <= 0)
        search_radius = (width > height ? width : height) / 5;

    float last_cx = width / 2.0f;
    float last_cy = height / 2.0f;

    for (int f = 0; f < num_frames; f++) {
        const uint8_t *frame = frames[f];

        if (f == 0) {
            /* First frame: full image scan */
            centroid_region(frame, width, height, stride, bpp,
                           threshold_pct, &out_cx[f], &out_cy[f]);
        } else {
            /* Search window around last position */
            int x0 = (int)last_cx - search_radius;
            int y0 = (int)last_cy - search_radius;
            int x1 = (int)last_cx + search_radius;
            int y1 = (int)last_cy + search_radius;

            if (x0 < 0) x0 = 0;
            if (y0 < 0) y0 = 0;
            if (x1 > width) x1 = width;
            if (y1 > height) y1 = height;

            int rw = x1 - x0;
            int rh = y1 - y0;

            const uint8_t *region_start = frame + y0 * stride + x0 * bpp;

            float rcx, rcy;
            centroid_region(region_start, rw, rh, stride, bpp,
                           threshold_pct, &rcx, &rcy);

            out_cx[f] = x0 + rcx;
            out_cy[f] = y0 + rcy;
        }

        last_cx = out_cx[f];
        last_cy = out_cy[f];
    }

    return 0;
}


/* ========== Fast Frame Crop ========== */

/*
 * Crop a frame and convert to RGB24 uint8 in one pass.
 * Handles: mono8, mono16, RGB24, Bayer8, Bayer16.
 *
 * src: source frame data
 * src_w, src_h: source dimensions
 * src_stride: source bytes per row
 * channels: 1 (mono) or 3 (RGB)
 * bpp: bytes per pixel per channel (1 or 2)
 * crop_x, crop_y, crop_w, crop_h: crop rectangle
 * dst: output buffer (must be crop_w * crop_h * 3 bytes)
 */
EXPORT void crop_to_rgb24(
    const uint8_t *src, int src_w, int src_h, int src_stride,
    int channels, int bpp,
    int crop_x, int crop_y, int crop_w, int crop_h,
    uint8_t *dst
) {
    for (int y = 0; y < crop_h; y++) {
        int sy = crop_y + y;
        if (sy < 0 || sy >= src_h) {
            memset(dst + y * crop_w * 3, 0, crop_w * 3);
            continue;
        }

        const uint8_t *src_row = src + sy * src_stride;
        uint8_t *dst_row = dst + y * crop_w * 3;

        for (int x = 0; x < crop_w; x++) {
            int sx = crop_x + x;
            if (sx < 0 || sx >= src_w) {
                dst_row[x*3] = dst_row[x*3+1] = dst_row[x*3+2] = 0;
                continue;
            }

            if (channels == 3) {
                if (bpp == 2) {
                    const uint16_t *p = (const uint16_t *)(src_row + sx * 6);
                    dst_row[x*3]   = (uint8_t)(p[0] >> 8);
                    dst_row[x*3+1] = (uint8_t)(p[1] >> 8);
                    dst_row[x*3+2] = (uint8_t)(p[2] >> 8);
                } else {
                    const uint8_t *p = src_row + sx * 3;
                    dst_row[x*3]   = p[0];
                    dst_row[x*3+1] = p[1];
                    dst_row[x*3+2] = p[2];
                }
            } else {
                /* Mono -> RGB (triplicate) */
                uint8_t v;
                if (bpp == 2) {
                    v = (uint8_t)(((const uint16_t *)(src_row + sx * 2))[0] >> 8);
                } else {
                    v = src_row[sx];
                }
                dst_row[x*3] = dst_row[x*3+1] = dst_row[x*3+2] = v;
            }
        }
    }
}

/*
 * Apply unsharp mask sharpening to RGB24 image in-place.
 *
 * data: RGB24 image (w * h * 3 bytes)
 * w, h: dimensions
 * strength: sharpening strength (0.0 = off, 1.0+ = strong)
 */
EXPORT void sharpen_rgb24(uint8_t *data, int w, int h, float strength) {
    if (strength <= 0.0f || w < 3 || h < 3)
        return;

    /* Work on a copy for reading neighbor values */
    int size = w * h * 3;
    uint8_t *copy = (uint8_t *)malloc(size);
    if (!copy) return;
    memcpy(copy, data, size);

    for (int y = 1; y < h - 1; y++) {
        for (int x = 1; x < w - 1; x++) {
            int idx = (y * w + x) * 3;
            for (int c = 0; c < 3; c++) {
                float center = (float)copy[idx + c];
                float avg = (
                    (float)copy[((y-1)*w + x)*3 + c] +
                    (float)copy[((y+1)*w + x)*3 + c] +
                    (float)copy[(y*w + x-1)*3 + c] +
                    (float)copy[(y*w + x+1)*3 + c]
                ) * 0.25f;

                float val = center + strength * (center - avg);
                if (val < 0) val = 0;
                if (val > 255) val = 255;
                data[idx + c] = (uint8_t)val;
            }
        }
    }

    free(copy);
}
