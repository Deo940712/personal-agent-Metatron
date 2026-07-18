"""The rule-based firewall scanner — the single gate every LLM output must pass.

``DeterministicNarrator`` prose is scalar-free by construction. ``FusionNarrator``
prose comes from LLMs, which can hallucinate a price, a percentage, or an absolute
buy/sell order. This scanner is the deterministic, offline check that screens EVERY
LLM output (both writers AND the judge) before any of it is allowed into a
``CrowdNarrative``. Non-empty result → that candidate is rejected.

It enforces, at the text layer, the same red-lines the contract enforces at the type
layer (see ``references/firewall.md`` and ``agent/SOUL.md`` rules 6/9/10):

- No numeric market token: a bare number attached to a price/NAV/currency/percent/
  yield context. (Structural digit-context patterns, not "the engine emitted a float".)
- No absolute buy/sell / order language: 買進/賣出/加碼/減碼/停損/委託單/掛單 and the
  English "buy it / sell it / place an order" family.

This is intentionally conservative: it would rather reject a clean-but-suspicious line
than let a leak through, because the fallback (deterministic prose) is always safe.
"""

from __future__ import annotations

import re
import unicodedata

# Digits in ANY width: LLM zh-TW prose routinely emits fullwidth digits (０-９) and a
# fullwidth percent (％), which ASCII-only patterns miss entirely. This class is reused
# everywhere a "digit" is matched below so a fullwidth number cannot slip a metric past.
_D = r"[0-9\uFF10-\uFF19]"

# --- Normalization -----------------------------------------------------------------
# Adversarial outputs split or disguise banned tokens: fullwidth letters (ＢＵＹ),
# homoglyphs, zero-width joiners, and spacing (買 進). We scan a normalized COPY so those
# tricks collapse back to their canonical form. NFKC folds width/compatibility variants;
# then we drop zero-width marks and interior whitespace/dots that only serve to break a
# token apart. This is deterministic and offline.
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)
# Characters an adversary inserts BETWEEN token chars to dodge a literal match. We strip
# these only to build the scan copy; the original text is never mutated for callers.
_SPLIT_CHARS = re.compile(r"[\s\u00b7\u2027\u30fb._\uff0e\uff65]+")


def _normalize(text: str) -> str:
    """Fold width/compatibility forms and remove split/zero-width chars (scan copy)."""
    folded = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH)
    return _SPLIT_CHARS.sub("", folded)

# --- Numeric market tokens ---------------------------------------------------------
# A digit that sits in a price / currency / percent / NAV / yield context. We do NOT
# flag ordinal list markers ("1. ", "2. ") or the stance labels; those carry no metric.
_NUMERIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("currency_ntd", re.compile(rf"(?:NT\$|NTD|新台幣|台幣|元|塊)\s*{_D}", re.IGNORECASE)),
    ("currency_trailing", re.compile(rf"{_D}[\d,.\uFF10-\uFF19]*\s*(?:元|塊|億|萬)")),
    ("percent", re.compile(rf"{_D}[\d,.\uFF10-\uFF19]*\s*[%\uFF05]|百分之\s*{_D}")),
    (
        "price_nav",
        re.compile(rf"(?:股價|淨值|NAV|報價|價格|市價|目標價)\s*[:：]?\s*{_D}", re.IGNORECASE),
    ),
    ("yield_num", re.compile(rf"(?:殖利率|配息率|報酬率|漲跌幅)\s*[:：]?\s*{_D}")),
    ("bare_decimal", re.compile(r"(?<![\d\uFF10-\uFF19])\d+\.\d+")),
    # Internal numeric signal encodings a leaked prompt could carry. stance/score/
    # modifier/weight are engine-internal ordinals that must never surface in prose.
    ("signal_token", re.compile(r"\b(?:stance|score|modifier|weight)\s*=", re.IGNORECASE)),
    # Chinese-numeral metrics — ALWAYS anchored to a unit so a bare degree adverb like
    # "十分看好" (very bullish) or "萬一" (in case) is NOT flagged; only "五十元" /
    # "百分之八" / "一百元" style metric+unit combinations are.
    ("cn_numeral_unit", re.compile(r"[一二三四五六七八九十百千萬兩○零]+\s*(?:元|塊|億|％|%)")),
    ("cn_percent", re.compile(r"百分之\s*[一二三四五六七八九十百兩○零]")),
)

