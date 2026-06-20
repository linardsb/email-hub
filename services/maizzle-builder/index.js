/**
 * Maizzle Builder Service
 *
 * Express server that receives email template source + config via HTTP,
 * runs CSS optimization (PostCSS email plugin + Lightning CSS) then
 * Maizzle's build programmatically, and returns compiled HTML.
 *
 * Called by the FastAPI backend (app/email_engine/) via HTTP POST.
 */

import express from "express";
import { inlineCss, minify, format } from "@maizzle/framework";
import postcss from "postcss";
import emailOptimize, { loadOntology } from "./postcss-email-optimize.js";
import { transform } from "lightningcss";
import { isPreCompiledEmail } from "./precompiled-detect.js";
import { compileMjml, mjmlVersion } from "./mjml-compile.js";
import { parseDocument } from "htmlparser2";
import { findAll } from "domutils";
import render_dom from "dom-serializer";

const app = express();
const PORT = process.env.PORT || 3001;
app.use(express.json({ limit: "5mb" }));

let ontologyVersion = null;
try {
  ontologyVersion = loadOntology().version;
  console.log(`Ontology loaded: ${ontologyVersion}`);
} catch (err) {
  console.warn(`Ontology not loaded: ${err.message}`);
}

async function optimizeCss(html, targetClients) {
  const MSO_RE = /<!--\[if\s+mso.*?\]>.*?<!\[endif\]-->/gis;
  const msoMap = new Map();
  let idx = 0;
  let safe = html;
  for (const m of html.matchAll(MSO_RE)) {
    const ph = `__MSO_${idx++}__`;
    msoMap.set(ph, m[0]);
    safe = safe.replace(m[0], ph);
  }

  const STYLE_RE = /<style[^>]*>([\s\S]*?)<\/style>/gi;
  const blocks = [];
  let match;
  while ((match = STYLE_RE.exec(safe)) !== null) blocks.push(match[1]);

  if (!blocks.length) {
    for (const [ph, orig] of msoMap) safe = safe.replace(ph, orig);
    return { optimizedHtml: safe, optimization: { removed_properties: [], conversions: [], warnings: [], original_css_size: 0, optimized_css_size: 0 } };
  }

  const allRemoved = [], allConversions = [], allWarnings = [];
  let origSize = 0, optSize = 0;
  const optimized = [];

  for (const css of blocks) {
    origSize += Buffer.byteLength(css, 'utf-8');
    const r = await postcss([emailOptimize({ targetClients })]).process(css, { from: undefined });
    let out = r.css;
    try { out = transform({ filename: 'email.css', code: Buffer.from(out), minify: true }).code.toString(); } catch { /* minification is best-effort */ }
    optSize += Buffer.byteLength(out, 'utf-8');
    optimized.push(out);
    if (r.emailOptimization) {
      allRemoved.push(...r.emailOptimization.removed_properties);
      allConversions.push(...r.emailOptimization.conversions);
      allWarnings.push(...r.emailOptimization.warnings);
    }
  }

  let bi = 0;
  let result = safe.replace(STYLE_RE, () => `<style>${optimized[bi++] || ''}</style>`);
  for (const [ph, orig] of msoMap) result = result.replace(ph, orig);

  return { optimizedHtml: result, optimization: { removed_properties: allRemoved, conversions: allConversions, warnings: allWarnings, original_css_size: origSize, optimized_css_size: optSize } };
}

async function optimizeInlineStyles(html, targetClients) {
  const dom = parseDocument(html, { decodeEntities: false });
  const elements = [];
  let idx = 0;
  findAll((node) => {
    if (node.attribs && node.attribs.style) {
      elements.push({ node, index: idx++ });
      return true;
    }
    return false;
  }, dom.children);

  if (elements.length === 0) {
    return { html, inline_removed: [], inline_conversions: [], shorthand_expansions: 0, responsive: [] };
  }

  // Build synthetic stylesheet from inline styles
  const rules = elements.map(({ node, index: i }) =>
    `.__inline_${i} { ${node.attribs.style} }`
  ).join('\n');

  // Run through PostCSS with ontology plugin
  const result = await postcss([emailOptimize({ targetClients })])
    .process(rules, { from: 'inline-styles.css' });

  // Extract processed declarations back to elements
  result.root.walkRules((rule) => {
    const match = rule.selector.match(/__inline_(\d+)/);
    if (!match) return;
    const i = parseInt(match[1], 10);
    const el = elements.find(e => e.index === i);
    if (!el) return;
    const decls = [];
    rule.walkDecls((decl) => decls.push(`${decl.prop}: ${decl.value}`));
    el.node.attribs.style = decls.join('; ');
  });

  const optimizedHtml = render_dom(dom, { decodeEntities: false });
  const opt = result.emailOptimization || {};

  return {
    html: optimizedHtml,
    inline_removed: opt.removed_properties || [],
    inline_conversions: opt.conversions || [],
    shorthand_expansions: opt.shorthand_expansions || 0,
    responsive: opt.responsive || [],
  };
}

app.get("/health", (_req, res) => {
  res.json({ status: "healthy", service: "maizzle-builder", ontology_version: ontologyVersion, mjml_version: mjmlVersion });
});

