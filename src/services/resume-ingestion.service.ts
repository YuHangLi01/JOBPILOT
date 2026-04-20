import { PDFParse } from 'pdf-parse';
import { getLLMClient } from '../integrations/llm/client';
import { buildResumeProfileExtractPrompt } from '../prompts/resume-profile-extract.prompt';
import { profileMemoryService } from './profile-memory.service';
import { ResumeProfileExtractionSchema } from '../types';
import type {
  ResumeIngestionInput,
  ResumeIngestionResult,
  ResumeProfileExtraction,
  UpsertUserProfileInput,
} from '../types';
import { createLogger } from '../utils/logger';

const log = createLogger('ResumeIngestion');

function uniqueStrings(values: string[] | undefined, limit: number): string[] | undefined {
  if (!values?.length) return undefined;
  const seen = new Set<string>();
  const out: string[] = [];
  for (const value of values) {
    const normalized = value.trim();
    if (!normalized) continue;
    const key = normalized.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(normalized);
    if (out.length >= limit) break;
  }
  return out.length ? out : undefined;
}

function compactText(value: string | undefined, maxLen: number): string | undefined {
  const trimmed = value?.trim();
  if (!trimmed) return undefined;
  return trimmed.slice(0, maxLen);
}

function normalizeProfilePatch(userId: string, extracted: ResumeProfileExtraction): UpsertUserProfileInput {
  const now = Date.now();
  return {
    user_id: userId,
    profile_version: 1,
    target_roles: uniqueStrings(extracted.target_roles, 5),
    target_industries: uniqueStrings(extracted.target_industries, 5),
    preferred_cities: uniqueStrings(extracted.preferred_cities, 5),
    years_of_experience: extracted.years_of_experience,
    core_skill_tags: uniqueStrings(extracted.core_skill_tags, 12),
    weak_skill_tags: uniqueStrings(extracted.weak_skill_tags, 8),
    certifications: compactText(extracted.certifications, 300),
    resume_focus_summary: compactText(extracted.resume_focus_summary, 500),
    constraints_summary: compactText(extracted.constraints_summary, 300),
    last_active_at: now,
    updated_at: now,
  };
}

export class ResumeIngestionService {
  private llm = getLLMClient();

  private async extractPdfText(buffer: Buffer): Promise<string> {
    const parser = new PDFParse({ data: new Uint8Array(buffer) });
    try {
      const result = await parser.getText();
      return result.text.trim();
    } finally {
      await parser.destroy();
    }
  }

  private async extractProfile(resumeText: string): Promise<ResumeProfileExtraction> {
    const prompt = buildResumeProfileExtractPrompt(resumeText);
    return this.llm.chatJSON<ResumeProfileExtraction>(
      [{ role: 'user', content: prompt }],
      (raw) => {
        try {
          const json = JSON.parse(raw);
          const parsed = ResumeProfileExtractionSchema.safeParse(json);
          return parsed.success ? parsed.data : null;
        } catch {
          return null;
        }
      },
      '简历画像提取',
    );
  }

  async ingest(input: ResumeIngestionInput): Promise<ResumeIngestionResult> {
    log.info('开始导入 PDF 简历', {
      userId: input.userId,
      filename: input.filename,
      source: input.source,
    });

    const extractedText = await this.extractPdfText(input.buffer);
    if (!extractedText) {
      throw new Error('PDF 未提取到有效文本，请确认简历内容可复制或未加密。');
    }

    const profile = await this.extractProfile(extractedText);
    const profilePatch = normalizeProfilePatch(input.userId, profile);
    const writeResult = await profileMemoryService.upsert(profilePatch);

    if (!writeResult.success) {
      throw new Error(writeResult.error || '写入 user_profile 失败');
    }

    return {
      filename: input.filename,
      source: input.source,
      extractedText,
      profilePatch,
      writeResult,
    };
  }
}

export const resumeIngestionService = new ResumeIngestionService();
