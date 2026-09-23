"""Runtime language selection. English is the source language.

Translation keys are stable ASCII identifiers. Some of them double as stored
values: `Reading.reason` is compared in logic and `valuations.reason` is written
to SQLite, so a key must never change when the display language does.
"""
from __future__ import annotations

import json
from pathlib import Path

from .model import DATA

LANGUAGES = {'en': 'English', 'fr': 'Français'}
DEFAULT = 'en'

_current = DEFAULT


def settings_file(directory=None):
    return Path(directory or DATA) / 'settings.json'


def load_language(directory=None):
    """A missing or damaged settings file must not prevent the app from starting."""
    global _current
    try:
        stored = json.loads(settings_file(directory).read_text('utf-8')).get('language')
    except (OSError, ValueError, AttributeError):
        stored = None
    _current = stored if stored in LANGUAGES else DEFAULT
    return _current


def set_language(code, directory=None):
    global _current
    if code not in LANGUAGES:
        raise ValueError(f'Unknown language: {code}')
    _current = code
    file = settings_file(directory)
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if file.exists():
            try:
                data = json.loads(file.read_text('utf-8'))
            except ValueError:
                data = {}
        data['language'] = code
        temporary = file.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), 'utf-8')
        temporary.replace(file)
    except OSError:
        # A read-only data directory still allows the session to switch language.
        pass
    return code


def language():
    return _current


def language_name(code=None):
    return LANGUAGES.get(code or _current, LANGUAGES[DEFAULT])


def code_for_name(name):
    return next((code for code, label in LANGUAGES.items() if label == name), DEFAULT)


def t(key, **fields):
    """Translate a key; fall back to English, then to the key itself."""
    text = CATALOG.get(_current, {}).get(key)
    if text is None:
        text = CATALOG[DEFAULT].get(key, key)
    return text.format(**fields) if fields else text


