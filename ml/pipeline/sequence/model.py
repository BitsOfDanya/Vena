import torch
import torch.nn as nn


class EventTokenizer(nn.Module):
    def __init__(self, vocab_size, d_model):
        super().__init__()
        self.state_embedding = nn.Embedding(vocab_size, d_model, padding_idx=0)
        self.alarm_proj = nn.Linear(1, d_model)
        self.delta_proj = nn.Linear(1, d_model)
        self.time_proj = nn.Linear(2, d_model)

    def forward(self, state, alarm, delta, hour_sin, hour_cos):
        tok = self.state_embedding(state)
        tok = tok + self.alarm_proj(alarm.unsqueeze(-1))
        tok = tok + self.delta_proj(delta.unsqueeze(-1))
        time_feat = torch.stack([hour_sin, hour_cos], dim=-1)
        tok = tok + self.time_proj(time_feat)
        return tok


def _causal_mask(length, device):
    return torch.triu(torch.ones((length, length), dtype=torch.bool, device=device), diagonal=1)


class EventTransformer(nn.Module):
    def __init__(self, vocab_size, d_model=128, nhead=4, num_layers=3, dim_feedforward=None,
                 dropout=0.1):
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
        self.head = nn.Sequential(
            nn.LayerNorm(d_model),
            nn.Linear(d_model, d_model),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model, 1),
        )

    def forward(self, state, alarm, delta, hour_sin, hour_cos, pad_mask):
        tok = self.tokenizer(state, alarm, delta, hour_sin, hour_cos)

        b = tok.size(0)
        cls = self.cls_token.expand(b, -1, -1)
        tok = torch.cat([cls, tok], dim=1)
        cls_mask = torch.zeros(b, 1, dtype=torch.bool, device=pad_mask.device)
        full_mask = torch.cat([cls_mask, pad_mask], dim=1)

        out = self.encoder(tok, src_key_padding_mask=full_mask)
        cls_out = out[:, 0]
        logit = self.head(cls_out).squeeze(-1)
        return logit

    def num_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def load_pretrained_encoder(self, pretrain_model):
        self.tokenizer.load_state_dict(pretrain_model.tokenizer.state_dict())
        self.encoder.load_state_dict(pretrain_model.encoder.state_dict())


class EventPretrainModel(nn.Module):
    def __init__(self, vocab_size, d_model=128, nhead=4, num_layers=3, dim_feedforward=None,
                 dropout=0.1):
        super().__init__()
        dim_feedforward = dim_feedforward or d_model * 4
        self.tokenizer = EventTokenizer(vocab_size, d_model)
        layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=dim_feedforward,
            dropout=dropout, activation="gelu", batch_first=True, norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=num_layers)
        self.mask_head = nn.Linear(d_model, vocab_size)
        self.next_head = nn.Linear(d_model, vocab_size)

    def encode(self, state, alarm, delta, hour_sin, hour_cos, pad_mask, causal=False):
        tok = self.tokenizer(state, alarm, delta, hour_sin, hour_cos)
        attn_mask = _causal_mask(tok.size(1), tok.device) if causal else None
        return self.encoder(tok, mask=attn_mask, src_key_padding_mask=pad_mask)

    def forward_masked(self, state, alarm, delta, hour_sin, hour_cos, pad_mask):
        h = self.encode(state, alarm, delta, hour_sin, hour_cos, pad_mask, causal=False)
        return self.mask_head(h)

    def forward_next(self, state, alarm, delta, hour_sin, hour_cos, pad_mask):
        h = self.encode(state, alarm, delta, hour_sin, hour_cos, pad_mask, causal=True)
        return self.next_head(h)

    def num_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
