"""NII AntiDeepfake checkpoints (fairseq wav2vec2 + mean-pool + linear, CC BY-NC-SA 4.0) loaded into HF transformers
Wav2Vec2Model without fairseq. Score = logit_fake - logit_real (higher = more synthetic). Input: whole clip, 16 kHz,
waveform layer-normalized (zero mean, unit variance) as in the authors' inference script."""
import re, torch
from pathlib import Path
from safetensors.torch import load_file
from transformers import Wav2Vec2Config, Wav2Vec2Model
def _map(k):
    k = k.replace("m_ssl.model.", "")
    k = re.sub(r"feature_extractor\.conv_layers\.(\d+)\.0\.", r"feature_extractor.conv_layers.\1.conv.", k)
    k = re.sub(r"feature_extractor\.conv_layers\.(\d+)\.2\.1\.", r"feature_extractor.conv_layers.\1.layer_norm.", k)
    if k.startswith("layer_norm."): k = "feature_projection." + k
    k = k.replace("post_extract_proj.", "feature_projection.projection.")
    k = k.replace("encoder.pos_conv.0.", "encoder.pos_conv_embed.conv.")
    k = k.replace(".self_attn.", ".attention.").replace(".self_attn_layer_norm.", ".layer_norm.")
    k = k.replace(".fc1.", ".feed_forward.intermediate_dense.").replace(".fc2.", ".feed_forward.output_dense.")
    k = k.replace("mask_emb", "masked_spec_embed")
    return k
class AntiDeepfake(torch.nn.Module):
    def __init__(self, d):
        super().__init__(); d = Path(d)
        cfg = Wav2Vec2Config.from_pretrained(d); cfg.layerdrop = 0.0; cfg.mask_time_prob = 0.0; cfg.apply_spec_augment = False
        self.ssl = Wav2Vec2Model(cfg); self.fc = torch.nn.Linear(cfg.hidden_size, 2)
        sd = load_file(str(d / "model.safetensors")); ssl_sd, miss = {}, []
        for k, v in sd.items():
            if k.startswith("proj_fc."): continue
            ssl_sd[_map(k)] = v
        own = self.ssl.state_dict()
        # weight-norm parametrisation names differ across torch versions
        for a, b in (("encoder.pos_conv_embed.conv.weight_g", "encoder.pos_conv_embed.conv.parametrizations.weight.original0"),
                     ("encoder.pos_conv_embed.conv.weight_v", "encoder.pos_conv_embed.conv.parametrizations.weight.original1")):
            if a in ssl_sd and a not in own and b in own: ssl_sd[b] = ssl_sd.pop(a)
        ssl_sd = {k: v for k, v in ssl_sd.items() if k in own}
        missing = [k for k in own if k not in ssl_sd]
        self.ssl.load_state_dict(ssl_sd, strict=False)
        self.fc.weight.data, self.fc.bias.data = sd["proj_fc.weight"], sd["proj_fc.bias"]
        self.missing = missing
    @torch.inference_mode()
    def score(self, x):
        w = torch.as_tensor(x, dtype=torch.float32, device=self.fc.weight.device)
        w = torch.nn.functional.layer_norm(w, w.shape)[None]
        h = self.ssl(w).last_hidden_state.mean(1)
        lg = self.fc(h)[0].float()
        return float(lg[0] - lg[1])
