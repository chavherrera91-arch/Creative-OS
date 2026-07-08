import type { Campaign } from "../types";

export function campaignToMarkdown(c: Campaign): string {
  const L: string[] = [];
  const h = (t: string) => L.push(`\n## ${t}\n`);
  const li = (t: string) => L.push(`- ${t}`);

  L.push(`# Campaña Creativa — ${c.input.name}`);
  L.push(`\n> Generado por Creative OS · ${new Date(c.createdAt).toLocaleDateString("es")} · Motor: ${c.generatedBy === "claude" ? "Claude AI" : "Local"}`);
  if (c.input.sourceUrl) L.push(`> Origen: ${c.input.sourceUrl}`);

  h("Creative Score");
  L.push(`**${c.score.total}/100** — ${c.score.verdict}`);
  c.score.metrics.forEach((m) => li(`${m.label}: ${"★".repeat(m.stars)}${"☆".repeat(5 - m.stars)} — ${m.note}`));
  c.score.platforms.forEach((p) => li(`${p.name}: ${p.score}/10 — ${p.note}`));

  h("1. Product Intelligence");
  L.push(`**Problema:** ${c.intelligence.problem}`);
  L.push(`\n**Problemas secundarios:**`);
  c.intelligence.secondaryProblems.forEach(li);
  L.push(`\n**Beneficios:**`);
  c.intelligence.benefits.forEach(li);
  L.push(`\n**Audiencias:**`);
  c.intelligence.audiences.forEach((a) => li(`**${a.name}** — ${a.description}. Dolores: ${a.pains.join("; ")}`));
  L.push(`\n**Ángulos de venta:**`);
  c.intelligence.angles.forEach((a) => li(`**${a.name}** (${a.emotion}): ${a.description} Big idea: ${a.bigIdea}`));
  L.push(`\n**Objeciones:**`);
  c.intelligence.objections.forEach((o) => li(`${o.objection} → ${o.response}`));
  L.push(`\n**Diferenciadores:**`);
  c.intelligence.differentiators.forEach(li);
  L.push(`\n**Precio:** ${c.intelligence.pricing.recommended} (${c.intelligence.pricing.range})`);
  L.push(c.intelligence.pricing.strategy);
  L.push(`\n**Escalado:** ${c.intelligence.scaling.level} — ${c.intelligence.scaling.reasoning}`);

  h("2. Hooks");
  c.hooks.forEach((g) => {
    L.push(`\n### ${g.emoji} ${g.category}`);
    g.items.forEach(li);
  });

  h("3. Anuncios (Ad Generator)");
  c.ads.forEach((a) => {
    L.push(`\n### ${a.title}`);
    L.push(`- **Plataforma:** ${a.platform} · **Formato:** ${a.format}`);
    L.push(`- **Texto principal:** ${a.primaryText.replace(/\n/g, " / ")}`);
    L.push(`- **Headline:** ${a.headline}`);
    L.push(`- **CTA:** ${a.cta}`);
    L.push(`- **Specs:** ${a.specs}`);
    L.push(`- **Notas:** ${a.notes}`);
  });

  h("4. Guiones (Script Generator)");
  c.scripts.forEach((s) => {
    L.push(`\n### [${s.duration}] ${s.title}`);
    L.push(`Hook: ${s.hook}`);
    s.beats.forEach((b) => li(`**${b.time} · ${b.label}** — VOZ: ${b.voiceover} | VISUAL: ${b.visual}`));
    L.push(`CTA: ${s.cta}`);
  });

  h("5. Storyboards (Visual Generator)");
  c.visualSets.forEach((v) => {
    L.push(`\n### ${v.title}`);
    L.push(v.concept);
    v.scenes.forEach((s) =>
      li(`**Escena ${s.n}** · Plano: ${s.shot} · Sujeto: ${s.subject} · Expresión: ${s.expression} · Luz: ${s.light} · Texto: "${s.text}" · Movimiento: ${s.movement} · Duración: ${s.duration} · Audio: ${s.audio}`)
    );
  });

  h("6. Prompts de imagen IA");
  c.imagePrompts.forEach((g) => {
    L.push(`\n### ${g.tool}`);
    g.prompts.forEach((p) => li(`**${p.title}** (${p.meta}): \`${p.prompt}\``));
  });

  h("7. Prompts de video IA");
  c.videoPrompts.forEach((g) => {
    L.push(`\n### ${g.tool}`);
    g.prompts.forEach((p) => li(`**${p.title}** (${p.meta}): \`${p.prompt}\``));
  });

  h("8. UGC Generator");
  c.ugc.forEach((u) => {
    L.push(`\n### ${u.emoji} ${u.persona}`);
    L.push(`- Perfil: ${u.profile}`);
    L.push(`- Tono: ${u.tone} · Setting: ${u.setting}`);
    L.push(`- Hook: ${u.hook}`);
    L.push(`- Guion: ${u.script}`);
  });

  h("9. Thumbnails");
  c.thumbnails.forEach((t) => li(`**${t.concept}** — "${t.headline}" · ${t.style} · Layout: ${t.layout}`));

  h("10. Landing Copy");
  L.push(`**Headline:** ${c.landing.headline}`);
  L.push(`**Subheadline:** ${c.landing.subheadline}`);
  L.push(`\n**Beneficios:**`);
  c.landing.benefits.forEach((b) => li(`**${b.title}**: ${b.text}`));
  L.push(`\n**FAQ:**`);
  c.landing.faq.forEach((f) => li(`**${f.q}** ${f.a}`));
  L.push(`\n**Garantía:** ${c.landing.guarantee}`);
  L.push(`\n**CTAs:** ${c.landing.ctas.join(" · ")}`);

  h("11. Ofertas (Offer Builder)");
  c.offers.forEach((o) => {
    L.push(`\n### ${o.type} — ${o.name}`);
    L.push(`${o.description}\n- Estructura: ${o.structure}\n- Ejemplo: ${o.example}\n- Ideal para: ${o.bestFor}`);
  });

  h("12. Creative Planner");
  c.planner.forEach((w) => {
    L.push(`\n### ${w.week}`);
    L.push(w.goal);
    w.items.forEach((i) => li(`**${i.count}× ${i.type}** [${i.platform}] (prioridad ${i.priority}) — ${i.notes}`));
  });

  h("13. Viral Predictor");
  L.push(`**Probabilidad: ${c.viral.probability}%** — ${c.viral.verdict}`);
  c.viral.factors.forEach((f) => li(`[${f.impact}] ${f.factor}: ${f.note}`));
  L.push(`\n**Recomendaciones:**`);
  c.viral.recommendations.forEach(li);

  h("14. A/B Testing");
  c.abTests.forEach((t) => {
    L.push(`\n### ${t.emoji} ${t.element} (${t.variants.length} variantes) — métrica: ${t.metric}`);
    t.variants.forEach(li);
  });

  h("15. Creative Library (búsquedas)");
  c.library.forEach((l) => li(`[${l.platform}] ${l.name}: ${l.url} — ${l.note}`));

  if (c.competitor) {
    h("16. Análisis de competidor");
    L.push(`URL: ${c.competitor.url}`);
    L.push(`Framework: ${c.competitor.framework}`);
    L.push(`Cómo ganarle:`);
    c.competitor.howToBeat.forEach(li);
  }

  return L.join("\n");
}

export function download(filename: string, content: string, mime = "text/plain") {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
