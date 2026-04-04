# WCAG 2.1 AA Checklist

Quick reference for accessibility compliance.

## Perceivable

### 1.1 Text Alternatives

- [ ] All images have appropriate alt text
- [ ] Decorative images have `alt=""` and `aria-hidden="true"`
- [ ] Complex images have extended descriptions
- [ ] Icons have accessible names

### 1.2 Time-based Media

- [ ] Videos have captions
- [ ] Audio has transcripts
- [ ] Live streams have real-time captions (AAA)

### 1.3 Adaptable

- [ ] Content structure conveyed through semantics
- [ ] Reading order makes sense when CSS disabled
- [ ] Instructions don't rely solely on sensory characteristics

### 1.4 Distinguishable

- [ ] Color is not the only visual means of conveying info
- [ ] Text contrast ratio ≥ 4.5:1 (3:1 for large text)
- [ ] Text resizable to 200% without loss of functionality
- [ ] No horizontal scrolling at 320px width

## Operable

### 2.1 Keyboard Accessible

- [ ] All functionality available via keyboard
- [ ] No keyboard traps
- [ ] Single-key shortcuts can be disabled/remapped

### 2.2 Enough Time

- [ ] Time limits can be turned off, adjusted, or extended
- [ ] Moving content can be paused, stopped, or hidden
- [ ] No time limits on reading (AAA)

### 2.3 Seizures and Physical Reactions

- [ ] No content flashes more than 3 times per second

### 2.4 Navigable

- [ ] Skip navigation link provided
- [ ] Pages have descriptive titles
- [ ] Focus order is logical
- [ ] Link purpose clear from link text
- [ ] Multiple ways to find pages
- [ ] Headings and labels descriptive
- [ ] Focus visible

### 2.5 Input Modalities

- [ ] Target size ≥ 44×44px
- [ ] Pointer gestures have alternatives
- [ ] Motion-activated features can be disabled

## Understandable

### 3.1 Readable

- [ ] Page language specified (`lang` attribute)
- [ ] Language of parts specified when different

### 3.2 Predictable

- [ ] No unexpected context changes on focus
- [ ] No unexpected context changes on input
- [ ] Consistent navigation
- [ ] Consistent identification of components

### 3.3 Input Assistance

- [ ] Error identification: errors described in text
- [ ] Labels or instructions for user input
- [ ] Error suggestions provided
- [ ] Error prevention for legal/financial (reversible, checked, confirmed)

## Robust

### 4.1 Compatible

- [ ] Valid HTML (no duplicate IDs, proper nesting)
- [ ] Name, role, value available for custom components
- [ ] Status messages programmatically determinable

## Testing Tools

```bash
# Automated testing
npx @axe-core/cli https://localhost:3000

# Browser extensions
# - axe DevTools
# - WAVE
# - Lighthouse

# Screen readers
# - VoiceOver (Mac): Cmd+F5
# - NVDA (Windows): Free download
# - JAWS (Windows): Commercial
```

## Contrast Checkers

- APCA (preferred): https://apcacontrast.com/
- WebAIM: https://webaim.org/resources/contrastchecker/
