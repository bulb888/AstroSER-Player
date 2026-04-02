"""Richardson-Lucy deconvolution with GPU (CuPy CUDA kernel) / CPU fallback.

Uses spatial-domain convolution (not FFT) — optimal for small PSF kernels
typical in astronomical seeing (3x3 to 11x11 pixels).
GPU path uses custom CUDA kernels, no cuFFT dependency.
"""

import numpy as np

# Try GPU path
try:
    import cupy as cp

    # CUDA kernel for spatial 2D convolution (small kernel)
    _CONV2D_KERNEL = cp.RawKernel(r'''
    extern "C" __global__
    void conv2d(
        const double* input, const double* kernel,
        double* output,
        int width, int height, int ksize
    ) {
        int x = blockDim.x * blockIdx.x + threadIdx.x;
        int y = blockDim.y * blockIdx.y + threadIdx.y;
        if (x >= width || y >= height) return;

        int half = ksize / 2;
        double sum = 0.0;
        for (int ky = 0; ky < ksize; ky++) {
            for (int kx = 0; kx < ksize; kx++) {
                int sy = y + ky - half;
                int sx = x + kx - half;
                // Clamp to borders
                if (sy < 0) sy = 0;
                if (sy >= height) sy = height - 1;
                if (sx < 0) sx = 0;
                if (sx >= width) sx = width - 1;
                sum += input[sy * width + sx] * kernel[ky * ksize + kx];
            }
        }
        output[y * width + x] = sum;
    }
    ''', 'conv2d')

    _USE_GPU = True
except (ImportError, Exception):
    _USE_GPU = False


def has_gpu() -> bool:
    """Check if GPU deconvolution is available."""
    return _USE_GPU


def _gaussian_psf(radius: float) -> np.ndarray:
    """Generate a normalized 2D Gaussian PSF kernel."""
    ksize = max(3, int(radius * 4) | 1)
    half = ksize // 2
    y, x = np.mgrid[-half:half+1, -half:half+1].astype(np.float64)
    sigma = max(radius, 0.5)
    psf = np.exp(-(x**2 + y**2) / (2 * sigma**2))
    psf /= psf.sum()
    return psf


def _conv2d_gpu(image_gpu, kernel_gpu, width, height, ksize):
    """GPU spatial 2D convolution via CUDA kernel."""
    output = cp.empty_like(image_gpu)
    block = (16, 16)
    grid = ((width + 15) // 16, (height + 15) // 16)
    _CONV2D_KERNEL(grid, block, (image_gpu, kernel_gpu, output, width, height, ksize))
    return output


def _rl_channel_gpu(observed, psf_gpu, psf_flip_gpu, ksize, w, h, iterations):
    """RL on one channel, fully on GPU with spatial convolution."""
    estimate = observed.copy()
    for _ in range(iterations):
        blurred = _conv2d_gpu(estimate, psf_gpu, w, h, ksize)
        blurred = cp.maximum(blurred, 1e-10)
        ratio = observed / blurred
        correction = _conv2d_gpu(ratio, psf_flip_gpu, w, h, ksize)
        estimate *= correction
    return cp.clip(estimate, 0.0, 1.0)


def _conv2d_cpu(image, kernel):
    """CPU spatial 2D convolution."""
    from scipy.ndimage import convolve
    return convolve(image, kernel, mode='reflect')


def _rl_channel_cpu(observed, psf, psf_flip, iterations):
    """RL on one channel, CPU."""
    estimate = observed.copy()
    for _ in range(iterations):
        blurred = _conv2d_cpu(estimate, psf)
        blurred = np.maximum(blurred, 1e-10)
        ratio = observed / blurred
        correction = _conv2d_cpu(ratio, psf_flip)
        estimate *= correction
    return np.clip(estimate, 0.0, 1.0)


def richardson_lucy(image: np.ndarray, psf_radius: float = 1.5,
                    iterations: int = 10) -> np.ndarray:
    """Apply Richardson-Lucy deconvolution.

    Uses GPU CUDA kernels if available, CPU scipy otherwise.
    Accepts float32 [0,1] or uint8 input. Returns same dtype.

    Args:
        image: float32 [0,1] or uint8 — (H,W) or (H,W,3).
        psf_radius: Gaussian PSF sigma in pixels.
        iterations: RL iteration count.

    Returns:
        Deconvolved image, same shape and dtype as input.
    """
    is_float = image.dtype in (np.float32, np.float64)

    if is_float:
        # Already in [0,1] float range — work directly
        img_f = image.astype(np.float64)
    else:
        # uint8 → normalize to [0,1]
        img_f = image.astype(np.float64) / 255.0

    psf = _gaussian_psf(psf_radius)
    psf_flip = psf[::-1, ::-1].copy()
    ksize = psf.shape[0]

    if _USE_GPU:
        result = _rl_gpu(img_f, psf, psf_flip, ksize, iterations)
    else:
        result = _rl_cpu(img_f, psf, psf_flip, iterations)

    if is_float:
        return result.astype(np.float32)
    else:
        return np.clip(result * 255, 0, 255).astype(np.uint8)


def _rl_gpu(img_f, psf, psf_flip, ksize, iterations):
    """GPU path. Input/output float64 [0,1]."""
    h, w = img_f.shape[:2]
    psf_gpu = cp.asarray(psf)
    psf_flip_gpu = cp.asarray(psf_flip)

    if img_f.ndim == 2:
        obs = cp.asarray(img_f)
        obs = cp.maximum(obs, 1e-10)
        result = _rl_channel_gpu(obs, psf_gpu, psf_flip_gpu, ksize, w, h, iterations)
        return cp.asnumpy(result)

    out = np.empty_like(img_f)
    for c in range(img_f.shape[2]):
        obs = cp.asarray(img_f[:, :, c])
        obs = cp.maximum(obs, 1e-10)
        ch = _rl_channel_gpu(obs, psf_gpu, psf_flip_gpu, ksize, w, h, iterations)
        out[:, :, c] = cp.asnumpy(ch)

    return out


def _rl_cpu(img_f, psf, psf_flip, iterations):
    """CPU fallback path. Input/output float64 [0,1]."""
    if img_f.ndim == 2:
        obs = np.maximum(img_f, 1e-10)
        return _rl_channel_cpu(obs, psf, psf_flip, iterations)

    out = np.empty_like(img_f)
    for c in range(img_f.shape[2]):
        obs = np.maximum(img_f[:, :, c], 1e-10)
        out[:, :, c] = _rl_channel_cpu(obs, psf, psf_flip, iterations)

    return out
