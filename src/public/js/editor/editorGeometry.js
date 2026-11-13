/**
 * Géométrie de l'éditeur graphique — fonctions pures (aucun DOM).
 *
 * Convention de coordonnées : pour tous les éléments, x/y désignent le
 * CENTRE de l'élément dans l'espace design ; w/h sont la taille non
 * rotée ; rotation en degrés (sens horaire).
 */

export const DEG = Math.PI / 180;

export function rotatePoint(px, py, cx, cy, angleDeg) {
  const a = angleDeg * DEG;
  const cos = Math.cos(a);
  const sin = Math.sin(a);
  const dx = px - cx;
  const dy = py - cy;
  return { x: cx + dx * cos - dy * sin, y: cy + dx * sin + dy * cos };
}

/** Point global -> coordonnées locales de l'élément (origine au centre). */
export function toLocal(px, py, el) {
  const p = rotatePoint(px, py, el.x, el.y, -(el.rotation || 0));
  return { x: p.x - el.x, y: p.y - el.y };
}

/** Coordonnées locales (origine au centre) -> point global. */
export function toGlobal(lx, ly, el) {
  const p = rotatePoint(lx, ly, 0, 0, el.rotation || 0);
  return { x: el.x + p.x, y: el.y + p.y };
}

export function elementCenter(el) {
  return { x: el.x, y: el.y };
}

/**
 * Test de collision point/élément (AABB dans le repère local).
 * textHeight : hauteur dynamique optionnelle (texte enveloppé).
 */
export function hitTest(px, py, el, textHeight) {
  const local = toLocal(px, py, el);
  const h = textHeight || el.h;
  return (
    local.x >= -el.w / 2 &&
    local.x <= el.w / 2 &&
    local.y >= -h / 2 &&
    local.y <= h / 2
  );
}

export const HANDLES = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];

/** Position globale du centre d'une poignée de l'élément. */
export function handlePoint(el, handle, textHeight) {
  const h = textHeight || el.h;
  const hw = el.w / 2;
  const hh = h / 2;
  const map = {
    nw: [-hw, -hh],
    n: [0, -hh],
    ne: [hw, -hh],
    e: [hw, 0],
    se: [hw, hh],
    s: [0, hh],
    sw: [-hw, hh],
    w: [-hw, 0],
  };
  const [lx, ly] = map[handle];
  return toGlobal(lx, ly, el);
}

/**
 * Position globale de la poignée de rotation (tige au-dessus du côté haut).
 */
export function rotateHandlePoint(el, textHeight) {
  const h = textHeight || el.h;
  return toGlobal(0, -h / 2 - Math.max(18, el.w * 0.08), el);
}

/** Résout un redimensionnement. Retourne le nouvel état {x,y,w,h} (centre). */
export function solveResize(el, handle, px, py, opts = {}) {
  const local = toLocal(px, py, el);
  const min = opts.minSize || 24;
  let w = el.w;
  let h = opts.textHeight || el.h;

  const anchorLocal = {
    // coin ou côté opposé qui reste fixe, en coordonnées locales (ancien repère)
    nw: [el.w / 2, el.h / 2],
    n: [0, el.h / 2],
    ne: [-el.w / 2, el.h / 2],
    e: [-el.w / 2, 0],
    se: [-el.w / 2, -el.h / 2],
    s: [0, -el.h / 2],
    sw: [el.w / 2, -el.h / 2],
    w: [el.w / 2, 0],
  }[handle];

  const dirX = handle.includes('w') ? -1 : handle.includes('e') ? 1 : 0;
  const dirY = handle.includes('n') ? -1 : handle.includes('s') ? 1 : 0;

  if (dirX !== 0) {
    w = dirX > 0 ? local.x + el.w / 2 : el.w / 2 - local.x;
  }
  if (dirY !== 0 && !opts.keepHeight) {
    h = dirY > 0 ? local.y + h / 2 : h / 2 - local.y;
  }

  // Proportion contrainte (images par défaut)
  if (opts.aspect) {
    const ratio = (opts.textHeight || el.h) / el.w;
    if (dirX !== 0 && dirY === 0) h = w * ratio;
    else if (dirY !== 0 && dirX === 0) w = h / ratio;
    else if (dirX !== 0 && dirY !== 0) {
      // coins : garder le ratio de l'élément d'origine
      if (w / h > 1 / ratio) h = w * ratio;
      else w = h / ratio;
    }
  }

  w = Math.max(min, w);
  h = Math.max(min, h);

  // L'ancre doit rester fixe : centre' = ancre_global + R(theta)·(nouvel écart)
  const anchorGlobal = toGlobal(anchorLocal[0], anchorLocal[1], el);
  const newHalfW = w / 2;
  const newHalfH = h / 2;
  const oppositeLocal = {
    nw: [newHalfW, newHalfH],
    n: [0, newHalfH],
    ne: [-newHalfW, newHalfH],
    e: [-newHalfW, 0],
    se: [-newHalfW, -newHalfH],
    s: [0, -newHalfH],
    sw: [newHalfW, -newHalfH],
    w: [newHalfW, 0],
  }[handle];
  // center + R·(oppositeLocal) = anchorGlobal → center = anchor - R·(oppositeLocal)
  const rot = el.rotation || 0;
  const rotOpposite = rotatePoint(oppositeLocal[0], oppositeLocal[1], 0, 0, rot);
  const center = {
    x: anchorGlobal.x - rotOpposite.x,
    y: anchorGlobal.y - rotOpposite.y,
  };

  return { x: center.x, y: center.y, w, h };
}

