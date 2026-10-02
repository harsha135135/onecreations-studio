from tools.admission import experiment_keys as ek

WF = {
    "4": {"class_type": "CLIPTextEncode", "_meta": {"title": "pos"}, "inputs": {"clip": ["2", 0], "text": "a temple"}},
    "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": ""}},
    "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": 1000}},
    "7": {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": 512, "height": 320, "length": 49, "batch_size": 1}},
}
BASE = dict(scene={"pillars": 8}, choreography={"m2a_asura": {"start": [-2.2, -3.5, 0], "end": [1.3, -4.5, 0]}},
            camera_digest="cam1", timewarp="identity", export_settings={"passes": True},
            control_meta={"convention": "min-max", "lo_pct": 0, "hi_pct": 100, "fps": "24/1"},
            workflow=WF, first_frame_sha256="ff1", model_hashes={"ltx": ["a", "b"]}, seed=1000)


def keys(**changes):
    return ek.keys_from_inputs(**dict(BASE, **changes))


def test_split_workflow_blanks_prompts_and_seed_without_mutating():
    prompts, blank = ek.split_workflow(WF)
    assert prompts == ["a temple", ""]
    assert blank["8"]["inputs"]["noise_seed"] == "<seed>" and blank["4"]["inputs"]["text"] == "<prompt>"
    assert "_meta" not in blank["4"] and WF["4"]["inputs"]["text"] == "a temple" and "_meta" in WF["4"]


def test_keys_follow_the_dependency_graph():
    k0 = keys()
    assert k0 == keys()                                   # deterministic
    wf2 = {**WF, "4": {**WF["4"], "inputs": {**WF["4"]["inputs"], "text": "a different prompt"}}}
    k_prompt = keys(workflow=wf2)
    assert k_prompt["control_render"] == k0["control_render"] and k_prompt["generation"] != k0["generation"]
    k_seed = keys(seed=1001)
    assert k_seed["control_render"] == k0["control_render"] and k_seed["generation"] != k0["generation"]
    k_cam = keys(camera_digest="cam2")
    assert k_cam["control_render"] != k0["control_render"] and k_cam["generation"] != k0["generation"]
    k_choreo = keys(choreography={"m2a_asura": {"start": [-2.0, -3.5, 0], "end": [1.3, -4.5, 0]}})
    assert k_choreo["control_render"] != k0["control_render"]
    k_ff = keys(first_frame_sha256="ff2")
    assert k_ff["control_render"] == k0["control_render"] and k_ff["generation"] != k0["generation"]
    wf_res = {**WF, "7": {**WF["7"], "inputs": {**WF["7"]["inputs"], "width": 768}}}
    assert keys(workflow=wf_res)["generation"] != k0["generation"]
