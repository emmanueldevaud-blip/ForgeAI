/**
 * PublisherDraftService — Service unifié pour la gestion des brouillons
 * Abstraction sur SportPublication (post/reel) et StoryDraft
 */

import { publisherStore } from '../stores/publisherStore.js';
import {
  // Studio V2 (post/reel)
  createStudioDraftFromCalendar,
  createStudioDraft,
  getStudioDraft,
  updateStudioDraft,
  validateStudioDraft,
  publishStudioDraft,
  publishStudioDraftFacebook,
  publishStudioDraftBoth,
  previewStudioDraft,
  getSuggestedPhotos,
  generateStudioDraftVariants,
  generateStudioDraftText,
  lockStudioDraftTitle,
  lockStudioDraftContent,
  lockStudioDraftPhoto,
  // Story Studio
  createStoryDraft,
  getStoryDraft,
  updateStoryDraft,
  updateStorySlideDesign,
  renderStorySlide,
  validateStoryDraft as validateStoryDraftApi,
  publishStoryDraft as publishStoryDraftApi,
  listStoryDrafts,
  // Calendar
  getMonthCalendar,
  getWeekCalendar,
  getPublishJobStatus as getPublishJobStatusApi,
} from '../services/sportApi.js?v=20';
import {
  createStudioRender,
  getStudioRenderJob,
  cancelStudioRender,
  uploadPhotos,
  photoFileUrl,
} from '../services/photosApi.js?v=8';
import { publishStoryWithPipeline } from '../services/storyPublishPipeline.js';

/** Détail lisible d'une erreur API (champ `detail` FastAPI, message, etc.). */
function apiErrorDetail(error) {
  const detail = error?.data?.detail ?? error?.detail ?? error?.message
    ?? String(error ?? 'Erreur inconnue');
  if (Array.isArray(detail)) {
    return detail.map(d => `${d?.loc ? `${d.loc.join('.')}: ` : ''}${d?.msg || ''}`.trim()).join(' | ');
  }
  return String(detail);
}

export class PublisherDraftService {
  constructor() {
    this.currentDraftType = null; // 'studio' | 'story'
    this.currentDraftId = null;
    this.currentFormatOverride = null;
    // A01 : dernière cause d'échec de création serveur. L'UI doit l'afficher
    // et ne pas annoncer une sauvegarde réussie tant qu'elle est positionnée.
    this.serverDraftError = null;
  }

  _recordServerDraftError(error) {
    this.serverDraftError = {
      status: error?.status ?? null,
      detail: apiErrorDetail(error),
    };
    console.warn('[PublisherDraftService] Brouillon serveur différé :', this.serverDraftError.detail);
    return this.serverDraftError;
  }

  // ========== Création ==========

  /**
   * Crée un brouillon pour une publication/post/reel depuis le calendrier
   */
  async createFromCalendar({ calendarEntryId, format = 'post', styles = ['stats'], visualType = 'photo' }) {
    try {
      const res = await createStudioDraftFromCalendar({
        calendar_entry_id: calendarEntryId,
        styles,
        visual_type: visualType,
      });
      if (!res?.publication_id) throw new Error(res?.detail || 'Création impossible');
      this.currentDraftType = 'studio';
      this.currentDraftId = res.publication_id;
      this.currentFormatOverride = format;
      this.serverDraftError = null;
      // Sync avec le store local (post | carousel | reel | story)
      publisherStore.resetDraft(format, calendarEntryId);
      return await this.load(res.publication_id);
    } catch (error) {
      throw new Error(error?.data?.detail || error?.message || 'Erreur création brouillon');
    }
  }

  /**
   * Crée un brouillon Story depuis une activité Garmin + photos
   */
  async createStoryFromGarmin({ activityId, photoIds, calendarEntryId = null }) {
    try {
      const res = await createStoryDraft({
        activity_id: activityId,
        photo_ids: photoIds,
        calendar_entry_id: calendarEntryId,
      });
      if (!res?.id) throw new Error(res?.detail || 'Création Story impossible');
      this.currentDraftType = 'story';
      this.currentDraftId = res.id;
      this.currentFormatOverride = null;
      this.serverDraftError = null;
      publisherStore.resetDraft('story', calendarEntryId);
      return await this.loadStory(res.id);
    } catch (error) {
      throw new Error(error?.data?.detail || error?.message || 'Erreur création Story');
    }
  }

