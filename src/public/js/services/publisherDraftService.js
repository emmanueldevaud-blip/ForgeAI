/**
 * PublisherDraftService — Service unifié pour la gestion des brouillons
 * Abstraction sur SportPublication (post/reel) et StoryDraft
 */

import { publisherStore } from '../stores/publisherStore.js';
import {
  // Studio V2 (post/reel)
  createStudioDraftFromCalendar,
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
} from '../services/sportApi.js?v=16';
import {
  createStudioRender,
  getStudioRenderJob,
  cancelStudioRender,
} from '../services/photosApi.js?v=8';

export class PublisherDraftService {
  constructor() {
    this.currentDraftType = null; // 'studio' | 'story'
    this.currentDraftId = null;
    this.currentFormatOverride = null;
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
      publisherStore.resetDraft('story', calendarEntryId);
      return await this.loadStory(res.id);
    } catch (error) {
      throw new Error(error?.data?.detail || error?.message || 'Erreur création Story');
    }
  }

  /**
   * Crée un brouillon vierge (sans entrée calendrier)
   */
  async createBlank(format = 'post') {
    // Pour l'instant, on crée via une entrée calendrier "manuelle" ou on utilise un brouillon local uniquement
    publisherStore.resetDraft(format);
    this.currentDraftType = format === 'story' ? 'story' : 'studio';
    this.currentDraftId = null;
    this.currentFormatOverride = null;
    return publisherStore.getState().draft;
  }

  // ========== Chargement ==========

  async load(draftId, formatOverride = null) {
    if (this.currentDraftId !== draftId) this.currentFormatOverride = null;
    if (['post', 'carousel', 'reel', 'story'].includes(formatOverride)) {
      this.currentFormatOverride = formatOverride;
    }
    this.currentDraftType = 'studio';
    this.currentDraftId = draftId;
    const pub = await getStudioDraft(draftId);
    this._syncStoreFromStudio(pub, this.currentFormatOverride);
    return publisherStore.getState().draft;
  }

  async loadStory(draftId) {
    this.currentDraftType = 'story';
    this.currentDraftId = draftId;
    this.currentFormatOverride = null;
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

  async save(data) {
    if (!this.currentDraftId) throw new Error('Aucun brouillon chargé');

    const updates = {};
    if (data.caption) {
      updates.title = data.caption.title;
      updates.content = data.caption.content;
      updates.hashtags = data.caption.hashtags;
    }
    if (data.media) {
      updates.photo_ids = data.media.map(m => parseInt(m.id.replace('photo_', ''))).filter(id => !isNaN(id));
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
    if (!this.currentDraftId) throw new Error('Aucun brouillon');

    if (this.currentDraftType === 'story') {
      const res = await publishStoryDraftApi(this.currentDraftId, { confirm: true, platforms });
      return this.loadStory(this.currentDraftId);
    } else {
      let fn = publishStudioDraft;
      if (platforms.includes('facebook') && platforms.includes('instagram')) fn = publishStudioDraftBoth;
      else if (platforms.includes('facebook')) fn = publishStudioDraftFacebook;
      await fn(this.currentDraftId, { confirm: true });
      return this.load(this.currentDraftId);
    }
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
