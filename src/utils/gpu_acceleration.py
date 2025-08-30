"""GPU acceleration utilities for image processing and other tasks."""

import logging
from typing import Optional, Any
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import QSize

logger = logging.getLogger(__name__)

class GPUAccelerator:
    """Handles GPU acceleration for various tasks."""
    
    def __init__(self):
        self.gpu_available = False
        self.gpu_type = None
        self.acceleration_enabled = False
        self._detect_gpu_capabilities()
    
    def _detect_gpu_capabilities(self):
        """Detect available GPU acceleration capabilities."""
        try:
            # Try to detect OpenGL support (built into Qt)
            from PyQt6.QtOpenGL import QOpenGLWidget
            self.gpu_available = True
            self.gpu_type = 'opengl'
            logger.info("OpenGL GPU acceleration available")
        except ImportError:
            logger.debug("OpenGL not available")
        
        # Try to detect other GPU libraries
        try:
            import cv2
            if cv2.cuda.getCudaEnabledDeviceCount() > 0:
                self.gpu_available = True
                self.gpu_type = 'cuda'
                logger.info("CUDA GPU acceleration available")
        except:
            pass
        
        if not self.gpu_available:
            logger.info("No GPU acceleration available, using CPU")
    
    def enable_acceleration(self, enabled: bool = True):
        """Enable or disable GPU acceleration."""
        if self.gpu_available:
            self.acceleration_enabled = enabled
            logger.info(f"GPU acceleration {'enabled' if enabled else 'disabled'}")
        else:
            self.acceleration_enabled = False
            if enabled:
                logger.warning("GPU acceleration requested but not available")
    
    def resize_image_gpu(self, image: QImage, size: QSize) -> QImage:
        """Resize image using GPU acceleration if available."""
        if not self.acceleration_enabled or not self.gpu_available:
            return image.scaled(size, aspectRatioMode=1, transformMode=1)  # Smooth scaling
        
        try:
            # Use GPU-accelerated scaling if available
            if self.gpu_type == 'opengl':
                return self._resize_with_opengl(image, size)
            elif self.gpu_type == 'cuda':
                return self._resize_with_cuda(image, size)
        except Exception as e:
            logger.warning(f"GPU image resize failed, falling back to CPU: {e}")
        
        # Fallback to CPU
        return image.scaled(size, aspectRatioMode=1, transformMode=1)
    
    def _resize_with_opengl(self, image: QImage, size: QSize) -> QImage:
        """Resize image using OpenGL."""
        # This would require more complex OpenGL setup
        # For now, fall back to Qt's optimized scaling
        return image.scaled(size, aspectRatioMode=1, transformMode=1)
    
    def _resize_with_cuda(self, image: QImage, size: QSize) -> QImage:
        """Resize image using CUDA."""
        try:
            import cv2
            import numpy as np
            
            # Convert QImage to numpy array
            width = image.width()
            height = image.height()
            ptr = image.bits()
            ptr.setsize(height * width * 4)  # 4 bytes per pixel (RGBA)
            arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 4))
            
            # Convert RGBA to BGR for OpenCV
            bgr_arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
            
            # Upload to GPU
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(bgr_arr)
            
            # Resize on GPU
            gpu_resized = cv2.cuda.resize(gpu_img, (size.width(), size.height()))
            
            # Download from GPU
            resized_arr = gpu_resized.download()
            
            # Convert back to RGBA
            rgba_arr = cv2.cvtColor(resized_arr, cv2.COLOR_BGR2RGBA)
            
            # Convert back to QImage
            h, w, ch = rgba_arr.shape
            bytes_per_line = ch * w
            result_image = QImage(rgba_arr.data, w, h, bytes_per_line, QImage.Format.Format_RGBA8888)
            
            return result_image
            
        except Exception as e:
            logger.error(f"CUDA image resize failed: {e}")
            raise
    
    def process_image_batch_gpu(self, images: list, size: QSize) -> list:
        """Process a batch of images using GPU acceleration."""
        if not self.acceleration_enabled or not self.gpu_available:
            return [img.scaled(size, aspectRatioMode=1, transformMode=1) for img in images]
        
        try:
            # Batch processing can be more efficient on GPU
            processed = []
            for image in images:
                processed.append(self.resize_image_gpu(image, size))
            return processed
        except Exception as e:
            logger.warning(f"GPU batch processing failed, falling back to CPU: {e}")
            return [img.scaled(size, aspectRatioMode=1, transformMode=1) for img in images]

# Global GPU accelerator instance
_gpu_accelerator = None

def get_gpu_accelerator() -> GPUAccelerator:
    """Get the global GPU accelerator instance."""
    global _gpu_accelerator
    if _gpu_accelerator is None:
        _gpu_accelerator = GPUAccelerator()
    return _gpu_accelerator

def enable_gpu_acceleration(enabled: bool = True):
    """Enable or disable GPU acceleration globally."""
    get_gpu_accelerator().enable_acceleration(enabled)

def resize_image_optimized(image: QImage, size: QSize) -> QImage:
    """Resize image using the best available method (GPU or CPU)."""
    return get_gpu_accelerator().resize_image_gpu(image, size)