import axios from 'axios';
import { feishuAuth } from './auth';
import { config } from '../../config';
import { createLogger } from '../../utils/logger';
import { FEISHU_API_BASE } from '../../constants';
import type { JDParsed, InterviewQuestion } from '../../types';

const log = createLogger('FeishuDoc');

/**
 * 飞书文档服务
 *
 * 使用飞书文档 API 创建文档并写入格式化内容
 * 文档：https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/create
 */
export class FeishuDocumentService {
  private folderToken: string;

  constructor() {
    this.folderToken = config.feishu.docFolderToken;
  }

  /**
   * 创建面试准备文档
   * 返回文档链接
   */
  async createInterviewPrepDoc(params: {
    jdParsed: JDParsed;
    jobSummary: string;
    resumeSuggestions: string[];
    interviewQuestions: InterviewQuestion[];
  }): Promise<{ docUrl: string; documentId: string }> {
    const { jdParsed, jobSummary, resumeSuggestions, interviewQuestions } = params;

    const docTitle = `面试准备 - ${jdParsed.company_name} - ${jdParsed.job_title}`;
    log.info('创建面试准备文档', { title: docTitle });

    try {
      const headers = await feishuAuth.getAuthHeaders();

      // Step 1: 创建空文档
      const createResp = await axios.post(
        `${FEISHU_API_BASE}/docx/v1/documents`,
        {
          title: docTitle,
          folder_token: this.folderToken || undefined,
        },
        { headers, timeout: 15000 },
      );

      if (createResp.data.code !== 0) {
        throw new Error(`文档创建失败: code=${createResp.data.code}, msg=${createResp.data.msg}`);
      }

      const documentId = createResp.data.data?.document?.document_id;
      if (!documentId) {
        throw new Error('文档创建成功但未返回 document_id');
      }

      log.info(`空文档创建成功: documentId=${documentId}`);

      // Step 2: 向文档中写入内容块
      await this.writeDocContent(documentId, headers, {
        jdParsed,
        jobSummary,
        resumeSuggestions,
        interviewQuestions,
      });

      // 文档链接格式
      const docUrl = `https://feishu.cn/docx/${documentId}`;
      log.info(`面试准备文档创建完成: ${docUrl}`);

      return { docUrl, documentId };
    } catch (err) {
      log.error('创建面试准备文档异常', err instanceof Error ? err.message : err);
      throw err;
    }
  }

  /**
   * 向文档写入结构化内容
   * 使用飞书文档 block API 逐步写入
   */
  private async writeDocContent(
    documentId: string,
    headers: Record<string, string>,
    params: {
      jdParsed: JDParsed;
      jobSummary: string;
      resumeSuggestions: string[];
      interviewQuestions: InterviewQuestion[];
    },
  ): Promise<void> {
    const { jdParsed, jobSummary, resumeSuggestions, interviewQuestions } = params;

    // 构建文档内容文本块列表
    // 使用飞书文档 API 的 batch_create_block 接口
    const blocks = this.buildDocBlocks(jdParsed, jobSummary, resumeSuggestions, interviewQuestions);

    try {
      // 获取文档根 block_id（即 document_id 本身作为根节点）
      const url = `${FEISHU_API_BASE}/docx/v1/documents/${documentId}/blocks/${documentId}/children`;

      // 分批写入，每次最多 50 个 block
      const batchSize = 50;
      for (let i = 0; i < blocks.length; i += batchSize) {
        const batch = blocks.slice(i, i + batchSize);
        await axios.post(
          url,
          {
            children: batch,
            index: i === 0 ? 0 : -1, // 第一批放在开头，之后追加到末尾
          },
          { headers, timeout: 15000 },
        );
      }

      log.info(`文档内容写入成功: ${blocks.length} 个内容块`);
    } catch (err) {
      log.warn('文档内容写入部分失败，文档已创建但内容可能不完整', err instanceof Error ? err.message : err);
      // 不抛出错误 — 文档已创建，内容写入失败属于降级
    }
  }

