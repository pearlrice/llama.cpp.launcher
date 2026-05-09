# coding:utf-8
"""Download presets shared by the launcher UI and autodeploy script."""

DEFAULT_MODEL_PRESET_KEY = "qwen3.5-9b"

MODEL_PRESETS = {
    "none": {
        "display_name": "无",
        "directory": "",
        "llm_name": "",
        "mm_name": "",
        "artifacts": {},
    },
    "qwen3.5-27b": {
        "display_name": "Qwen3.5-27B UD-Q4_K_XL",
        "directory": "qwen3.5-27b",
        "llm_name": "Qwen3.5-27B-UD-Q4_K_XL",
        "mm_name": "Qwen3.5-mmproj-F16",
        "artifacts": {
            "llm": {
                "filename": "Qwen3.5-27B-UD-Q4_K_XL.gguf",
                "sources": [
                    ("HuggingFace", "https://huggingface.co/unsloth/Qwen3.5-27B-GGUF/resolve/main/Qwen3.5-27B-UD-Q4_K_XL.gguf"),
                    ("ModelScope", "https://modelscope.cn/models/unsloth/Qwen3.5-27B-GGUF/resolve/master/Qwen3.5-27B-UD-Q4_K_XL.gguf"),
                ],
            },
            "mm": {
                "filename": "mmproj-F16.gguf",
                "sources": [
                    ("HuggingFace", "https://huggingface.co/unsloth/Qwen3.5-27B-GGUF/resolve/main/mmproj-F16.gguf"),
                    ("ModelScope", "https://modelscope.cn/models/unsloth/Qwen3.5-27B-GGUF/resolve/master/mmproj-F16.gguf"),
                ],
            },
        },
    },
    "gemma-4-31b": {
        "display_name": "Gemma 4 31B UD-Q4_K_XL",
        "directory": "gemma-4-31b",
        "llm_name": "Gemma4-31B-UD-Q4_K_XL",
        "mm_name": "Gemma4-mmproj-BF16",
        "artifacts": {
            "llm": {
                "filename": "gemma-4-31B-it-UD-Q4_K_XL.gguf",
                "sources": [
                    ("HuggingFace", "https://huggingface.co/unsloth/gemma-4-31B-it-GGUF/resolve/main/gemma-4-31B-it-UD-Q4_K_XL.gguf"),
                    ("ModelScope", "https://modelscope.cn/models/unsloth/gemma-4-31B-it-GGUF/resolve/master/gemma-4-31B-it-UD-Q4_K_XL.gguf"),
                ],
            },
            "mm": {
                "filename": "mmproj-BF16.gguf",
                "sources": [
                    ("HuggingFace", "https://huggingface.co/unsloth/gemma-4-31B-it-GGUF/resolve/main/mmproj-BF16.gguf"),
                    ("ModelScope", "https://modelscope.cn/models/unsloth/gemma-4-31B-it-GGUF/resolve/master/mmproj-BF16.gguf"),
                ],
            },
        },
    },
    "qwen3.5-9b": {
        "display_name": "Qwen3.5-9B UD-Q4_K_XL",
        "directory": "qwen3.5-9b",
        "llm_name": "Qwen3.5-9B-UD-Q4_K_XL",
        "mm_name": "Qwen3.5-9B-mmproj-BF16",
        "artifacts": {
            "llm": {
                "filename": "Qwen3.5-9B-UD-Q4_K_XL.gguf",
                "sources": [
                    ("HuggingFace", "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-UD-Q4_K_XL.gguf"),
                    ("ModelScope", "https://modelscope.cn/models/unsloth/Qwen3.5-9B-GGUF/resolve/master/Qwen3.5-9B-UD-Q4_K_XL.gguf"),
                ],
            },
            "mm": {
                "filename": "mmproj-BF16.gguf",
                "sources": [
                    ("HuggingFace", "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/mmproj-BF16.gguf"),
                    ("ModelScope", "https://modelscope.cn/models/unsloth/Qwen3.5-9B-GGUF/resolve/master/mmproj-BF16.gguf"),
                ],
            },
        },
    },
}


def get_model_preset(key):
    return MODEL_PRESETS.get(key) or MODEL_PRESETS[DEFAULT_MODEL_PRESET_KEY]
