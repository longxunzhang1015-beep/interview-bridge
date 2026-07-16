"""音频捕获模块 — 通过 Windows WASAPI Loopback 捕获系统音频输出

使用 Windows Core Audio API (via comtypes) 实现 loopback 捕获，
不需要额外安装虚拟音频设备或启用 Stereo Mix。
"""

import struct
import threading
import queue
import logging

import numpy as np
import comtypes
from comtypes import CLSCTX_ALL, GUID, STDMETHOD, HRESULT, IUnknown
from ctypes import (
    byref, c_void_p, c_uint32, c_int64, c_uint64, c_ubyte,
    POINTER, cast, string_at, windll, oledll,
)

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GUID 常量
# ---------------------------------------------------------------------------

CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
IID_IMMDeviceEnumerator = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
IID_IMMDevice = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
IID_IAudioClient = GUID("{1CB9AD4C-DBFA-4C32-B178-C2F568A703B2}")
IID_IAudioCaptureClient = GUID("{C8ADBD64-E71E-48A0-A4DE-185C395CD317}")

# eRender + eConsole
EDataFlow_eRender = 0
ERole_eConsole = 0

# Stream flags
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000

# Buffer flags
AUDCLNT_BUFFERFLAGS_SILENT = 0x00000002

# Share mode
AUDCLNT_SHAREMODE_SHARED = 0

# ---------------------------------------------------------------------------
# COM 接口定义
# ---------------------------------------------------------------------------

class IAudioCaptureClient(IUnknown):
    _iid_ = IID_IAudioCaptureClient
    _methods_ = [
        STDMETHOD(HRESULT, "GetBuffer", [
            POINTER(c_void_p), POINTER(c_uint32),
            POINTER(c_uint32), POINTER(c_uint64), POINTER(c_uint64),
        ]),
        STDMETHOD(HRESULT, "ReleaseBuffer", [c_uint32]),
        STDMETHOD(HRESULT, "GetNextPacketSize", [POINTER(c_uint32)]),
    ]


class IAudioClient(IUnknown):
    _iid_ = IID_IAudioClient
    _methods_ = [
        STDMETHOD(HRESULT, "Initialize", [
            c_uint32, c_uint32, c_int64, c_int64, c_void_p, c_void_p,
        ]),
        STDMETHOD(HRESULT, "GetBufferSize", [POINTER(c_uint32)]),
        STDMETHOD(HRESULT, "GetStreamLatency", [POINTER(c_int64)]),
        STDMETHOD(HRESULT, "GetCurrentPadding", [POINTER(c_uint32)]),
        STDMETHOD(HRESULT, "IsFormatSupported", [
            c_uint32, c_void_p, POINTER(c_void_p),
        ]),
        STDMETHOD(HRESULT, "GetMixFormat", [POINTER(c_void_p)]),
        STDMETHOD(HRESULT, "GetDevicePeriod", [
            POINTER(c_int64), POINTER(c_int64),
        ]),
        STDMETHOD(HRESULT, "Start", []),
        STDMETHOD(HRESULT, "Stop", []),
        STDMETHOD(HRESULT, "Reset", []),
        STDMETHOD(HRESULT, "SetEventHandle", [c_void_p]),
        STDMETHOD(HRESULT, "GetService", [
            POINTER(GUID), POINTER(c_void_p),
        ]),
    ]


class IMMDevice(IUnknown):
    _iid_ = IID_IMMDevice
    _methods_ = [
        STDMETHOD(HRESULT, "Activate", [
            POINTER(GUID), c_uint32, c_void_p, POINTER(c_void_p),
        ]),
        STDMETHOD(HRESULT, "OpenPropertyStore", [c_uint32, POINTER(c_void_p)]),
        STDMETHOD(HRESULT, "GetId", [POINTER(c_void_p)]),
        STDMETHOD(HRESULT, "GetState", [POINTER(c_uint32)]),
    ]


