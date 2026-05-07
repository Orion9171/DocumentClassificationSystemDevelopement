# import dependencies
import os
import re
import json
import pickle
from contextlib import nullcontext
from typing import Dict, Tuple, Optional, List
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from transformers import AutoTokenizer, AutoConfig, AutoModelForCausalLM
from peft import PeftModel

# OCR settings / File parsers
try:
    import fitz  
except Exception:
    fitz = None

try:
    from docx import Document
except Exception:
    Document = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import pytesseract
except Exception:
    pytesseract = None

# Chunking+Pooling Classifier
class ChunkPoolingClassifier(nn.Module):
    def __init__(self, backbone: nn.Module, hidden_size: int, num_labels: int, pool: str = "last"):
        super().__init__()
        self.encoder = backbone 
        self.classifier = nn.Linear(hidden_size, num_labels)
        self.pool = pool

    def _masked_mean(self, token_hidden, attn_mask):
        m = attn_mask.unsqueeze(-1).to(token_hidden.dtype)  # (N, L, 1)
        denom = m.sum(dim=1).clamp_min(1.0)
        return (token_hidden * m).sum(dim=1) / denom

    def _last_token(self, token_hidden, attn_mask):
        lengths = attn_mask.long().sum(dim=1).clamp_min(1)  # (N,)
        idx = (lengths - 1).view(-1, 1, 1).expand(-1, 1, token_hidden.size(-1))
        idx = idx.to(token_hidden.device)
        return token_hidden.gather(1, idx).squeeze(1)

    def _get_base_model(self):
        """
        CausalLM: model.model 是 transformer 主體
        PEFT: base_model.model 也可能存在
        """
        base = getattr(self.encoder, "model", None)
        if base is None:
            base = getattr(getattr(self.encoder, "base_model", None), "model", None)
        return base if base is not None else self.encoder

    def forward(self, input_ids=None, attention_mask=None, chunk_mask=None, labels=None, **kwargs):
        kwargs.pop("labels", None)

        device = input_ids.device

        if attention_mask is None:
            attention_mask = torch.ones_like(input_ids, device=device)

        if input_ids.dim() == 2:
            B, L = input_ids.shape
            input_ids = input_ids.view(B, 1, L)
            attention_mask = attention_mask.view(B, 1, L)
            if chunk_mask is None:
                chunk_mask = torch.ones((B, 1), device=device, dtype=torch.float32)
        else:
            if chunk_mask is None:
                B, C, _ = input_ids.shape
                chunk_mask = torch.ones((B, C), device=device, dtype=torch.float32)

        input_ids = input_ids.to(device)
        attention_mask = attention_mask.to(device)
        chunk_mask = chunk_mask.to(device)

        B, C, L = input_ids.shape

        flat_ids = input_ids.reshape(-1, L)
        flat_attn = attention_mask.reshape(-1, L)

        if self.classifier.weight.device != device:
            self.classifier.to(device)

        base = self._get_base_model()

        out = base(
            input_ids=flat_ids,
            attention_mask=flat_attn,
            output_hidden_states=True,
            return_dict=True,
        )

        token_hidden = getattr(out, "last_hidden_state", None)
        if token_hidden is None:
            hs = getattr(out, "hidden_states", None)
            token_hidden = hs[-1] if hs is not None else None

        if token_hidden is None:
            raise ValueError("Backbone output has no last_hidden_state/hidden_states. Check model type.")

        # --- token pooling per chunk ---
        if self.pool == "last":
            rep = self._last_token(token_hidden, flat_attn)
        elif self.pool == "mean":
            rep = self._masked_mean(token_hidden, flat_attn)
        elif self.pool == "cls":
            rep = token_hidden[:, 0]
        else:
            raise ValueError(f"Unknown pool type: {self.pool}")

        # --- chunk pooling ---
        H = rep.size(-1)
        rep = rep.view(B, C, H) 
        m = chunk_mask.unsqueeze(-1).to(rep.dtype)  
        sent_vec = (rep * m).sum(dim=1) / m.sum(dim=1).clamp_min(1e-6)  

        logits = self.classifier(sent_vec)  
        return {"logits": logits}
    
