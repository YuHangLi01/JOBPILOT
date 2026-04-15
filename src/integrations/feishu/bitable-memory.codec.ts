/**
 * 求职记忆多维表格：TS 模型 ↔ 飞书单元格 编解码（与 constants 中列名一致）
 */
import type { JobRecordMemory, MemorySummaryRecord, UserProfileMemory } from '../../types';
import {
  JobType,
  MemoryDecision,
  MemoryPeriodKey,
  ProcessingStatus,
  SeniorityLevel,
  SimilarityBucket,
  WorkMode,
} from '../../types';

export function buildTextEqFilter(fieldName: string, value: string) {
  return {
    conjunction: 'and' as const,
    conditions: [{ field_name: fieldName, operator: 'is' as const, value: [value] }],
  };
}

export function buildUserAndPeriodFilter(fieldUser: string, userId: string, fieldPeriod: string, periodKey: string) {
  return {
    conjunction: 'and' as const,
    conditions: [
      { field_name: fieldUser, operator: 'is' as const, value: [userId] },
      { field_name: fieldPeriod, operator: 'is' as const, value: [periodKey] },
    ],
  };
}

/** 将内存模型 key 编码为飞书列名 → 单元格值（undefined/null 跳过，不覆盖为清空） */
export function encodeMemoryFields(
  fieldMap: Record<string, string>,
  data: Record<string, unknown>,
  options?: { joinArrayValues?: boolean },
): Record<string, unknown> {
  const fields: Record<string, unknown> = {};
  for (const [key, label] of Object.entries(fieldMap)) {
    let v = data[key];
    if (v === undefined || v === null) continue;
    if (options?.joinArrayValues && Array.isArray(v)) {
      v = (v as unknown[]).map(String).join('、');
    }
    fields[label] = v;
  }
  return fields;
}

export function rowKeysToObject(
  fieldMap: Record<string, string>,
  feishuFields: Record<string, unknown>,
): Record<string, unknown> {
  const labelToKey = Object.fromEntries(Object.entries(fieldMap).map(([k, v]) => [v, k]));
  const out: Record<string, unknown> = {};
  for (const [label, val] of Object.entries(feishuFields)) {
    const key = labelToKey[label];
    if (!key) continue;
    out[key] = val;
  }
  return out;
}

function readString(val: unknown): string | undefined {
  if (val === null || val === undefined) return undefined;
  if (typeof val === 'string') return val;
  if (typeof val === 'number' || typeof val === 'boolean') return String(val);
  return undefined;
}

function readNumber(val: unknown): number | undefined {
  if (typeof val === 'number' && Number.isFinite(val)) return val;
  if (typeof val === 'string') {
    const n = Number(val);
    return Number.isFinite(n) ? n : undefined;
  }
  return undefined;
}