class IMMDeviceEnumerator(IUnknown):
    _iid_ = IID_IMMDeviceEnumerator
    _methods_ = [
        STDMETHOD(HRESULT, "EnumAudioEndpoints", [
            c_uint32, c_uint32, POINTER(c_void_p),
        ]),
        STDMETHOD(HRESULT, "GetDefaultAudioEndpoint", [
            c_uint32, c_uint32, POINTER(c_void_p),
        ]),
        STDMETHOD(HRESULT, "GetDevice", [
            c_void_p, POINTER(c_void_p),
        ]),
        STDMETHOD(HRESULT, "RegisterEndpointNotificationCallback", [c_void_p]),
        STDMETHOD(HRESULT, "UnregisterEndpointNotificationCallback", [c_void_p]),
    ]


# ---------------------------------------------------------------------------
# AudioCapture 类
# ---------------------------------------------------------------------------

class AudioCapture:
    """通过 WASAPI Loopback 捕获系统音频输出"""

    def __init__(self, audio_queue: queue.Queue):
        self._audio_queue = audio_queue
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info("音频捕获线程已启动")

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    # ------------------------------------------------------------------
    # 核心循环
    # ------------------------------------------------------------------

    def _capture_loop(self):
        try:
            self._wasapi_loop()
        except Exception as e:
            logger.error(f"WASAPI 音频捕获失败: {e}")
            logger.error(
                "备选方案：在 Windows 声音设置中启用「立体声混音(Stereo Mix)」\n"
                "  右键任务栏音量 → 声音设置 → 更多声音设置 → 录制 → 右键启用立体声混音"
            )
            self._running = False

    def _wasapi_loop(self):
        """使用 Windows Core Audio API 进行 loopback 捕获"""

        # 1. 创建设备枚举器
        enumerator = comtypes.CoCreateInstance(
            CLSID_MMDeviceEnumerator,
            interface=IMMDeviceEnumerator,
            clsctx=CLSCTX_ALL,
        )

        # 2. 获取默认渲染设备（扬声器）
        device_ptr = c_void_p()
        enumerator.GetDefaultAudioEndpoint(
            EDataFlow_eRender, ERole_eConsole, byref(device_ptr)
        )
        device = cast(device_ptr, POINTER(IMMDevice))
        logger.info("已获取默认扬声器设备")

        # 3. 激活 IAudioClient
        ac_ptr = c_void_p()
        device.Activate(
            byref(IID_IAudioClient), CLSCTX_ALL, None, byref(ac_ptr)
        )
        audio_client = cast(ac_ptr, POINTER(IAudioClient))

        # 4. 获取混音格式
        mix_format_ptr = c_void_p()
        audio_client.GetMixFormat(byref(mix_format_ptr))

        fmt_bytes = string_at(mix_format_ptr, 18)
        wFormatTag = struct.unpack_from("<H", fmt_bytes, 0)[0]
        nChannels = struct.unpack_from("<H", fmt_bytes, 2)[0]
        nSamplesPerSec = struct.unpack_from("<I", fmt_bytes, 4)[0]
        wBitsPerSample = struct.unpack_from("<H", fmt_bytes, 14)[0]
        nBlockAlign = struct.unpack_from("<H", fmt_bytes, 12)[0]
        is_float = (wFormatTag == 3 or wBitsPerSample == 32)
        bytes_per_frame = nBlockAlign

        logger.info(
            f"混音格式: {nSamplesPerSec}Hz, {nChannels}ch, "
            f"{wBitsPerSample}bit, block={nBlockAlign}"
        )

        # 5. 初始化 (共享模式 + LOOPBACK) — 必须传 mix_format_ptr
        hr = audio_client.Initialize(
            AUDCLNT_SHAREMODE_SHARED,
            AUDCLNT_STREAMFLAGS_LOOPBACK,
            100_0000,           # 100ms buffer
            0,                  # periodicity (必须为 0)
            mix_format_ptr,     # pFormat (loopback 不能为 NULL)
            c_void_p(0),        # AudioSessionGuid (NULL)
        )
        oledll.ole32.CoTaskMemFree(mix_format_ptr)

        if hr < 0:
            raise OSError(f"IAudioClient::Initialize 失败: 0x{hr & 0xFFFFFFFF:08X}")

        # 6. 获取缓冲区大小
        buf_frames = c_uint32()
        audio_client.GetBufferSize(byref(buf_frames))
        logger.info(f"WASAPI 缓冲区: {buf_frames.value} frames")

        # 7. 获取 IAudioCaptureClient
        cap_ptr = c_void_p()
        audio_client.GetService(
            byref(IID_IAudioCaptureClient), byref(cap_ptr)
        )
        capture_client = cast(cap_ptr, POINTER(IAudioCaptureClient))

        # 8. 启动
        audio_client.Start()
        logger.info(f"Loopback 捕获已启动 ({nSamplesPerSec}Hz, {nChannels}ch)")

        target_sr = config.SAMPLE_RATE

        # 9. 主捕获循环
        while self._running:
            packet_size = c_uint32()
            hr = capture_client.GetNextPacketSize(byref(packet_size))
            if hr < 0:
                break

            while packet_size.value > 0 and self._running:
                data_ptr = c_void_p()
                num_frames = c_uint32()
                flags = c_uint32()

                hr = capture_client.GetBuffer(
                    byref(data_ptr), byref(num_frames),
                    byref(flags), None, None,
                )
                if hr < 0:
                    break

                if num_frames.value > 0 and not (flags.value & AUDCLNT_BUFFERFLAGS_SILENT):
                    raw = string_at(data_ptr, num_frames.value * bytes_per_frame)

                    if is_float:
                        audio_np = np.frombuffer(raw, dtype=np.float32).reshape(-1, nChannels)
                    else:
                        audio_np = np.frombuffer(raw, dtype=np.int16).reshape(-1, nChannels)
                        audio_np = audio_np.astype(np.float32) / 32768.0

                    resampled = self._resample(audio_np, nSamplesPerSec, target_sr, nChannels)
                    self._audio_queue.put(resampled)

                capture_client.ReleaseBuffer(num_frames)

                hr = capture_client.GetNextPacketSize(byref(packet_size))
                if hr < 0:
                    break

            windll.kernel32.Sleep(10)

        # 10. 停止
        audio_client.Stop()
        logger.info("Loopback 捕获已停止")

    # ------------------------------------------------------------------
    # 重采样
    # ------------------------------------------------------------------

    def _resample(
        self,
        audio: np.ndarray,
        src_sr: int,
        dst_sr: int,
        channels: int,
    ) -> np.ndarray:
        """混合为单声道 + 高质量重采样到目标采样率"""
        if audio.size == 0:
            return np.zeros((0, 1), dtype=np.float32)

        # 立体声 → 单声道
        if channels > 1:
            mono = np.mean(audio, axis=1).astype(np.float32)
        else:
            mono = audio.flatten().astype(np.float32)

        # 重采样
        if src_sr == dst_sr:
            return mono.reshape(-1, 1)

        # 整数倍抽取：直接取每 N 个样本（无损，无边界伪影）
        ratio = src_sr / dst_sr
        if abs(ratio - round(ratio)) < 0.001:
            step = int(round(ratio))
            mono = mono[::step]
        else:
            # 非整数倍：使用线性插值（精度足够，计算快）
            duration = len(mono) / src_sr
            target_len = max(1, int(duration * dst_sr))
            indices = np.linspace(0, len(mono) - 1, target_len, dtype=np.float32)
            idx_floor = np.floor(indices).astype(np.int32)
            idx_ceil = np.minimum(idx_floor + 1, len(mono) - 1)
            frac = indices - idx_floor.astype(np.float32)
            mono = mono[idx_floor] * (1 - frac) + mono[idx_ceil] * frac

        if len(mono) == 0:
            return np.zeros((0, 1), dtype=np.float32)

        return mono.astype(np.float32).reshape(-1, 1)