CATALOG = {
'en': {
    # --- Reading reasons (also used as logic keys) -------------------------
    'reason.auto': 'Auto',
    'reason.empty': 'Empty cell',
    'reason.empty_confirmed': 'Confirmed empty',
    'reason.pending': 'Confirming…',
    'reason.local_ref': 'Local reference',
    'reason.unreadable_count': 'Unreadable count',
    'reason.variant': 'Variant to confirm',
    'reason.unknown_icon': 'Icon to confirm',
    'reason.hidden_icon': 'Icon hidden or different',
    'reason.manual': 'Manual correction',
    'reason.last_known': 'Last known state',
    'reason.to_check': 'To check',
    # --- Valuation events (stored in SQLite) -------------------------------
    'event.refresh': 'Refresh',
    'event.session_start': 'Session start',
    'event.session_end': 'Session end',
    # --- Stash layouts -----------------------------------------------------
    'layout.currency': 'Currencies',
    'layout.expedition': 'Expedition',
    'layout.runes': 'Runes',
    'layout.kalguuran': 'Kalguuran Runes',
    'layout.soul_cores': 'Soul Cores',
    'layout.idols': 'Idols',
    'layout.ancient_augments': 'Ancient Augments',
    'layout.unknown': 'Unrecognised type',
    'layout.auto': 'Automatic',
    # --- Window and header -------------------------------------------------
    'app.title': 'Exile Worth · PoE 2',
    'app.brand': 'EXILE WORTH',
    'app.tagline': '  /  Your stash, in value',
    'app.footer': 'Local reading • no input sent to the game • prices: poe.ninja',
    # --- Toolbar -----------------------------------------------------------
    'bar.league': 'League',
    'bar.load_prices': 'Load prices',
    'bar.language': 'Language',
    'bar.import': 'Import a screenshot',
    'bar.capture': 'Capture in 5 s',
    'bar.analyze': 'Analyse',
    'bar.export_csv': 'Export CSV',
    'bar.save_image': 'Save the image',
    'bar.start': 'Start',
    'bar.pause': 'Pause',
    # --- Capture state badge ----------------------------------------------
    'state.paused': '● Paused',
    'state.tracking': '● Tracking',
    'state.waiting': '● Waiting for the game',
    'state.preview': '● Live preview',
    'state.unstable': '● Image moving',
    'state.stopping': '● Stopping',
    'state.stopping_action': 'Stopping…',
    # --- Pages and tabs ----------------------------------------------------
    'page.stash': 'My stash',
    'page.detail': 'Detail & reading',
    'page.history': 'Value & history',
    'tab.detection': 'Automatic reading',
    'tab.inventory': 'Inventory',
    'tab.history': 'History',
    'tab.corrections': 'Corrections',
    # --- Dashboard ---------------------------------------------------------
    'dash.total_title': 'Estimate in divines',
    'dash.total_placeholder': 'The total appears once a screenshot is read.',
    'dash.cards_hint': 'Each tab keeps its last known inventory. Click a card to see its contents.',
    'dash.preview_card': 'Live preview',
    'dash.live_badge': '● Updating live',
    'dash.total_partial': ' · partial',
    'dash.preview_unidentified': '{layout} · tab not identified',
    'dash.preview_detail': 'Current screenshot · not added to the stash\n{unread} cells to check · {unpriced} unpriced',
    'dash.see_detail': 'See detail',
    'dash.never_synced': 'Never synchronised',
    'dash.last_read': 'Last read: {stamp}',
    'dash.partial': '\nPartial · {count} to check · {unpriced} unpriced',
    'dash.abbreviated': '\nAbbreviated quantities: estimate',
    'dash.tracked': 'Tracked stash · {tabs} tab(s) synchronised',
    'dash.tracked_detail': '{unread} cell(s) unread · {missing} unpriced · {uncertain} to check. Last known states.',
    'dash.displayed_title': 'Estimate for the displayed tab',
    'dash.displayed_detail': '{valued} cell(s) valued · {unread} to read · {missing} unpriced',
    'dash.preview_line': 'Displayed tab: {amount} (preview, not added to the total)',
    'dash.auto_add_hint': 'A tab is added automatically once its active title is readable.',
    'dash.abbreviated_suffix': ' · Abbreviated quantities: estimate',
    # --- Detail page -------------------------------------------------------
    'detail.default_title': 'Reading of the displayed stash',
    'detail.live_preview': 'Live preview',
    'detail.live_preview_of': 'Live preview · {layout}',
    'detail.live_preview_tab': 'Live preview · {name} · {layout}',
    'detail.canvas_empty': 'Open a stash tab\nthen import or capture the game.',
    'detail.canvas_no_image': 'Inventory kept.\nNo screenshot available for this tab.',
    'detail.recognition_placeholder': 'Names appear once the icons are identified.',
    'detail.recognition': '{identified}/{total} occupied cells identified · {ambiguous} variants to confirm. Provisional quantities wait for three readings before being saved.',
    'detail.recognition_none': 'No occupied cell recognised on this screenshot.',
    'col.cell': 'Cell',
    'col.item': 'Item',
    'col.quantity': 'Qty',
    'col.value': 'Value',
    'col.value_unit': 'Value ({unit})',
    'col.state': 'State',
    'col.tab': 'Tab',
    'col.last_read': 'Last read',
    'col.date': 'Date',
    'col.saved_cells': 'Saved cells',
    'item.unknown': 'Unrecognised item',
    'item.unknown_variant': '{name} · unknown variant',
    'reading.provisional': ' (provisional)',
    'reading.provisional_suffix': ' · provisional quantity',
    'reading.abbreviated_suffix': ' · abbreviated',
    'reading.last_confirmed_suffix': ' · last confirmed quantity',
    # --- Corrections -------------------------------------------------------
    'fix.slot_placeholder': 'Click a cell on the screenshot.',
    'fix.slot_selected': 'Selected: {name} — a correction is possible if the automatic reading is uncertain.',
    'fix.correct_icon': 'Correct the icon',
    'fix.learn_empty': 'Learn the empty cell',
    'fix.correct_quantity': 'Correct a quantity…',
    'fix.hint': 'Icons and white counters are read automatically. The corrections above are optional, for uncertain detections.',
    'fix.saved': '{slot}: {kind} reference saved.',
    'fix.kind_empty': 'empty',
    'fix.kind_icon': 'icon',
    'fix.need_preview': 'Open the live preview to correct a detection on the current screenshot.',
    'fix.need_preview_quantity': 'Open the live preview to correct the quantity on the current screenshot.',
    'fix.need_pause': 'Pause, then select a cell on a screenshot.',
    'fix.need_item': 'Load the prices, then choose a currency from the list.',
    'fix.need_tab': 'Analyse a screenshot with a recognised tab first, then select a cell.',
    'fix.dialog_title': 'Correction',
    'fix.dialog_prompt': 'Quantity checked visually:',
    # --- Status messages ---------------------------------------------------
    'status.intro': 'Import a screenshot or capture the game: icons and quantities are read automatically.',
    'status.busy': 'Pause the reading and wait for the operations to finish.',
    'status.loading_icons': 'Loading icons: {done}/{total}',
    'status.loading_prices': 'Loading…',
    'status.prices_not_loaded': 'Prices not loaded',
    'status.prices_received': 'Prices received on {stamp}',
    'status.prices_stale_suffix': ' · stale cache',
    'status.prices_unavailable': 'Prices unavailable — try again or use an existing cache',
    'status.prices_load_league': 'Load the prices for this league.',
    'status.prices_summary': 'Prices: {stamp}{age} · {missing} unpriced · {uncertain} to check',
    'status.prices_expired': ' · expired',
    'status.catalog_loaded': 'Catalogue loaded · {families} icon families',
    'status.icons_missing': ' · {count} icons unavailable',
    'status.categories_missing': ' · {categories} prices unavailable; visual references kept.',
    'status.capture_countdown': 'Capture in {remaining} s: go back to the game, stash open.',
    'status.frame_loaded': 'Screenshot loaded. Reading icons and counters automatically…',
    'status.analysing': 'Local OCR analysis…',
    'status.waiting_catalog': 'Reading as soon as the icon catalogue is loaded…',
    'status.wait_before_start': 'Wait for the analysis or the loading to finish before starting tracking.',
    'status.started': 'Started: go back to Path of Exile with the stash open. Every new readable tab is added automatically.',
    'status.stopping': 'Stopping the capture…',
    'status.paused': 'Capture paused.',
    'status.waiting_game': 'Tracking started — go back to the Path of Exile window, stash open. The game must be in the foreground.',
    'status.unknown_layout': 'Unrecognised stash type: pick its type in the selector. No grid applied.',
    'status.unknown_layout_short': 'Unrecognised stash type: choose a view in the selector. No grid applied.',
    'status.tab_recognised': 'Tab recognised: {name}',
    'status.preview_only': 'Live preview — active title unreadable; inventory not synchronised.',
    'status.synced': '{name} synchronised',
    'status.synced_partial': '{name} · {known}/{total} cells confirmed · partial synchronisation',
    'status.identified': '{known}/{total} cells identified with a quantity. {suffix}',
    'status.ready_for_tracking': 'Ready for continuous tracking.',
    'status.tab_to_recognise': 'Active tab still to be recognised for automatic tracking.',
    'status.exported': 'Inventory exported.',
    'status.no_image': 'No image to save: capture the game or start tracking.',
    'status.image_saved': 'Original image saved locally: {path}',
    'status.save_failed': 'Saving failed: {error}',
    'status.session_needs_rows': 'Synchronise at least one registered tab before starting a session.',
    'status.session_needs_prices': 'Load the prices for this league before marking the session.',
    'status.session_marked': '{reason} saved with the last known states of the tabs.',
    'status.language_changed': 'Language changed to {language}.',
    # --- Errors ------------------------------------------------------------
    'error.title_capture': 'Capture',
    'error.title_tab': 'Tab',
    'error.unreadable_image': 'Unreadable image.',
    'error.foreground': 'The Path of Exile window must be in the foreground.',
    'error.windows_only': 'Continuous capture requires Windows.',
    'error.aspect_ratio': 'Use a full 16:9 screenshot, without borders.',
    'error.encode': 'Unable to encode the screenshot.',
    # --- Profiles / tab identity -------------------------------------------
    'profile.need_name': 'Select the active label and provide a name.',
    'profile.duplicate_name': 'This name already exists. Use a distinct alias for duplicates.',
    'profile.unreadable_tab': 'Active tab unreadable: preview without synchronisation.',
    'profile.unreadable_title': 'Active title unreadable: no new inventory created.',
    'profile.ambiguous_label': 'Several tabs share this label: ambiguous identity.',
    'profile.moved': 'Tab “{name}” found again at its new position.',
    'profile.type_corrected': 'Type of “{name}” corrected automatically.',
    'profile.auto_added': 'Tab “{name}” added automatically to the stash.',
    'profile.unknown_tab': 'Unknown tab or hidden label: synchronisation suspended.',
    'profile.ambiguous_identity': 'Ambiguous identity: select a more distinctive label.',
    # --- History page ------------------------------------------------------
    'history.mode_current': 'Historical rates',
    'history.mode_fixed': 'Fixed prices of the first displayed point',
    'history.session_start': 'Session start',
    'history.session_end': 'Session end',
    'history.export': 'Export this history to CSV',
    'history.note': 'Values in divines · last 500 points · observed stock, not farming profit.\n'
                    'Go through all your tabs before each session boundary; their observations are not simultaneous.',
    'history.empty': 'No valuation recorded.',
    'history.empty_hint': 'No valuation: synchronise a registered tab to start.',
    'history.summary': '{count} point(s). The prices and quantities of each date are kept.',
    'history.session_open': 'Session open since {time}. End it after reviewing your tabs.',
    'history.session_delta': 'Session: change at historical rates {historical:+.2f} div · '
                             'change at fixed starting prices {fixed:+.2f} div. Estimates based on the available readings.',
    'history.select_hint': 'Select a point to see its tabs and the date of its prices.',
    'history.chart_empty': 'Chart available after a valuation with prices.',
    'history.quality': '{unread} to check · {unpriced} unpriced · {approximate} abbreviated',
    'history.quality_stale': ' · stale prices',
    'history.detail_header': 'Detail at historical rates. Prices: {date} · conversion: 1 divine = {rate} {primary}.',
    'history.detail_tab': '{name}: {amount}, last observation {observed}',
    'history.never_read': 'never read',
    'history.prices_unavailable': 'unavailable',
    'history.col_date': 'Date (local)',
    'history.col_event': 'Event',
    'history.col_value': 'Value (div)',
    'history.col_quality': 'Reading state',
},
'fr': {
    'reason.auto': 'Auto',
    'reason.empty': 'Case vide',
    'reason.empty_confirmed': 'Vide confirmé',
    'reason.pending': 'Confirmation en cours',
    'reason.local_ref': 'Référence locale',
    'reason.unreadable_count': 'Nombre illisible',
    'reason.variant': 'Variante à vérifier',
    'reason.unknown_icon': 'Icône à vérifier',
    'reason.hidden_icon': 'Icône masquée ou différente',
    'reason.manual': 'Correction manuelle',
    'reason.last_known': 'Dernier état connu',
    'reason.to_check': 'À vérifier',
    'event.refresh': 'Actualisation',
    'event.session_start': 'Début de session',
    'event.session_end': 'Fin de session',
    'layout.currency': 'Currencies',
    'layout.expedition': 'Expédition',
    'layout.runes': 'Runes',
    'layout.kalguuran': 'Runes kalguuran',
    'layout.soul_cores': 'Soul Cores',
    'layout.idols': 'Idoles',
    'layout.ancient_augments': 'Ancient Augments',
    'layout.unknown': 'Type non reconnu',
    'layout.auto': 'Automatique',
    'app.title': 'Exile Worth · PoE 2',
    'app.brand': 'EXILE WORTH',
    'app.tagline': '  /  Votre coffre, en valeur',
    'app.footer': 'Lecture locale • aucune action dans le jeu • prix : poe.ninja',
    'bar.league': 'Ligue',
    'bar.load_prices': 'Charger les prix',
    'bar.language': 'Langue',
    'bar.import': 'Importer une capture',
    'bar.capture': 'Capturer dans 5 s',
    'bar.analyze': 'Analyser',
    'bar.export_csv': 'Exporter CSV',
    'bar.save_image': "Enregistrer l'image",
    'bar.start': 'Démarrer',
    'bar.pause': 'Mettre en pause',
    'state.paused': '● En pause',
    'state.tracking': '● Suivi actif',
    'state.waiting': '● En attente du jeu',
    'state.preview': '● Aperçu en direct',
    'state.unstable': '● Image en mouvement',
    'state.stopping': '● Arrêt en cours',
    'state.stopping_action': 'Arrêt en cours…',
    'page.stash': 'Mon coffre',
    'page.detail': 'Détail & lecture',
    'page.history': 'Valeur & historique',
    'tab.detection': 'Lecture automatique',
    'tab.inventory': 'Inventaire',
    'tab.history': 'Historique',
    'tab.corrections': 'Corrections',
    'dash.total_title': 'Estimation en divines',
    'dash.total_placeholder': 'Le total apparaît dès la lecture d’une capture.',
    'dash.cards_hint': 'Chaque onglet conserve son dernier inventaire connu. Clique sur une carte pour voir son contenu.',
    'dash.preview_card': 'Aperçu en direct',
    'dash.live_badge': '● Mise à jour en direct',
    'dash.total_partial': ' · partiel',
    'dash.preview_unidentified': '{layout} · onglet non identifié',
    'dash.preview_detail': 'Capture actuelle · non ajoutée au coffre\n{unread} cases à vérifier · {unpriced} sans prix',
    'dash.see_detail': 'Voir le détail',
    'dash.never_synced': 'Jamais synchronisé',
    'dash.last_read': 'Dernière lecture : {stamp}',
    'dash.partial': '\nPartiel · {count} à vérifier · {unpriced} sans prix',
    'dash.abbreviated': '\nQuantités abrégées : estimation',
    'dash.tracked': 'Coffre suivi · {tabs} onglet(s) synchronisé(s)',
    'dash.tracked_detail': '{unread} case(s) non lue(s) · {missing} sans prix · {uncertain} à vérifier. Derniers états connus.',
    'dash.displayed_title': 'Estimation de l’onglet affiché',
    'dash.displayed_detail': '{valued} case(s) valorisée(s) · {unread} à lire · {missing} sans prix',
    'dash.preview_line': 'Onglet affiché : {amount} (aperçu, non ajouté au total)',
    'dash.auto_add_hint': 'L’onglet est ajouté automatiquement quand son titre actif est lisible.',
    'dash.abbreviated_suffix': ' · Quantités abrégées : estimation',
    'detail.default_title': 'Lecture du coffre affiché',
    'detail.live_preview': 'Aperçu en direct',
    'detail.live_preview_of': 'Aperçu en direct · {layout}',
    'detail.live_preview_tab': 'Aperçu en direct · {name} · {layout}',
    'detail.canvas_empty': 'Ouvre un onglet de coffre\npuis importe ou capture le jeu.',
    'detail.canvas_no_image': 'Inventaire conservé.\nPas de capture disponible pour cet onglet.',
    'detail.recognition_placeholder': 'Les noms apparaissent après identification des icônes.',
    'detail.recognition': '{identified}/{total} cases occupées identifiées · {ambiguous} variantes à préciser. Les quantités provisoires attendent trois lectures avant sauvegarde.',
    'detail.recognition_none': 'Aucune case occupée reconnue sur cette capture.',
    'col.cell': 'Case',
    'col.item': 'Objet',
    'col.quantity': 'Qté',
    'col.value': 'Valeur',
    'col.value_unit': 'Valeur ({unit})',
    'col.state': 'État',
    'col.tab': 'Onglet',
    'col.last_read': 'Dernière lecture',
    'col.date': 'Date',
    'col.saved_cells': 'Cases enregistrées',
    'item.unknown': 'Objet non reconnu',
    'item.unknown_variant': '{name} · variante inconnue',
    'reading.provisional': ' (provisoire)',
    'reading.provisional_suffix': ' · quantité provisoire',
    'reading.abbreviated_suffix': ' · abrégé',
    'reading.last_confirmed_suffix': ' · dernière quantité confirmée',
    'fix.slot_placeholder': 'Clique une case sur la capture.',
    'fix.slot_selected': 'Sélection : {name} — une correction est possible si la lecture automatique est incertaine.',
    'fix.correct_icon': 'Corriger l’icône',
    'fix.learn_empty': 'Apprendre la case vide',
    'fix.correct_quantity': 'Corriger une quantité…',
    'fix.hint': 'Lecture automatique des icônes et compteurs blancs. Les corrections ci-dessus sont facultatives, pour les détections incertaines.',
    'fix.saved': '{slot} : référence {kind} enregistrée.',
    'fix.kind_empty': 'vide',
    'fix.kind_icon': 'icône',
    'fix.need_preview': 'Ouvre l’aperçu en direct pour corriger une détection sur la capture actuelle.',
    'fix.need_preview_quantity': 'Ouvre l’aperçu en direct pour corriger la quantité sur la capture actuelle.',
    'fix.need_pause': 'En pause, sélectionne une case sur une capture.',
    'fix.need_item': 'Charge les prix puis choisis une currency dans la liste.',
    'fix.need_tab': 'Analyse d’abord une capture avec un onglet reconnu, puis sélectionne une case.',
    'fix.dialog_title': 'Correction',
    'fix.dialog_prompt': 'Quantité vérifiée visuellement :',
    'status.intro': 'Importe une capture ou capture le jeu : les icônes et quantités seront lues automatiquement.',
    'status.busy': 'Mets la lecture en pause et attends la fin des opérations.',
    'status.loading_icons': 'Chargement des icônes : {done}/{total}',
    'status.loading_prices': 'Chargement…',
    'status.prices_not_loaded': 'Prix non chargés',
    'status.prices_received': 'Prix reçus le {stamp}',
    'status.prices_stale_suffix': ' · cache périmé',
    'status.prices_unavailable': 'Prix indisponibles — réessaie ou utilise un cache existant',
    'status.prices_load_league': 'Charge les prix de cette ligue.',
    'status.prices_summary': 'Prix : {stamp}{age} · {missing} sans prix · {uncertain} à vérifier',
    'status.prices_expired': ' · périmés',
    'status.catalog_loaded': 'Catalogue chargé · {families} familles d’icônes',
    'status.icons_missing': ' · {count} icônes indisponibles',
    'status.categories_missing': ' · Prix {categories} indisponibles ; références visuelles conservées.',
    'status.capture_countdown': 'Capture dans {remaining} s : retourne dans le jeu, stash ouvert.',
    'status.frame_loaded': 'Capture chargée. Lecture automatique des icônes et compteurs…',
    'status.analysing': 'Analyse OCR locale…',
    'status.waiting_catalog': 'Lecture dès que le catalogue d’icônes sera chargé…',
    'status.wait_before_start': 'Attends la fin de l’analyse ou du chargement avant de démarrer le suivi.',
    'status.started': 'Démarré : retourne dans Path of Exile, coffre ouvert. Chaque nouvel onglet lisible sera ajouté automatiquement.',
    'status.stopping': 'Arrêt de la capture…',
    'status.paused': 'Capture en pause.',
    'status.waiting_game': 'Suivi démarré — retourne dans la fenêtre Path of Exile, coffre ouvert. Le jeu doit être au premier plan.',
    'status.unknown_layout': 'Type de stash non reconnu : choisis son type dans le sélecteur. Aucune grille appliquée.',
    'status.unknown_layout_short': 'Type de stash non reconnu : choisis une vue dans le sélecteur. Aucune grille appliquée.',
    'status.tab_recognised': 'Onglet reconnu : {name}',
    'status.preview_only': 'Aperçu direct — titre actif illisible ; inventaire non synchronisé.',
    'status.synced': '{name} synchronisé',
    'status.synced_partial': '{name} · {known}/{total} cases confirmées · synchronisation partielle',
    'status.identified': '{known}/{total} cases identifiées avec quantité. {suffix}',
    'status.ready_for_tracking': 'Prêt pour le suivi continu.',
    'status.tab_to_recognise': 'Onglet actif à reconnaître pour le suivi automatique.',
    'status.exported': 'Inventaire exporté.',
    'status.no_image': 'Aucune image à enregistrer : capture le jeu ou démarre le suivi.',
    'status.image_saved': 'Image originale enregistrée localement : {path}',
    'status.save_failed': "Échec de l'enregistrement : {error}",
    'status.session_needs_rows': 'Synchronise au moins un onglet enregistré avant de commencer une session.',
    'status.session_needs_prices': 'Charge les prix de cette ligue avant de marquer la session.',
    'status.session_marked': '{reason} enregistrée avec les derniers états connus des onglets.',
    'status.language_changed': 'Langue changée pour {language}.',
    'error.title_capture': 'Capture',
    'error.title_tab': 'Onglet',
    'error.unreadable_image': 'Image non lisible.',
    'error.foreground': 'La fenêtre Path of Exile doit être au premier plan.',
    'error.windows_only': 'La capture continue nécessite Windows.',
    'error.aspect_ratio': 'Utilise une capture complète au format 16:9, sans bordures.',
    'error.encode': "Impossible d'encoder la capture.",
    'profile.need_name': 'Sélectionne le libellé actif et indique un nom.',
    'profile.duplicate_name': 'Ce nom existe déjà. Utilise un alias distinct pour les doublons.',
    'profile.unreadable_tab': 'Onglet actif illisible : aperçu sans synchronisation.',
    'profile.unreadable_title': 'Titre actif illisible : aucun nouvel inventaire créé.',
    'profile.ambiguous_label': 'Plusieurs onglets portent ce libellé : identité ambiguë.',
    'profile.moved': 'Onglet « {name} » retrouvé à sa nouvelle position.',
    'profile.type_corrected': 'Type de « {name} » corrigé automatiquement.',
    'profile.auto_added': 'Onglet « {name} » ajouté automatiquement au coffre.',
    'profile.unknown_tab': 'Onglet inconnu ou libellé masqué : synchronisation suspendue.',
    'profile.ambiguous_identity': 'Identité ambiguë : sélectionne un libellé plus distinctif.',
    'history.mode_current': 'Cours historiques',
    'history.mode_fixed': 'Prix fixes du premier point affiché',
    'history.session_start': 'Début de session',
    'history.session_end': 'Fin de session',
    'history.export': 'Exporter cet historique CSV',
    'history.note': 'Valeurs en divines · 500 derniers points · stock observé, pas un gain de farm.\n'
                    'Parcours tous tes onglets avant chaque borne de session ; leurs observations ne sont pas simultanées.',
    'history.empty': 'Aucune valorisation enregistrée.',
    'history.empty_hint': 'Aucune valorisation : synchronise un onglet enregistré pour commencer.',
    'history.summary': '{count} point(s). Les prix et quantités de chaque date sont conservés.',
    'history.session_open': 'Session ouverte depuis {time}. Termine après avoir revu tes onglets.',
    'history.session_delta': 'Session : variation aux cours historiques {historical:+.2f} div · '
                             'variation à prix de départ fixes {fixed:+.2f} div. Estimations selon les lectures disponibles.',
    'history.select_hint': 'Sélectionne un point pour consulter ses onglets et la date de ses prix.',
    'history.chart_empty': 'Courbe disponible après une valorisation avec prix.',
    'history.quality': '{unread} à vérifier · {unpriced} sans prix · {approximate} abrégées',
    'history.quality_stale': ' · prix périmés',
    'history.detail_header': 'Détail aux cours historiques. Prix : {date} · conversion : 1 divine = {rate} {primary}.',
    'history.detail_tab': '{name} : {amount}, dernière observation {observed}',
    'history.never_read': 'jamais lu',
    'history.prices_unavailable': 'indisponibles',
    'history.col_date': 'Date (locale)',
    'history.col_event': 'Événement',
    'history.col_value': 'Valeur (div)',
    'history.col_quality': 'État de la lecture',
},
}