  /**
   * Crée un brouillon Story standalone depuis une composition du Composer.
   * Contrairement au parcours Garmin, les slides et designs v2 sont déjà
   * produits localement : le serveur n'a qu'à les enregistrer.
   */
  async createStandaloneStoryDraft() {
    const draft = publisherStore.draft || {};
    const design = draft.design || {};
    const photoIds = (Array.isArray(draft.media) ? draft.media : [])
      .map((media) => Number(media?.photoId ?? media?.id))
      .filter((id) => Number.isFinite(id) && id > 0);
    try {
      const created = await createStoryDraft({
        activity_id: null,
        source: 'manual',
        photo_ids: photoIds,
        slides: design.slides || [],
        design_documents: design.designDocuments || [],
        caption: draft.caption?.content || '',
        hashtags: draft.caption?.hashtags || '',
      });
      if (!created?.id) throw new Error(created?.detail || 'Création Story impossible');
      this.serverDraftError = null;
      this.currentDraftType = 'story';
      this.currentDraftId = created.id;
      this.currentFormatOverride = null;
      publisherStore.draft = { ...publisherStore.draft, id: created.id };
      publisherStore._notify?.();
      return created;
    } catch (error) {
      throw new Error(this._recordServerDraftError(error).detail);
    }
  }

  /**
   * Crée un brouillon standalone (sans entrée de calendrier).
   * Lot 0 (A01) : le brouillon est créé côté serveur ; le store local reste
   * la source de contenu tant que le brouillon serveur n'existe pas.
   */
  async createStandaloneDraft(format = 'post') {
    const visualType = format === 'reel' ? 'reel' : format === 'carousel' ? 'carousel' : 'photo';
    let created;
    try {
      created = await createStudioDraft({ visual_type: visualType });
    } catch (error) {
      throw new Error(this._recordServerDraftError(error).detail);
    }
    if (!created?.id) {
      const error = new Error(created?.detail || 'Création du brouillon impossible');
      error.data = created;
      throw new Error(this._recordServerDraftError(error).detail);
    }
    this.serverDraftError = null;
    this.currentDraftType = 'studio';
    this.currentDraftId = created.id;
    this.currentFormatOverride = format;
    // Ne pas recharger le brouillon vide depuis le serveur : le contenu local
    // déjà saisi doit être conservé jusqu'au premier save() (Lot 0 A01).
    publisherStore.draft = { ...publisherStore.draft, id: created.id };
    publisherStore._notify();
    return publisherStore.getState().draft;
  }

  /**
   * Crée un brouillon vierge (sans entrée calendrier).
   * Lot 0 (A01) : création serveur du brouillon standalone pour les formats
   * Studio (post/carousel/reel) — le draft local est ensuite sauvegardé dessus.
   * (Une Story standalone nécessite une activité source : non gérée à ce lot.)
   */
  async createBlank(format = 'post') {
    // Brouillon local conservé en attendant : la création serveur est tentée à
    // la volée (et retentée au premier save/publish si elle échoue ici).
    publisherStore.resetDraft(format);
    this.currentDraftType = format === 'story' ? 'story' : 'studio';
    this.currentDraftId = null;
    this.currentFormatOverride = null;
    if (this.currentDraftType === 'story') {
      return publisherStore.getState().draft;
    }
    try {
      return await this.createStandaloneDraft(format);
    } catch {
      // A01 : on conserve le brouillon local si la création serveur échoue
      // (réseau, 422 stratégie absente) — save()/publish() la retenteront.
      // `serverDraftError` porte la cause et doit être affichée par l'UI.
      return publisherStore.getState().draft;
    }
  }

  // ========== Chargement ==========

