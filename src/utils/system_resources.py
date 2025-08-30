"""System resource detection and optimization utilities."""

import os
import sys
import logging
from typing import Dict, Any, Optional
from pathlib import Path

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.warning("psutil not available - using basic system detection")

logger = logging.getLogger(__name__)

class SystemResourceManager:
    """Manages dynamic system resource allocation for optimal performance."""
    
    def __init__(self):
        self.system_info = self._detect_system_capabilities()
        self.performance_profile = self._determine_performance_profile()
        logger.info(f"System Resources: {self.system_info}")
        logger.info(f"Performance Profile: {self.performance_profile}")
    
    def _detect_system_capabilities(self) -> Dict[str, Any]:
        """Detect available system resources."""
        try:
            if PSUTIL_AVAILABLE:
                return self._detect_with_psutil()
            else:
                return self._detect_basic()
        except Exception as e:
            logger.error(f"Error detecting system capabilities: {e}")
            return self._get_fallback_system_info()
    
    def _detect_with_psutil(self) -> Dict[str, Any]:
        """Detect system capabilities using psutil."""
        # CPU Information
        cpu_count = psutil.cpu_count(logical=True)
        cpu_count_physical = psutil.cpu_count(logical=False)
        cpu_freq = psutil.cpu_freq()
        
        # Memory Information
        memory = psutil.virtual_memory()
        total_memory_gb = memory.total / (1024**3)
        available_memory_gb = memory.available / (1024**3)
        
        # Disk Information
        disk_usage = psutil.disk_usage('/')
        disk_free_gb = disk_usage.free / (1024**3)
        
        # Network Information
        network_stats = psutil.net_io_counters()
        
        # GPU Detection (basic)
        has_gpu = self._detect_gpu()
        
        return {
            'cpu': {
                'logical_cores': cpu_count,
                'physical_cores': cpu_count_physical,
                'max_frequency': cpu_freq.max if cpu_freq else None,
                'current_frequency': cpu_freq.current if cpu_freq else None,
            },
            'memory': {
                'total_gb': round(total_memory_gb, 2),
                'available_gb': round(available_memory_gb, 2),
                'usage_percent': memory.percent,
            },
            'disk': {
                'free_gb': round(disk_free_gb, 2),
                'total_gb': round(disk_usage.total / (1024**3), 2),
            },
            'network': {
                'bytes_sent': network_stats.bytes_sent,
                'bytes_recv': network_stats.bytes_recv,
            },
            'gpu': {
                'available': has_gpu,
                'details': self._get_gpu_details() if has_gpu else None,
            },
            'platform': sys.platform,
            'python_version': sys.version_info[:2],
        }
    
    def _detect_basic(self) -> Dict[str, Any]:
        """Basic system detection without psutil."""
        # Use os.cpu_count() for basic CPU detection
        cpu_count = os.cpu_count() or 4
        
        # Basic memory detection (Windows)
        total_memory_gb = 8.0  # Default assumption
        available_memory_gb = 4.0
        
        if sys.platform == 'win32':
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                c_ulong = ctypes.c_ulong
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ('dwLength', c_ulong),
                        ('dwMemoryLoad', c_ulong),
                        ('ullTotalPhys', ctypes.c_ulonglong),
                        ('ullAvailPhys', ctypes.c_ulonglong),
                        ('ullTotalPageFile', ctypes.c_ulonglong),
                        ('ullAvailPageFile', ctypes.c_ulonglong),
                        ('ullTotalVirtual', ctypes.c_ulonglong),
                        ('ullAvailVirtual', ctypes.c_ulonglong),
                        ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
                    ]
                
                memoryStatus = MEMORYSTATUSEX()
                memoryStatus.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                kernel32.GlobalMemoryStatusEx(ctypes.byref(memoryStatus))
                
                total_memory_gb = memoryStatus.ullTotalPhys / (1024**3)
                available_memory_gb = memoryStatus.ullAvailPhys / (1024**3)
            except:
                pass  # Use defaults
        
        # GPU Detection (basic)
        has_gpu = self._detect_gpu()
        
        return {
            'cpu': {
                'logical_cores': cpu_count,
                'physical_cores': cpu_count // 2,  # Estimate
                'max_frequency': None,
                'current_frequency': None,
            },
            'memory': {
                'total_gb': round(total_memory_gb, 2),
                'available_gb': round(available_memory_gb, 2),
                'usage_percent': ((total_memory_gb - available_memory_gb) / total_memory_gb) * 100,
            },
            'disk': {
                'free_gb': 100.0,  # Default
                'total_gb': 500.0,  # Default
            },
            'network': {
                'bytes_sent': 0,
                'bytes_recv': 0,
            },
            'gpu': {
                'available': has_gpu,
                'details': self._get_gpu_details() if has_gpu else None,
            },
            'platform': sys.platform,
            'python_version': sys.version_info[:2],
        }
    
    def _detect_gpu(self) -> bool:
        """Detect if GPU acceleration is available."""
        try:
            # Try to detect NVIDIA GPU
            import subprocess
            result = subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return True
        except:
            pass
        
        try:
            # Try to detect AMD GPU (Windows)
            if sys.platform == 'win32':
                import wmi
                c = wmi.WMI()
                for gpu in c.Win32_VideoController():
                    if gpu.Name and ('AMD' in gpu.Name or 'Radeon' in gpu.Name):
                        return True
        except:
            pass
        
        return False
    
    def _get_gpu_details(self) -> Optional[Dict[str, Any]]:
        """Get detailed GPU information."""
        try:
            # Try NVIDIA first
            import subprocess
            result = subprocess.run([
                'nvidia-smi', 
                '--query-gpu=name,memory.total,memory.free,utilization.gpu',
                '--format=csv,noheader,nounits'
            ], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                gpu_info = []
                for line in lines:
                    parts = line.split(', ')
                    if len(parts) >= 4:
                        gpu_info.append({
                            'name': parts[0],
                            'memory_total_mb': int(parts[1]),
                            'memory_free_mb': int(parts[2]),
                            'utilization_percent': int(parts[3]),
                        })
                return {'nvidia': gpu_info}
        except:
            pass
        
        return None
    
    def _get_fallback_system_info(self) -> Dict[str, Any]:
        """Fallback system info if detection fails."""
        return {
            'cpu': {'logical_cores': 4, 'physical_cores': 2},
            'memory': {'total_gb': 8.0, 'available_gb': 4.0, 'usage_percent': 50.0},
            'disk': {'free_gb': 100.0, 'total_gb': 500.0},
            'network': {'bytes_sent': 0, 'bytes_recv': 0},
            'gpu': {'available': False, 'details': None},
            'platform': sys.platform,
            'python_version': sys.version_info[:2],
        }
    
    def _determine_performance_profile(self) -> str:
        """Determine the optimal performance profile based on system capabilities."""
        cpu_cores = self.system_info['cpu']['logical_cores']
        memory_gb = self.system_info['memory']['total_gb']
        has_gpu = self.system_info['gpu']['available']
        
        # High-end system
        if cpu_cores >= 12 and memory_gb >= 16 and has_gpu:
            return 'ultra'
        # High-performance system
        elif cpu_cores >= 8 and memory_gb >= 12:
            return 'high'
        # Mid-range system
        elif cpu_cores >= 6 and memory_gb >= 8:
            return 'medium'
        # Budget system
        elif cpu_cores >= 4 and memory_gb >= 4:
            return 'low'
        # Very limited system
        else:
            return 'minimal'
    
    def get_optimal_settings(self) -> Dict[str, Any]:
        """Get optimal settings based on system capabilities."""
        profile = self.performance_profile
        cpu_cores = self.system_info['cpu']['logical_cores']
        memory_gb = self.system_info['memory']['available_gb']
        
        settings = {
            'ultra': {
                'concurrent_downloads': min(cpu_cores, 5),  # Capped at 5 for system stability
                'thread_pool_size': cpu_cores * 2,
                'memory_cache_mb': min(int(memory_gb * 1024 * 0.3), 2048),  # 30% of available RAM, max 2GB
                'image_cache_size': 1000,
                'network_timeout': 30,
                'retry_attempts': 5,
                'batch_size': 10,
                'ui_update_interval': 50,  # ms
                'enable_gpu_acceleration': True,
                'preload_content': True,
                'aggressive_caching': True,
            },
            'high': {
                'concurrent_downloads': min(cpu_cores, 5),  # Capped at 5 for system stability
                'thread_pool_size': cpu_cores * 1.5,
                'memory_cache_mb': min(int(memory_gb * 1024 * 0.25), 1024),  # 25% of available RAM, max 1GB
                'image_cache_size': 500,
                'network_timeout': 25,
                'retry_attempts': 4,
                'batch_size': 8,
                'ui_update_interval': 75,  # ms
                'enable_gpu_acceleration': self.system_info['gpu']['available'],
                'preload_content': True,
                'aggressive_caching': True,
            },
            'medium': {
                'concurrent_downloads': min(cpu_cores, 5),  # Capped at 5 for system stability
                'thread_pool_size': cpu_cores,
                'memory_cache_mb': min(int(memory_gb * 1024 * 0.2), 512),  # 20% of available RAM, max 512MB
                'image_cache_size': 300,
                'network_timeout': 20,
                'retry_attempts': 3,
                'batch_size': 5,
                'ui_update_interval': 100,  # ms
                'enable_gpu_acceleration': False,
                'preload_content': True,
                'aggressive_caching': False,
            },
            'low': {
                'concurrent_downloads': min(cpu_cores, 4),  # Capped at 4 for low-end systems
                'thread_pool_size': max(cpu_cores - 1, 2),
                'memory_cache_mb': min(int(memory_gb * 1024 * 0.15), 256),  # 15% of available RAM, max 256MB
                'image_cache_size': 150,
                'network_timeout': 15,
                'retry_attempts': 2,
                'batch_size': 3,
                'ui_update_interval': 150,  # ms
                'enable_gpu_acceleration': False,
                'preload_content': False,
                'aggressive_caching': False,
            },
            'minimal': {
                'concurrent_downloads': 3,
                'thread_pool_size': 2,
                'memory_cache_mb': 64,
                'image_cache_size': 50,
                'network_timeout': 10,
                'retry_attempts': 1,
                'batch_size': 1,
                'ui_update_interval': 200,  # ms
                'enable_gpu_acceleration': False,
                'preload_content': False,
                'aggressive_caching': False,
            }
        }
        
        return settings.get(profile, settings['medium'])
    
    def get_current_resource_usage(self) -> Dict[str, float]:
        """Get current system resource usage."""
        try:
            if PSUTIL_AVAILABLE:
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory = psutil.virtual_memory()
                disk_io = psutil.disk_io_counters()
                network_io = psutil.net_io_counters()
                
                return {
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'memory_available_gb': memory.available / (1024**3),
                    'disk_read_mb_s': getattr(disk_io, 'read_bytes', 0) / (1024**2),
                    'disk_write_mb_s': getattr(disk_io, 'write_bytes', 0) / (1024**2),
                    'network_recv_mb_s': getattr(network_io, 'bytes_recv', 0) / (1024**2),
                    'network_sent_mb_s': getattr(network_io, 'bytes_sent', 0) / (1024**2),
                }
            else:
                # Basic fallback without psutil
                return {
                    'cpu_percent': 50.0,  # Assume moderate usage
                    'memory_percent': 60.0,
                    'memory_available_gb': self.system_info['memory']['available_gb'],
                    'disk_read_mb_s': 0,
                    'disk_write_mb_s': 0,
                    'network_recv_mb_s': 0,
                    'network_sent_mb_s': 0,
                }
        except Exception as e:
            logger.error(f"Error getting resource usage: {e}")
            return {}
    
    def should_throttle_operations(self) -> bool:
        """Determine if operations should be throttled due to high resource usage."""
        try:
            usage = self.get_current_resource_usage()
            
            # Throttle if CPU > 90% or Memory > 95%
            if usage.get('cpu_percent', 0) > 90:
                logger.info("Throttling due to high CPU usage")
                return True
            
            if usage.get('memory_percent', 0) > 95:
                logger.info("Throttling due to high memory usage")
                return True
            
            # Throttle if available memory < 500MB
            if usage.get('memory_available_gb', 1) < 0.5:
                logger.info("Throttling due to low available memory")
                return True
            
            return False
        except Exception as e:
            logger.error(f"Error checking throttle conditions: {e}")
            return False
    
    def optimize_for_current_load(self) -> Dict[str, Any]:
        """Dynamically adjust settings based on current system load."""
        base_settings = self.get_optimal_settings()
        
        if self.should_throttle_operations():
            # Reduce resource usage
            return {
                **base_settings,
                'concurrent_downloads': max(base_settings['concurrent_downloads'] // 2, 1),
                'thread_pool_size': max(base_settings['thread_pool_size'] // 2, 2),
                'memory_cache_mb': base_settings['memory_cache_mb'] // 2,
                'batch_size': max(base_settings['batch_size'] // 2, 1),
                'ui_update_interval': base_settings['ui_update_interval'] * 2,
            }
        
        return base_settings

# Global instance
_resource_manager = None

def get_resource_manager() -> SystemResourceManager:
    """Get the global resource manager instance."""
    global _resource_manager
    if _resource_manager is None:
        _resource_manager = SystemResourceManager()
    return _resource_manager

def get_optimal_settings() -> Dict[str, Any]:
    """Get optimal settings for the current system."""
    return get_resource_manager().get_optimal_settings()

def should_throttle() -> bool:
    """Check if operations should be throttled."""
    return get_resource_manager().should_throttle_operations()