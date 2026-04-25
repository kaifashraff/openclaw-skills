# Laqab SEO Optimization Plan

**Created:** 2026-04-25 11:45 UTC
**Author:** JARVIS (Laqab CEO)

---

## SEO Strategy for Laqab

### Target Keywords (By Priority)

**Primary Keywords (High Intent, Transactional)**
| Keyword | Monthly Searches (Est.) | Competition | Priority |
|---------|------------------------|-------------|----------|
| hand embroidered sherwani | 1,000-2,000 | Medium | 🔴 HIGH |
| zari sherwani price | 500-1,000 | Low | 🔴 HIGH |
| custom sherwani ahmedabad | 200-500 | Low | 🔴 HIGH |
| hand embroidery sherwani | 500-1,000 | Medium | 🔴 HIGH |
| sherwani for wedding | 1,000-2,000 | High | 🟡 MEDIUM |

**Secondary Keywords (Informational, Nurturing)**
| Keyword | Monthly Searches (Est.) | Competition | Priority |
|---------|------------------------|-------------|----------|
| how to identify hand embroidery | 300-500 | Low | 🟡 MEDIUM |
| difference hand embroidered vs machine | 200-300 | Low | 🟡 MEDIUM |
| best sherwani for grooms | 500-800 | Medium | 🟡 MEDIUM |
| zari work process | 100-200 | Low | 🟢 LOW |

**Long-Tail Keywords (Low Competition)**
| Keyword | Monthly Searches (Est.) | Competition | Priority |
|---------|------------------------|-------------|----------|
| hand embroidered sherwani under 15000 | 100-200 | Low | 🟢 LOW |
| gold zari sherwani for reception | 100-200 | Low | 🟢 LOW |
| custom designed sherwani 25 days delivery | 50-100 | Low | 🟢 LOW |

---

## On-Page SEO Improvements

### 1. Meta Tags (app/layout.tsx)

Current:
```
title: 'LAQAB | Premium Ethnic Menswear - Sherwani, Kurta, Wedding Wear'
description: 'Discover exquisite ethnic menswear at LAQAB...'
```

Proposed:
```
title: 'Hand Embroidered Sherwani & Ethnic Wear | LAQAB - Ahmedabad'
description: 'Premium hand embroidered sherwani, kurta, bandhgala by skilled karigars. Custom orders available. 15-25 days delivery. Shop now.'
```

### 2. Product Page SEO (app/products/[slug]/page.tsx)

Add structured data / Schema markup:
- Product schema with price, availability, reviews
- Organization schema
- LocalBusiness schema (for Google Business)

### 3. Homepage SEO

Add meta keywords to homepage (hidden but recognized):
```html
<meta name="keywords" content="hand embroidered sherwani, zari work, ethnic menswear, wedding sherwani, custom sherwani, Ahmedabad, India, karigar, handcraft" />
```

### 4. Image Alt Tags

All product images should have descriptive alt text:
```
Current: alt={product.name}
Proposed: alt={`Hand Embroidered ${product.name} by LAQAB - ${product.work}`}
```

### 5. Internal Linking

Add links between related products/collections to boost SEO:
- Product pages → Related products
- Collections → Featured products
- About page → Products (craftsmanship story)

---

## Local SEO (Google Business)

### Google Business Profile Optimization

**Business Name:** LAQAB - Hand Embroidered Ethnic Wear

**Categories:**
- Primary: Clothing Store
- Secondary: Ethnic Wear Store, Wedding Dress Shop

**Attributes:**
- "Handmade" ✓
- "Indian-owned business" ✓
- "Women-led" (if applicable)

**Photos to Add:**
1. Product photos (10+)
2. Team/karigar photos
3. Workshop/workspace photos
4. Packaging photos

**Posts:** Update weekly with:
- New product launches
- Behind-the-scenes content
- Customer testimonials
- Festival offers

---

## Content SEO Strategy

### Blog/Content Ideas (for website)

1. **"How to Identify Real Hand Embroidery: A Complete Guide"**
   - Target keyword: "how to identify hand embroidery"
   - Length: 1,500+ words
   - CTA: Custom order inquiry

2. **"Wedding Sherwani Guide 2026: Styles, Trends, and Tips"**
   - Target keyword: "best sherwani for wedding"
   - Include trend predictions, color guide, styling tips

3. **"The Art of Zari: Traditional Craftsmanship in Modern Fashion"**
   - Target keyword: "zari work process"
   - Storytelling angle, craftsmanship focus

4. **"Custom vs Ready-Made Sherwani: Which is Right for You?"**
   - Target keyword: "custom sherwani"
   - Comparison, benefits of each

5. **"Caring for Your Hand Embroidered Sherwani: A Complete Guide"**
   - Target keyword: "hand embroidered sherwani care"
   - Maintenance tips, storage guide

### Content Calendar

| Month | Content Focus | SEO Target |
|-------|--------------|------------|
| May | Wedding prep, custom orders | "wedding sherwani" |
| June | Monsoon care, festival prep | "hand embroidery care" |
| July-Aug | Festival season | "festive sherwani" |
| Sept-Oct | Wedding season starts | "wedding sherwani 2026" |
| Nov-Dec | Peak season | "custom sherwani" |

---

## Technical SEO

### Website Speed Optimization

1. **Image Optimization**
   - Use next/image with proper sizing
   - Compress product images (WebP format)
   - Lazy load below-fold images

2. **Core Web Vitals Targets**
   - LCP (Largest Contentful Paint): < 2.5s
   - FID (First Input Delay): < 100ms
   - CLS (Cumulative Layout Shift): < 0.1

3. **Mobile Optimization**
   - Test on mobile-first
   - Touch targets 48px minimum
   - Font size readable on mobile

### URL Structure

Current: `/products/royal-gold-embroidered-sherwani`
Good: `/products/royal-gold-embroidered-sherwani` ✓

For collections: `/collections/wedding-special` ✓

---

## Link Building Strategy

### Backlinks to Target

1. **Wedding vendor directories**
   - WeddingWire India
   - ShaadiCraft
   - WeddingUstaad

2. **Local business directories**
   - JustDial
   - Sulekha
   - IndiaMart

3. **Fashion/style blogs**
   - Outreach to Indian fashion bloggers
   - Guest post opportunities

4. **Social media cross-links**
   - Link Instagram → Website
   - Link WhatsApp → Website
   - YouTube description → Website

---

## SEO Checklist (Priority Order)

- [ ] Update meta title and description in layout.tsx
- [ ] Add meta keywords tag
- [ ] Add alt tags to all product images
- [ ] Create Google Business profile
- [ ] Add Schema markup (JSON-LD)
- [ ] Write first blog post: "How to Identify Real Hand Embroidery"
- [ ] Submit to Google Search Console
- [ ] Create social profiles (Instagram, Pinterest)
- [ ] Submit to local directories (JustDial, Sulekha)
- [ ] Build 5+ backlinks from wedding directories

---

## Quick Wins (Today)

1. **Meta tags update** (15 min) → layout.tsx
2. **Image alt tags** (10 min) → products/[slug] + ProductDetailClient
3. **Google Business setup guide** (already done in LAQAB_OPERATIONS.md)
4. **First blog post draft** (30 min)

---

**SEO is a long-term investment. Focus on quality content + local SEO first.**

🤖⚡