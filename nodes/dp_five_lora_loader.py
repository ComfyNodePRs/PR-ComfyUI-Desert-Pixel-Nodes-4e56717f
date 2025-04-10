import folder_paths
from nodes import LoraLoader
import torch
from typing import List, Tuple, Dict, Any
import os
import comfy.utils

class DP_Five_Lora:
    """
    Optimized ComfyUI node for loading up to five LoRA models simultaneously.
    """
    _lora_cache = {}  # Cache for loaded LoRA weights
    _weight_cache = {}  # Cache for preloaded weights
    
    def __init__(self):
        self.lora_loader = LoraLoader()
        self._setup_optimizations()
    
    @classmethod
    def INPUT_TYPES(cls):
        lora_files = ['None'] + folder_paths.get_filename_list("loras")
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "loader_state": (["ON", "OFF"],),
                "Lora_01": (lora_files,),
                "Lora_01_Strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.01}),
            },
            "optional": {
                "Lora_02": (lora_files,),
                "Lora_02_Strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.01}),
                "Lora_03": (lora_files,),
                "Lora_03_Strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.01}),
                "Lora_04": (lora_files,),
                "Lora_04_Strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.01}),
                "Lora_05": (lora_files,),
                "Lora_05_Strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.01}),
            }
        }
    
    RETURN_TYPES = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("model", "clip", "lora_info")
    FUNCTION = "apply_lora"
    CATEGORY = "DP/loaders"

    def _setup_optimizations(self):
        """Setup PyTorch optimizations"""
        if torch.cuda.is_available():
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
            torch.backends.cudnn.benchmark = True
            torch.backends.cudnn.deterministic = False
            
            # Optimize CUDA allocator
            torch.cuda.set_per_process_memory_fraction(0.95)
            torch.cuda.empty_cache()

    @classmethod
    def preload_weights(cls, lora_name: str):
        """Preload LoRA weights into RAM"""
        if lora_name not in [None, "None", "none"]:
            lora_path = folder_paths.get_full_path("loras", lora_name)
            if lora_path and lora_path not in cls._weight_cache:
                cls._weight_cache[lora_path] = comfy.utils.load_torch_file(lora_path)

    def _batch_apply_loras(self, model: Any, clip: Any, lora_batch: List[Tuple[str, float]]) -> Tuple[Any, Any]:
        """Apply multiple LoRAs in an optimized batch"""
        with torch.cuda.amp.autocast():  # Keep mixed precision
            for lora_name, strength in lora_batch:
                if lora_name != "None" and strength > 0:
                    # Use the proven working method instead of custom implementation
                    model, clip = self.lora_loader.load_lora(
                        model, clip, lora_name, strength, strength
                    )
                    
                    # Clear intermediate memory if needed
                    torch.cuda.empty_cache()
        
        return model, clip

    def apply_lora(self, model, clip, loader_state, Lora_01, Lora_01_Strength,
                  Lora_02="None", Lora_02_Strength=0.0,
                  Lora_03="None", Lora_03_Strength=0.0,
                  Lora_04="None", Lora_04_Strength=0.0,
                  Lora_05="None", Lora_05_Strength=0.0):
        
        if loader_state == "OFF":
            return (model, clip, "LoRA Models Info:\nBypassed - No LoRAs applied")

        weights_info = ["LoRA Models Info:"]
        loras = [
            (Lora_01, Lora_01_Strength),
            (Lora_02, Lora_02_Strength),
            (Lora_03, Lora_03_Strength),
            (Lora_04, Lora_04_Strength),
            (Lora_05, Lora_05_Strength)
        ]
        
        # Filter valid LoRAs and sort by size for optimal memory usage
        valid_loras = [(name, strength) for name, strength in loras 
                      if name not in [None, "None", "none"] and strength > 0]
        
        if valid_loras:
            # Preload all weights
            for lora_name, _ in valid_loras:
                self.preload_weights(lora_name)
            
            # Process in optimal batch size
            batch_size = 2  # Adjust based on available memory
            for i in range(0, len(valid_loras), batch_size):
                batch = valid_loras[i:i+batch_size]
                model, clip = self._batch_apply_loras(model, clip, batch)
                
                # Add to info string
                for name, strength in batch:
                    weights_info.append(f"{name}: {strength}")
                
                # Clear intermediate memory
                torch.cuda.empty_cache()
        
        return (model, clip, "\n".join(weights_info))

    @classmethod
    def cleanup_cache(cls):
        """Clear all caches to free memory"""
        cls._lora_cache.clear()
        cls._weight_cache.clear()
        torch.cuda.empty_cache()