# Chunking Collator
class ChunkingCollator:
    def __init__(self, tokenizer, chunk_len=None, overlap=32, max_chunks=8):
        self.tok = tokenizer
        self.chunk_len = int(chunk_len or getattr(tokenizer, "model_max_length", 512) or 512)
        self.stride = max(1, self.chunk_len - int(overlap))
        self.max_chunks = int(max_chunks)
        self.pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id

    def _make_chunks(self, ids):
        if not ids:
            ids = [self.pad_id]

        chunks, i = [], 0
        while i < len(ids) and len(chunks) < self.max_chunks:
            chunks.append(ids[i:i + self.chunk_len])
            i += self.stride

        if not chunks:
            chunks = [[self.pad_id]]

        padded, attn = [], []
        for seg in chunks:
            if len(seg) < self.chunk_len:
                pad = self.chunk_len - len(seg)
                padded.append(seg + [self.pad_id] * pad)
                attn.append([1] * len(seg) + [0] * pad)
            else:
                padded.append(seg[:self.chunk_len])
                attn.append([1] * self.chunk_len)
        return padded, attn

    def __call__(self, features):
        import torch
        def get_text(f):
            t = f.get("instruction", None)
            if t is None:
                t = f.get("text", "")
            if t is None:
                t = ""
            return str(t)

        texts  = [get_text(f) for f in features]
        labels = torch.tensor([int(f["labels"]) for f in features], dtype=torch.long)

        all_ids, all_attn = [], []
        for t in texts:
            enc = self.tok(t, add_special_tokens=True, truncation=False, return_attention_mask=False)
            ids = enc.get("input_ids", []) or []
            p, a = self._make_chunks(ids)
            all_ids.append(p)
            all_attn.append(a)

        B = len(texts)
        C = max(len(x) for x in all_ids) 
        L = self.chunk_len

        input_ids      = torch.full((B, C, L), self.pad_id, dtype=torch.long)
        attention_mask = torch.zeros((B, C, L), dtype=torch.long)
        chunk_mask     = torch.zeros((B, C),    dtype=torch.float32)

        for i in range(B):
            Ci = len(all_ids[i])
            input_ids[i, :Ci]      = torch.tensor(all_ids[i],  dtype=torch.long)
            attention_mask[i, :Ci] = torch.tensor(all_attn[i], dtype=torch.long)
            chunk_mask[i, :Ci]     = 1.0

        return {
            "input_ids": input_ids,            
            "attention_mask": attention_mask,  
            "chunk_mask": chunk_mask,          
            "labels": labels                
        }
