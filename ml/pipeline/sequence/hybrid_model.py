import torch
import torch.nn as nn

from pipeline.sequence.model import EventTokenizer


class HybridEventTransformer(nn.Module):
    def __init__(self, vocab_size, feature_dim, d_model=128, nhead=4, num_layers=3,
                 dim_feedforward=None, dropout=0.1):
        super().__init__()
        dim_feedforward = dim_feedforward or d_model * 4
        self.tokenizer = EventTokenizer(vocab_size, d_model)
        self.cls_token = nn.Parameter(torch.zeros(1, 1, d_model))
        nn.init.normal_(self.cls_token, std=0.02)
        layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=dim_feedforward,
            dropout=dropout, activation="gelu", batch_first=True, norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=num_layers)
        fusion_dim = d_model + feature_dim
        self.fusion_norm = nn.LayerNorm(fusion_dim)
        self.head = nn.Sequential(
            nn.Linear(fusion_dim, d_model),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model, 1),
        )

    def forward(self, state, alarm, delta, hour_sin, hour_cos, pad_mask, features):
        tok = self.tokenizer(state, alarm, delta, hour_sin, hour_cos)

        b = tok.size(0)
        cls = self.cls_token.expand(b, -1, -1)
        tok = torch.cat([cls, tok], dim=1)
        cls_mask = torch.zeros(b, 1, dtype=torch.bool, device=pad_mask.device)
        full_mask = torch.cat([cls_mask, pad_mask], dim=1)

        out = self.encoder(tok, src_key_padding_mask=full_mask)
        cls_out = out[:, 0]

        fused = torch.cat([cls_out, features], dim=-1)
        fused = self.fusion_norm(fused)
        logit = self.head(fused).squeeze(-1)
        return logit

    def num_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def load_pretrained_encoder(self, pretrain_model):
        self.tokenizer.load_state_dict(pretrain_model.tokenizer.state_dict())
        self.encoder.load_state_dict(pretrain_model.encoder.state_dict())
