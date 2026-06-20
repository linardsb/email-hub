import { describe, it, expect, beforeAll } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import postcss from 'postcss';

const __dirname = dirname(fileURLToPath(import.meta.url));

const TEMPLATE_DIR = resolve(__dirname, '../../app/ai/templates/library');
function loadTemplate(name) {
  return readFileSync(resolve(TEMPLATE_DIR, `${name}.html`), 'utf-8');
}

describe('isPreCompiledEmail', () => {
  let isPreCompiledEmail;

  beforeAll(async () => {
    const mod = await import('./precompiled-detect.js');
    isPreCompiledEmail = mod.isPreCompiledEmail;
  });

  it('detects golden templates as pre-compiled', () => {
    const html = loadTemplate('promotional_hero');
    expect(isPreCompiledEmail(html)).toBe(true);
  });

  it('detects multiple golden templates as pre-compiled', () => {
    for (const name of ['newsletter_2col', 'transactional_receipt', 'minimal_text']) {
      expect(isPreCompiledEmail(loadTemplate(name))).toBe(true);
    }
  });

  it('rejects Maizzle template source', () => {
    const maizzle = `<extends src="layouts/default.html"><block name="content"><p>Hello</p></block></extends>`;
    expect(isPreCompiledEmail(maizzle)).toBe(false);
  });

  it('rejects HTML with <x- custom tags', () => {
    const source = `<!DOCTYPE html><html><body><x-header>Logo</x-header></body></html>`;
    expect(isPreCompiledEmail(source)).toBe(false);
  });

  it('rejects plain HTML without inline styles', () => {
    const source = `<!DOCTYPE html><html><body><table role="presentation"><tr><td>Hi</td></tr></table><table role="presentation"><tr><td>Bye</td></tr></table></body></html>`;
    expect(isPreCompiledEmail(source)).toBe(false);
  });

  it('rejects HTML fragment without document shell', () => {
    const source = `<table role="presentation" cellpadding="0"><tr><td style="color:red">A</td></tr></table><table role="presentation" cellpadding="0"><tr><td style="padding:10px">B</td></tr></table><p style="margin:0">C</p>`;
    expect(isPreCompiledEmail(source)).toBe(false);
  });

  it('rejects HTML without table layout', () => {
    const source = `<!DOCTYPE html><html><body><div style="color:red">A</div><div style="padding:10px">B</div><p style="margin:0">C</p></body></html>`;
    expect(isPreCompiledEmail(source)).toBe(false);
  });
});

describe('postcss-email-optimize shorthand expansion', () => {
  let emailOptimize;

  beforeAll(async () => {
    const mod = await import('./postcss-email-optimize.js');
    emailOptimize = mod.default;
  });

  it('expands font shorthand into longhands', async () => {
    const css = '.test { font: 700 32px/40px Inter, sans-serif; }';
    const result = await postcss([emailOptimize()]).process(css, { from: undefined });
    expect(result.css).toContain('font-weight');
    expect(result.css).toContain('font-size');
    expect(result.css).toContain('font-family');
    expect(result.emailOptimization.shorthand_expansions).toBeGreaterThan(0);
  });

  it('expands padding shorthand into 4 longhands', async () => {
    const css = '.test { padding: 16px 32px; }';
    const result = await postcss([emailOptimize()]).process(css, { from: undefined });
    expect(result.css).toContain('padding-top');
    expect(result.css).toContain('padding-right');
    expect(result.css).toContain('padding-bottom');
    expect(result.css).toContain('padding-left');
  });

  it('preserves url with colon in background', async () => {
    const css = '.test { background: url(https://example.com/img.png) no-repeat; }';
    const result = await postcss([emailOptimize()]).process(css, { from: undefined });
    expect(result.css).toContain('https://example.com/img.png');
  });

  it('extracts responsive breakpoints from @media', async () => {
    const css = '@media (max-width: 600px) { .mobile { font-size: 14px; } }';
    const result = await postcss([emailOptimize()]).process(css, { from: undefined });
    expect(result.emailOptimization.responsive).toContain('600px');
    // @media rule is preserved
    expect(result.css).toContain('@media');
  });

  it('reports shorthand expansions count', async () => {
    const css = '.a { margin: 10px; } .b { padding: 5px 10px; }';
    const result = await postcss([emailOptimize()]).process(css, { from: undefined });
    expect(result.emailOptimization.shorthand_expansions).toBeGreaterThanOrEqual(8);
  });
});

