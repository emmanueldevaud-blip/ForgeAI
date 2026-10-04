"""Score de qualité d'une photo (heuristique locale, Pillow).

Tout se calcule sur une miniature : ni l'original ni un modèle externe ne
sont nécessaires. Les métriques sont bornées à [0, 1] et restent des
heuristiques (documentées telles quelles dans docs/photos.md) :

- ``sharpness``    : variance du laplacien (netteté perçue) ;
- ``blur``         : densité des contours (« pas flou ») ;
- ``exposure``     : luminosité moyenne + pixels saturés ;
- ``composition``  : proche d'un format standard (1:1, 4:3, 3:2, 16:9) ;
- ``overall``      : moyenne pondérée des quatre.

En cas de problème quelconque, ``assess_quality`` lève une exception que
l'appelant attrape : la qualité ne doit jamais faire échouer une analyse.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

# Échantillon de travail : suffisant pour des métriques, rapide en Python pur.
_SAMPLE_MAX = 256

# Seuil |laplacien| au-dessus duquel un pixel est compté comme « contour ».
_EDGE_THRESHOLD = 12.0
# Densité de contours considérée comme « image nette ».
_EDGE_TARGET = 0.05
# Variance du laplacien donnant un score de netteté de 0,5.
_SHARPNESS_HALF = 100.0

_STANDARD_RATIOS = (1.0, 4 / 3, 3 / 2, 16 / 9, 9 / 16, 3 / 4, 2 / 3)

_WEIGHTS = {"sharpness": 0.35, "blur": 0.25, "exposure": 0.30, "composition": 0.10}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _laplacian_stats(gray: Image.Image) -> tuple[float, float, int]:
    """(variance du laplacien, densité de contours, pixels analysés).

    Convolution 3x3 en Python pur sur l'échantillon : pas de numpy, pas de
    dépendance supplémentaire.
    """
    width, height = gray.size
    if width < 3 or height < 3:
        return 0.0, 0.0, 0
    # Mode "L" : 1 octet par pixel (pas de dépréciation Image.getdata).
    data = gray.tobytes()
    total = 0.0
    total_sq = 0.0
    edges = 0
    count = 0
    for y in range(1, height - 1):
        row = y * width
        up = row - width
        down = row + width
        for x in range(1, width - 1):
            i = row + x
            lap = 4.0 * data[i] - data[up + x] - data[down + x] - data[i - 1] - data[i + 1]
            total += lap
            total_sq += lap * lap
            if abs(lap) >= _EDGE_THRESHOLD:
                edges += 1
            count += 1
    if count == 0:
        return 0.0, 0.0, 0
    mean = total / count
    variance = max(0.0, total_sq / count - mean * mean)
    return variance, edges / count, count


def _exposure_score(gray: Image.Image) -> tuple[float, float]:
    histogram = gray.histogram()
    total = sum(histogram) or 1
    mean = sum(i * n for i, n in enumerate(histogram)) / total
    under = sum(histogram[:8]) / total
    over = sum(histogram[248:]) / total
    centered = 1.0 - abs(mean / 255.0 - 0.5) * 2.0
    score = _clamp01(centered - 2.0 * (under + over))
    return score, mean


def _composition_score(width: int, height: int) -> float:
    if not width or not height:
        return 0.0
    ratio = width / height
    distance = min(abs(ratio - std) / std for std in _STANDARD_RATIOS)
    # 5 % d'écart = format standard (score plein) ; au-delà, décroissance linéaire.
    if distance <= 0.05:
        return 1.0
    return _clamp01(1.0 - (distance - 0.05) * 2.0)


def assess_quality(image_path: Path) -> dict:
    """Calcule le score de qualité de ``image_path``. Lève en cas d'erreur."""
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source)
        if image.mode != "L":
            image = image.convert("L")
        if max(image.size) > _SAMPLE_MAX:
            image = image.copy()
            image.thumbnail((_SAMPLE_MAX, _SAMPLE_MAX), Image.Resampling.BILINEAR)

        lap_variance, edge_density, samples = _laplacian_stats(image)
        exposure, mean_luminance = _exposure_score(image)

    sharpness = _clamp01(lap_variance / (lap_variance + _SHARPNESS_HALF))
    blur = _clamp01(edge_density / _EDGE_TARGET)
    composition = _composition_score(image.width, image.height)
    overall = sum(_WEIGHTS[key] * value for key, value in (
        ("sharpness", sharpness),
        ("blur", blur),
        ("exposure", exposure),
        ("composition", composition),
    ))

    return {
        "overall": round(overall, 3),
        "sharpness": round(sharpness, 3),
        "blur": round(blur, 3),
        "exposure": round(exposure, 3),
        "composition": round(composition, 3),
        # Diagnostics (non pondérés).
        "mean_luminance": round(mean_luminance, 1),
        "laplacian_variance": round(lap_variance, 1),
        "edge_density": round(edge_density, 4),
        "sampled_pixels": samples,
    }