  async load(draftId, formatOverride = null) {
    if (this.currentDraftId !== draftId) this.currentFormatOverride = null;
    if (['post', 'carousel', 'reel', 'story'].includes(formatOverride)) {
      this.currentFormatOverride = formatOverride;
    }
    this.currentDraftType = 'studio';
    this.currentDraftId = draftId;
    this.serverDraftError = null;
    const pub = await getStudioDraft(draftId);
    this._syncStoreFromStudio(pub, this.currentFormatOverride);
    return publisherStore.getState().draft;
  }

  async loadStory(draftId) {
    this.currentDraftType = 'story';
    this.currentDraftId = draftId;
    this.currentFormatOverride = null;
    this.serverDraftError = null;
    const draft = await getStoryDraft(draftId);
    this._syncStoreFromStory(draft);
    return publisherStore.getState().draft;
  }

  // ========== Synchronisation Store ↔ API ==========

  _syncStoreFromStudio(pub, formatOverride = null) {
    const design = pub?.design || {};
    const media = [];
    if (design.carousel && design.carousel.length) {
      design.carousel.forEach((id, i) => media.push({
        id: `photo_${id}`,
        photoId: id,
        url: `/photos/${id}/file`,
        thumbnail_url: `/photos/${id}/file?size=small`,
        crop: { x: 0, y: 0, w: 1, h: 1 },
        order: i,
        type: 'photo',
        source: 'library',
      }));
    } else if (pub?.photo_id) {
      media.push({
        id: `photo_${pub.photo_id}`,
        photoId: pub.photo_id,
        url: `/photos/${pub.photo_id}/file`,
        thumbnail_url: `/photos/${pub.photo_id}/file?size=small`,
        crop: { x: 0, y: 0, w: 1, h: 1 },
        order: 0,
        type: 'photo',
        source: 'library',
      });
    }

    const detectedFormat = pub.content_type === 'reel' || pub.visual_type === 'reel'
      ? 'reel'
      : (pub.visual_type === 'story'
        ? 'story'
        : (pub.visual_type === 'carousel' ? 'carousel' : 'post'));

    publisherStore.draft = {
      ...publisherStore.draft,
      id: pub.id,
      format: ['post', 'carousel', 'reel', 'story'].includes(formatOverride)
        ? formatOverride
        : detectedFormat,
      media,
      design: design,
      caption: {
        title: pub.title || '',
        content: pub.content || '',
        hashtags: pub.hashtags || '',
        accountId: null,
      },
      status: pub.status,
      sourceEntryId: pub.calendar_entry_id,
      createdAt: pub.created_at ? new Date(pub.created_at).getTime() : null,
      updatedAt: pub.updated_at ? new Date(pub.updated_at).getTime() : null,
    };
    publisherStore._notify();
  }

  _syncStoreFromStory(draft) {
    const media = [];
    (draft.selected_asset_ids || []).forEach((id, i) => {
      media.push({
        id: `photo_${id}`,
        photoId: id,
        url: `/photos/${id}/file`,
        thumbnail_url: `/photos/${id}/file?size=small`,
        crop: { x: 0, y: 0, w: 1, h: 1 },
        order: i,
        type: 'photo',
        source: 'library',
      });
    });

    publisherStore.draft = {
      ...publisherStore.draft,
      id: draft.id,
      format: 'story',
      media,
      design: {
        slides: draft.slides || [],
        designDocuments: draft.design_documents || [],
      },
      caption: {
        title: '',
        content: draft.caption || '',
        hashtags: draft.hashtags || '',
        accountId: null,
      },
      music: draft.audio_configuration || {},
      status: draft.status,
      sourceEntryId: draft.calendar_entry_id,
      createdAt: draft.created_at ? new Date(draft.created_at).getTime() : null,
      updatedAt: draft.updated_at ? new Date(draft.updated_at).getTime() : null,
    };
    publisherStore._notify();
  }

  // ========== Sauvegarde ==========