  /**
   * 构建飞书文档内容块
   * 参考：https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document-block-children/batch_create
   */
  private buildDocBlocks(
    jdParsed: JDParsed,
    jobSummary: string,
    resumeSuggestions: string[],
    interviewQuestions: InterviewQuestion[],
  ): DocBlock[] {
    const blocks: DocBlock[] = [];

    // --- 第 1 节：岗位信息 ---
    blocks.push(this.heading2Block('📌 岗位信息'));
    blocks.push(this.textBlock(`公司：${jdParsed.company_name}`));
    blocks.push(this.textBlock(`岗位：${jdParsed.job_title}`));
    blocks.push(this.textBlock(`地点：${jdParsed.location || '未注明'}`));
    blocks.push(this.textBlock(`级别：${jdParsed.seniority || '未注明'}`));
    blocks.push(this.textBlock(`核心技能：${jdParsed.key_skills.join('、') || '未提取'}`));

    // --- 第 2 节：岗位要求总结 ---
    blocks.push(this.heading2Block('📋 岗位要求总结'));
    blocks.push(this.textBlock(jobSummary));

    // --- 第 3 节：简历修改建议 ---
    blocks.push(this.heading2Block('✏️ 简历修改建议'));
    for (let i = 0; i < resumeSuggestions.length; i++) {
      blocks.push(this.textBlock(`${i + 1}. ${resumeSuggestions[i]}`));
    }

    // --- 第 4 节：可能面试题 ---
    blocks.push(this.heading2Block('🎯 可能面试题'));
    for (let i = 0; i < interviewQuestions.length; i++) {
      const q = interviewQuestions[i];
      blocks.push(this.textBlock(`【问题 ${i + 1}】${q.question}`));
      blocks.push(this.textBlock(`出题意图：${q.intent}`));
      blocks.push(this.textBlock(`回答要点：${q.answer_tips.join('；')}`));
      blocks.push(this.textBlock('')); // 空行分隔
    }

    // --- 第 5 节：准备清单 ---
    blocks.push(this.heading2Block('✅ 你的准备清单'));
    blocks.push(this.textBlock('□ 根据建议更新简历'));
    blocks.push(this.textBlock('□ 准备每道面试题的答案'));
    blocks.push(this.textBlock('□ 了解公司背景和业务'));
    blocks.push(this.textBlock('□ 准备自我介绍'));
    blocks.push(this.textBlock('□ 准备向面试官提问的问题'));

    // --- 第 6 节：后续跟进 ---
    blocks.push(this.heading2Block('📅 后续跟进行动'));
    blocks.push(this.textBlock('1. 投递简历'));
    blocks.push(this.textBlock('2. 3 个工作日内关注反馈'));
    blocks.push(this.textBlock('3. 无反馈则尝试联系 HR'));
    blocks.push(this.textBlock('4. 面试后 24 小时内发感谢邮件'));

    return blocks;
  }

  /** 生成标题块（heading2） */
  private heading2Block(text: string): DocBlock {
    return {
      block_type: 4, // heading2
      heading2: {
        elements: [{ text_run: { content: text } }],
      },
    };
  }

  /** 生成文本块（paragraph） */
  private textBlock(text: string): DocBlock {
    return {
      block_type: 2, // text
      text: {
        elements: [{ text_run: { content: text } }],
      },
    };
  }
}

// ===== 飞书文档 block 类型 =====
interface DocBlockElement {
  text_run: { content: string; text_element_style?: Record<string, unknown> };
}

interface DocBlock {
  block_type: number;
  text?: { elements: DocBlockElement[] };
  heading2?: { elements: DocBlockElement[] };
}

  /**
   * 读取飞书云文档，返回 Markdown 字符串
   *
   * 调用飞书 docx v1 blocks API，将文档 block 结构转换为 Markdown 文本。
   * 支持分页（page_token 循环）。
   *
   * @param docToken 飞书云文档 token（document_id）
   */
  async readDocAsMarkdown(docToken: string): Promise<string> {
    log.info('读取飞书云文档', { docToken });
    const headers = await feishuAuth.getAuthHeaders();

    const allBlocks: FeishuBlock[] = [];
    let pageToken: string | undefined;

    // 分页拉取所有 block
    do {
      const params: Record<string, string> = { document_revision_id: '-1', page_size: '100' };
      if (pageToken) params['page_token'] = pageToken;

      const queryString = new URLSearchParams(params).toString();
      const resp = await axios.get(
        `${FEISHU_API_BASE}/docx/v1/documents/${docToken}/blocks?${queryString}`,
        { headers, timeout: 15000 },
      );

      if (resp.data.code !== 0) {
        throw new Error(
          `飞书文档读取失败: code=${resp.data.code}, msg=${resp.data.msg}`,
        );
      }

      const items: FeishuBlock[] = resp.data.data?.items ?? [];
      allBlocks.push(...items);
      pageToken = resp.data.data?.has_more ? resp.data.data.page_token : undefined;
    } while (pageToken);

    log.info(`文档块读取完成: ${allBlocks.length} 个 block`, { docToken });
    return blocksToMarkdown(allBlocks);
  }
}

