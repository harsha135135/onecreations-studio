import json
import struct

from tools import inspect_safetensors as ist


def make_safetensors(path, tensors, metadata=None):
    header, offset = {}, 0
    for name, (dtype, shape) in tensors.items():
        n = ist.DTYPE_BYTES[dtype]
        for d in shape:
            n *= d
        header[name] = {"dtype": dtype, "shape": shape, "data_offsets": [offset, offset + n]}
        offset += n
    if metadata:
        header["__metadata__"] = metadata
    raw = json.dumps(header).encode()
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"\0" * offset)


def test_lora_summary_peft_naming(tmp_path):
    f = tmp_path / "adapter.safetensors"
    tensors = {}
    for i in range(3):
        for proj in ("to_q", "to_k"):
            base = f"transformer_blocks.{i}.attn1.{proj}"
            tensors[base + ".lora_A.weight"] = ("BF16", [32, 64])
            tensors[base + ".lora_B.weight"] = ("BF16", [64, 32])
    make_safetensors(f, tensors, {"format": "pt"})
    header, meta = ist.read_header(f)
    lo = ist.lora_summary(header)
    assert meta == {"format": "pt"}
    assert lo["lora_modules"] == 6
    assert lo["rank_histogram"] == {32: 6}
    assert lo["module_families"] == {
        "transformer_blocks.N.attn1.to_k": [32],
        "transformer_blocks.N.attn1.to_q": [32],
    }
    assert lo["incomplete_or_mismatched"] == []


def test_lora_summary_kohya_naming_with_alpha_and_mismatch(tmp_path):
    f = tmp_path / "kohya.safetensors"
    make_safetensors(f, {
        "lora_unet_a.lora_down.weight": ("F16", [16, 8]),
        "lora_unet_a.lora_up.weight": ("F16", [8, 16]),
        "lora_unet_a.alpha": ("F16", []),
        "lora_unet_b.lora_down.weight": ("F16", [16, 8]),
        "lora_unet_b.lora_up.weight": ("F16", [8, 4]),   # rank mismatch
        "lora_unet_c.lora_down.weight": ("F16", [4, 8]),  # missing up
    })
    header, _ = ist.read_header(f)
    lo = ist.lora_summary(header)
    assert lo["rank_histogram"] == {16: 1}
    assert lo["alpha_tensors"] == 1
    assert lo["incomplete_or_mismatched"] == ["lora_unet_b", "lora_unet_c"]


def test_summary_counts_params(tmp_path):
    f = tmp_path / "m.safetensors"
    make_safetensors(f, {"w": ("BF16", [4, 4]), "b": ("F32", [4])})
    header, _ = ist.read_header(f)
    s = ist.summarize(header)
    assert s["params"] == 20
    assert s["data_bytes"] == 4 * 4 * 2 + 4 * 4
    assert ist.main([str(f), "--lora-summary", "--list"]) == 0