  /**
   * Résout l'identifiant serveur d'un média pour la sauvegarde.
   * Lot 0 (A14) : un `photoId` numérique explicite est conservé ; à défaut, on
   * extrait l'entier du préfixe `photo_` de l'id d'affichage. Un média sans ID
   * serveur numérique est signalé (erreur visible) plutôt que filtré silencieusement.
   */
  _resolveServerPhotoId(media) {
    const explicit = media?.photoId;
    if (explicit !== undefined && explicit !== null && explicit !== '') {
      const raw = String(explicit).trim();
      if (/^\d+$/.test(raw) && Number(raw) > 0) return Number(raw);
    }
    const raw = String(media?.id ?? '').replace(/^photo_/, '').trim();
    if (/^\d+$/.test(raw) && Number(raw) > 0) return Number(raw);
    return null;
  }

  async save(data) {
    let serverDraftReady = true;
    if (!this.currentDraftId) {
      // Lot 0 (A01) : création serveur du brouillon standalone à la volée au premier save.
      if (this.currentDraftType === 'story') throw new Error('Aucun brouillon');
      try {
        await this.createStandaloneDraft(this.currentFormatOverride || 'post');
      } catch {
        // A01 : garder la saisie locale et ne pas simuler une sauvegarde serveur.
        serverDraftReady = false;
      }
    }

    if (!serverDraftReady) {
      publisherStore.draft.updatedAt = Date.now();
      publisherStore._notify();
      return publisherStore.getState().draft;
    }

    const updates = {};
    if (data.caption) {
      updates.title = data.caption.title;
      updates.content = data.caption.content;
      updates.hashtags = data.caption.hashtags;
    }
    if (data.media) {
      const resolvedIds = data.media.map(m => this._resolveServerPhotoId(m));
      const missing = data.media.filter((m, i) => resolvedIds[i] === null);
      if (missing.length > 0) {
        throw new Error(
          `Média sans identifiant serveur : ${missing.map(m => String(m.id ?? m.photoId ?? 'inconnu')).join(', ')}. Sélectionnez une photo de la bibliothèque.`,
        );
      }
      updates.photo_ids = resolvedIds;
    }
    if (data.design) updates.design = data.design;
    if (data.music && this.currentDraftType === 'story') {
      updates.audio_configuration = data.music;
    }
    if (data.photoId !== undefined && data.photoId !== null) {
      updates.photo_id = Number(data.photoId);
    }
    if (data.visualType) updates.visual_type = data.visualType;

    if (this.currentDraftType === 'story') {
      await updateStoryDraft(this.currentDraftId, updates);
      return this.loadStory(this.currentDraftId);
    } else {
      await updateStudioDraft(this.currentDraftId, updates);
      return this.load(this.currentDraftId);
    }
  }

  async saveStorySlide(slideIndex, design) {
    if (this.currentDraftType !== 'story') throw new Error('Pas un brouillon Story');
    await updateStorySlideDesign(this.currentDraftId, slideIndex, design);
    return this.loadStory(this.currentDraftId);
  }

  // ========== IA ==========

  async generateVariants({ tone, styles, customInstructions, count = 3 }) {
    if (!this.currentDraftId || this.currentDraftType !== 'studio') throw new Error('Brouillon Studio requis');
    return generateStudioDraftVariants(this.currentDraftId, { tone, styles, custom_instructions: customInstructions, count });
  }

  /**
   * Génère un texte (court ou long) selon le ton.
   * Endpoint réel : POST /community-manager/studio/draft/{id}/generate-text
   * @param {{tone?:string, length?:'short'|'long', customInstructions?:string}} options
   */
  async generateText({ tone, length = 'short', customInstructions } = {}) {
    if (!this.currentDraftId || this.currentDraftType !== 'studio') throw new Error('Brouillon Studio requis');
    return generateStudioDraftText(this.currentDraftId, {
      publication_id: Number(this.currentDraftId),
      length: length === 'long' ? 'long' : 'short',
      tone: tone || undefined,
      custom_instructions: customInstructions || undefined,
    });
  }

  // ========== Verrous ==========

  async lockTitle(locked) {
    if (!this.currentDraftId || this.currentDraftType !== 'studio') return;
    await lockStudioDraftTitle(this.currentDraftId, locked);
    return this.load(this.currentDraftId);
  }