// ===== 飞书 block 转 Markdown =====

interface FeishuBlockElement {
  text_run?: { content: string };
  mention_user?: { user_id: string; name?: string };
  mention_doc?: { url: string; title?: string };
  code?: { content: string; language?: string };
}

interface FeishuBlock {
  block_type: number;
  block_id?: string;
  // 各 block_type 对应的内容字段
  text?: { elements: FeishuBlockElement[]; style?: { list?: { type?: string } } };
  heading1?: { elements: FeishuBlockElement[] };
  heading2?: { elements: FeishuBlockElement[] };
  heading3?: { elements: FeishuBlockElement[] };
  heading4?: { elements: FeishuBlockElement[] };
  heading5?: { elements: FeishuBlockElement[] };
  code?: { elements: FeishuBlockElement[]; style?: { language?: string } };
  quote?: { elements: FeishuBlockElement[] };
  bullet?: { elements: FeishuBlockElement[] };
  ordered?: { elements: FeishuBlockElement[] };
  // ordered list index maintained externally
  [key: string]: unknown;
}

/** 从 block elements 中提取纯文本 */
function elementsToText(elements?: FeishuBlockElement[]): string {
  if (!elements) return '';
  return elements
    .map((el) => {
      if (el.text_run) return el.text_run.content;
      if (el.mention_user) return `@${el.mention_user.name ?? el.mention_user.user_id}`;
      if (el.mention_doc) return `[${el.mention_doc.title ?? el.mention_doc.url}](${el.mention_doc.url})`;
      return '';
    })
    .join('');
}

/**
 * 将飞书 docx block 列表转换为 Markdown 文本
 *
 * 支持的 block_type：
 *  2 = text/paragraph
 *  3 = heading1, 4 = heading2, 5 = heading3, 6 = heading4, 7 = heading5
 *  9 = ordered list, 10 = bullet list
 * 11 = code block
 * 14 = quote
 * 22 = horizontal rule
 */
function blocksToMarkdown(blocks: FeishuBlock[]): string {
  const lines: string[] = [];
  let orderedIndex = 1;

  for (const block of blocks) {
    switch (block.block_type) {
      case 1: // page block — root, ignore or treat as title
        break;

      case 2: { // text / paragraph
        const text = elementsToText(block.text?.elements);
        lines.push(text);
        break;
      }

      case 3: // heading1
        lines.push(`# ${elementsToText(block.heading1?.elements)}`);
        orderedIndex = 1;
        break;
      case 4: // heading2
        lines.push(`## ${elementsToText(block.heading2?.elements)}`);
        orderedIndex = 1;
        break;
      case 5: // heading3
        lines.push(`### ${elementsToText(block.heading3?.elements)}`);
        orderedIndex = 1;
        break;
      case 6: // heading4
        lines.push(`#### ${elementsToText((block.heading4 as { elements?: FeishuBlockElement[] })?.elements)}`);
        break;
      case 7: // heading5
        lines.push(`##### ${elementsToText((block.heading5 as { elements?: FeishuBlockElement[] })?.elements)}`);
        break;

      case 9: // ordered list
        lines.push(`${orderedIndex}. ${elementsToText(block.ordered?.elements)}`);
        orderedIndex++;
        break;

      case 10: // bullet list
        lines.push(`- ${elementsToText(block.bullet?.elements)}`);
        orderedIndex = 1;
        break;

      case 11: { // code block
        const lang = (block.code as { style?: { language?: string } })?.style?.language ?? '';
        const codeText = elementsToText((block.code as { elements?: FeishuBlockElement[] })?.elements);
        lines.push(`\`\`\`${lang}\n${codeText}\n\`\`\``);
        break;
      }

      case 14: // quote
        lines.push(`> ${elementsToText(block.quote?.elements)}`);
        break;

      case 22: // horizontal rule
        lines.push('---');
        break;

      default:
        // 未知 block 类型，尝试提取 text elements
        break;
    }
  }

  return lines.join('\n\n').trim();
}

export const feishuDocumentService = new FeishuDocumentService();