describe('compileMjml', () => {
  let compileMjml;
  let mjmlVersion;

  beforeAll(async () => {
    const mod = await import('./mjml-compile.js');
    compileMjml = mod.compileMjml;
    mjmlVersion = mod.mjmlVersion;
  });

  it('compiles valid MJML to HTML with table layout', () => {
    const result = compileMjml(
      '<mjml><mj-body><mj-section><mj-column><mj-text>Hello</mj-text></mj-column></mj-section></mj-body></mjml>',
    );
    expect(result.html).toContain('<table');
    expect(result.html).toContain('Hello');
    expect(result.errors).toEqual([]);
  });

  it('returns errors for unknown MJML tags', () => {
    const result = compileMjml(
      '<mjml><mj-body><mj-section><mj-column><mj-unknown>Bad</mj-unknown></mj-column></mj-section></mj-body></mjml>',
    );
    expect(result.errors.length).toBeGreaterThan(0);
    expect(result.errors[0]).toHaveProperty('message');
    // Still produces HTML output despite errors (soft validation)
    expect(result.html).toBeDefined();
  });

  it('generates MSO conditionals for Outlook', () => {
    const result = compileMjml(
      '<mjml><mj-body><mj-section><mj-column><mj-text>Outlook test</mj-text></mj-column></mj-section></mj-body></mjml>',
    );
    expect(result.html).toContain('<!--[if mso');
  });

  it('compiles multi-column layout to responsive table', () => {
    const result = compileMjml(`
      <mjml><mj-body><mj-section>
        <mj-column><mj-text>Left</mj-text></mj-column>
        <mj-column><mj-text>Right</mj-text></mj-column>
      </mj-section></mj-body></mjml>
    `);
    expect(result.html).toContain('Left');
    expect(result.html).toContain('Right');
    // Two columns produce table-based layout
    expect(result.html).toContain('<table');
    expect(result.errors).toEqual([]);
  });

  it('exports a valid semver version string', () => {
    expect(mjmlVersion).toMatch(/^\d+\.\d+\.\d+/);
  });
});

// Guards the Maizzle 6 build/preview render path. Maizzle 6 replaced the
// monolithic render() (now Vue-SFC oriented) with standalone transformers;
// the sidecar composes inlineCss + minify (build) and inlineCss + format
// (preview). CI does not boot the sidecar, so these assert the transformer
// contract the /build and /preview handlers depend on.
describe('Maizzle 6 CSS transformers (build/preview render path)', () => {
  let inlineCss, minify, format;

  beforeAll(async () => {
    const mod = await import('@maizzle/framework');
    inlineCss = mod.inlineCss;
    minify = mod.minify;
    format = mod.format;
  });

  it('inlines a <style> rule onto matching elements (build path)', () => {
    const html = `<!DOCTYPE html><html><head><style>.x{color:red}</style></head><body><table role="presentation"><tr><td class="x">Hi</td></tr></table></body></html>`;
    const out = minify(inlineCss(html), { collapseWhitespace: true, removeComments: true });
    expect(out).toMatch(/<td[^>]*style="[^"]*color:\s*red/);
  });

  it('preserves MSO conditional comments through minify', () => {
    const html = `<!DOCTYPE html><html><head><style>.x{color:red}</style></head><body><!--[if mso]><table><tr><td>mso</td></tr></table><![endif]--><table role="presentation"><tr><td class="x">Hi</td></tr></table></body></html>`;
    const out = minify(inlineCss(html), { collapseWhitespace: true, removeComments: true });
    expect(out).toContain('<!--[if mso]>');
  });

  it('inlines + prettifies without throwing (preview path)', async () => {
    const html = `<!DOCTYPE html><html><head><style>.x{color:red}</style></head><body><table role="presentation"><tr><td class="x">Hi</td></tr></table></body></html>`;
    const out = await format(inlineCss(html));
    expect(out).toMatch(/<td[^>]*style="[^"]*color:\s*red/);
  });
});
