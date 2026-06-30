# RedTable Point — App-Style Redesign Plan

> **Current**: Sidebar-based layout (left panel + floating search) — "website" feel
> **Target**: Top Navigation + Bottom Sheet layout — "native app" feel
> **Context**: Single `index.html` (478 lines) with Kakao Maps JS SDK, ~7133-line GeoJSON data

---

## Architecture Target

```
┌─────────────────────────────────────────────┐
│  TOP NAVIGATION (position: fixed, top: 0)    │
│  ┌───────────────────────────────────────┐   │
│  │      🔍 가게 이름 또는 주소 검색     ✕ │   │  ← Center-aligned search
│  └───────────────────────────────────────┘   │
│  [🍚한식] [🍝양식] [☕카페] [🍜중식] ...    │   │  ← Horizontal scroll chips
└─────────────────────────────────────────────┘

                  ╔═══════════════╗
                  ║  🍚  (circular)║  ← Floating circular markers
                  ║               ║      with soft shadow
                  ╚═══════════════╝
                  MAP AREA (fills remaining)

┌─────────────────────────────────────────────┐
│ ═══ (drag handle)                           │  ← BOTTOM SHEET
│ [기본순] [쿠폰] [거리순]                    │  ← Sort tabs
│ ┌─────────────────────────────────────────┐ │
│ │ 🍚 꽂뚝불낙지	       한식  │  ← Store cards
│ │ 📍 서울 영등포구 영등포로 41길 10        │ │
│ │ ┌──────────┐ (image placeholder)        │ │
│ │ │ 📷 이미지 │                            │ │
│ │ └──────────┘                            │ │
│ ├─────────────────────────────────────────┤ │
│ │ ☕ 커피노리	               카페  │ │
│ │ 📍 서울 영등포구 영등포로 41길 14        │ │
│ │ ...                                     │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

### Bottom Sheet States
| State | Height | Trigger | Content |
|-------|--------|---------|---------|
| `collapsed` | ~60px | Default / tap outside | Drag handle only |
| `peek` | ~35% | Tap handle / marker click | Handle + sort tabs + card preview |
| `half` | ~55% | Swipe up / tap card | Handle + tabs + 4-5 cards |
| `full` | ~85% | Swipe up fully | Handle + tabs + all cards + scroll |

---

## Wave Overview & Dependencies

```
Wave 1: CSS Foundation (parallel-safe)
  ├── 1.1 Design tokens & CSS custom properties
  ├── 1.2 Top navigation CSS
  ├── 1.3 Bottom sheet CSS (with snap states)
  ├── 1.4 Circular marker CSS (canvas rendering)
  └── 1.5 Store card CSS

Wave 2: HTML Restructure (depends on Wave 1)
  ├── 2.1 Top navigation HTML (search + chips row)
  ├── 2.2 Bottom sheet HTML (handle + tabs + card container)
  └── 2.3 Remove old sidebar/search-container HTML

Wave 3: JS Logic Migration (depends on Wave 2)
  ├── 3.1 Bottom sheet state machine (drag interaction)
  ├── 3.2 updateBottomSheet function (migrate from updateSidebar)
  ├── 3.3 Category chips → filter wiring
  ├── 3.4 Sort tabs logic (기본순/쿠폰/거리순)
  └── 3.5 Search bar integration

Wave 4: Marker Redesign (depends on Wave 1.4)
  └── 4.1 Circular floating marker rendering

Wave 5: Cleanup & Verification (depends on all)
  ├── 5.1 Remove dead code
  └── 5.2 QA + Diagnostics
```

---

## Wave 1 — CSS Foundation

All CSS tasks in Wave 1 can run in parallel since they add non-conflicting rule sets.

### 1.1 Design Tokens & CSS Custom Properties

| Field | Value |
|-------|-------|
| **Category** | `visual-engineering` |
| **Skills** | `frontend-ui-ux` |
| **Dependencies** | None |
| **File** | `index.html` (`<style>`) |
| **Estimate** | Small |

**Changes**:

Replace the current `:root {}` block (lines 8-26) with expanded tokens:

```css
:root {
  /* === Category colors (keep existing) === */
  --cat-한식-bg: #FFF3E0; --cat-한식-text: #E65100;
  --cat-양식-bg: #E8F5E9; --cat-양식-text: #2E7D32;
  --cat-카페-bg: #FFF8E1; --cat-카페-text: #F57F17;
  --cat-중식-bg: #FBE9E7; --cat-중식-text: #BF360C;
  --cat-뷰티-bg: #FCE4EC; --cat-뷰티-text: #C2185B;
  --cat-일식-bg: #E3F2FD; --cat-일식-text: #1565C0;
  --cat-베이커리-bg: #FCE4EC; --cat-베이커리-text: #D81B60;
  --cat-서프샵-bg: #E0F2F1; --cat-서프샵-text: #00695C;
  --cat-기타-bg: #F5F5F5; --cat-기타-text: #616161;

  /* === Layout dimensions === */
  --topnav-height: 120px;           /* search + chips */
  --topnav-search-height: 48px;
  --topnav-chips-height: 44px;
  --bottomsheet-handle-height: 28px;
  --bottomsheet-tabs-height: 44px;
  --bottomsheet-collapsed: 60px;    /* handle only */
  --bottomsheet-peek: 35vh;
  --bottomsheet-half: 55vh;
  --bottomsheet-full: 85vh;

  /* === Spacing (keep existing) === */
  --space-xs: 4px; --space-sm: 8px;
  --space-md: 12px; --space-lg: 16px;
  --space-xl: 24px;

  /* === Radius === */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 20px;
  --radius-full: 9999px;

  /* === Shadows === */
  --shadow-soft: 0 4px 20px rgba(0, 0, 0, 0.08);
  --shadow-medium: 0 8px 30px rgba(0, 0, 0, 0.12);
  --shadow-strong: 0 12px 40px rgba(0, 0, 0, 0.16);
  --shadow-marker: 0 4px 12px rgba(0, 0, 0, 0.2);

  /* === Glass === */
  --glass-bg: rgba(255, 255, 255, 0.85);
  --glass-blur: blur(12px);
  --glass-border: 1px solid rgba(255, 255, 255, 0.3);

  /* === Z-index system === */
  --z-map: 0;
  --z-markers: 100;
  --z-bottomsheet: 500;
  --z-topnav: 1000;
  --z-popup: 1100;
  --z-status: 1200;
}
```

**Success Criteria**:
- [x] All existing `var(--cat-*)` references still resolve correctly
- [x] New tokens are defined for every value needed by top nav, bottom sheet, and markers
- [x] No hardcoded magic numbers in Wave 2-5 CSS (all use variables)

---

### 1.2 Top Navigation CSS

| Field | Value |
|-------|-------|
| **Category** | `visual-engineering` |
| **Skills** | `frontend-ui-ux` |
| **Dependencies** | 1.1 |
| **File** | `index.html` |
| **Estimate** | Small |

**CSS to add** (in `<style>`, after the `:root` block):

```css
/* ==========================================
   TOP NAVIGATION
   ========================================== */