  async lockContent(locked) {
    if (!this.currentDraftId || this.currentDraftType !== 'studio') return;
    await lockStudioDraftContent(this.currentDraftId, locked);
    return this.load(this.currentDraftId);
  }

  async lockPhoto(locked) {
    if (!this.currentDraftId || this.currentDraftType !== 'studio') return;
    await lockStudioDraftPhoto(this.currentDraftId, locked);
    return this.load(this.currentDraftId);
  }

  // ========== Photos suggérées ==========

  async getSuggestedPhotos(limit = 20) {
    if (!this.currentDraftId || this.currentDraftType !== 'studio') return [];
    return getSuggestedPhotos(this.currentDraftId, limit);
  }

  // ========== Rendu ==========

  async renderStorySlide(slideIndex) {
    if (this.currentDraftType !== 'story') throw new Error('Pas un brouillon Story');
    return renderStorySlide(this.currentDraftId, slideIndex);
  }

  async getStoryRenderJobs() {
    if (this.currentDraftType !== 'story') return { render_jobs: [] };
    const res = await getStoryDraft(this.currentDraftId);
    return { render_jobs: res.render_jobs || [] };
  }

  // ========== Rendu Studio (Post/Reel) ==========

  async createRender(publicationId) {
    if (this.currentDraftType !== 'studio') throw new Error('Brouillon Studio requis');
    return createStudioRender(publicationId);
  }

  async getRenderJob(jobId) {
    return getStudioRenderJob(jobId);
  }

  async cancelRender(jobId) {
    return cancelStudioRender(jobId);
  }

  // ========== Validation ==========

  async validate() {
    if (!this.currentDraftId) throw new Error('Aucun brouillon');
    if (this.currentDraftType === 'story') {
      await validateStoryDraftApi(this.currentDraftId, { status: 'awaiting_validation' });
      return this.loadStory(this.currentDraftId);
    } else {
      await validateStudioDraft(this.currentDraftId, { confirm: true });
      return this.load(this.currentDraftId);
    }
  }

  // ========== Publication ==========

  async publish({ platforms = ['instagram'] } = {}) {
    // Lot 1 / A05 : le carrousel est sélectionnable mais Meta ne recevrait qu'une
    // seule photo. Bloquer avant toute sauvegarde/enfilement, avec un message clair.
    const draftFormat = publisherStore.draft?.format || this.currentFormatOverride;
    if (this.currentFormatOverride === 'carousel' || draftFormat === 'carousel') {
      throw new Error(
        'Le format carrousel ne peut pas encore être publié : Meta recevrait une seule photo. '
        + 'Choisissez une photo unique.',
      );
    }

    if (!this.currentDraftId) {
      // Lot 0 (A01) : un brouillon standalone sans ID serveur est créé à la
      // volée avant publication, puis le contenu local est persisté dessus.
      if (this.currentDraftType === 'story') {
        // Story standalone : le Composer a déjà composé les slides, on crée
        // le StoryDraft serveur correspondant avant de lancer le pipeline.
        try {
          await this.createStandaloneStoryDraft();
        } catch {
          throw new Error(`Publication impossible : ${apiErrorDetail(this.serverDraftError)}. Le brouillon reste local.`);
        }
      } else {
        try {
          await this.createStandaloneDraft(this.currentFormatOverride || 'post');
        } catch {
          // A01 : pas de publication réelle si le brouillon serveur n'existe pas.
          throw new Error(`Publication impossible : ${apiErrorDetail(this.serverDraftError)}. Le brouillon reste local.`);
        }
        const draft = publisherStore.draft;
        await this.save({
          caption: draft.caption,
          media: draft.media,
          design: draft.design,
          music: draft.music,
        });
      }
    }

    if (this.currentDraftType === 'story') {
      // Lot 1 / A06 : une seule vérité, la publication Story est Instagram uniquement.
      if (platforms.some((platform) => platform !== 'instagram')) {
        throw new Error('La publication Story est disponible sur Instagram uniquement.');
      }
      // Même pipeline que le bouton « Valider et publier » de l'éditeur Story :
      // les slides sont exportées/uploadées avant validation et publication.
      const storyDesign = publisherStore.draft.design || {};
      const result = await publishStoryWithPipeline({
        draftId: this.currentDraftId,
        slides: storyDesign.slides || [],
        designDocuments: storyDesign.designDocuments || [],
        deps: { uploadPhotos, photoFileUrl },
        draftData: {
          caption: publisherStore.draft.caption?.content || '',
          hashtags: publisherStore.draft.caption?.hashtags || '',
          audio_configuration: publisherStore.draft.music || {},
        },
        api: {
          save: (payload) => updateStoryDraft(this.currentDraftId, payload),
          validate: (draftId) => validateStoryDraftApi(draftId, { status: 'awaiting_validation' }),
          publish: (draftId, data) => publishStoryDraftApi(draftId, data),
        },
        platforms,
      });
      return { ...(result || {}), draft: await this.loadStory(this.currentDraftId) };
    } else {
      let fn = publishStudioDraft;
      if (platforms.includes('facebook') && platforms.includes('instagram')) fn = publishStudioDraftBoth;
      else if (platforms.includes('facebook')) fn = publishStudioDraftFacebook;
      const result = await fn(this.currentDraftId, { confirm: true });
      return { ...(result || {}), draft: await this.load(this.currentDraftId) };
    }
  }