app.post("/build", async (req, res) => {
  const start = Date.now();
  const { source, production = false, target_clients } = req.body;
  if (!source) return res.status(400).json({ error: "source is required" });

  try {
    let html = source;
    let optimization = null;
    if (ontologyVersion && target_clients?.length) {
      const r = await optimizeCss(html, target_clients);
      html = r.optimizedHtml;
      optimization = r.optimization;
    }

    const passthrough = isPreCompiledEmail(html);

    if (passthrough) {
      // Optimize inline styles on passthrough emails
      if (ontologyVersion && target_clients?.length) {
        const inlineResult = await optimizeInlineStyles(html, target_clients);
        html = inlineResult.html;
        if (optimization) {
          optimization.removed_properties.push(...inlineResult.inline_removed);
          optimization.conversions.push(...inlineResult.inline_conversions);
          optimization.shorthand_expansions = (optimization.shorthand_expansions || 0) + inlineResult.shorthand_expansions;
          optimization.responsive = [...(optimization.responsive || []), ...inlineResult.responsive];
        } else {
          optimization = {
            removed_properties: inlineResult.inline_removed,
            conversions: inlineResult.inline_conversions,
            warnings: [],
            shorthand_expansions: inlineResult.shorthand_expansions,
            responsive: inlineResult.responsive,
            original_css_size: 0,
            optimized_css_size: 0,
          };
        }
      }
      res.json({
        html,
        build_time_ms: Date.now() - start,
        passthrough: true,
        ...(optimization && { optimization }),
      });
      return;
    }

    // Maizzle 6 replaced the monolithic render() (now Vue-SFC oriented) with
    // standalone transformers. The sidecar only needs CSS inlining + minify on
    // already-assembled HTML, so compose those directly. Non-production builds
    // skip inlining, matching the old default render() behaviour.
    let compiled = html;
    if (production) {
      compiled = minify(inlineCss(html), { collapseWhitespace: true, removeComments: true });
    }
    res.json({
      html: compiled,
      build_time_ms: Date.now() - start,
      passthrough: false,
      ...(optimization && { optimization }),
    });
  } catch (err) {
    console.error("Build failed:", err.message);
    res.status(500).json({ error: "Build failed", detail: err.message, build_time_ms: Date.now() - start });
  }
});

app.post("/preview", async (req, res) => {
  const start = Date.now();
  const { source, target_clients } = req.body;
  if (!source) return res.status(400).json({ error: "source is required" });

  try {
    let html = source;
    let optimization = null;
    if (ontologyVersion && target_clients?.length) {
      const r = await optimizeCss(html, target_clients);
      html = r.optimizedHtml;
      optimization = r.optimization;
    }

    const passthrough = isPreCompiledEmail(html);

    if (passthrough) {
      if (ontologyVersion && target_clients?.length) {
        const inlineResult = await optimizeInlineStyles(html, target_clients);
        html = inlineResult.html;
        if (optimization) {
          optimization.removed_properties.push(...inlineResult.inline_removed);
          optimization.conversions.push(...inlineResult.inline_conversions);
          optimization.shorthand_expansions = (optimization.shorthand_expansions || 0) + inlineResult.shorthand_expansions;
          optimization.responsive = [...(optimization.responsive || []), ...inlineResult.responsive];
        } else {
          optimization = {
            removed_properties: inlineResult.inline_removed,
            conversions: inlineResult.inline_conversions,
            warnings: [],
            shorthand_expansions: inlineResult.shorthand_expansions,
            responsive: inlineResult.responsive,
            original_css_size: 0,
            optimized_css_size: 0,
          };
        }
      }
      res.json({
        html,
        build_time_ms: Date.now() - start,
        passthrough: true,
        ...(optimization && { optimization }),
      });
      return;
    }

    const compiled = await format(inlineCss(html));
    res.json({
      html: compiled,
      build_time_ms: Date.now() - start,
      passthrough: false,
      ...(optimization && { optimization }),
    });
  } catch (err) {
    console.error("Preview failed:", err.message);
    res.status(500).json({ error: "Preview failed", detail: err.message, build_time_ms: Date.now() - start });
  }
});

app.post("/compile-mjml", async (req, res) => {
  const start = Date.now();
  const { mjml, options = {}, target_clients } = req.body;

  if (!mjml || typeof mjml !== "string") {
    return res.status(400).json({ error: "mjml field is required and must be a string" });
  }

  try {
    const result = compileMjml(mjml, options);

    let html = result.html;
    let optimization = null;

    if (ontologyVersion && target_clients?.length) {
      const r = await optimizeCss(html, target_clients);
      html = r.optimizedHtml;
      optimization = r.optimization;
    }

    res.json({
      html,
      errors: result.errors || [],
      build_time_ms: Date.now() - start,
      ...(optimization && { optimization }),
    });
  } catch (err) {
    console.error("MJML compilation failed:", err.message);
    res.status(500).json({
      error: "MJML compilation failed",
      detail: err.message,
      build_time_ms: Date.now() - start,
    });
  }
});

app.listen(PORT, () => console.log(`Maizzle builder listening on port ${PORT}`));