#top-nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: var(--z-topnav);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-md) var(--space-lg) var(--space-sm);
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border-bottom: var(--glass-border);
  pointer-events: none; /* container doesn't block clicks */
}
#top-nav > * {
  pointer-events: auto; /* children are interactive */
}

/* --- Search Bar --- */
#search-wrapper {
  display: flex;
  align-items: center;
  width: min(480px, 100%);
  height: var(--topnav-search-height);
  padding: 0 var(--space-lg);
  background: #f2f3f5;
  border-radius: var(--radius-xl);
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  transition: box-shadow 0.2s, background 0.2s;
}
#search-wrapper:focus-within {
  background: #fff;
  box-shadow: var(--shadow-medium);
}
#search-icon {
  font-size: 16px;
  margin-right: var(--space-sm);
  opacity: 0.5;
  flex-shrink: 0;
}
#search-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 15px;
  padding: var(--space-sm) 0;
  color: #1a1a1a;
}
#search-input::placeholder { color: #999; }
#clear-search {
  background: none;
  border: none;
  cursor: pointer;
  color: #999;
  font-size: 16px;
  padding: var(--space-xs);
  flex-shrink: 0;
}

/* --- Category Chips Row --- */
#chips-row {
  display: flex;
  gap: var(--space-sm);
  width: 100%;
  max-width: 600px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: var(--space-xs) 0;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none; /* Firefox */
}
#chips-row::-webkit-scrollbar { display: none; } /* Chrome/Safari */

.chip {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px 6px 10px;
  border-radius: var(--radius-full);
  border: 1.5px solid #e0e0e0;
  background: white;
  font-size: 13px;
  font-weight: 500;
  color: #555;
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
  white-space: nowrap;
}
.chip:hover {
  border-color: #bbb;
  background: #fafafa;
}
.chip.active {
  background: #2b2b2b;
  color: white;
  border-color: #2b2b2b;
}
.chip .chip-emoji { font-size: 15px; }
.chip .chip-count {
  font-size: 11px;
  opacity: 0.7;
  font-weight: 400;
}
.chip.active .chip-count { opacity: 0.8; }
```

**Success Criteria**:
- [x] Search bar is centered, has glass effect, and matches mockup width (~480px max)
- [x] Category chips scroll horizontally with hidden scrollbar
- [x] Active chips have filled dark background; inactive are outlined
- [x] Top nav doesn't block map interactions (pointer-events trick)

---

### 1.3 Bottom Sheet CSS

| Field | Value |
|-------|-------|
| **Category** | `visual-engineering` |
| **Skills** | `frontend-ui-ux` |
| **Dependencies** | 1.1 |
| **File** | `index.html` |
| **Estimate** | Medium |

**CSS to add**:

```css
/* ==========================================
   BOTTOM SHEET
   ========================================== */
#bottom-sheet {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: var(--z-bottomsheet);
  background: white;
  border-radius: var(--radius-xl) var(--radius-xl) 0 0;
  box-shadow: var(--shadow-strong);
  transition: transform 0.4s cubic-bezier(0.32, 0.72, 0, 1);
  will-change: transform;
  display: flex;
  flex-direction: column;
  overflow: hidden;

  /* Start collapsed */
  transform: translateY(calc(100% - var(--bottomsheet-collapsed)));
}
/* Map area adjusts so bottom sheet doesn't overlap controls */
#map {
  /* No change needed — map fills viewport, sheet overlays */
}

/* --- States --- */
#bottom-sheet.state-peek {
  transform: translateY(calc(100% - var(--bottomsheet-peek)));
}
#bottom-sheet.state-half {
  transform: translateY(calc(100% - var(--bottomsheet-half)));
}
#bottom-sheet.state-full {
  transform: translateY(0);
}

