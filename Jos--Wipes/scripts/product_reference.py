"""Shared helpers for product-reference intent and official product image resolution."""

from __future__ import annotations

import unicodedata
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent.resolve()
PRODUCT_REFERENCE_DIR = PROJECT_ROOT / "assets" / "referencias"

PRODUCT_IMAGE_CANDIDATES = [
    "embalagem_jose_wipes_oficial.png",
    "embalagem_jose_wipes_oficial-removebg-preview.png",
    "embalagem_jose_wipes_oficial-removebg.png",
    "embalagem_jose_wipes_oficial.webp",
    "embalagem_jose_wipes_oficial.jpg",
    "embalagem_jose_wipes_oficial.jpeg",
]

PRODUCT_IMAGE_GLOB_PATTERNS = [
    "embalagem_jose_wipes_oficial*.png",
    "embalagem_jose_wipes_oficial*.webp",
    "embalagem_jose_wipes_oficial*.jpg",
    "embalagem_jose_wipes_oficial*.jpeg",
    "*jose*wipes*embalagem*.png",
    "*jose*wipes*package*.png",
]

PRODUCT_REFERENCE_KEYWORDS = (
    "embalagem",
    "embalagem oficial",
    "usar a embalagem",
    "use a embalagem",
    "mostrar a embalagem",
    "mostrar o produto",
    "usar o produto",
    "pacote",
    "produto",
    "wipes",
    "wet wipes",
    "package",
    "packet",
    "lenço",
    "lenços",
    "lenco",
    "lencos",
    "lenço umedecido",
    "lenço umedecido oficial",
    "lenços umedecidos",
    "lenco umedecido",
    "lencos umedecidos",
)


def _normalize_text(text: str | None) -> str:
    if not text:
        return ""

    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(normalized.lower().split())


def detectar_gatilhos_referencia_produto(*texts: str | None) -> list[str]:
    """Return the matched normalized trigger keywords for product-reference intent."""

    combined = " ".join(_normalize_text(text) for text in texts if text).strip()
    if not combined:
        return []

    matches: list[str] = []
    for keyword in PRODUCT_REFERENCE_KEYWORDS:
        normalized_keyword = _normalize_text(keyword)
        if normalized_keyword in combined and normalized_keyword not in matches:
            matches.append(normalized_keyword)
    return matches


def prompt_pede_referencia_produto(*texts: str | None) -> bool:
    """True when the provided text asks to show/use the package or wet wipes."""

    return bool(detectar_gatilhos_referencia_produto(*texts))


def obter_imagem_produto_path(*, strict: bool = False) -> Path:
    """Resolve the official product image inside assets/referencias with filename fallbacks."""

    candidatos: list[Path] = [PRODUCT_REFERENCE_DIR / name for name in PRODUCT_IMAGE_CANDIDATES]

    vistos = {path.resolve() for path in candidatos if path.exists()}
    encontrados = [path for path in candidatos if path.exists()]

    for pattern in PRODUCT_IMAGE_GLOB_PATTERNS:
        for path in sorted(PRODUCT_REFERENCE_DIR.glob(pattern)):
            resolved = path.resolve()
            if resolved not in vistos:
                vistos.add(resolved)
                encontrados.append(path)

    if encontrados:
        return encontrados[0]

    if strict:
        raise FileNotFoundError(
            f"Nenhuma imagem oficial do produto foi encontrada em {PRODUCT_REFERENCE_DIR}"
        )

    return candidatos[0]


def scene_dict_pede_referencia_produto(scene: dict[str, object] | None) -> bool:
    """Infer product-reference need from a legacy scene dict."""

    if not scene:
        return False

    produto_overlay = scene.get("produto_overlay", {})
    if isinstance(produto_overlay, dict) and produto_overlay.get("ativo"):
        return True

    audio = scene.get("audio", {})
    texto_overlay = scene.get("texto_overlay", {})
    textos = [
        scene.get("titulo"),
        scene.get("prompt"),
        audio.get("texto_fala") if isinstance(audio, dict) else None,
        texto_overlay.get("texto") if isinstance(texto_overlay, dict) else None,
    ]
    return prompt_pede_referencia_produto(*textos)


def aplicar_regra_referencia_produto_plano(
    plano: dict[str, object],
    briefing: str | None = None,
) -> dict[str, object]:
    """Ensure a legacy plan marks at least one product shot when the briefing asks for it."""

    cenas = plano.get("cenas", [])
    if not isinstance(cenas, list):
        return plano

    any_scene_marked = False
    briefing_pede_produto = prompt_pede_referencia_produto(briefing)

    for scene in cenas:
        if not isinstance(scene, dict):
            continue
        produto_overlay = scene.setdefault("produto_overlay", {})
        if not isinstance(produto_overlay, dict):
            produto_overlay = {}
            scene["produto_overlay"] = produto_overlay

        if scene_dict_pede_referencia_produto(scene):
            produto_overlay["ativo"] = True
            produto_overlay.setdefault("posicao", "centro_inferior")
            produto_overlay.setdefault("tamanho_pct", 55)
            any_scene_marked = True

    if briefing_pede_produto and cenas and not any_scene_marked:
        last_scene = cenas[-1]
        if isinstance(last_scene, dict):
            produto_overlay = last_scene.setdefault("produto_overlay", {})
            if isinstance(produto_overlay, dict):
                produto_overlay["ativo"] = True
                produto_overlay.setdefault("posicao", "centro_inferior")
                produto_overlay.setdefault("tamanho_pct", 55)

    return plano