/** Angle global depuis le centre d'un élément vers un point. */
export function angleToPoint(el, px, py) {
  return Math.atan2(py - el.y, px - el.x) / DEG;
}

export function clampRotation(deg, snap = 0) {
  let r = ((deg % 360) + 360) % 360;
  if (snap > 0) r = Math.round(r / snap) * snap;
  return ((r % 360) + 360) % 360;
}

/** Bornes d'un crop (ratios 0..1) avec taille minimale. */
export function clampCrop(crop) {
  const min = 0.05;
  let { x = 0, y = 0, w = 1, h = 1 } = crop || {};
  x = Math.min(Math.max(0, x), 1 - min);
  y = Math.min(Math.max(0, y), 1 - min);
  w = Math.min(Math.max(min, w), 1 - x);
  h = Math.min(Math.max(min, h), 1 - y);
  return { x, y, w, h };
}

/**
 * Résout le redimensionnement d'un rectangle de crop (ratios 0..1) dans
 * l'espace local de l'image. `handle` parmi n/s/e/w/ne/nw/se/s/sw.
 */
export function solveCrop(crop, handle, lx, ly, localW, localH) {
  // lx/ly : point local dans le repère de l'élément (origine au centre)
  // Conversion en coordonnées 0..1 locales de l'image
  const u = lx / localW + 0.5;
  const v = ly / localH + 0.5;
  const c = clampCrop(crop);
  let { x, y, w, h } = c;
  const right = x + w;
  const bottom = y + h;
  const min = 0.05;

  if (handle.includes('w')) {
    const nx = Math.min(Math.max(0, u), x + w - min);
    w = right - nx;
    x = nx;
  }
  if (handle.includes('e')) {
    w = Math.min(Math.max(min, u), 1) - x;
  }
  if (handle.includes('n')) {
    const ny = Math.min(Math.max(0, v), y + h - min);
    h = bottom - ny;
    y = ny;
  }
  if (handle.includes('s')) {
    h = Math.min(Math.max(min, v), 1) - y;
  }
  if (handle === 'n' || handle === 's') {
    // purement vertical : inchangé côté x
  }

  return clampCrop({ x, y, w, h });
}

/**
 * Crop « cover » : cadre une image (iw×ih) dans un rect cible (cw×ch)
 * en remplissant, centré. Retourne un crop en ratios 0..1.
 */
export function coverCrop(iw, ih, cw, ch) {
  if (!iw || !ih || !cw || !ch) return { x: 0, y: 0, w: 1, h: 1 };
  const ratio = Math.max(cw / iw, ch / ih);
  const sw = Math.min(iw, cw / ratio);
  const sh = Math.min(ih, ch / ratio);
  return {
    x: (iw - sw) / 2 / iw,
    y: (ih - sh) / 2 / ih,
    w: sw / iw,
    h: sh / ih,
  };
}

/** Mise à l'échelle proportionnelle de tout un design lors d'un changement de format. */
export function scaleDesign(design, newW, newH) {
  const oldW = design.format.width;
  const oldH = design.format.height;
  if (oldW === newW && oldH === newH) return design;
  const ratio = Math.min(newW / oldW, newH / oldH);
  const dx = (newW - oldW * ratio) / 2;
  const dy = (newH - oldH * ratio) / 2;
  return {
    ...design,
    format: { ...design.format, width: newW, height: newH },
    elements: (design.elements || []).map((el) => ({
      ...el,
      x: el.x * ratio + dx,
      y: el.y * ratio + dy,
      w: el.w * ratio,
      h: el.h * ratio,
      size: el.size ? Math.round(el.size * ratio) : el.size,
    })),
  };
}