def load_app_config(config_path: Optional[str] = None) -> dict:
    """
    read config.json。
    預設會從 classifier_service.py 同一層資料夾找 config.json。
    """
    base_path = os.path.dirname(os.path.abspath(__file__))

    if config_path is None:
        config_path = os.path.join(base_path, "config.json")

    if not os.path.exists(config_path):
        print(f"[ClassifierService] 找不到 config.json，使用程式預設設定：{config_path}")
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)
# Model Deployment Service
class ClassifierService:
    def __init__(self, model_dir: Optional[str] = None, config_path: Optional[str] = None):
        self.base_path = os.path.dirname(os.path.abspath(__file__))

        # read config.json
        self.app_config = load_app_config(config_path)
        model_config = self.app_config.get("model_config", {})

        # 優先順序：
        # 1. 外部傳入 model_dir
        # 2. config.json 的 model_config.model_path
        # 3. classifier_service.py 同層的 Llama-classifier-finetuned
        config_model_path = model_config.get("model_path", "")

        self.model_dir = (
            model_dir
            or config_model_path
            or os.path.join(self.base_path, "Llama-classifier-finetuned")
        )

        self.model_dir = os.path.abspath(os.path.expanduser(self.model_dir))

        # config 裡可選填 base_model
        self.config_base_model = model_config.get("base_model", "")

        print(f"[ClassifierService] 使用模型資料夾：{self.model_dir}")

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = None
        self.clf = None
        self.chunk_collator = None
        self.id2label: Dict[int, str] = {}
        self.label2id: Dict[str, int] = {}
        self.meta = {}
        self.model_ready = False

        self._load_all()
    # Load in the model
    def _load_all(self):
        if not os.path.isdir(self.model_dir):
            raise FileNotFoundError(f"找不到模型資料夾：{self.model_dir}")

        label_map_path = os.path.join(self.model_dir, "label_map.json")
        meta_path = os.path.join(self.model_dir, "model_meta.json")
        classifier_head_path = os.path.join(self.model_dir, "classifier_head.pt")

        if not os.path.exists(label_map_path):
            raise FileNotFoundError(f"找不到 label_map.json：{label_map_path}")
        if not os.path.exists(meta_path):
            raise FileNotFoundError(f"找不到 model_meta.json：{meta_path}")
        if not os.path.exists(classifier_head_path):
            raise FileNotFoundError(f"找不到 classifier_head.pt：{classifier_head_path}")

        with open(label_map_path, "r", encoding="utf-8") as f:
            lm = json.load(f)
        self.id2label = {int(k): v for k, v in lm["id2label"].items()}
        self.label2id = {str(k): int(v) for k, v in lm["label2id"].items()}

        with open(meta_path, "r", encoding="utf-8") as f:
            self.meta = json.load(f)

        backbone_name = (self.config_base_model or self.meta.get("backbone_name", "") or "meta-llama/Meta-Llama-3-8B-Instruct")
        pool = self.meta.get("pool", "last")
        chunk_len = int(self.meta.get("chunk_len", 256))
        overlap = int(self.meta.get("overlap", 32))
        max_chunks = int(self.meta.get("max_chunks", 4))

        # tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_dir, trust_remote_code=True)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.tokenizer.padding_side = "right"
        self.tokenizer.truncation_side = "right"

        # backbone
        torch_dtype = torch.float16 if self.device == "cuda" else torch.float32

        # 先試 4bit（如果環境支援）
        backbone = None
        quant_loaded = False

        if self.device == "cuda":
            try:
                from transformers import BitsAndBytesConfig

                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch_dtype,
                    bnb_4bit_use_double_quant=True,
                )
                cfg = AutoConfig.from_pretrained(backbone_name, trust_remote_code=True)
                cfg.use_cache = False

                backbone = AutoModelForCausalLM.from_pretrained(
                    backbone_name,
                    config=cfg,
                    quantization_config=bnb_config,
                    device_map="auto",
                    trust_remote_code=True,
                )
                quant_loaded = True
                print("[ClassifierService] 4bit backbone loaded.")
            except Exception as e:
                print(f"[ClassifierService] 4bit 載入失敗，改用一般模式：{e}")

        if backbone is None:
            cfg = AutoConfig.from_pretrained(backbone_name, trust_remote_code=True)
            cfg.use_cache = False
            backbone = AutoModelForCausalLM.from_pretrained(
                backbone_name,
                config=cfg,
                torch_dtype=torch_dtype,
                trust_remote_code=True,
            )
            backbone.to(self.device)
            print("[ClassifierService] full precision / half precision backbone loaded.")

        # LoRA adapter
        backbone = PeftModel.from_pretrained(backbone, self.model_dir)
        backbone.eval()

        hidden_size = getattr(backbone.config, "hidden_size", None)
        if hidden_size is None:
            hidden_size = getattr(getattr(backbone, "config", None), "hidden_size", None)
        if hidden_size is None:
            raise ValueError("找不到 hidden_size，無法建立 classifier head。")

        num_labels = len(self.id2label)

        self.clf = ChunkPoolingClassifier(
            backbone=backbone,
            hidden_size=hidden_size,
            num_labels=num_labels,
            pool=pool,
        )

        # 載入 classifier head
        state = torch.load(classifier_head_path, map_location="cpu")
        self.clf.classifier.load_state_dict(state, strict=True)
        self.clf.to(self.device)
        self.clf.eval()

        self.chunk_collator = ChunkingCollator(
            tokenizer=self.tokenizer,
            chunk_len=chunk_len,
            overlap=overlap,
            max_chunks=max_chunks,
        )

        self.model_ready = True
        print("[ClassifierService] model ready.")

    def amp_context(self):
        if self.device == "cuda":
            return torch.amp.autocast("cuda", dtype=torch.float16)
        return nullcontext()

    # Text Extract
    def extract_text_from_file(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".txt":
            return self._extract_text_from_txt(file_path)

        if ext == ".docx":
            return self._extract_text_from_docx(file_path)

        if ext == ".pdf":
            text = self._extract_text_from_pdf(file_path)
            if text.strip():
                return text
            return self._extract_text_from_pdf_ocr(file_path)

        if ext in [".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"]:
            return self._extract_text_from_image_ocr(file_path)

        raise ValueError(f"不支援的檔案格式：{ext}")

    def _extract_text_from_txt(self, file_path: str) -> str:
        for enc in ["utf-8", "utf-8-sig", "cp950", "big5"]:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    return f.read()
            except Exception:
                continue
        return ""

    def _extract_text_from_docx(self, file_path: str) -> str:
        if Document is None:
            raise RuntimeError("缺少 python-docx。請安裝：pip install python-docx")
        doc = Document(file_path)
        lines = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
        return "\n".join(lines)

    def _extract_text_from_pdf(self, file_path: str) -> str:
        if fitz is None:
            return ""
        try:
            doc = fitz.open(file_path)
            texts = []
            for page in doc:
                t = page.get_text("text")
                if t:
                    texts.append(t)
            return "\n".join(texts).strip()
        except Exception:
            return ""

    def _extract_text_from_pdf_ocr(self, file_path: str) -> str:
        if fitz is None or Image is None or pytesseract is None:
            return ""
        try:
            doc = fitz.open(file_path)
            texts = []
            for page_idx in range(len(doc)):
                page = doc.load_page(page_idx)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                tmp_img = f"{file_path}_ocr_tmp_{page_idx}.png"
                pix.save(tmp_img)
                try:
                    texts.append(self._extract_text_from_image_ocr(tmp_img))
                finally:
                    if os.path.exists(tmp_img):
                        os.remove(tmp_img)
            return "\n".join(texts).strip()
        except Exception:
            return ""

    def _extract_text_from_image_ocr(self, file_path: str) -> str:
        if pytesseract is None or Image is None:
            raise RuntimeError("缺少 OCR 依賴。請安裝 pillow、pytesseract，並安裝 tesseract OCR。")
        img = Image.open(file_path)
        return pytesseract.image_to_string(img, lang="chi_tra+eng")

   # Data Preprocessing
    def preprocess_text(self, raw_text: str) -> str:
        """
        只抽取公文主旨，避免公文文號、來文機關、日期等欄位干擾分類。
        適用格式：
        1. 主旨：xxxx
        2. 主旨
        xxxx
        """
        text = (raw_text or "").replace("\x00", " ").strip()
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\r\n", "\n", text)
        text = re.sub(r"\n+", "\n", text)

        if not text:
            return ""

        # Case 1: 主旨：xxxx 或 主旨: xxxx
        m = re.search(r"主旨\s*[:：]\s*(.+)", text, flags=re.DOTALL)
        if m:
            subject = m.group(1).strip()
            subject = self._clean_subject_tail(subject)
            return subject[:500]

        # Case 2: 「主旨」獨立成一行，下一行才是主旨內容
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        for i, line in enumerate(lines):
            if line == "主旨":
                subject_lines = lines[i + 1:]
                subject = " ".join(subject_lines).strip()
                subject = self._clean_subject_tail(subject)
                return subject[:500]

            # 處理像「主旨 行政院...」這種同一行但沒有冒號的情況
            if line.startswith("主旨 "):
                subject = line.replace("主旨", "", 1).strip()
                subject = self._clean_subject_tail(subject)
                return subject[:500]

        # Case 3: fallback，排除明顯不是主旨的欄位
        ignore_keywords = [
            "公文測試資料",
            "LLM 公文分類系統端到端測試用 PDF",
            "公文文號",
            "來文機關",
            "來文字號",
            "來文日期",
            "辦畢日期",
            "承辦單位",
            "DEPT_NO",
        ]

        candidate_lines = []
        for line in lines:
            if any(keyword in line for keyword in ignore_keywords):
                continue
            if len(line) >= 10:
                candidate_lines.append(line)

        if candidate_lines:
            return " ".join(candidate_lines[:3])[:500]

        return text[:500]


    def _clean_subject_tail(self, subject: str) -> str:
        """
        避免主旨後面誤接到其他欄位。
        """
        subject = re.sub(r"\s+", " ", subject).strip()

        stop_words = [
            "說明",
            "附件",
            "正本",
            "副本",
            "承辦單位",
            "DEPT_NO",
            "來文機關",
            "來文字號",
            "來文日期",
            "辦畢日期",
        ]

        for stop in stop_words:
            idx = subject.find(stop)
            if idx > 0:
                subject = subject[:idx].strip()

        return subject

    # Inference
    @torch.no_grad()
    def predict_text(self, text: str) -> Tuple[str, float]:
        if not self.model_ready:
            raise RuntimeError("模型尚未成功載入。")
        text = self.preprocess_text(text)
        if not text:
            return "無法辨識", 0.0

        example = {"instruction": text, "labels": 0}
        batch = self.chunk_collator([example])

        for k, v in batch.items():
            if isinstance(v, torch.Tensor):
                batch[k] = v.to(self.device)

        with self.amp_context():
            outputs = self.clf(**batch)

        logits = outputs["logits"] if isinstance(outputs, dict) else outputs.logits
        probs = F.softmax(logits.float(), dim=-1)[0].detach().cpu().numpy()

        pred_id = int(np.argmax(probs))
        pred_label = self.id2label[pred_id]
        max_prob = float(probs[pred_id])

        return pred_label, max_prob

    def classify_file(self, file_path: str) -> Tuple[str, float]:
        raw_text = self.extract_text_from_file(file_path)
        return self.predict_text(raw_text)

_service: Optional[ClassifierService] = None

def get_classifier_service() -> ClassifierService:
    global _service
    if _service is None:
        _service = ClassifierService()
    return _service

def classify_text(text: str) -> Tuple[str, float]:
    return get_classifier_service().predict_text(text)

def classify_file(file_path: str) -> Tuple[str, float]:
    return get_classifier_service().classify_file(file_path)
