"""模型加载器 — 支持 MPS/CPU 自动检测和量化"""

import logging
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoProcessor

logger = logging.getLogger(__name__)


def get_device(device_config: str) -> str:
    """根据配置和硬件可用性决定推理设备"""
    if device_config == "auto":
        if torch.backends.mps.is_available():
            # Apple Silicon GPU，通过 Metal Performance Shaders 加速
            logger.info("检测到 Apple Silicon MPS，使用 MPS 加速")
            return "mps"
        if torch.cuda.is_available():
            # NVIDIA GPU
            logger.info("检测到 CUDA GPU")
            return "cuda"
        # 没有 GPU，回退到 CPU
        logger.info("未检测到 GPU，使用 CPU")
        return "cpu"
    return device_config


def load_model(
    model_name: str,
    device: str = "auto",
    quantization: str | None = None,
) -> dict[str, Any]:
    """
    加载模型和处理器。

    Args:
        model_name: HuggingFace 模型名或本地路径
        device: 推理设备 (auto/mps/cpu/cuda)
        quantization: 量化方式 (None/4bit/8bit)

    Returns:
        {"model": model, "processor": processor, "device": device_str}
    """
    # 根据配置和硬件决定实际推理设备
    resolve_device = get_device(device)

    logger.info(f"正在加载模型: {model_name}")

    # 构建 from_pretrained 的额外参数
    kwargs: dict[str, Any] = {}

    # 量化配置：4-bit 或 8-bit，显著降低内存占用（如 31B 模型 4-bit 约 8GB）
    if quantization == "4bit":
        from transformers import BitsAndBytesConfig
        kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True)
        logger.info("使用 4-bit 量化加载")
    elif quantization == "8bit":
        from transformers import BitsAndBytesConfig
        kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
        logger.info("使用 8-bit 量化加载")

    # 非量化模式下需要手动设置设备和数据类型
    if quantization is None:
        if resolve_device == "mps":
            # MPS 模式：用 float32 避免数值溢出（float16 在 MPS 上容易产生 inf/nan）
            kwargs.setdefault("device_map", {"": resolve_device})
        else:
            # CUDA/CPU 模式：让 transformers 自动分配设备映射
            kwargs.setdefault("device_map", "auto")

    # 加载 processor（tokenizer + 图像处理器等）
    # 输出较简单，通常瞬间完成
    processor = AutoProcessor.from_pretrained(model_name)

    # 加载模型权重 — 这一步最耗时（几秒到几十秒）
    # transformers 内部会用 tqdm 显示 "Loading weights: XX%" 进度条
    # **kwargs 解包上面构建的参数（量化配置、设备映射等）
    # ignore_mismatched_sizes=True 抑制 "position_ids | UNEXPECTED" 警告
    # （旧模型权重存了该参数但新模型代码不再使用，无害）
    kwargs.setdefault("ignore_mismatched_sizes", True)
    model = AutoModelForCausalLM.from_pretrained(model_name, **kwargs)

    # 非量化模式下，模型可能先加载到 CPU，这里手动移到目标设备
    if quantization is None and resolve_device != "cpu":
        model = model.to(resolve_device)

    # 切换到评估模式：关闭 dropout 等训练专用层，确保推理结果确定性
    model.eval()

    logger.info(f"模型加载完成，设备: {resolve_device}")

    return {
        "model": model,
        "processor": processor,
        "device": resolve_device,
    }
