/**
 * Pipeline de publication Story partagé entre le StoryEditorView et le
 * Composer/Publisher final.
 *
 * Étapes uniques : export JPEG de chaque slide -> upload -> published_photo_id
 * -> sauvegarde du brouillon -> validation -> publication.
 *
 * Le rendu utilise un EditorCanvas hors écran afin que l'étape « Publier » du
 * Composer puisse exporter les slides même lorsque l'éditeur graphique n'est
 * plus monté. Un appelant déjà monté (StoryEditorView) peut fournir son propre
 * `renderSlide` pour conserver son canvas.
 */

import { EditorState } from '../editor/editorState.js?v=2';
import { EditorCanvas } from '../editor/editorCanvas.js?v=2';

/** Identifiant de la photo de fond d'un design Story. */
export function storyPhotoId(design) {
  if (design?.background?.type === 'photo' && design.background.photo_id) {
    return design.background.photo_id;
  }
  return design?.carousel?.[0] || null;
}

/** Export JPEG d'un design Story via un canvas hors écran. */
export async function renderStorySlideDesign(design, deps = {}) {
  if (typeof deps.photoFileUrl !== 'function') {
    throw new Error("L'export des Stories n'est pas configuré.");
  }
  const state = new EditorState(design);
  const canvas = new EditorCanvas({ state });
  const photoId = storyPhotoId(design);
  if (photoId) {
    await canvas.setBackgroundImage(deps.photoFileUrl(photoId, 'original'), design.background?.crop || null);
  } else {
    await canvas.ensureImages();
  }
  return canvas.exportBlob('image/jpeg', 0.94);
}

/**
 * Exporte et téléverse chaque slide, puis renseigne `published_photo_id`.
 * @returns {{slides: Array, design_documents: Array}}
 */
export async function exportStorySlides({
  draftId,
  slides = [],
  designDocuments = [],
  deps = {},
  renderSlide = null,
} = {}) {
  if (!Array.isArray(designDocuments) || designDocuments.length === 0) {
    throw new Error('Aucune slide Story à exporter.');
  }
  if (typeof deps.uploadPhotos !== 'function') {
    throw new Error("L'export des Stories n'est pas configuré.");
  }

  const nextSlides = Array.isArray(slides) ? slides.map((slide) => ({ ...slide })) : [];
  const nextDesigns = designDocuments.map((design) => ({ ...design }));

  for (let index = 0; index < nextDesigns.length; index += 1) {
    const design = nextDesigns[index];
    const rendered = renderSlide
      ? await renderSlide(design, index)
      : await renderStorySlideDesign(design, deps);
    const blob = rendered?.blob || rendered;
    if (!blob) throw new Error(`Impossible d'exporter la Story ${index + 1}.`);
    // Un éditeur monté peut renvoyer le design exact qu'il a rendu.
    if (rendered?.design) nextDesigns[index] = rendered.design;

    const name = `story-${draftId || 'draft'}-${index + 1}.jpg`;
    const file = typeof File === 'function'
      ? new File([blob], name, { type: 'image/jpeg' })
      : { name, type: 'image/jpeg' };
    const result = await deps.uploadPhotos([file]);
    const items = Array.isArray(result?.items) ? result.items : result;
    const photo = items?.[0];
    if (!photo?.id) throw new Error(`Impossible d'enregistrer la Story ${index + 1}.`);

    nextSlides[index] = { ...(nextSlides[index] || {}), published_photo_id: photo.id };
  }

  return { slides: nextSlides, design_documents: nextDesigns };
}

/** Indique si toutes les slides sont déjà exportées (statut affiché dans le Publisher). */
export function storySlidesReady(design = {}) {
  const slides = Array.isArray(design?.slides) ? design.slides : [];
  const docs = Array.isArray(design?.designDocuments) ? design.designDocuments : [];
  return slides.length > 0
    && slides.length === docs.length
    && slides.every((slide) => !!slide?.published_photo_id);
}

/** Plateformes Story acceptées, avec dépliage de `both`. */
export function normalizeStoryPlatforms(values) {
  const platforms = [];
  for (const value of values || []) {
    const targets = value === 'both' ? ['instagram', 'facebook'] : [value];
    for (const platform of targets) {
      if (['instagram', 'facebook'].includes(platform) && !platforms.includes(platform)) {
        platforms.push(platform);
      }
    }
  }
  return platforms;
}

/**
 * Pipeline complet côté Composer final : export/upload, sauvegarde, validation,
 * publication. Les appels API sont injectés pour rester testable sans réseau.
 */
export async function publishStoryWithPipeline({
  draftId,
  slides,
  designDocuments,
  deps,
  api,
  renderSlide = null,
  platforms = ['instagram'],
  draftData = {},
} = {}) {
  // Refuser une cible inconnue avant même l'export des slides.
  const targets = normalizeStoryPlatforms(platforms);
  if (!targets.length) {
    throw new Error('Choisissez au moins une plateforme de publication Story.');
  }
  const prepared = await exportStorySlides({ draftId, slides, designDocuments, deps, renderSlide });
  const payload = {
    slides: prepared.slides,
    design_documents: prepared.design_documents,
  };
  if (draftData.caption !== undefined) payload.caption = draftData.caption;
  if (draftData.hashtags !== undefined) payload.hashtags = draftData.hashtags;
  // Lot 1 / A07 : la musique est une donnée de brouillon créatif. Elle n'est
  // jamais envoyée à l'API de publication (pas de paramètre Meta Story supporté).
  if (draftData.audio_configuration !== undefined) {
    payload.audio_configuration = draftData.audio_configuration;
  }

  await api.save(payload);
  await api.validate(draftId);
  return api.publish(draftId, { confirm: true, platforms: targets });
}