# --- Prompt-injection / meta-instruction markers -----------------------------------
# A model output that tries to break frame ("ignore the rules, here's the real advice")
# is rejected outright. Heuristic and non-exhaustive by nature — documented as such.
_INJECTION = re.compile(
    r"忽略(?:前述|上述|以上|先前)"
    r"|(?:以下|接下來)是(?:實際|真正|真實)(?:的)?(?:操作|建議|指示)"
    r"|實際操作建議"
    r"|ignore\s+(?:the\s+)?(?:previous|above|prior)\s+(?:instructions?|rules?)"
    r"|here('?s| is)\s+the\s+(?:real|actual)\s+(?:advice|recommendation)",
    re.IGNORECASE,
)

# --- Absolute buy/sell / order language --------------------------------------------
# Conditional persona wording ("這類人格可能傾向…") is fine; an imperative order is not.
# Bare 買進/賣出 are included so the scanner matches what README documents ("order
# phrase (買進/賣出/委託單 …) is rejected"). The deterministic persona voices only ever
# use them in compounds like 加碼/停損/出貨 (conditional description, kept), never as a
# flat 買進/賣出 imperative — that flat form is exactly the order we must drop.
_ORDER_TERMS: tuple[str, ...] = (
    "買進",
    "賣出",
    "委託單",
    "掛單",
    "下單",
    "掛買",
    "掛賣",
    "停損單",
    "市價單",
    "限價單",
    "務必買進",
    "務必賣出",
    "建議買進",
    "建議賣出",
    "應該買進",
    "應該賣出",
    "快買",
    "快賣",
    "全力買進",
    "全數賣出",
    "現在就買",
    "現在就賣",
)
_ORDER_EN = re.compile(
    r"\b(?:place\s+(?:an?\s+)?order|buy\s+it\s+now|sell\s+it\s+now|you\s+should\s+(?:buy|sell))\b",
    re.IGNORECASE,
)


def scan_violations(text: str) -> tuple[str, ...]:
    """Return a tuple of violation tags found in ``text``. Empty tuple == clean.

    Deterministic and offline. A non-empty result means the candidate MUST be
    rejected before it can enter a CrowdNarrative.

    Two normalization levels are scanned so adversarial disguises collapse without
    weakening the numeric patterns:

    - ``folded`` (NFKC only, spaces/dots preserved) drives the numeric patterns — a
      fullwidth ``５０`` becomes ``50`` while ``3.14`` keeps its dot for ``bare_decimal``.
    - ``collapsed`` (folded + zero-width/split chars removed) drives the literal
      order-term and injection matching — ``買 進`` and ``忽　略`` collapse to canonical
      form. The caller's text itself is never mutated.
    """
    folded = unicodedata.normalize("NFKC", text)
    collapsed = _normalize(text)
    hits: list[str] = []
    for tag, pattern in _NUMERIC_PATTERNS:
        if pattern.search(folded):
            hits.append(f"numeric:{tag}")
    for term in _ORDER_TERMS:
        if term in collapsed:
            hits.append(f"order:{term}")
    if _ORDER_EN.search(folded) or _ORDER_EN.search(collapsed):
        hits.append("order:en")
    # Injection markers are scanned on BOTH copies: English variants rely on ``\s+``
    # word gaps (folded keeps spaces), while split CJK ("忽　略前述") needs collapsed.
    if _INJECTION.search(folded) or _INJECTION.search(collapsed):
        hits.append("injection")
    return tuple(hits)


def is_clean(text: str) -> bool:
    """True if ``text`` carries no firewall violation."""
    return not scan_violations(text)