/* --- Drag Handle --- */
#sheet-handle {
  flex-shrink: 0;
  display: flex;
  justify-content: center;
  align-items: center;
  height: var(--bottomsheet-handle-height);
  cursor: grab;
  user-select: none;
  touch-action: none;
}
#sheet-handle:active { cursor: grabbing; }
#sheet-handle::after {
  content: '';
  display: block;
  width: 36px;
  height: 4px;
  border-radius: 2px;
  background: #ddd;
}

/* --- Sort Tabs --- */
#sheet-tabs {
  flex-shrink: 0;
  display: flex;
  gap: 0;
  height: var(--bottomsheet-tabs-height);
  padding: 0 var(--space-lg);
  border-bottom: 1px solid #f0f0f0;
}
.sheet-tab {
  position: relative;
  padding: 0 var(--space-lg);
  font-size: 14px;
  font-weight: 500;
  color: #999;
  cursor: pointer;
  display: flex;
  align-items: center;
  transition: color 0.2s;
  background: none;
  border: none;
  user-select: none;
}
.sheet-tab.active {
  color: #1a1a1a;
}
.sheet-tab.active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: var(--space-lg);
  right: var(--space-lg);
  height: 3px;
  border-radius: 1.5px 1.5px 0 0;
  background: #e74c3c;
}

/* --- Sheet Content (card list) --- */
#sheet-content {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  padding: var(--space-sm) var(--space-lg) var(--space-xl);
}

