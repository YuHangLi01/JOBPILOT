import type { MemoryContextForJobAnalysis } from '../types';

/**
 * 进入 LLM 的轻量记忆视图（已结构化 + 便于截断，避免把整段表格原文塞进 Prompt）
 */
export interface LightMemoryPromptContext {
  /** 用户目标岗位 / 方向 */
  target_roles?: string[];
  /** 画像核心技能 */
  core_skill_tags?: string[];
  /** 画像薄弱技能 */
  weak_skill_tags?: string[];
  /** 历史高频技能缺口（标签） */
  recurring_gap_tags?: string[];
  /** 薄弱项总结（单行截断） */
  weak_points_one_liner?: string;
  /** 与当前 JD 相近的历史岗位（每行已截断） */
  similar_job_lines?: string[];
  /** 近期行动备忘（单行截断） */
  action_hint_one_liner?: string;
  /** 求职阶段 / 偏好提示（如职级偏好、约束摘要压缩） */
  job_search_stage_hint?: string;
}

const MAX_TAGS = 10;
const MAX_SIMILAR_LINES = 3;
const MAX_LINE_CHARS = 96;
const MAX_WEAK_CHARS = 160;
const MAX_ACTION_CHARS = 120;

function clip(s: string, max: number): string {
  const t = s.replace(/\s+/g, ' ').trim();
  if (!t) return '';
  return t.length <= max ? t : `${t.slice(0, max)}…`;
}

function takeUnique(tags: string[] | undefined, max: number): string[] {
  if (!tags?.length) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of tags) {
    const t = raw.trim();
    if (!t || seen.has(t)) continue;
    seen.add(t);
    out.push(t);
    if (out.length >= max) break;
  }
  return out;
}

function mergeGapTags(ctx: MemoryContextForJobAnalysis): string[] {
  const freq = new Map<string, number>();
  const bump = (arr: string[] | undefined) => {
    for (const t of arr ?? []) {
      const k = t.trim();
      if (!k) continue;
      freq.set(k, (freq.get(k) ?? 0) + 1);
    }
  };
  bump(ctx.summary?.top_skill_gap_tags);
  for (const r of ctx.recent_job_records) bump(r.gap_skill_tags);
  return [...freq.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, MAX_TAGS)
    .map(([k]) => k);
}

function isLightMemoryEmpty(m: LightMemoryPromptContext): boolean {
  return (
    !m.target_roles?.length &&
    !m.core_skill_tags?.length &&
    !m.weak_skill_tags?.length &&
    !m.recurring_gap_tags?.length &&
    !m.weak_points_one_liner &&
    !m.similar_job_lines?.length &&
    !m.action_hint_one_liner &&
    !m.job_search_stage_hint
  );
}

/**
 * 从编排层拉取到的记忆上下文，裁剪为 Prompt 专用结构；无可展示内容时返回 null（调用方即无记忆块）
 */
export function buildLightMemoryFromAnalysis(ctx: MemoryContextForJobAnalysis): LightMemoryPromptContext | null {
  const p = ctx.profile;
  const s = ctx.summary;

  const similar_job_lines = ctx.similar_job_records.slice(0, MAX_SIMILAR_LINES).map((r) => {
    const tags = takeUnique(r.skill_tags, 6).join('、') || '—';
    const line = `${r.job_title}｜技能：${tags}`;
    return clip(line, MAX_LINE_CHARS);
  });

  const stageParts: string[] = [];
  if (p?.seniority_preference) stageParts.push(`职级偏好：${p.seniority_preference}`);
  if (p?.constraints_summary) stageParts.push(clip(p.constraints_summary, 80));

  const out: LightMemoryPromptContext = {
    target_roles: takeUnique(p?.target_roles, 6),
    core_skill_tags: takeUnique(p?.core_skill_tags, MAX_TAGS),
    weak_skill_tags: takeUnique(p?.weak_skill_tags, 8),
    recurring_gap_tags: mergeGapTags(ctx),
    weak_points_one_liner: s?.weak_points_summary ? clip(s.weak_points_summary, MAX_WEAK_CHARS) : undefined,
    similar_job_lines: similar_job_lines.length ? similar_job_lines : undefined,
    action_hint_one_liner: s?.action_plan_summary ? clip(s.action_plan_summary, MAX_ACTION_CHARS) : undefined,
    job_search_stage_hint: stageParts.length ? clip(stageParts.join('；'), MAX_LINE_CHARS) : undefined,
  };

  return isLightMemoryEmpty(out) ? null : out;
}

type LightMemoryVariant = 'summary' | 'resume' | 'interview';

const BASE_RULE = `【记忆使用规则】以下为该用户的轻量记忆摘要，用于**个性化**与**可执行**输出。
- **禁止**逐字复述或轻微改写下列历史措辞；须结合**本次 JD** 产出**新的**句子与结论。
- 记忆与本次 JD **冲突**或**证据不足**时，**以本次 JD 为准**，不要编造用户经历。
- 控制篇幅：记忆只作辅助，不要喧宾夺主。`;

const VARIANT_HINT: Record<LightMemoryVariant, string> = {
  summary:
    '总结仍以岗位本身为主；记忆仅用于微调「适合人群 / 投递强调点」等 1~2 处表述，且须与本次 JD 一致。',
  resume:
    '每条建议须具体、可改简历（动词+对象+结果）；不要输出与历史建议同义的重复句。',
  interview:
    '题目与考察点须紧扣本 JD；若引用用户薄弱项，用**新的问法**考察能力，勿复述历史题库句式。',
};

function lines(label: string, items: string[] | undefined, bullet = '-'): string {
  if (!items?.length) return '';
  return `${label}\n${items.map((x) => `${bullet} ${x}`).join('\n')}`;
}

/**
 * 将结构化记忆渲染为可嵌入 Prompt 的片段；memory 为 null/undefined 时返回空串（优雅降级）
 */
export function formatLightMemoryBlock(
  memory: LightMemoryPromptContext | null | undefined,
  variant: LightMemoryVariant,
): string {
  if (!memory || isLightMemoryEmpty(memory)) {
    return '';
  }

  const chunks: string[] = [
    BASE_RULE,
    `【本任务侧重】${VARIANT_HINT[variant]}`,
    lines('【目标岗位】', memory.target_roles),
    lines('【技能画像 · 核心】', memory.core_skill_tags),
    lines('【技能画像 · 薄弱】', memory.weak_skill_tags),
    lines('【历史常见缺口（标签）】', memory.recurring_gap_tags),
  ];

  if (memory.weak_points_one_liner) {
    chunks.push(`【薄弱项总结】\n- ${memory.weak_points_one_liner}`);
  }
  if (memory.similar_job_lines?.length) {
    chunks.push(lines('【最近相似岗位（仅标题+技能提示）】', memory.similar_job_lines));
  }
  if (memory.action_hint_one_liner) {
    chunks.push(`【行动备忘（勿复述，仅作方向）】\n- ${memory.action_hint_one_liner}`);
  }
  if (memory.job_search_stage_hint) {
    chunks.push(`【求职阶段 / 约束提示】\n- ${memory.job_search_stage_hint}`);
  }

  const body = chunks.filter(Boolean).join('\n\n');
  // 总硬上限，防止极端宽表撑爆上下文
  const MAX_BLOCK = 1400;
  const text = body.length > MAX_BLOCK ? `${body.slice(0, MAX_BLOCK)}…` : body;
  return `\n## 轻量记忆上下文（可选）\n${text}\n`;
}