  /** Interroge le vrai résultat d'un job de publication (souvent asynchrone). */
  async getPublishJobStatus(jobId) {
    return getPublishJobStatusApi(jobId);
  }

  /**
   * Attend un état terminal (ou un délai maximum) sur les jobs enfilemés par
   * publish(). Le POST ne dit que « queued » : sans ce polling l'UI annonce
   * une publication réussie même quand Meta a refusé la demande.
   */
  async waitForPublishJobs(jobIds, options = {}) {
    const ids = [...new Set((Array.isArray(jobIds) ? jobIds : []).filter(Boolean))];
    if (!ids.length) return { status: 'queued', jobs: [] };

    const attempts = Math.max(1, Number(options.attempts) || 10);
    const delayMs = Math.max(0, Number(options.delayMs) || 1200);
    const sleep = options.sleep
      || ((ms) => new Promise((resolve) => globalThis.setTimeout(resolve, ms)));
    const terminal = new Set(['done', 'failed', 'cancelled', 'error']);
    let jobs = [];

    for (let attempt = 0; attempt < attempts; attempt += 1) {
      jobs = await Promise.all(ids.map(async (jobId) => {
        try {
          return await this.getPublishJobStatus(jobId);
        } catch (error) {
          return { job_id: jobId, status: 'error', error_message: error?.message || 'Statut indisponible' };
        }
      }));
      if (jobs.every((job) => terminal.has(job?.status))) break;
      if (attempt < attempts - 1) await sleep(delayMs);
    }

    const failed = jobs.find((job) => ['failed', 'cancelled', 'error'].includes(job?.status));
    if (failed) {
      return {
        status: 'failed',
        jobs,
        error: failed.error_message || failed.error || 'Publication impossible',
        media: failed.instagram_media_id || null,
      };
    }
    const published = jobs.length > 0 && jobs.every((job) => job?.status === 'done');
    return {
      status: published ? 'published' : 'queued',
      jobs,
      media: jobs.find((job) => job?.instagram_media_id)?.instagram_media_id || null,
    };
  }

  // ========== Aperçu ==========

  async preview(format = 'feed') {
    if (!this.currentDraftId || this.currentDraftType !== 'studio') throw new Error('Brouillon Studio requis');
    return previewStudioDraft(this.currentDraftId, format);
  }

  // ========== Calendrier ==========

  async getCalendarMonth(year, month) {
    return getMonthCalendar(year, month);
  }

  async getCalendarWeek(monday) {
    return getWeekCalendar(monday);
  }

  // ========== Utilitaires ==========

  getCurrentDraft() {
    return { type: this.currentDraftType, id: this.currentDraftId };
  }

  clearCurrent() {
    this.currentDraftType = null;
    this.currentDraftId = null;
    this.currentFormatOverride = null;
  }
}

export const publisherDraftService = new PublisherDraftService();