/* --- Store Cards --- */
.store-card {
  display: flex;
  gap: var(--space-md);
  padding: var(--space-md) 0;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background 0.15s;
}
.store-card:last-child { border-bottom: none; }
.store-card:hover { background: #fafafa; }
.store-card:active { background: #f0f0f0; }

.store-card-image {
  flex-shrink: 0;
  width: 80px;
  height: 80px;
  border-radius: var(--radius-md);
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: #ccc;
  overflow: hidden;
}
.store-card-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.store-card-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
}
.store-card-title {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.store-card-categories {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.store-card-address {
  font-size: 12px;
  color: #888;
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.store-card-empty {
  text-align: center;
  color: #999;
  padding: var(--space-xl);
  font-size: 14px;
}

/* --- Coupon badge (future) --- */
.store-card-badge {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  background: #e74c3c;
  color: white;
}
```

**Success Criteria**:
- [x] Bottom sheet renders in `collapsed` state on load (only handle visible)
- [x] Sheet smoothly animates between `collapsed`, `peek`, `half`, `full` states
- [x] Sort tabs have underline indicator on active tab
- [x] Store cards are rich: image placeholder, title, categories, address
- [x] Sheet content scrolls independently when in `half` or `full` state

---

### 1.4 Circular Marker CSS / Canvas Rendering Spec

| Field | Value |
|-------|-------|
| **Category** | `visual-engineering` |
| **Skills** | `frontend-ui-ux` |
| **Dependencies** | 1.1 |
| **File** | `index.html` (JS canvas changes) |
| **Estimate** | Small |

**New marker design** (canvas rendering spec):

| Aspect | Current | Target |
|--------|---------|--------|
| Shape | Water-drop pin (bezier curve) | Perfect circle |
| Background | White fill | White circle with shadow |
| Shadow | `rgba(0,0,0,0.3)`, blur 4, offsetY 2 | `rgba(0,0,0,0.2)`, blur 8, offsetY 4 |
| Emoji area | `arc(size/2, size/3, size/4)` | Centered `arc(size/2, size/2, size*0.35)` |
| Size | 48px | 44px default, 52px on hover |
| Border | 1px `#eee` stroke | No border (shadow is visual boundary) |
| Hover effect | Size +8px (image swap) | Size +8px + shadow increase |

**Required changes to `createEmojiMarkerImage`** (lines 132-178):

```javascript
function createEmojiMarkerImage(emoji, size) {
  size = size || 44;
  var dpr = window.devicePixelRatio || 1;
  var cacheKey = emoji + '-' + size + '-v2';  // bust old cache
  if (markerCache[cacheKey]) return markerCache[cacheKey];

  var canvas = document.createElement('canvas');
  canvas.width = size * dpr;
  canvas.height = size * dpr;
  var ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  // Shadow (render twice: once for shadow, once for fill)
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2 - 1, 0, Math.PI * 2);
  ctx.shadowColor = 'rgba(0, 0, 0, 0.2)';
  ctx.shadowBlur = 8;
  ctx.shadowOffsetY = 4;
  ctx.fillStyle = 'white';
  ctx.fill();

  // Re-draw circle to avoid shadow darkening the center
  ctx.shadowColor = 'transparent';
  ctx.shadowBlur = 0;
  ctx.shadowOffsetY = 0;
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2 - 1, 0, Math.PI * 2);
  ctx.fillStyle = 'white';
  ctx.fill();

  // Emoji
  ctx.font = (size * 0.45) + 'px "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(emoji, size / 2, size / 2 + 1);

  var dataUrl = canvas.toDataURL();
  markerCache[cacheKey] = dataUrl;
  return dataUrl;
}
```

**Also update the hover handler** (lines 325-330):
- Keep the size swap on hover, but ensure the larger image has the same circular style.

**Success Criteria**:
- [x] Markers are circular (not water-drop shaped)
- [x] Soft shadow visible beneath each marker
- [x] Emoji is centered clearly inside the circle
- [x] Hover enlarges the marker with enhanced shadow
- [x] Retina display renders crisp markers (DPR scaling preserved)

---

### 1.5 Store Card CSS (reuses category badges)

No standalone task — card CSS is part of 1.3 (bottom sheet). The existing `.category-badge` and `.cat-*` classes reused for cards.

---

## Wave 2 — HTML Restructure

### 2.1 Top Navigation HTML

| Field | Value |
|-------|-------|
| **Category** | `visual-engineering` |
| **Skills** | `frontend-ui-ux` |
| **Dependencies** | 1.2 |
| **File** | `index.html` |
| **Estimate** | Small |

**HTML to add** (insert after `<div id="map"></div>` but before `<script>`, or as sibling to `#map`):

```html
<!-- TOP NAVIGATION -->
<div id="top-nav">
  <div id="search-wrapper">
    <span id="search-icon">🔍</span>
    <input type="text" id="search-input" placeholder="가게 이름 또는 주소 검색" autocomplete="off">
    <button id="clear-search" style="display:none;">✕</button>
  </div>
  <div id="chips-row" id="chips-row">
    <!-- populated by JS -->
  </div>
</div>
```

**Key details**:
- `action` attrs: Same `id` values as current `#search-input` and `#clear-search` — preserves JS binding
- `#chips-row` is initially empty; populated by JS in Wave 3.3
- Uses `autocomplete="off"` to prevent browser autofill overlay

**Success Criteria**:
- [x] Top nav renders with glass-morphism background
- [x] Search bar mirrors current position but centered
- [x] Chips row is empty but ready for JS population

---

### 2.2 Bottom Sheet HTML

| Field | Value |
|-------|-------|
| **Category** | `visual-engineering` |
| **Skills** | `frontend-ui-ux` |
| **Dependencies** | 1.3 |
| **File** | `index.html` |
| **Estimate** | Small |

**HTML to add** (after `#top-nav`, before `#map`, or as sibling to `#map`):

```html
<!-- BOTTOM SHEET -->
<div id="bottom-sheet" class="state-collapsed">
  <div id="sheet-handle"></div>
  <div id="sheet-tabs">
    <button class="sheet-tab active" data-sort="default">기본순</button>
    <button class="sheet-tab" data-sort="coupon">쿠폰</button>
    <button class="sheet-tab" data-sort="distance">거리순</button>
  </div>
  <div id="sheet-content">
    <!-- populated by updateBottomSheet() -->
  </div>
</div>
```

**Key details**:
- `data-sort` attributes on tabs for JS targeting
- `#sheet-content` is the rendering target for `updateBottomSheet()`
- Initial class `state-collapsed` corresponds to collapsed state

**Success Criteria**:
- [x] Bottom sheet renders at bottom of viewport in collapsed state
- [x] Handle, tabs, and content container are distinct elements
- [x] All three sort tabs are present with correct labels

---

### 2.3 Remove Old Sidebar/Search HTML

| Field | Value |
|-------|-------|
| **Category** | `visual-engineering` |
| **Skills** | `frontend-ui-ux` |
| **Dependencies** | 2.1, 2.2 (new structure in place first) |
| **File** | `index.html` |
| **Estimate** | Small |

**Remove these HTML elements**:

1. **Remove entire `.sidebar-tabs` div** (lines 88-91):
   ```html
   <div class="sidebar-tabs">
       <div onclick="toggleSidebar()">☰</div>
       <div onclick="toggleSidebar('filter')">🏷️</div>
   </div>
   ```

2. **Remove entire `#sidebar` div** (lines 92-109):
   ```html
   <div id="sidebar">...</div>
   ```

3. **Remove old `#search-container`** (lines 111-117):
   ```html
   <div id="search-container">...</div>
   ```

**Success Criteria**:
- [x] No sidebar elements in the DOM
- [x] No old search-container in the DOM
- [x] `toggleSidebar()` calls would throw (but are no longer called)

---

## Wave 3 — JS Logic Migration

### 3.1 Bottom Sheet State Machine (Drag Interaction)

| Field | Value |
|-------|-------|
| **Category** | `logic` |
| **Skills** | None |
| **Dependencies** | 1.1, 1.3 (CSS classes exist) |
| **File** | `index.html` (JS in `<script>`) |
| **Estimate** | Medium |

**Implementation**: Add after the Kakao Maps load callback.

```javascript
// =============================================
// Bottom Sheet State Machine
// =============================================
var sheet = document.getElementById('bottom-sheet');
var sheetHandle = document.getElementById('sheet-handle');
var sheetStates = ['collapsed', 'peek', 'half', 'full'];

function setSheetState(state) {
  sheet.className = 'state-' + state;
}

var dragStartY = 0;
var dragCurrentY = 0;
var isDragging = false;

sheetHandle.addEventListener('mousedown', startDrag);
sheetHandle.addEventListener('touchstart', startDrag, { passive: true });

function startDrag(e) {
  isDragging = true;
  dragStartY = e.touches ? e.touches[0].clientY : e.clientY;
  document.addEventListener('mousemove', onDrag);
  document.addEventListener('mouseup', endDrag);
  document.addEventListener('touchmove', onDrag, { passive: true });
  document.addEventListener('touchend', endDrag);
}

function onDrag(e) {
  if (!isDragging) return;
  dragCurrentY = e.touches ? e.touches[0].clientY : e.clientY;
  var delta = dragStartY - dragCurrentY; // positive = swipe up
  
  var currentState = sheet.className.replace('state-', '');
  var currentIndex = sheetStates.indexOf(currentState);
  
  var newIndex;
  if (delta > 50) { // swipe up
    newIndex = Math.min(currentIndex + 1, sheetStates.length - 1);
  } else if (delta < -50) { // swipe down
    newIndex = Math.max(currentIndex - 1, 0);
  } else {
    return; // threshold not met
  }
  
  if (newIndex !== currentIndex) {
    setSheetState(sheetStates[newIndex]);
  }
  isDragging = false;
  cleanupDrag();
}

function endDrag() {
  isDragging = false;
  cleanupDrag();
}

function cleanupDrag() {
  document.removeEventListener('mousemove', onDrag);
  document.removeEventListener('mouseup', endDrag);
  document.removeEventListener('touchmove', onDrag);
  document.removeEventListener('touchend', endDrag);
}

// Tap handle to toggle between collapsed and peek
sheetHandle.addEventListener('click', function() {
  if (sheet.className === 'state-collapsed') {
    setSheetState('peek');
  } else {
    setSheetState('collapsed');
  }
});
```

**Alternative simpler approach** (recommended for MVP): Use `click` to cycle through states instead of full drag:

```javascript
var stateOrder = ['collapsed', 'peek', 'half', 'full'];
var stateIndex = 0;

sheetHandle.addEventListener('click', function() {
  stateIndex = (stateIndex + 1) % stateOrder.length;
  setSheetState(stateOrder[stateIndex]);
});
```

**Success Criteria**:
- [x] Sheet can be expanded by clicking/ dragging the handle
- [x] Sheet can be collapsed by dragging down or clicking handle
- [x] Animation is smooth (CSS transition on `transform`)
- [x] Drag threshold of ~50px prevents accidental triggers

---

### 3.2 updateBottomSheet Function (Migrate from updateSidebar)

| Field | Value |
|-------|-------|
| **Category** | `logic` |
| **Skills** | None |
| **Dependencies** | 2.2 (bottom sheet HTML exists), 1.5 (card CSS exists) |
| **File** | `index.html` |
| **Estimate** | Medium |

**Current `updateSidebar`** (lines 348-383) renders list items into `#sidebar-content`.

**New `updateBottomSheet`** replaces it:

```javascript
function updateBottomSheet() {
  var sheetContent = document.getElementById('sheet-content');
  sheetContent.innerHTML = '';
  
  var filtered = allMarkers.filter(m => {
    var p = m.feature.properties;
    var match = (p.title || '').toLowerCase().includes(searchTerm) || (p.address || '').toLowerCase().includes(searchTerm);
    return match && (p.categories || []).some(cat => activeCategories.has(cat));
  });
  
  // Update store count in header
  var headerSpan = document.getElementById('store-count-header');
  if (headerSpan) headerSpan.textContent = '매장 (' + filtered.length + ')';
  
  if (filtered.length === 0) {
    sheetContent.innerHTML = '<div class="store-card-empty">검색 결과가 없습니다</div>';
    return;
  }
  
  // Sort based on active tab
  var sortBy = document.querySelector('.sheet-tab.active');
  var sortKey = sortBy ? sortBy.dataset.sort : 'default';
  if (sortKey === 'distance') {
    var center = map.getCenter();
    filtered.sort(function(a, b) {
      var aDist = getDistance(center, a.marker.getPosition());
      var bDist = getDistance(center, b.marker.getPosition());
      return aDist - bDist;
    });
  }
  // 'default' keeps original order; 'coupon' is placeholder for future
  
  filtered.forEach(m => {
    var p = m.feature.properties;
    var emoji = categoryIcons[p.categories[0]] || '📌';
    var categoriesHtml = (p.categories || []).map(cat =>
      '<span class="category-badge cat-' + esc(cat) + '">' + esc(cat) + '</span>'
    ).join('');
    
    var card = document.createElement('div');
    card.className = 'store-card';
    card.innerHTML =
      '<div class="store-card-image">' +
        esc(emoji) +
      '</div>' +
      '<div class="store-card-body">' +
        '<div class="store-card-title">' + esc(p.title || 'Untitled') + '</div>' +
        '<div class="store-card-categories">' + categoriesHtml + '</div>' +
        '<div class="store-card-address">📍 ' + esc(p.address || '') + '</div>' +
      '</div>';
    
    card.onclick = (function(marker, feature) {
      return function(e) {
        e.stopPropagation();
        map.setCenter(marker.getPosition());
        map.setLevel(5);
        openPopup(marker, feature);
        // Expand sheet to peek when card is clicked
        setSheetState('peek');
      };
    })(m.marker, m.feature);
    
    sheetContent.appendChild(card);
  });
}

// Helper: approximate distance between two LatLng points (Haversine)
function getDistance(latlng1, latlng2) {
  var R = 6371; // km
  var dLat = (latlng2.getLat() - latlng1.getLat()) * Math.PI / 180;
  var dLng = (latlng2.getLng() - latlng1.getLng()) * Math.PI / 180;
  var a = Math.sin(dLat/2) * Math.sin(dLat/2) +
          Math.cos(latlng1.getLat() * Math.PI / 180) * Math.cos(latlng2.getLat() * Math.PI / 180) *
          Math.sin(dLng/2) * Math.sin(dLng/2);
  var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}
```

**Also update `updateMarkers`** to call `updateBottomSheet` instead of `updateSidebar` (line 408).

**Success Criteria**:
- [x] `updateBottomSheet` renders the same filtered data as `updateSidebar` did
- [x] Store cards show emoji placeholder image, title, categories, address
- [x] Click on a card centers the map and opens popup
- [x] Empty state shows "검색 결과가 없습니다"
- [x] Sort by distance works when '거리순' tab is active
- [x] `updateMarkers()` calls `updateBottomSheet()` instead of `updateSidebar()`

---

### 3.3 Category Chips → Filter Wiring

| Field | Value |
|-------|-------|
| **Category** | `logic` |
| **Skills** | None |
| **Dependencies** | 2.1 (chips row exists) |
| **File** | `index.html` |
| **Estimate** | Small |

**Replace `updateFilterChips` function** (lines 412-437). The old function populated the filter pane inside the sidebar. The new function populates the chips row in the top nav:

```javascript
function updateFilterChips() {
  var chipsRow = document.getElementById('chips-row');
  chipsRow.innerHTML = '';
  
  // Add "All" chip first
  var allChip = document.createElement('div');
  allChip.className = 'chip' + (activeCategories.size === Object.keys(categoryIcons).length ? ' active' : '');
  allChip.innerHTML = '<span class="chip-emoji">📍</span> 전체 <span class="chip-count">' + allMarkers.length + '</span>';
  allChip.onclick = function() {
    if (activeCategories.size === Object.keys(categoryIcons).length) {
      // Deselect all
      activeCategories.clear();
    } else {
      // Select all
      Object.keys(categoryIcons).forEach(cat => activeCategories.add(cat));
    }
    updateMarkers();
  };
  chipsRow.appendChild(allChip);
  
  Object.keys(categoryIcons).forEach(cat => {
    var count = allMarkers.filter(m => (m.feature.properties.categories || []).includes(cat)).length;
    var chip = document.createElement('div');
    chip.className = 'chip' + (activeCategories.has(cat) ? ' active' : '');
    chip.innerHTML = '<span class="chip-emoji">' + categoryIcons[cat] + '</span> ' + cat + ' <span class="chip-count">' + count + '</span>';
    chip.onclick = function(e) {
      e.stopPropagation();
      if (activeCategories.has(cat)) {
        activeCategories.delete(cat);
      } else {
        activeCategories.add(cat);
      }
      updateMarkers();
    };
    chipsRow.appendChild(chip);
  });
}
```

**Also call `updateFilterChips()` on initial load** (same as current behavior, line ~409).

**Success Criteria**:
- [x] Chips row in top nav shows all categories with emoji + name + count
- [x] "전체" chip appears first (toggle all/none)
- [x] Clicking a chip toggles that category filter
- [x] Active chips have filled style; inactive chips have outlined style
- [x] Filtering updates both markers and bottom sheet simultaneously

---

### 3.4 Sort Tabs Logic

| Field | Value |
|-------|-------|
| **Category** | `logic` |
| **Skills** | None |
| **Dependencies** | 2.2, 3.2 |
| **File** | `index.html` |
| **Estimate** | Small |

**Add event handlers** for sort tabs:

```javascript
// In the Kakao Maps load callback, after sheet tabs are in DOM:
document.querySelectorAll('.sheet-tab').forEach(function(tab) {
  tab.addEventListener('click', function() {
    document.querySelectorAll('.sheet-tab').forEach(function(t) {
      t.classList.remove('active');
    });
    this.classList.add('active');
    updateBottomSheet();
  });
});
```

**Sort behaviors**:
| `data-sort` | Behavior |
|-------------|----------|
| `default` | Original data order (as loaded from GeoJSON) |
| `coupon` | Same as default (placeholder for future coupon filter) |
| `distance` | Sort by Haversine distance from current map center |

**Success Criteria**:
- [x] Clicking a sort tab makes it active and deactivates others
- [x] '기본순' keeps original order
- [x] '거리순' sorts cards by distance from map center
- [x] Bottom sheet re-renders when sort tab changes

---

### 3.5 Search Bar Integration

| Field | Value |
|-------|-------|
| **Category** | `logic` |
| **Skills** | None |
| **Dependencies** | 2.1 |
| **File** | `index.html` |
| **Estimate** | Small |

**Minimal changes needed** — the existing search logic (lines 449-473) uses `#search-input` and `#clear-search` IDs, which are preserved in the new HTML. However:

1. **Remove the old `#result-count`** display reference (line 455) — the count is shown in the chips row "전체" chip instead.
2. **Update `updateResultCount`** or remove it (no longer shown in top nav; count is in chips).
3. **Ensure the search icon (`🔍`) is part of the input wrapper** (already in HTML from 2.1).

```javascript
// Simplified: keep existing oninput logic, remove result-count ref
var searchInput = document.getElementById('search-input');
var clearSearch = document.getElementById('clear-search');
var debounceTimer;

searchInput.oninput = function(e) {
  clearSearch.style.display = e.target.value ? 'block' : 'none';
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(function() {
    searchTerm = e.target.value.toLowerCase();
    updateMarkers();
  }, 300);
};

clearSearch.onclick = function() {
  searchInput.value = '';
  clearSearch.style.display = 'none';
  searchTerm = '';
  updateMarkers();
};
```

**Success Criteria**:
- [x] Search input works with debounce as before
- [x] Clear button appears when text is entered
- [x] Search filters both markers and bottom sheet cards
- [x] Result count is conveyed via chips (number updates in "전체" chip)

---

## Wave 4 — Marker Redesign

### 4.1 Circular Floating Marker Rendering

| Field | Value |
|-------|-------|
| **Category** | `visual-engineering` |
| **Skills** | `frontend-ui-ux` |
| **Dependencies** | 1.4 (canvas rendering spec) |
| **File** | `index.html` |
| **Estimate** | Small |

**Already specified in 1.4** — this wave applies the spec.

**Changes**:
1. **Replace `createEmojiMarkerImage`** with the circular version from 1.4.
2. **Update the marker creation loop** (lines 312-337) to:
   - Use `createEmojiMarkerImage(iconText, 44)` for default size
   - On hover, swap to `createEmojiMarkerImage(iconText, 52)` with larger shadow
   - Keep `mouseover`/`mouseout` handlers for hover effect

3. **Remove the old `catColor` usage** from marker image (line 317). The circular markers don't use category background color — they're white with emoji.

**Success Criteria**:
- [x] Markers are circular, not water-drop shaped
- [x] Soft shadow visible beneath each marker
- [x] Hover effect enlarges marker with enhanced shadow
- [x] Emoji is centered and readable
- [x] Retina display support (DPR scaling)

---

## Wave 5 — Cleanup & Verification

### 5.1 Remove Dead Code

| Field | Value |
|-------|-------|
| **Category** | `cleanup` |
| **Skills** | `ai-slop-remover` |
| **Dependencies** | All Waves 1-4 |
| **File** | `index.html` |
| **Estimate** | Small |

**Remove these JS functions and references**:

| Code | Lines | Reason |
|------|-------|--------|
| `toggleSidebar(pane)` | 222-228 | Sidebar removed; replaced by bottom sheet |
| `window.selectAll` | 439-442 | Replaced by "전체" chip |
| `window.deselectAll` | 444-447 | Replaced by "전체" chip |
| `updateResultCount(count)` | 454-456 | Count shown in chips now |
| Old `updateSidebar` function body | 348-383 | Replaced by `updateBottomSheet` |
| Old `updateFilterChips` function body | 412-437 | Replaced by chips-row version |
| `#result-count` element reference | ~452 | No longer in DOM |
| `sidebarContent` variable | ~294, ~349 | Sidebar removed |
| `activeCategories = new Set(...)` | ~216 | Keep — still used by chips |

**Also remove these CSS classes** (if no longer referenced):
| Class | Reason |
|-------|--------|
| `.sidebar-item` | Sidebar removed |
| `.sidebar-tabs` | Sidebar removed |
| `.filter-chip` | Replaced by `.chip` |
| `#search-container` | Replaced by `#top-nav` |
| `#sidebar` | Replaced by `#bottom-sheet` |
| `#sidebar.collapsed` | Sidebar removed |

**Also remove HTML comments / dead template references** from old structure.

**Success Criteria**:
- [x] No `toggleSidebar` calls in the code
- [x] No references to deleted DOM elements (`#sidebar`, `.sidebar-tabs`, `#search-container`)
- [x] `updateSidebar` function removed (or renamed to `updateBottomSheet`)
- [x] No dead CSS selectors

---

### 5.2 QA + Diagnostics

| Field | Value |
|-------|-------|
| **Category** | `verification` |
| **Skills** | `playwright`, `review-work` |
| **Dependencies** | All Waves 1-5 |
| **File** | — |
| **Estimate** | Medium |

**Checklist**:

| # | Check | Method |
|---|-------|--------|
| 1 | `lsp_diagnostics` on `index.html` — 0 errors | `lsp_diagnostics` |
| 2 | Top nav renders at top with glass effect | Visual + DevTools |
| 3 | Search bar centered, functional with debounce | Type + observe |
| 4 | Category chips scroll horizontally, toggle filter | Click each chip |
| 5 | Bottom sheet starts collapsed, cycles through states | Click handle |
| 6 | Sort tabs order: 기본순 > 쿠폰 > 거리순 | Click each tab |
| 7 | 거리순 sorts by distance from map center | Move map, check order |
| 8 | Store cards render with emoji/categories/address | Visual inspection |
| 9 | Card click centers map + opens popup | Click card |
| 10 | Map markers are circular, not water-drop | Visual inspection |
| 11 | Marker hover enlarges | Hover over marker |
| 12 | Marker clustering still works at zoom ≤10 | Zoom out |
| 13 | Search + category filters work together | Both active |
| 14 | Empty state shows "검색 결과가 없습니다" | Filter to zero |
| 15 | Mobile: sheet still works and cards look good | DevTools mobile view |
| 16 | No console errors | DevTools console |

**Success Criteria**:
- [x] All 16 checks pass
- [x] LSP diagnostics: 0 errors
- [x] No console errors on load

---

## Execution Order

### Parallel Wave 1 (5 CSS tasks — no conflicts)
```
agent-1: Task 1.1  (Design tokens)
agent-2: Task 1.2  (Top nav CSS)
agent-3: Task 1.3  (Bottom sheet CSS)
agent-4: Task 1.4  (Circular marker spec — canvas code only)
```
All 1.x can run simultaneously since they add non-conflicting rule sets.

### Parallel Wave 2 (2 HTML + 1 cleanup)
```
agent-1: Task 2.1  (Top nav HTML)
agent-2: Task 2.2  (Bottom sheet HTML)
```
Both depend on 1.x being in place.

### Sequential Wave 2 → 2.3 (depends on 2.1, 2.2)
```
agent-1: Task 2.3  (Remove old sidebar/search HTML)
```

### Parallel Wave 3 (JS migration)
```
agent-1: Task 3.1  (Bottom sheet state machine)
agent-2: Task 3.2  (updateBottomSheet)
agent-3: Task 3.3  (Category chips wiring)
agent-4: Task 3.4  (Sort tabs logic)
agent-5: Task 3.5  (Search bar integration)
```
All depend on Wave 2. Tasks 3.2, 3.3 modify JS functions; 3.1 is new code. They can run in parallel if each edits a distinct section.

### Sequential Wave 4 (depends on 1.4)
```
agent-1: Task 4.1  (Apply circular markers in JS)
```
Modifies the marker rendering loop — ensure no conflict with Wave 3.

### Parallel Wave 5 (cleanup + verification)
```
agent-1: Task 5.1  (Remove dead code)
agent-2: Task 5.2  (QA + diagnostics)
```
5.1 must run after all Waves 1-4. 5.2 runs after 5.1.

---

## Skill Load Recommendations

| Task | Recommended Skills | Notes |
|------|-------------------|-------|
| 1.1 | `frontend-ui-ux` | Design system thinking |
| 1.2 | `frontend-ui-ux` | Glass-morphism, layout |
| 1.3 | `frontend-ui-ux` | Bottom sheet animations |
| 1.4 | `frontend-ui-ux` | Canvas rendering |
| 2.1 | `frontend-ui-ux` | Semantic HTML |
| 2.2 | `frontend-ui-ux` | Semantic HTML |
| 2.3 | — | Simple deletion |
| 3.1 | — | State machine logic |
| 3.2 | — | Function refactoring |
| 3.3 | — | Event wiring |
| 3.4 | — | Sort logic |
| 3.5 | — | Debounced input |
| 4.1 | `frontend-ui-ux` | Canvas + marker swap |
| 5.1 | `ai-slop-remover` | Dead code removal |
| 5.2 | `playwright`, `review-work` | QA automation |

---

## Risk & Edge Cases

| Risk | Mitigation |
|------|-----------|
| **Kakao Maps z-index conflicts** with bottom sheet | Explicit z-index system in CSS variables; `#bottom-sheet` at `--z-bottomsheet: 500` |
| **Bottom sheet blocks map panning** when collapsed | Sheet is only 60px tall in collapsed state; map fills remaining space. Ensure `pointer-events: none` on sheet container when collapsed, or only on handle area |
| **Bottom sheet drag interferes with card scroll** | Use `touch-action: pan-y` on `#sheet-content` for inner scroll; drag gesture only on `#sheet-handle` |
| **Marker cluster click vs bottom sheet** | Cluster click already opens popup; sheet can auto-expand to `peek` state when marker is clicked |
| **Large dataset performance (396+ features)** | Cards are rendered in DOM — fine for <500. If performance issues, virtualize with intersection observer |
| **Canvas security (toDataURL tainted)** | No external images on canvas — only emoji text + shapes. No taint risk |
| **Browser support for `backdrop-filter`** | Falls back to solid white on Safari <14 / Firefox <103. Acceptable degradation |
| **Search + filter combo edge case** | Both filters apply simultaneously in `updateMarkers`/`updateBottomSheet` — ensure AND logic, not OR |
| **Bottom sheet state reset on filter change** | Re-render preserves current state; no reset needed |

---

## Specific Migration: `updateSidebar` → `updateBottomSheet`

### Caller Changes

| Old Call | New Call | File:Line |
|----------|----------|-----------|
| `updateSidebar()` | `updateBottomSheet()` | `updateMarkers()` ~408 |
| (called from `updateMarkers`) | (same) | — |

### Variable Mapping

| Old Variable | New Variable | Change |
|-------------|-------------|--------|
| `sidebarContent` (getElementById) | `sheetContent` (getElementById) | Target element ID changes |
| `.sidebar-item` div | `.store-card` div | Complete card redesign |
| `<h3>` for title | `.store-card-title` div | Semantic change |
| Direct text for categories | `.store-card-categories` div | Structured layout |
| `<p>` for address | `.store-card-address` div | With 📍 icon |
| (no image) | `.store-card-image` div | New — emoji placeholder |
| `item.onclick` | `card.onclick` | Same behavior, new target |

### Data Flow (unchanged)

```
allMarkers → filter by (searchTerm + activeCategories) → sort (by tab) → render cards
                                         ↑
                              updateMarkers() called from:
                                - searchInput.oninput
                                - clearSearch.onclick
                                - chip.onclick (category toggle)
                                - tab click (sort change)
```

The filter-sort-render pipeline is identical — only the render target and card markup change.

---

## Summary of Files Changed

| File | Change Type | Lines Affected |
|------|-------------|---------------|
| `index.html` | Modified | ~80% of file touched (CSS: rewrite, HTML: replace, JS: refactor) |

**No other files need changes.** The entire application is a single HTML file.