function readStringArray(val: unknown): string[] | undefined {
  if (val === null || val === undefined) return undefined;
  if (typeof val === 'string') {
    const parts = val
      .split(/[,;，、\n\r]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    return parts.length ? parts : undefined;
  }
  if (!Array.isArray(val) || val.length === 0) return undefined;
  const out: string[] = [];
  for (const item of val) {
    if (typeof item === 'string') out.push(item);
    else if (item && typeof item === 'object' && 'text' in item) {
      const t = (item as { text?: unknown }).text;
      if (typeof t === 'string') out.push(t);
    }
  }
  return out.length ? out : undefined;
}

function readTimestamp(val: unknown): number | undefined {
  return readNumber(val);
}

function parseEnum<T extends string>(val: unknown, allowed: readonly T[]): T | undefined {
  const s = readString(val);
  if (!s) return undefined;
  return (allowed as readonly string[]).includes(s) ? (s as T) : undefined;
}

export function parseUserProfile(raw: Record<string, unknown>): UserProfileMemory | null {
  const user_id = readString(raw.user_id);
  const profile_version = readNumber(raw.profile_version);
  const updated_at = readTimestamp(raw.updated_at);
  if (!user_id || profile_version === undefined || updated_at === undefined) return null;
  return {
    user_id,
    profile_version,
    target_roles: readStringArray(raw.target_roles),
    target_industries: readStringArray(raw.target_industries),
    preferred_cities: readStringArray(raw.preferred_cities),
    work_mode: parseEnum(raw.work_mode, Object.values(WorkMode) as WorkMode[]),
    years_of_experience: readNumber(raw.years_of_experience),
    seniority_preference: parseEnum(
      raw.seniority_preference,
      Object.values(SeniorityLevel) as SeniorityLevel[],
    ),
    core_skill_tags: readStringArray(raw.core_skill_tags),
    weak_skill_tags: readStringArray(raw.weak_skill_tags),
    certifications: readString(raw.certifications),
    resume_focus_summary: readString(raw.resume_focus_summary),
    constraints_summary: readString(raw.constraints_summary),
    last_active_at: readTimestamp(raw.last_active_at),
    updated_at,
  };
}

export function parseJobRecord(raw: Record<string, unknown>): JobRecordMemory | null {
  const job_record_id = readString(raw.job_record_id);
  const user_id = readString(raw.user_id);
  const job_title = readString(raw.job_title);
  const jd_fingerprint = readString(raw.jd_fingerprint);
  const processing_status = parseEnum(
    raw.processing_status,
    Object.values(ProcessingStatus) as ProcessingStatus[],
  );
  const job_date = readTimestamp(raw.job_date);
  const created_at = readTimestamp(raw.created_at);
  const updated_at = readTimestamp(raw.updated_at);
  const skill_tags = readStringArray(raw.skill_tags) ?? [];
  if (!job_record_id || !user_id || !job_title || !jd_fingerprint || !processing_status) return null;
  if (job_date === undefined || created_at === undefined || updated_at === undefined) return null;
  return {
    job_record_id,
    user_id,
    job_date,
    company_name: readString(raw.company_name),
    job_title,
    location: readString(raw.location),
    job_type: parseEnum(raw.job_type, Object.values(JobType) as JobType[]),
    seniority: parseEnum(raw.seniority, Object.values(SeniorityLevel) as SeniorityLevel[]),
    skill_tags,
    matched_skill_tags: readStringArray(raw.matched_skill_tags),
    gap_skill_tags: readStringArray(raw.gap_skill_tags),
    fit_score: readNumber(raw.fit_score),
    decision: parseEnum(raw.decision, Object.values(MemoryDecision) as MemoryDecision[]),
    decision_reason_summary: readString(raw.decision_reason_summary),
    resume_advice_summary: readString(raw.resume_advice_summary),
    interview_focus_tags: readStringArray(raw.interview_focus_tags),
    similarity_bucket: parseEnum(
      raw.similarity_bucket,
      Object.values(SimilarityBucket) as SimilarityBucket[],
    ),
    similar_job_refs_json: readString(raw.similar_job_refs_json),
    jd_fingerprint,
    processing_status,
    error_code: readString(raw.error_code),
    error_message: readString(raw.error_message),
    created_at,
    updated_at,
  };
}

export function parseMemorySummary(raw: Record<string, unknown>): MemorySummaryRecord | null {
  const summary_id = readString(raw.summary_id);
  const user_id = readString(raw.user_id);
  const period_key = parseEnum(raw.period_key, Object.values(MemoryPeriodKey) as MemoryPeriodKey[]);
  const computed_at = readTimestamp(raw.computed_at);
  const source_record_count = readNumber(raw.source_record_count);
  const summary_version = readNumber(raw.summary_version);
  const updated_at = readTimestamp(raw.updated_at);
  if (!summary_id || !user_id || !period_key) return null;
  if (
    computed_at === undefined ||
    source_record_count === undefined ||
    summary_version === undefined ||
    updated_at === undefined
  ) {
    return null;
  }
  return {
    summary_id,
    user_id,
    period_key,
    computed_at,
    source_record_count,
    top_target_role_tags: readStringArray(raw.top_target_role_tags),
    top_skill_gap_tags: readStringArray(raw.top_skill_gap_tags),
    top_strength_tags: readStringArray(raw.top_strength_tags),
    weak_points_summary: readString(raw.weak_points_summary),
    recent_similar_job_advice: readString(raw.recent_similar_job_advice),
    action_plan_summary: readString(raw.action_plan_summary),
    evidence_job_ids_json: readString(raw.evidence_job_ids_json),
    summary_version,
    updated_at,
  };
}
